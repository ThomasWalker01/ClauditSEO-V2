"""Item 234 (AI surface, change 1): a paid row may not raise its severity on
a free check that did not fire.

The AI surface prompt raises `AIS/id-page-absent` to HIGH "when
`entity-unresolvable` also fires". On twenty22 the row was HIGH with "entity-
unresolvable also fires" in its note, on a page whose free table said
`entity-unresolvable` was not assessed. The contract now refuses such a raise
at parse and at re-parse: the row keeps the registry default, the claim is
taken out, and the note says why. A raise the sweep supports stands.
"""

from __future__ import annotations

from clauditseo.analysts import contract

PAGE = "https://ais.fixture/"


def _enforced(sweep_raised, note="entity-unresolvable also fires; no /about entity page",
              measured=("AIS",), evidence="no page carries the entity; entity-unresolvable fired."):
    row = contract.Row(check="AIS/id-page-absent", dimension="AIS", check_id="id-page-absent",
                       page=PAGE, status="FAIL", severity="high",
                       evidence=evidence,
                       replacement=None, note=note, raised=True)
    parsed = contract.Parsed(status=contract.READ, rows=[row], part="ai-surface")
    contract.enforce(parsed, contract.Rules(sweep_raised=sweep_raised,
                                            sweep_measured=set(measured)))
    return parsed.rows[0]


def test_a_raise_on_a_check_that_did_not_fire_is_refused():
    row = _enforced({})
    assert row.severity == "medium" and not row.raised, (row.severity, row.raised)
    assert "also fires" not in row.note and "fired" not in row.evidence, (row.note, row.evidence)
    assert "raise refused: entity-unresolvable did not fire in this audit" in row.note, row.note


def test_a_raise_the_sweep_supports_stands():
    row = _enforced({"entity-unresolvable": {"/"}})
    assert row.severity == "high" and row.raised, (row.severity, row.raised)


def test_nothing_is_judged_where_the_dimension_was_not_measured():
    row = _enforced({}, measured=())
    assert row.severity == "high", row.severity


def test_a_raise_that_claims_nothing_is_left_alone():
    row = _enforced({}, note="the entity is named on no page the crawl reached",
                    evidence="no page carries the entity")
    assert row.severity == "high", row.severity
