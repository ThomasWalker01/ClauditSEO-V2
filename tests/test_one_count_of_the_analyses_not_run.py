"""Five readers of "analyses not run", one sum.

Audit finding F4, 2026-09-18. All of these were on screen at once on twenty22,
about one set:

    shell control        Open the catalogue · 24     25 tools - triage
    catalogue head       All analyses · 23 · 0 read · 21 can run now · 1 need a page
    landing lane         Analyses not run 23 · run 22, no estimate yet
    Run all button       Run all 21
    part-page drawer     All analyses · 24 not run

0 read + 21 can run now + 1 need a page = 22, under a head that said 23. The
unaccounted row is `migration-redirects`, whose state is `needs_input` and whose
own row in that catalogue reads "needs context a crawl cannot supply" - in none
of the three numbers, so the reader was left to find the difference.

Worse than untidy: `batch.count` counted it, so the landing told the operator
that pressing Run all would run 22 analyses and the button they then pressed ran
21. On Birch that promise carried a price - "USD 0.63 to run 22".

The rule is `catalogue.tsx`'s own, written above the numbers it describes:

    "The header's three numbers and the button's (brief v5 step Q): what is
     read, what can run now, what needs a page first. The button counts what
     run-all would tick - the same set as 'can run now'."

Three numbers that do not sum to the fourth is that rule not holding. And
`population.tsx`: "the server names each of them ... so two components cannot
word the same population two ways" - here five components worded one population
five ways.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


@pytest.fixture(scope="module")
def counted():
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("onecount")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "One Count"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "onecount.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, db, run_id, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_batch_totals_reconcile(counted):
    """`listed = count + need_page + needs_input + read`, which is what makes
    five readers of it agree. It did not hold: `count` and `listed` were 22 and
    23 with nothing naming the difference."""
    base, db, run_id, site_id = counted
    got = httpx.get(f"{base}/api/runs/{run_id}/analyses", timeout=60).json()
    b = got["batch"]
    for key in ("listed", "count", "need_page", "needs_input", "read"):
        assert key in b, f"{key} missing from the batch sum: {b}"
    assert b["listed"] == b["count"] + b["need_page"] + b["needs_input"] + b["read"], b


def test_the_batch_counts_only_what_run_all_would_run(counted):
    """`count` is the promise the landing quotes, with a price on it. It has to
    be the set the button ticks: not page-scoped AND `not_run`."""
    base, db, run_id, site_id = counted
    got = httpx.get(f"{base}/api/runs/{run_id}/analyses", timeout=60).json()
    avail = got["available"]
    would_run = [a for a in avail
                 if a.get("type") not in ("page", "triage")
                 and a.get("part") not in ("none", "report")
                 and a.get("state") == "not_run"]
    assert got["batch"]["count"] == len(would_run), (
        f"the batch promises {got['batch']['count']} and the button would run "
        f"{len(would_run)}")


def test_the_fixture_holds_a_row_the_batch_must_exclude(counted):
    """DISCIPLINE rule 5. If every analysis in the fixture is `not_run`, the
    two clauses above pass whatever the predicate is - which is the state the
    defect lived in for as long as it did."""
    base, db, run_id, site_id = counted
    got = httpx.get(f"{base}/api/runs/{run_id}/analyses", timeout=60).json()
    states = {a.get("state") for a in got["available"]}
    kinds = {a.get("type") for a in got["available"]}
    parts = {a.get("part") for a in got["available"]}
    assert states - {"not_run"} or kinds & {"page", "triage"} or parts & {"none", "report"}, (
        f"nothing in this fixture is excluded from the batch: {states} {kinds} {parts}")


# ---- the readers -----------------------------------------------------------

def test_the_control_that_opens_the_catalogue_counts_what_it_opens():
    """`notRunCount` excluded `triage` and nothing else, so it read 24 against
    a catalogue listing 23: the client plan writes to no part, is not in the
    drawer, and is reached from Reports."""
    cat = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    m = re.search(r"export function notRunCount[\s\S]{0,400}?\n\}", cat)
    assert m, "notRunCount not found"
    body = m.group(0)
    for clause in ('x.part !== "none"', 'x.part !== "report"', 'x.type !== "triage"'):
        assert clause in body, f"{clause} missing from notRunCount:\n{body}"
    # And no screen keeps a second filter of its own.
    anat = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    assert "notRunCount(lanes)" in anat, "anatomy still filters `available` itself"
    assert 'available.filter((x: Analysis) => x.type !== "triage")' not in anat


def test_the_catalogue_head_names_the_fourth_remainder():
    cat = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    assert "needsInput" in cat, "the head has no count for `needs_input`"
    assert "context a crawl cannot supply" in cat


def test_the_landing_names_what_the_batch_cannot_run():
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "b.needs_input" in lanes, (
        "the landing's aside does not say what the batch leaves out")
