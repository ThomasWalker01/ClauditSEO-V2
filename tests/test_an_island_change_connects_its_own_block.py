"""An island row's change connects the block the row is about.

Screen audits round 4, Structured data AC-07 (High): two cards about the
Person block on /web-design1/ and /website-seo/ proposed
`{"@id":".../#webpage","about":{"@id":".../#organization"}}`, which leaves the
Person adrift, under "automatic checks and analysis agree".
"""
from __future__ import annotations

from clauditseo.analysts import contract


def _row(block, replacement):
    return contract.Row(check="ONP/schema-island", dimension="ONP", check_id="schema-island",
                        page="https://gate-six.test/x/", status="WARN", severity="medium",
                        evidence="Person block sits adrift", replacement=replacement, note="",
                        block=block)


def test_a_change_to_another_node_is_not_kept():
    why = contract._island_change_astray(_row(
        "Person#1", '{"@id":"https://gate-six.test/x/#webpage","about":{"@id":"https://gate-six.test/#organization"}}'))
    assert why and "not the Person block" in why


def test_a_change_that_names_the_block_stands():
    assert contract._island_change_astray(_row(
        "Person#1", '{"@id":"https://gate-six.test/x/#webpage","author":{"@id":"https://gate-six.test/#person"}}')) is None
    assert contract._island_change_astray(_row(None, "anything")) is None
