"""The UA matrix and `ua-server-refusal` (item 137, brief v18 step AZ, task 4).

The matrix is new crawler behaviour whose real numbers only come from a live
run; these are the seeded reproductions the operator verifies against
(`137-az-status-and-plan.md`): one matrix row per named agent with its robots
verdict, a refusal told apart from a disallow, the pass gated to T2/site scope,
and `ua-server-refusal` held until a CDN/WAF is named.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.robots import RobotsPolicy
from clauditseo.crawler.types import TierBudget
from clauditseo.crawler.ua_matrix import (UA_MATRIX_AGENTS, UAMatrixRow,
                                          build_ua_matrix, probe_urls)
from clauditseo.engine.types import Tier

FAST = TierBudget(max_pages=12, request_timeout_s=5, wall_clock_s=60, delay_s=0)

_ROBOTS = "User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n"
_HOME = ("<html><head><title>UA Matrix Fixture Home</title>"
         '<meta name="description" content="Home of the UA matrix fixture, with '
         'enough words to be a real indexable page for the crawl.">'
         '</head><body><h1>H</h1><a href="/a">a</a><a href="/b">b</a></body></html>')
_PAGE = ("<html><head><title>UA Matrix Fixture Page {n}</title></head><body>"
         "<h1>{n}</h1><p>Some body copy on page {n} for the crawl to read.</p>"
         "</body></html>")


class _UAServer:
    """A fixture site whose response can depend on the request's User-Agent —
    enough to fake a CDN 403 to one crawler's UA string. `refuse_ua` is a
    substring matched case-insensitively against the User-Agent header."""

    def __init__(self, refuse_ua: str | None = None):
        self.refuse_ua = (refuse_ua or "").lower()
        routes = {
            "/robots.txt": ("text/plain", _ROBOTS),
            "/": ("text/html", _HOME),
            "/a": ("text/html", _PAGE.format(n="A")),
            "/b": ("text/html", _PAGE.format(n="B")),
        }
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                ua = (self.headers.get("User-Agent") or "").lower()
                entry = routes.get(self.path)
                if entry is None:
                    self.send_response(404); self.end_headers(); return
                if (server.refuse_ua and server.refuse_ua in ua
                        and self.path != "/robots.txt"):
                    self.send_response(403)
                    self.send_header("Server", "cloudflare")
                    self.send_header("CF-RAY", "abc123")
                    self.end_headers(); return
                ctype, body = entry
                payload = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):  # keep test output clean
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


def test_one_matrix_row_per_named_agent_with_its_robots_verdict():
    with _UAServer() as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True)
    assert len(cr.ua_matrix) == len(UA_MATRIX_AGENTS)
    by = {m["agent"]: m for m in cr.ua_matrix}
    assert set(by) == {a for a, _ua, _c in UA_MATRIX_AGENTS}
    assert by["GPTBot"]["robots"] == "disallow"          # robots blocks it
    assert by["Googlebot"]["robots"] == "allow"
    assert all(m["home_status"] == 200 for m in cr.ua_matrix if m["sent"])


def test_a_server_refusal_is_told_apart_from_a_robots_disallow():
    # The server 403s the CCBot UA; robots disallows GPTBot. Only the first is a
    # ua-server-refusal — the second is the site's own choice, working.
    with _UAServer(refuse_ua="CCBot") as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True)
    by = {m["agent"]: m for m in cr.ua_matrix}
    assert by["CCBot"]["home_status"] == 403
    assert UAMatrixRow(**by["CCBot"]).refused is True
    assert "cf-ray" in by["CCBot"]["headers"], by["CCBot"]["headers"]
    # GPTBot is disallowed by robots, so a 403 (if any) is not a server refusal.
    assert by["GPTBot"]["robots"] == "disallow"
    assert UAMatrixRow(**by["GPTBot"]).refused is False


def test_a_disallowed_agent_is_never_refused():
    row = UAMatrixRow(agent="GPTBot", robots="disallow", home_status=403)
    assert row.refused is False


def test_an_allowed_agent_the_server_refuses_is_refused():
    assert UAMatrixRow(agent="CCBot", robots="allow", home_status=403).refused
    assert UAMatrixRow(agent="CCBot", robots="allow", home_status=200,
                       probe_status=[200, 429]).refused
    assert not UAMatrixRow(agent="CCBot", robots="allow", home_status=200,
                           probe_status=[200, 200]).refused


def test_the_matrix_runs_only_at_t2_and_site_scope_even_when_asked():
    # `ua_matrix=True` on all three: the tier and scope gate holds regardless,
    # so a pulse and a nav crawl carry none, and only the T2 site crawl does.
    with _UAServer() as s:
        pulse = crawl(s.base + "/", Tier.T1,
                      budget=TierBudget(3, 5, 60, 0), ua_matrix=True)
        nav = crawl(s.base + "/", Tier.T2, budget=FAST, nav_only=True, ua_matrix=True)
        full = crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True)
    assert pulse.ua_matrix == [], "a T1 pulse must not spend on the matrix"
    assert nav.ua_matrix == [], "a nav-scoped crawl answers a narrower question"
    assert len(full.ua_matrix) == len(UA_MATRIX_AGENTS), "the deep site crawl carries it"


def test_the_matrix_is_opt_in_and_off_by_default():
    # An incidental T2 crawl does not pay for the matrix; only the audit's deep
    # crawl asks for it (adaptive.py). Off by default keeps the suite — and any
    # non-audit caller — from spending agents x (1+probes) fetches unasked.
    with _UAServer() as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST)
    assert cr.ua_matrix == []


def test_the_crawl_evidence_carries_the_matrix():
    with _UAServer() as s:
        ev = snapshot(crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True))
    assert len(ev["ua_matrix"]) == len(UA_MATRIX_AGENTS)


def test_probe_urls_are_reached_same_host_html_pages_other_than_home():
    class P:
        def __init__(self, url, status=200, ct="text/html"):
            self.url, self.status, self.content_type = url, status, ct
    pages = [P("https://x.test/"), P("https://x.test/a"),
             P("https://x.test/bad", status=404),
             P("https://other.test/c"), P("https://x.test/b")]
    got = probe_urls("https://x.test/", pages)
    assert got == ["https://x.test/a", "https://x.test/b"]


# --- ua-server-refusal is HELD until a CDN/WAF is named ----------------------

def _crawl_context_for(ev, cdn=None):
    from clauditseo.analysts.expert import build_context

    class S:
        domain = "x.test"
        cdn_or_waf = cdn
    return build_context("crawl", ev, S())


def test_ua_server_refusal_is_held_until_a_cdn_is_named():
    with _UAServer(refuse_ua="CCBot") as s:
        ev = snapshot(crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True))
    # No CDN on the record: the matrix shows the refusal, but the field the fix
    # needs is absent, so the brief is told the check is held.
    held = _crawl_context_for(ev, cdn=None)
    assert "HELD" in held["CDN_OR_WAF"]
    assert "not named on the site record" in held["CDN_OR_WAF"]
    # And the matrix itself is present with the refusal visible for the brief.
    assert "Refused?" in held["UA_MATRIX"] and "CCBot" in held["UA_MATRIX"]
    # With a CDN named, the field carries the address the fix needs.
    named = _crawl_context_for(ev, cdn="Cloudflare")
    assert named["CDN_OR_WAF"] == "Cloudflare"


def test_ua_server_refusal_costs_a_model_call_and_no_sweep_emits_it():
    from clauditseo.checks import check_cost, sweep_checks
    assert check_cost("TEC/ua-server-refusal") == "model"
    assert "ua-server-refusal" not in sweep_checks()


def test_ua_server_refusal_files_under_crawl():
    from clauditseo import anatomy
    assert anatomy.categorise("ua-server-refusal", "TEC") == "crawl"


# --- 145 BG step 1: the agent list, with classes -----------------------------

def test_four_agent_classes_and_each_named_agent_has_one():
    from clauditseo.crawler.ua_matrix import AGENT_CLASSES, AI_AGENT_CLASSES, agents_of
    assert AI_AGENT_CLASSES == ("dataset", "training", "index", "answer-time")
    tokens = [t for t, _ua, _c in UA_MATRIX_AGENTS]
    assert len(tokens) == len(set(tokens))
    assert all(c in AGENT_CLASSES for _t, _ua, c in UA_MATRIX_AGENTS)
    # The addendum's section 1, class by class.
    assert agents_of("search") == ("Googlebot", "Bingbot")
    assert agents_of("dataset") == ("CCBot",)
    assert set(agents_of("training")) == {"GPTBot", "ClaudeBot", "Bytespider", "Meta-ExternalAgent",
                                          "Amazonbot", "PetalBot", "Google-Extended", "Applebot-Extended"}
    assert set(agents_of("index")) == {"OAI-SearchBot", "Claude-SearchBot", "Applebot", "PerplexityBot"}
    # Claude-User is user-initiated, whatever a CDN files it as.
    assert set(agents_of("answer-time")) == {"ChatGPT-User", "Claude-User", "Perplexity-User",
                                             "MistralAI-User", "DuckAssistBot", "Meta-ExternalFetcher"}


def test_a_robots_token_is_read_in_robots_and_never_sent_as_a_ua():
    tokens = {t for t, ua, _c in UA_MATRIX_AGENTS if ua is None}
    assert tokens == {"Google-Extended", "Applebot-Extended"}
    robots = "User-agent: *\nAllow: /\n\nUser-agent: Google-Extended\nDisallow: /\n"
    with _UAServer() as s:
        seen: list[str] = []
        orig = s._server.RequestHandlerClass.do_GET

        def spy(self):
            seen.append(self.headers.get("User-Agent") or "")
            return orig(self)
        s._server.RequestHandlerClass.do_GET = spy
        policy = RobotsPolicy(s.base + "/robots.txt", 200, robots)
        rows = build_ua_matrix(s.base + "/", [], policy, timeout_s=5, deadline=float("inf"))
    by = {r["agent"]: r for r in rows}
    ext = by["Google-Extended"]
    assert ext["sent"] is False and ext["robots"] == "disallow"
    assert ext["home_status"] is None and ext["probe_status"] == []
    assert ext["agent_class"] == "training"
    # No request carried a token as its UA; the base bots' strings did go out.
    assert not any("Google-Extended" in u or "Applebot-Extended" in u for u in seen)
    assert len(seen) == len(UA_MATRIX_AGENTS) - len(tokens)


def test_each_sent_row_keeps_status_retained_headers_and_body_length():
    with _UAServer(refuse_ua="Claude-SearchBot") as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True)
    by = {m["agent"]: m for m in cr.ua_matrix}
    ok, refused = by["Googlebot"], by["Claude-SearchBot"]
    assert ok["agent_class"] == "search" and refused["agent_class"] == "index"
    assert ok["home_status"] == 200 and ok["home_body_len"] == len(_HOME.encode())
    assert ok["headers"]["content-type"] == "text/html"
    assert len(ok["probe_body_len"]) == len(ok["probe_status"]) == len(ok["probe_headers"])
    assert refused["home_status"] == 403 and refused["home_body_len"] == 0
    assert refused["headers"].get("cf-ray") == "abc123" and "cloudflare" in refused["headers"].get("server", "")
    assert all(h.get("cf-ray") for h in refused["probe_headers"])
