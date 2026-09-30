"""Phase 1 expert tools: crawl evidence capture, placeholder substitution,
and the guarantee that nothing is invented when evidence is absent."""

from __future__ import annotations

import dataclasses
import json

import pytest

import clauditseo.modules  # noqa: F401
from clauditseo.analysts.base import AnalystResponse
from clauditseo.analysts.expert import (ABSENT, EXPERT_TOOLS, build_context,
                                       render_prompt, run_expert,
                                       ungrounded_figures)
from clauditseo.config import Settings
from clauditseo.crawler.crawl import crawl, normalise_url
from clauditseo.crawler.evidence import html_records, inlinks, snapshot
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite

FAST = TierBudget(max_pages=30, request_timeout_s=5, wall_clock_s=30, delay_s=0)


def _page(title: str, body: str, canonical: str | None = "self",
          robots: str | None = None) -> str:
    head = (f"<title>{title}</title>"
            '<meta name="viewport" content="width=device-width">')
    if canonical:
        head += f'<link rel="canonical" href="{canonical}">'
    if robots:
        head += f'<meta name="robots" content="{robots}">'
    return f"<html><head>{head}</head><body>{body}</body></html>"


@pytest.fixture
def site_fixture():
    sitemap = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/'
               'schemas/sitemap/0.9">{entries}</urlset>')
    routes = {
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                         sitemap.format(entries="".join(
                             f"<url><loc>{{base}}{p}</loc></url>"
                             for p in ("/", "/about", "/ghost")))),
        # Homepage links to the BARE ORIGIN as well as itself — the shape that
        # made the crawler fetch it twice.
        "/": (200, {}, _page("Fixture Home Page Title",
                             '<h1>Home</h1><a href="{base}">home again</a>'
                             '<a href="/about">about</a><a href="/hidden">hidden</a>'
                             '<a href="/list?sort=asc&utm_source=news">sorted</a>'
                             '<img src="/hero.jpg" alt="A roof"><img src="/x.png">',
                             canonical="/")),
        "/about": (200, {}, _page("About Us Fixture Page", "<h1>About</h1>",
                                  canonical="/about")),
        "/hidden": (200, {"X-Robots-Tag": "noindex"},
                    _page("Hidden Fixture Page", "<h1>Hidden</h1>", canonical="/hidden")),
        "/list": (200, {}, _page("Listing Fixture Page", "<h1>List</h1>",
                                 canonical="/list")),
        "/social": (200, {}, _page(
            "Social Fixture Page",
            '<h1>Social</h1>'
            '<a href="https://www.linkedin.com/company/fixture">LinkedIn</a>'
            '<a href="https://not-a-profile.example/page">Elsewhere</a>',
            canonical="/social")),
    }
    site = FixtureSite({}).start()
    site.routes.update({
        path: (status, headers, body.replace("{base}", site.base_url))
        for path, (status, headers, body) in routes.items()
    })
    yield site
    site.stop()


# --- crawler evidence -------------------------------------------------------

def test_url_normalisation_collapses_equivalent_spellings():
    assert normalise_url("https://X.example") == "https://x.example/"
    assert normalise_url("https://x.example") == normalise_url("https://x.example/")
    assert normalise_url("https://x.example:443/a") == "https://x.example/a"
    assert normalise_url("http://x.example:80/a#frag") == "http://x.example/a"
    # Path case and any query key the server can read genuinely address
    # different content — preserved. The tracking keys it cannot read are
    # stripped; `tests/test_url_tracking_params.py` guards both directions.
    assert normalise_url("https://x.example/A") != normalise_url("https://x.example/a")
    assert "?b=1" in normalise_url("https://x.example/a?b=1")


def test_homepage_is_not_crawled_twice(site_fixture):
    """Gate for the logged bug: a link to the bare origin must not produce a
    second copy of the homepage — nor a 100%-duplicate finding against it."""
    result = crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST)
    home = [p for p in result.pages if (p.url.rstrip("/") == site_fixture.base_url)]
    assert len(home) == 1, [p.url for p in result.pages]
    assert len({p.url for p in result.pages}) == len(result.pages)

    audit = run_audit(Site(domain="fixture.local"), result, ["CNT"], Tier.T2)
    self_dupes = [f for f in audit.findings
                  if f.check_id == "duplicate-content" and f.subject == "/|/"]
    assert not self_dupes


def test_evidence_snapshot_captures_what_findings_cannot(site_fixture):
    result = crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST)
    ev = snapshot(result)

    assert ev["start_url"].endswith("/")
    assert ev["robots_status"] == 200
    assert ev["sitemaps"] and ev["sitemaps"][0]["entry_count"] == 3
    assert ev["sitemap_entry_total"] == 3

    graph = inlinks(ev)
    about = next(u for u in graph if u.endswith("/about"))
    assert graph[about], "inlink sources must survive the crawl"

    hidden = next(p for p in ev["pages"] if p["url"].endswith("/hidden"))
    assert hidden["x_robots_tag"] == "noindex"      # header, not markup
    assert all("title" in p for p in html_records(ev))
    # No page bodies are stored — the snapshot must stay small.
    assert "content" not in ev["pages"][0]


# --- prompt rendering -------------------------------------------------------

@pytest.mark.parametrize("tool_id", ["crawl", "indexability", "urls", "speed",
                                     "security", "mobile-viewport",
                                     "links", "hreflang",
                                     "migration-redirects"])
def test_site_scoped_briefs_render_with_no_placeholders_left(site_fixture, tool_id):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    context = build_context(tool_id, ev, Site(domain="fixture.local"))
    prompt = render_prompt(tool_id, context)
    assert "{{" not in prompt, "every placeholder must be filled or marked absent"
    assert ABSENT in prompt, "inputs the suite cannot supply must be marked absent"
    assert site_fixture.base_url in prompt


def test_indexability_brief_carries_inlinks_and_canonical_targets(site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    context = build_context("indexability", ev, Site(domain="fixture.local"))
    # v18 step BA: the canonical map is the "now" table; hreflang is out of scope
    # (the brief's non-goals), so the old hreflang-absence note is gone.
    table = context["CANONICAL_MAP"]
    assert "Inlinks" in table and "Canonical target status" in table
    assert "X-Robots: noindex" in table          # header directive surfaced
    # The redirect log and the convention are the other halves of the "now".
    assert "REDIRECT_LOG" in context and "URL_CONVENTION" in context


def test_absent_evidence_is_marked_not_invented():
    context = build_context("crawl",
                            {"start_url": "https://x.example/", "tier": "T1",
                             "pages": [], "sitemaps": []},
                            Site(domain="x.example"))
    # The crawl brief (brief v18 step AZ) marks its task-4 inputs absent rather
    # than inventing them, and reports a sitemap that did not respond as missing.
    assert ABSENT in context["UA_MATRIX"]
    assert "did not respond" in context["SITEMAP_INVENTORY"]


# --- the runner -------------------------------------------------------------

class StubExpert:
    name = "stub"
    model_id = "stub-1"

    def __init__(self, report="## CRAWL HEALTH SUMMARY\nAll clear."):
        self.report = report
        self.seen_prompt = ""

    def run_agent(self, system, bundle, toolkit, max_tokens, max_output=0):
        # The brief must arrive as plain text, not JSON-escaped.
        assert isinstance(bundle, str) and "\\n" not in bundle[:200]
        self.seen_prompt = bundle
        return AnalystResponse(findings=[], tokens_in=20, tokens_out=20,
                               text=self.report)


def _db(tmp_path, ev):
    conn = connect(tmp_path / "expert.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Expert Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_evidence(conn, run_id, ev)
    return conn, run_id


def test_run_expert_returns_markdown_and_caches(tmp_path, site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    provider = StubExpert()

    first = run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
                       cfg, provider)
    assert first["status"] == "ok" and first["cached"] is False
    assert "CRAWL HEALTH SUMMARY" in first["report"]
    assert "ROLE" in provider.seen_prompt and "crawl and discovery" in provider.seen_prompt.lower()

    second = run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
                        cfg, StubExpert())
    assert second["cached"] is True and second["tokens"] == 0
    conn.close()


def test_run_expert_without_evidence_or_provider_is_honest(tmp_path, site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")

    no_provider = run_expert(conn, run_id, "crawl", ev,
                             Site(domain="x"), cfg, None)
    assert no_provider["status"] == "unavailable"
    assert "ANTHROPIC_API_KEY" in no_provider["reason"]

    no_evidence = run_expert(conn, run_id, "crawl", {}, Site(domain="x"),
                             cfg, StubExpert())
    assert no_evidence["status"] == "unavailable"
    assert "no stored crawl evidence" in no_evidence["reason"]

    unknown = run_expert(conn, run_id, "nope", ev, Site(domain="x"), cfg,
                         StubExpert())
    assert unknown["status"] == "unavailable"
    conn.close()


def test_figures_not_in_evidence_are_surfaced_for_verification():
    evidence = json.dumps({"pages": "27 crawled"})
    assert ungrounded_figures("We found 27 pages.", evidence) == []
    assert "8123" in ungrounded_figures("Traffic fell 8123 visits.", evidence)
    # Status codes and small ordinals are vocabulary, not claims.
    assert ungrounded_figures("Three 301s and a 404 were found.", evidence) == []
    # Nor are identifiers and standards references measurements.
    assert ungrounded_figures(
        "Issue mobile-viewport-01 fails WCAG 2.1 SC 1.4.4 over HTTP/2; "
        "the outline jumps h2 to h4.", evidence) == []


def test_editing_a_prompt_file_invalidates_that_tool_s_cache(tmp_path, monkeypatch):
    """A cached report that survives a prompt edit makes the edit look like it
    did nothing — the failure mode that hid the unattended-mode fix."""
    from clauditseo.analysts import expert as expert_module

    before = expert_module.brief_version("crawl")
    # Bytes, not text. `write_text` translates "\n" to the platform newline,
    # so restoring through it left the prompt CRLF where it had been LF: the
    # test edited a source file and did not put back what it found. Invisible
    # until item 170 bound `clauditseo/prompts/*.md -text` and the restored
    # file showed as modified — and one of these prompts is held to its relay
    # attachment byte for byte, so the bytes are the thing to restore.
    original = (expert_module.PROMPT_DIR / "crawl.md").read_bytes()
    try:
        (expert_module.PROMPT_DIR / "crawl.md").write_bytes(
            original + b"\n# an edit\n")
        assert expert_module.brief_version("crawl") != before
    finally:
        (expert_module.PROMPT_DIR / "crawl.md").write_bytes(original)
    assert expert_module.brief_version("crawl") == before
    # A different tool's key must not move when this one's prompt changes.
    assert expert_module.brief_version("indexability") != before


def test_briefs_are_told_no_one_can_answer_a_clarifying_question():
    """Every brief carries an interactive clarifier gate. Unattended, a
    question is not a pause — it is a wasted call and a report that never
    arrives."""
    from clauditseo.analysts.expert import SYSTEM_FRAMING
    assert "UNATTENDED" in SYSTEM_FRAMING
    assert "never ask one" in SYSTEM_FRAMING


def test_click_depth_and_anchors_reach_the_links_brief(site_fixture):
    """`links` replaced `site-architecture` at brief v17 step AW, and the
    two facts this clause is about - the depth of a page and the words on
    the links into it - are what the new brief needs most: a suggestion
    may only draw an anchor from the target's own words, so a page set
    without them would have the model inventing one."""
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    home = next(p for p in ev["pages"] if p["url"] == ev["start_url"])
    about = next(p for p in ev["pages"] if p["url"].endswith("/about"))
    assert home["click_depth"] == 0 and about["click_depth"] == 1

    context = build_context("links", ev, Site(domain="fixture.local"))
    assert "Depth" in context["PAGE_SET"]
    assert "Topic terms" in context["PAGE_SET"]
    assert "about" in context["LINK_GRAPH"]          # anchor text captured
    assert "Anchor" in context["LINK_GRAPH"]


def test_transport_probe_reaches_the_security_brief(site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    context = build_context("security", ev, Site(domain="fixture.local"))
    # A local http fixture has no TLS; the brief must be told, not misled.
    assert "NOT a full scan" in context["TLS_PROBE"] or "no transport probe" in context["TLS_PROBE"]
    assert "header set" in context["RESPONSE_HEADERS"]
    # The two inputs this build cannot collect say so, naming the checks.
    assert "spf" in context["DNS_RECORDS"] and "not assessable" in context["DNS_RECORDS"]


def test_viewport_tags_are_reproduced_verbatim(site_fixture):
    """Re-homed from `VIEWPORT_TAG_DATA` to `TEMPLATE_SET` when the Mobile
    brief went to schema mobile/2 (item 147, brief v20): the context is per
    template now rather than per URL, and the tags travel in that table.

    The claim itself is unchanged and is load-bearing. A normalised viewport
    string is a DIFFERENT string, and all six parse-only checks read it
    character by character -- `width=device-width` against `width = device-width`
    against `width=device-Width`. The prompt says "quote strings exactly; no
    normalisation, spacing or case changes", and this is what holds the context
    builder to it.
    """
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    context = build_context("mobile-viewport", ev, Site(domain="fixture.local"))
    assert 'content="width=device-width"' in context["TEMPLATE_SET"]
    # The three absences the brief holds nine of its fifteen checks on, each
    # naming which checks it holds and why -- not a bare placeholder.
    for key, held in (("HEAD_RAW", "viewport-late"),
                      ("HEAD_RENDERED", "viewport-injected"),
                      ("MOBILE_RENDER", "tap-target")):
        assert ABSENT in context[key], key
        assert held in context[key], (
            f"{key} is absent but does not say which check that holds")


def test_operator_inputs_override_derived_context(site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    plain = build_context("hreflang", ev, Site(domain="fixture.local"))
    assert plain["TARGET_LOCALES"] == ABSENT

    supplied = build_context("hreflang", ev, Site(domain="fixture.local"),
                             {"TARGET_LOCALES": "en-AU, en-GB", "PLATFORM": "  "})
    assert supplied["TARGET_LOCALES"] == "en-AU, en-GB"
    assert supplied["PLATFORM"] == ABSENT      # whitespace is not an answer


def test_migration_brief_requires_the_redirect_map(tmp_path, site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")

    blocked = run_expert(conn, run_id, "migration-redirects", ev,
                         Site(domain="fixture.local"), cfg, StubExpert())
    assert blocked["status"] == "needs_input"
    assert "Redirect map" in blocked["required"]

    provider = StubExpert("## 1. INPUT COVERAGE\nSupplied.")
    ok = run_expert(conn, run_id, "migration-redirects", ev,
                    Site(domain="fixture.local"), cfg, provider,
                    operator_inputs={"REDIRECT_MAP": "/old,/new,301"})
    assert ok["status"] == "ok"
    assert "/old,/new,301" in provider.seen_prompt
    conn.close()


@pytest.mark.parametrize("tool_id", ["content-brief"])
def test_page_scoped_briefs_render_with_no_placeholders_left(site_fixture, tool_id):
    """Covers awkward placeholder shapes too: the entity brief writes
    {{EXISTING_JSONLD_OR_"none found"}}, which a strict pattern would skip
    silently and leave as raw braces in the prompt."""
    from clauditseo.crawler.fetch import Fetcher

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    with Fetcher(timeout_s=5) as fetcher:
        page = fetcher.fetch(site_fixture.base_url + "/")
    context = build_context(tool_id, ev, Site(domain="fixture.local"), page=page)
    prompt = render_prompt(tool_id, context)
    assert "{{" not in prompt and "}}" not in prompt


def test_inline_css_is_stripped_so_the_body_survives_the_cap():
    """A WP Rocket used-CSS block ate the entire excerpt on a real site,
    leaving an entity audit with no page content to assess."""
    from clauditseo.analysts.expert import trimmed_html

    html = ("<html><head><title>T</title>"
            '<style id="wpr-usedcss">' + ("a{color:red}" * 4000) + "</style>"
            '<script type="application/ld+json">{"@type":"Organization"}</script>'
            '<script>window.x=' + ("1" * 3000) + ";</script></head>"
            "<body><h1>The heading that matters</h1></body></html>")
    trimmed = trimmed_html(html, cap=8000)

    assert "The heading that matters" in trimmed      # body survives
    assert '{"@type":"Organization"}' in trimmed      # JSON-LD never stripped
    assert "a{color:red}a{color:red}" not in trimmed  # CSS body removed
    assert "characters of inline CSS removed" in trimmed
    assert "characters of inline JavaScript removed" in trimmed
    assert "were removed from this excerpt" in trimmed  # removal is disclosed

    # Short inline blocks are left alone; nothing is trimmed unnecessarily.
    small = "<html><head><style>a{color:red}</style></head><body>hi</body></html>"
    assert trimmed_html(small) == small


def test_placeholder_keys_ignore_inline_defaults():
    from clauditseo.analysts.expert import placeholder_key
    assert placeholder_key("SITE_URL") == "SITE_URL"
    assert placeholder_key("T2_PAGES|100") == "T2_PAGES"
    assert placeholder_key('EXISTING_JSONLD_OR_"none found"') == "EXISTING_JSONLD"


def test_model_routing_by_tier_with_operator_override():
    import dataclasses as dc

    from clauditseo.analysts.expert import model_for_tool, tier_of
    cfg = dc.replace(Settings(), llm_model="sonnet-x",
                     llm_model_fast="haiku-x", llm_model_deep="opus-x")

    assert tier_of("mobile-viewport") == "fast"
    # `content-cannibalisation` since brief v17 step AX retired
    # `cannibalisation-map`. Any deep brief serves; what this
    # clause is about is the tier deciding the model.
    assert tier_of("content-cannibalisation") == "deep"
    assert tier_of("crawl") == "standard"

    assert model_for_tool(cfg, "mobile-viewport") == "haiku-x"
    assert model_for_tool(cfg, "content-cannibalisation") == "opus-x"
    assert model_for_tool(cfg, "crawl") == "sonnet-x"
    # An explicit operator choice always wins over the tier.
    assert model_for_tool(cfg, "mobile-viewport", "opus-x") == "opus-x"


def test_image_brief_never_estimates_a_file_size(site_fixture):
    from clauditseo.crawler.fetch import Fetcher

    from clauditseo.analysts.expert import NOT_MEASURED

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    context = build_context("images", ev, Site(domain="fixture.local"))
    # Weight is not in the inventory this crawl stores, and the brief is
    # told so in the one form the prompt turns into a held row.
    assert NOT_MEASURED in context["PAGE_SET"]
    assert any("was not observed on this run" in a for a in context["_ENGINE_ASSUMPTIONS"])


def test_every_registered_tool_has_a_prompt_file():
    from clauditseo.analysts.expert import PROMPT_DIR
    for tool_id, spec in EXPERT_TOOLS.items():
        path = PROMPT_DIR / spec["prompt"]
        assert path.exists(), f"{tool_id} has no prompt file"
        text = path.read_text(encoding="utf-8")
        assert "# ROLE" in text and "# CONSTRAINTS" in text
        assert spec["scope"] in ("site", "page")


# --- token accounting and cache bypass ---------------------------------------
#
# Both exist so a model comparison can be trusted: a cached reply reports zero
# tokens, and a two-phase brief that only bills for its second call understates
# its own cost by roughly half.

class CountingExpert:
    name = "counting"
    model_id = "count-1"

    def __init__(self):
        self.calls = 0

    def run_agent(self, system, bundle, toolkit, max_tokens, max_output=0):
        self.calls += 1
        return AnalystResponse(findings=[], tokens_in=100, tokens_out=10,
                               text=f"## SECTION {self.calls}\nBody text.")


def test_a_split_brief_bills_for_both_of_its_calls(tmp_path, site_fixture):
    from clauditseo.analysts.expert import SPLIT_BRIEFS
    # Any two-phase brief will do; this clause is about the billing, not
    # about which brief splits. `site-architecture` was the one named here
    # and it was retired at brief v17 step AW, so the register itself
    # chooses - a hand-named brief is what made this clause fail on a
    # change that had nothing to do with billing.
    assert SPLIT_BRIEFS, "this test needs a two-phase brief"

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="",
                              model_prices={"count-1": (10.0, 100.0)})
    # The first split brief that runs on this fixture with no operator input:
    # `https-security` was the one sorted first until item 143 step BD retired
    # it, and the next, `migration-redirects`, waits on a redirect map - a
    # refusal that bills nothing is not what this clause is about.
    for tool in sorted(SPLIT_BRIEFS):
        provider = CountingExpert()
        result = run_expert(conn, run_id, tool, ev, Site(domain="fixture.local"),
                            cfg, provider)
        if provider.calls:
            break
    assert provider.calls == 2 and result["calls"] == 2
    # Both halves, not just the one that produced the final response.
    assert result["tokens_in"] == 200 and result["tokens_out"] == 20
    assert result["tokens"] == 220
    assert result["cost"] == pytest.approx(200 / 1e6 * 10.0 + 20 / 1e6 * 100.0)

    logged = conn.execute(
        "SELECT quantity, actual_cost FROM cost_entries WHERE operation=?",
        (f"EXPERT:{tool}",)).fetchone()
    assert logged[0] == 220
    assert logged[1] == pytest.approx(result["cost"])
    conn.close()


def test_no_cache_forces_a_fresh_call_so_models_can_be_compared(tmp_path, site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")

    first = run_expert(conn, run_id, "crawl", ev,
                       Site(domain="fixture.local"), cfg, CountingExpert())
    assert first["cached"] is False

    replayed = run_expert(conn, run_id, "crawl", ev,
                          Site(domain="fixture.local"), cfg, CountingExpert())
    assert replayed["cached"] is True and replayed["tokens"] == 0

    provider = CountingExpert()
    fresh = run_expert(conn, run_id, "crawl", ev,
                       Site(domain="fixture.local"), cfg, provider,
                       use_cache=False)
    assert fresh["cached"] is False and provider.calls == 1
    assert fresh["tokens"] == 110, "a bypassed cache must report real usage"
    conn.close()


# --- machine-readable findings index -----------------------------------------
#
# Briefs answer in whatever shape their prompt asks for, which is why only one
# of thirteen was ever parseable. The index is appended by the shared framing
# so every brief gains it without its prompt file being touched.

def test_findings_index_is_parsed_and_removed_from_the_prose():
    from clauditseo.analysts.expert import parse_findings_block
    report = (
        "## SUMMARY\nAll considered.\n\n"
        "```clauditseo-findings\n"
        "severity | code | one-line summary | affected URLs\n"
        "high | sitemap-coverage | 22 pages absent | https://x.test/a, https://x.test/b\n"
        "low | title-length | one title is long | -\n"
        "```\n")
    clean, found = parse_findings_block(report)
    assert "clauditseo-findings" not in clean and clean.endswith("All considered.")
    assert [f["code"] for f in found] == ["sitemap-coverage", "title-length"]
    assert found[0]["severity"] == "high"
    assert found[0]["affected_urls"] == ["https://x.test/a", "https://x.test/b"]
    assert found[1]["affected_urls"] == []          # "-" is not a URL


def test_a_malformed_index_row_is_dropped_not_guessed_at():
    from clauditseo.analysts.expert import parse_findings_block
    # The surviving row names a check the app actually has. It read
    # `real-one` until Q-54, which was fine while nothing validated the id
    # and became the thing under test the moment something did.
    _, found = parse_findings_block(
        "text\n```clauditseo-findings\n"
        "urgent | made-up-severity | not a real level | -\n"      # bad severity
        "high | too-few-columns\n"                                # short row
        "medium | title-length | this survives | /page\n"
        "```")
    assert [f["code"] for f in found] == ["title-length"]
    assert found[0]["affected_urls"] == ["/page"]


REPORT_WITH_AN_INVENTED_CHECK = "\n".join((
    "text",
    "```clauditseo-findings",
    "high | headers-csp-missing | a brief invented this | /page",
    "low | canonical-mismatch | a real check | /page",
    "```",
))


def test_a_row_naming_a_check_the_app_does_not_have_is_dropped():
    """Q-54, and it is not hypothetical.

    Fifteen rows reached the operator's record under ids no check answers -
    `headers-csp-missing`, `cookies-samesite-none` and thirteen more, every
    one invented by a brief and stored verbatim, because this reader
    validated the severity, the column count and the page and never the
    check.

    A finding stored under an id nothing raises can never be cleared, never
    be scored and never be re-checked. It sits in the record for good and
    reads exactly like a real one.
    """
    from clauditseo.analysts.expert import parse_findings_block

    drops: list[dict] = []
    _, found = parse_findings_block(
        REPORT_WITH_AN_INVENTED_CHECK, drops=drops)
    assert [f["code"] for f in found] == ["canonical-mismatch"]
    assert [d["check"] for d in drops] == ["headers-csp-missing"]
    assert drops[0]["reason"] == "unknown check id"


def test_the_engines_own_ids_are_not_called_unknown():
    """The rule must not throw away the engine's own findings.

    Two families no register can enumerate: `axe-*`, whose ids come from
    axe-core's rule set at run time, and `adaptive-no-escalation`, raised by
    the escalation policy rather than by a dimension module. The record
    holds 79 rows under those two names, and the first draft of this rule
    called every one of them invalid.
    """
    from clauditseo.checks import known_check

    assert known_check("axe-color-contrast")
    assert known_check("A11Y/axe-color-contrast")
    assert known_check("adaptive-no-escalation")
    assert known_check("TEC/adaptive-no-escalation")
    assert known_check("canonical-mismatch") and known_check("ONP/title-length")
    assert not known_check("headers-csp-missing")
    assert not known_check("")


def test_a_report_with_no_index_still_returns_cleanly():
    from clauditseo.analysts.expert import parse_findings_block
    clean, found = parse_findings_block("## SUMMARY\nNothing wrong here.")
    assert found == [] and clean == "## SUMMARY\nNothing wrong here."


def test_expert_findings_are_stored_without_touching_score_or_states(tmp_path, site_fixture):
    """They are listed and linked, but they are commentary: a model finding
    that vanishes between runs is not evidence of a fix."""
    from clauditseo.persistence.runs import expert_findings, record_expert_findings
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)

    record_expert_findings(conn, run_id, "crawl", "m-1", [
        {"severity": "high", "code": "sitemap-coverage", "summary": "22 absent",
         "affected_urls": ["https://x.test/a"]},
        {"severity": "low", "code": "minor", "summary": "cosmetic",
         "affected_urls": []}])

    stored = expert_findings(conn, run_id)
    assert [f["severity"] for f in stored] == ["high", "low"]   # severity ordered
    assert stored[0]["affected_urls"] == ["https://x.test/a"]
    assert all(f["source"] == "model-judgement" for f in stored)
    assert all(f["dimension"] == "EXP:crawl" for f in stored)
    assert all(f["fingerprint"] for f in stored)
    # They enter the memory as candidates — seen once, not yet confirmed —
    # never straight to open. The full walk is tested in test_memory.py.
    states = {r["state"] for r in conn.execute("SELECT state FROM finding_states")}
    assert states <= {"candidate"}
    conn.close()


def test_rerunning_a_tool_replaces_its_findings_rather_than_doubling_them(tmp_path, site_fixture):
    from clauditseo.persistence.runs import expert_findings, record_expert_findings
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    one = [{"severity": "high", "code": "a", "summary": "first", "affected_urls": []}]
    record_expert_findings(conn, run_id, "crawl", "m-1", one)
    record_expert_findings(conn, run_id, "crawl", "m-1", one)
    assert len(expert_findings(conn, run_id)) == 1
    # A different tool's findings survive the replace.
    record_expert_findings(conn, run_id, "indexability", "m-1", one)
    assert len(expert_findings(conn, run_id)) == 2
    conn.close()


def test_a_flagged_figure_arrives_with_the_sentence_it_came_from():
    """A bare list of digits under a caution trains operators to ignore it."""
    from clauditseo.analysts.expert import figure_context
    report = ("## NOTES\n"
              "- Meta description length threshold applied as 120-160 characters "
              "for safe SERP display.\n")
    assert "safe SERP display" in figure_context(report, "160")
    assert figure_context(report, "99999") == ""


# --- phase 6 and 7 briefs ----------------------------------------------------

def test_the_speed_brief_never_presents_an_unmeasured_timing_as_measured(
        site_fixture) -> None:
    """Re-homed from `render-blocking` when that brief was retired (item 141
    step 3a), because the invariant is generic and its successor was carrying
    it unguarded: **a brief handed no timing must be told it may not state a
    cost as measured.**

    Only one half moved, and the other did not go quietly. The retired test
    also asserted that the crawler's own fetch time can never read as a
    user-experienced timing — "Crawler fetch time ... not a user measurement".
    That half **retired with its input**: `_speed_context` sends the trace and
    never sends the crawler's fetch time, so there is no number left to
    mislabel. The risk is gone because the input is gone, not because the rule
    was dropped.
    """
    from clauditseo.analysts.expert import build_context

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))

    # No page carried a trace — the fixture crawl takes none — so the brief is
    # told so by name rather than handed an empty section to fill in.
    bare = build_context("speed", ev, Site(domain="fixture.local"))
    assert ABSENT in bare["PAGE_SET"]
    assert "no page carried a performance trace" in bare["PAGE_SET"]


# --- phase 8: local ----------------------------------------------------------
#
# Three of these four audit things a crawl cannot see. The risk is not that
# they fail — it is that they quietly substitute site data for profile data and
# turn a comparison into a tautology.

def test_local_signals_carries_phone_variants_verbatim_with_their_source(site_fixture):
    """The brief refuses to report an inconsistency without exhibiting the
    conflicting variants, so the matched text must survive unnormalised."""
    from clauditseo.crawler.evidence import nap_mentions
    from clauditseo.modules.loc import PHONE_RE

    found = nap_mentions("Call us on (03) 9111 2222 today, or 0400 111 222 after hours.",
                         PHONE_RE)
    values = [f["value"] for f in found]
    assert "(03) 9111 2222" in values, "bracket and spacing must survive"
    assert any(v.strip() == "0400 111 222" for v in values)
    assert "after hours" in found[-1]["context"]


def test_local_schema_is_kept_verbatim_and_only_when_local(site_fixture):
    from clauditseo.crawler.evidence import local_schema_blocks
    local = '{"@type":"Plumber","telephone":"(03) 9111 2222"}'
    unrelated = '{"@type":"BreadcrumbList","itemListElement":[]}'
    kept = local_schema_blocks([local, unrelated])
    assert kept == [local], "the block is quoted back as a before, so it is not reserialised"


def test_gbp_brief_never_passes_site_nap_off_as_profile_nap(site_fixture):
    """Substituting the site's NAP for the profile's would turn the audit's
    central comparison into a tautology that always passes."""
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    ctx = build_context("gbp-audit", ev, Site(domain="fixture.local"))

    assert ABSENT in ctx["NAP_DETAILS"]
    assert "no access to the Business Profile" in ctx["NAP_DETAILS"]
    for pillar in ("POSTS_DATA", "PHOTOS_DATA", "QA_DATA", "REVIEWS_DATA",
                   "ATTRIBUTES", "HOURS"):
        assert ABSENT in ctx[pillar], f"{pillar} cannot be seen by a crawl"
    # The site side is supplied and labelled as such. With no Places lookup
    # there is no profile data here at all.
    assert "The site side of the comparison" in ctx["KEY_PAGES"]
    assert "GOOGLE PLACES" not in ctx["KEY_PAGES"]
    assert site_fixture.base_url in ctx["WEBSITE_URL"]


def test_citations_brief_gets_the_site_reference_but_no_invented_canonical(site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    ctx = build_context("citations-nap", ev, Site(domain="fixture.local"))

    # A canonical record is a business fact, not a crawl observation.
    for key in ("CANONICAL_NAME", "CANONICAL_ADDRESS", "CANONICAL_PHONE"):
        assert ABSENT in ctx[key]
        assert "confirm which is the name of record" in ctx[key]
    assert ctx["CANONICAL_URL"].startswith("http")
    assert "cannot query directories" in ctx["LISTING_DATA"]


def test_review_brief_offers_only_markup_it_actually_found(site_fixture):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    ctx = build_context("review-signals", ev, Site(domain="fixture.local"))

    assert ABSENT in ctx["REVIEW_EXPORT"]
    assert "cannot be computed from a crawl" in ctx["REVIEW_EXPORT"]
    assert "carrying Review or AggregateRating was found" in ctx["MARKUP_SOURCE"]


@pytest.mark.parametrize("tool_id", ["local-signals", "gbp-audit",
                                     "citations-nap", "review-signals"])
def test_local_briefs_render_with_no_placeholders_left(site_fixture, tool_id):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    prompt = render_prompt(tool_id, build_context(tool_id, ev,
                                                  Site(domain="fixture.local")))
    assert "{{" not in prompt, "every placeholder must be filled or marked absent"
    assert ABSENT in prompt


def test_local_signals_issue_codes_match_the_deterministic_module():
    """The sweep raises these codes and the brief writes their fixes. If the
    two sets drift apart, a finding gets a fix that never reaches it."""
    from clauditseo.analysts.expert import PROMPT_DIR
    brief = (PROMPT_DIR / "local-signals.md").read_text(encoding="utf-8")
    for code in ("nap-missing", "nap-inconsistent", "localbusiness-schema-missing",
                 "opening-hours-missing", "thin-location-page"):
        assert code in brief, f"{code} is raised by modules/loc.py but absent from the brief"


def test_evidence_from_before_local_capture_is_not_reported_as_absence(site_fixture):
    """A run crawled before local capture existed has the key missing; a
    current run that found nothing has it present and empty. Collapsing the two
    made a brief call a plainly published phone number missing, and raise it
    critical."""
    from clauditseo.analysts.expert import UNCOLLECTED_LOCAL_EVIDENCE

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    stale = {**ev, "pages": [{k: v for k, v in p.items()
                              if k not in ("nap_mentions", "local_schema")}
                             for p in ev["pages"]]}

    ctx = build_context("local-signals", stale, Site(domain="fixture.local"))
    assert UNCOLLECTED_LOCAL_EVIDENCE in ctx["SITE_URL_OR_PAGE_LIST"]
    assert "not evidence of absence" in ctx["SITE_URL_OR_PAGE_LIST"]
    assert "no finding may be raised on this basis" in ctx["SITE_URL_OR_PAGE_LIST"]

    review = build_context("review-signals", stale, Site(domain="fixture.local"))
    assert UNCOLLECTED_LOCAL_EVIDENCE in review["MARKUP_SOURCE"]

    # A current crawl that genuinely finds nothing says so plainly instead.
    fresh = build_context("local-signals", ev, Site(domain="fixture.local"))
    assert UNCOLLECTED_LOCAL_EVIDENCE not in fresh["SITE_URL_OR_PAGE_LIST"]


def test_local_business_subtypes_are_recognised_not_just_plumber():
    """Naming one subtype meant a correctly marked-up roofer was reported as
    having no LocalBusiness schema at all."""
    from clauditseo.modules.loc import is_local_business
    for name in ("Plumber", "RoofingContractor", "LocalBusiness", "Dentist",
                 "https://schema.org/Electrician", "Restaurant"):
        assert is_local_business(name), name
    for name in ("Organization", "BreadcrumbList", "WebPage", "FAQPage"):
        assert not is_local_business(name), name


def test_australian_mobile_and_service_numbers_are_matched():
    """The previous pattern required a 3-or-4 digit group straight after the
    area code, so it missed every 04XX XXX XXX mobile — the usual way a local
    business publishes a number — and reported nap-missing instead."""
    from clauditseo.modules.loc import PHONE_RE
    for number in ("0400 111 222", "0433 456 789", "0412345678", "(03) 9111 2222",
                   "03 9111 2222", "0398765432", "1300 555 111", "1800 123 456",
                   "13 11 14", "+61 3 9111 2222", "+61 400 111 222"):
        assert PHONE_RE.findall(number), number
    for text in ("ABN 12 345 678 901", "postcode 3000", "2026-08-07",
                 "order 1234567890123"):
        assert not PHONE_RE.findall(text), text


def test_repeated_schema_is_counted_not_pasted_eighty_times(site_fixture):
    """A templated site emits the same business node on every page. Sending
    all of them cost 218,000 input tokens on a real run — and their sameness
    is the finding, which a count states better than eighty copies show."""
    from clauditseo.analysts.expert import SCHEMA_EXAMPLES, build_context

    block = ('{"@type":["RoofingContractor","LocalBusiness"],'
             '"aggregateRating":{"ratingValue":"4.8","reviewCount":"77"}}')
    # 40 templated pages, as a real suburb-page site produces.
    ev = {"start_url": "https://x.test/",
          "pages": [{"url": f"https://x.test/suburb-{i}/", "status": 200,
                     "content_type": "text/html", "local_schema": [block],
                     "nap_mentions": []} for i in range(40)]}
    pages = len(ev["pages"])
    assert pages > SCHEMA_EXAMPLES, "fixture must exceed the example cap"

    markup = build_context("review-signals", ev, Site(domain="fixture.local"))["MARKUP_SOURCE"]
    assert markup.count("aggregateRating") <= SCHEMA_EXAMPLES + 1
    # Identical blocks group into one form, and the real total is still stated.
    assert f"{pages} block(s)" in markup and "1 distinct form" in markup
    assert str(pages) in markup, "the count the finding rests on must survive"


def test_omitted_schema_forms_are_declared_not_dropped_silently(site_fixture):
    """A cap that is not announced reads as 'this is everything'."""
    from clauditseo.analysts.expert import SCHEMA_EXAMPLES, build_context

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    ev = {**ev, "pages": [{**p, "local_schema": [f'{{"@type":"Plumber","n":{i}}}']}
                          for i, p in enumerate(ev["pages"])]}
    dump = build_context("local-signals", ev, Site(domain="fixture.local"))["SITE_URL_OR_PAGE_LIST"]
    distinct = len([p for p in ev["pages"] if p.get("status") == 200])
    if distinct > SCHEMA_EXAMPLES:
        assert "not shown" in dump
        assert f"{distinct} distinct form" in dump


# --- phase 5: content --------------------------------------------------------

def test_content_brief_knows_whether_the_page_already_exists(site_fixture):
    """A rewrite and a new page are different commissions, and the crawl can
    settle which this is.

    Said in `PAGE` since brief v17 step AX rather than in a key of its own:
    the supplied prompt asks for one block describing the page - url, type,
    exists, h1, title, words, outline - and a second key saying the same
    thing in one word is a second place for the two to disagree.
    """
    from clauditseo.crawler.fetch import Fetcher
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    with Fetcher(timeout_s=10) as fetcher:
        page = fetcher.fetch(site_fixture.base_url + "/about")
    ctx = build_context("content-brief", ev, Site(domain="fixture.local"), page=page)
    assert "exists: yes" in ctx["PAGE"], ctx["PAGE"]
    assert "/about" in ctx["PAGE"], ctx["PAGE"]


# The Content site briefs, which are the four of brief v17 step AX
# since `freshness` and `content-gap` were retired with the two
# others they replace.
@pytest.mark.parametrize("tool_id", ["content-coverage", "content-substance",
                                     "content-cannibalisation",
                                     "content-benchmark"])
def test_content_site_briefs_render_with_no_placeholders_left(site_fixture, tool_id):
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    prompt = render_prompt(tool_id, build_context(tool_id, ev,
                                                  Site(domain="fixture.local")))
    assert "{{" not in prompt and ABSENT in prompt


def test_a_truncated_report_says_why_its_findings_are_missing(tmp_path, site_fixture):
    """The index is written last, so a report that runs out of budget loses it.
    An empty finding list would otherwise read as a clean result."""
    class Truncating:
        name, model_id = "trunc", "trunc-1"

        def run_agent(self, system, bundle, toolkit, max_tokens, max_output=0):
            return AnalystResponse(findings=[], tokens_in=10, tokens_out=10,
                                   text="## SUMMARY\nCut off mid-sen",
                                   stop="max_tokens")

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    result = run_expert(conn, run_id, "crawl", ev,
                        Site(domain="fixture.local"),
                        dataclasses.replace(Settings(), anthropic_api_key=""),
                        Truncating())
    assert result["truncated"] is True
    assert result["findings"] == []
    assert "That is truncation, not a clean result" in result["report"]
    conn.close()


# --- stored results ----------------------------------------------------------
#
# The analyst cache is keyed on evidence, not on the run, so it can answer
# "have I seen this bundle" but not "what did this tool last say about this
# site" — which is what a client-first sweep down the tool list asks.

def test_a_report_is_kept_against_its_run_not_only_in_the_cache(tmp_path, site_fixture):
    from clauditseo.persistence.runs import expert_report, expert_report_index

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")

    run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
               cfg, StubExpert())
    stored = expert_report(conn, run_id, "crawl")
    assert stored and "CRAWL HEALTH SUMMARY" in stored["report"]
    assert stored["stored"] is True and stored["status"] == "ok"

    index = expert_report_index(conn, run_id)
    assert [r["tool"] for r in index] == ["crawl"]
    assert index[0]["findings"] == 0        # the stub raises none
    conn.close()


def test_a_cached_replay_still_records_the_report_against_this_run(tmp_path, site_fixture):
    """The cache is shared across runs of the same evidence. A replay must
    still leave this run with something to show."""
    from clauditseo.persistence.runs import expert_report

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    # `local-signals`, not `security`: this clause needs a context with
    # nothing run-specific in it, and the Security brief names its run. It was
    # `llms-txt-builder` until that brief retired (item 145).
    run_expert(conn, run_id, "local-signals", ev, Site(domain="fixture.local"),
               cfg, StubExpert())

    other = runs.create_run(conn, repo.list_sites(
        conn, repo.list_clients(conn)[0]["id"])[0]["id"], ["TEC"], "T2")
    runs.store_evidence(conn, other, ev)
    replay = run_expert(conn, other, "local-signals", ev,
                        Site(domain="fixture.local"), cfg, StubExpert())
    assert replay["cached"] is True
    assert expert_report(conn, other, "local-signals") is not None
    conn.close()


def test_running_again_replaces_the_stored_result(tmp_path, site_fixture):
    from clauditseo.persistence.runs import expert_report, expert_report_index

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
               cfg, StubExpert("## CRAWL HEALTH SUMMARY\nFirst pass."))
    run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
               cfg, StubExpert("## CRAWL HEALTH SUMMARY\nSecond pass."),
               use_cache=False)

    assert len(expert_report_index(conn, run_id)) == 1
    assert "Second pass" in expert_report(conn, run_id, "crawl")["report"]
    conn.close()


def test_the_index_reports_the_worst_severity_for_list_markers(tmp_path, site_fixture):
    """The tool list colours its marker by the worst thing found, so browsing
    shows where the problems are before anything is opened."""
    from clauditseo.persistence.runs import expert_report_index, store_expert_report

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    store_expert_report(conn, run_id, "local-signals", {
        "model": "m", "report": "text",
        "findings": [{"severity": "low", "code": "a", "summary": "s"},
                     {"severity": "critical", "code": "b", "summary": "s"},
                     {"severity": "medium", "code": "c", "summary": "s"}]})
    row = expert_report_index(conn, run_id)[0]
    assert row["findings"] == 3 and row["worst_severity"] == "critical"
    conn.close()


# --- run estimates -----------------------------------------------------------

def test_estimates_scale_to_the_size_of_the_crawl_in_front_of_you(tmp_path, site_fixture):
    """The same brief against a 10-page site and a 100-page site are different
    jobs, so one flat average predicts badly for both."""
    from clauditseo.persistence.runs import expert_estimates, store_expert_report

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    site_id = repo.list_sites(conn, repo.list_clients(conn)[0]["id"])[0]["id"]
    # One row per (run, tool), so each sample needs its own run.
    for tokens, pages, ms in ((10_000, 10, 20_000), (50_000, 50, 100_000)):
        other = runs.create_run(conn, site_id, ["TEC"], "T2")
        store_expert_report(conn, other, "crawl",
                            {"model": "m", "report": "r", "tokens": tokens},
                            elapsed_ms=ms, pages_crawled=pages)

    at_20 = expert_estimates(conn, pages=20)["crawl"]
    assert at_20["tokens"] == 20_000        # 1,000 tokens a page, median of both
    assert at_20["seconds"] == 40           # 2 seconds a page
    assert at_20["scaled_to_pages"] == 20
    assert at_20["samples"] == 2

    # Twice the site, twice the estimate.
    assert expert_estimates(conn, pages=40)["crawl"]["tokens"] == 40_000
    conn.close()


def test_estimates_say_when_they_are_not_scaled(tmp_path, site_fixture):
    """History without a page count still informs, but must not pretend to
    have been sized to this site."""
    from clauditseo.persistence.runs import expert_estimates, store_expert_report

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    store_expert_report(conn, run_id, "crawl",
                        {"model": "m", "report": "r", "tokens": 30_000})
    got = expert_estimates(conn, pages=100)["crawl"]
    assert got["tokens"] == 30_000 and got["scaled_to_pages"] is None
    conn.close()


def test_a_runaway_run_does_not_drag_every_later_estimate(tmp_path, site_fixture):
    """Medians, not means: one truncated or runaway brief should not poison
    the forecast for every future sweep."""
    from clauditseo.persistence.runs import expert_estimates, store_expert_report

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, _ = _db(tmp_path, ev)
    site_id = repo.list_sites(conn, repo.list_clients(conn)[0]["id"])[0]["id"]
    for tokens in (20_000, 21_000, 400_000):
        store_expert_report(conn, runs.create_run(conn, site_id, ["TEC"], "T2"),
                            "crawl",
                            {"model": "m", "report": "r", "tokens": tokens},
                            pages_crawled=100)
    estimate = expert_estimates(conn, pages=100)["crawl"]
    assert estimate["tokens"] == 21_000, "the outlier must not set the estimate"
    conn.close()


def test_briefs_with_no_history_are_counted_not_assumed_free(tmp_path, site_fixture):
    from clauditseo.persistence.runs import expert_estimates

    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, _ = _db(tmp_path, ev)
    assert expert_estimates(conn, pages=100) == {}
    conn.close()


def test_a_brief_raising_one_code_twice_is_merged():
    """The fingerprint is (site, tool, code), so five rows carrying the same
    code all collapse to one state — four of them invisible to the memory
    while the report showed the id five times, identifying none of them."""
    from clauditseo.persistence.runs import _merge_by_code

    merged = _merge_by_code([
        {"code": "sitemap-coverage", "severity": "low", "summary": "first",
         "affected_urls": ["https://x/a"]},
        {"code": "sitemap-coverage", "severity": "high", "summary": "second",
         "affected_urls": ["https://x/b"]},
    ])
    assert len(merged) == 1
    assert merged[0]["severity"] == "high"          # worst of the two
    assert merged[0]["affected_urls"] == ["https://x/a", "https://x/b"]
    assert "first" in merged[0]["summary"] and "second" in merged[0]["summary"]


# --- the declared-figure chain: figures must travel by value, not by re-read ---

_DECLARED_REPORT = """## CRAWL HEALTH SUMMARY

Organic sessions fell 755501 percent since the rebuild, costing 91724 dollars.

```clauditseo-findings
severity | code | summary | urls
high | sitemap-coverage | Organic sessions fell 755501 percent since the rebuild. |
```
"""


def _run_declared(tmp_path, site_fixture, report=_DECLARED_REPORT):
    """Drive the real production path, in the real order.

    `run_expert` records the findings and then stores the report — the order
    every caller uses (`expert.py:2165/2169` cached, `:2256/2282` fresh). A
    test that called the two persistence functions itself would prove only
    what the test did.
    """
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    # A legacy (non-contract) site brief hosts these declared-figure tests: the
    # feature is generic, and `_DECLARED_REPORT` is the legacy pipe-index shape.
    # `crawl`, `indexability` (brief v18 step BA) and `urls` (brief v19 step BB)
    # are contract briefs that read a JSON block instead, so the legacy path —
    # which the remaining briefs still use — is driven through `local-signals`
    # (it was `llms-txt-builder` until item 145 retired that brief),
    # a site-scoped legacy brief that is NOT split (a split brief asks twice and
    # a stub returns its report both times, doubling the findings index so the
    # first strip leaves the second — which the split hosts mobile-viewport and
    # https-security would). Its context echoes the crawled URL list, so a
    # URL-sourced digit still grounds. This clause has moved once per brief that
    # took the contract shape; it left `url-hygiene` when item 141 retired it.
    out = run_expert(conn, run_id, "local-signals", ev, Site(domain="fixture.local"),
                     cfg, StubExpert(report))
    assert out["status"] == "ok", out
    return conn, run_id, out


def test_a_declared_figure_is_marked_in_production_call_order(tmp_path, site_fixture):
    """The flag is read from a row the caller writes afterwards.

    `record_expert_findings` re-read `expert_reports.figures`, but every
    caller stores that row after recording the findings, so `declared` was
    always empty and the flag was stamped false forever. Nothing caught it
    because no test drove the two calls in the order production uses.
    """
    conn, run_id, out = _run_declared(tmp_path, site_fixture)
    assert out["figures_to_verify"], "the brief must declare an ungrounded figure"

    row = conn.execute(
        "SELECT evidence FROM findings WHERE run_id=? AND dimension='EXP:local-signals'",
        (run_id,)).fetchone()
    assert row, "the brief finding was not recorded"
    assert json.loads(row["evidence"]).get("figure_unverified") is True, (
        "a figure the brief itself flagged was recorded as verified")

    # The flag is not the point — reaching the client is. WF-03 was open for
    # fourteen rounds with the answer computed, stored and never rendered.
    from clauditseo.reporting.generate import _expert_section, tool_runs_for
    from clauditseo.reporting.render import ANALYST_FIGURE_NOTE
    site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                           (run_id,)).fetchone()["site_id"]
    section, _ = _expert_section(conn, tool_runs_for(conn, site_id), site_id, "client")
    assert "755501" in section, "the brief finding did not reach the document"
    assert ANALYST_FIGURE_NOTE in section, (
        "the declared figure reached a client document unmarked")
    conn.close()


def test_a_number_only_in_a_context_line_is_not_treated_as_declared():
    """A declared figure is its `value`, never the sentence it was quoted in.

    Both consumers stringified the whole `{value, context}` dict before
    extracting numbers, so every number sharing a sentence with a flagged
    figure was treated as flagged too.

    Asserted as a unit, deliberately. Driving a brief cannot isolate this:
    `ungrounded_figure_details` declares *every* ungrounded number in the
    report, so a second number in the prose is genuinely declared and the
    two behaviours are indistinguishable end to end. The distinguishing case
    is a context number that is NOT itself declared — a measured one, here
    `12` — which only a hand-built input can express.
    """
    from clauditseo.persistence.runs import declared_values

    figures = [{"value": "755501",
                "context": "Organic sessions fell 755501 percent across 12 pages."}]
    assert declared_values(figures) == {"755501"}, (
        "a number from the context line was treated as a declared figure")

    # Shape tolerance: a bare value, an empty value, and a blank all behave.
    assert declared_values([{"value": "7"}, {"value": ""}, {}]) == {"7"}
    assert declared_values(None) == set()


def test_a_measured_figure_is_not_marked(tmp_path, site_fixture):
    """The marker must not fire on a number the crawl actually measured.

    A marker that appears on measured figures teaches the operator to read
    past it, which is how a provenance signal stops being one.
    """
    report = _DECLARED_REPORT.replace(
        "high | sitemap-coverage | Organic sessions fell 755501 percent since the rebuild. |",
        "high | img-alt-missing | 1 images carry no alt attribute. |")
    conn, run_id, _ = _run_declared(tmp_path, site_fixture, report)
    row = conn.execute(
        "SELECT summary, evidence FROM findings WHERE run_id=?"
        " AND dimension='EXP:local-signals'", (run_id,)).fetchone()
    assert row and "alt attribute" in row["summary"]
    assert json.loads(row["evidence"]).get("figure_unverified") is not True, (
        f"a measured figure was marked as analyst-derived: {row['summary']!r}")
    conn.close()


#: The figure appears ONLY in the findings-index row. The prose above it
#: carries no number at all, which is the case the extraction could not see:
#: `parse_findings_block` removes the index before the figures are read.
_INDEX_ONLY_REPORT = """## CRAWL HEALTH SUMMARY

The sitemap does not agree with what the crawl reached.

```clauditseo-findings
severity | code | summary | urls
high | sitemap-coverage | Organic sessions fell 755501 percent since the rebuild. |
```
"""


def test_a_figure_stated_only_in_the_findings_index_is_still_declared(
        tmp_path, site_fixture):
    """The index is the text the client actually gets.

    `_expert_section` prints the index rows into the deliverable and drops the
    prose, so a figure that appears only in a row is precisely the figure that
    reaches a client. `run_expert` computed `figures_to_verify` from the
    report *after* `parse_findings_block` had removed that index, so the one
    surface the marker exists to protect was the one the extraction could not
    see.
    """
    conn, run_id, out = _run_declared(tmp_path, site_fixture, _INDEX_ONLY_REPORT)

    assert "755501" in {f["value"] for f in out["figures_to_verify"]}, (
        "a figure stated only in the findings index was not declared; "
        f"got {out['figures_to_verify']}")

    row = conn.execute(
        "SELECT evidence FROM findings WHERE run_id=? AND dimension='EXP:local-signals'",
        (run_id,)).fetchone()
    assert json.loads(row["evidence"]).get("figure_unverified") is True

    from clauditseo.reporting.generate import _expert_section, tool_runs_for
    from clauditseo.reporting.render import ANALYST_FIGURE_NOTE
    site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                           (run_id,)).fetchone()["site_id"]
    section, _ = _expert_section(conn, tool_runs_for(conn, site_id), site_id, "client")
    assert ANALYST_FIGURE_NOTE in section, (
        "the figure reached the client document unmarked")
    conn.close()


_CROWDED_REPORT = """## CRAWL HEALTH SUMMARY

Counts observed: 4111, 4222, 4333, 4444, 4555, 4666, 4777 and 4888.

```clauditseo-findings
severity | code | summary | urls
high | sitemap-coverage | Organic sessions fell 755501 percent since the rebuild. |
```
"""

_URL_COLUMN_REPORT = """## CRAWL HEALTH SUMMARY

The sitemap does not agree with what the crawl reached.

```clauditseo-findings
severity | code | summary | urls
high | sitemap-coverage | Twelve pages are absent. | https://x.test/blog/2024/09/top-15-loans, https://x.test/p?id=8871
```
"""


def test_a_finding_figure_is_not_crowded_out_by_prose_figures(tmp_path, site_fixture):
    """The set is capped at eight and ordered by string sort, not by position.

    So which figures survive is decided by lexicographic accident. Measured
    against the operator's own database: 9 of 25 stored briefs sit exactly at
    the cap, and on `content-gap` all eight slots went to section numbering
    (`0.5, 01 … 07`) while the figures its findings actually quote were
    dropped. A figure stated in a finding is the one that reaches a client,
    so it must not lose its slot to prose.
    """
    conn, run_id, out = _run_declared(tmp_path, site_fixture, _CROWDED_REPORT)
    declared = {f["value"] for f in out["figures_to_verify"]}

    assert "755501" in declared, (
        f"the finding's figure was crowded out by prose; got {sorted(declared)}")
    # And the prose figures it used to share the set with are not displaced.
    for prose in ("4111", "4888"):
        assert prose in declared, (
            f"{prose} lost its slot to the finding row; got {sorted(declared)}")
    conn.close()


def test_url_path_digits_are_not_declared_figures(tmp_path, site_fixture):
    """Scanning the raw index admitted its fourth column — the URL list.

    `parse_findings_block` already splits that column into structured URLs, so
    the extractor was re-reading as prose something the parser had understood.
    Path digits then consume slots in the capped set and are shown to the
    operator as figures the analyst derived, which teaches them to skim the
    one panel that exists to be read carefully.
    """
    conn, run_id, out = _run_declared(tmp_path, site_fixture, _URL_COLUMN_REPORT)
    declared = {f["value"] for f in out["figures_to_verify"]}

    for path_digit in ("2024", "09", "8871", "15"):
        assert path_digit not in declared, (
            f"{path_digit} came from a URL, not a claim; got {sorted(declared)}")
    conn.close()


# --- hreflang applicability -------------------------------------------------
#
# The condition, never the fixture. Both paid golden runs on 2026-08-24 raised
# hreflang against a deliberately single-locale site and it was the only false
# positive either model produced — with a context that named no locale at all,
# so neither model had anything to decide applicability from. These assert what
# the brief is *told*, on records built from the condition itself.

def _locale_records(*pairs, hreflang=None):
    return [{"url": url, "lang": lang,
             "hreflang": hreflang if url == pairs[0][0] else []}
            for url, lang in pairs]


def test_a_single_locale_site_is_told_its_hreflang_absence_is_correct():
    from clauditseo.analysts.expert import locale_evidence

    text, multi = locale_evidence(
        _locale_records(("https://x.test/", "en"),
                        ("https://x.test/services", "en")), "https://x.test/")
    assert multi is False
    assert "SINGLE locale" in text
    assert "absence is correct rather than a defect" in text


def test_a_second_declared_language_makes_hreflang_apply():
    from clauditseo.analysts.expert import locale_evidence

    text, multi = locale_evidence(
        _locale_records(("https://x.test/en/", "en"),
                        ("https://x.test/de/", "de")), "https://x.test/")
    assert multi is True
    assert "APPLIES" in text and "more than one declared language" in text


def test_locale_shaped_folders_alone_make_hreflang_apply():
    """A site can serve two locales and declare `lang` on neither."""
    from clauditseo.analysts.expert import locale_evidence

    text, multi = locale_evidence(
        _locale_records(("https://x.test/en-au/", None),
                        ("https://x.test/en-gb/", None)), "https://x.test/")
    assert multi is True
    assert "more than one locale-shaped URL folder" in text


def test_an_existing_annotation_makes_hreflang_apply_on_one_declared_language():
    """The trap the gate must not spring: a broken cluster on a site whose
    pages all declare the same `lang` is exactly the case the brief exists
    for, and a locale count alone would wave it through."""
    from clauditseo.analysts.expert import locale_evidence

    text, multi = locale_evidence(
        _locale_records(("https://x.test/", "en"), ("https://x.test/a", "en"),
                        hreflang=[["de", "https://x.test/de/"]]),
        "https://x.test/")
    assert multi is True
    assert "alternate annotations already in place" in text


def test_the_hreflang_brief_carries_the_locale_evidence_into_its_prompt(site_fixture):
    """The builder can be right and the brief still never see it — the
    placeholder has to exist in the prompt file."""
    ev = snapshot(crawl(site_fixture.base_url + "/", Tier.T2, budget=FAST))
    context = build_context("hreflang", ev, Site(domain="fixture.local"))
    assert "OBSERVED_LOCALE_EVIDENCE" in context
    prompt = render_prompt("hreflang", context)
    assert "{{" not in prompt
    assert context["OBSERVED_LOCALE_EVIDENCE"] in prompt


def test_the_hreflang_brief_is_told_the_gate_is_settled_and_may_not_re_decide_it():
    """Rewritten with the prompt at schema intl/2 (item 148, brief v20), and
    the instruction is now the OPPOSITE of what it was — for the same reason.

    The old prompt carried an `# APPLICABILITY GATE` section telling the model
    how to report "does not apply". That branch was **unreachable**:
    `_hreflang_applies` is wired as `applies` on the tool and the engine does
    not dispatch this brief at all on a single-locale site with no target
    locales stated (Q-32, answered "gate it server-side" by the operator on
    31 August 2026). A model that is running has already passed the gate, so a
    "not applicable" row could only ever be a false absence.

    So the concern has not been dropped, it has been inverted: the brief must
    be TOLD the gate is settled, and must be FORBIDDEN from emitting the row.
    Asserted here rather than left to the prompt's author, because a model
    handed a FORMAT with an x-default assessment in it will fill that section
    with something, and "not applicable" is the plausible thing to fill it with.
    """
    from clauditseo.analysts.expert import PROMPT_DIR

    brief = (PROMPT_DIR / "hreflang.md").read_text(encoding="utf-8")
    assert "THE GATE HAS ALREADY BEEN DECIDED" in brief
    assert "Do not re-litigate it" in brief
    # The prohibition, and it appears twice on purpose — once where the gate is
    # explained and once in the rules, because the rules are what a model
    # re-reads while writing Block 2.
    assert brief.count('"not applicable" row') >= 2, (
        "the prohibition must survive into the rules, not only the preamble")
    # And the one case that DOES survive the gate, so the section is not simply
    # a refusal with nothing behind it.
    assert "locale evidence that conflicts" in brief
    # The old prompt called Block 1 a "machine-readable findings index"; the
    # rewrite makes it a fenced JSON object and declares its schema version, so
    # the assertion pins the version rather than the old phrase. A schema bump
    # that the contract reader has not been taught is the failure this catches.
    assert "## Block 1 — findings" in brief
    assert '"schema": "intl/2"' in brief
