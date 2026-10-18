"""A stale verdict that states the fault is dropped (screen audits round 4,
Content AC-03): two `CNT/stale` PASS-OVERRIDE rows closed the finding with
"older than the 730-day service threshold".
"""
from __future__ import annotations

from clauditseo.analysts import contract


def _row(status, evidence):
    return contract.Row(check="CNT/stale", dimension="CNT", check_id="stale", page="/a/",
                        status=status, severity="low", evidence=evidence,
                        replacement="No change", note="")


def test_a_pass_that_says_older_than_is_refuted():
    why = contract._refutes_itself(
        _row("PASS-OVERRIDE", "dateModified 2024-11-29T17:18:44+11:00, older than the "
                              "730-day service threshold"), "No change")
    assert why and "older than the threshold" in why


def test_a_pass_inside_the_threshold_stands():
    assert contract._refutes_itself(
        _row("PASS-OVERRIDE", "dateModified 2026-01-10, inside the 730-day threshold"),
        "No change") is None
    assert contract._refutes_itself(
        _row("FAIL", "dateModified 2022-01-10, older than the 730-day threshold"),
        "Update it") is None
