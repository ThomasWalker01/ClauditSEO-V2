"""A part shows only its own replacement copy (item 218).

"Replacement copy · 50 of 205" on the Backlinks page held no backlinks row:
its rows were Indexability, Crawl, Structured data and Links checks. The
table filtered with `checks.size === 0 || checks.has(s.check_id)`, where
`checks` was the part's BRIEF checks, so a part with no brief passed every
proposed row in the site record. Any part without a brief had the same hole.

It now asks the part's one ownership rule (`belongsTo`, the rule `fixesOf`
files cards by), and a part that owns no check says it has no replacement
copy and draws nothing else.
"""

from __future__ import annotations

from pathlib import Path

from tests.needs_build import needs_build
from tests.parts import open_part
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)
from tests.test_the_client_landing_is_three_lanes import _page

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


@needs_build
def test_a_part_that_owns_no_check_borrows_no_other_parts_copy(served):
    base, ids = served

    def go(pg):
        owns = pg.evaluate(f"""async () => (await (await fetch('/api/sites/{ids['site']}/anatomy')).json())
          .categories.find((c) => c.key === 'backlinks')""")
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
        pg.wait_for_selector(".anat-layout", timeout=15_000)
        open_part(pg, "Backlinks")
        pg.wait_for_timeout(1500)
        return owns, pg.evaluate("""() => ({
          none: (document.querySelector('.rep-none')?.textContent || '').trim(),
          heads: [...document.querySelectorAll('h4')].map((h) => h.textContent.trim()) })""")

    owns, got = _page(served, go)
    assert not (owns.get("brief_checks") or owns.get("filed_checks") or owns.get("check_prefixes")), (
        f"the fixture's Backlinks owns checks now, so this clause tests nothing: {owns}")
    assert not any(h.startswith("Replacement copy") for h in got["heads"]), (
        f"a part that owns no check drew another part's replacement copy: {got}")
    assert got["none"] == "No replacement copy for this part.", got


def test_the_table_asks_the_parts_own_rule():
    src = (UI / "anatomy.tsx").read_text(encoding="utf-8")
    assert "checks.size === 0 ||" not in src, "the empty set still means every row"
    assert "belongsTo(current)" in src
    page = (UI / "part_page.tsx").read_text(encoding="utf-8")
    assert "const belongs = belongsTo(part);" in page, (
        "the Fixes block and the replacement table have two ownership rules again")
