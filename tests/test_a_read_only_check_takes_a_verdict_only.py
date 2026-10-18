"""A read-only check takes a verdict only, and a refusal is a hold (item 269,
row 7).

The Content prompts mark free checks "(free, read only)": the analysis may set
the automatic checks' verdict aside and raise nothing of its own. Nothing
enforced it, so two `CNT/stale` rows dated inside the threshold they cited
stood as faults; and a `CNT/gap` card carried "not_assessable: ..." as a
copyable replacement.
"""

from __future__ import annotations

from clauditseo import briefs
from clauditseo.analysts import contract


def test_the_prompts_read_only_checks_are_read():
    assert "CNT/stale" in briefs.read_only_checks("content-substance")
    assert "CNT/title-overlap" in briefs.read_only_checks("content-cannibalisation")
    assert briefs.read_only_checks("no-such-tool") == frozenset()


def _parsed(rows):
    return contract.Parsed(status=contract.READ, rows=rows, dropped=[], assumptions=[],
                           not_assessable=[], block=True, part="content", strategy=None)


def _row(check, status="FAIL", rep="Update the date"):
    return contract.Row(check=check, dimension="CNT", check_id=check.split("/")[1],
                        page="/a", status=status, severity="medium", evidence="e",
                        replacement=rep, note="")


def test_enforce_keeps_verdicts_and_holds_refusals():
    rules = contract.Rules(read_only=frozenset({"CNT/stale"}))
    parsed = contract.enforce(_parsed([
        _row("CNT/stale"), _row("CNT/stale", status="PASS-OVERRIDE", rep="No change"),
        _row("CNT/gap", rep="not_assessable: a location page needs a named place")]), rules)
    assert [r.status for r in parsed.rows] == ["PASS-OVERRIDE"], parsed.rows
    assert any("read only" in str(d.get("reason")) for d in parsed.dropped), parsed.dropped
    assert parsed.not_assessable[0]["needs"] == "a location page needs a named place"
