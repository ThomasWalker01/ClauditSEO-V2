"""The baseline's frame, stated in the document whose counts stand on it.

WF-28 (High, carried since report 023) and UX-22 (Medium, carried since 019),
which report 091 names as **one residue seen from two sides** and asks to be
closed in one commit so the register records it once rather than twice.

Round 090 gave the comparison document a frame and round 091 made that frame
state one count of what the *current* run read. Both are about run B. Three of
the document's four section counts are decided by run B and are now framed:
`Persisting issues` and the score movement read the current run, and `Not
re-checked` states its reason per finding.

`## New issues` is not. `why_new` reads `crawled_a` and `dims_a` — the
baseline's paths and the baseline's dimensions — so a finding is "new" when the
baseline was in a position to see it and did not. `Resolved issues` is decided
the same way from the other end. Neither count means anything without the
baseline's scope, and `compare_runs` computed it at
`_run_scope(conn, run_a)` and then wrote only run B's into `diff["scope"]`.

Measured in report 091 on the pair the operator's database holds: run
`8fdeb042` recorded 99 crawled paths and no `sitemap_entry_total`, so
`_breadth_phrase` printed nothing beside the baseline composite either, and
`## New issues — 825` stood on a frame that appeared nowhere on the page.

The rule this file guards: **a comparison document states the baseline's scope
as well as the current run's, or says it could not establish it.** Silence is
not an option, for the reason `_diff_scope_lines` already gives about the
current run — the counts are printed regardless, so an absent frame is not a
fact withheld but a figure with nothing holding it.

The grain rule from round 091 binds the baseline sentence too, and this is the
easier of the two places to break it: a baseline's path count is often the only
count it has, and calling it "pages" would be UX-84 again, one run over.

DISCIPLINE rule 3 — consumers of `diff["scope"]` enumerated by grep before
this was written rather than taken from the report's list: `_diff_scope_lines`
via `DIFF_SCOPE_KEY` (`clauditseo/reporting/render.py`), `CompareView`
(`dashboard/src/views.tsx:1552`, which spells the key by hand — CQ-204), and
`compare_runs` itself, which is the writer. Nothing else reads it.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.reporting.render import render_comparison_report

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_anchors as ca  # noqa: E402


def _page(url: str, status: int = 200,
          content_type: str = "text/html; charset=utf-8") -> dict:
    """One stored page, in the shape `data/clauditseo.db` actually holds.

    CQ-203 is a guard whose fixture was a shape the product's own write path
    cannot produce. These keys were read off a stored blob, the same way
    `tests/test_a_comparison_states_one_count_of_what_it_read.py` derived its
    copy — deliberately duplicated rather than imported, so neither file's
    fixture can be changed for the other file's reasons.
    """
    return {"url": url, "requested_url": url, "status": status,
            "content_type": content_type, "title": "t", "links": []}


def _evidence(pages: list[dict], discovered: int | None) -> dict:
    """A crawl record in the shape `store_evidence` receives."""
    return {"stats": {"fetched": len(pages), "blocked_by_robots": 0,
                      "errors": 0, "queue_remaining": 0,
                      "duplicate_url_forms": 0, "sitemaps_read": 1},
            "pages": pages, "robots_blocked": [],
            "sitemap_entry_total": discovered, "truncated_by": None}


# --- the baseline's frame, at the source -----------------------------------

def test_the_diff_carries_the_baseline_scope_its_new_count_is_decided_by(
        tmp_path):
    """Driven through the product's own writers, not a hand-built dict.

    `compare_runs` already calls `_run_scope(conn, run_a)` — the values exist
    in the function and were dropped on the floor. This asserts they reach the
    one structure every consumer of the comparison reads.
    """
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Site, Tier

    conn = connect(tmp_path / "baseline-frame.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    def store(paths: list[str], pages: list[dict], dims: list[str]) -> str:
        run_id = runs.create_run(conn, site, dims, "T2")
        runs.store_evidence(conn, run_id, _evidence(pages, 10))
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2,
            dimensions=dims, findings=[], crawled_paths=set(paths)))
        return run_id

    baseline = store(["/"], [_page("https://x.test/")], ["ONP"])
    current = store(["/", "/a", "/b"],
                    [_page("https://x.test/"), _page("https://x.test/a"),
                     _page("https://x.test/b")], ["ONP", "TEC"])

    scope = runs.compare_runs(conn, baseline, current)["scope"]
    conn.close()

    assert scope["pages_crawled"] == 3 and scope["dimensions"] == ["ONP", "TEC"], (
        "the current run's frame is what round 090 and 091 established and "
        "must survive this change unchanged")
    assert scope["pages_crawled_baseline"] == 1, (
        "the `New issues` count is decided against the baseline's crawled "
        "paths and the diff does not carry them: "
        f"{sorted(scope)}")
    assert scope["dimensions_baseline"] == ["ONP"], (
        "a dimension the baseline never audited cannot make a finding new, "
        "and the diff does not say which ones it audited")
    assert scope["pages_fetched_baseline"] == 1, (
        "the baseline's page count is carried at the same grain as the "
        "current run's, or the document compares two different quantities")


# --- the baseline's frame, in the document ---------------------------------

#: `diff["scope"]` as `compare_runs` assembles it once the baseline is carried.
DIFF_SCOPE = {"pages_crawled": 3, "pages_fetched": 4,
              "pages_fetched_basis": "derived", "dimensions": ["ONP", "TEC"],
              "pages_crawled_baseline": 2, "pages_fetched_baseline": 2,
              "pages_fetched_basis_baseline": "recorded",
              "dimensions_baseline": ["ONP"]}


def _render(diff_scope: dict | None, audience: str = "client") -> str:
    a = {"id": "run-a", "finished_at": "2026-08-01T00:00:00+10:00",
         "composite_score": 70.0, "scope": None}
    b = {"id": "run-b", "finished_at": "2026-08-20T00:00:00+10:00",
         "composite_score": 74.0,
         "scope": {"pages_fetched": 4, "pages_fetched_basis": "derived",
                   "discovered": 10, "robots_blocked": 0,
                   "truncated_by": None}}
    diff = {"new": [], "resolved": [], "persisting": [], "not_rechecked": [],
            "scope": diff_scope}
    markdown, _ = render_comparison_report({"domain": "x.test"}, a, b, diff,
                                           audience)
    return markdown


def _baseline_sentence(markdown: str) -> str:
    line = [ln for ln in markdown.splitlines()
            if ln.startswith("Baseline scope:")]
    assert line, (
        "the document states no baseline scope, so `## New issues` and "
        "`## Resolved issues` stand on a frame that appears nowhere on the "
        "page — WF-28, measured on run `8fdeb042` at 99 crawled paths")
    return line[0]


@pytest.mark.parametrize("audience", ["client", "internal"])
def test_the_document_states_the_baseline_frame_its_counts_stand_on(audience):
    """The finding, stated as an assertion, scoped to its own line.

    CQ-203 is a guard that asserted a bare `15` appeared anywhere in a
    document. This locates the sentence first and asserts inside it, so a
    figure that happens to appear elsewhere cannot satisfy it.
    """
    sentence = _baseline_sentence(_render(DIFF_SCOPE, audience))

    assert "2 pages" in sentence, (
        f"the baseline's page count is not in its own sentence: {sentence!r}")
    assert "ONP" in sentence and "TEC" not in sentence, (
        "the baseline audited ONP alone; naming the current run's dimensions "
        f"here would restate run B's frame as run A's: {sentence!r}")
    assert "source:" in sentence, (
        "a stated frame carries provenance like every other claim in the "
        f"document: {sentence!r}")


def test_the_baseline_sentence_says_which_sections_stand_on_it():
    """UX-22's half. A frame nobody can attach to a count is a fact printed
    beside the thing it explains, which is what the four section headings
    already were before round 090."""
    markdown = _render(DIFF_SCOPE)
    sentence = _baseline_sentence(markdown)

    assert "New issues" in sentence and "Resolved issues" in sentence, (
        "the sentence does not name the counts it frames, so a reader has to "
        f"work out which of the four it applies to: {sentence!r}")
    assert markdown.index(sentence) < markdown.index("## New issues"), (
        "a frame printed under the figures it frames is a footnote — the "
        "rule WF-02's fix established for the current run's sentence")


def test_a_baseline_with_only_a_path_count_is_not_called_pages():
    """Round 091's grain rule, one run over, and the easier place to break it.

    A baseline stored before the evidence column has crawled paths and no
    readable-page count at all. Calling those paths "pages" asserts a grain
    nothing established, which is exactly the half of UX-84 that was a wrong
    word rather than a wrong number.
    """
    scope = dict(DIFF_SCOPE)
    del scope["pages_fetched_baseline"]
    del scope["pages_fetched_basis_baseline"]

    sentence = _baseline_sentence(_render(scope))

    assert "2 distinct paths" in sentence, (
        f"the only count the baseline has is a path count: {sentence!r}")
    assert "2 pages" not in sentence, (
        f"a path count stated under the word pages is UX-84: {sentence!r}")


def test_a_comparison_that_cannot_frame_its_baseline_says_so():
    """Every diff stored before this change carries no baseline keys, and the
    counts are printed for those documents too.

    `_diff_scope_lines` already argues this for the current run: a comparison
    prints its counts regardless, so an absent frame is not a fact withheld
    but a figure with nothing holding it. The same reasoning decides this
    case, and the product already has a shape for saying it.
    """
    scope = {k: v for k, v in DIFF_SCOPE.items() if not k.endswith("_baseline")}

    markdown = _render(scope)

    assert not [ln for ln in markdown.splitlines()
                if ln.startswith("Baseline scope:")], (
        "a frame that was not established must not be stated as one")
    assert "TO CONFIRM" in markdown and "baseline" in markdown, (
        "the document neither states the baseline's frame nor says it could "
        "not establish it, so `## New issues` reads as framed when it is not")


# --- the screen, which is the same rule in a second place ------------------

def test_the_compare_screen_states_the_baseline_frame_too():
    """DISCIPLINE rule 3, and the reason it is a rule.

    `CompareView` renders `New (825)` and `Resolved (…)` under a sentence that
    frames the current run, which is the document's defect on a second
    surface — and rule 3's own case is four rounds that each fixed a subset
    and reported success.

    Asserted against a slice of `CompareResult`'s scope declaration and of the
    render, not against the file as one string. CQ-203 is a guard whose three
    assertions were whole-document substring matches, and round 091's own
    tripwire had to be tightened for exactly this reason: `pages_fetched`
    already appears elsewhere in this file on a different payload, so a
    file-wide `in` would pass for the wrong reason.
    """
    source = (Path(__file__).resolve().parents[1]
              / "dashboard" / "src" / "views.tsx").read_text(encoding="utf-8")

    start = source.index("type CompareResult")
    declaration = source[start:source.index("function scopeCount", start)]
    for key in ("pages_crawled_baseline", "pages_fetched_baseline",
                "dimensions_baseline"):
        assert key in declaration, (
            f"CompareResult does not declare {key}, so the screen cannot "
            "render the frame New and Resolved are decided under")

    view = source[source.index("export function CompareView"):]
    assert "Baseline audit ${scopeCount(" in view, (
        "the screen states no baseline frame, or states it without the "
        "shared count helper — which is how the two sentences drift on the "
        "grain rule round 091 established")
    assert "did not report the baseline scope" in view, (
        "a comparison stored before renderer 1.28.0 carries no baseline keys "
        "and its cards are rendered anyway, so the screen must say the frame "
        "is missing rather than leaving the sentence above it to be read as "
        "covering them")

# --- CQ-206, taken at round 104, the deadline its own disposition named -----
#
# CQ-206 was first raised in report 092 and carried by eleven reports. Round
# 103 recorded it as a strict xfail naming round 104 as the deadline, for the
# attribution reason and not for effort: round 103's lever *was*
# `_diff_scope_lines`, so taking CQ-206 in the same commit would have put two
# changes to one function under one lever.
#
# The claim, re-verified again here rather than carried on report 103's word:
# `compare_runs` has exactly two callers, `clauditseo/api/app.py:2310` and
# `clauditseo/reporting/generate.py:330`, both of which call it live and
# discard the diff; the `reports` table
# (`clauditseo/db/migrations/0001_initial.sql:113-121`) holds a `path` to a
# rendered file and no diff column at all. So no comparison is stored
# anywhere, and the population the comments justified the fallback with -
# "every diff stored before this change" - cannot exist. Two populations do:
# a **run**, whose `crawl_evidence` is what a diff can spread from, and a
# **document**, which carries the `RENDERER_VERSION` that wrote it. Every
# corrected comment names one of those two.
#
# The population is walked, not listed - DISCIPLINE rule 3's own words, "a
# hard-coded list of three is how a partial fix passes". The xfail's matcher
# read two hard-coded files, and the grep that opened this lever found the
# same false claim in a third (`clauditseo/persistence/runs.py`) that the
# guard could not see. `check_anchors.source_files` already walks the tree
# for the same reason and is reused rather than copied.
#
# Three things the line-scanning matcher could not see, each fixed here and
# each with a case in the tree that proves it matters:
#
#   - a `/*`-opening line. `views.tsx:1640` carried the claim and started
#     `/*`, which is neither `//` nor `*`, so the guard walked past it.
#   - a docstring. `render.py`'s `_basis_note` and `runs.py`'s `compare_runs`
#     both record the reason in prose that begins no comment line at all.
#   - a sentence split across two wrapped lines, and its converse: two
#     unrelated sentences sharing one line. `render.py:74` pairs "written"
#     with "comparison" across a sentence boundary and is not the defect,
#     while the real claim at `render.py:239` spans a line break. A per-line
#     matcher gets both wrong, which is CQ-110's shape from both sides.

STORAGE = r"(?<![-\w])(stored|persisted|written)(?![-\w])"
SUBJECT = r"(?<![-\w])(diffs?|comparisons?)(?![-\w])"
#: The boundaries on SUBJECT are the same rule STORAGE carries above and
#: for the same reason. Without them `diff` matches inside `different`,
#: so "written by different tools" reads as a storage word governing a
#: diff and any comment containing that ordinary phrase is reported as a
#: defect. Found 2026-09-02 by a docstring that said exactly that.
#: The claim is a storage word *governing* a diff, in either order, with at
#: most one function word between them. Adjacency rather than a bag of words
#: over the sentence, because the sentence-wide version reports two true
#: statements as defects: `runs.py:2703` says "the run stored no evidence, so
#: a diff from such a run says nothing", which attributes the storing to the
#: run and is exactly right, and `runs.py:258` says "nineteen hand-written
#: comparisons", where the storage word is not one. The negative lookbehind
#: on the hyphen is what separates "hand-written" from "written".
CLAIMS_STORAGE = re.compile(
    rf"{SUBJECT}\s+(?:that\s+|which\s+|was\s+|were\s+|is\s+|are\s+)?{STORAGE}"
    rf"|{STORAGE}\s+(?:\w+\s+)?{SUBJECT}", re.I)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_COMMENT = re.compile(r"^(#+:?|//+:?|/\*+|\*+/?)\s?(.*)$")


def _prose(path: Path) -> list[tuple[int, str]]:
    """`(line number, text)` for every run of prose in one source file.

    Comment blocks are joined before they are read, so a sentence that wraps
    is one string rather than two. Python docstrings are collected through
    `ast` rather than by pattern, because a docstring opens no comment token
    and there is nothing to scan for - the parser already knows which strings
    are prose and which are data.
    """
    blocks: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover - the suite would be red first
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node)
                    if doc:
                        blocks.append((getattr(node, "lineno", 1), doc))

    run: list[str] = []
    start: int | None = None
    for n, line in enumerate(text.splitlines(), 1):
        body = line.strip()
        marker = _COMMENT.match(body) if body.startswith(
            ("#", "//", "*", "/*")) else None
        if marker:
            if start is None:
                start = n
            run.append(marker.group(2))
        elif run:
            blocks.append((start or n, " ".join(run)))
            run, start = [], None
    if run:
        blocks.append((start or 1, " ".join(run)))
    return blocks


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text.replace("\n", " "))]


def _found(path: Path) -> list[str]:
    out = []
    for line, text in _prose(path):
        for sentence in _sentences(text):
            if CLAIMS_STORAGE.search(sentence):
                out.append(f"{path.name}:{line}: {sentence}")
    return out


def test_the_matcher_reads_the_shapes_the_line_scanner_could_not(tmp_path):
    """The guard's own guard, watched failing on each shape it was blind to.

    Four cases, three of which the round-103 matcher walked past and one it
    reported wrongly. Built as files rather than asserted against the tree,
    so that fixing the tree cannot make this stop testing the matcher.
    """
    hidden = tmp_path / "hidden.tsx"
    hidden.write_text(
        "/* Every comparison stored before this round carries nothing. */\n"
        "const a = 1;\n", encoding="utf-8")
    assert _found(hidden), "a `/*`-opening line hides the claim"

    doc = tmp_path / "doc.py"
    doc.write_text('def f():\n    """A diff stored before then has no rung."""\n',
                   encoding="utf-8")
    assert _found(doc), "a docstring hides the claim"

    wrapped = tmp_path / "wrapped.py"
    wrapped.write_text("# says it could not establish the frame - which is\n"
                       "# what every comparison stored before this version\n"
                       "# gets.\n", encoding="utf-8")
    assert _found(wrapped), "a sentence split across two lines hides the claim"

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        "# Both keys are absent when the run stored no evidence, so a diff\n"
        "# from such a run says nothing about a page count.\n"
        "# One generator rather than nineteen hand-written comparisons.\n",
        encoding="utf-8")
    assert not _found(innocent), (
        "a true sentence about a stored run, and a hyphenated word that is "
        f"not a storage claim, are reported as defects: {_found(innocent)}")


def test_the_population_is_walked_rather_than_listed():
    """CQ-206's own residue. The round-103 matcher named two files by hand
    and the third carrying the claim was invisible to it, so the walk is
    asserted rather than assumed."""
    walked = {q.relative_to(ROOT).as_posix() for q in ca.source_files(ROOT)}

    for named in ("clauditseo/reporting/render.py",
                  "dashboard/src/views.tsx",
                  "clauditseo/persistence/runs.py"):
        assert named in walked, f"{named} is outside the guard's population"


def test_no_comment_justifies_the_baseline_fallback_with_a_stored_comparison():
    """CQ-206. The reason a branch exists is what the next author acts on.

    Every source file under `check_anchors.SOURCE_ROOTS`, not the two the
    finding happened to anchor to. `tests/` is outside that population for
    the reason `check_anchors` records - a test says what the defect was, and
    this file's own header is the instance.
    """
    offenders = []
    for path in ca.source_files(ROOT):
        for line, text in _prose(path):
            for sentence in _sentences(text):
                if CLAIMS_STORAGE.search(sentence):
                    offenders.append(
                        f"{path.relative_to(ROOT).as_posix()}:{line}: "
                        f"{sentence}")

    assert not offenders, (
        "a comment justifies behaviour by a population of stored "
        "comparisons, and none is stored anywhere - `compare_runs` is called "
        "live by both its callers and the `reports` table holds only a "
        "rendered path. Name the run whose evidence is missing, or the "
        "renderer version that wrote the document (CQ-206):\n  "
        + "\n  ".join(offenders))
