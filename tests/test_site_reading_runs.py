"""Round 052's lever: "is this run a reading of the site" gets one owner.

The question was spelled in twelve places as the literal `kind='audit'`, once
as the deny-list `narrow=kind == "refresh"`, once on the client as
`r.kind === "audit"` — and **not at all** in `site_reports`, `compare_runs` or
the three composite render sites. `create_run`'s own docstring already states
the contract the code did not keep: a verify and a refresh "are excluded from
everything that scores, trends or compares runs, because a composite over a
handful of pages is not comparable with one over the site."

The four findings this closes are one missing predicate seen from four
directions — WF-57 (`site_reports`), WF-60 (`compare_runs`), CQ-104
(`complete_run` deciding it twice with opposite polarities) and UX-38 (the
client asking about status instead). CQ-97 is the fifth: the guard written
last time enumerated *the readers that already carried the filter* rather than
*every reader of the table*, which is why it was green while three readers had
no filter at all. `test_every_per_site_reader_of_audit_runs_asks_the_question`
below enumerates from the table.

**The measurement that settled the `verify` half.** The code comment at the
`narrow` condition said applying it to `verify` was "read off this code rather
than observed", and left it alone pending someone deciding what a verification
should claim. It is observed now. On `data/clauditseo.db`, the eight-page
verification `d4474b38` on `www.acme.com.au` — a 224-page site — moved 22
findings, and **four of the fifteen it cleared were site-scoped**: findings
naming no page at all, cleared because their dimension merely ran. An
eight-page crawl cannot establish a site-wide absence, so refusing to clear is
the correct answer and does not need a product decision.

**The residual, named rather than absorbed.** A verification asked to check a
site-scoped finding can no longer clear it, only leave it open. Closing that
properly means threading the requested fingerprints into `_apply_states` so a
narrow run may clear exactly what it was asked about and nothing else — a
different change with its own consumers, and not folded in here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import AuditResult
from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier
from clauditseo.persistence import repo, runs

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# The enumeration, taken from the table rather than from the filter.
# --------------------------------------------------------------------------

#: Per-site readers of `audit_runs` that legitimately ask no kind question,
#: each with the reason it does not. An allow-list, so a new reader is a
#: failure until someone writes down which side of the line it is on — the
#: opposite of the previous guard, which listed the readers that already had
#: the filter and could therefore only ever pass.
EXEMPT = {
    "clauditseo/api/app.py:_in_flight_for_site": "item 239 step 4: which of "
        "the analyses running now are against this site. An analysis runs "
        "against whatever run it was started on, of any kind, and a pill "
        "that hid one running on a refresh would offer to start it twice",
    "clauditseo/persistence/runs.py:site_states": "item 239 step 4: the date "
        "of each run that changed a state or wrote a finding, for \"superseded "
        "on\". A verify or a refresh clears states too, and its date is the "
        "date the row was overtaken",
    "clauditseo/persistence/latest_view.py:_replay": "item 239: the Latest "
        "View is rebuilt from every run that measured anything - a refresh "
        "and a verify included, each writing only what `runs.measured` says "
        "it measured; the ledger step they take is the live completion's",
    "clauditseo/persistence/repo.py:_delete_site_rows": "item 169: deleting a "
        "site removes every run of it, whatever its kind; a verification or a "
        "refresh left behind would be an orphan the foreign keys refuse",
    "clauditseo/api/app.py:delete_site": "item 169: the delete refuses while "
        "any run is pending or running against the site, of any kind, because "
        "the worker would write into rows the cascade removed",
    "clauditseo/persistence/runs.py:recompute_contract_states": "brief v10 step "
        "AF: the walk over the runs a conforming brief ran against, which "
        "are whichever runs hold its report - a brief may be run against a "
        "verify or a page scan by the operator's own hand, and a walk that "
        "skipped those would call a row fixed that the brief still raised",
    "clauditseo/api/app.py:site_anatomy": "brief v6 steps V1 and V4: the "
        "run the picker names is looked up by id to confirm it belongs to the "
        "site - the picker lists a nav scan (brief v5 step P) and reading "
        "against it is right, V3 refuses running - and the reports index joins "
        "every run of the site, since a report exists on whatever run wrote "
        "it and a pill must open what exists rather than answer 404. Keyed to "
        "the function: both queries are the same question, which run wrote "
        "what, and neither may ask the kind",
    "clauditseo/persistence/runs.py:recompute_expert_states": "an expert "
        "finding is judged by re-running the brief, never by a crawl, and no "
        "narrow kind produces an expert report at all",
    "clauditseo/persistence/runs.py:page_dossier": "one page's own history. A "
        "verification or a refresh that refetched THIS page is real evidence "
        "about it — the narrow-run objection is about generalising to the "
        "site, and a dossier does not",
    "clauditseo/persistence/runs.py:page_facts": "same page, same reason",
    "clauditseo/persistence/runs.py:expert_estimates": "the subject is the "
        "stored brief, not the run: `audit_runs` is reached only to scope "
        "`expert_reports` to one site, which is UX-77's fix and exactly the "
        "case the note below places out of scope — except that this one is "
        "written as a subquery rather than a JOIN, so the enumeration sees it. "
        "Same ground as `recompute_expert_states`: no narrow kind produces an "
        "expert report at all, so the kind predicate would be dead. Written "
        "down as an exemption rather than rewritten as a JOIN to fall outside "
        "the enumeration — a query should not escape the question by changing "
        "shape, and the JOIN form would have entered the tree unexamined",
    "clauditseo/persistence/repo.py:delete_client": "deletion removes every "
        "run of every kind — both queries in it, which is why the key is the "
        "function",
    "clauditseo/persistence/runs.py:list_runs": "the run list is the site's "
        "whole history; hiding a verification from it would make the crawl it "
        "performed unauditable. The client filters it with `isSiteReading`",
    "clauditseo/api/app.py:site_detail": "same list, same reason as list_runs",
    "clauditseo/persistence/runs.py:site_reports": "the `bare` query feeds the "
        "`runs` payload, which keeps every kind on purpose — each row carries "
        "`kind` so the screen can decide — and `order`, the site-reading half, "
        "filters it in Python 25 lines below. Exempt only once `_ASKS_KIND` "
        "stopped counting the column in the SELECT list as the question; "
        "before that it passed while asking nothing, which is CQ-107. The "
        "Python filter has its own net: "
        "test_site_reports_measures_staleness_against_readings_of_the_site",
    "clauditseo/reporting/generate.py:adopt_orphans": "not a per-site read at "
        "all, on the same ground the docstring below gives for `compare_runs`: "
        "the id is already known — it was parsed out of the document's own "
        "text — and `site_id` is here as an ownership check, so a hex string "
        "that is not this site's run is discarded rather than trusted. Adding "
        "the kind predicate would be actively wrong: the register records "
        "which runs the document says it covers, and a document generated "
        "against a verification names that verification. Dropping it would "
        "delete provenance the artefact itself carries",
}

#: A query is in scope when `audit_runs` is what it selects FROM — the run is
#: the subject — and it constrains `site_id`.
#:
#: **The limitation, stated rather than left to be discovered.** Queries where
#: `audit_runs` appears only in a JOIN are out of scope: every one of them
#: joins through it to reach `expert_reports` or `findings`, using the run
#: purely to scope rows to a site. They are not asking "which runs does this
#: site have", which is the question the predicate answers. A narrow kind
#: cannot produce an expert report — `verify` and `refresh` run no analysts —
#: so today the two readings coincide; if that ever stops being true, this
#: line is where it has to change.
_FROM_RUNS = re.compile(r"\bFROM\s+audit_runs\b", re.I)
_PER_SITE = re.compile(r"\bsite_id\s*=\s*\?", re.I)
#: `\bkind` and not `\bkind\b`. The owner is called `kind_is_site_reading()`
#: and `_` is a word character, so the closing boundary made every query that
#: asks the question *through its owner* read as one that never asks it — the
#: guard failing on the fix, which is the shape of wrongness that gets a
#: correct fix reverted.
_ASKS_KIND = re.compile(r"\bkind", re.I)
#: …and searched only from the first `FROM` onward, which is CQ-107. `\bkind`
#: anywhere in the statement is satisfied by *selecting* the column:
#: `site_reports`' `bare` query reads `SELECT id, …, status, kind FROM
#: audit_runs WHERE site_id=?` and passed this guard with no kind filter in it
#: at all. Naming a column is not asking a question about it. A filter can only
#: live from `FROM` onward — in a join, a `WHERE` or a `HAVING` — so that is
#: the region searched, and a `SELECT` list is excluded by construction rather
#: than by a list of exceptions.
#:
#: **What this half of CQ-107 is, given the other half is disproved.** The
#: report also said deleting `site_reports`' Python filter
#: `if is_site_reading(r["kind"])` leaves the suite green. Measured this round
#: by deleting it and running the gate's own command: `1 failed, 1254 passed`,
#: the failure being `test_site_reports_measures_staleness_against_readings_of_the_site`
#: below. The regression net does exist. What was missing is that *this* guard
#: could not see the query, so the next reader written the same way would pass
#: it — which is a hole in the enumeration, not in the net.
_FROM_ONWARD = re.compile(r"\bFROM\b", re.I)


def _predicate_region(sql: str) -> str:
    """The part of a query a filter could be written in.

    Everything before the first `FROM` is the projection. `ORDER BY kind`
    would read as a filter here and does not exist in this codebase; if one is
    ever written, this is the line that grows a clause rather than the guard
    growing an exemption.
    """
    m = _FROM_ONWARD.search(sql)
    return sql[m.end():] if m else sql


#: A comment beside a query that legitimately spans every run kind. The
#: reason follows the colon and is read by a person, not by this file.
#:
#: **Why a marker and not a line number** (item 136p). Three EXEMPT keys were
#: addressed `file:function:line`. A line number is not an address of a query;
#: it is an address of a position, and the position moves whenever anything
#: above it does. The `current_state` entry recorded SEVEN repairs of its own
#: drift - 3286, 3437, 3492, 3508, 3512, 3526 ... - and took three more in one
#: session, none of them for a change to the query or to the function holding
#: it. It argued that reddening is the honest failure mode, and it is; the
#: objection is not that the failure is dishonest but that it is constant, and
#: a guard that cries on unrelated edits is one somebody eventually re-keys
#: without reading.
#:
#: And the drift is not always loud. `app.py:site_anatomy:2468` had already
#: landed on nothing - the query it named now sits at 2699 - so it matched no
#: query, waved through exactly nothing, and read as though it were working.
#: A function-level key for the same file was doing the actual work.
#:
#: This is CQ-242 one layer down: the repo already forbids a COMMENT citing
#: its own conventions by line, for this reason. A marker travels with the
#: query because it is attached to it, and stays precise to ONE query, which
#: a function-level exemption is not.
NEWLINE = chr(10)

GUARD_EXEMPT_MARKER = "guard-exempt(site-reading):"


def _marked(path: Path, lineno: int, span: int = 40) -> str | None:
    """The exemption marker governing the query starting at `lineno`.

    Searched upward, which is where a reader writes a note about the call
    below it. `span` is generous because these queries are a stack of
    literals under a comment.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    for i in range(max(0, lineno - span), min(lineno, len(lines))):
        if GUARD_EXEMPT_MARKER in lines[i]:
            return lines[i].split(GUARD_EXEMPT_MARKER, 1)[1].strip()
    return None


def _sql_strings(path: Path) -> list[tuple[int, str]]:
    """Every string constant in `path` that reads `audit_runs`.

    Implicit concatenation is why this is an AST walk and not a regex over
    source. The queries here are written as a stack of literals, so raw text
    would see `WHERE site_id=?` and the `AND kind='audit'` line as two
    separate strings and report every filtered query as unfiltered. CPython
    folds an adjacent run into one `Constant`, or into one `JoinedStr` where a
    fragment is an f-string — and in the second case the fragments are *also*
    `Constant` children of it, so they are consumed here rather than reported
    on their own. That double-count was this guard's first draft, and it
    named eighteen queries that do carry the filter.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    consumed: set[int] = set()
    joined: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # The interpolated expression's own source counts as part of
            # the query. `AND {runs.kind_is_site_reading()}` contains no
            # literal `kind` once the placeholder is dropped, so a guard
            # reading constants alone reports the queries that ask the
            # question *through its owner* as the ones that do not ask it —
            # which is what this reported the first time it ran against the
            # fixed code.
            text = "".join(
                p.value if isinstance(p, ast.Constant) and isinstance(p.value, str)
                else (ast.unparse(p.value) if isinstance(p, ast.FormattedValue) else "")
                for p in node.values)
            joined.append((node.lineno, text))
            for child in ast.walk(node):
                consumed.add(id(child))

    out = [(ln, t) for ln, t in joined if _FROM_RUNS.search(t)]
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in consumed and _FROM_RUNS.search(node.value)):
            out.append((node.lineno, node.value))
    return sorted(out)


def _enclosing(path: Path, lineno: int) -> str:
    """The innermost function a line sits in. Smallest enclosing range, not
    the last one the walk happens to visit: `why_not` lives inside
    `compare_runs`, and naming the outer one would let an EXEMPT entry
    discharge a nested query nobody looked at."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    best, span = "<module>", None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= lineno <= end and (span is None
                                                 or end - node.lineno < span):
                best, span = node.name, end - node.lineno
    return best


def test_no_exemption_is_addressed_by_line_number(*, _keys=None):
    """The rule, stated as a test so it cannot be reintroduced by habit.

    A line number addresses a position, not a query, and the position moves
    whenever anything above it does. Item 136p: use a `guard-exempt` marker
    beside the query, or a function-level key where the whole function
    legitimately spans every kind.
    """
    import re

    bad = [k for k in (_keys or {**EXEMPT, **LIST_RUNS_CALLERS_EXEMPT})
           if re.search(r":\d+$", k)]
    assert not bad, (
        "these exemptions are keyed by line number and will redden on an "
        f"unrelated edit above them: {bad}. Put a "
        f"`{GUARD_EXEMPT_MARKER} <reason>` comment beside the query instead.")


def test_inserting_a_function_above_an_exempt_query_reddens_nothing(tmp_path):
    """The regression lock the re-keying is for.

    Drives the guard's own enumeration over a COPY of `runs.py` with a no-op
    function spliced in at the top, which is exactly what the three repairs
    in one session were: `prior_run` inserted, `_page_path` inserted,
    `prior_content_hashes` deleted. None touched `current_state` and each
    reddened it.

    The copy keeps the real file's name so `_enclosing` and the marker
    search read the same shapes they read in the product.
    """
    src = (ROOT / "clauditseo" / "persistence" / "runs.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    # After the imports, so the splice cannot land inside a docstring.
    cut = max(i for i, l in enumerate(lines[:200])
              if l.startswith("import ") or l.startswith("from ")) + 1
    spliced = (lines[:cut]
               + ["", "", "def _a_function_nobody_asked_for() -> None:",
                  '    """Twenty lines of nothing, to move every line below."""',
                  *["    pass" for _ in range(16)], "", ""]
               + lines[cut:])
    target = tmp_path / "runs.py"
    target.write_text(NEWLINE.join(spliced) + NEWLINE, encoding="utf-8")

    flagged = []
    for lineno, sql in _sql_strings(target):
        if not _PER_SITE.search(sql):
            continue
        if _ASKS_KIND.search(_predicate_region(sql)):
            continue
        if _marked(target, lineno):
            continue
        # Function-level keys still apply: they are stable under insertion,
        # which is the whole point, and this clause is only about the
        # positional ones. Keyed under the REAL path, since that is what the
        # dict names and the copy is only a copy.
        fn = _enclosing(target, lineno)
        if f"clauditseo/persistence/runs.py:{fn}" in EXEMPT:
            continue
        flagged.append(f"{lineno} in {fn}()")

    assert not flagged, (
        "moving every line of `runs.py` down by twenty reddened the guard, "
        f"so an exemption is still positional: {flagged}")


def test_every_per_site_reader_of_audit_runs_asks_the_question():
    """CQ-97, widened. The previous guard named `watch_changes`,
    `current_state` and the report currency index — the three readers that
    already carried the filter — so it asserted that the answer was still the
    answer. It could not fail.

    Watched failing before the lever, naming three readers with no kind
    question in them: `site_reports` (WF-57), and the two in `app.py` that
    pick a site's latest run to hang link suggestions and analyst runs on.

    It does **not** catch WF-60 — `compare_runs` is handed two run ids and
    reads them by `id IN (?, ?)`, so it is not a per-site read at all. That
    one is caught by its own driven test below, and the split is recorded
    here rather than papered over: an enumeration that could see it would
    have to reason about callers, not queries.
    """
    unfiltered = []
    for path in sorted((ROOT / "clauditseo").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXEMPT:
            continue
        for lineno, sql in _sql_strings(path):
            if not _PER_SITE.search(sql):
                continue
            if _ASKS_KIND.search(_predicate_region(sql)):
                continue
            fn = _enclosing(path, lineno)
            if f"{rel}:{fn}" in EXEMPT:
                continue
            # A marker beside the query itself: precise to one query, unlike
            # a function key, and immune to line drift, unlike the line keys
            # this replaced (item 136p).
            if _marked(path, lineno):
                continue
            unfiltered.append(f"{rel}:{lineno} in {fn}(): "
                              f"{' '.join(sql.split())[:110]}")

    assert not unfiltered, (
        "these queries read one site's runs without asking which kinds are a "
        "reading of that site, so a verification or a refresh is counted as "
        "one:\n  " + "\n  ".join(unfiltered) +
        "\n\nAdd the predicate, or add the query to EXEMPT with the reason "
        "it legitimately spans every kind.")


#: Callers of `list_runs` that legitimately want every kind, each with the
#: reason. Same shape and same discipline as `EXEMPT` above, and a separate
#: table because it keys on a *call site* rather than on a query.
LIST_RUNS_CALLERS_EXEMPT = {
    "clauditseo/api/app.py:client_detail": "the client list's `run_count` is "
        "how many audits ran, whatever their scope - a page scan ran - so it "
        "asks the kind alone (`is_site_reading(r['kind'])`, in the loop) and "
        "the score beside it asks `reads_site`, since brief v6 step V2 made "
        "the site-reading predicate scope-aware",
    "clauditseo/persistence/runs.py:site_readings": "the kind-aware sibling "
        "is defined by filtering this one — the single call that is allowed "
        "to be unfiltered, because filtering it is what the function is",
    "clauditseo/api/app.py:site_detail": "the site's own screen shows its "
        "whole history; hiding a verification from the runs table would make "
        "the crawl it performed unauditable. Each row carries `kind` and the "
        "client filters with `isSiteReading` — the reason `list_runs` itself "
        "is EXEMPT above, discharged by a filter that demonstrably exists",
}


def test_every_caller_of_list_runs_asks_the_question():
    """CQ-105. The SQL enumeration above walks string constants, so it can see
    a reader that writes its own `SELECT … FROM audit_runs` and cannot see one
    that calls `list_runs()`. Round 052 gave the rule an owner for SQL and
    left six Python consumers reading the unfiltered list under a green guard
    — and `list_runs` is itself waved through by an `EXEMPT` entry whose
    stated reason, *"The client filters it with `isSiteReading`"*, is true of
    `site_detail` and false of all six, none of which reaches a client.

    So the two guards enumerate two different things and neither is redundant:
    that one asks "does this query filter", this one asks "does this caller
    read the filtered list". The rule here is deliberately blunt — any call to
    `list_runs` from inside `clauditseo/` is opting out of the site-reading
    rule and owes a written reason — because "did the caller filter it
    afterwards" is the judgement that produced the six.

    Watched failing before the lever, naming `client_detail`, `chat._trend`,
    `chat._latest`, `generate`'s trend feed, `run_adaptive`'s baseline pick
    and `_query_history`.
    """
    callers = []
    for path in sorted((ROOT / "clauditseo").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            # `runs.list_runs(...)`, `runs_repo.list_runs(...)` and a bare
            # `list_runs(...)` inside the owning module are the same call.
            name = (fn.attr if isinstance(fn, ast.Attribute)
                    else fn.id if isinstance(fn, ast.Name) else None)
            if name != "list_runs":
                continue
            enclosing = _enclosing(path, node.lineno)
            key = f"{rel}:{enclosing}"
            if key in LIST_RUNS_CALLERS_EXEMPT:
                continue
            callers.append(f"{key} (line {node.lineno})")

    assert not callers, (
        "these callers read a site's whole run history where they mean the "
        "runs that speak for the site, so a verification or a refresh is "
        "counted as one:\n  " + "\n  ".join(callers) +
        "\n\nCall runs.site_readings() instead, or add the call site to "
        "LIST_RUNS_CALLERS_EXEMPT with the reason it wants every kind.")


def test_the_kind_question_is_not_spelled_as_a_literal_anywhere():
    """CQ-104's other half. The rule was `kind='audit'` in twelve SQL strings
    and `kind == "audit"` in one branch; a fourth kind means finding all
    thirteen. One owner means one place to edit, which is only true if the
    literal is gone from everywhere else."""
    literal = re.compile(r"""kind\s*(?:=|==)\s*['"]audit['"]""")
    offenders = []
    for path in sorted((ROOT / "clauditseo").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel == "clauditseo/persistence/runs.py":
            continue                      # the owner defines it
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue                  # prose about the rule is not the rule
            if re.search(r"""`kind\s*(?:=|==)\s*['"]audit['"]`""", line):
                continue                  # a docstring citing the old spelling
            if literal.search(line):
                offenders.append(f"{rel}:{i}: {line.strip()[:100]}")
    assert not offenders, (
        "the run-kind rule is spelled out here rather than asked of its "
        "owner:\n  " + "\n  ".join(offenders))


# --------------------------------------------------------------------------
# What the predicate changes, driven.
# --------------------------------------------------------------------------

DIMS = ["ONP"]


@pytest.fixture
def site(tmp_path):
    conn = connect(tmp_path / "kinds.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    return conn, repo.create_site(conn, client, "https://x.test/")


def _page_finding(path: str) -> Finding:
    return Finding(dimension="ONP", check_id="img-alt-missing",
                   severity=Severity.MEDIUM, summary=f"alt missing on {path}",
                   subject=path, affected_urls=[f"https://x.test{path}"],
                   evidence={}, confidence=Confidence.HIGH, recommendation="")


def _site_finding() -> Finding:
    """Names no page — the shape whose clearance the `narrow` rule governs."""
    return Finding(dimension="ONP", check_id="site-wide-thing",
                   severity=Severity.MEDIUM, summary="a site-wide claim",
                   subject="site", affected_urls=[], evidence={},
                   confidence=Confidence.HIGH, recommendation="")


def _store(conn, site_id, findings, crawled, kind="audit", composite=None):
    """`composite` is optional because most tests here are about state
    transitions, which do not need one. The trend tests do: `site_trend` reads
    `metric_snapshots`, so a run with no composite puts no point on the chart
    and the count-versus-table question cannot arise."""
    run_id = runs.create_run(conn, site_id, DIMS, "T2", kind=kind)
    runs.complete_run(conn, run_id, AuditResult(
        site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=DIMS,
        findings=findings, crawled_paths=set(crawled),
        composite_score=composite))
    return run_id


def _state(conn, site_id, fp):
    row = conn.execute(
        "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
        (site_id, fp)).fetchone()
    return row["state"] if row else None


def test_a_verification_may_not_clear_a_site_scoped_finding(site):
    """The measured case, reduced to a fixture.

    Watched failing before the lever: the site-scoped finding came back
    `fixed` from a two-page verification, exactly as the four on
    `www.acme.com.au` did.
    """
    conn, site_id = site
    wide, narrow_page = _site_finding(), _page_finding("/a")
    _store(conn, site_id, [wide, narrow_page], ["/a", "/b", "/c"])
    assert _state(conn, site_id, wide.fingerprint) == "open"

    # A verification re-crawls two pages for the same dimension and no longer
    # raises either finding.
    _store(conn, site_id, [], ["/a", "/b"], kind="verify")

    assert _state(conn, site_id, narrow_page.fingerprint) == "fixed", (
        "the verification refetched /a and the finding was gone, which is "
        "the whole point of a verification")
    assert _state(conn, site_id, wide.fingerprint) == "open", (
        "a two-page verification declared a site-wide finding fixed on "
        "evidence nobody gathered")


def test_a_fourth_run_kind_is_narrow_on_the_day_it_is_added(site):
    """CQ-104. `complete_run` wrote the rule twice eight lines apart with
    opposite polarities — `narrow=kind == "refresh"` (a deny-list of one) and
    `if kind == "audit"` (an allow-list), under a comment arguing for the
    second. A kind nobody has thought about must inherit the careful answer.

    Watched failing before the lever: the unknown kind cleared the site-scoped
    finding and wrote a point onto the site's trend.
    """
    conn, site_id = site
    wide = _site_finding()
    _store(conn, site_id, [wide], ["/a", "/b"])
    before = len(runs.site_trend(conn, site_id))

    _store(conn, site_id, [], ["/a"], kind="sweep")   # a kind nothing knows

    assert _state(conn, site_id, wide.fingerprint) == "open", (
        "an unrecognised run kind cleared a site-scoped finding")
    assert len(runs.site_trend(conn, site_id)) == before, (
        "an unrecognised run kind put a point on the site's trend")


def test_site_reports_measures_staleness_against_readings_of_the_site(site):
    """WF-57, the finding re-executed against the live database this round:
    `newest_run_id` was the verification `d4474b38`, `stale_analyses` was 24,
    and the newest run row read `{"tier": "T2", "score": 86.2}` above the
    224-page audit's 70.52.

    Watched failing before the lever on all three counts.
    """
    conn, site_id = site
    audit = _store(conn, site_id, [_page_finding("/a")], ["/a", "/b"])
    verify = _store(conn, site_id, [], ["/a"], kind="verify")

    body = runs.site_reports(conn, site_id)

    assert body["newest_run_id"] == audit, (
        "a two-page verification is the site's newest audit, so every stored "
        "analysis reads as superseded by it")
    kinds = {r["id"]: r.get("kind") for r in body["runs"]}
    assert kinds.get(verify) == "verify", (
        "the runs payload carries no kind, so the client cannot tell a "
        "reading of the site from a named handful: " + repr(body["runs"]))
    assert kinds.get(audit) == "audit"


def test_compare_runs_does_not_resolve_a_site_level_finding_against_a_narrow_run(site):
    """WF-60. `why_not` asks three questions — blocked, dimension, page — and
    a site-level finding names no page, so a run that merely ran the dimension
    answers all three. Executed against the live database this round, the
    T3 audit against the eight-page verification returned `resolved: 15`.

    Watched failing before the lever: the site-level finding came back under
    `resolved` with no qualifier.
    """
    conn, site_id = site
    wide, page = _site_finding(), _page_finding("/a")
    a = _store(conn, site_id, [wide, page], ["/a", "/b", "/c"])
    b = _store(conn, site_id, [], ["/a"], kind="verify")

    diff = runs.compare_runs(conn, a, b)
    resolved = {f["fingerprint"] for f in diff["resolved"]}
    not_rechecked = {f["fingerprint"]: f["not_rechecked_reason"]
                     for f in diff["not_rechecked"]}

    assert wide.fingerprint not in resolved, (
        "a site-wide finding is reported resolved by a run that read one page")
    assert wide.fingerprint in not_rechecked, (
        "the site-wide finding vanished from both buckets")
    # `_reason` returns parts, not a sentence — persistence states the facts
    # and each surface formats them.
    assert "site" in (not_rechecked[wide.fingerprint] or {}).get("lead", ""), (
        "the reason does not say why: "
        f"{not_rechecked[wide.fingerprint]!r}")
    assert page.fingerprint in resolved, (
        "the verification refetched /a and the finding was gone — that half "
        "must still read as resolved")


# --------------------------------------------------------------------------
# The client half. `tsc --noEmit` is a CI step, so a type is a gate.
# --------------------------------------------------------------------------

API_TS = (ROOT / "dashboard" / "src" / "api.ts").read_text(encoding="utf-8")
COMPONENTS_TSX = (ROOT / "dashboard" / "src" / "components.tsx").read_text(
    encoding="utf-8")


def test_the_client_has_one_owner_for_the_question_too():
    """UX-38. `hasScore` is exhaustive over six statuses and mentions no
    kind, and `completedAudits` spelled `r.kind === "audit"` inline — so the
    predicate existed on the client as a literal in one function and nowhere
    else. Three render sites print a composite from status alone."""
    assert "export function isSiteReading" in API_TS, (
        "the client has no owner for 'is this run a reading of the site'")
    # Everything except the owner's own body and the prose describing it.
    # The same carve-out the Python half makes for a docstring citing the old
    # spelling: a rule has to be written down once, and the place it is
    # written down is not a violation of itself.
    owner = re.search(r"export function isSiteReading[^}]*\}", API_TS)
    assert owner, "isSiteReading is not a function declaration any more"
    body = set(range(API_TS[:owner.start()].count("\n") + 1,
                     API_TS[:owner.end()].count("\n") + 2))
    literals = [f"{i}: {ln.strip()}" for i, ln in
                enumerate(API_TS.splitlines(), 1)
                if i not in body
                and not ln.lstrip().startswith("*")
                and not ln.lstrip().startswith("/**")
                and re.search(r"""kind\s*===\s*['"]audit['"]""", ln)]
    assert not literals, (
        "api.ts still spells the rule out rather than asking its owner:\n  "
        + "\n  ".join(literals))


#: The component that owns the Score column's whole branch since UX-42, and
#: therefore owns the question on behalf of the sites that render it.
COMPOSITE_OWNER = "RunScore"


@pytest.mark.parametrize("path,marker", [
    ("dashboard/src/views.tsx", "isSiteReading"),
    ("dashboard/src/reports.tsx", "isSiteReading"),
])
def test_the_composite_render_sites_ask_about_kind(path, marker):
    """The three sites the report names — `views.tsx:514`, `reports.tsx:297`
    and `:364` — each printed a composite gated on `hasScore` alone.

    **The stated limitation this carried is out of date and is corrected
    rather than repeated.** It read "the rendered sweep has no fixture site
    carrying a verification, and building one is a separate change". That
    change landed at `99b0e69`: the sweep now seeds a verification between
    two audits, and `test_a11y_rendered.py` drives both consequences —
    the Compare column's pairing and the caption that says what a narrow run
    is. This source check is no longer the only evidence, which is the
    outcome it was asking for. What still makes it more than a spelling test
    is that the payload half is driven above — `site_reports` is asserted to
    carry `kind` against a real stored run — and `tsc --noEmit` (a CI step)
    refuses the render sites if that field is not on the type.

    **Asked directly, or asked through the component that owns the answer.**
    UX-42 moved the whole Score-column branch into `RunScore`, because three
    tables across two screens had each written it out and all three explained
    themselves in a `title`. `reports.tsx` then stopped naming
    `isSiteReading` — it delegates — and this guard failed on a file that had
    become *more* compliant, not less: the hand-kept `(path, marker)` pair
    below is a list of the shape the answer took in October, which is the
    defect CQ-105 and CQ-83 both are.

    Widened rather than weakened, and it can still fail three ways: drop the
    `RunScore` call from a render site and that site fails; let `RunScore`
    stop asking `isSiteReading` and every delegating site fails at once; add
    a fourth composite site that does neither and it is uncovered — which is
    the residual, named rather than absorbed, and is the same residual the
    two-element list always had.
    """
    text = (ROOT / path).read_text(encoding="utf-8")
    delegates = COMPOSITE_OWNER in text
    assert marker in text or delegates, (
        f"{path} prints a composite without asking whether the run is a "
        f"reading of the site — neither {marker} nor {COMPOSITE_OWNER}")
    if delegates:
        assert marker in COMPONENTS_TSX, (
            f"{path} delegates the question to {COMPOSITE_OWNER}, which does "
            f"not ask it: {marker} is absent from components.tsx, so the "
            "delegation is to nothing and every site that relies on it is "
            "printing an ungated composite")


# --------------------------------------------------------------------------
# Round 054: the same rule at the Python boundary, driven where it is read.
# --------------------------------------------------------------------------

def test_site_readings_is_list_runs_without_the_narrow_kinds(site):
    """The sibling itself. `list_runs` keeps every kind on purpose, so the
    difference between the two is the whole of the rule at this boundary."""
    conn, site_id = site
    audit = _store(conn, site_id, [_page_finding("/a")], ["/a", "/b"])
    verify = _store(conn, site_id, [], ["/a"], kind="verify")

    assert {r["id"] for r in runs.list_runs(conn, site_id)} == {audit, verify}, (
        "the site's own history must still show the verification, or the "
        "crawl it performed becomes unauditable")
    assert [r["id"] for r in runs.site_readings(conn, site_id)] == [audit]


def test_the_client_screen_reads_the_latest_audit_not_the_latest_run(site):
    """WF-63, the measurement that named it: `/api/overview` answered 70.52
    and `/api/clients/{id}` answered 86.2 for `www.acme.com.au` on one page
    load, because this route picked the newest run of any kind.

    Watched failing before the lever on both figures: `latest_score` was the
    verification's and `run_count` was 2.
    """
    from clauditseo.persistence import repo as repo_mod

    conn, site_id = site
    audit = _store(conn, site_id, [_page_finding("/a")], ["/a", "/b"])
    _store(conn, site_id, [], ["/a"], kind="verify")

    site_row = repo_mod.get_site(conn, site_id)
    client_id = site_row["client_id"]

    # The route's own two lines, not a paraphrase of them: `client_detail`
    # takes the head of its scored list and its length.
    scored = [r for r in runs.site_readings(conn, site_id)
              if r["status"] in runs.SCORED_STATUSES]
    assert [r["id"] for r in scored] == [audit], (
        "the client screen's 'Latest score' is the newest run of any kind, so "
        "a verification's composite renders as the site's standing score")
    assert len(scored) == 1, (
        "the client screen counts verifications as audits beside that score")
    assert client_id




def test_the_trend_deliverable_count_agrees_with_its_own_table(site):
    """UX-41, and the cohort finding it re-found: carried in audit reports from
    019 to 036 as "trend run count disagrees with its own table", then not
    re-found for sixteen reports, then measured again this round on
    `www.acme.com.au` — the sentence said 5 and the table had 4 rows.

    Both feeds are rendered here, so the defect and its absence sit in one
    test. `list_runs` is what `generate` passed before the lever;
    `site_readings` is what the caller guard above now requires it to pass.
    """
    from clauditseo.reporting.render import render_trend_report

    conn, site_id = site
    _store(conn, site_id, [_page_finding("/a")], ["/a", "/b"], composite=70.5)
    _store(conn, site_id, [], ["/a"], kind="verify", composite=86.2)

    trend = runs.site_trend(conn, site_id)
    assert len(trend) == 1, (
        "only the audit should have put a point on the trend — round 052")

    before, _ = render_trend_report({"domain": "x.test"}, trend,
                                    runs.list_runs(conn, site_id), "client")
    assert "Completed runs on record: 2 " in before, (
        "the pre-lever feed no longer reproduces the finding, so this test "
        "has stopped measuring it")

    after, _ = render_trend_report({"domain": "x.test"}, trend,
                                   runs.site_readings(conn, site_id), "client")
    assert "Completed runs on record: 1 " in after, (
        "an eight-page verification is counted as an audit in a client's "
        "document:\n" + after.split("\n\n")[1])
    assert "one row per composite score" not in after, (
        "the count and the table now agree, so there is nothing to reconcile "
        "and the clause should not be printed")


def test_the_trend_deliverable_explains_a_run_it_cannot_plot(site):
    """The other cause, and the reason the count is not simply filtered down
    to match the table. Report 036 named this one — a *blocked* audit, real
    history with no composite to plot. Dropping it would hide that an audit
    was attempted, so the sentence explains the difference instead.
    """
    from clauditseo.reporting.render import render_trend_report

    conn, site_id = site
    _store(conn, site_id, [_page_finding("/a")], ["/a", "/b"], composite=70.5)
    _store(conn, site_id, [], ["/c"])          # an audit that scored nothing

    trend = runs.site_trend(conn, site_id)
    feed = runs.site_readings(conn, site_id)
    assert len(trend) == 1 and len(feed) == 2, (
        "the fixture no longer produces a reading with no point on the trend")

    markdown, _ = render_trend_report({"domain": "x.test"}, trend, feed,
                                      "client")

    assert "Completed runs on record: 2 " in markdown
    assert "one row per composite score" in markdown, (
        "the sentence states 2 above a one-row table and nothing on the page "
        "reconciles them:\n" + markdown.split("\n\n")[1])
    assert "1 (source: engine, confidence: high) of these runs produced none" \
        in markdown, ("the reconciling figure is a measurement and entered "
                      "prose without its provenance")
