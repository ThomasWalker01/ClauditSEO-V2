"""A run that read one page does not print its composite as the site's score.

Audit finding F2, 2026-09-18, and the highest-consequence of that round: 72.77
with the word "fair" is what reaches a client conversation, and it was the
composite of one page of fifty-three.

Measured on the live server before the fix, run `991401ab` (`scan_scope='page'`,
1 page crawled of 53):

    every Client tab's h1        Audit T1 finished 12 hours ago and scored 72.77.
    #/sites/<id>/reports         (-)72.8  + "out of 100, fair"
    ?tab=all&view=audits         page scan            <- the rule, applied
    ?tab=all&view=audits trend   No audit has produced a score yet

So one screen already had it right and two did not, and the Record and the
Reports table disagreed about the same run in the same session.

The cause was not a missing gate on the screen. `RunScore` has always held the
branch; `/api/sites/{id}/reports` never sent a scope for it to gate on - neither
on its `runs` list nor on its per-analysis rows - while `_run_dict` has stamped
`effective_scope` on every other run payload since brief v6 step V2. A screen
cannot apply a rule about data it was not given, which is why the guards below
are on the payload as much as on the markup.
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


# ---- source: no call site may omit the scope -------------------------------

def _calls(tag: str) -> list[tuple[str, int, str]]:
    """Every call of `<tag …/>` in the dashboard, as (file, line, text).

    Cut at the self-closing `/>`, not at the first `>`: these calls are
    multi-line and their props hold arrow functions, so a lazy `…>` ends the
    match inside `(r) =>` and reads every call as propless - which is how the
    first version of this guard reported `pane_audit.tsx`, the one call site
    that was right all along, as missing the scope.
    """
    out = []
    for path in sorted(SRC.glob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"<" + tag + r"\b", text):
            window = text[m.start(): m.start() + 500]
            end = window.find("/>")
            out.append((path.name, text[:m.start()].count("\n") + 1,
                        re.sub(r"\s+", " ", window[:end + 2] if end > 0 else window)))
    return out


def test_the_tree_holds_run_score_calls_for_this_to_check():
    """DISCIPLINE rule 5: three call sites existed when this was written -
    `pane_audit.tsx` (the one that was right), and two in `reports.tsx`."""
    calls = _calls("RunScore")
    assert len(calls) >= 3, calls


def test_every_run_score_is_told_what_the_run_read():
    """`RunScore`'s narrow-scan branch cannot fire without `scope`, and a call
    that omits it prints a page scan's composite as a score."""
    bad = [f"{f}:{n}: {t[:110]}" for f, n, t in _calls("RunScore")
           if "scope=" not in t]
    assert not bad, "a RunScore that is not told the run's scope:\n" + "\n".join(bad)


def test_every_narrow_run_note_is_told_what_the_runs_read():
    """The caption that defines "page scan" is suppressed unless the rows
    carry a scope, so the table printed the word with nothing defining it."""
    calls = _calls("NarrowRunNote")
    assert len(calls) >= 3, calls
    bad = [f"{f}:{n}: {t[:110]}" for f, n, t in calls if "scope" not in t]
    assert not bad, "a NarrowRunNote fed rows with no scope:\n" + "\n".join(bad)


def test_the_headline_says_what_a_narrow_score_is_over():
    """The h1 prints the number rather than withholding it - there is room in
    a sentence - so it has to say what the number is over."""
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "scoreExtent(" in lanes, "the headline does not qualify a narrow score"
    api = (SRC / "api.ts").read_text(encoding="utf-8")
    assert "export const scoreExtent" in api
    # One spelling: the headline and the Reports card both read it.
    assert "scoreExtent(" in (SRC / "reports.tsx").read_text(encoding="utf-8")


# ---- the payload has to carry it -------------------------------------------

@pytest.fixture(scope="module")
def narrow():
    """A site whose only completed audit read a single page."""
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("narrowscore")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Narrow"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "narrowscore.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T1")
        runs.complete_run(conn, run_id, _run(_Hub()))
        # What makes it narrow, and the one field the screens gate on.
        conn.execute("UPDATE audit_runs SET scan_scope='page', composite_score=72.77"
                     " WHERE id=?", (run_id,))
        conn.commit()
        conn.close()
        yield base, db, run_id, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_reports_payload_says_what_each_run_read(narrow):
    base, db, run_id, site_id = narrow
    got = httpx.get(f"{base}/api/sites/{site_id}/reports", timeout=60).json()
    rows = got["runs"]
    assert rows, got
    for r in rows:
        assert "effective_scope" in r, (
            f"a run row with no scope for RunScore to gate on: {r}")
        assert "site_reading" in r, r
    mine = next(r for r in rows if r["id"] == run_id)
    assert mine["effective_scope"] == "page", mine
    assert mine["site_reading"] is False, mine
    assert mine["score"] == 72.77, mine


def test_the_store_agrees_that_this_run_is_not_the_site(narrow):
    """The fixture's premise, asserted so a green run cannot mean the run
    stopped being narrow."""
    base, db, run_id, site_id = narrow
    conn = connect(db)
    try:
        row = conn.execute("SELECT * FROM audit_runs WHERE id=?", (run_id,)).fetchone()
        assert runs.scope_of(row) == "page"
        assert runs.reads_site(row) is False
    finally:
        conn.close()
