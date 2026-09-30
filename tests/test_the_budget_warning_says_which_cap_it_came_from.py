"""The budget warning says which cap produced it - UX-78.

`_budget_status` builds one `warning` string from either of two caps. The
token cap writes it; the USD cap overwrites it, but only when the USD
threshold is also crossed. So on an install with
`CLAUDITSEO_MONTHLY_BUDGET_TOKENS` set and no USD cap, `warning` is a sentence
about tokens - and the payload says nothing about which of the two it is.

That silence is what the tools screen pays for. `dashboard/src/tools.tsx`
appends the priced-entry clause to `warning` unconditionally, producing
"1,185,949 of 1,200,000 monthly tokens used - a floor: 14 of 48 entries
priced": a caveat about `actual_cost` attached to `quantity`, which is
recorded on every entry and is not a floor. Home and Admin do not have this,
because both attach the clause to the dollar figure itself and leave
`warning` alone.

**The fix belongs on the server, and this file is why.** The screen cannot
derive the basis: `cap_tokens` and `cap_usd` can both be set and both be
under threshold, and a client reading "which cap is configured" would answer
for a warning neither produced. Only the branch that wrote the sentence knows
which one it was. One owner, three consumers - the same division round 079
chose when it put `usd_entries` and `usd_unpriced` beside every dollar total
rather than letting each screen count.

**Pure Python on purpose.** `tests/test_unpriced_spend_is_named.py` already
holds `_budget_status` cases and imports `DIST` at module level, so
`scripts/prove_fail.py` refuses the whole file and DISCIPLINE rule 1 cannot be
answered there. The frame's rendered half is guarded in
`tests/test_the_spending_screen_frames_its_money.py`, which is browser-gated
for good reason; this file keeps the half that can be proven red where it can
be proven red.
"""

from __future__ import annotations

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


@pytest.fixture
def spent(tmp_path):
    """One month, three entries, one priced - so both caps have something to
    be crossed by, and the priced-entry frame has a real minority to state."""
    conn = connect(tmp_path / "caps.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Capped Co")
    site = repo.create_site(conn, client, "capped.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.log_cost(conn, run_id, "llm", "EXPERT:priced", "tokens", 1000,
                  actual_cost=4.00)
    runs.log_cost(conn, run_id, "llm", "EXPERT:unpriced-a", "tokens", 2000)
    runs.log_cost(conn, run_id, "llm", "EXPERT:unpriced-b", "tokens", 4000)
    yield conn
    conn.close()


class _Caps:
    def __init__(self, tokens=None, usd=None):
        self.monthly_budget_tokens = tokens
        self.monthly_budget_usd = usd


def test_a_token_cap_warning_is_labelled_as_one(spent):
    """The install UX-78 is about: a token cap and no dollar cap.

    The assertion on the sentence is not decoration - it is what stops this
    test passing against a `warning` of `None`, where a basis of anything at
    all would be trivially satisfiable.
    """
    from clauditseo.api.app import _budget_status

    status = _budget_status(spent, _Caps(tokens=7000))

    assert "monthly tokens used" in (status["warning"] or ""), (
        "the fixture did not cross the token cap, so nothing below is being "
        "tested")
    assert status["warning_basis"] == "tokens", (
        "the payload does not say which cap produced the warning, so a "
        "consumer appending a dollars-priced caveat cannot tell that this "
        "sentence counts tokens - which are recorded on every entry and are "
        "not a floor")


def test_a_dollar_cap_warning_is_labelled_as_one(spent):
    """Both caps crossed. The USD branch overwrites the sentence, so the
    basis must be overwritten with it - a label left behind by the branch
    that did not win is worse than no label."""
    from clauditseo.api.app import _budget_status

    status = _budget_status(spent, _Caps(tokens=7000, usd=4.00))

    assert "monthly budget used" in (status["warning"] or "")
    assert status["warning_basis"] == "usd"


def test_no_warning_carries_no_basis(spent):
    """The must-not-change direction. A basis standing beside a `None`
    warning is a label for a sentence that was never written, and a consumer
    keying on it would render the clause with nothing to attach it to."""
    from clauditseo.api.app import _budget_status

    status = _budget_status(spent, _Caps())

    assert status["warning"] is None
    assert status["warning_basis"] is None
