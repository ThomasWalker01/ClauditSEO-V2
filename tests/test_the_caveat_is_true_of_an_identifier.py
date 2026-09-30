"""The honesty caveat says what the document did, not where the number came from.

CQ-194, and `QUESTIONS.md` Q-7 answered **change the caveat wording to
something true of an identifier** by the operator on 24 August 2026.

`generate.py` appends one note on either of two conditions — the brief flagged
the figure as derived (`figure_is_unverified`), or this deliverable cannot
ground the number (`ungrounded_uncaveated_lines`). The second condition asks
only whether the token appears in the measured evidence, and a brief's prose
quotes the client's own site back at them, so it fires on identifiers: measured
read-only over `data/clauditseo.db` before this guard was written, 33 of 275
stored `EXP:*` summaries are ungrounded and **13 of them are marked for an
identifier rather than a figure** — `1300 922 223` on four rows, `[505 Toorak
Rd]` / `[3142]` on two, an HTTP `200` on three, `foundingDate "2019"`,
`Apache/2.4.52` and `HTTP/1.1`.

The note those rows carried said the figure was *derived by the analyst*. Of a
number the client published on their own website that is not a caveat, it is a
false statement, printed on the one marker every true caveat in the document
depends on being believed —
`reports/out/www-acme-com-au-run-client-2026-08-22-91f9ad50.md:295` told a
reader that the client's own published phone number "was not measured".

**The remedy the operator chose is the wording, not the gate.** The alternative
— grounding a brief line against the evidence the brief itself was given — was
measured to ground 0 of the 33, because that evidence is stored nowhere:
`expert_reports` keeps the model's prose, `findings.evidence` keeps
`{confidence_stated, from_brief}`, `analyst_cache` keeps a `bundle_hash` and not
the bundle, and the crawl HTML is not persisted at all. So the gate keeps
exactly the reach it has and the mark stops claiming something it cannot know.

**Both halves are asserted, because a reword can break two things silently.**
The mark must still be there (an identifier the document did not measure is
still a value the reader should confirm), and it must still be the
`[TO CONFIRM: …]` shape `unsourced_number_lines` and `ungrounded_uncaveated_lines`
read off the rendered line — a reword that stopped matching would turn the
whole gate green against prose it used to refuse.
"""

from __future__ import annotations

import json

from clauditseo.reporting import generate as gen
from clauditseo.reporting.checks import ungrounded_uncaveated_lines
from clauditseo.reporting.render import ANALYST_FIGURE_NOTE
from tests.test_a_brief_number_is_grounded_or_caveated import _plant, _row_for
from tests.test_reporting_g7 import db_with_runs  # noqa: F401

#: The client's own published phone number, off the row the finding names.
#: An identifier the analyst did not derive and the deliverable did not
#: measure, which is the whole of the distinction this guard holds.
PUBLISHED_PHONE = "1300 922 223"


def test_an_identifier_is_marked_without_being_called_the_analysts(db_with_runs):  # noqa: F811
    """The instance, driven through `generate` rather than read off the constant.

    Red before the reword: the rendered row told the client that the phone
    number printed on their own website was "derived by the analyst".
    """
    conn, run_ids = db_with_runs
    _plant(conn, run_ids[-1], "local-signals",
           f"Published phone {PUBLISHED_PHONE} conflicts with the schema "
           f"telephone, which is not valid for the published number.")

    md = gen.generate(conn, "run", "client", [run_ids[-1]])["markdown"]
    row = _row_for(md, PUBLISHED_PHONE)

    # Non-vacuity for the assertion below, and the must-not-change direction:
    # the document still says it did not measure this.
    assert ANALYST_FIGURE_NOTE in row, (
        "the identifier row carries no caveat at all, so the assertion below "
        f"is true about nothing: {row!r}")
    assert "derived by the analyst" not in row, (
        "the client's own published phone number is printed with a note "
        f"saying the analyst derived it: {row!r}")


def test_the_note_makes_no_claim_about_where_the_number_came_from():
    """The rule, stated so a later edit cannot walk it back one word at a time.

    One note is placed on two conditions and only one of them knows anything
    about provenance (`figure_is_unverified` asks the brief; the grounding half
    asks this document's evidence). A note that names the analyst is therefore
    unprovable on half the rows it lands on. The enforceable form is that the
    mark speaks about the measurement and not about the author.
    """
    assert "analyst" not in ANALYST_FIGURE_NOTE.lower(), (
        f"{ANALYST_FIGURE_NOTE!r} attributes the number to the analyst, which "
        "the grounding condition that placed it on half these rows never "
        "established")
    assert "derived" not in ANALYST_FIGURE_NOTE.lower(), (
        f"{ANALYST_FIGURE_NOTE!r} says the number was derived, which is false "
        "of an identifier the client published")


def test_the_reworded_note_is_still_the_marker_the_gate_reads():
    """The half a reword breaks silently. `ungrounded_uncaveated_lines` skips a
    line containing `[TO CONFIRM`, and `unsourced_number_lines` accepts the same
    marker in place of a source tag. A note that stopped carrying it would make
    every ungrounded brief line pass the gate."""
    assert ANALYST_FIGURE_NOTE.startswith("[TO CONFIRM"), (
        f"{ANALYST_FIGURE_NOTE!r} is no longer the marker gate G7 reads off a "
        "rendered line")

    evidence = json.dumps({"measured": [{"composite_score": 91.9}]})
    ungrounded = f"Published phone {PUBLISHED_PHONE} is on the site."
    # The positive control: the line is refused without the note...
    assert ungrounded_uncaveated_lines(ungrounded, evidence) == [ungrounded]
    # ...and accepted with it, which is the property being protected.
    assert ungrounded_uncaveated_lines(
        f"{ungrounded} {ANALYST_FIGURE_NOTE}", evidence) == []
