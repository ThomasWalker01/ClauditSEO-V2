"""WF-101 / Q-21. A finding that describes the audit is not a defect, so it
cannot relapse.

The provenance invariant *requires* a run to raise its own scope limits as
findings — "Sitemap coverage not assessed, this audit was scoped to the
navigation tier". Once raised, each is a row in `findings` with a fingerprint,
a state, and every transition the state machine offers. So a narrower run
re-raised the statement that it was narrower, and `_apply_states` recorded
that as a regression of a fixed defect: on 24 August 2026 the 24-page verify
of `www.acme.com.au` moved nine findings `fixed -> regressed` and two of the
nine were statements about that run's own narrowness, against a standing set
of 31 regressions of which 6 were `info`.

The operator's answer (Q-21, 2026-08-25) picked the exclusion and named the
mechanism with it: *"marked at emission ... carry an explicit flag from the
emitter rather than inferring from severity (severity == info is not the
test)"*. Both halves are guarded here — the transition below, and the flag's
membership in `test_the_flag_is_carried_by_the_emitter_not_inferred`.

What must NOT move is the other side, and it is asserted in the same run as
the fix rather than in a separate test: an ordinary defect re-raised by the
same crawl still regresses. A blanket suppression would satisfy every
assertion about scope statements and destroy the feature.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import AuditResult
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier
from clauditseo.persistence import repo, runs

ROOT = Path(__file__).resolve().parents[1]
DIMS = ["TEC"]


def _scope_note() -> Finding:
    """The real one, copied in shape from `modules/tec.py`."""
    return Finding(dimension="TEC", check_id="unreachable-not-assessed",
                   severity=Severity.INFO,
                   summary="Reachability not assessed - this audit was "
                           "scoped to the navigation tier.",
                   subject="unreachable", affected_urls=[],
                   scope_statement=True)


def _defect() -> Finding:
    """A site-scoped defect that names no page either, so the two differ in
    exactly one thing: the flag. Were the assertion below passing because of
    the page rule rather than because of the flag, this one would pass too."""
    return Finding(dimension="TEC", check_id="robots-missing",
                   severity=Severity.MEDIUM, summary="No robots.txt.",
                   subject="robots", affected_urls=[])


def _result(findings: list[Finding]) -> AuditResult:
    return AuditResult(
        site=Site(domain="scope.test"), tier=Tier.T2, dimensions=DIMS,
        findings=findings,
        subscores={"TEC": SubScore(dimension="TEC", score=80.0, weight=1.0)},
        composite_score=80.0, crawled_paths={"/"})


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "scope.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Scope Co")
    site_id = repo.create_site(conn, client, "scope.test")
    yield conn, site_id
    conn.close()


def _run(conn, site_id, findings, *, kind="audit") -> str:
    run_id = runs.create_run(conn, site_id, DIMS, "T2", kind=kind)
    runs.complete_run(conn, run_id, _result(findings))
    return run_id


def _state(conn, site_id, finding: Finding) -> str | None:
    row = conn.execute(
        "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
        (site_id, finding.fingerprint)).fetchone()
    return row["state"] if row else None


# --- the transition ---------------------------------------------------------

def test_a_scope_statement_re_raised_after_being_cleared_is_not_a_regression(db):
    """The measured case, in three runs: raise, clear, re-raise."""
    conn, site_id = db
    note, defect = _scope_note(), _defect()

    _run(conn, site_id, [note, defect])
    assert _state(conn, site_id, note) == "open", "precondition: it was raised"
    assert _state(conn, site_id, defect) == "open"

    _run(conn, site_id, [])                      # a wider run says neither
    assert _state(conn, site_id, note) == "fixed", (
        "precondition: the statement has to reach `fixed` for the transition "
        "this test is about to be reachable at all")
    assert _state(conn, site_id, defect) == "fixed"

    _run(conn, site_id, [note, defect])          # a narrower run raises both
    assert _state(conn, site_id, note) == "open", (
        "a scope statement re-raised by a narrower crawl was recorded as a "
        "regression of a fixed defect - nothing regressed, a smaller crawl "
        "looked at less")
    assert _state(conn, site_id, defect) == "regressed", (
        "the other side, and the one that must not move: an ordinary defect "
        "re-raised by the same run is still a regression. If this fails the "
        "fix is a blanket suppression, not the rule Q-21 answered")


def test_a_scope_statement_already_recorded_as_regressed_heals(db):
    """The rows the defect had already moved before it was found.

    Six standing `info` regressions on the operator's site were written by the
    unfixed code. A rule stated as "does not take this edge" would leave every
    one of them stuck in `regressed` for good, because nothing else ever moves
    a re-emitted finding out of that state - right about the future and
    permanently wrong about the count on the screen.
    """
    conn, site_id = db
    note = _scope_note()
    _run(conn, site_id, [note])
    conn.execute("UPDATE finding_states SET state='regressed'"
                 " WHERE site_id=? AND fingerprint=?",
                 (site_id, note.fingerprint))
    conn.commit()

    _run(conn, site_id, [note])
    assert _state(conn, site_id, note) == "open"


def test_an_operator_decision_on_a_scope_statement_is_still_never_moved(db):
    """`accepted-risk` outranks every rule a run derives, this one included."""
    conn, site_id = db
    note = _scope_note()
    _run(conn, site_id, [note])
    runs.set_state(conn, site_id, note.fingerprint, "accepted-risk")
    _run(conn, site_id, [note])
    assert _state(conn, site_id, note) == "accepted-risk"


# --- the mechanism ----------------------------------------------------------

#: Emitters whose `check_id` declares a non-assessment but which are NOT scope
#: statements, each with the reason. The reason is the same one in both: the
#: finding appears because of what the PAGE contains, not because of how the
#: run was made - so a page that was server-rendered and stopped being so is a
#: real regression and must still fire. Excluding them costs nothing the
#: operator asked for; including them would silence an alarm about the site.
NOT_A_SCOPE_STATEMENT = {
    # Item 215: several entity @ids and none evidently the site's. True of
    # a complete crawl of every page - it is the markup, not the reach.
    "schema-orphan-not-assessed":
        "the site declares several entity @ids and none is evidently its own; "
        "true of a complete crawl, and fixed on the site record",
    # About the site's markup, not about what the run reached (operator,
    # 2026-09-06). A scope statement says "the crawl did not get far
    # enough to measure this"; this says "there is no header landmark on
    # this site, so no image can be identified as the logo", which is true
    # of a complete crawl of every page and is a thing to fix.
    "img-logo-not-assessed":
        "there is no header landmark on this site, so no image can be "
        "identified as the logo - true of a complete crawl of every page, "
        "and a thing to fix",
    "extractability-not-assessed":
        "raised per page because that page's content renders in the browser",
}

#: Every emitter that carries `scope_statement=True` today, with where it is
#: raised. The *declared* half of the check; the population it is compared
#: against is walked out of the tree by `_finding_calls`.
#:
#: CQ-228, first raised at report 100 and carried to 114. The clause below
#: used to narrow the must-be-flagged set to ids ending `-not-assessed`, which
#: is five of the ten emitters that actually carry the flag - so the flag
#: could be deleted from any of the other five and every check in this file
#: still passed. A scope limit that stops being declared reads to the client
#: as a defect relapsing, which is the exact confusion Q-21 answered by
#: introducing the flag.
#:
#: This is a registry of the expected *result*, not of the population, so it
#: is not the hard-coded list of three DISCIPLINE rule 3 forbids: the tree is
#: still enumerated, and the two are asserted equal in both directions. A flag
#: dropped shrinks the walk and fails; a flag added grows the walk and fails
#: until it is written down here, which is what stops this registry going
#: stale the way a one-directional check would let it.
SCOPE_STATEMENT_EMITTERS = {
    "adaptive-escalation": "clauditseo/adaptive.py",
    # The escalation this run declined to make (relay item 136a): the
    # pulse suggested the site-level picture mattered and the operator
    # had asked for one page. A statement about the run's scope, which
    # is what this flag is for - and never a regression, because the
    # next run at a wider scope simply does not raise it.
    "adaptive-scope-held": "clauditseo/adaptive.py",
    "adaptive-no-escalation": "clauditseo/adaptive.py",
    "axe-coverage": "clauditseo/axe.py",
    "axe-sampled": "clauditseo/modules/a11y.py",
    "backlinks-not-assessed": "clauditseo/modules/ofp.py",
    "contrast-not-assessed": "clauditseo/modules/a11y.py",
    "cwv-not-assessed": "clauditseo/modules/prf.py",
    "domain-authority-reported": "clauditseo/modules/ofp.py",
    # Item 236: the referring-domain count, reported as the authority is.
    "referring-domains-reported": "clauditseo/modules/ofp.py",
    "unreachable-not-assessed": "clauditseo/modules/tec.py",
    # `third-party-scripts-not-assessed` was here until migration 0054 retired
    # the whole `third-party-scripts` family with the lab proxies. Removed
    # rather than left as a stale row: this register is what the guard below
    # walks, and a name in it that no emitter constructs fails the guard by
    # design -- which is the register working, not a gap.
}


def _finding_calls():
    """Every `Finding(...)` construction under `clauditseo/`, read from source.

    Enumerated from the tree rather than from a list this test keeps, because
    a hard-coded list of ten is how a partial fix passes (DISCIPLINE rule 3).
    A new `-not-assessed` emitter added tomorrow is inside this test's reach
    on the day it is written.
    """
    for path in sorted((ROOT / "clauditseo").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Finding"):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            check = kw.get("check_id")
            if not isinstance(check, ast.Constant) or not isinstance(check.value, str):
                continue
            flag = kw.get("scope_statement")
            yield (path.relative_to(ROOT).as_posix(), node.lineno, check.value,
                   isinstance(flag, ast.Constant) and flag.value is True)


def test_the_flag_is_carried_by_the_emitter_not_inferred():
    """Precondition for everything above: the flag reaches the real emitters.

    A guard written only against the hand-built fixture at the top of this
    file would hold with every module in the tree unflagged, which is the
    shape DISCIPLINE rule 5 is about - a check whose evidence cannot disagree
    with it.
    """
    calls = list(_finding_calls())
    assert calls, "the source scan found no Finding() construction at all"

    flagged = {c for _, _, c, f in calls if f}
    assert {"unreachable-not-assessed", "domain-authority-reported"} <= flagged, (
        "the two checks Q-21 was asked about are not flagged at their "
        f"emitters. Flagged: {sorted(flagged)}")

    unflagged = [(p, n, c) for p, n, c, f in calls
                 if c.endswith("-not-assessed") and not f
                 and c not in NOT_A_SCOPE_STATEMENT]
    assert not unflagged, (
        "these checks declare in their own name that they measured nothing, "
        "and do not carry `scope_statement=True`. Either flag the emitter, or "
        "add the check id to NOT_A_SCOPE_STATEMENT with the reason it is "
        f"about the site rather than about the run: {unflagged}")

    stale = sorted(set(NOT_A_SCOPE_STATEMENT) - {c for _, _, c, _ in calls})
    assert not stale, (
        f"NOT_A_SCOPE_STATEMENT names checks nothing emits any more: {stale}")


def test_every_flagged_emitter_is_covered_by_this_guard():
    """CQ-228. The whole flagged population, not the `-not-assessed` half.

    The clause above can only see an emitter whose id ends `-not-assessed`.
    Five of the ten that carry the flag do not - `adaptive-escalation`,
    `adaptive-no-escalation`, `axe-coverage`, `axe-sampled` and
    `domain-authority-reported` - and four of those five were named nowhere in
    this file, so deleting `scope_statement=True` from any of them left every
    check here green.

    Both directions, because one direction is how a registry rots. Losing a
    flag fails on the first clause; adding a flagged emitter without writing
    it down fails on the second, so the registry cannot quietly stop
    describing the tree.

    Proven under mutation rather than by argument: with
    `scope_statement=True` removed from `axe-coverage`, this fails on the
    first clause naming `axe-coverage`, and the file's other four checks stay
    green - which is the whole finding, restated as a measurement.
    """
    flagged = {c for _, _, c, f in _finding_calls() if f}
    assert flagged, "the source scan found no flagged emitter at all"

    lost = sorted(set(SCOPE_STATEMENT_EMITTERS) - flagged)
    assert not lost, (
        "these emitters are recorded here as scope statements and no longer "
        "carry `scope_statement=True` at their construction. A scope limit "
        "that stops being declared reads to the client as a defect "
        f"relapsing: {lost}")

    undeclared = sorted(flagged - set(SCOPE_STATEMENT_EMITTERS))
    assert not undeclared, (
        "these emitters carry `scope_statement=True` and are not in "
        "SCOPE_STATEMENT_EMITTERS. Add them with the module they are raised "
        "in, so losing the flag from one of them is visible to the clause "
        f"above: {undeclared}")

    wrong = sorted(
        f"{check} is raised in {sorted(where)} and recorded as "
        f"{SCOPE_STATEMENT_EMITTERS[check]}"
        for check, where in _flagged_locations().items()
        if check in SCOPE_STATEMENT_EMITTERS
        and SCOPE_STATEMENT_EMITTERS[check] not in where)
    assert not wrong, (
        "the registry names the wrong module for these, so a reader "
        f"following it goes to the wrong file: {wrong}")


def _flagged_locations() -> dict[str, set[str]]:
    """`check_id -> every file it is raised in with the flag set."""
    out: dict[str, set[str]] = {}
    for path, _, check, flag in _finding_calls():
        if flag:
            out.setdefault(check, set()).add(path)
    return out


def test_severity_is_not_the_test_the_flag_replaced():
    """Q-21's answer says so in terms, and the measurement behind it was that
    severity fails in both directions: `sitemap-coverage-not-assessed` is
    `info` in every stored row while `sitemap-coverage` beside it is `low` and
    about the site, and five of the six standing `info` rows described the run
    while the sixth did not. So the flagged set must not be recoverable by
    reading severity off the same call."""
    by_check: dict[str, list[bool]] = {}
    for _path, _lineno, check, flag in _finding_calls():
        by_check.setdefault(check, []).append(flag)
    flagged = {c for c, fs in by_check.items() if any(fs)}
    unflagged = {c for c, fs in by_check.items() if not any(fs)}

    # `third-party-scripts-none` carried this clause -- a clean result about the
    # site is not a statement about the run, however informational it reads --
    # until migration 0054 retired the id. `sitemap-coverage` below makes the
    # same point and is alive, so the claim keeps a live example rather than
    # being dropped with the id.
    assert "sitemap-coverage" in unflagged, (
        "the site-scoped sitemap finding is about the site and must still "
        "be able to regress")
    assert "adaptive-escalation" in flagged, (
        "the run's own staging decision describes the run by construction")
