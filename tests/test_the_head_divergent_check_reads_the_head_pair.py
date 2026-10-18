"""Item 165: TEC/head-divergent, and `js-rendering` retired.

js-rendering's parity table asked about canonical, meta description, robots,
hreflang and Open Graph. `render-only` does not cover them, and the 160 head
pair captured all five with only the viewport diffs reading it. The check
reads that pair; the brief retires.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from clauditseo.modules import tec

ROOT = Path(__file__).resolve().parents[1]
URL = "https://x.test/a"
FACTS = SimpleNamespace(path="/a")
SERVED = ('<head><title>A</title><meta name="description" content="Served">'
          '<meta property="og:title" content="A"></head>')


def _run(fetched, rendered, traced=True):
    trace = {"traced": traced, "head_fetched": fetched, "head_rendered": rendered}
    return tec._head_divergent("TEC", FACTS, URL, trace)


def test_head_divergent_fires_on_a_rendered_canonical_the_fetch_did_not_carry():
    rendered = SERVED.replace("</head>", '<link rel="canonical" href="https://x.test/a"></head>')
    got = _run(SERVED, rendered)
    assert len(got) == 1 and got[0].check_id == "head-divergent"
    assert got[0].evidence["elements"] == [
        {"element": "canonical", "case": "injected", "fetched": None, "rendered": "https://x.test/a"}]
    assert got[0].severity.name == "MEDIUM"


def test_head_divergent_is_one_row_per_page():
    rendered = (SERVED.replace("Served", "Rewritten")
                .replace("</head>", '<meta name="robots" content="noindex">'
                                    '<link rel="alternate" hreflang="en-AU" href="https://x.test/au"></head>'))
    got = _run(SERVED, rendered)
    assert len(got) == 1
    assert {(e["element"], e["case"]) for e in got[0].evidence["elements"]} == {
        ("meta description", "changed"), ("meta robots", "injected"), ("hreflang en-au", "injected")}
    # The same head twice, or only the viewport differing, is not this check's.
    assert _run(SERVED, SERVED) == []
    viewport = SERVED.replace("</head>", '<meta name="viewport" content="width=device-width"></head>')
    assert _run(SERVED, viewport) == []


def test_head_divergent_is_not_assessed_on_an_untraced_page():
    rendered = SERVED.replace("</head>", '<link rel="canonical" href="https://x.test/a"></head>')
    assert _run(SERVED, rendered, traced=False) == []
    assert tec._head_divergent("TEC", FACTS, URL, None) == []
    assert _run(tec.UNAVAIL, rendered) == []
    # And the screen says not assessed rather than clean: the trace rung, and
    # the version rung for traced runs from before the check existed.
    assert "head-divergent" in tec.TRACE_DERIVED_CHECKS
    assert tec.COLLECTED_SINCE["head-divergent"] == "0.26.0"
    from clauditseo import anatomy
    assert anatomy.categorise("head-divergent", "TEC") == "crawl"


def test_js_rendering_is_not_offered_anywhere():
    from clauditseo import anatomy, briefs, playbook
    from clauditseo.analysts.expert import EXPERT_TOOLS
    assert "js-rendering" not in EXPERT_TOOLS
    assert not (ROOT / "clauditseo" / "prompts" / "js-rendering.md").exists()
    assert "js-rendering" not in {b.id for b in briefs.catalogue()}
    tools = [t for phase in playbook.PLAYBOOK for t in phase["tools"]]
    assert "js-rendering" not in {t["id"] for t in tools} | {t.get("expert") for t in tools}
    assert "js-rendering" not in anatomy.TOOL_CATEGORIES
    # A page-scoped brief still exists, so the vehicles re-homed onto one are
    # not passing because their population emptied (3a's rule).
    assert any(v.get("scope") == "page" for v in EXPERT_TOOLS.values())
    crawl = next(t for t in tools if t["id"] == "crawl")
    assert "head-divergent" in crawl["checks"]
