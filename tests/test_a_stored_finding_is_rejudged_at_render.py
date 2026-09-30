"""A brief finding stored before the figure flag existed is judged at render.

`record_expert_findings` stamps `figure_unverified` into each finding's
`evidence` JSON at record time, and `_expert_section` reads that stamp back.
Nothing recomputes it — so renderer 1.22.0's fix, which widened the judgement
from the capped display list to every figure the extractor flagged, reaches no
run already in the operator's database. Measured read-only against
`data/clauditseo.db` for report 077 and re-measured for report 080: of **275**
stored `EXP:*` findings, **188 carry no `figure_unverified` key at all**. Those
rows render into a client document today with `source: model judgement` beside
them and no `[TO CONFIRM: …]`, and seven of them quote a figure their own
brief flagged as derived.

What these guards pin is a **read-time fallback**, and its three edges:

- **absent key → re-derive**, from that brief's own stored `figures_to_verify`;
- **`false` → trusted, never re-judged.** A stamp is a judgement made with the
  brief's uncapped figure list in hand. The stored list is the *capped* one, so
  re-judging a `false` could only ever narrow a decision made at full width —
  it cannot recover what the cap dropped, and it would overwrite a correct
  answer with a worse one;
- **`true` → still marks**, unchanged.

Nothing here rewrites `findings.evidence`. The stored row is the operator's
history and a read-time question does not get to edit it; re-stamping would
also destroy the only evidence of which rows predate the field.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.reporting.generate import _expert_section, tool_runs_for
from clauditseo.reporting.render import ANALYST_FIGURE_NOTE

#: Five digits, no separators, standing alone in the prose. Measured
#: constraints, not taste: `extract_numbers` treats 1-10, HTTP status codes,
#: dates, clock pairs and dotted versions as vocabulary rather than figures
#: (`tests/test_figure_cap_declares_what_it_withheld.py` records why), and
#: since round 081 a digit run touching a letter is not a number at all. A
#: smaller or an embedded number would be dropped for a reason that has
#: nothing to do with the stamp this file is about.
FLAGGED = "41537"

#: A second five-digit number the brief never flagged, so the control quotes a
#: figure that is genuinely not in `figures_to_verify` rather than one the
#: extractor happened to discard.
UNFLAGGED = "27604"

#: CQ-173. A number that is only the second half of a standards reference.
#: The brief's own extractor flagged `164` out of `E.164` - `is_identifier_fragment`
#: lets it through, because the character before the digits is a full stop and
#: not a letter - so the value really is in `figures_to_verify` on disk. The
#: summary below quotes the reference and no derived figure at all, and until
#: renderer 1.24.0 the deliverable caveated it on the strength of that alone.
#: Measured against `data/clauditseo.db`: `local-signals/nap-inconsistent` is
#: the row it happened to, and it is one of the seven the read-time
#: FALLBACK marks - not one of nine, which is that seven plus the two
#: rows carrying a stored `figure_unverified: true` that the fallback
#: never decides. CQ-182.
STRUCTURAL = "164"

TOOL = "sitemap-coverage"

REJUDGED = "rejudged-absent-stamp"
STRUCTURE_ONLY = "quotes-only-a-standard"
CONTROL = "no-flagged-figure"
TRUSTED_FALSE = "stamped-false"
STAMPED_TRUE = "stamped-true"

FINDINGS = [
    {"code": REJUDGED, "severity": "high",
     "summary": f"Only {FLAGGED} of the indexable pages appear in the sitemap."},
    {"code": CONTROL, "severity": "medium",
     "summary": f"The sitemap omits {UNFLAGGED} indexable pages."},
    {"code": TRUSTED_FALSE, "severity": "medium",
     "summary": f"A crawl of {FLAGGED} pages was completed."},
    {"code": STAMPED_TRUE, "severity": "low",
     "summary": "The sitemap lastmod dates do not track publication."},
    {"code": STRUCTURE_ONLY, "severity": "medium",
     "summary": "Every listing gives the `tel` value as an E.164 string."},
]


@pytest.fixture
def rendered(tmp_path):
    """One run, one brief, four stored findings, then the section they render.

    The findings are written through `record_expert_findings` and *then* their
    stamps are edited, rather than inserted by hand: everything else in the
    evidence JSON — `confidence_stated`, `from_brief` — has to be the shape the
    application really writes, or the fixture is asserting about a row that
    only exists in this file. Editing the stamp afterwards is what reproduces
    the population the finding is about: a row recorded before the field
    existed carries no key, and there is no other way to make one.
    """
    conn = connect(tmp_path / "rejudge.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Rejudge Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")

    figures = [{"value": FLAGGED,
                "context": f"roughly {FLAGGED} pages are absent from the sitemap"},
               {"value": STRUCTURAL,
                "context": "the `tel` value is an E.164 string"}]
    runs.store_expert_report(conn, run_id, TOOL, {
        "model": "stub-model",
        "report": "prose the deliverable does not print",
        "findings": FINDINGS,
        "figures_to_verify": figures,
    })
    runs.record_expert_findings(conn, run_id, TOOL, "stub-model", FINDINGS,
                                figures=figures)

    # The stamps, set to the four states the fallback has to tell apart. The
    # key is *deleted* for the first two — not set to None — because that is
    # what a row written before the field existed looks like, and `.get()`
    # cannot tell the two apart while `in` can.
    stamps = {REJUDGED: None, CONTROL: None, STRUCTURE_ONLY: None,
              TRUSTED_FALSE: False, STAMPED_TRUE: True}
    with conn:
        for code, want in stamps.items():
            row = conn.execute(
                "SELECT evidence FROM findings WHERE run_id=? AND check_id=?",
                (run_id, code)).fetchone()
            ev = json.loads(row["evidence"] or "{}")
            if want is None:
                ev.pop("figure_unverified", None)
            else:
                ev["figure_unverified"] = want
            conn.execute(
                "UPDATE findings SET evidence=? WHERE run_id=? AND check_id=?",
                (json.dumps(ev), run_id, code))

    try:
        section, _ = _expert_section(conn, tool_runs_for(conn, site_id), site_id, "client")
        rows = {}
        for line in section.splitlines():
            for code in stamps:
                if f"`{code}`" in line:
                    rows[code] = line
        yield rows
    finally:
        conn.close()


def _line(rows: dict[str, str], code: str) -> str:
    assert code in rows, (
        f"`{code}` never reached the client document, so this file is not "
        f"asserting about the rendered row it names. Got: {sorted(rows)}")
    return rows[code]


def test_a_finding_stored_without_the_stamp_is_judged_when_it_renders(rendered):
    """The finding this whole file exists for.

    188 stored rows carry no stamp. This one quotes `41537`, which its own
    brief flagged as derived and stored in `figures_to_verify` — and it prints
    into a client's document with a provenance tag that is true and no caveat,
    which reads as though the number had been audited.
    """
    line = _line(rendered, REJUDGED)
    assert ANALYST_FIGURE_NOTE in line, (
        f"{FLAGGED} was flagged as derived by the brief that produced this "
        f"finding, and printed to a client as though it had been checked, "
        f"because the row was stored before the stamp existed. Row: {line}")


def test_an_unstamped_finding_quoting_no_flagged_figure_is_left_alone(rendered):
    """The control, so the fallback cannot be a wall that caveats everything.

    A read-time rule that marks every unstamped row would pass the test above
    and destroy the meaning of the marker — 188 rows would arrive at the client
    caveated, and a caveat that is always present carries no information.
    """
    line = _line(rendered, CONTROL)
    assert ANALYST_FIGURE_NOTE not in line, (
        f"{UNFLAGGED} is not in this brief's `figures_to_verify`, so nothing "
        f"declared it derived, yet the row was caveated. Row: {line}")


def test_a_stamp_of_false_is_trusted_rather_than_re_judged(rendered):
    """A must-not-change direction, and the reason the fallback keys on
    absence rather than on falsiness.

    This summary quotes `41537`, so a rule that re-judged every row `.get()`
    reports as falsy would mark it. The stamp was written with the brief's
    **uncapped** figure list in hand; the stored list is the capped one. So
    re-deriving here can only ever replace a judgement made at full width with
    one made at less, which is CQ-08's defect pointed the other way.
    """
    line = _line(rendered, TRUSTED_FALSE)
    assert ANALYST_FIGURE_NOTE not in line, (
        "a stored `figure_unverified: false` was overwritten by a re-derivation "
        f"made against the capped list, which is narrower than the judgement it "
        f"replaced. Row: {line}")


def test_a_stamp_of_true_still_marks(rendered):
    """The other must-not-change direction: the path that already worked.

    This summary quotes no figure at all, so a fallback that re-derived
    unconditionally would *unmark* it — a row the analyst declared derived,
    silently promoted to measured on its way to a client.
    """
    line = _line(rendered, STAMPED_TRUE)
    assert ANALYST_FIGURE_NOTE in line, (
        f"a stored `figure_unverified: true` stopped reaching the document. "
        f"Row: {line}")



def test_a_finding_quoting_only_a_standards_reference_is_not_caveated(rendered):
    """CQ-173, at the one place a client meets it.

    `_declares_a_figure` asked whether any number in the summary is one the
    brief flagged, and read the summary with no rule about what a number in
    prose IS - while the extractor that produced the flagged list has had one
    since `mask_vocabulary` was written. So `E.164` in a summary matched `164`
    in the stored list, and renderer 1.23.0 printed
    `[TO CONFIRM: figure derived by the analyst, not measured]` beside
    `local-signals/nap-inconsistent` in a client document generated on
    22 August 2026. That summary quotes two phone numbers off the site and no
    derived figure.

    A caveat that fires without cause costs more than one that fails to fire:
    it teaches the reader to discount the mark, and the mark is what the
    product's provenance invariant is sold on. Measured read-only over the
    stored corpus, reading the summary through the same vocabulary moves the
    set the FALLBACK marks from 7 to 6, and the one it drops is this row. The
    9 and 8 this docstring used to give are the totals including the two
    stamped-true rows, which the fallback does not decide - one measurement,
    two populations, and CQ-182 is that three registers gave both under one
    name.
    """
    line = _line(rendered, STRUCTURE_ONLY)
    assert ANALYST_FIGURE_NOTE not in line, (
        f"the summary quotes `E.164` and no derived figure, yet the client's "
        f"document warns that a number in it is unverified. Row: {line}")


def test_the_structural_case_still_reaches_the_document_at_all(rendered):
    """Non-vacuity, because the assertion above is an absence.

    A row that stopped rendering would satisfy it for the wrong reason, and
    `_line` already fails loudly on that - this states it as its own case so
    the reason is in the suite output rather than in a helper.
    """
    line = _line(rendered, STRUCTURE_ONLY)
    assert "E.164" in line, (
        f"the row rendered without the reference the case is about: {line}")
