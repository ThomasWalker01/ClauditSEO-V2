"""The home page's duplicate Organization block has a card whose change
removes it.

Screen audits round 3, Structured data US-01 (High): on twenty22's `/` the
one certain, free fault - a second Organization block for one @id - had no
card that removes it. The sweep's `schema-redundant-block` row was folded
into the analysis card "Listing in the wrong place", whose Replace-with adds
`subjectOf`, because that row said it also resolved the duplicate; and the
`schema-duplicate-id` card's Replace-with was the validator's fallback for a
type short of properties: "Add the missing properties, or remove the type".

Three changes: the duplicate-id issue carries its own advice; the redundant
block names the writer where every block has one; and a removal check is
closed by another card only when that card's change removes or merges.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.modules import onp
from clauditseo.schema_rules import audit_entities, parse_blocks

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"


def test_a_duplicate_id_says_keep_one_node():
    blocks = ['{"@context":"https://schema.org","@type":"Organization",'
              '"@id":"https://gate-six.test/#organization","name":"Gate Six"}'] * 2
    entities, _ = parse_blocks(blocks)
    dup = [i for i in audit_entities(entities) if i["kind"] == "duplicate-id"]
    assert dup, "no duplicate-id issue for two nodes on one @id"
    advice = dup[0].get("instead") or ""
    assert advice.startswith("Keep one node for https://gate-six.test/#organization")
    assert "remove the second block" in advice
    assert "Add the missing properties" not in advice


def test_a_redundant_block_says_remove_and_names_its_writer():
    src = inspect.getsource(onp)
    start = src.index('raise_(check_id="schema-redundant-block"')
    raise_src = src[start:src.index("expected = SCHEMA_FOR_TYPE", start)]
    assert 'f"Remove the second {key.split(\'|\')[0]} block' in raise_src
    assert "every one here is written by" in raise_src
    assert "Keep one block per subject; a plugin" not in raise_src


def test_a_removal_is_closed_only_by_a_change_that_removes():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert 'const REMOVAL_CHECKS = new Set(["schema-redundant-block", "schema-duplicate-id"]);' in page
    assert r"/\b(remove|delete|drop|merge)\b/i.test(f.replacement" in page
    closed = page[page.index("const removes = "):page.index("const shownFixes")]
    assert "!REMOVAL_CHECKS.has(" in closed and "|| removes(f)" in closed
    assert "\x08" not in page


def test_a_card_with_no_markup_says_the_change_rather_than_an_empty_box():
    # On twenty22 both duplicate cards drew "Replace with" over an empty box.
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    body = page[page.index("function SchemaFixBody("):]
    body = body[:body.index("\n}\n")]
    assert "fix.replacement?.trim() ? (" in body
    assert '<p className="fix-lbl muted">Do this</p>' in body
    assert "{fix.recommendation ||" in body
    assert ".schema-advice {" in (SRC / "styles.css").read_text(encoding="utf-8")
