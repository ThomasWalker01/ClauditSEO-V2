"""CQ-09: the grounding half of gate G7 must read the specialist briefs.

`generate` builds `narrative` from `render_run_report`, whose `_analyst_section`
excludes `EXP:*` by construction, and then *appends* `_expert_section` to
`markdown` afterwards. So the half of the gate that grounds numbers against
measured evidence has never once looked at the model-written prose most likely
to contain a fabricated one — the specialist briefs. The other half,
`unsourced_number_lines`, does read the section and passes it trivially: every
brief row carries a `provenance_tag`, which is a true statement about where the
prose came from and no statement at all about whether the number in it was
measured.

Audit 013 reproduced the same hole on the analyst section end to end, with a
planted finding reading "Organic sessions fell 47318 percent" that printed into
a client document carrying `confidence: medium`. That half was closed by
narrowing `_evidence_text`. This file is the same reproduction pointed at the
section the fix did not reach.

**What the remedy is, and why it is a caveat rather than a refusal.** A number
in brief prose that the deliverable's measured evidence cannot ground is
exactly what `ANALYST_FIGURE_NOTE` says it is — not measured by this report.
(It said *derived by the analyst* until renderer 1.30.0, which is a claim this
half never establishes, because a brief's prose quotes the client's own site
back at them: CQ-194, guarded by
`tests/test_the_caveat_is_true_of_an_identifier.py`.) The product already
prints that note beside a figure the brief's own extractor flagged; CQ-09's remedy is that it also prints it when the
deliverable itself cannot ground the number, which is a question the brief's
stored figure list cannot answer because it was computed against the brief's
crawl evidence rather than against the document's. Measured read-only over
`data/clauditseo.db` before this file was written: 31 of 275 stored `EXP:*`
findings quote a number the deliverable's evidence does not contain and carry
no caveat today.

The gate keeps its teeth. `ungrounded_uncaveated_lines` reads the *rendered*
prose and fails on an ungrounded number whose line carries no marker, so a
renderer that stops applying the note — the class UX-80 closed by deleting a
`title` no guard could see — is a red suite rather than a silent regression in
a client's document.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.persistence import runs
from clauditseo.reporting import generate as gen
from clauditseo.reporting.checks import (ReportCheckError,
                                         ungrounded_uncaveated_lines)
from clauditseo.reporting.render import ANALYST_FIGURE_NOTE
from tests.test_reporting_g7 import db_with_runs  # noqa: F401

FABRICATED = "47318"


def _plant(conn, run_id, tool, summary, figures=None, fid="exp-plant"):
    """A stored brief and one `EXP:*` finding under it, as the product stores
    them. Inserted rather than generated: the point is a row that reaches
    `_expert_section`, and `record_expert_findings`' own stamping is a
    different question — `figure_is_unverified` owns it, and the declared-figure
    case below is what asserts the two conditions do not collide."""
    runs.store_expert_report(
        conn, run_id, tool,
        {"model": "m-1", "report": "## SUMMARY\nSee index.",
         "findings": [{"severity": "high", "summary": summary}],
         "figures_to_verify": figures or []})
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
        " source, model_id, confidence, summary, affected_urls, evidence,"
        " recommendation, fingerprint, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fid, run_id, f"EXP:{tool}", "brief-note", "high",
         "model-judgement", "m-1", "medium", summary, "[]",
         json.dumps({"confidence_stated": True}), "", f"fp-{fid}",
         "2026-08-23T00:00:00Z"))
    conn.commit()


def _row_for(markdown: str, needle: str) -> str:
    rows = [ln for ln in markdown.splitlines() if needle in ln]
    assert rows, f"no rendered line quotes {needle!r}"
    return rows[0]


def test_a_fabricated_brief_figure_cannot_print_as_measured(db_with_runs):  # noqa: F811
    """Audit 013's reproduction, moved to the section its fix did not reach.

    Red before this lever: the row printed the invented figure beside a true
    `source: model judgement` tag and no caveat, which reads to a client as a
    number the tool checked.
    """
    conn, run_ids = db_with_runs
    _plant(conn, run_ids[-1], "crawl",
           f"Organic sessions fell {FABRICATED} percent after the template change.")

    md = gen.generate(conn, "run", "client", [run_ids[-1]])["markdown"]
    row = _row_for(md, FABRICATED)
    assert ANALYST_FIGURE_NOTE in row, (
        "a number the deliverable's evidence does not contain printed with no "
        f"caveat: {row!r}")


def test_the_gate_refuses_an_ungrounded_brief_line_with_no_caveat():
    """The check itself, at its own entry point, so it can fail on prose the
    renderer never produced — DISCIPLINE rule 5."""
    evidence = json.dumps({"measured": [{"composite_score": 91.9}]})

    assert ungrounded_uncaveated_lines(
        f"Organic sessions fell {FABRICATED} percent.", evidence) == [
        f"Organic sessions fell {FABRICATED} percent."]
    # The caveat is what makes the line honest, and it is read from the line
    # rather than from whoever decided to put it there.
    assert ungrounded_uncaveated_lines(
        f"Organic sessions fell {FABRICATED} percent. {ANALYST_FIGURE_NOTE}",
        evidence) == []
    # Grounded in the measured evidence: no caveat needed, none demanded.
    assert ungrounded_uncaveated_lines("Composite is 91.9.", evidence) == []


def test_assert_report_honest_reads_the_brief_section():
    """The gate's entry point — the one the product actually calls — must be
    able to refuse a brief section."""
    evidence = json.dumps({"measured": [{"composite_score": 91.9}]})

    with pytest.raises(ReportCheckError) as raised:
        gen.assert_report_honest(
            "Composite: 91.9 (source: engine, confidence: high)", "", evidence,
            brief_narrative=f"Organic sessions fell {FABRICATED} percent.")
    assert FABRICATED in str(raised.value), (
        f"the refusal must name what it refused; got {raised.value}")

    # Same line, caveated: accepted.
    gen.assert_report_honest(
        "Composite: 91.9 (source: engine, confidence: high)", "", evidence,
        brief_narrative=(f"Organic sessions fell {FABRICATED} percent. "
                         f"{ANALYST_FIGURE_NOTE}"))


def test_a_grounded_brief_row_gains_no_caveat(db_with_runs):  # noqa: F811
    """Must-not-change. 244 of the 275 stored brief findings are this case; a
    lever that caveated them would make the marker mean nothing."""
    conn, run_ids = db_with_runs
    run = runs.get_run(conn, run_ids[-1])
    grounded = str(run["composite_score"])
    _plant(conn, run_ids[-1], "crawl",
           f"The composite of {grounded} is what the audit recorded.")

    md = gen.generate(conn, "run", "client", [run_ids[-1]])["markdown"]
    row = _row_for(md, "is what the audit recorded")
    assert ANALYST_FIGURE_NOTE not in row, (
        f"a number the evidence does contain was caveated anyway: {row!r}")


def test_a_declared_figure_still_carries_exactly_one_note(db_with_runs):  # noqa: F811
    """Must-not-change, and the one direction two independent conditions can
    break: `figure_is_unverified` and the new grounding check both fire on a
    declared figure that is also ungrounded, and the row must not say it
    twice."""
    conn, run_ids = db_with_runs
    _plant(conn, run_ids[-1], "crawl",
           f"Lost revenue was {FABRICATED} dollars.",
           figures=[{"value": FABRICATED,
                     "context": f"Lost revenue was {FABRICATED} dollars."}])

    md = gen.generate(conn, "run", "client", [run_ids[-1]])["markdown"]
    row = _row_for(md, FABRICATED)
    assert row.count(ANALYST_FIGURE_NOTE) == 1, (
        f"the caveat is printed {row.count(ANALYST_FIGURE_NOTE)} times: {row!r}")


def test_the_brief_section_narrative_reaches_the_gate(db_with_runs):  # noqa: F811
    """The structural half of CQ-09, asserted where it can be wrong.

    `_expert_section` returns its markdown and the model prose inside it, and
    `generate` hands the second to `assert_report_honest`. Asserting the return
    shape alone would be rule 4's defect — a signature is not evidence the
    caller uses it — so this drives `generate` and reads what the gate was
    given.
    """
    conn, run_ids = db_with_runs
    _plant(conn, run_ids[-1], "crawl",
           f"Organic sessions fell {FABRICATED} percent after the change.")

    seen = {}
    real = gen.assert_report_honest

    def spy(markdown, narrative, evidence_text, brief_narrative=""):
        seen["brief"] = brief_narrative
        return real(markdown, narrative, evidence_text,
                    brief_narrative=brief_narrative)

    gen.assert_report_honest = spy
    try:
        gen.generate(conn, "run", "client", [run_ids[-1]])
    finally:
        gen.assert_report_honest = real

    assert FABRICATED in seen.get("brief", ""), (
        "the gate was handed a brief narrative that does not contain the "
        f"brief's own prose: {seen.get('brief')!r}")
