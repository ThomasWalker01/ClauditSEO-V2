"""Automated report honesty checks (gate G7).

1. No number in a report may lack a source tag. Dates, times, ISO stamps,
   version strings, run ids, hostnames and check ids are identity, not
   metrics, and are exempt; everything else with a digit must sit on a line
   carrying `source:` or an explicit `[TO CONFIRM: …]` marker.
2. Every number in analyst-written narrative must exist verbatim in the
   deterministic evidence it was generated from.
"""

from __future__ import annotations

import re

MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
_EXEMPT = [
    re.compile(rf"\b\d{{1,2}} (?:{MONTHS}) \d{{4}}\b"),      # DD Month YYYY
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][\d:+.Zz-]+)?\b"),  # ISO 8601
    re.compile(r"\b\d{2}:\d{2}(?::\d{2})?\b"),               # times
    re.compile(r"\bv\d+[\w.]*\b"),                           # version strings
    re.compile(r"\b[0-9a-f]{8,}\b"),                          # run/finding ids
    re.compile(r"\bT[123]\b"),                               # tier labels
    # Evidence item ids. Three generators issue them and only two were
    # listed: `f{i}` (`clauditseo/analysts/base.py:149`), `x{j}`
    # (`clauditseo/analysts/base.py:191`) and `t{n}`
    # (`clauditseo/analysts/tools.py:243`). A tool id reaches `validate_draft`'s
    # `extra_ids`, so a finding may cite one, and the internal document
    # renders the citation line verbatim (`render.py:592`).
    re.compile(r"\b[ftx]\d+\b"),                            # evidence item ids
    re.compile(r"\bISO\s?8601\b"),                           # the standard's name
    # Dimension codes. A11Y carries digits, so the header line listing a
    # run's dimensions read as an untagged metric and blocked every report
    # for a run that included accessibility. A code is a name, not a number.
    re.compile(r"\bA11Y\b"),
    # Backticked paths. A URL path is an identifier, the same class as a
    # run id or a version string, and this report now lists the pages a
    # check affects — so a client's own URLs (`/blog/eofy-2026-...`,
    # `/success-stories/...-70k-line-of-credit`) read as untagged
    # metrics. Narrow to spans that start with a slash: a bare `42` in
    # backticks is still a number that has to say where it came from.
    re.compile(r"`/[^`]*`"),
    # Hostnames. CQ-130: the report title is `# SEO audit report - <domain>`
    # for **both** audiences (`render_run_report`'s `title`), so a client
    # whose domain carries a digit could not be sent a document at all.
    # Driven read-only
    # over the live database on 20 August 2026, the client document
    # generated for 1 of 3 real sites and the internal document for 0 of 3.
    # A host is a name, not a measurement - the same reasoning as `A11Y`.
    #
    # Two narrowings, because every entry here is a hole in the one gate
    # the provenance invariant rests on. The final label must be
    # **alphabetic**, so "94.23", "1,489" and "3.5s" are untouched. And the
    # lookahead requires the **first** label to contain a letter, so a
    # missing space after a full stop ("the score fell to 12.Then") cannot
    # carry the figure in front of it out of the gate's sight.
    re.compile(r"\b(?=[a-z0-9-]*[a-z])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b",
               re.I),
    # Backticked check ids, `DIM/check-id`. CQ-130's other half, internal
    # only (`render.py:816,848`): `h1-missing` and `h1-multiple` are the only
    # two digit-bearing check ids under `clauditseo/modules/`, and a missing
    # H1 is among the most common findings the product raises - so the
    # internal template was blocked for essentially any real audit.
    # Backticked and slash-bearing, the same shape the path rule above
    # already exempts; a bare `42` in backticks is still a number that has
    # to say where it came from.
    re.compile(r"`[A-Z][A-Z0-9]{1,4}/[a-z0-9-]+`"),
]
_NUMBER = re.compile(r"\d[\d,.]*\d|\d")
#: The source tag, matched as a tag rather than as a substring - CQ-55, and
#: demonstrated failure class 3, "a verification gate defeated by weak
#: matching", which this codebase has shipped before.
#:
#: Two leaks under one root. The tag was tested with `"source:" in
#: line.lower()`, so any word ending in it satisfied the gate - "Resource: 12
#: pages were affected." generated clean, reproduced 19 August 2026. And it
#: was tested against the **raw** line while the number was tested against
#: `stripped`, so a tag sitting inside a span the exemptions had already
#: discounted as an identifier sourced the metric beside it. Both close by
#: searching the same string the number was found in, for a tag with nothing
#: lettered attached to its front.
#:
#: The lookbehind excludes a hyphen as well as a letter, so "Open-source:" is
#: not a tag; a tag after a markdown bullet ("- source: engine") has a space
#: in front of it and still is one.
_TAG = re.compile(r"(?<![A-Za-z-])source:", re.I)

#: The lead of a hoisted section-provenance line (Q-57). A model-written
#: section — the client plan, a brief's findings table — carried the same
#: source tag on thirty consecutive lines, each tag longer than the line it
#: annotated. The tag is now stated once under the heading and the per-line
#: copies are dropped, so `unsourced_number_lines` has to learn that the
#: lines beneath such a declaration are sourced by it.
#:
#: **Keyed on this exact lead, not on "a tag with no number", deliberately.**
#: A heuristic that opened a scope on any tag-bearing line without a metric
#: would let a fabricated number through wherever a section happened to open
#: with prose — a real hole in the one gate the provenance invariant rests on
#: (`QUESTIONS.md` Q-57 names this cost). Only a line the renderer built with
#: `render.section_provenance` opens a scope, and the scope closes at the next
#: H1/H2 heading, so a covered span is exactly one model-written block.
_SECTION_SOURCE = re.compile(r"^_?Provenance note\b", re.I)
_MAJOR_HEADING = re.compile(r"#{1,2}\s")


class ReportCheckError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("report failed honesty checks:\n" + "\n".join(problems))
        self.problems = problems


def unsourced_number_lines(markdown: str) -> list[str]:
    """Lines containing a metric-like number with no source tag.

    A section-provenance line (Q-57) sources the lines beneath it until the
    next H1/H2 heading, so a hoisted tag covers its own block and nothing
    else; a differing line still carries its own tag and is sourced by it.
    """
    flagged = []
    section_sourced = False
    for line in markdown.splitlines():
        # A major heading closes any hoisted scope: the tag belongs to the
        # block it was declared in, never to the document. H3 and deeper do
        # not close it, because the plan's own sub-headings are H3.
        if _MAJOR_HEADING.match(line):
            section_sourced = False
        stripped = line
        for pattern in _EXEMPT:
            stripped = pattern.sub("", stripped)
        # `stripped` for all three, not `line` for two of them: a line
        # is one claim, and the checker may not call a span an
        # identifier while counting numbers and then read a tag out
        # of it.
        if _SECTION_SOURCE.match(stripped.strip()) and _TAG.search(stripped):
            # Opens the scope for the rows beneath it. It carries its own tag,
            # so the line below's normal test already passes it.
            section_sourced = True
        if _NUMBER.search(stripped) and not _TAG.search(stripped) \
                and "[TO CONFIRM" not in stripped and not section_sourced:
            flagged.append(line.strip())
    return flagged


def ungrounded_narrative_numbers(narrative: str, evidence_text: str) -> list[str]:
    """Numbers in analyst narrative absent from the evidence — compared as
    whole normalised tokens, not substrings, so "43" is not grounded by a
    "1043" buried in a hash or count."""
    from clauditseo.numbers import extract_numbers, ungrounded

    stripped = narrative
    for pattern in _EXEMPT:
        stripped = pattern.sub("", stripped)
    return ungrounded(stripped, extract_numbers(evidence_text))


def ungrounded_uncaveated_lines(brief_narrative: str,
                                evidence_text: str) -> list[str]:
    """Lines of specialist-brief prose quoting a number the deliverable's
    measured evidence does not contain, with no caveat on the line.

    CQ-09. The grounding half above reads `narrative`, which `_analyst_section`
    builds with `EXP:*` excluded by construction, while `_expert_section` is
    appended to `markdown` afterwards — so the model-written prose most likely
    to carry a fabricated number was the one text neither half of this gate
    ever grounded. `unsourced_number_lines` does read the section and passes it
    trivially: every brief row carries a `provenance_tag`, which is a true
    statement about where the prose came from and no statement at all about
    whether the number in it was measured.

    **Per line, and the caveat is read from the line.** A brief row whose
    number the document cannot ground renders carrying `ANALYST_FIGURE_NOTE`,
    which is a `[TO CONFIRM: …]` marker — the same thing `unsourced_number_lines`
    accepts in place of a source tag, for the same reason. So this asks the
    rendered text whether the marker is there, not the renderer whether it
    decided to put one. A renderer that stops applying the note is then a red
    suite rather than a silent change to a client's document, which is the
    class UX-80 closed by deleting a `title` no guard could see.

    **Not widened, and `_evidence_text` is deliberately left alone.** Audit 014
    reproduced the cost of the other direction: the allowed set was widened by
    the analyst's declared figures, which admitted brief figures into a check
    over text that could never contain a brief finding while letting a
    fabricated number through. The declared figures do their work where they
    render — the note on the row — and this reads the result of that rather
    than re-deriving the decision behind it.
    """
    flagged = []
    for line in brief_narrative.splitlines():
        if "[TO CONFIRM" in line:
            continue
        if ungrounded_narrative_numbers(line, evidence_text):
            flagged.append(line.strip())
    return flagged


def assert_report_honest(markdown: str, narrative: str, evidence_text: str,
                         brief_narrative: str = "") -> None:
    problems = [f"number without source tag: {line!r}"
                for line in unsourced_number_lines(markdown)]
    problems += [f"narrative number not in evidence: {n!r}"
                 for n in ungrounded_narrative_numbers(narrative, evidence_text)]
    # Named apart from the analyst half because the two refuse for different
    # reasons: an analyst number must be IN the evidence, a brief number must
    # be in the evidence OR caveated on its own line. Folding them would make
    # one message describe two rules.
    problems += [f"brief number neither grounded nor caveated: {line!r}"
                 for line in ungrounded_uncaveated_lines(brief_narrative,
                                                         evidence_text)]
    if problems:
        raise ReportCheckError(problems)
