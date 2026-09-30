"""The three first-hand markers on `CNT/eeat`, as fields (item 136q commit 7).

Not a registration: `CNT/eeat` exists in `content-substance.md` and fires. It
carried its evidence as prose, so a reader could not tell WHICH marker was
missing without parsing the sentence. 145 asks for the three as fields.

**The engine already accepted them.** `contract.parse` has read a row's
`fields` dict into `Row.fields` since brief v11; the item reads as though the
mechanism needed building, and it did not. So this commit is the prompt
declaring the three and nothing else — additive, no new evidence class, no
change to when the row fires or to its severity.
"""

from __future__ import annotations

from pathlib import Path

NL = chr(10)

PROMPT = (Path(__file__).resolve().parents[1] / "clauditseo" / "prompts"
          / "content-substance.md")


def _parse(rows_json: str):
    from clauditseo.analysts import contract

    body = NL.join(("## Block 1", "", "```json", rows_json, "```", ""))
    return contract.parse(body, ["CNT/eeat"], ["https://x.test/blog/post"])


def test_the_three_markers_are_emitted_as_booleans():
    parsed = _parse("""{"rows": [{
        "check": "CNT/eeat", "page": "/blog/post", "status": "FAIL",
        "severity": "MEDIUM", "evidence": "no author; no date",
        "fields": {"named_author": false, "first_person_attributed": true,
                   "dated_specific": false},
        "replacement": "Add an author block and a publish date"}]}""")
    assert not parsed.dropped, parsed.dropped
    row = parsed.rows[0]
    assert row.fields == {"named_author": False,
                          "first_person_attributed": True,
                          "dated_specific": False}, row.fields
    # Additive: the two the item says must not change.
    assert row.evidence == "no author; no date"
    assert row.replacement == "Add an author block and a publish date"


def test_a_marker_is_true_only_on_evidence_the_check_already_accepts():
    """The rule has to be where the MODEL reads it, so it is asserted in the
    prompt rather than in code — nothing in the engine can tell whether a
    boolean was justified, and a test that pretended otherwise would be
    checking its own fixture."""
    src = PROMPT.read_text(encoding="utf-8")
    block = src[src.index("CNT/eeat"):src.index("An `eeat` row MUST carry") + 1400]
    for marker in ("named_author", "first_person_attributed", "dated_specific"):
        assert marker in block, marker
    assert "Each is true ONLY on evidence this check already" in block
    assert "No new evidence class" in block


def test_eeat_severity_and_firing_are_unchanged():
    """The item is explicit that this adds fields and nothing else."""
    src = PROMPT.read_text(encoding="utf-8")
    # The registered defaults line, untouched.
    assert "eeat on a service/location/YMYL page — HIGH" in src
    assert "YMYL topics (finance, health, legal): eeat is HIGH" in src
    # And the evidence the check accepts is the same list it always was.
    for accepted in ("named author with a role/credential and a",
                     "first-person experience tied to a place",
                     "cited sources with dates"):
        assert accepted in src, accepted


def test_the_row_shape_example_shows_the_fields():
    """A prompt that states a rule and shows an example without it teaches
    the example."""
    src = PROMPT.read_text(encoding="utf-8")
    assert '"fields": { "named_author": false' in src
