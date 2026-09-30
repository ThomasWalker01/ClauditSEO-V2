"""The anchor is the key the backlog is filed on, so the key gets a guard.

Round 044, WF-44 and WF-43 — the report pairs them as "the two halves of an
unverifiable backlog", and they are two uses of one thing:

  WF-44 — an anchor is the address a fix is sent to. Five in the carried set
          did not resolve, the oldest for fifteen reports, and one was
          re-asserted as "re-read at `clauditseo/provenance.py:44,338-350`" —
          a range that has never existed in a 157-line file.

  WF-43 — an anchor is also the key that ages a finding. The ten-round
          disposition gate had not run for four rounds and four findings aged
          20-33 reports had never entered `audits/DISPOSITIONS.md` at all.

Round 039's fix for the same defect class (WF-39) was an instruction: tell the
auditor to run `wc -l` before writing an anchor. `test_loop_instructions.py`
still asserts that instruction is present, and it is — it was present for all
fifteen rounds the worst anchor survived. An instruction nobody can watch fail
is DISCIPLINE rule 4's subject exactly, which is why this round's answer is a
checker rather than another sentence.

The two halves land differently on purpose. `undispositioned` is a pytest
below, because its remedy is a row in a register and a round may add one.
Anchor *resolution* is not, and `test_loop_instructions.py` says why
`audits/**` is absent from `REGISTER_FILES`: a report is an untouched record
and a round may not edit one, so a test firing on a committed report's own
content would be unsatisfiable. That check runs from `/audit-fix` step 2 the
way `scripts/reconcile_findings.py` does; what is guarded here is that the
checker can see a bad anchor when there is one.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AUDITS = ROOT / "audits"
sys.path.insert(0, str(ROOT / "scripts"))

import check_anchors as ca  # noqa: E402
from tests.private_register import needs_register


# --------------------------------------------------------------------------
# WF-44 — the resolver, watched failing against files built to fail it
# --------------------------------------------------------------------------

def test_the_resolver_detects_a_line_past_the_end_of_a_file(tmp_path):
    """DISCIPLINE rule 1, against a constructed file rather than a reverted
    one — the same shape `test_the_bom_check_actually_detects_one` uses, and
    for the same reason: the real bad anchors are corrected in the report
    this round commits, so asserting today's tree is clean would never
    exercise the failing branch."""
    (tmp_path / "short.py").write_text("a\nb\nc\n", encoding="utf-8")
    report = "the guard is at `short.py:2` and the leak at `short.py:9`"
    # `short.py` has no directory component, so it is skipped by design.
    assert ca.unresolvable(report, tmp_path) == []

    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "short.py").write_text("a\nb\nc\n", encoding="utf-8")
    report = "the guard is at `pkg/short.py:2` and the leak at `pkg/short.py:9`"

    assert ca.unresolvable(report, tmp_path) == [
        "pkg/short.py:9 — file is 3 lines"]


def test_a_range_is_judged_by_its_end_not_its_start(tmp_path):
    """CQ-20's real anchor is `tests/test_packaging.py:140-145,194-209`
    against a 207-line file: the start of every range resolves and only the
    last one overshoots, by two lines. A checker reading range starts would
    have passed it, which is the failure this assertion exists to refuse."""
    pkg = tmp_path / "tests"
    pkg.mkdir()
    (pkg / "t.py").write_text("\n".join("x" * 1 for _ in range(207)),
                              encoding="utf-8")

    assert ca.unresolvable("`tests/t.py:140-145,194-207`", tmp_path) == []
    assert ca.unresolvable("`tests/t.py:140-145,194-209`", tmp_path) == [
        "tests/t.py:140-145,194-209 — file is 207 lines"]


def test_the_resolver_detects_a_path_that_does_not_exist(tmp_path):
    assert ca.unresolvable("`clauditseo/gone.py:3`", tmp_path) == [
        "clauditseo/gone.py:3 — no such file"]


@needs_register
def test_the_bad_anchors_of_report_043_are_found_in_the_real_report():
    """The proof that matters: the checker run against the committed report
    the finding was raised from, not a fixture written to satisfy it.

    `audits/043-2026-08-18.md` is immutable — a report is committed on its
    own and never edited — so this reads back for as long as the files it
    names stay shorter than the lines it cites. Three are asserted by name
    rather than all six: `clauditseo/provenance.py` is 157 lines against
    citations at 350 and 335, `tests/test_provenance.py` is 112 against 991,
    and `dashboard/src/favicon.ts` is 44 against 486 — three to eight times
    the headroom, so growth in the tree cannot quietly turn this green. The
    other two overshoot by one and two lines and are deliberately left out
    of the assertion for exactly that reason.
    """
    text = (AUDITS / "043-2026-08-18.md").read_text(encoding="utf-8")
    bad = ca.unresolvable(ca.evidence_cells(text))
    paths = {line.split(":")[0] for line in bad}

    assert {"clauditseo/provenance.py",
            "tests/test_provenance.py",
            "dashboard/src/favicon.ts"} <= paths, bad


@needs_register
def test_a_prior_anchor_quoted_as_wrong_is_not_read_as_an_address():
    """A row correcting an anchor quotes the bad one to say what was wrong
    with it. Report 044's CQ-65 reads "the prior anchor
    `tests/test_provenance.py:974-991` names a file of 112 lines", and WF-44
    quotes all five in its Finding cell.

    Scanning the whole document reports those quotations as defects, which
    would make an honest account of a mistake indistinguishable from
    repeating it — a check no report that explains itself could ever pass.
    Anchors are therefore read from the Evidence column, where an anchor is
    used as an address.
    """
    text = (AUDITS / "044-2026-08-18.md").read_text(encoding="utf-8")

    quoted = {p for p, _ in ca.anchors(text)}
    addresses = {p for p, _ in ca.anchors(ca.evidence_cells(text))}

    assert "tests/test_provenance.py" in quoted
    whole_doc = {line.split(":")[0] for line in ca.unresolvable(text)}
    evidence = {line.split(":")[0] for line in
                ca.unresolvable(ca.evidence_cells(text))}
    assert "tests/test_provenance.py" in whole_doc, (
        "the premise: scanning the whole report does flag the quotation")
    assert "tests/test_provenance.py" not in evidence, (
        "and reading only the Evidence column does not")
    assert addresses <= quoted


def test_an_escaped_pipe_does_not_shift_the_evidence_column():
    """CQ-86 is this defect in the register guard, found the same round: a
    cell counter splitting on every `|` reads a GFM-escaped one as a column
    boundary. Here it would silently move the Evidence column one cell left
    for any row quoting a rule with an alternation in it, so every anchor in
    that row would go unchecked — the failure mode being fixed, reintroduced
    by the fix.
    """
    row = (f"{ca._PILLAR_HEADER}\n"
           "| --- | --- | --- | --- | --- |\n"
           r"| CQ-99 | matches `a \| b` | High | `clauditseo/gone.py:3` | x |")

    assert ca.anchors(ca.evidence_cells(row)) == [("clauditseo/gone.py", "3")]


@needs_register
def test_the_checker_names_what_it_did_not_check(capsys):
    """DISCIPLINE rule 4. A bare `app.py:629` cannot be resolved without
    guessing which `app.py` is meant, and guessing is the class of mistake
    WF-44 is about — so it is skipped. A skip nobody reports is coverage
    nobody has, which is why the summary line states both counts.

    **WF-46: the status is no longer discarded, and the assertion is not
    `== 0`.** This test called `main` against the real `audits/` and checked
    two substrings while `main` returned 1, so the one runner the resolve
    half had could not fail. Binding it flatly to zero would ship a worse
    thing than that: `main` checks the newest report, a round may not edit a
    committed report, and `audit-fix/SKILL.md` step 2 says in as many words
    that a surviving bad anchor is reported and carried to `NEXT_UP.md`
    rather than blocking — so a flat `== 0` would make the next report with
    a bad anchor an unfixable red, and the only way out would be the edit
    the rule forbids. Report 045's remediation proposed gating that on "the
    newest report is the one this round wrote", which nothing in the tree
    can tell a test.

    So the admissible non-zero is enumerated instead: an unresolvable anchor
    in a committed report, which is the one failure a round cannot repair.
    The cohort half's remedy *is* a row a round may add, and
    `test_every_long_lived_anchor_has_a_disposition` holds it to zero
    unconditionally — a non-zero from that half fails there and here.
    """
    status = ca.main([], AUDITS)
    out = capsys.readouterr().out

    assert "evidence anchors checked" in out
    assert "not checked" in out
    assert status == 0 or "UNRESOLVABLE ANCHORS" in out, (
        f"main returned {status} for a reason a round could have fixed; "
        f"the only admissible non-zero here is a committed report's "
        f"unresolvable anchor. Output was: {out}")


# --------------------------------------------------------------------------
# WF-43 — the gate that forces a decision, made capable of seeing a gap
# --------------------------------------------------------------------------

def test_the_cohort_check_sees_an_anchor_with_no_row(tmp_path):
    """The existing guard on this register,
    `test_the_engineering_set_is_counted_from_its_own_table`, asserts the
    stated figures match the rows it can see. It is structurally unable to
    notice a row that was never written, which is how four findings aged
    20-33 reports stayed out of the file entirely. This one is keyed on what
    the reports say, not on what the register says, so it can disagree with
    the register — DISCIPLINE rule 5.
    """
    audits = tmp_path / "audits"
    audits.mkdir()
    body = (f"{ca._PILLAR_HEADER}\n"
            "| --- | --- | --- | --- | --- |\n"
            "| CQ-01 | old | High | `pkg/old.py:1` | x |\n"
            "| CQ-02 | new | High | `pkg/new.py:1` | x |\n")
    for n in range(1, 13):
        (audits / f"{n:03d}-2026-08-14.md").write_text(
            body if n >= 11 else body.replace("| CQ-02 | new | High "
                                              "| `pkg/new.py:1` | x |\n", ""),
            encoding="utf-8")
    (audits / "DISPOSITIONS.md").write_text("# empty\n", encoding="utf-8")
    current = (audits / "012-2026-08-14.md").read_text(encoding="utf-8")

    missing = ca.undispositioned(audits, current)

    assert missing == ["pkg/old.py — cited by 12 reports, no row"], missing


def test_the_cohort_check_accepts_a_row_in_any_form(tmp_path):
    """The register's rows carry an anchor in whatever form the round that
    wrote it used — `clauditseo/adaptive.py:70,107` with lines,
    `dashboard/src/api.ts:303-315` with a range, `render.py` bare. A strict
    parse would report a disposition that exists as missing, and a false
    alarm on a register the loop is required to keep is what teaches people
    to edit around a check.

    **The fixture gained a header row when WF-45 landed, and the change is
    the finding rather than an accommodation of it.** It previously wrote a
    lone `| `pkg/old.py:70,107` | 12 |` with no header and no delimiter,
    which is not a GFM table and rendered as prose — readable only by a
    check that searched the document as one string. That is exactly what
    `.claude/agents/auditor.md` was discharged by. Every table in the real
    register has a header; the three anchor forms this test is about are
    unchanged and still accepted.
    """
    audits = tmp_path / "audits"
    audits.mkdir()
    body = (f"{ca._PILLAR_HEADER}\n"
            "| --- | --- | --- | --- | --- |\n"
            "| CQ-01 | old | High | `pkg/old.py:1` | x |\n")
    for n in range(1, 13):
        (audits / f"{n:03d}-2026-08-14.md").write_text(body, encoding="utf-8")
    current = body
    header = "| anchor | rounds |\n| --- | --- |\n"

    (audits / "DISPOSITIONS.md").write_text(
        header + "| `pkg/old.py:70,107` | 12 |\n", encoding="utf-8")
    assert ca.undispositioned(audits, current) == []

    (audits / "DISPOSITIONS.md").write_text(
        header + "| `old.py` | 12 |\n", encoding="utf-8")
    assert ca.undispositioned(audits, current) == []


@needs_register
def test_every_long_lived_anchor_has_a_disposition():
    """WF-43, the gate itself. `audit-fix/SKILL.md` step 4 says every finding
    at ten rounds gets one of six outcomes recorded in
    `audits/DISPOSITIONS.md` **before the round selects any lever** — and
    `git log -1 -- audits/DISPOSITIONS.md` named round 038 while rounds 039,
    040, 041 and 043 each selected one.

    Watched failing before the register was written: it reported 23 paths
    at 10 to 41 reports with no row, against an audit that had found four by
    hand.

    Keyed on the path, not on `path:lines`. `DISPOSITIONS.md` records that a
    finding-ID column was proposed twice and rejected because the auditor
    renumbers IDs every round; line numbers move for the same reason, so a
    range key would reset an age to one whenever code above it was edited.
    The cost is that the count is a citation count and not a survival count
    — a file cited across forty reports through successive different
    findings gets one row — which is why the register states it that way in
    its own column heading rather than calling it `rounds`.
    """
    current = (AUDITS / sorted(
        p.name for p in ca.reports(AUDITS))[-1]).read_text(encoding="utf-8")

    missing = ca.undispositioned(AUDITS, current)

    assert missing == [], missing


@pytest.mark.parametrize("path", [p for p in ca.reports(AUDITS)],
                         ids=lambda p: p.name)
def test_every_report_exposes_its_evidence_column(path):
    """The collector, not the content. Every check above reads the Evidence
    column, so a report the extractor cannot parse would be checked as an
    empty document and pass silently — the shape of failure this repository
    has paid for five times by its own count."""
    text = path.read_text(encoding="utf-8", errors="replace")

    assert ca.evidence_cells(text).strip(), (
        f"{path.name} exposes no Evidence column to check")


# --------------------------------------------------------------------------
# WF-45 — the gate defeated by substring matching
# --------------------------------------------------------------------------

def _cohort_corpus(tmp_path, register: str, anchor: str = "pkg/thing.py:1",
                   reports_count: int = 10):
    """A minimal `audits/` where one anchor is exactly at the threshold.

    Ten reports each citing the same anchor in their Evidence column, plus a
    `DISPOSITIONS.md` whose text the caller controls. That is the whole input
    `undispositioned` reads, so the fixture is the finding: what discharges
    the gate is decided by the register's shape and nothing else.
    """
    audits = tmp_path / "audits"
    audits.mkdir()
    for n in range(1, reports_count + 1):
        (audits / f"{n:03d}-2026-01-01.md").write_text(
            f"{ca._PILLAR_HEADER}\n"
            "| --- | --- | --- | --- | --- |\n"
            f"| CQ-01 | a thing | High | `{anchor}` | it breaks |\n",
            encoding="utf-8")
    (audits / "DISPOSITIONS.md").write_text(register, encoding="utf-8")
    return audits


def test_prose_naming_a_file_does_not_discharge_the_gate(tmp_path):
    """WF-45, live defeat one. `.claude/agents/auditor.md` was cited by 11
    reports with no register row at all and passed the gate, because
    `audits/DISPOSITIONS.md:77` contains the sentence "and `auditor.md` now
    says so in the rule that ages a finding". The containment test read the
    register as one string, so a sentence *about* a file discharged the
    requirement to decide what happens to the findings *in* it.

    Watched failing before the row-level match landed: this returned `[]`.
    """
    audits = _cohort_corpus(tmp_path, (
        "## Notes\n\n"
        "The gate now runs, and `pkg/thing.py` is named here in prose to say\n"
        "so, which is not a disposition.\n"))

    missing = ca.undispositioned(audits, (audits / "010-2026-01-01.md")
                                 .read_text(encoding="utf-8"))

    assert missing == ["pkg/thing.py — cited by 10 reports, no row"]


def test_a_struck_through_row_does_not_discharge_the_gate(tmp_path):
    """WF-45, live defeat two, and the more expensive of the pair.
    `clauditseo/modules/prf.py` is cited by 42 reports and carried four live
    findings in report 044 — CQ-61, CQ-62, CQ-67, CQ-74 — while passing the
    gate on `audits/DISPOSITIONS.md:122`, a `~~struck-through~~` row reading
    "**taken, round 031**" for a different finding that closed four rounds
    before those four were raised.

    A strike means *this finding* was disposed of, not *this file* was. Read
    the other way it makes the register self-silencing: every disposition the
    loop ever completes permanently exempts the file it touched.

    Watched failing before the row-level match landed: this returned `[]`.
    """
    audits = _cohort_corpus(tmp_path, (
        "| finding | anchor | rounds |\n"
        "| --- | --- | --- |\n"
        "| ~~an older, unrelated defect~~ — **taken, round 031** | "
        "`pkg/thing.py:140-150` | 19 |\n"))

    missing = ca.undispositioned(audits, (audits / "010-2026-01-01.md")
                                 .read_text(encoding="utf-8"))

    assert missing == ["pkg/thing.py — cited by 10 reports, no row"]


def test_a_live_row_still_discharges_the_gate(tmp_path):
    """The other direction, and the one that decides whether the fix is
    usable. A gate that reports a path already carrying a decision is a false
    alarm on a register the loop is required to keep, which
    `undispositioned`'s own docstring names as what teaches people to edit
    around a check."""
    audits = _cohort_corpus(tmp_path, (
        "| finding | anchor | rounds |\n"
        "| --- | --- | --- |\n"
        "| the thing is wrong | `pkg/thing.py:140-150` | 19 |\n"))

    assert ca.undispositioned(audits, (audits / "010-2026-01-01.md")
                              .read_text(encoding="utf-8")) == []


def test_a_row_naming_the_file_without_its_directory_still_discharges(tmp_path):
    """The deliberate looseness that survives the rewrite. Rows written
    before the derived table used whatever form the round had —
    `` `loc.py:21` ``, `` `render.py` `` — and the reports key on full paths,
    so dropping the bare-name fallback would report twenty live decisions as
    missing. It is kept, and narrowed from "anywhere in the document" to
    "in some row's anchor cell"."""
    audits = _cohort_corpus(tmp_path, (
        "| finding | anchor | rounds |\n"
        "| --- | --- | --- |\n"
        "| the thing is wrong | `thing.py:21`, `other.tsx` | 19 |\n"))

    assert ca.undispositioned(audits, (audits / "010-2026-01-01.md")
                              .read_text(encoding="utf-8")) == []


def test_a_row_in_the_derived_table_discharges_from_its_own_anchor_column(
        tmp_path):
    """The register has two engineering tables with different shapes: the
    older one is `finding | anchor | rounds` and the one round 044 derived is
    `anchor | reports citing | ...`. The anchor column is found by its header
    rather than by position, because a fix keyed on column two would silence
    the 23 rows the previous round added."""
    audits = _cohort_corpus(tmp_path, (
        "| anchor | reports citing | findings in report 044 | routing |\n"
        "| --- | --- | --- | --- |\n"
        "| `pkg/thing.py` | 41 | CQ-08 (H) | engineering |\n"))

    assert ca.undispositioned(audits, (audits / "010-2026-01-01.md")
                              .read_text(encoding="utf-8")) == []


# --------------------------------------------------------------------------
# WF-46 — the exit status the suite computed and threw away
# --------------------------------------------------------------------------

def test_main_returns_nonzero_when_an_anchor_does_not_resolve(tmp_path,
                                                              capsys):
    """WF-46. `main`'s return value is its whole contract — it is what
    `sys.exit` hands the shell and what step 2 reads — and nothing asserted
    it. `test_the_checker_names_what_it_did_not_check` calls `main` against
    the real `audits/` and checks two substrings of stdout, discarding the
    status; it was green while `main` returned 1.

    Watched failing before the assertion landed only in the sense that
    nothing computed it: this is the first test of the value.
    """
    audits = _cohort_corpus(tmp_path, (
        "| anchor | reports citing | findings | routing |\n"
        "| --- | --- | --- | --- |\n"
        "| `pkg/thing.py` | 41 | CQ-01 (H) | engineering |\n"),
        anchor="pkg/thing.py:9999")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "thing.py").write_text("one line\n", encoding="utf-8")

    assert ca.main([], audits) == 1
    assert "file is 1 lines" in capsys.readouterr().out


def test_main_returns_zero_when_both_halves_pass(tmp_path, capsys):
    """The other half of the same contract. A status that is 1 for every
    input is not a check, and a fixture proving only the failure direction
    cannot tell the two apart."""
    audits = _cohort_corpus(tmp_path, (
        "| anchor | reports citing | findings | routing |\n"
        "| --- | --- | --- | --- |\n"
        "| `pkg/thing.py` | 41 | CQ-01 (H) | engineering |\n"),
        anchor="pkg/thing.py:1")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "thing.py").write_text("one line\n", encoding="utf-8")

    assert ca.main([], audits) == 0
    assert "clean" in capsys.readouterr().out


# --------------------------------------------------------------------------
# WF-96 — the gate reads addresses and never claims
# --------------------------------------------------------------------------
#
# A row's anchor resolving is not evidence the row still describes what is
# there. UX-09 was *"the scope line tags three figures through `m()` in one
# sentence"*; `ca8c02c` repaired that on 20 August 2026 and twenty-eight
# consecutive reports carried the row anyway, at High, counted in every
# `high:` line the loop reads and ranked by anchor age in every cohort walk.
# `unresolvable` could not have seen it — the address was correct throughout.
#
# Nothing mechanical can decide whether a sentence still describes a function,
# so this does not try. What it does is put the two side by side in the gate's
# own output, which is the cheapest thing that makes the drift visible to the
# person doing the carry.

def _readable_corpus(tmp_path, anchor: str, source: str,
                     finding: str = "a thing that is wrong"):
    """A cohort corpus whose anchor points at real, distinctive source."""
    audits = _cohort_corpus(tmp_path, (
        "| anchor | reports citing | findings | routing |\n"
        "| --- | --- | --- | --- |\n"
        "| `pkg/thing.py` | 41 | CQ-01 (H) | engineering |\n"),
        anchor=anchor)
    for report in sorted(audits.glob("0*.md")):
        report.write_text(
            f"{ca._PILLAR_HEADER}\n"
            "| --- | --- | --- | --- | --- |\n"
            f"| CQ-01 | {finding} | High | `{anchor}` | it breaks |\n",
            encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "thing.py").write_text(source, encoding="utf-8")
    return audits


def test_the_gate_can_show_the_source_a_row_cites(tmp_path, capsys):
    """The claim and the code, printed together, on request.

    Watched failing before `context_lines` and `--context` existed: the run
    printed the summary and the `clean` line and no source at all, so the
    assertion on the cited text failed on a stdout that could not carry it.
    """
    audits = _readable_corpus(
        tmp_path,
        anchor="pkg/thing.py:2",
        source="def scope_line(parts):\n"
               "    return provenance_tag(' and '.join(parts))\n"
               "# one tag, at the end of the sentence\n",
        finding="the scope line tags three figures through `m()`")

    assert ca.main(["--context"], audits) == 0
    shown = capsys.readouterr().out
    assert "CQ-01" in shown
    assert "the scope line tags three figures through `m()`" in shown
    assert "return provenance_tag(' and '.join(parts))" in shown

    assert ca.main([], audits) == 0
    assert "return provenance_tag" not in capsys.readouterr().out, (
        "the default output is what CI and step 2 read; the re-read surface "
        "is opt-in so it cannot flood them")


def test_showing_the_source_does_not_change_what_the_gate_decides(tmp_path,
                                                                  capsys):
    """`--context` adds a reading surface, not a verdict.

    A mode that made a red gate green would be worse than no mode, and one
    that silently omitted the anchors it could not read would hide exactly
    the rows most worth looking at — an unresolvable anchor is a drifted row
    by definition.

    Watched failing before the fix: `main` ignored the flag, so the context
    block was absent and the assertion on the unreadable marker failed while
    the status was already 1 for the other half's reason.
    """
    audits = _readable_corpus(
        tmp_path, anchor="pkg/thing.py:9999", source="one line\n")

    assert ca.main(["--context"], audits) == 1
    shown = capsys.readouterr().out
    assert "UNRESOLVABLE ANCHORS" in shown
    assert "pkg/thing.py:9999" in shown
    assert "unreadable" in shown


# --------------------------------------------------------------------------
# Q-16 — the same resolve judgement, over the second corpus
# --------------------------------------------------------------------------
#
# Promoted by the operator on 25 August 2026 after CQ-151 was carried by
# eleven reports and its remedy given twice without surviving a round. The
# invariant is checkable in two halves and both are asserted below: an anchor
# in a source comment resolves, and the population of such anchors comes from
# a walk of the tree rather than from a list somebody keeps up to date.


def _source_tree(tmp_path, files: dict[str, str]) -> Path:
    """A miniature repository: `{"clauditseo/a.py": "..."}` and so on.

    Built rather than pointed at the real tree, because a fixture that can
    only be satisfied by the repository being green cannot be watched failing
    — DISCIPLINE rule 1, and the reason the WF-44 resolver tests above build
    their own files too.
    """
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tmp_path


def test_a_source_comment_citing_a_line_past_the_end_is_found(tmp_path):
    """The failing direction, watched first. `crawl.py` cited `api/app.py:31`
    for an import that is on line 32 of `clauditseo/api/app.py`, and eleven
    reports went by without anything computing that.
    """
    root = _source_tree(tmp_path, {
        "clauditseo/target.py": "one\ntwo\n",
        "clauditseo/citer.py": "# see `clauditseo/target.py:99` for the gate\n",
    })

    failures, seen, quoted, _ = ca.unresolvable_source(root)

    assert seen == 1, "the population must be non-empty or the check is vacuous"
    assert quoted == 0
    assert len(failures) == 1
    assert "clauditseo/citer.py:1" in failures[0], (
        "the citing comment is what gets repaired, so it is named first")
    assert "clauditseo/target.py:99" in failures[0]
    assert "file is 2 lines" in failures[0]


def test_a_source_comment_citing_a_missing_file_is_found(tmp_path):
    """The shape all five of CQ-151's live pointers had: not a line past the
    end but a path that is repo-relative to nothing. `api/app.py` resolves
    from no root in this tree, and rewriting it as `clauditseo/api/app.py` is
    what sends the author back to the line to re-derive it.
    """
    root = _source_tree(tmp_path, {
        "clauditseo/api/app.py": "one\n" * 50,
        "dashboard/src/screen.tsx": "/* the key is at `api/app.py:31`. */\n",
    })

    failures, seen, _, _ = ca.unresolvable_source(root)

    assert seen == 1
    assert len(failures) == 1
    assert "no such file" in failures[0]
    assert "dashboard/src/screen.tsx:1" in failures[0]


def test_a_source_comment_whose_address_resolves_is_not_reported(tmp_path):
    """The other direction. A checker that fails on every input is not a
    checker, and the two fixtures above prove only the failing half."""
    root = _source_tree(tmp_path, {
        "clauditseo/target.py": "one\ntwo\nthree\n",
        "scripts/citer.py": "# see `clauditseo/target.py:2-3` for the gate\n",
    })

    failures, seen, quoted, _ = ca.unresolvable_source(root)

    assert seen == 1, "the population must be non-empty or this proves nothing"
    assert failures == []
    assert quoted == 0


def test_the_same_wrong_pointer_in_two_files_is_reported_twice(tmp_path):
    """`anchors` deduplicates and `source_citations` does not, and the
    difference is a repair that would otherwise be reported as done. Two of
    CQ-151's live pointers were the identical string `api/app.py:1017`, in
    `expert.tsx` and in `tools.tsx`; collapsing them would have named one
    file and left the other wrong.
    """
    root = _source_tree(tmp_path, {
        "dashboard/src/one.tsx": "/* `clauditseo/gone.py:4` */\n",
        "dashboard/src/two.tsx": "/* `clauditseo/gone.py:4` */\n",
    })

    failures, seen, _, _ = ca.unresolvable_source(root)

    assert seen == 2
    assert len(failures) == 2
    assert {"dashboard/src/one.tsx", "dashboard/src/two.tsx"} == {
        line.split(":")[0] for line in failures}


def test_a_paragraph_that_quotes_an_address_is_not_read_as_giving_one(
        tmp_path):
    """The source analogue of
    `test_a_prior_anchor_quoted_as_wrong_is_not_read_as_an_address`, and the
    same reasoning: `check_anchors`'s own docstring quotes report 044's bad
    anchor to explain why `evidence_cells` exists, and a check that could not
    tell that from a wrong address would be unsatisfiable by any file that
    explains itself. Source has no Evidence column to narrow to, so the
    distinction is declared with `QUOTE_MARKER` — and it is counted and
    reported, never silently dropped.
    """
    root = _source_tree(tmp_path, {
        "scripts/citer.py":
            '"""Why the resolver exists.\n'
            '\n'
            'Report 044 cited `tests/gone.py:974-991` against a file of 112\n'
            'lines - anchor-quote, the address is the defect being described.\n'
            '"""\n',
    })

    failures, seen, quoted, _ = ca.unresolvable_source(root)

    assert failures == []
    assert seen == 0
    assert quoted == 1, "skipped, but counted — DISCIPLINE rule 4"


def test_the_quote_marker_does_not_reach_past_its_own_paragraph(tmp_path):
    """The escape is narrow or it is a way to switch the check off. Scoped to
    the file, one marker would blind `scripts/check_anchors.py` — the file in
    the tree most likely to accumulate quoted bad addresses — to the rule it
    implements.
    """
    root = _source_tree(tmp_path, {
        "scripts/citer.py":
            "# Report 044 cited `tests/gone.py:974-991` - anchor-quote.\n"
            "\n"
            "# The key is written at `clauditseo/absent.py:12`.\n",
    })

    failures, seen, quoted, _ = ca.unresolvable_source(root)

    assert quoted == 1
    assert seen == 1
    assert len(failures) == 1
    assert "clauditseo/absent.py:12" in failures[0], (
        "the marked paragraph is skipped and the one below it is not")


def test_the_source_population_is_walked_rather_than_listed():
    """Q-16's second half, and the half CQ-151 died of. The finding named
    four files in report 073 and five by report 085; the count grew in eight
    of eleven rounds because a report can only re-list what someone typed
    into the last one.

    Asserted against the real tree, because a walk that finds files in a
    fixture proves nothing about whether it is pointed at the repository.
    """
    walked = ca.source_files(ROOT)

    assert len(walked) > 50, (
        f"a population of {len(walked)} is not this repository's source")
    roots = {p.relative_to(ROOT).parts[0] for p in walked}
    assert roots == {"clauditseo", "dashboard", "scripts"}
    assert all(p.suffix in ca.SOURCE_SUFFIXES for p in walked)


@needs_register
def test_every_source_comment_anchor_resolves():
    """The invariant itself, held to zero unconditionally.

    Unlike the resolve half over `audits/`, this one has no escape hatch and
    should not have one: a report is an untouched record a round may not
    edit, but a comment is source, and a round that writes a wrong address
    can always fix it in the commit that wrote it. That is the whole
    difference Q-16 turns on — the remedy is available, so the gate can be
    absolute.

    The population is asserted non-empty in the same test, which is the
    guard's-population invariant applied to this guard.
    """
    failures, seen, quoted, generated = ca.unresolvable_source(ROOT)

    assert seen > 0, (
        "no source anchors were resolved at all — a green here would mean "
        "the walk stopped finding them, not that the tree is clean")
    assert failures == [], (
        "a source comment sends a reader to an address that does not exist:\n"
        + "\n".join(f"  {line}" for line in failures)
        + f"\n({seen} anchors resolved, {quoted} quoted under "
          f"{ca.QUOTE_MARKER!r} and {generated} under generated output, "
          f"both skipped)")


# --------------------------------------------------------------------------
# Relay 105 — an address a clean checkout can never have
# --------------------------------------------------------------------------

def test_an_anchor_under_generated_output_is_skipped_rather_than_failed(
        tmp_path):
    """The failing direction, watched first. `render.py`'s version-history
    note quotes what a document written by an older renderer *said*, and the
    document is a report artifact under `reports/out/` — ignored, never
    committed, and absent from every clean checkout by construction. Resolving
    it made the guard's answer depend on whether the machine running it
    happened to have generated a report, which is green here and red on CI.
    """
    root = _source_tree(tmp_path, {
        ".gitignore": "reports/out/\n",
        "clauditseo/citer.py":
            "# 1.30.0: at `reports/out/run-2026-08-22-91f9ad50.md:295` the\n"
            "# note was attached to the client's own phone number.\n",
    })

    failures, seen, quoted, generated = ca.unresolvable_source(root)

    assert failures == []
    assert seen == 0, "a generated path is never resolved"
    assert quoted == 0
    assert generated == 1, "skipped, but counted — DISCIPLINE rule 4"


def test_a_stale_source_anchor_beside_a_generated_one_still_reddens(tmp_path):
    """The value Q-16 promoted the guard for, kept. An exclusion that also
    stops the check firing on a genuinely stale *source* address would buy CI
    green by passing real drift, so the two are asserted in one tree: the
    generated citation is skipped and the wrong one beside it is still named.
    """
    root = _source_tree(tmp_path, {
        ".gitignore": "reports/out/\n",
        "clauditseo/target.py": "one\ntwo\n",
        "clauditseo/citer.py":
            "# see `reports/out/run-2026-08-22.md:295` for what it said\n"
            "\n"
            "# the gate is at `clauditseo/target.py:99`\n",
    })

    failures, seen, _, generated = ca.unresolvable_source(root)

    assert generated == 1
    assert seen == 1
    assert len(failures) == 1
    assert "clauditseo/target.py:99" in failures[0]
    assert "file is 2 lines" in failures[0]


def test_a_path_that_only_looks_generated_is_still_resolved(tmp_path):
    """The exclusion is `.gitignore`'s answer, not a guess from the name.
    `reports/out/` is ignored and `reports/` is not, so a committed document
    one level up is still an address a reader is meant to open — and a rule
    keyed on the word "reports" would have stopped checking it.
    """
    root = _source_tree(tmp_path, {
        ".gitignore": "reports/out/\n",
        "reports/brief.md": "one\ntwo\n",
        "clauditseo/citer.py": "# the scope is at `reports/brief.md:99`\n",
    })

    failures, seen, _, generated = ca.unresolvable_source(root)

    assert generated == 0
    assert seen == 1
    assert len(failures) == 1
    assert "reports/brief.md:99" in failures[0]


def test_a_tree_with_no_gitignore_excludes_nothing(tmp_path):
    """The fixtures above this section build no `.gitignore`, so the absence
    has to mean "nothing is generated output" rather than "everything is" —
    otherwise adding this exclusion would quietly switch off every resolver
    test that predates it.
    """
    root = _source_tree(tmp_path, {
        "clauditseo/citer.py": "# see `reports/out/run.md:295`\n",
    })

    failures, seen, _, generated = ca.unresolvable_source(root)

    assert ca.generated_prefixes(root) == ()
    assert generated == 0
    assert seen == 1
    assert len(failures) == 1


def test_the_evidence_half_skips_generated_output_too(tmp_path):
    """Both halves make the same judgement, so both take the same exclusion.
    Report 100 cites two comparison documents under `reports/out/`, and a fix
    to the source half alone would leave `/audit-fix` step 2 red on any
    machine that had not generated them — the same defect, in the corpus a
    round may not edit its way out of.
    """
    _source_tree(tmp_path, {
        ".gitignore": "reports/out/\n",
        "clauditseo/target.py": "one\ntwo\n",
    })
    evidence = ("`reports/out/comparison-2026-08-23-eda5c0bb.md:5` and "
                "`clauditseo/target.py:99`")

    bad = ca.unresolvable(evidence, tmp_path)

    assert len(bad) == 1, "the generated citation is skipped, the stale one is not"
    assert "clauditseo/target.py:99" in bad[0]
    assert ca.generated_anchors(evidence, tmp_path) == [
        ("reports/out/comparison-2026-08-23-eda5c0bb.md", "5")]


def test_the_generated_prefixes_are_read_from_this_repositorys_gitignore():
    """Derived rather than typed, for CQ-151's reason one level out: a list of
    output directories in this module would be a second declaration of
    something `.gitignore` already states, and the two would drift the first
    time a build wrote somewhere new.

    Asserted against the real tree, because prefixes found in a fixture prove
    nothing about whether the reader is pointed at the repository.
    """
    prefixes = ca.generated_prefixes(ROOT)

    assert "reports/out" in prefixes, (
        "the directory the renderer writes client documents to")
    assert "dashboard/dist" in prefixes, "the built bundle"
    assert ca.is_generated("reports/out/run-2026-08-22-91f9ad50.md", prefixes)
    assert not ca.is_generated("clauditseo/reporting/render.py", prefixes)
    assert ca.is_generated("clauditseo/__pycache__/render.pyc", prefixes), (
        "an unanchored entry matches at any depth, as git reads it")


# --------------------------------------------------------------------------
# Q-28 / CQ-227 — a bare citation is resolved when exactly one file bears the
# name, and refused loudly when two do
# --------------------------------------------------------------------------

def test_a_bare_citation_with_one_matching_file_is_resolved(tmp_path):
    """The failing direction, watched first. Q-28's answer is *resolve them*:
    `render.py:592` names one file in this tree, so declining to resolve it
    was never protecting anyone from a guess — there was nothing to guess.

    Measured at HEAD before this clause existed: the source half checked 15
    citations and skipped 92, of which 41 name exactly one tracked file.
    """
    root = _source_tree(tmp_path, {
        "clauditseo/reporting/render.py": "one\ntwo\n",
        "scripts/citer.py": "# the version note is at `render.py:99`\n",
    })

    failures, resolved, ambiguous, unmatched = ca.unresolvable_bare_source(root)

    assert resolved == 1, (
        "the population must be non-empty or the check is vacuous")
    assert (ambiguous, unmatched) == (0, 0)
    assert len(failures) == 1
    assert "scripts/citer.py:1" in failures[0], (
        "the citing comment is what gets repaired, so it is named first")
    assert "clauditseo/reporting/render.py" in failures[0], (
        "the resolved path is named, not the bare spelling alone — the "
        "reader has to be able to check the resolution the guard made")
    assert "render.py is 2 lines" in failures[0], (
        "the length is stated against the file that was actually read, not "
        "against a bare 'file' — the resolution is part of the claim")


def test_a_bare_citation_that_resolves_cleanly_is_not_reported(tmp_path):
    """The other direction. A checker that fails on every input is not a
    checker, and the clause above proves only the failing half."""
    root = _source_tree(tmp_path, {
        "clauditseo/reporting/render.py": "one\ntwo\nthree\n",
        "scripts/citer.py": "# the version note is at `render.py:2-3`\n",
    })

    failures, resolved, ambiguous, unmatched = ca.unresolvable_bare_source(root)

    assert resolved == 1, "the population must be non-empty or this proves nothing"
    assert failures == []
    assert (ambiguous, unmatched) == (0, 0)


def test_a_bare_citation_matching_two_files_is_refused_and_not_guessed(
        tmp_path):
    """The guard that makes the widening safe, and the one Q-28's own answer
    names as its condition: *"only safe while it refuses the ambiguous case
    loudly"*.

    `ANCHOR`'s stated ground for skipping bare citations is that guessing
    which `app.py` is meant is the mistake WF-44 is about. That ground is
    true of the ambiguous case and only of it, so the refusal moves here
    rather than being dropped — and it reddens rather than being counted,
    because a citation that silently stops being checked the day a second
    file takes its name is the coverage-nobody-reports failure one level out.
    The repair is one word: give the comment its directory.
    """
    root = _source_tree(tmp_path, {
        "clauditseo/api/app.py": "one\n" * 50,
        "clauditseo/admin/app.py": "one\n" * 50,
        "scripts/citer.py": "# the gate is at `app.py:31`\n",
    })

    failures, resolved, ambiguous, unmatched = ca.unresolvable_bare_source(root)

    assert (resolved, ambiguous, unmatched) == (0, 1, 0), (
        "an ambiguous citation is refused, not resolved to whichever file "
        "the walk reached first")
    assert len(failures) == 1
    assert "scripts/citer.py:1" in failures[0]
    assert "clauditseo/admin/app.py" in failures[0]
    assert "clauditseo/api/app.py" in failures[0], (
        "both candidates are named, so the author can say which was meant "
        "without re-deriving the ambiguity the guard already found")


def test_a_bare_token_that_names_no_file_is_counted_not_failed(tmp_path):
    """The population's other two thirds, and the reason "forbid them" would
    have been a lint on the wrong text.

    Measured over this repository: of the 92 tokens the source half skipped,
    51 are not citations at all — 47 of them are CSS contrast ratios written
    `4.5:1`, plus a host and port, a minified vendor bundle's `t.y:0`, and
    this module's own `path.ext:12` example. `BARE` cannot tell those from an
    address, and a matcher clever enough to try would be guessing about
    exactly the thing WF-44 says not to guess about. So the tree decides it:
    a token whose name no file bears is not an address, and it is counted and
    named rather than either failed or silently dropped.
    """
    root = _source_tree(tmp_path, {
        "clauditseo/target.py": "one\ntwo\n",
        "dashboard/src/styles.css": "/* contrast 4.5:1 against the surface */\n",
    })

    failures, resolved, ambiguous, unmatched = ca.unresolvable_bare_source(root)

    assert failures == [], (
        "a contrast ratio is not a stale address, and reddening on one would "
        "make the guard unusable in the file that carries 47 of them")
    assert (resolved, ambiguous, unmatched) == (0, 0, 1)


def test_the_basename_index_is_walked_from_the_whole_tree(tmp_path):
    """Not from `SOURCE_ROOTS`. Measured: six of the 41 resolvable bare
    citations name a file the source walk never sees — `OPERATOR_ACTIONS.md`
    cited from `app.py`, `views.tsx` and `rotate-registers.ps1`, a prompt
    under `clauditseo/prompts/`, and `.claude/loop/PROFILE.md` cited from
    `prove_fail.py`. Indexing only the source population would leave those
    six reported as naming no file, which is the same clean line over a real
    gap that CQ-227 is about.

    Generated output is excluded on `is_generated`'s judgement, so a name
    that only exists in a build directory does not resolve on the machine
    that built it and fail to on every other — DISCIPLINE rule 12's sibling,
    and the defect `generated_prefixes` exists for.
    """
    root = _source_tree(tmp_path, {
        "OPERATOR_ACTIONS.md": "one\ntwo\n",
        "clauditseo/keep.py": "x\n",
        "dashboard/dist/keep.py": "x\n",
        ".gitignore": "dashboard/dist/\n",
    })

    index = ca.tree_basenames(root)

    assert index["OPERATOR_ACTIONS.md"] == ["OPERATOR_ACTIONS.md"], (
        "a file at the repository root is in the index; the six citations "
        "that resolve outside SOURCE_ROOTS are why the walk is not the "
        "source walk")
    assert index["keep.py"] == ["clauditseo/keep.py"], (
        "the copy under generated output is excluded, so its presence on one "
        "machine cannot turn a unique name into an ambiguous one")


def test_every_bare_source_citation_that_names_a_file_resolves():
    """The invariant Q-28's answer creates, held to zero unconditionally and
    for `test_every_source_comment_anchor_resolves`'s reason: a comment is
    source, so the remedy is always available in the commit that wrote it.

    The population is asserted non-empty in the same test, which is the
    guard's-population invariant applied to this guard.
    """
    failures, resolved, ambiguous, unmatched = ca.unresolvable_bare_source(ROOT)

    assert resolved > 0, (
        "no bare citation resolved at all — a green here would mean the "
        "index stopped matching, not that the tree is clean")
    assert failures == [], (
        "a bare source citation names a file that does not reach the line, "
        "or names two files and cannot be resolved at all:\n"
        + "\n".join(f"  {line}" for line in failures)
        + f"\n({resolved} resolved by unique filename, {ambiguous} refused "
          f"as ambiguous, {unmatched} naming no file in the tree)")


# --------------------------------------------------------------------------
# CQ-234 — the listing has to survive the characters a report is written in
# --------------------------------------------------------------------------

_ARROW = "→"

#: A report shaped only as far as `context_lines` reads it: the pillar header,
#: one finding row whose claim carries a character cp1252 has no slot for, and
#: an anchor into a file the corpus provides. The arrow is not decoration - a
#: `RENDERER_VERSION` bump is written `1.34.0` + arrow + `1.35.0`, and report
#: 116 carries thirty of them.
_ARROW_REPORT = f"""# corpus

## PHASE 1 — FINDINGS

| ID | Finding | Severity | Evidence | Impact |
| --- | --- | --- | --- | --- |
| CQ-01 | The renderer moved 1.34.0{_ARROW}1.35.0 and the caption did not. | High | `clauditseo/thing.py:1` | A stored document reads as current. |
"""


def _arrow_corpus(tmp_path):
    """The smallest tree `main` will walk end to end: one report, one register
    it can find no rows in, and one source file an anchor resolves into."""
    audits = tmp_path / "audits"
    audits.mkdir()
    (audits / "001-2026-01-01.md").write_text(_ARROW_REPORT, encoding="utf-8")
    (audits / "DISPOSITIONS.md").write_text("# Dispositions\n", encoding="utf-8")
    (tmp_path / "clauditseo").mkdir()
    (tmp_path / "clauditseo" / "thing.py").write_text("x\n", encoding="utf-8")
    return audits


def test_a_stream_that_cannot_carry_the_character_still_carries_the_line():
    """DISCIPLINE rule 1, with the failing half asserted in the same test.

    The first clause is the defect: a cp1252 stdout - what Windows gives a
    piped `print` when `PYTHONIOENCODING` is unset - raises on the arrow. The
    second is that `readable_output` removes the raise without changing the
    encoding, so a consumer that asked for cp1252 still gets cp1252 bytes.

    Written against a constructed `TextIOWrapper` rather than the real stdout
    because a test may not reconfigure the stream pytest is capturing on and
    still be honest about what it proved.
    """
    unrepaired = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")

    with pytest.raises(UnicodeEncodeError):
        unrepaired.write(_ARROW)
        unrepaired.flush()

    buffer = io.BytesIO()
    repaired = io.TextIOWrapper(buffer, encoding="cp1252")
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = repaired
    try:
        ca.readable_output()
        print(f"1.34.0{_ARROW}1.35.0")
        repaired.flush()
    finally:
        sys.stdout, sys.stderr = stdout, stderr

    written = buffer.getvalue()

    assert repaired.encoding.lower().replace("-", "") == "cp1252", (
        "readable_output changed the stream's encoding; a consumer that "
        "asked for cp1252 would now be handed UTF-8 bytes it cannot decode, "
        "which trades the crash for mojibake rather than fixing it")
    assert b"1.34.0" in written and b"1.35.0" in written, (
        "the line either side of the unencodable character did not survive, "
        "so the escape replaced more than the character it could not carry")
    assert _ARROW.encode("cp1252", "backslashreplace") in written, (
        "the character was dropped or replaced with a lossy placeholder; "
        "backslashreplace is chosen so the reader can still tell which "
        f"character it was, and got {written!r}")


def test_the_context_listing_finishes_on_a_stdout_that_cannot_hold_a_report(
        tmp_path):
    """The operator's own invocation, end to end and out of process.

    CQ-234 was carried for ten reports and reproduced by hand at each; what
    was missing was a run of the real entry point under the real failing
    condition. `PYTHONIOENCODING=cp1252` is that condition made deterministic
    - it is what an unset `PYTHONIOENCODING` already gives a piped stdout on
    this platform, forced rather than waited for, so the guard does not
    depend on the machine it runs on.

    Exit 1 is admissible here and is the reason stderr is read rather than
    the status: `main` returns 1 for *"anchors did not resolve"* as well, so
    the crash is indistinguishable from a completed check by exit code alone.
    That is the finding's own impact sentence, and this is the assertion that
    would have caught it.
    """
    audits = _arrow_corpus(tmp_path)
    driver = (
        "import sys, pathlib; "
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r}); "
        "import check_anchors; "
        f"sys.exit(check_anchors.main(['--context'], pathlib.Path({str(audits)!r})))"
    )

    run = subprocess.run(
        [sys.executable, "-c", driver],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    err = run.stderr.decode("utf-8", errors="replace")
    out = run.stdout.decode("cp1252", errors="replace")

    assert "UnicodeEncodeError" not in err, (
        "the listing died on a character the report is written in:\n" + err)
    assert run.returncode in (0, 1), (
        f"the run neither passed nor reported a failure (exit "
        f"{run.returncode}):\n{err}")
    assert "context" in out, (
        "the --context block never started, so this guard would pass on a "
        f"run that printed nothing at all; got {out!r}")
    assert _ARROW.encode("cp1252", "backslashreplace").decode() in out, (
        "the claim carrying the unencodable character is not in the "
        "listing, so the run stopped before reaching it or dropped the row")
