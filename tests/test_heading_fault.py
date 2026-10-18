"""`heading-skip` records the position of the heading that skipped a level.

`heading-skip` said "Heading level jumps H2 to H4 on /" and no more, and on a
page with forty-eight headings that left the operator counting down the outline
by hand. So the check records `outline_index` — where in the outline the skip
is — and this file is the check side of it: the position is the deeper heading
not the one before it, is the first skip only, is recorded beside the sequence,
and reaches the wire, or is absent as a key rather than a null.

**The display of that position is retired (Q-51, operator 2026-09-07).** F-07
opened the page's tagged outline list at the recorded position; that list was a
second outline on the Headings card and it was retired for the v16d ladder,
which reads `onp.heading_outline_state` directly and marks the skip from the
outline itself rather than from a stored index. The four browser tests that
read that display (`.out-fault`, `.out-unplaced`) went with it. The check still
records the index — it is cheap, and a later display may want it — which is why
the check-side tests below stay. The browser helpers here (`open_headings`,
`browser_page`, `live`, `restage`, `restore`) remain because other files import
them.

**Ordinary tests, not guards**, per the rule `FEATURES.md` states: the
behaviour did not exist, so there was no prior failure to observe and DISCIPLINE
rule 1 does not apply. Every assertion here was red against the tree before the
feature — `outline_index` appeared nowhere in the engine, on the wire, or in
the bundle.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from clauditseo import axe
from clauditseo.crawler.types import Page
from clauditseo.modules.onp import OnPageModule
from clauditseo.modules.pagefacts import extract_facts
from clauditseo.persistence.runs import _outline_index
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.parts import open_part, open_page_filter

MOD = OnPageModule()


def facts_for(body: str, url: str = "https://x.test/"):
    return extract_facts(Page(url=url, requested_url=url, status=200,
                              content_type="text/html; charset=utf-8",
                              content=f"<html lang=en><body><main>{body}"
                                      "</main></body></html>"))


def skip_finding(body: str):
    found = [f for f in MOD._page_checks(facts_for(body))
             if f.check_id == "heading-skip"]
    return found[0] if found else None


# --- clause 1: the check carries the position -------------------------------

def test_the_finding_names_the_heading_that_skipped_not_only_that_one_did():
    """The position is an index into the same outline the screen renders, so
    the two cannot disagree about which heading is meant."""
    body = "<h1>Top</h1><h2>One</h2><h2>Two</h2><h4>Jumped</h4>"
    f = skip_finding(body)
    assert f is not None, "the fixture does not even raise the finding"
    at = f.evidence["outline_index"]
    assert at == 3, f"expected the H4 at position 3, got {at}"
    assert facts_for(body).headings[at] == (4, "Jumped"), (
        "the index points at a different heading than the one the summary "
        "describes")


def test_the_position_is_the_deeper_heading_not_the_one_before_it():
    """`zip(levels, levels[1:])` yields pairs, and the off-by-one it invites
    is the difference between marking the fault and marking the heading above
    it — which reads as a correct outline with a mark on it."""
    f = skip_finding("<h1>Top</h1><h3>Jumped</h3>")
    assert f.evidence["outline_index"] == 1, (
        "the H1 is not the fault; the H3 that followed it is")


def test_only_the_first_skip_is_reported_and_the_position_is_its_own():
    """The check stops at the first skip. The position has to be that skip's,
    not the last one on the page."""
    f = skip_finding("<h1>Top</h1><h3>First jump</h3><h2>Back</h2>"
                     "<h2>Level</h2><h5>Second jump</h5>")
    assert f.evidence["outline_index"] == 1


def test_a_page_whose_levels_are_sequential_raises_nothing_to_place():
    assert skip_finding("<h1>Top</h1><h2>One</h2><h3>Deeper</h3>") is None


def test_the_sequence_is_still_recorded_beside_the_position():
    """The shape of the outline was this finding's evidence before the
    feature and is still what a reader checks the claim against."""
    f = skip_finding("<h1>Top</h1><h2>One</h2><h4>Jumped</h4>")
    assert f.evidence["sequence"] == [1, 2, 4]


# --- clause 2: what the wire does with it, and without it -------------------

def test_a_stored_position_reaches_the_wire():
    assert _outline_index(json.dumps({"sequence": [1, 4], "outline_index": 1})) == 1


@pytest.mark.parametrize("evidence,why", [
    (None, "a finding with no evidence at all"),
    ("", "an empty evidence column"),
    ("{}", "evidence that records nothing"),
    (json.dumps({"sequence": [2, 4]}),
     "a finding stored before the check recorded a position"),
    ("not json at all", "evidence that will not parse"),
    ("[1, 2, 3]", "evidence that is not an object"),
    (json.dumps({"outline_index": "3"}), "a position stored as a string"),
    (json.dumps({"outline_index": True}),
     "a bool, which is an int in Python and would sail through isinstance"),
    (json.dumps({"outline_index": None}), "a position explicitly null"),
])
def test_every_way_a_position_can_be_absent_answers_none(evidence, why):
    """None is the answer, and the caller then sends no key at all — so the
    screen can never mistake a default for a measurement. That is the whole
    of the second sentence of the acceptance signal."""
    assert _outline_index(evidence) is None, why


def test_the_key_is_absent_from_the_payload_rather_than_null(tmp_path):
    """A `null` on the wire is a value, and a screen reading it as one has to
    remember that this particular null means "nobody measured this". Absent
    is not forgettable."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    conn = connect(tmp_path / "wire.db")
    migrate(conn)
    operator = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, operator, "Wire Co")
    site = repo.create_site(conn, client, "wire.test")
    run_id = runs.create_run(conn, site, ["ONP"], "T2")
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
        " summary, affected_urls, evidence, fingerprint, created_at)"
        " VALUES ('f1', ?, 'ONP', 'heading-skip', 'low', 'Old finding.',"
        " '[\"https://wire.test/\"]', '{\"sequence\": [2, 4]}', 'fp1',"
        " '2026-01-01T00:00:00+00:00')", (run_id,))
    conn.execute(
        "INSERT INTO finding_states (site_id, fingerprint, state,"
        " changed_by_run, updated_at)"
        " VALUES (?, 'fp1', 'open', ?, '2026-01-01T00:00:00+00:00')",
        (site, run_id))
    conn.commit()

    headings = [c for c in runs.anatomy_view(conn, site)["categories"]
                if c["key"] == "headings"][0]
    assert headings["findings"], "the fixture stored no open finding"
    assert "outline_index" not in headings["findings"][0], (
        "a finding with no recorded position must carry no position key")


# --- clauses 1 and 2 again, on the screen, in a browser ---------------------

def restage(db: str, mutate) -> list:
    """Rewrite the stored `heading-skip` evidence, and hand back the original.

    The fixture database is shared with the tests above, so every caller
    restores what it changed. Amending what was *stored* rather than
    arranging a screen state is the point: the case being rendered is a real
    stored finding, which is the only way the second sentence of the
    acceptance signal can be read honestly.
    """
    conn = sqlite3.connect(db)
    before = conn.execute(
        "SELECT id, evidence FROM findings WHERE check_id='heading-skip'"
        " AND evidence LIKE '%outline_index%'").fetchall()
    assert before, "the fixture holds no placed finding to amend"
    for fid, evidence in before:
        conn.execute("UPDATE findings SET evidence=? WHERE id=?",
                     (json.dumps(mutate(json.loads(evidence))), fid))
    conn.commit()
    conn.close()
    return before


def restore(db: str, before: list) -> None:
    conn = sqlite3.connect(db)
    for fid, evidence in before:
        conn.execute("UPDATE findings SET evidence=? WHERE id=?", (evidence, fid))
    conn.commit()
    conn.close()


def open_headings(pg, base: str, site: str, path: str) -> None:
    """The client screen, narrowed to one page, with Headings open.

    Both steps, in this order, because the outline renders only once a page
    is chosen: the part's "what the page has now" card is the one-page
    block, and there is nothing to read back before then.

    The card is the three-block page's since brief v14 step AP; the outline
    is the v16d ladder (`.ho-ladder`) since Q-51 retired the tagged list, so
    the wait is on the ladder rather than the list.
    """
    pg.goto(f"{base}/#/sites/{site}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=15_000)
    open_part(pg, 'Headings')
    open_page_filter(pg)
    pg.fill(".page-find", path)
    pg.wait_for_selector(".now-card", timeout=15_000)
    pg.wait_for_selector(".ho-ladder", timeout=15_000)
    pg.wait_for_timeout(300)


#: The two conditions the live tests below need, copied from
#: `test_a11y_rendered.py` rather than invented — the same browser and the
#: same built bundle, for the same reason. Applied per test rather than as a
#: module `pytestmark`, which would take the static ones with them.
#:
#: Guarded at collection, not inside the body: the `python` job installs no
#: extras by design, so an import of `sync_playwright` above a
#: `pytest.skip` turns a skip into a red run — the mistake F-10's live test
#: records making. And a skip here is not the clause going quiet:
#: `.github/workflows/ci.yml` runs this file in `rendered-a11y` too, where
#: both conditions hold and the job fails on any skip.
def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@pytest.fixture()
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 720})
        try:
            yield pg
        finally:
            browser.close()
