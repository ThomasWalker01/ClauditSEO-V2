"""The Speed contract brief (item 141, brief v19 step BC): it loads and
conforms, declares its eighteen checks (thirteen free the trace sweep raises,
five analysis the brief judges), the five analysis checks are priced as model
calls, and its context reads the per-page performance trace the browser pass
stored. The free-check judgements are pinned in test_the_speed_trace_checks;
the part page and its six visuals are held behind 150 BJ -> 155, so nothing
about the display is asserted here."""

from __future__ import annotations

from clauditseo import briefs
from clauditseo.analysts.expert import EXPERT_TOOLS, _speed_context, conforms
from clauditseo.checks import check_costs
from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Site, Tier

FREE = ["lcp-slow", "cls-high", "inp-long-tasks", "ttfb-slow", "render-blocking",
        "unused-css-js", "uncompressed", "no-cache-headers", "unminified",
        "third-party-weight", "page-weight", "cwv-not-assessed"]
ANALYSIS = ["critical-path", "lcp-cause", "cls-cause", "inp-cause", "third-party-policy"]


def test_the_brief_loads_conforms_and_owns_the_speed_part():
    by = briefs.by_id()
    assert by["speed"].part == "speed" and by["speed"].scope == "site"
    assert len(by["speed"].checks) == 18 and conforms("speed")
    assert EXPERT_TOOLS["speed"]["build"] is _speed_context


def test_the_five_analysis_checks_are_priced_as_model_calls():
    costs = check_costs()
    for c in ANALYSIS:
        assert costs.get(f"PRF/{c}") == "model" or costs.get(c) == "model", c
    # The free checks the sweep raises stay free.
    for c in FREE:
        assert costs.get(f"PRF/{c}", "free") == "free" or costs.get(c, "free") == "free", c


def _page(url, html):
    return Page(url=url, requested_url=url, status=200, content_type="text/html", content=html)


def test_the_context_renders_the_trace_and_marks_untraced_pages(tmp_path):
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[
        _page("https://x.test/", "<html><head><title>t</title></head><body><h1>h</h1></body></html>"),
        _page("https://x.test/blog/a", "<html><head><title>t</title></head><body><h1>h</h1></body></html>"),
    ])
    # One page traced, one not — the context must render the trace and name the
    # untraced page rather than inventing numbers for it.
    trace = {
        "device_profile": "mid-tier mobile, 4G", "ttfb_ms": 720, "fcp_ms": 1100,
        "lcp": {"ms": 3400, "element": "img.hero", "url": "https://x.test/hero.avif",
                "is_image": True, "sub_parts": {"ttfb": 720, "load_delay": 1180,
                                                "load_time": 940, "render_delay": 560}},
        "cls": {"value": 0.18, "shifts": [{"value": 0.18, "sources": ["div#ad"]}]},
        "tbt_ms": 610,
        "long_tasks": [{"start_ms": 900, "duration_ms": 200,
                        "scripts": [{"url": "https://cdn.ads.com/t.js", "ms": 180}]}],
        "resources": [{"url": "https://x.test/theme.css", "type": "css", "bytes": 180000,
                       "transfer": 190000, "start_ms": 200, "duration_ms": 300,
                       "blocking": True, "async": False, "defer": False, "media": None,
                       "discovered_by": "link", "cache_control": None,
                       "compression": "none", "coverage": {"used": 20000, "total": 180000},
                       "whitespace_ratio": 0.35}],
        "fonts": [{"family": "Inter", "display": "block", "preloaded": False, "swap_observed": "unavailable"}],
        "head_rendered": "<head><title>t</title></head>",
        "frames": "unavailable",
    }
    ev = snapshot(crawl, perf_traces={"https://x.test/": trace})
    ctx = _speed_context(ev, Site(domain="x.test"), conn=None, run_id=None)
    ps = ctx["PAGE_SET"]
    assert "LCP 3400 ms" in ps and "img.hero" in ps
    assert "render_delay 560" in ps                      # sub-parts rendered
    assert "cdn.ads.com/t.js 180ms" in ps                # long task by script
    assert "template /" in ps                            # template from the pattern table
    assert "/blog/a" in ps and "not traced" in ps        # the untraced page named
    assert ctx["DEVICE_PROFILE"].startswith("mid-tier mobile")
    assert "no field data connected" in ctx["FIELD_DATA"]   # cwv-not-assessed path
    # Budgets default to Google's where the record is silent.
    assert ctx["LCP_GOOD"] == "2500" and ctx["TTFB_GOOD"] == "800"


def test_a_site_budget_overrides_the_default_in_context():
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2,
                        pages=[_page("https://x.test/", "<html><body>x</body></html>")])
    ev = snapshot(crawl)
    ctx = _speed_context(ev, Site(domain="x.test", ttfb_good="500", framework="Next.js"),
                         conn=None, run_id=None)
    assert ctx["TTFB_GOOD"] == "500" and ctx["FRAMEWORK"] == "Next.js"


def test_the_page_set_is_substituted_once_and_not_into_a_sentence() -> None:
    """`{{PAGE_SET}}` is the trace dataset — tens of kilobytes — so every
    occurrence in the spec is a copy of it in the prompt.

    It appeared **twice**: once as the data block, which is its job, and once as
    a *noun inside the task sentence* (`For {{PAGE_SET}}: (1) read the free rows
    …`), where the writer meant "the page set" and substitution wedged the whole
    dataset mid-instruction.

    Measured on the brief's first live run (twenty22 `95ac5495`,
    2026-09-12): the duplicate was **~23,800 of 53,225 input tokens — USD
    0.0595, 19% of a USD 0.308 run**. Checked against the output before it was
    changed: the report named all twelve templates with exact figures either
    way, so this was a cost defect and not a quality one.

    The spec is installed verbatim, so this is asserted here rather than left to
    review: a second copy is invisible reading the file and costs a fifth of
    every run.
    """
    from pathlib import Path
    import re

    spec = (Path(__file__).resolve().parents[1]
            / "clauditseo" / "prompts" / "speed.md").read_text(encoding="utf-8")
    seen = re.findall(r"\{\{PAGE_SET\}\}", spec)
    assert len(seen) == 1, (
        f"{{{{PAGE_SET}}}} appears {len(seen)} times; each one copies the whole "
        "trace dataset into the prompt")

    # And the surviving one is the data block, not prose. The line that carries
    # it is a labelled field, so the placeholder is preceded by its own name.
    line = next(ln for ln in spec.splitlines() if "{{PAGE_SET}}" in ln)
    assert "PAGE SET:" in line, (
        f"the surviving placeholder is not the data block: {line.strip()!r}")


def test_the_token_estimate_is_within_reach_of_what_a_real_run_billed() -> None:
    """The estimator gates the analyst layer's budget cap
    (`spent + est > budget_cap`), so reading low does not mislead a display —
    it lets a task through a cap that should have stopped it.

    Grounded in the one real measurement there is: the Speed brief's rendered
    prompt against twenty22 `95ac5495` was **124,256 characters** and billed
    **53,225** input tokens. At the old `chars // 4` that estimates 31,064, a
    1.71x under-read.

    Asserted as a bound rather than an equality, and **asymmetrically**: the
    estimate may exceed the real figure (a skipped task is visible and
    recoverable) but may not fall short of it (spend nobody authorised).
    """
    from clauditseo.analysts.layer import EST_OUTPUT_TOKENS, estimate_tokens

    MEASURED_CHARS, MEASURED_INPUT_TOKENS = 124_256, 53_225
    est = estimate_tokens(MEASURED_CHARS) - EST_OUTPUT_TOKENS
    assert est >= MEASURED_INPUT_TOKENS * 0.98, (
        f"estimate {est:,} reads low against a billed {MEASURED_INPUT_TOKENS:,} "
        "— the direction that overruns the budget cap")
    assert est <= MEASURED_INPUT_TOKENS * 1.30, (
        f"estimate {est:,} is more than 30% over a billed "
        f"{MEASURED_INPUT_TOKENS:,}; over-reading is the safe direction but a "
        "cap that never lets anything run is its own defect")
