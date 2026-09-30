"""Item 151: mobile parity is retrieved, not inferred.

The fixtures are seeded reproductions of the two sites the item names, served
from 127.0.0.1 - neither is fetched. Birch's case: Googlebot-smartphone served
a body 60% smaller than a browser's, title and description intact
(533,687 -> 216,745 bytes). Acme's: byte-identical across all three agents,
one hash.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from clauditseo.crawler import parity
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import Page, TierBudget
from clauditseo.engine.types import Tier

FAST = TierBudget(max_pages=40, request_timeout_s=5, wall_clock_s=60, delay_s=0)

_HEAD = ('<head><title>Birch Fixture {path}</title>'
         '<meta name="description" content="The same description for every agent.">'
         '<link rel="canonical" href="{canon}"></head>')
_COPY = " ".join(f"word{i}" for i in range(300))


def _page(path: str, links: list[str], padding: int = 0) -> str:
    anchors = "".join(f'<a href="{href}">{href}</a>' for href in links)
    pad = f"<script>var x='{'a' * padding}';</script>" if padding else ""
    return (f"<html>{_HEAD.format(path=path, canon=path)}<body>{pad}"
            f"<main><h1>Heading {path}</h1><p>{_COPY}</p>{anchors}</main></body></html>")


class _AgentSite:
    """A fixture site that can answer each user agent differently.
    `body(path, ua)` returns the HTML or None for a 404; every request is
    logged with its user agent."""

    def __init__(self, body):
        self.log: list[tuple[str, str]] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                ua = self.headers.get("User-Agent") or ""
                site.log.append((self.path, ua))
                if self.path == "/robots.txt":
                    payload, ctype = b"User-agent: *\nAllow: /\n", "text/plain"
                else:
                    html = body(self.path, ua)
                    if html is None:
                        self.send_response(404); self.end_headers(); return
                    payload, ctype = html.encode("utf-8"), "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self):
        self._thread.start(); return self

    def __exit__(self, *a):
        self._server.shutdown(); self._server.server_close()


_PATHS = ["/", "/services", "/about"]


def _links(path):
    return [p for p in _PATHS if p != path]


def _acme(path, ua):
    return _page(path, _links(path)) if path in _PATHS else None


def _birch(path, ua):
    """Googlebot gets the same copy, links and head in a far lighter body."""
    if path not in _PATHS:
        return None
    if "Googlebot" in ua:
        return _page(path, _links(path))
    return _page(path, _links(path), padding=8000)


def _doc(html: str, url="https://x.test/", status=200) -> dict:
    return parity.document(Page(url=url, requested_url=url, status=status,
                                content=html, content_type="text/html"))


def test_the_probe_compares_the_document_not_a_field_list():
    six = [f"/s{n}" for n in range(6)]
    doc = _doc(_page("/", six))
    for key in ("status", "final_url", "bytes", "main_hash", "words", "internal_links",
                "jsonld_blocks", "jsonld_hash",
                "title", "meta_description", "canonical", "meta_robots", "h1"):
        assert key in doc, key
    # Same title, description, canonical, robots and h1 - a field list calls
    # this clean. Half the copy and none of the links is not the same document.
    thin = _doc(_page("/", []).replace(_COPY, " ".join(_COPY.split()[:100])))
    got = parity.compare(doc, thin)
    assert got["named"] == []
    assert got["verdict"] == "size"
    assert {s["field"] for s in got["size"]} >= {"words", "internal_links", "main_hash"}
    # And a named field is named.
    retitled = _doc(_page("/", six).replace("Birch Fixture", "Other"))
    assert parity.compare(doc, retitled)["verdict"] == "named"
    assert parity.compare(doc, retitled)["named"][0]["field"] == "title"


def test_a_size_only_divergence_still_raises():
    with _AgentSite(_birch) as s:
        cr = crawl(s.base + "/", Tier.T1, budget=FAST, mobile_parity=True)
    block = cr.mobile_parity
    assert block["probed"] == 3
    assert block["device"]["verdict"] == "no divergence"
    assert block["bot"]["verdict"] == "divergence"
    row = block["pages"][0]
    assert row["bot"]["verdict"] == "size" and row["bot"]["named"] == []
    assert [x["field"] for x in row["bot"]["size"]] == ["bytes"]
    docs = row["documents"]
    assert docs["googlebot-smartphone"]["bytes"] < docs["iphone"]["bytes"] * 0.6
    assert docs["googlebot-smartphone"]["title"] == docs["desktop"]["title"]
    assert block["statement"] == "mobile parity: divergence on 3 of 3 page(s)"


def test_byte_identical_across_agents_raises_nothing():
    with _AgentSite(_acme) as s:
        cr = crawl(s.base + "/", Tier.T1, budget=FAST, mobile_parity=True)
    block = cr.mobile_parity
    for row in block["pages"]:
        docs = row["documents"]
        assert len({d["main_hash"] for d in docs.values()}) == 1
        assert len({d["bytes"] for d in docs.values()}) == 1
        assert row["device"]["verdict"] == row["bot"]["verdict"] == "same"
    assert block["device"]["verdict"] == block["bot"]["verdict"] == "no divergence"
    assert parity.diverged(block) is False


def test_a_negative_parity_result_is_stored_not_discarded():
    with _AgentSite(_acme) as s:
        cr = crawl(s.base + "/", Tier.T1, budget=FAST, mobile_parity=True)
    stored = snapshot(cr)["mobile_parity"]
    assert stored["statement"] == "mobile parity: no divergence across 3 page(s)"
    assert stored["probed"] == 3 and len(stored["pages"]) == 3
    assert stored["javascript_executed"] is False
    # Not asked for is None, which is not the same as probed-and-clean.
    with _AgentSite(_acme) as s:
        plain = crawl(s.base + "/", Tier.T1, budget=FAST)
    assert snapshot(plain)["mobile_parity"] is None


def _many(path, ua):
    """Forty pages over eight URL templates, every page linked from home."""
    paths = [f"/t{t}/p{n}" for t in range(8) for n in range(5)]
    if path == "/":
        return _page("/", paths)
    return _page(path, ["/"]) if path in paths else None


def test_the_probe_does_not_multiply_the_tier_page_budget():
    with _AgentSite(_many) as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST, mobile_parity=True)
    probe_agents = {ua for _key, ua in parity.PARITY_AGENTS}
    probed = [p for p, ua in s.log if ua in probe_agents]
    assert len(cr.pages) > parity.SAMPLE_CAP * 3
    assert len(probed) == cr.mobile_parity["fetches"] <= 3 * parity.SAMPLE_CAP
    assert cr.mobile_parity["pages"][0]["url"].endswith("/")       # home first
    # Full mode - a site whose previous run diverged - probes every readable page.
    with _AgentSite(_many) as s:
        full = crawl(s.base + "/", Tier.T2, budget=FAST, mobile_parity="full")
    assert full.mobile_parity["mode"] == "full"
    assert full.mobile_parity["probed"] == len(full.pages)


def test_a_verification_never_probes():
    with _AgentSite(_acme) as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST, mobile_parity=True,
                   only_urls=[s.base + "/about"])
    assert cr.mobile_parity is None


def test_a_failed_fetch_is_not_a_divergence():
    ok = _doc(_page("/", _links("/")))
    down = parity.document(Page(url="https://x.test/", requested_url="https://x.test/",
                                status=0, error="ConnectTimeout"))
    assert parity.compare(ok, down)["verdict"] == "not_assessed"
    # A refusal is: Googlebot answered 403 where the browser got the page.
    refused = parity.document(Page(url="https://x.test/", requested_url="https://x.test/",
                                   status=403, content="no", content_type="text/html"))
    assert parity.compare(ok, refused)["verdict"] == "named"


# --- the checks TEC raises from the stored block ------------------------------

def _findings(block):
    from clauditseo.crawler.types import CrawlResult
    from clauditseo.modules.tec import TechnicalModule
    cr = CrawlResult(start_url="https://x.test/", tier=Tier.T1)
    cr.mobile_parity = block
    return {f.check_id: f for f in TechnicalModule()._parity(cr)}


def _block_for(body):
    with _AgentSite(body) as s:
        return crawl(s.base + "/", Tier.T1, budget=FAST, mobile_parity=True).mobile_parity


def test_tribes_lighter_bot_body_is_the_medium_size_check_not_bot_parity():
    got = _findings(_block_for(_birch))
    assert set(got) == {"mobile-parity-size"}
    f = got["mobile-parity-size"]
    assert f.severity.name == "MEDIUM" and f.affected_total == 3
    assert f.evidence["pages"][0]["pair"] == "googlebot-smartphone vs iphone"
    assert set(f.evidence["pages"][0]["differs"]) == {"bytes"}


def test_bizcaps_identical_documents_raise_no_parity_check():
    assert _findings(_block_for(_acme)) == {}


def test_less_copy_or_fewer_links_for_googlebot_is_bot_parity():
    def body(path, ua):
        if path not in _PATHS:
            return None
        if "Googlebot" in ua:
            return _page(path, []).replace(_COPY, "short")
        return _page(path, _links(path) + [f"/x{n}" for n in range(6)])
    got = _findings(_block_for(body))
    assert "bot-parity" in got and "mobile-parity" not in got
    assert got["bot-parity"].severity.name == "HIGH"
    assert {"words", "internal_links"} <= set(got["bot-parity"].evidence["pages"][0]["differs"])


def test_a_retitled_phone_document_is_mobile_parity():
    def body(path, ua):
        if path not in _PATHS:
            return None
        html = _page(path, _links(path))
        return html.replace("Birch Fixture", "Mobile") if "iPhone" in ua else html
    got = _findings(_block_for(body))
    assert got["mobile-parity"].severity.name == "HIGH"
    assert "title" in got["mobile-parity"].summary


def test_the_finding_states_that_javascript_was_not_executed():
    f = _findings(_block_for(_birch))["mobile-parity-size"]
    assert "No JavaScript was executed" in f.summary
    assert f.evidence["javascript_executed"] is False
    assert "client-side" in f.evidence["basis"]


def test_the_parity_checks_are_registered_free_on_crawl_and_versioned():
    from clauditseo import anatomy, playbook
    from clauditseo.checks import check_costs
    from clauditseo.modules import tec
    costs = check_costs()
    crawl_tool = next(t for phase in playbook.PLAYBOOK for t in phase["tools"]
                      if t["id"] == "crawl")
    for check in ("mobile-parity", "mobile-parity-size", "bot-parity"):
        assert costs[f"TEC/{check}"] == "free"
        assert anatomy.categorise(check, "TEC") == "crawl"
        assert tec.COLLECTED_SINCE[check] == "0.27.0"
        assert check in tec.PARITY_CHECKS and check in crawl_tool["checks"]


def test_a_run_without_the_probe_reads_parity_as_not_assessed(tmp_path):
    import json
    from clauditseo import ENGINE_VERSION
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "clauditseo.db")
    migrate(conn)
    op_id = repo.ensure_default_operator(conn, "Item 151")
    site_id = repo.create_site(conn, repo.create_client(conn, op_id, "Co"), "x.test")
    checks = {"crawl": ["TEC/mobile-parity", "TEC/bot-parity", "TEC/mobile-parity-size"]}

    def plant(evidence):
        run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
        conn.execute("UPDATE audit_runs SET status='complete', crawl_evidence=?,"
                     " engine_version=? WHERE id=?",
                     (json.dumps(evidence), ENGINE_VERSION, run_id))
        conn.commit()
        return runs.not_assessed_payload(conn, run_id, checks_by_part=checks).get("crawl", {})

    page = {"url": "https://x.test/", "status": 200}
    missing = plant({"pages": [page]})
    assert set(missing) == set(checks["crawl"])
    assert "Googlebot-smartphone" in missing["TEC/bot-parity"]
    clean = plant({"pages": [page], "mobile_parity": _block_for(_acme)})
    assert not set(clean) & set(checks["crawl"])
    conn.close()


# --- the site's next run ------------------------------------------------------

def test_a_site_that_diverged_is_probed_in_full_on_its_next_run(tmp_path):
    import json
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "clauditseo.db")
    migrate(conn)
    op_id = repo.ensure_default_operator(conn, "Item 151")
    site_id = repo.create_site(conn, repo.create_client(conn, op_id, "Co"), "x.test")
    assert runs.parity_mode(conn, site_id) is True          # a first run samples

    def finished(block):
        run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
        conn.execute("UPDATE audit_runs SET status='complete', composite_score=50,"
                     " kind='audit', scan_scope='site', crawl_evidence=? WHERE id=?",
                     (json.dumps({"pages": [], "mobile_parity": block}), run_id))
        conn.commit()
        return run_id

    finished(_block_for(_birch))
    assert runs.parity_mode(conn, site_id) == "full"
    clean = finished(_block_for(_acme))
    assert runs.parity_mode(conn, site_id) is True
    # Asked about the run after the clean one, the clean one decides; asked
    # about the clean one itself, the diverged one before it does.
    assert runs.parity_mode(conn, site_id, clean) == "full"
    finished(None)                                          # from before 0.27.0
    assert runs.parity_mode(conn, site_id) is True
    conn.close()


def test_both_audit_paths_ask_for_the_probe():
    import inspect
    from clauditseo import adaptive
    from clauditseo.api import app as _app
    src = inspect.getsource(adaptive.run_adaptive)
    assert src.count("mobile_parity=parity") == 2, "the pulse and the deep crawl"
    assert "mobile_parity=runs.parity_mode(" in inspect.getsource(_app._execute_run)


# --- the crawl brief reads it -------------------------------------------------

def _crawl_brief(ev):
    from clauditseo.analysts.expert import build_context
    from clauditseo.engine.types import Site
    return build_context("crawl", ev, Site(domain="127.0.0.1"))["UA_MATRIX"]


def test_the_crawl_brief_is_told_what_the_probe_found_clean_or_not():
    with _AgentSite(_birch) as s:
        birch = snapshot(crawl(s.base + "/", Tier.T1, budget=FAST, mobile_parity=True))
    text = _crawl_brief(birch)
    assert "mobile parity: divergence on 3 of 3 page(s)" in text
    assert "size: bytes (vs iphone)" in text
    assert "No JavaScript was executed" in text
    assert "This analysis does not emit them" in text
    # A T1 pulse has no UA matrix; the parity result still reaches the brief.
    assert "no crawler access test on this crawl" in text

    with _AgentSite(_acme) as s:
        clean = snapshot(crawl(s.base + "/", Tier.T1, budget=FAST, mobile_parity=True))
    assert "mobile parity: no divergence across 3 page(s)" in _crawl_brief(clean)


def test_a_run_without_the_probe_tells_the_brief_parity_was_not_assessed():
    with _AgentSite(_acme) as s:
        plain = snapshot(crawl(s.base + "/", Tier.T1, budget=FAST))
    text = _crawl_brief(plain)
    assert "did not fetch pages as a phone and as Googlebot-smartphone" in text
    assert "Do not assume it" in text


def test_structured_data_served_to_one_agent_only_is_a_difference():
    """Item 153's third question. Birch's own diff found one identical WebSite
    block for every agent; this is the case it was checking for."""
    block = '<script type="application/ld+json">{"@type": "Organization"}</script>'
    plain = _page("/", _links("/"))
    extra = plain.replace("</head>", block + "</head>")
    got = parity.compare(_doc(plain), _doc(extra))
    assert got["verdict"] == "size"
    assert [x["field"] for x in got["size"]] == ["structured_data"]
    # Reformatted JSON is the same structured data.
    spaced = plain.replace("</head>", block.replace(": ", ":   ") + "</head>")
    assert parity.compare(_doc(extra), _doc(spaced))["verdict"] == "same"


# --- the Crawl part's "now" payload (server half; the page is 162's) ---------

def _now_for(tmp_path, block, finding=None):
    import json
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "now.db")
    migrate(conn)
    op_id = repo.ensure_default_operator(conn, "Item 151")
    site_id = repo.create_site(conn, repo.create_client(conn, op_id, "Co"), "x.test")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T1")
    start = block["pages"][0]["url"] if block else "http://127.0.0.1/"
    ev = {"start_url": start, "pages": [],
          **({"mobile_parity": block} if block is not None else {})}
    conn.execute("UPDATE audit_runs SET status='complete', crawl_evidence=? WHERE id=?",
                 (json.dumps(ev), run_id))
    if finding is not None:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
            " source, model_id, confidence, summary, affected_urls, evidence,"
            " recommendation, fingerprint, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("f1", run_id, "TEC", finding.check_id, finding.severity.value,
             "deterministic", None, "high", finding.summary, "[]", "{}", "",
             "fp-f1", "2026-09-15T00:00:00Z"))
    conn.commit()
    try:
        return runs.crawl_now_payload(conn, run_id)["mobile_parity"]
    finally:
        conn.close()


def test_the_crawl_now_payload_is_null_where_the_run_did_not_probe(tmp_path):
    assert _now_for(tmp_path, None) is None


def test_the_crawl_now_payload_carries_a_clean_probe_as_a_measurement(tmp_path):
    got = _now_for(tmp_path, _block_for(_acme))
    assert got["statement"] == "mobile parity: no divergence across 3 page(s)"
    assert got["probed"] == 3 and got["fetches"] == 9
    assert got["device"] == got["bot"] == "no divergence"
    assert got["javascript_executed"] is False and "client-side" in got["covers"]
    assert got["agents"] == ["desktop", "iphone", "googlebot-smartphone"]
    assert [r["path"] for r in got["pages"]][0] == "/"
    assert all(r["device"] == {"verdict": "same", "differs": []} for r in got["pages"])
    assert got["raised"] == {}


def test_the_crawl_now_payload_names_what_differed_and_what_was_raised(tmp_path):
    block = _block_for(_birch)
    finding = _findings(block)["mobile-parity-size"]
    got = _now_for(tmp_path, block, finding)
    row = got["pages"][0]
    assert row["bot"]["verdict"] == "size" and row["bot"]["compared_with"] == "iphone"
    assert [d["field"] for d in row["bot"]["differs"]] == ["bytes"]
    assert row["agents"]["googlebot-smartphone"]["bytes"] < row["agents"]["iphone"]["bytes"]
    # Hashes and head fields stay in the evidence, not on the screen's row.
    assert set(row["agents"]["desktop"]) == {"status", "bytes"}
    assert got["raised"]["mobile-parity-size"]["severity"] == finding.severity.value
