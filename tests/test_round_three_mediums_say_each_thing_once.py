"""Round-3 Medium findings where one screen said a thing two ways.

- URLs AC-01: the part header called rows "seen once" that the record and
  the lane call "to confirm".
- Pages AC-03: "LCP p75 is 6603 ms … Measured from a single lab run": one
  run has no 75th percentile.
- Local AC-02: "Scores under EXP, LOC", while an analysis row never scores.
- Content AC-04: "analysed under an earlier brief" on every analysis card of
  the part, from one part-wide flag.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.modules import prf
from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"
ANAT = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
PAGE = (SRC / "part_page.tsx").read_text(encoding="utf-8")


def test_the_part_count_says_to_confirm():
    assert "` · ${current.to_confirm!.value} to confirm`" in ANAT


def test_p75_only_for_field_data():
    assert "{'p75 ' if got.source == 'crux' else ''}is " in inspect.getsource(prf)


def test_a_part_does_not_score_under_exp():
    assert '.filter((d) => !d.startsWith("EXP")).join(", ")' in ANAT
    assert '?.some((d) => !d.startsWith("EXP")) ? (' in ANAT


def test_the_earlier_brief_mark_is_per_card():
    assert '"brief_changed": _brief_changed(er["tool_id"], er["brief_version"]),' \
        in inspect.getsource(runs).split("brief_runs.setdefault(part, []).append({", 1)[1][:900]
    assert "earlierBrief={(part.brief_runs ?? []).some((r) => r.brief_changed" in PAGE
    assert "(f.briefs ?? []).includes(r.tool)" in PAGE


def test_one_observation_is_listed_once_with_its_pages():
    # Run views AC-03: one NOINDEX-LINKED sentence four times, no page named.
    comp = (SRC / "components.tsx").read_text(encoding="utf-8")
    assert "export function oneInsightPerSentence(" in comp
    assert "const observed = oneInsightPerSentence(" in comp
    assert '<div className="muted insight-pages">' in comp
    assert ".insight-pages {" in (SRC / "styles.css").read_text(encoding="utf-8")


def test_the_crawl_pair_is_two_readings_of_the_site():
    # Record AC-02: a one-page scan after any audit was "one of the two newest
    # crawls" and silenced the comparison for the whole site.
    pane = (SRC / "pane_audit.tsx").read_text(encoding="utf-8")
    assert 'r.site_reading !== false && !r.part_only && !["page", "nav"].includes(scopeOf(r) ?? "")' in pane
    src = inspect.getsource(runs.crawl_diff)
    assert "NOT IN ('page', 'nav')" in src and "part_only_runs(conn, site_id)" in src


def test_render_only_is_clean_over_the_pages_the_rendered_pass_read():
    # Crawl AC-03: "clean on every page this audit fetched (45 crawled)" for a
    # check the tile said read 0 of 5 rendered pages.
    app = (SRC.parent.parent / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'cat["samples"] = {"render-only": {"n": _rendered, "basis": "rendered"}}' in app


def test_the_compromise_verdict_shows_what_was_seen_loading():
    # Security AC-06: the verdict's basis is the model's inventory; the screen
    # now shows the hosts the automatic checks saw scripts and styles load
    # from, and names any the basis leaves out.
    app = (SRC.parent.parent / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'cat["load_origins"] = sorted({h for kind in ("script", "style")' in app
    assert "The automatic checks saw scripts and styles load from {seen.join(\", \")}." in PAGE
    assert "The analysis&rsquo;s basis does not name {unnamed.join(\", \")}." in PAGE


def test_a_check_the_analysis_passed_is_said_passed():
    # Structured data AC-03: "a pass, not a hold" in the drops, "neither clean
    # nor open" in the table, "not a pass" in page mode, for one check.
    assert 'const PASS_NOT_HOLD = "a pass, not a hold";' in PAGE
    assert ".filter((d) => d.reason !== PASS_NOT_HOLD)" in PAGE
    assert "analysis judged and found nothing wrong with" in PAGE
    assert '=== "model" && !passedHere.has(c)' in PAGE
    import inspect as _i
    from clauditseo.analysts import contract
    assert '"reason": "a pass, not a hold"' in _i.getsource(contract)


def test_a_resolved_row_that_is_also_held_says_why():
    # Structured data AC-07: "resolved by the ... fix" in the table, and the
    # hold line pointing at "the reason on its row" that carried none.
    assert "+ (heldN ? ` · held where not: ${heldSays(" in PAGE
