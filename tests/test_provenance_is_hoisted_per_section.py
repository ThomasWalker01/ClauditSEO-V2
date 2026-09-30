"""Q-57: a model-written section states its provenance once, under the
heading, not on every line.

The client plan put `(source: model judgement (claude-sonnet-5), confidence:
not stated by the model)` on roughly thirty consecutive lines, each tag
longer than the line it annotated; a brief's findings table carried the same
tag in every row's last cell. The invariant is right — every number's
provenance stays determinable from the document — and applying it per line to
flowing prose is what produced the noise. So the tag is hoisted to one line
under the heading, the per-line copies are dropped for the lines that share
it, and a line whose provenance differs still carries its own.

Two things are held here, because the hoist is a real change to the one gate
the provenance invariant rests on (`QUESTIONS.md` Q-57 names the cost):

  - `unsourced_number_lines` reads the hoisted line as sourcing the block
    beneath it, and that scope closes at the next H1/H2 heading — so a covered
    span is exactly one model-written block and an untagged number in the next
    section still fails.
  - a section with one line of differing provenance keeps that line's tag and
    drops the rest, so the outlier is the one thing the reader's eye is drawn
    to.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.reporting.checks import unsourced_number_lines
from clauditseo.reporting.render import section_provenance


# --- the gate learns a section scope, and the scope has an edge -------------

def test_a_hoisted_tag_sources_the_lines_beneath_it():
    md = "\n".join([
        section_provenance("model judgement (claude-sonnet-5)",
                           "not stated by the model", scope="in this plan"),
        "",
        "The largest cluster is 14 rows and leads the roadmap.",
        "22 indexable pages are absent from the sitemap.",
    ])
    # Neither roadmap line carries a tag of its own; the hoisted line sources
    # them both.
    assert unsourced_number_lines(md) == []


def test_the_scope_closes_at_the_next_major_heading():
    """The hoist covers its own block, not the document. A number in the next
    H2 section, with no tag, still fails — otherwise the hoist would be a hole
    the width of the report."""
    md = "\n".join([
        section_provenance("model judgement (x)", "not stated by the model"),
        "22 indexable pages are absent from the sitemap.",
        "## Overall score",
        "Composite score: 91.9 out of 100.",
    ])
    flagged = unsourced_number_lines(md)
    assert any("91.9" in f for f in flagged), flagged
    assert not any("22 indexable" in f for f in flagged), flagged


def test_an_h3_subheading_does_not_close_the_scope():
    """The plan's own headings are H3, so they must not end the coverage the
    plan opened — only the report's H1/H2 sections do."""
    md = "\n".join([
        section_provenance("model judgement (x)", "not stated by the model",
                           scope="in this plan"),
        "### Roadmap",
        "The first cluster closes 14 rows.",
    ])
    assert unsourced_number_lines(md) == []


def test_an_untagged_number_with_no_hoist_still_fails():
    """The unchanged half: without a hoisted line above it, a bare number is
    still refused."""
    assert unsourced_number_lines("The largest cluster is 14 rows.") == \
        ["The largest cluster is 14 rows."]


# --- the brief table: hoisted when uniform, per-line where it differs -------

def _row(check, summary, model="m-1", confidence="medium", stated=False):
    return {"severity": "high", "check_id": check, "summary": summary,
            "affected_urls": "[]", "model_id": model, "confidence": confidence,
            "evidence": json.dumps({"figure_unverified": False,
                                    "confidence_stated": stated})}


def _render(rows):
    from clauditseo.reporting.generate import _brief_table
    lines: list[str] = []
    narrative: list[str] = []
    _brief_table(lines, narrative, rows, {"model": "m-1"}, None,
                 evidence_text=None)
    return "\n".join(lines)


def test_a_uniform_group_drops_the_provenance_column():
    """Every row is model judgement at one model with no stated confidence, so
    the tag is stated once and the column is gone."""
    md = _render([_row("sitemap-coverage", "22 pages are absent."),
                  _row("orphan-pages", "9 pages have no inbound link.")])
    prov = [ln for ln in md.splitlines()
            if ln.strip().startswith("_Provenance note")]
    assert len(prov) == 1, md
    assert "source: model judgement (m-1)" in prov[0]
    assert "confidence: not stated by the model" in prov[0]
    # No Provenance column, and no row repeats the tag.
    assert "| Provenance |" not in md
    assert md.count("source:") == 1, "the tag is stated once, not per row"
    # Still sourced, so the gate passes.
    assert unsourced_number_lines(md) == []


def test_a_mixed_group_keeps_only_the_differing_row_tagged():
    """One row states its confidence where the others did not: the section tag
    is the common provenance, the outlier keeps its own tag, the rest have a
    blank cell."""
    rows = [_row("sitemap-coverage", "22 pages are absent."),
            _row("orphan-pages", "9 pages have no inbound link."),
            _row("thin-content", "3 pages are thin.",
                 confidence="high", stated=True)]
    md = _render(rows)
    prov = [ln for ln in md.splitlines()
            if ln.strip().startswith("_Provenance note")]
    assert len(prov) == 1 and "not stated by the model" in prov[0], md
    # The column is present because the group is mixed.
    assert "| Provenance |" in md
    # The two matching rows carry no tag; the outlier does.
    outlier = [ln for ln in md.splitlines() if "thin-content" in ln][0]
    assert "source: model judgement (m-1), confidence: high" in outlier
    for matching in ("sitemap-coverage", "orphan-pages"):
        row = [ln for ln in md.splitlines() if matching in ln][0]
        assert "source:" not in row, row
    assert unsourced_number_lines(md) == []
