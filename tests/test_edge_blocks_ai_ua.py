"""`AIS/edge-blocks-ai-ua`: the edge refuses an AI agent robots.txt permits
(item 145, brief v22 step BG, step 4; channel rulings 20260915-0520 and
20260915-1430, the second adding the operator's per-agent edge declaration).

The twenty22 case from the addendum: training agents told no in robots.txt
(a stated policy), and Claude-SearchBot, OAI-SearchBot and MistralAI-User
refused at the edge with no rule saying so (an unstated block). The two
render as two things: `TEC/ai-crawler-blocked` rows and `AIS/edge-blocks-ai-ua`
rows. The search agents' refusals stay `TEC/ua-server-refusal`'s, so one
refusal is one row.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, TierBudget
from clauditseo.engine.types import Severity, Site, Tier
from clauditseo.modules.ais import AiSurfaceModule, edge_blocks
from clauditseo.modules.tec import TechnicalModule

FAST = TierBudget(max_pages=12, request_timeout_s=5, wall_clock_s=60, delay_s=0)

_TRAINING_TOLD_NO = ("GPTBot", "ClaudeBot", "CCBot", "Bytespider",
                     "Meta-ExternalAgent", "Amazonbot", "PetalBot")
_ROBOTS = ("User-agent: *\nAllow: /\n\n"
           + "".join(f"User-agent: {a}\nDisallow: /\n\n" for a in _TRAINING_TOLD_NO))
_HOME = ("<html><head><title>Twenty22 fixture home</title></head><body><h1>Home</h1>"
         + "<p>Real copy that a reader would lift an answer from, repeated. </p>" * 20
         + '<a href="/a">a</a><a href="/b">b</a></body></html>')
_PAGE = "<html><head><title>Page {n}</title></head><body><h1>{n}</h1>" + "<p>Copy.</p>" * 30 + "</body></html>"


class _Edge:
    """A fixture edge: `refuse` UA substrings get a 403 with a Cloudflare
    signature, `challenge` ones a 200 carrying `cf-mitigated: challenge` and a
    stub body, `stub` ones a plain 200 with a stub body."""

    def __init__(self, refuse=(), challenge=(), stub=()):
        routes = {"/robots.txt": ("text/plain", _ROBOTS), "/": ("text/html", _HOME),
                  "/a": ("text/html", _PAGE.format(n="A")), "/b": ("text/html", _PAGE.format(n="B"))}
        lower = lambda xs: tuple(x.lower() for x in xs)  # noqa: E731
        refuse, challenge, stub = lower(refuse), lower(challenge), lower(stub)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                ua = (self.headers.get("User-Agent") or "").lower()
                entry = routes.get(self.path)
                if entry is None:
                    self.send_response(404); self.end_headers(); return
                ctype, body = entry
                if self.path != "/robots.txt":
                    if any(r in ua for r in refuse):
                        self.send_response(403)
                        self.send_header("Server", "cloudflare")
                        self.send_header("CF-RAY", "abc123")
                        self.end_headers(); return
                    if any(c in ua for c in challenge) or any(s in ua for s in stub):
                        body = "<html><body>Just a moment...</body></html>"
                payload = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                if any(c in ua for c in challenge) and self.path != "/robots.txt":
                    self.send_header("cf-mitigated", "challenge")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self):
        self._thread.start(); return self

    def __exit__(self, *a):
        self._server.shutdown(); self._server.server_close()


def _twenty22(policy="block", declared=(), **edge):
    edge.setdefault("refuse", ("Claude-SearchBot", "OAI-SearchBot", "MistralAI-User"))
    with _Edge(**edge) as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True)
    site = Site(domain="twenty22.test", ai_crawler_policy=policy,
                ai_edge_blocked_agents=",".join(declared) or None)
    ctx = {"crawl": cr, "site": site}
    found = (TechnicalModule().run(cr.pages, Tier.T2, ctx)
             + AiSurfaceModule().run(cr.pages, Tier.T2, ctx))
    return cr, found


def test_edge_block_on_an_index_agent_reads_as_visibility():
    _cr, found = _twenty22()
    edge = {f.evidence["agent"]: f for f in found if f.check_id == "edge-blocks-ai-ua"}
    assert set(edge) == {"Claude-SearchBot", "OAI-SearchBot", "MistralAI-User"}, sorted(edge)
    row = edge["Claude-SearchBot"]
    assert row.dimension == "AIS" and row.severity is Severity.HIGH
    assert row.evidence["class"] == "index"
    assert "absent from its results" in row.summary, row.summary
    first = row.evidence["responses"][0]
    assert first["status"] == 403 and first["signature"].get("cf-ray") == "abc123"
    assert edge["MistralAI-User"].evidence["class"] == "answer-time"
    assert "cannot look" in edge["MistralAI-User"].summary


def test_a_toggled_training_block_and_an_unstated_index_block_are_two_rows():
    # twenty22 as measured (run 384ac68e): the edge refuses the toggled
    # training agents and the untoggled index agents alike. Only the
    # operator's declaration tells them apart (channel 20260915-1430). This
    # fixture's robots.txt tells the training agents no, so the declared one
    # here is an agent robots permits.
    _cr, found = _twenty22(refuse=("PerplexityBot", "Claude-SearchBot"), declared=("PerplexityBot",))
    edge = {f.evidence["agent"]: f for f in found if f.check_id == "edge-blocks-ai-ua"}
    chosen, unstated = edge["PerplexityBot"], edge["Claude-SearchBot"]
    assert chosen.severity is Severity.LOW and chosen.evidence["declared"] is True
    assert unstated.severity is Severity.HIGH and unstated.evidence["declared"] is False
    assert chosen.fingerprint != unstated.fingerprint
    assert "blocked at the firewall deliberately" in chosen.summary
    assert "unverified IP" in unstated.summary
    # And the robots.txt half stays its own check, LOW under the stated policy.
    told = [f for f in found if f.check_id == "ai-crawler-blocked"]
    assert {f.evidence["agent"] for f in told} == set(_TRAINING_TOLD_NO)
    assert all(f.severity is Severity.LOW for f in told)


def test_an_edge_that_passes_search_uas_and_refuses_ai_uas_is_a_measured_block():
    cr, found = _twenty22(refuse=("Claude-SearchBot",))
    # Same vantage point: the search agent got through, the AI agent did not.
    assert next(r for r in cr.ua_matrix if r["agent"] == "Googlebot")["home_status"] == 200
    edge = [f for f in found if f.check_id == "edge-blocks-ai-ua"]
    assert len(edge) == 1 and edge[0].severity is Severity.HIGH
    assert edge[0].confidence.name == "HIGH", "a sweep measurement states no lowered confidence"
    assert edge[0].evidence["vantage"] == "unverified-ip" and edge[0].evidence["field"] == "not pulled"
    assert "whether the vendor's real crawler is exempted at the firewall is not measurable" in edge[0].summary


def test_a_declared_edge_block_is_the_policy_working():
    from clauditseo.checks import is_blocker
    _cr, found = _twenty22(declared=("OAI-SearchBot",))
    row = next(f for f in found if f.check_id == "edge-blocks-ai-ua" and f.evidence["agent"] == "OAI-SearchBot")
    assert row.severity is Severity.LOW and row.evidence["declared"] is True
    assert "policy working" in row.summary
    assert not is_blocker("AIS/edge-blocks-ai-ua")


def test_a_disallowed_agent_is_not_an_edge_block_even_when_refused():
    _cr, found = _twenty22(refuse=("GPTBot",))
    assert not any(f.check_id == "edge-blocks-ai-ua" for f in found)


def test_a_search_agent_refusal_is_not_this_check():
    _cr, found = _twenty22(refuse=("Googlebot", "bingbot"))
    edge = [f.evidence["agent"] for f in found if f.check_id == "edge-blocks-ai-ua"]
    # Googlebot's UA string is also the substring of no AI agent's, so nothing.
    assert "Googlebot" not in edge and "Bingbot" not in edge, edge


def test_a_challenge_or_a_stub_body_at_200_is_an_edge_block():
    _cr, found = _twenty22(refuse=(), challenge=("PerplexityBot",), stub=("DuckAssistBot",))
    edge = {f.evidence["agent"]: f.evidence["responses"][0]["reason"]
            for f in found if f.check_id == "edge-blocks-ai-ua"}
    assert edge == {"PerplexityBot": "challenge", "DuckAssistBot": "short body"}, edge


def test_a_crawl_with_no_matrix_raises_nothing_and_is_not_assessed(tmp_path):
    assert edge_blocks(CrawlResult(start_url="https://x.test/", tier=Tier.T2)) == []

    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T"), "t.test")
    checks = {"ai-surface": ["AIS/edge-blocks-ai-ua"]}

    def reason(matrix):
        run_id = runs.create_run(conn, site_id, ["AIS", "TEC"], "T2")
        ev = snapshot(CrawlResult(start_url="https://t.test/", tier=Tier.T2))
        if matrix is not None:
            ev["ua_matrix"] = matrix
        runs.store_evidence(conn, run_id, ev)
        return runs.not_assessed_payload(conn, run_id, checks_by_part=checks).get(
            "ai-surface", {}).get("AIS/edge-blocks-ai-ua")

    assert "did not fetch pages as the AI crawlers" in reason(None)
    old = [{"agent": "GPTBot", "robots": "allow", "home_status": 200, "probe_status": []}]
    assert "predates the crawler list" in reason(old)
    new = [dict(old[0], agent_class="training", sent=True)]
    assert reason(new) is None
    conn.close()


def test_the_crawl_analysis_is_told_ua_server_refusal_is_for_search_agents_only():
    from clauditseo.analysts.expert import build_context
    with _Edge(refuse=("Claude-SearchBot",)) as s:
        ev = snapshot(crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True))

    class S:
        domain = "twenty22.test"
        cdn_or_waf = None
    text = build_context("crawl", ev, S())["UA_MATRIX"]
    assert "`ua-server-refusal` is for the search agents only" in text
    line = next(ln for ln in text.splitlines() if ln.startswith("| Claude-SearchBot"))
    assert "edge-blocks-ai-ua" in line and "index" in line, line
