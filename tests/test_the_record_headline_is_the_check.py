"""The record's group headline is the check, never its first instance's
sentence; coverage notes are a strip of their own with no verb; "on pages
gone" is a filter; and the verbs sit behind the row's overflow.

Brief v2 step F (`_plans/site-screen-brief-v2-2026-09-03.md`, UX-08,
UX-09, UI-04). The headline of a 227-page group was its first instance's
sentence, "Heading level jumps H1→H4 on /blog/attention-brokers…" (UX-08);
five Info-severity "not assessed" notes sat among findings with
accept/withdraw ×N beside them (UX-09); and the two verbs stood at equal
weight on every row (UI-04).

**What the brief asked for that the product cannot give, recorded here.**
The headline was to be "the check's own description (the catalogue
string)"; no catalogue of check descriptions exists on the wire, so the
headline is the check's id said as words. "Seen once" needs a field the
record does not carry - which audit first saw a finding - and is not
offered. The filters became chips in brief v3 step L
(`test_the_record_filters_are_chips.py`); this file drives them as chips.
"""

from __future__ import annotations

import re

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

COVERAGE = re.compile(r"(-not-assessed$|-coverage$|^third-party-scripts)")

_JS = """() => ({
  groups: [...document.querySelectorAll('tbody tr.group-row')].map((tr) => ({
    key: (tr.querySelector('code')?.textContent || '').trim(),
    headline: (tr.querySelector('.group-headline')?.textContent || '').trim(),
    verbsInline: [...tr.querySelectorAll('td:last-child > button')].length,
    more: tr.querySelectorAll('td:last-child details.row-more').length,
    verbs: [...tr.querySelectorAll('td:last-child button')].map((b) => b.textContent.trim()),
  })),
  notes: [...document.querySelectorAll('.coverage-notes li')].map((li) => ({
    check: (li.querySelector('code')?.textContent || '').trim(),
    buttons: li.querySelectorAll('button').length,
  })),
  notesSummary: (document.querySelector('.coverage-notes summary')?.textContent || '').trim(),
  options: [...document.querySelectorAll('[aria-label="state filter"] [data-state]')].map((b) => b.dataset.state),
  intro: (document.querySelector('.pane-body > p.muted')?.textContent || '').trim(),
  introOpen: !!document.querySelector('.record-what[open]'),
  banner: (document.querySelector('.mark-bar')?.textContent || '').trim(),
  rows: document.querySelectorAll('tbody tr:has(code)').length,
})"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _open(browser, base, site_id, tail=""):
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(f"{base}/#/sites/{site_id}?tab=all{tail}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".state-filters", timeout=30_000)
    pg.click('[aria-label="state filter"] [data-state="all"]')
    pg.wait_for_selector("tbody tr:has(code)", timeout=30_000)
    return pg


def test_the_headline_is_the_check_and_the_notes_are_a_strip(browser, served):
    import httpx

    base, ids = served
    states = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()["states"]
    notes = [s for s in states if s["severity"] == "info" and COVERAGE.search(s["check_id"])]
    assert notes, "precondition: the fixture holds no coverage note"
    first_summary = {}
    for s in states:
        first_summary.setdefault(f"{s['dimension']}/{s['check_id']}", s["summary"])

    # A coverage note is Info-severity (the product's `is_coverage_note` rule);
    # a real finding that merely shares the `-coverage` suffix — `sitemap-coverage`
    # is MEDIUM since item 137 (brief v18 step AZ) — is a finding, and belongs in
    # the rows. Match the product: the note keys are the Info-severity ones only.
    note_keys = {f"{s['dimension']}/{s['check_id']}" for s in notes}

    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["groups"], got
    for g in got["groups"]:
        assert g["headline"], g
        assert g["headline"] != first_summary.get(g["key"]), (
            f"{g['key']}'s headline is its first instance's sentence: {g['headline']!r}")
        assert g["key"] not in note_keys, (
            f"a coverage note is grouped as a finding: {g['key']}")
    assert {n["check"] for n in got["notes"]} == {f"{s['dimension']}/{s['check_id']}" for s in notes}
    assert all(n["buttons"] == 0 for n in got["notes"]), got["notes"]
    assert got["notesSummary"].startswith(f"Coverage notes — not findings ({len(notes)})"), got["notesSummary"]


def test_the_verbs_sit_behind_the_rows_overflow(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    with_verbs = [g for g in got["groups"] if g["verbs"]]
    assert with_verbs, got["groups"]
    for g in with_verbs:
        assert g["verbsInline"] == 0 and g["more"] == 1, g


def test_pages_gone_is_a_filter_and_the_intro_is_one_sentence(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
        pg.click('[aria-label="state filter"] [data-state="gone"]')
        pg.wait_for_timeout(300)
        gone = pg.evaluate(_JS)
    finally:
        pg.close()
    assert "gone" in got["options"], got["options"]
    # Every group left under the filter carries the marker's count.
    assert all(g["key"] for g in gone["groups"]), gone
    assert got["intro"].startswith("Every finding this site has ever had"), got["intro"]
    assert got["intro"].count(".") <= 2 or not got["introOpen"], got["intro"]
    assert not got["introOpen"]
