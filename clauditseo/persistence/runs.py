"""Run persistence: audit runs, findings, the fingerprint state machine,
metric snapshots and the cost log.

State machine per (site, fingerprint):
    first seen                -> open
    seen while 'fixed'        -> regressed   (surfaced loudly by the dashboard)
    absent while open/regressed, and its dimension was part of the run -> fixed
    accepted-risk             -> never changed automatically
    withdrawn                 -> never cleared by absence; a LATER RUN that
                                 sees the finding reopens it (see 0023)
    a SCOPE STATEMENT seen again -> open, never regressed. A finding that
                                 describes the audit rather than the site
                                 (`Finding.scope_statement`) has no defect to
                                 come back, so a narrower run re-raising it is
                                 not a relapse (Q-21, WF-101)
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import json
import re
from pathlib import Path
import sqlite3
from dataclasses import dataclass

from clauditseo.engine.core import AuditResult

from .repo import create_id, now_iso

#: The finding-state vocabulary, owned here rather than re-derived per consumer.
#:
#: It was owned by the schema's CHECK constraint alone (``0023``), so every
#: consumer wrote its own copy — a negative filter, two literal tuples, a set of
#: hand-mapped report keys, a TypeScript union and an array literal in a select.
#: A negative filter is the shape that fails silently, because a value added to
#: the constraint is admitted by every one of them without a line changing. The
#: docstring on :func:`compare_runs` records that happening to ``accepted-risk``
#: at five values; it happened again to ``withdrawn`` at six, and the second one
#: put a finding the product had retracted into a model-written brief about a
#: fee-paying client's site.
#:
#: ``ALL_STATES`` is asserted against the live CHECK constraint by
#: ``test_every_state_the_schema_allows_is_classified_for_the_model``, so a
#: seventh value cannot be added to the schema without being classified here.
ALL_STATES = ("candidate", "open", "fixed", "regressed", "accepted-risk",
              "withdrawn")

#: What the dispatcher's memory may contain. Positive by construction: a new
#: state is withheld from the model until somebody adds it here, which is the
#: safe direction to fail in.
LIVE_STATES = ("candidate", "open", "fixed", "regressed")

#: Withheld from the model, for two different reasons that must not be merged.
#: ``accepted-risk`` is present and the operator has decided to live with it —
#: recommending it again is noise. ``withdrawn`` was never true, and the model
#: cannot leak what it never saw.
MODEL_BLIND_STATES = ("accepted-risk", "withdrawn")

#: What the operator's own control may write, as against what a run derives.
#:
#: The split is the same one :data:`MODEL_BLIND_STATES` makes, read from the
#: other side. ``candidate``, ``fixed`` and ``regressed`` are conclusions the
#: lifecycle walk draws from what a crawl saw; a person setting one by hand
#: writes a claim no run gathered, which is the defect WF-61 describes reached
#: through the product's own button. The two model-blind states are the
#: opposite — no run can ever derive them, so this route is the only thing
#: that will ever record one. ``open`` joins them as the way back from both.
#:
#: Owned here rather than in the route because the route was the sixth reader
#: of this vocabulary and the only writer, which is how ``withdrawn`` came to
#: be counted, typed, filtered, explained and painted while remaining
#: unsettable — see the account above :data:`ALL_STATES`. A seventh
#: operator-owned state added to :data:`MODEL_BLIND_STATES` is settable
#: without a line changing in ``api/app.py``.
OPERATOR_SETTABLE_STATES = ("open",) + MODEL_BLIND_STATES

#: The latest ``findings`` row for a fingerprint **on one site**.
#:
#: A fingerprint is ``sha256(dimension:check_id:subject)`` and the subject is
#: usually a URL path, so two clients that both have ``nap-missing`` on
#: ``/contact-us`` share one fingerprint. That is by design — ``finding_states``
#: is keyed on ``(site_id, fingerprint)``, so the identity is only ever meant
#: to be read within a site.
#:
#: Every read that turned a fingerprint back into its text and URLs had
#: dropped the site half of that key, joining on the fingerprint alone and
#: taking whichever row was written last anywhere. The record showed one
#: client's URLs under another client's finding; the verify would have
#: fetched them, ``_apply_states`` would have cleared findings by looking at
#: the wrong site's pages, and IndexNow would have submitted a third party's
#: URLs. Nineteen fingerprints were shared across three sites when this was
#: found.
LATEST_FINDING = """
    SELECT f2.rowid FROM findings f2
      JOIN audit_runs a2 ON a2.id = f2.run_id
     WHERE f2.fingerprint = {fp} AND a2.site_id = {site}
     ORDER BY f2.created_at DESC, f2.rowid DESC LIMIT 1"""


def _latest_finding(fp: str = "fs.fingerprint", site: str = "fs.site_id") -> str:
    return LATEST_FINDING.format(fp=fp, site=site)


def create_run(conn: sqlite3.Connection, site_id: str, dimensions: list[str],
               tier: str, created_by: str | None = None,
               analyst_enabled: bool = False, kind: str = "audit",
               scan_scope: str | None = None, scan_depth: str | None = None,
               scan_url: str | None = None) -> str:
    # Brief v6 step V2: an audit that states no scope reads the site - the
    # launch route and the CLI always state one, and a caller that says
    # nothing (a scheduled audit, an import) means the whole site. Only a
    # row from before the column existed is NULL, and for that the page
    # count decides.
    if scan_scope is None and kind == "audit":
        scan_scope = "full"
    """`kind='verify'` for a pass that re-crawls only the pages behind
    specific findings, `kind='refresh'` for a pass that re-measures ONE page
    for ONE dimension (`FEATURES.md` F-06). Both still apply state
    transitions — that is the point of running them — but are excluded from
    everything that scores, trends or compares runs, because a composite over
    a handful of pages is not comparable with one over the site.

    A refresh is the narrower of the two and carries one extra rule, applied
    in `_apply_states`: it may not clear a site-scoped finding, because it
    never read the site."""
    run_id = create_id()
    with conn:
        conn.execute(
            "INSERT INTO audit_runs (id, site_id, dimensions, tier, status, engine_version,"
            " analyst_enabled, started_at, created_by, created_at, kind,"
            " scan_scope, scan_depth, scan_url)"
            " VALUES (?, ?, ?, ?, 'running', '', ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, site_id, json.dumps(dimensions), tier, int(analyst_enabled),
             now_iso(), created_by, now_iso(), kind, scan_scope, scan_depth, scan_url),
        )
    return run_id


def add_progress(conn: sqlite3.Connection, run_id: str, label: str,
                 replace_last: bool = False) -> None:
    """Append a progress step (or update the latest one in place, for
    fast-ticking counters like crawl page counts)."""
    row = conn.execute("SELECT progress FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    if row is None:
        return
    steps = json.loads(row["progress"] or "[]")
    entry = {"label": label, "at": now_iso()}
    if replace_last and steps:
        steps[-1] = entry
    else:
        steps.append(entry)
    with conn:
        conn.execute("UPDATE audit_runs SET progress=? WHERE id=?",
                     (json.dumps(steps), run_id))


def store_evidence(conn: sqlite3.Connection, run_id: str, evidence: dict) -> None:
    """Keep the crawl's derived record with the run so expert tools can be
    run later without re-crawling."""
    with conn:
        conn.execute("UPDATE audit_runs SET crawl_evidence=? WHERE id=?",
                     (json.dumps(evidence, default=str), run_id))


@functools.lru_cache(maxsize=4)
def parsed_evidence(raw: str):
    """A run's stored `crawl_evidence`, parsed once per distinct blob.

    Read-only callers only - the object returned is SHARED between them and
    across requests, so a caller that changes it changes every later reading.
    The anatomy route alone parsed twenty22's 1.8 MB blob seventeen times,
    once per payload, which was most of the route's time. Keyed on the text,
    not the run id, so a re-stored blob is a different key and nothing needs
    invalidating. A writer that means to change evidence reads it with
    :func:`get_evidence`, which hands back its own copy."""
    return json.loads(raw)


#: The raw evidence text already read in this scope, per run. Unset - so
#: every read goes to the database - except inside :func:`one_evidence_read`.
_EVIDENCE_TEXT: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "_EVIDENCE_TEXT", default=None)


@contextlib.contextmanager
def one_evidence_read(conn: sqlite3.Connection):
    """Read each run's `crawl_evidence` from the database once in this block.

    The anatomy route assembles a dozen payloads against one run, and each
    read the 1.8 MB column for itself: parsing was cached, but copying the
    blob out of SQLite fifteen times was still a fifth of the route. Scoped
    to a block, and to the connection it names, rather than kept for the
    process: a long-lived connection - a run writing evidence - must never
    read a copy from before its own write. Inside it every payload also sees
    one version of the evidence, where separate reads could straddle a write.
    """
    token = _EVIDENCE_TEXT.set({"conn": conn, "text": {}})
    try:
        yield
    finally:
        _EVIDENCE_TEXT.reset(token)


def evidence_text(conn: sqlite3.Connection, run_id: str | None) -> str | None:
    """A run's stored `crawl_evidence` text, or None where the run or its
    evidence is absent. Read once per run inside :func:`one_evidence_read`."""
    memo = _EVIDENCE_TEXT.get()
    if memo is not None and memo["conn"] is not conn:
        memo = None
    if memo is not None and run_id in memo["text"]:
        return memo["text"][run_id]
    row = conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    raw = row["crawl_evidence"] if row else None
    if memo is not None:
        memo["text"][run_id] = raw
    return raw


def get_evidence(conn: sqlite3.Connection, run_id: str) -> dict:
    row = conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    if not row or not row["crawl_evidence"]:
        return {}
    return json.loads(row["crawl_evidence"])


def parity_mode(conn: sqlite3.Connection, site_id: str,
                before_run: str | None = None) -> bool | str:
    """How this run probes mobile and bot parity (item 151): `"full"` where the
    site's previous run found a divergence, so every readable page is fetched
    under the three agents; otherwise `True`, the sample.

    Read from `prior_run`'s stored `mobile_parity` block. A prior run with no
    block - a first run, or one from before 0.27.0 - is not a divergence, and
    the sample runs.
    """
    from clauditseo.crawler.parity import diverged
    prior = prior_run(conn, site_id, before_run)
    if not prior:
        return True
    return "full" if diverged(get_evidence(conn, prior["run_id"]).get("mobile_parity")) else True


def set_tier(conn: sqlite3.Connection, run_id: str, tier: str) -> None:
    """Adaptive runs record the tier they actually executed at."""
    with conn:
        conn.execute("UPDATE audit_runs SET tier=? WHERE id=?", (tier, run_id))


def fail_run(conn: sqlite3.Connection, run_id: str, reason: str) -> None:
    with conn:
        conn.execute(
            "UPDATE audit_runs SET status='failed', finished_at=?, error=? WHERE id=?",
            (now_iso(), reason, run_id),
        )


def recover_interrupted(conn: sqlite3.Connection,
                        older_than_hours: float = 0) -> int:
    """Server-start recovery.

    Runs execute on daemon threads inside the served process, so at boot NO
    thread can still own one: any 'pending'/'running' row is orphaned whatever
    its age. The previous two-hour guard meant a run interrupted ten minutes
    before a restart stayed "running" in the dashboard until some later
    restart happened to fall outside the window — on a stable server, forever.

    The age guard survives as an opt-in for unusual multi-process deployments
    sharing one database; the boot path passes 0. If uvicorn workers > 1 is
    ever supported this needs a liveness registry rather than a boot sweep,
    because then a sibling worker legitimately owns a running row.
    """
    age_clause = (f" AND created_at < datetime('now', '-{older_than_hours} hours')"
                  if older_than_hours > 0 else "")
    with conn:
        cur = conn.execute(
            "UPDATE audit_runs SET status='failed', finished_at=?,"
            " error='interrupted: server stopped while this run was in flight'"
            " WHERE status IN ('pending','running')" + age_clause,
            (now_iso(),))
    return cur.rowcount


#: Runs the operator has asked to stop.
#:
#: In process, not in the database, and that is the honest shape: the
#: worker is a thread in this process and the question is asked once per
#: page. A row would make it a poll of a file on every page of every
#: crawl, and would outlive the process that could act on it - a stop
#: asked for a run whose worker has gone is a stop nobody will ever
#: answer, and it would sit there to be answered by the next run to reuse
#: the id.
_STOP_REQUESTED: set[str] = set()


def request_stop(run_id: str) -> None:
    """Ask the crawl behind `run_id` to stop at its next page boundary."""
    _STOP_REQUESTED.add(run_id)


def stop_requested(run_id: str) -> bool:
    return run_id in _STOP_REQUESTED


def clear_stop(run_id: str) -> None:
    """One-shot: a stop asked for a run that has finished must not stop the
    next one to reuse the worker."""
    _STOP_REQUESTED.discard(run_id)


def cancel_run(conn: sqlite3.Connection, run_id: str, fetched: int) -> None:
    """Record a run the operator stopped, with what it did fetch.

    `cancelled`, not `failed`: `failed` means the product broke, and a run
    list that showed the second as the first would have the operator
    debugging their own decision. Not in `AUDITED_STATUSES` either - it
    reached some pages and scored nothing, and counting it as an audit
    would let a run somebody stopped stand as the site's standing
    position.
    """
    with conn:
        conn.execute(
            "UPDATE audit_runs SET status='cancelled', finished_at=?, error=?"
            " WHERE id=?",
            (now_iso(),
             f"stopped by the operator after {fetched} page(s) fetched",
             run_id))
    clear_stop(run_id)


#: A run that produced a score to compare. Trends, composites, deltas, "vs
#: previous" — and anything reading fetched pages, because a run that reached
#: no page has none to diff.
SCORED_STATUSES = ("complete",)

#: A run that happened. Scheduling, the site's standing position, run lists,
#: and the staleness counters that ask "how many audits since this one".
#:
#: A blocked crawl belongs here and not above. It is real history — a site
#: that refused us is a fact about the site, and pretending no audit occurred
#: makes the scheduler retry forever and the assistant deny an audit it is
#: simultaneously answering questions about. Its composite rests on
#: robots.txt alone, which is why it is not SCORED.
AUDITED_STATUSES = ("complete", "blocked")

#: A run kind whose crawl was chosen to represent the site, so its result may
#: be generalised to the site: scored onto the trend, counted as "the latest
#: audit", compared against another run, and allowed to clear a finding that
#: names no page.
#:
#: An allow-list, deliberately, and this is the whole point of the constant.
#: The rule was written twice inside one function eight lines apart, once as
#: `narrow=kind == "refresh"` — a deny-list naming the one kind anybody had
#: thought about — and once as `if kind == "audit"`, under a comment arguing
#: for the second spelling. A fourth kind therefore inherited the careless
#: answer from one and the careful answer from the other. Here it inherits
#: the careful one everywhere, and the day someone adds `sweep` they have to
#: come to this line and say what it may claim.
SITE_READING_KINDS = ("audit",)


def is_site_reading(kind: str | None) -> bool:
    """Whether this run may be generalised to the site it belongs to.

    `None` and the empty string are not readings. Rows predate the `kind`
    column — `0011_run_kind.sql` backfilled `'audit'`, so nothing stored is
    actually null — but a caller reading a row shape that omits the field
    should get the conservative answer rather than a KeyError-shaped guess.
    """
    return kind in SITE_READING_KINDS


def kind_is_site_reading(column: str = "kind") -> str:
    """The SQL fragment, generated for the same reason `status_in` is.

    Twelve queries spelled this `AND kind='audit'` by hand and three that
    needed it had nothing at all — `site_reports`, and the two readers in
    `app.py` that pick a site's latest run. A generator does not stop a
    reader forgetting to call it; what it does is make "the rule" a thing
    with one definition, so the guard that enumerates readers from the table
    has something to compare them against.
    """
    marks = ", ".join(f"'{k}'" for k in SITE_READING_KINDS)
    # Brief v6 step V2: a reading of the site is a site-reading kind AND a
    # site-wide scope - the stored scope, else the crawl's page count for a
    # row that stored none, never the tier. One predicate, so the anatomy,
    # the trend, the standing position and the client's label agree about
    # which run reads the site.
    prefix = column.rsplit(".", 1)[0] + "." if "." in column else ""
    return (f"({column} IN ({marks}) AND "
            f"{scope_is_site_wide(prefix + 'scan_scope', prefix + 'crawled_paths')})")


#: A crawl that fetched at least this many pages read the site, whatever its
#: tier said (brief v3 step I, WF-05b / WF-08). The tier is a budget, not a
#: reading: a T2 run on the operator's own site fetched 20 pages - the
#: navigation set - and a T1 run fetched one, and both wore "site-wide" and
#: the site's score on Home. `scan_scope` is written on insert now and
#: backfilled by `0034`; where it is still NULL, the page count decides,
#: and the tier never does.
SITE_WIDE_MIN_PATHS = 50


#: The engine's notes about how it ran (item 238): `adaptive.py` records
#: whether it escalated, and why. A statement about the run, not the site -
#: counted as a finding it was the "Prioritise & report" part's only one, and
#: made that part claim a score it never had.
ENGINE_RUN_NOTES = ("adaptive-escalation", "adaptive-no-escalation")


def is_coverage_note(check_id: str, severity: str | None) -> bool:
    """Whether a finding row is a coverage note rather than a finding: an
    Info-severity statement of what the audit could not measure (a check
    not assessed, or a coverage figure).

    The rule used to carry a third clause for `third-party-scripts*` — an Info
    inventory and its `-none` true-negative sibling, neither of which was a
    fault. Those ids are retired (migration 0054) and the clause went with
    them: a predicate matching nothing is a claim about a vocabulary that no
    longer exists.

    The one rule (brief v5 step S, UX-20). The record's screen has excluded
    these from its rows since brief v2 step F, while the anatomy's part
    totals - and so the sidebar's badges - counted them, and one part read
    14 in the sidebar against 13 on the record. Stated here once, carried
    on the wire as `coverage_note`, and used by the part totals.
    """
    if severity != "info":
        return False
    return (check_id.endswith("-not-assessed")
            or check_id.endswith("-coverage")
            or check_id in ENGINE_RUN_NOTES)


def coverage_note_sql(check: str = "f.check_id", severity: str = "f.severity") -> str:
    """The same rule as a SQL predicate, for the counts taken in SQL."""
    notes = ", ".join(f"'{n}'" for n in ENGINE_RUN_NOTES)
    return (f"({severity} = 'info' AND ({check} LIKE '%-not-assessed'"
            f" OR {check} LIKE '%-coverage' OR {check} IN ({notes})))")


def scope_of(row) -> str | None:
    """`page | nav | site | full`, or None when nothing is known: the stored
    scope, else the crawl's own page count - one page is a page scan, fewer
    than `SITE_WIDE_MIN_PATHS` is a navigation scan, at least that many read
    the site. The dashboard's `scopeOf` (api.ts) says the same."""
    scope = row["scan_scope"] if "scan_scope" in row.keys() else None
    if scope:
        return scope
    raw = row["crawled_paths"] if "crawled_paths" in row.keys() else None
    if not raw:
        return None
    try:
        n = len(json.loads(raw))
    except (TypeError, ValueError):
        return None
    if n == 0:
        return None
    return "page" if n == 1 else "nav" if n < SITE_WIDE_MIN_PATHS else "site"


def kind_in_site_reading_kinds(column: str = "kind") -> str:
    """The kind half of `kind_is_site_reading()` alone, for the readers whose
    question is about the kind and not about what the run may stand for.

    Two of them (WF-114). The backfill that writes `scan_scope` onto rows
    from before the column (0034) establishes a scope rather than asking
    one. The "one audit at a time per site" guard in the audit-launch route
    asks only whether a crawl is in flight: a nav-scoped audit is still a
    crawl racing the next one's writes and still bills the analyst layer,
    so scope is not its question and admitting it by scope reopened KI-19.

    Every OTHER reader asks the whole question, and that is the default a
    new one should reach for - the scope half is dropped deliberately here,
    not by convenience."""
    marks = ", ".join(f"'{k}'" for k in SITE_READING_KINDS)
    return f"{column} IN ({marks})"


def is_site_wide(row) -> bool:
    """Whether a run's reading may stand for the site."""
    return scope_of(row) in ("site", "full")


def reads_site(row) -> bool:
    """The Python twin of `kind_is_site_reading()` over a row (brief v6
    step V2): a site-reading kind whose scope is site-wide."""
    kind = row["kind"] if "kind" in row.keys() else None
    return is_site_reading(kind) and is_site_wide(row)


def narrow_run_refusal(row) -> str | None:
    """Why a brief may not run against this run, or None where it may
    (brief v6 step V3): a brief run against a nav or page scan reads those
    pages alone and would be offered to run again once a site-wide audit
    is picked. One sentence, the server's, shown on every control the
    screen disables for the same reason."""
    if reads_site(row):
        return None
    scope = scope_of(row) or "narrow"
    word = {"page": "page scan", "nav": "nav scan"}.get(scope, f"{scope} run")
    raw = row["crawled_paths"] if "crawled_paths" in row.keys() else None
    try:
        n = len(json.loads(raw)) if raw else 0
    except (TypeError, ValueError):
        n = 0
    return (f"This audit is a {word} — an analysis run against it reads {n} page"
            f"{'' if n == 1 else 's'}. Pick a site-wide audit, or run one on step 2.")


def scope_is_site_wide(scope: str = "scan_scope", paths: str = "crawled_paths") -> str:
    """The SQL twin of `is_site_wide`, for the readers that pick a site's
    score in one query - generated the way `kind_is_site_reading` is, so the
    rule has one owner."""
    return (f"({scope} IN ('site','full') OR ({scope} IS NULL AND {paths} IS NOT NULL"
            f" AND json_array_length({paths}) >= {SITE_WIDE_MIN_PATHS}))")


def status_in(statuses: tuple[str, ...], column: str = "status") -> str:
    """The SQL fragment for one of the vocabularies above.

    One generator rather than nineteen hand-written comparisons. Both concepts
    were spelled `status='complete'`, so adding `blocked` updated four sites
    and missed fifteen — and the column then meant two different things
    depending on which query a screen happened to call. Naming the concept at
    the call site makes the choice explicit and reviewable; spelling the
    literal makes it invisible.

    Interpolated rather than parameterised because these are module constants,
    never caller input, and a fragment has to compose into a larger statement.
    """
    quoted = ", ".join(f"'{s}'" for s in statuses)
    return f"{column} IN ({quoted})"


def terminal_status(result: AuditResult) -> str:
    """What a finished run should be filed as.

    'blocked' when the crawl obtained no eligible page — no 200 with an HTML
    body. A blanket `Disallow: /`, a 5xx on robots.txt, an unreachable host,
    or a crawl that retrieved only 404s and a PDF all land here, and they are
    the same fact to every page-derived check: nothing to read.

    It is a success, not a failure. The run did its job, the answer is "the
    site would not let us look", and that is frequently the most valuable
    finding an audit can return. `fail_run` remains for a run that broke.

    Absence is not zero. A caller that builds an `AuditResult` without stats —
    every direct construction in the suite, and any older path — gets
    'complete' as before, because "we did not record what we saw" must never
    be read as "we saw nothing".
    """
    eligible = (result.stats or {}).get("pages_eligible")
    return "blocked" if eligible == 0 else "complete"


def mark_complete(conn: sqlite3.Connection, run_id: str, stamp: str,
                  scores: dict | None = None, status: str = "complete") -> None:
    """The one place a run reaches a terminal status.

    Two paths finish a run — an audit through `complete_run`, and a Screaming
    Frog import through `importers.import_crawl` — and each wrote the status
    with its own UPDATE. Two writers of one column means a rule applied to one
    of them is a rule applied to half the runs in the database, and the
    difference only shows up in whichever path nobody was looking at. This
    owns the transition; the callers own what led to it.

    `scores` is None for an imported crawl. That is not an omission: an import
    carries evidence and no score, because the deterministic modules read
    fetched page bodies an import does not have. Stamping `engine_version` on
    a run the engine never scored would claim a comparability that does not
    exist, and `subscores` stays NULL rather than becoming an empty object,
    which reads as "scored, and nothing applied".

    Assumes an open transaction — both callers are already inside one, and the
    status write must land with the rows that justify it or not at all.
    """
    if scores is None:
        conn.execute(
            "UPDATE audit_runs SET status=?, finished_at=? WHERE id=?",
            (status, stamp, run_id))
    else:
        conn.execute(
            "UPDATE audit_runs SET status=?, engine_version=?,"
            " composite_score=?, subscores=?, finished_at=? WHERE id=?",
            (status, scores["engine_version"], scores["composite_score"],
             json.dumps(scores["subscores"]), stamp, run_id))
    # Item 239: a run that reaches its terminal status updates the Latest
    # View, here, because this is the one place that happens. `complete_run`
    # writes it again once the crawl's paths are stored.
    from . import latest_view
    latest_view.apply_run(conn, run_id)


def complete_run(conn: sqlite3.Connection, run_id: str, result: AuditResult) -> None:
    """Store findings, scores, state transitions and metric snapshots in one
    transaction so history is never half-written."""
    row = conn.execute(
        "SELECT site_id, kind, crawl_evidence FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    site_id = row["site_id"]
    subscores = {
        d: {"score": s.score, "weight": s.weight, "applicable": s.applicable,
            "coverage": s.coverage, "unmeasured": list(s.unmeasured),
            "detail": s.detail}
        for d, s in result.subscores.items()
    }
    stamp = now_iso()
    status = terminal_status(result)
    with conn:
        for f in result.findings:
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " model_id, confidence, summary, affected_urls, affected_total, evidence,"
                " recommendation, fingerprint, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (create_id(), run_id, f.dimension, f.check_id, f.severity.value,
                 f.source, f.model_id, f.confidence.value, f.summary,
                 json.dumps(f.affected_urls),
                 # The emitter's own count where it capped, and the length of
                 # what it handed over where it did not. Never left NULL from
                 # here on: NULL is reserved for rows that predate migration
                 # 0030, so "no frame" keeps meaning one thing (Q-26).
                 f.affected_total if f.affected_total is not None
                 else len(f.affected_urls),
                 # `scope_statement` rides in the evidence (item 239): the
                 # Latest View's replay re-runs this run's ledger step from
                 # the stored rows, and the flag decides re-raise vs regress.
                 json.dumps({**(f.evidence or {}),
                             **({"scope_statement": True} if getattr(f, "scope_statement", False)
                                else {})}, default=str),
                 f.recommendation, f.fingerprint, stamp),
            )
        mark_complete(conn, run_id, stamp,
                      {"engine_version": result.engine_version,
                       "composite_score": result.composite_score,
                       "subscores": subscores}, status)
        # What this run actually fetched, kept so a later comparison can ask.
        # `_apply_states` below uses the same set and has always been right
        # about it; the value simply never survived the call, which is why
        # `compare_runs` spent two rounds substituting worse evidence.
        conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?",
                     (json.dumps(sorted(getattr(result, "crawled_paths", None) or [])),
                      run_id))
        kind = row["kind"] if "kind" in row.keys() else "audit"
        # Re-read now that the crawl's paths are stored, so a legacy row with
        # no stored scope is judged by what it fetched (brief v6 step V2).
        fresh = conn.execute("SELECT kind, scan_scope, crawled_paths FROM audit_runs"
                             " WHERE id=?", (run_id,)).fetchone() or row
        # A run that was not a reading of the site may only clear what it
        # read — the rule `_apply_states` states in full at the condition
        # itself. Asked of the predicate rather than spelled as
        # `kind == "refresh"`, which was a deny-list of one: it made a
        # verification, and every kind added after it, wide by default.
        _apply_states(conn, site_id, run_id, result, stamp,
                      narrow=not reads_site(fresh))
        # The Latest View takes what this run measured (item 239), in the
        # same transaction as its states.
        from . import latest_view
        latest_view.apply_run(conn, run_id)
        # A verification's scores describe the handful of pages it fetched, so
        # they are not a point on this site's trend. Nor are a refresh's: one
        # page over one dimension measures a different population from the
        # audit it refreshes, and `(engine_version, scope.basis, tier,
        # scope.dimensions)` is the key that would have to call the two
        # comparable — the last term added by WF-58, and it is precisely the
        # difference a one-dimension refresh makes. Written as "only an
        # audit scores" rather than as a list of kinds to exclude, so a fourth
        # kind is out of the trend on the day it is added — and now asked of
        # the one predicate, so the argument this comment makes is the same
        # one the line above it makes.
        if reads_site(fresh):
            # Scope where the run has already stored its evidence, so
            # measured_share counts crawl breadth too. Callers store evidence
            # before completing; where one has not, the share is the
            # dimension-coverage figure alone rather than a guess.
            raw = row["crawl_evidence"] if "crawl_evidence" in row.keys() else None
            _snapshot_metrics(conn, site_id, result, stamp,
                              _scope(json.loads(raw)) if raw else None, run_id)
    _submit_fixed_to_indexnow(conn, site_id, run_id, stamp)


def _submit_fixed_to_indexnow(conn: sqlite3.Connection, site_id: str,
                              run_id: str, stamp: str) -> None:
    """Tell search engines about pages whose findings this run verified fixed.

    Optional enhancer: silent without CLAUDITSEO_INDEXNOW_KEY, and a submission
    failure never fails the run — the audit result matters more than the ping.
    Only URLs behind fixed-this-run findings are sent, not the whole site;
    IndexNow is a change notification, not a sitemap.
    """
    from clauditseo.config import settings

    cfg = settings()
    if not cfg.indexnow_key:
        return
    rows = conn.execute(
        "SELECT DISTINCT f.affected_urls FROM finding_states fs"
        f" JOIN findings f ON f.rowid = ({_latest_finding()})"
        " WHERE fs.site_id=? AND fs.state='fixed' AND fs.changed_by_run=?"
        " AND fs.updated_at=?", (site_id, run_id, stamp)).fetchall()
    urls: list[str] = []
    for row in rows:
        urls.extend(u for u in json.loads(row["affected_urls"] or "[]")
                    if u.startswith("http") and u not in urls)
    if not urls:
        return
    try:
        import httpx
        from urllib.parse import urlsplit
        host = urlsplit(urls[0]).netloc
        httpx.post("https://api.indexnow.org/indexnow",
                   json={"host": host, "key": cfg.indexnow_key,
                         "urlList": urls[:100]},
                   timeout=15.0)
        add_progress(conn, run_id,
                     f"IndexNow: submitted {min(len(urls), 100)} fixed URL(s)"
                     " for recrawl")
    except Exception:                        # noqa: BLE001 - the ping is optional
        pass


def crawlable_urls(affected_urls: list[str] | None) -> list[str]:
    """The URLs a verification pass could actually re-fetch, in order.

    The filter itself, lifted out of `pages_for_findings` so the screens can
    ask the same question the verify route answers with a 422. `affected_urls`
    is not a list of URLs — a finding may name a path, a header, a sitemap
    entry — and only the ones a crawler can address count.
    """
    return [u for u in (affected_urls or []) if u.startswith("http")]


def names_a_page(affected_urls: list[str] | None) -> bool:
    """Whether a crawl could look again at this finding.

    One owner for the rule the verify route enforces: `pages_for_findings`
    collects `crawlable_urls` across a batch and
    `POST /api/sites/{id}/verify` refuses the batch **422** when that comes to
    nothing — "these findings name no page to re-fetch — they are site-level,
    and are judged by a full audit".

    Carried on every row that carries a tick, rather than re-derived on the
    screen, for the reason `_finding_dict` already records for `specialist`:
    the server decides, so a row cannot offer a control the server would
    refuse. The anatomy payload in particular has two counts that look like
    this answer and are not — `pages` counts the untruncated `affected_urls`
    and `urls` is truncated to ten, and neither applies the `http` filter.
    """
    return bool(crawlable_urls(affected_urls))


#: The most pages one synchronous verification may fetch.
#:
#: `POST /api/sites/{id}/verify` runs inside the request on purpose — its own
#: docstring argues why — but it sized its crawl as
#: `max_pages=max(len(target["urls"]), 1)` off the untruncated `affected_urls`
#: of every marked finding, with no ceiling. A finding is not a page: one tick
#: on `img-alt-missing` for a four-hundred-page site was one four-hundred-page
#: blocking HTTP request, behind a button whose only cost statement was a
#: `title` reading "Seconds, and no model tokens." Raised at audit 011, carried
#: to report 038, and held by `audits/DISPOSITIONS.md` for the twenty-nine
#: reports after that.
#:
#: Twenty-five, from the crawl's own budget rather than from taste. T2 holds
#: `delay_s=0.5` between fetches and `request_timeout_s=15`, so twenty-five
#: pages is tens of seconds of held request when every page answers and minutes
#: when they do not — the outer edge of what an operator will read as "it is
#: working" rather than "it has hung", with no progress line and no cancel to
#: tell them apart. Above it the honest answer is a full audit, which runs in
#: the background and reports what it is doing.
#:
#: One owner, and it travels rather than being re-derived: `site_detail` and
#: `site_anatomy` both carry it, because the two screens holding a verify
#: button read different payloads and a rule implemented twice drifts — the
#: argument `names_a_page` records directly above, and the defect CQ-82 and
#: CQ-134 are both instances of.
VERIFY_PAGE_CAP = 25


def pages_named_by(affected_urls: list[str]) -> set[str]:
    """The paths a finding names, which is also the test for whether a narrow
    run is allowed to judge it at all.

    One owner, because two consumers need the same answer and they used to
    derive it separately: `_apply_states` skips a finding this returns empty
    for, and `verify_outcomes` has to report that the run therefore decided
    nothing about it. A rule enforced at one of two call sites is the defect
    CQ-105 records — the run-kind rule with an owner in SQL and none in Python.
    """
    from urllib.parse import urlsplit
    return {urlsplit(u).path or "/" for u in crawlable_urls(affected_urls)}


def _read_a_page_of(affected_urls: list[str],
                    crawled: set[str] | frozenset[str]) -> bool:
    """Did this run read a page the finding names?

    The clearing rule and the reporting rule are the same question asked by
    two functions, and WF-69 is what it cost to let them answer it
    separately. `_apply_states` decides whether a finding may be cleared;
    `verify_outcomes` decides whether the operator is told anything was
    decided. Both read this.

    Not folded into `pages_named_by`: that answers "which pages" and has a
    third caller (`pages_for_findings`) that wants the set rather than the
    verdict.
    """
    pages = pages_named_by(affected_urls)
    return bool(pages) and bool(pages & set(crawled))


def trace_instrumented(dimension: str, check_id: str) -> bool:
    """Whether a finding of this check can only be raised from a performance
    trace, so only a run that traced its page has looked for it (item 159).

    The three modules' `TRACE_DERIVED_CHECKS`, and nothing of its own, so a
    check added to any of them is protected on the day it is added.

    It carried `page-weight` as a local addition while PRF's set left it out
    on the ground that the HTML-bytes proxy also emitted it - untrue since
    migration 0054 retired that proxy. Item 168 corrected the set itself, and
    the addition came off here rather than being left as a second opinion
    about the same id.
    """
    from clauditseo.modules import prf as _prf
    from clauditseo.modules import sec as _sec
    from clauditseo.modules import tec as _tec
    by_dim = {"PRF": _prf.TRACE_DERIVED_CHECKS,
              "TEC": _tec.TRACE_DERIVED_CHECKS,
              "SEC": _sec.TRACE_DERIVED_CHECKS}
    return check_id in by_dim.get(dimension, ())


def cross_page(dimension: str, check_id: str) -> bool:
    """Whether a finding of this check is a property of the whole crawl
    (item 240). The four modules' `CROSS_PAGE_CHECKS`, nothing of its own."""
    from clauditseo.modules import cnt as _cnt
    from clauditseo.modules import links as _lnk
    from clauditseo.modules import onp as _onp
    from clauditseo.modules import sec as _sec
    return check_id in {"ONP": _onp.CROSS_PAGE_CHECKS, "CNT": _cnt.CROSS_PAGE_CHECKS,
                        "LNK": _lnk.CROSS_PAGE_CHECKS,
                        "SEC": _sec.CROSS_PAGE_CHECKS}.get(dimension, frozenset())


def image_derived(dimension: str, check_id: str) -> bool:
    """Whether only the browser image pass can raise this check (item 240)."""
    from clauditseo.modules import onp as _onp
    return dimension == "ONP" and check_id in _onp.IMAGE_DERIVED_CHECKS


@dataclass
class Reading:
    """What one run looked at (item 240): the instruments `measured` asks.

    Built from an `AuditResult` while the run completes, or from the stored
    run for a later question about it (the ledger re-derive). One shape, so
    both ask the one predicate."""
    run_id: str
    #: None where the caller does not know the run's dimensions (a verify's
    #: report); the dimension is then not asked.
    dimensions: frozenset[str] | None
    crawled: frozenset[str]
    traced: frozenset[str]
    imaged: frozenset[str]
    #: A reading of the site: an audit whose scope is site-wide. A refresh,
    #: a verify, a nav or page scan is not.
    site_reading: bool

    @classmethod
    def of_result(cls, run_id: str, result: "AuditResult", site_reading: bool) -> "Reading":
        return cls(run_id, frozenset(result.dimensions),
                   frozenset(getattr(result, "crawled_paths", None) or ()),
                   frozenset(getattr(result, "traced_paths", None) or ()),
                   frozenset(getattr(result, "imaged_paths", None) or ()),
                   site_reading)

    @classmethod
    def of_stored(cls, conn: sqlite3.Connection, run_id: str) -> "Reading | None":
        row = conn.execute("SELECT id, kind, scan_scope, crawled_paths, dimensions"
                           " FROM audit_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        from urllib.parse import urlsplit
        raw = evidence_text(conn, run_id)
        try:
            ev = parsed_evidence(raw) if raw else {}
        except (TypeError, ValueError):
            ev = {}
        pages = [p for p in (ev.get("pages") or []) if isinstance(p, dict) and p.get("url")]
        path = lambda u: urlsplit(u).path or "/"  # noqa: E731
        # A run that never recorded the paths it read (stored before the
        # column, or finished outside `complete_run`) read what the engine's
        # own rule says it read: the eligible pages of its evidence.
        from clauditseo.crawler.types import stored_page_is_eligible
        crawled = (json.loads(row["crawled_paths"]) if row["crawled_paths"] is not None
                   else [path(p["url"]) for p in pages if stored_page_is_eligible(p)])
        return cls(row["id"], frozenset(json.loads(row["dimensions"] or "[]")),
                   frozenset(crawled),
                   frozenset(path(p["url"]) for p in pages
                             if isinstance(p.get("perf"), dict)
                             and p["perf"].get("traced") is not False),
                   frozenset(path(p["url"]) for p in pages
                             if any(i.get("weight_kb") or i.get("rendered")
                                    for i in (p.get("image_inventory") or []))),
                   reads_site(row))


def measured(reading: Reading, dimension: str, check_id: str, affected_urls: list[str],
             source: str = "deterministic", raised: bool = False) -> tuple[str, str]:
    """Did this run measure this finding: `raised`, `clean` or `unmeasured`,
    with the reason (item 240, amendment 1 of item 239).

    The one place that decides what a run measured. `_apply_states` may clear
    only on `clean`; `verify_outcomes` reports a decision only on `raised` or
    `clean`. `unmeasured` never clears and never advances: absence of looking
    is not absence of the fault. Each instrument asked here once cost a false
    "fixed" that reached the record:

      - the dimension ran;
      - the source: an analysis's finding is measured by its analysis, which
        walks its own states - a sweep never clears it (the ONP-only T2 of
        2026-09-23 cleared 48 of a paid analysis's rows);
      - a cross-page check needs a reading of the whole site;
      - the page: a finding naming pages needs one of them read; one naming
        none needs a reading of the site;
      - the trace, for a trace-derived check;
      - the image pass, for an image-derived check.
    """
    if raised:
        return "raised", ""
    if reading.dimensions is not None and dimension not in reading.dimensions:
        return "unmeasured", "the run did not measure this dimension"
    if source != "deterministic":
        return "unmeasured", "an analysis's finding is measured only by its analysis"
    if cross_page(dimension, check_id) and not reading.site_reading:
        return "unmeasured", "a cross-page check needs a reading of the whole site"
    pages = pages_named_by(affected_urls)
    if pages and not pages & reading.crawled:
        return "unmeasured", "the run did not read a page the finding names"
    if not pages and not reading.site_reading:
        return "unmeasured", "a finding that names no page needs a reading of the whole site"
    if _untraced(dimension, check_id, affected_urls, reading.traced):
        return "unmeasured", "the run did not trace a page the finding names"
    if image_derived(dimension, check_id) and not (pages & reading.imaged if pages
                                                     else reading.imaged):
        return "unmeasured", "the run did not weigh the images on a page the finding names"
    return "clean", ""


def _untraced(dimension: str, check_id: str, affected_urls: list[str],
              traced: set[str] | frozenset[str]) -> bool:
    """Did this run fail to trace every page a trace-derived finding names?

    The instrument axis beside the page rule `_read_a_page_of` states, asked
    by the same two consumers for the same reason: `_apply_states` may not
    clear what the run did not look for, and `verify_outcomes` may not report
    it decided. False for any check a trace does not raise - those are
    answered by the fetch alone. A trace-derived finding that names no page
    needs the run to have traced something at all.
    """
    if not trace_instrumented(dimension, check_id):
        return False
    pages = pages_named_by(affected_urls)
    return not (pages & set(traced)) if pages else not traced


def emitted_fingerprints(result: AuditResult) -> set[str]:
    """What this run actually found — the deterministic fingerprints it
    re-emitted.

    One owner, because two consumers need the same answer and WF-100 is what
    it cost to let one of them approximate it. `_apply_states` drives the
    state machine from this set; `verify_outcomes` has to report an outcome
    from the same set, and it used `changed_by_run == run_id` instead. That
    is a record of a *transition*, and `_apply_states` writes a row only when
    it CLEARS one — so a finding that was already `fixed` and was re-found
    takes no branch, writes no row, and is indistinguishable from one nobody
    looked at. It is the CQ-105 lesson again: a rule with one owner rather
    than a copy at each consumer.

    Analyst findings are excluded here rather than at each caller: they are
    commentary and never drive the state machine, so a run that re-emits one
    has not established anything the record should move on.
    """
    return {f.fingerprint for f in result.findings if f.source == "deterministic"}


def scope_statement_fingerprints(result: AuditResult) -> set[str]:
    """The fingerprints this run raised ABOUT ITSELF rather than about the site.

    Read off `Finding.scope_statement`, which the emitter sets — see the field
    for the rule and for the two checks deliberately outside it. One owner
    beside :func:`emitted_fingerprints` for the same reason that one has: two
    consumers would otherwise each re-derive "is this about the crawl", and a
    rule with two implementations is the defect CQ-105 records.

    Filtered to `deterministic` for the same reason as `emitted_fingerprints`:
    an analyst finding never drives the state machine, so its flag would decide
    nothing and including it would let the two sets disagree on membership.
    """
    return {f.fingerprint for f in result.findings
            if f.source == "deterministic" and f.scope_statement}


def _apply_states(conn: sqlite3.Connection, site_id: str, run_id: str,
                  result: AuditResult, stamp: str,
                  narrow: bool = False) -> None:
    _advance_states(conn, site_id, run_id, stamp,
                    current=emitted_fingerprints(result),
                    about_the_run=scope_statement_fingerprints(result),
                    reading=Reading.of_result(run_id, result, site_reading=not narrow),
                    blocked=terminal_status(result) == "blocked")


def _advance_states(conn: sqlite3.Connection, site_id: str, run_id: str, stamp: str, *,
                    current: set[str], about_the_run: set[str], reading: "Reading",
                    blocked: bool) -> None:
    """One run's step of the ledger (item 239): the live completion and the
    Latest View's replay both take it, from an `AuditResult` and from a stored
    run respectively, so the two cannot drift. `current` is what the run
    re-emitted, `about_the_run` its scope statements, `reading` what it
    looked at (`measured`), `blocked` whether it read nothing at all."""
    for fp in sorted(current):
        row = conn.execute(
            "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
            (site_id, fp)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                " updated_at) VALUES (?, ?, 'open', ?, ?)",
                (site_id, fp, run_id, stamp))
        elif fp in about_the_run and row["state"] in ("fixed", "regressed",
                                                      "withdrawn"):
            # A scope statement stands `open` when it is re-raised, and never
            # `regressed`. `regressed` means a defect we had verified gone has
            # come back; a smaller crawl re-raising the statement that it is
            # smaller is not that, it is the provenance invariant working.
            #
            # Stated as "is never IN this state" rather than "does not take
            # this one edge", which is the difference between a rule and a
            # patch on a path: without the `regressed` arm the rows that were
            # already moved by this defect — six standing `info` rows on
            # `www.acme.com.au` at the time it was found — could never leave
            # it, and the count the operator steers by would stay wrong
            # forever while being right about every future run.
            #
            # `open` rather than "leave it alone", by the argument the
            # `withdrawn` branch below already makes in this function and for
            # the same reason: this run has seen the finding, so it stands
            # again — as `open`, because nothing was ever fixed and therefore
            # nothing relapsed. Leaving it `fixed` would label a scope limit
            # that is in force right now as one the site has dealt with.
            #
            # `accepted-risk` is untouched here as everywhere: an operator
            # decision is never moved by a run.
            #
            # Q-21, answered 2026-08-25 — "exclude them from the transition,
            # marked at emission ... carry an explicit flag from the emitter
            # rather than inferring from severity". WF-101, report 099.
            conn.execute(
                "UPDATE finding_states SET state='open', changed_by_run=?, updated_at=?"
                " WHERE site_id=? AND fingerprint=?",
                (run_id, stamp, site_id, fp))
        elif row["state"] == "fixed":
            conn.execute(
                "UPDATE finding_states SET state='regressed', changed_by_run=?, updated_at=?"
                " WHERE site_id=? AND fingerprint=?",
                (run_id, stamp, site_id, fp))
        elif row["state"] == "withdrawn":
            # A withdrawal retracts one audit's claim, not the question. This
            # run is new evidence and it has seen the finding, so it stands
            # again — as `open`, because nothing was ever fixed and therefore
            # nothing relapsed. Unlike `accepted-risk`, which is an operator
            # decision about a condition known to be there and so is never
            # moved, `withdrawn` is a statement about evidence, and evidence
            # is exactly what this run supplies.
            conn.execute(
                "UPDATE finding_states SET state='open', changed_by_run=?, updated_at=?"
                " WHERE site_id=? AND fingerprint=?",
                (run_id, stamp, site_id, fp))

    # Previously-open issues whose dimension was audited this run and whose
    # PAGE was actually visited, but which did not reappear, are fixed.
    #
    # The page condition was missing, and it is the difference between "we
    # looked and it is gone" and "we did not look". A 20-page nav crawl of a
    # 100-page site marked 456 findings on the 80 pages it never fetched as
    # fixed — and each would have come back as a REGRESSION on the next full
    # crawl, so the error compounds into a false alarm as well as a false
    # clearance. Absence of evidence is not evidence of a fix; the same
    # principle already guards sitemap coverage and the dimension list itself.
    from urllib.parse import urlsplit

    # A run that obtained no eligible page did not look at anything, so it
    # cannot have verified anything gone. The page rule below cannot express
    # that: a site-scoped finding names no page, so `pages` is empty, the
    # guard is skipped, and the dimension merely having run is the whole
    # test — which on a blocked crawl means "the module returned nothing
    # because it had nothing to read".
    #
    # This hole was invisible while LOC still raised its two site-scoped
    # findings on an empty crawl: they reappeared every run, so they never
    # reached the clearing pass. Correcting LOC to stop describing pages it
    # never fetched removed that accidental cover, and a crawl that fetched
    # nothing began marking findings verified-fixed — each one due back as a
    # false regression on the next real audit.
    #
    # Everything above this line still runs: a blocked run's own findings
    # open, and a finding that reappears still regresses. Only clearing is
    # withheld, because clearing is the one transition that claims evidence
    # of absence.
    if blocked:
        return

    # Item 240: one predicate decides what this run measured - `measured`,
    # which holds the rules this loop used to spell out one by one (the page
    # read, the narrow run's site-scoped rule, the trace) and the three it was
    # missing (an analysis's own rows, the image pass, cross-page checks).
    # Only `clean` clears; `unmeasured` never does.
    open_rows = conn.execute(
        "SELECT fs.fingerprint, f.dimension, f.check_id, f.affected_urls AS urls,"
        " f.source"
        " FROM finding_states fs"
        f" JOIN findings f ON f.rowid = ({_latest_finding()})"
        " WHERE fs.site_id=? AND fs.state IN ('open','regressed')",
        (site_id,)).fetchall()
    for row in open_rows:
        if row["fingerprint"] in current:
            continue
        verdict, _why = measured(reading, row["dimension"], row["check_id"],
                                 json.loads(row["urls"] or "[]"), source=row["source"])
        if verdict != "clean":
            continue
        conn.execute(
            "UPDATE finding_states SET state='fixed', changed_by_run=?, updated_at=?"
            " WHERE site_id=? AND fingerprint=?",
            (run_id, stamp, site_id, row["fingerprint"]))


def _snapshot_metrics(conn: sqlite3.Connection, site_id: str,
                      result: AuditResult, stamp: str,
                      scope: dict | None = None,
                      run_id: str | None = None) -> None:
    # `run_id` is stored on every row this writes, from migration 0044. The
    # stamp was the only handle for the table's whole life and it is second-
    # resolution, so two runs of one site finishing in one second wrote rows
    # nothing could tell apart — the ambiguity `_recoverable_dimension_sets`
    # refuses to resolve and `run_measured_share` documents joining around.
    # A trend point that names the run it reads against cannot be built on a
    # handle that vague, so the writer now says it outright.
    #
    # Defaulted rather than required, because the argument the caller passes
    # is the one it already holds and a fixture that plants rows directly is
    # writing a pre-0044 row on purpose. NULL keeps its old meaning: read it
    # back through the stamp.
    # A run that obtained no eligible page measured nothing, so it has no
    # point to contribute to any trend — not the composite, and not the
    # per-dimension lines either. Gated here, at the only writer, because a
    # rule enforced in every reader is a rule the next reader forgets.
    # Findings, states and the status itself are still written: a blocked run
    # is stored in full, and only its trend point is withheld.
    if terminal_status(result) == "blocked":
        return
    tier = result.tier.value
    ver = result.engine_version
    # Imported here rather than at module scope for the cycle `scoring` would
    # otherwise close back onto persistence.
    from clauditseo.engine.scoring import measured_share, share_basis

    # One frame, computed once, written onto every point this function stores.
    #
    # It was on one of the three INSERTs below and not on the other two, which
    # is CQ-96 and CQ-94. `site_trend` keyed comparability then on
    # `(engine_version, scope.basis, tier)` — it keys on `scope.dimensions`
    # as well since WF-58 below — and the trend table renders the basis
    # term as its own "Share basis" column, so on `composite_score`,
    # the only series a screen draws, a third of the key was NULL on every row
    # ever written and the column could only ever read `unknown`. The eight
    # per-dimension series carried the same hole.
    #
    # Bound to a name instead of repeated three times deliberately. The defect
    # was not that the expression was wrong anywhere; it was that it existed
    # at one call site out of three, so the next INSERT added here inherits
    # the frame rather than deciding again whether to carry one.
    #
    # The dimension set joins the frame for the same reason the basis did, and
    # it is the term that was missing longest. WF-58, carried from report 051
    # to 097: the key could say which engine measured, whether breadth was
    # applied and how deep the crawl went, and nothing about *which dimensions
    # ran* — so a composite of 91.0 over eight dimensions and one of 62.0 over
    # one came back `comparable: True`, which the launcher can produce in one
    # click from the anatomy screen.
    #
    # Stored on the frame because that is where a run states its own
    # population, at the moment it is known and by the same predicate the
    # per-dimension INSERT below uses. Not because it is the only place the
    # set can come from - WF-58 was recorded closed on that claim at round 097
    # and it is false. Every measured dimension writes a `{dim}.subscore` row
    # at this same `captured_at`, so a point whose frame predates this term
    # has its set written down in its own siblings, and `site_trend` recovers
    # it there rather than reading unknown. What recording it here buys is
    # that the recovered answer can be checked against a stored one, which is
    # the difference between a derivation and a guess.
    #
    # The *measured* set, by the same predicate the per-dimension INSERT below
    # uses — applicable, with coverage. Not the requested set: a dimension that
    # was asked for and read nothing contributes to neither the composite nor
    # the chart, so counting it would split a series on a difference no plotted
    # number carries. Sorted, so two runs that measured the same dimensions
    # produce the same term whatever order the modules ran in.
    #
    # After the spread, not before it like `basis`. `_scope` returns five keys
    # and none of them is `dimensions`, so this cannot displace anything today;
    # placing it here means a key added there cannot silently displace *this*
    # either, which is the direction that would matter — a frame that lost the
    # population would read as a pre-change row and be quietly comparable again.
    measured_dimensions = sorted(dim for dim, sub in result.subscores.items()
                                 if sub.applicable and sub.coverage)
    frame = json.dumps({"basis": share_basis(scope), **(scope or {}),
                        "dimensions": measured_dimensions},
                       default=str)
    # A run with no composite has no trend point. Writing one would put a
    # NULL — or, before composite() learned to say None, a 0.00 — on the line
    # the operator reads as the site's history, where a gap in measurement
    # would be indistinguishable from a collapse in quality.
    if result.composite_score is not None:
        conn.execute(
            "INSERT INTO metric_snapshots (id, site_id, metric_key, value, source, confidence,"
            " captured_at, tier, engine_version, scope, run_id)"
            " VALUES (?, ?, 'composite_score', ?, 'engine', 'high', ?, ?, ?, ?, ?)",
            (create_id(), site_id, result.composite_score, stamp, tier, ver, frame,
             run_id))
        # Beside the composite, at the moment both are known: how much of the
        # intended audit that score rests on. `measured_share` existed for two
        # rounds with no caller, so a T1 pulse over a tenth of the weight and
        # a full T3 entered a site's history indistinguishable — the score is
        # only half the fact.
        # The scope beside the value, because the key holds two quantities.
        # Dimension coverage alone and coverage scaled by crawl breadth are
        # not one series, and five rows for one site stood at 0.2879 and
        # 0.9362 in the same tier with nothing recording which was which.
        # `basis` first, then the counts it was derived from, so a reader can
        # both group the series and check the label against its own inputs.
        conn.execute(
            "INSERT INTO metric_snapshots (id, site_id, metric_key, value, source,"
            " confidence, captured_at, tier, engine_version, scope, run_id)"
            " VALUES (?, ?, 'measured_share', ?, 'engine', 'high', ?, ?, ?, ?, ?)",
            (create_id(), site_id, measured_share(result.subscores, scope),
             stamp, tier, ver,
             frame, run_id))
    for dim, sub in result.subscores.items():
        # `applicable` says the dimension was in scope. `coverage` says
        # whether any of it was obtained, and only the second decides whether
        # there is a measurement to record. Filtering on `applicable` alone
        # wrote `ofp.subscore = 100.0` at `confidence: high` for a dimension
        # that read no backlink data — a perfect score on zero evidence, into
        # the table the trend chart, the comparison and the analyst prompt all
        # read as measured history.
        if sub.applicable and sub.coverage:
            conn.execute(
                "INSERT INTO metric_snapshots (id, site_id, metric_key, value, source,"
                " confidence, captured_at, tier, engine_version, scope, run_id)"
                " VALUES (?, ?, ?, ?, 'engine', 'high', ?, ?, ?, ?, ?)",
                (create_id(), site_id, f"{dim.lower()}.subscore", sub.score,
                 stamp, tier, ver, frame, run_id))


def delete_run(conn: sqlite3.Connection, run_id: str) -> None:
    """Remove a run and everything it produced: findings, cost entries, and
    the metric snapshots captured at its completion (so trends stay honest),
    and the screenshots the rendered pass took for it.
    Finding states survive but lose their changed_by_run reference.

    A run's screenshots live exactly as long as the run (136j Part B). They
    are the only thing this product writes outside the database, so they are
    the only thing that can be orphaned by a delete - and a directory of
    pictures belonging to a run that no longer exists is unreachable by
    every route and invisible to every count."""
    row = conn.execute("SELECT site_id, finished_at, tier, started_at FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    if not row:
        return
    # Item 239's delete ruling: a delete is a rebuild. The run's rows go -
    # its analyses with them, so no pill says "analysed" by a run that is
    # gone - and the Latest View and the ledger are replayed from the runs
    # that remain. It used to null `changed_by_run` and keep every state the
    # run had written: delete twenty22's T2 and its 48 "fixed" stayed fixed,
    # with no run to explain them. The operator's judgements are events and
    # survive; what only this run measured becomes "not measured".
    from . import latest_view
    effect = latest_view.delete_effect(conn, run_id)
    with conn:
        latest_view._delete_rows(conn, run_id, row["site_id"], row["finished_at"])
    latest_view.rebuild(conn, row["site_id"], f"rebuilt after deleting run {run_id}", effect)
    # After the transaction, not inside it: a failure to remove pictures
    # must not roll back the delete of the run they belong to.
    _drop_screens(run_id)


def _drop_screens(run_id: str) -> None:
    """Remove a run's screenshot directory, if it has one."""
    import shutil

    from clauditseo import axe
    try:
        shutil.rmtree(axe.screens_dir(run_id), ignore_errors=True)
    except Exception:                                       # noqa: BLE001
        pass


# --- queries ----------------------------------------------------------------

def list_runs(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM audit_runs WHERE site_id=? ORDER BY created_at DESC, rowid DESC",
        (site_id,)).fetchall()
    return [_run_dict(r) for r in rows]


def site_readings(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    """`list_runs` filtered to the kinds that may be generalised to the site.

    A separate function rather than a default argument on `list_runs`: a
    caller has to choose, and the guard can then enumerate both call sets.
    `list_runs` stays the whole history — the run list on a site's own screen
    must show a verification, or the crawl it performed becomes unauditable —
    and this is what everything that speaks *for the site* reads instead.

    Round 052 gave the rule one owner in SQL, `kind_is_site_reading()`, and
    the twelve queries that needed it. It had no Python twin, so the six
    readers that reach `audit_runs` through `list_runs` kept the old answer
    under a green guard that walks SQL string constants and cannot see a
    function call. The measured cost, on `www.acme.com.au`: `/api/overview`
    answered `70.52` and `/api/clients/{id}` answered `86.2` for the same
    site on the same page load, because the second read the eight-page
    verification `d4474b38` as the site's latest run.
    """
    return [r for r in list_runs(conn, site_id) if reads_site(r)]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM audit_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    run = _run_dict(row)
    run["findings"] = run_findings(conn, run_id)
    run["costs"] = [dict(r) for r in conn.execute(
        "SELECT provider, operation, units, quantity, est_cost, actual_cost"
        " FROM cost_entries WHERE run_id=? ORDER BY created_at", (run_id,))]
    return run


def run_well_known(conn: sqlite3.Connection, run_id: str) -> dict | None:
    """The run's well-known path sweep, from its stored evidence, or None
    (item 143 step BD). A reader of its own rather than a key on `get_run`,
    whose columns are the stored-shape guard's to hold."""
    row = conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    if not row or not row["crawl_evidence"]:
        return None
    try:
        return json.loads(row["crawl_evidence"]).get("well_known") or None
    except (TypeError, ValueError):
        return None


def run_measured_share(conn: sqlite3.Connection, run: dict) -> dict | None:
    """The breadth figure stored for one run, with the frame it means under.

    **Read back, never recomputed.** Recomputing from `run["subscores"]` and
    `run["scope"]` would give the *arithmetic* a caller and leave the stored
    row exactly as unread as it has been for twelve rounds — and the two can
    honestly disagree, because a run completed under an older engine keeps the
    value that engine wrote. The row is the fact; this is its reader.

    **Keyed the way the writer keyed it.** `_snapshot_metrics` stamps
    `captured_at` with the same value `mark_complete` writes to `finished_at`,
    which is already the key `delete_run` removes a run's snapshots by. So the
    join is exact rather than nearest-in-time, and a run still in flight —
    `finished_at` NULL — matches nothing rather than borrowing the last
    audit's figure.

    **`basis` travels with the value because the key holds two quantities.**
    `share_basis` returns `coverage` when the site declared no total and
    `coverage+breadth` when it did, and five real rows for one site stood at
    0.2879 and 0.9362 in the same tier meaning different things. A caller
    handed the number alone would have to guess, which is the defect the
    `scope` column was added to close — re-committed one layer up.

    **None, never 0.0, when nothing was stored.** Only a site-reading kind
    snapshots at all, and `_snapshot_metrics` returns early on a blocked run,
    so a verify, a refresh and a robots-blocked audit all have no figure.
    "We did not measure the breadth" and "we measured it as none of the site"
    are the two things `page_coverage` exists to keep apart.
    """
    if not run.get("finished_at"):
        return None
    row = conn.execute(
        "SELECT value, scope FROM metric_snapshots"
        " WHERE site_id=? AND captured_at=? AND metric_key='measured_share'",
        (run["site_id"], run["finished_at"])).fetchone()
    if not row:
        return None
    # The counts come out of the stored frame rather than off the run's own
    # `scope`, so the figure and the numbers printed beside it are the same
    # arithmetic. Reading the run's evidence instead would let a screen state
    # a ratio the stored value was never scaled by.
    frame = json.loads(row["scope"]) if row["scope"] else {}
    return {
        "value": row["value"],
        # Rows written before migration 0022 carry `scope` NULL, so their
        # basis is unknown and says so — the same answer `site_trend` gives
        # them, and not a guess at which of the two they were.
        "basis": frame.get("basis"),
        "pages_fetched": frame.get("pages_fetched"),
        "discovered": frame.get("discovered"),
    }


def run_findings(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM findings WHERE run_id=?"
        " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
        " WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, dimension, check_id, rowid",
        (run_id,)).fetchall()
    return [_finding_dict(r) for r in rows]


def declared_values(figures: list[dict] | None) -> set[str]:
    """The figures themselves, never the prose they were quoted in.

    `figures_to_verify` holds `{"value", "context"}` pairs, and both consumers
    used to stringify the whole dict before extracting numbers — so every
    number in the context line was treated as declared. That widened the
    report gate's allow-list past what the analyst actually flagged, and
    marked findings that merely quoted an unrelated number from the same
    sentence. One owner, so the two cannot drift apart again.
    """
    out: set[str] = set()
    for item in figures or []:
        value = item.get("value") if isinstance(item, dict) else item
        if value is not None and str(value).strip():
            out.add(str(value).strip())
    return out


def _declares_a_figure(summary: str, figures: list[dict] | None,
                       underived: list[str] | None = None) -> bool:
    """Does this finding quote a figure the analyst flagged for checking?

    Both arguments, unioned, because they answer the same question at
    different widths. `figures` is `figures_to_verify` — the list the operator
    is shown, bounded by `FIGURES_TO_VERIFY_CAP` so the panel stays a list a
    person reads. `underived` is every figure the extractor flagged, uncapped.

    Asking the capped list alone made a display bound decide which numbers a
    client is warned about: a brief flagging forty-five figures caveated the
    first forty in the deliverable and printed the last five as though they
    had been checked. Unioned rather than replaced so a caller that knows only
    the shown list — the tests and the older call sites — keeps working, and
    `declared_values` normalises both because it already accepts a bare value
    as well as a `{"value", "context"}` pair.

    **The summary is read through the same vocabulary the extractor used,
    and CQ-173 is what asking without it cost.** The flagged values come from
    `ungrounded_figures`, which masks caveat blocks, dates, times, standards
    references and markdown structure before it decides a digit run is a
    figure. This side asked `extract_numbers` directly, with no such rule - so
    `E.164` in a summary matched a stored `164` and renderer 1.23.0 printed
    `[TO CONFIRM: figure derived by the analyst, not measured]` beside
    `local-signals/nap-inconsistent` in a client document, whose summary
    quotes two phone numbers off the site and no derived figure at all.
    Measured read-only over the stored corpus, masking moves the set THIS
    BRANCH marks from 7 findings to 6, and the one it drops is that row. Nine
    and eight are the same measurement counted differently - the totals
    including the two rows carrying a stored `figure_unverified: true`, which
    this branch never sees. CQ-182 is that three registers gave those two
    numbers under one name.

    A caveat that fires without cause is not a smaller error than one that
    fails to fire: it teaches the reader to discount the mark, which costs
    the true instances the read-time fallback above just won.
    """
    from clauditseo.analysts.expert import mask_vocabulary
    from clauditseo.numbers import extract_numbers
    values = declared_values(figures) | declared_values(underived)
    if not values:
        return False
    flagged = extract_numbers(" ".join(values))
    return bool(flagged & extract_numbers(mask_vocabulary(summary)))


def figure_is_unverified(evidence: dict, summary: str,
                         figures: list[dict] | None) -> bool:
    """Does this STORED brief finding quote a figure the analyst flagged?

    The stamp when the row carries one; re-derived from the brief's own stored
    figure list when it does not.

    `record_expert_findings` writes `figure_unverified` into each finding's
    evidence at record time and nothing recomputed it, so every improvement to
    the judgement reached only runs made after it landed. Renderer 1.22.0
    widened the judgement from the capped display list to every figure the
    extractor flagged and reached no run already in the database: measured
    read-only, 188 of 275 stored `EXP:*` findings carry no key at all, and
    six of those quote a figure their own brief flagged as derived. They
    print into a client document with a true provenance tag and no caveat,
    which reads as though the number had been audited.

    **Six rather than seven, and the masking is what moved it - CQ-184.**
    This paragraph attributed the movement to `14b4ebb` for one round, while
    `_declares_a_figure` forty lines above and `CHANGELOG.md` attributed the
    same 7-to-6 to the masking, so one file gave two causes for one number
    and a round re-measuring the branch had to pick which to believe.
    Re-measured read-only over `data/clauditseo.db`, moving this branch's two
    inputs independently: against the STORED figure list it marks 7 unmasked
    and 6 masked; against the re-judged list it marks 6 either way. So the
    masking is the cause. What `14b4ebb` did was filter the same value one
    layer earlier, which makes the count stop depending on the mask rather
    than dropping it - a real change to what this branch is handed, and not
    the reason the number is six. The row in every difference is
    `local-signals/nap-inconsistent`.

    **The fallback is a floor, not the answer.** All that survives on disk is
    `expert_reports.figures` — `figures_to_verify`, the list capped at
    `FIGURES_TO_VERIFY_CAP` so the operator's panel stays readable. The
    uncapped set needs the brief's `context`, which is not stored beside the
    payload. So a stored row can be re-judged only at the narrower width, and
    seven is a lower bound on how many of the 188 are derived rather than a
    count of them.

    Keyed on the key being ABSENT, never on it being falsy. A stored `false`
    is a judgement that was made with the uncapped list in hand; re-deriving
    over it would replace a decision made at full width with one made at less,
    which is the display-cap defect pointed the other way.

    Read-time only. Nothing here rewrites `findings.evidence` — the stored row
    is the operator's history, and re-stamping would also destroy the only
    evidence of which rows predate the field.
    """
    if "figure_unverified" in evidence:
        return bool(evidence["figure_unverified"])
    return _declares_a_figure(summary, figures)


def figures_still_derived(report: str | None, findings: list[dict] | None,
                          figures: list[dict] | None) -> list[dict]:
    """A stored brief's flagged-figure list, re-judged against today's rule.

    CQ-172, and the same argument `figure_is_unverified` above makes for the
    deliverable, applied to the surface the operator spot-checks from.
    `expert_reports.figures` is what the extractor produced on the day the
    brief ran, and nothing recomputes it — so the token boundary at round 081,
    the shared masking at 082 and the two vocabulary shapes at 083 each landed
    on the renderer and on neither route onto this column. Measured read-only
    against `data/clauditseo.db` at report 084: of 189 stored values across 38
    briefs, 28 are values today's code would not produce and 65 carry a
    context string the current locator would not choose. The operator's
    `js-rendering` panel asks for nine ordered-list indices to be checked
    before a client sees them.

    **Subtractive only, and that is a property of what survives on disk, not
    a caution.** The brief's judgement was `ungrounded_in_order(masked,
    allowed)` — every number the extractor saw, less the ones grounded in the
    crawl evidence. The evidence is not stored beside the payload, so `allowed`
    cannot be rebuilt and a value the rule would flag *today* but did not then
    cannot be recovered. What can be asked is the half that needs only the
    brief's own prose: would today's `mask_vocabulary` plus `number_tokens`
    still produce this value at all? A value they no longer see is not a
    figure by any reading, whatever the evidence said.

    The scan is reconstructed exactly as `ungrounded_figure_details` composes
    it — the parsed finding summaries, then the prose — because both are
    stored on the row and the offsets have to be the ones the extractor saw.
    Contexts are re-derived through the same masked text for the same reason
    CQ-171 gave: the locator may not point at an occurrence inside a span the
    extractor was blind to.

    Read-time only. Nothing here rewrites `expert_reports.figures` — the
    stored row is the operator's history and the only evidence of which briefs
    predate which rule.
    """
    if not figures:
        return []
    from clauditseo.analysts.expert import figure_context, mask_vocabulary
    from clauditseo.numbers import extract_numbers

    summaries = "\n".join((f.get("summary") or "") for f in (findings or []))
    scan = f"{summaries}\n{report or ''}"
    masked = mask_vocabulary(scan)
    still = extract_numbers(masked)
    kept: list[dict] = []
    for item in figures:
        value = item.get("value") if isinstance(item, dict) else item
        if value is None or str(value).strip() not in still:
            continue
        value = str(value).strip()
        # The pair rebuilt rather than mutated: a row written by an older
        # payload shape may carry keys this one does not know about, and
        # dropping them silently would make the panel's answer depend on when
        # the brief ran, which is the defect this function exists to end.
        base = dict(item) if isinstance(item, dict) else {}
        base["value"] = value
        base["context"] = figure_context(scan, value, locate_in=masked)
        kept.append(base)
    return kept


def _contributions_by_page(conn: sqlite3.Connection, run_id: str,
                           dimension: str) -> dict[str, list[dict]]:
    """What each page has already contributed to this run's rows for one tool.

    The discriminator KI-56's repair turns on, and it is stored rather than
    inferred. `findings` has no page column and cannot be given one without
    putting two rows with the same site-grained fingerprint inside one run —
    so each row it writes carries, in its `evidence`, the per-page parts it
    was merged from. Reading them back and re-merging is how a second page
    ADDS to the first while a re-read of the SAME page REPLACES what that page
    said before.

    Deriving the page from `affected_urls` instead was the obvious alternative
    and is the one `QUESTIONS.md` Q-23 costed as *"`affected_urls` becomes a
    load-bearing discriminator it was never designed to be"*. It is worse than
    it looks: a brief may name no URL at all (`hreflang` and `citations-nap`
    both do), and it may name a URL other than the page it was asked to read,
    so the same list would have to mean both "which page produced this" and
    "which pages are affected". An explicit key cannot be wrong about either.

    Rows written before this landed carry no `pages` key. They are attributed
    to `''` — the site-scoped page — which is the only honest reading: nothing
    on disk says which page they came from, and `''` is where a call that
    named no page has always belonged.
    """
    out: dict[str, list[dict]] = {}
    for row in conn.execute(
            "SELECT summary, severity, check_id, affected_urls, evidence"
            " FROM findings WHERE run_id=? AND dimension=?",
            (run_id, dimension)):
        try:
            ev = json.loads(row["evidence"] or "{}")
        except (TypeError, ValueError):
            ev = {}
        pages = ev.get("pages") if isinstance(ev, dict) else None
        if not isinstance(pages, dict):
            try:
                urls = json.loads(row["affected_urls"] or "[]")
            except (TypeError, ValueError):
                urls = []
            pages = {"": [{"code": row["check_id"], "severity": row["severity"],
                           "summary": row["summary"], "affected_urls": urls,
                           "figure_unverified": bool(
                               (ev or {}).get("figure_unverified"))}]}
        for page, parts in pages.items():
            out.setdefault(page, []).extend(p for p in parts if isinstance(p, dict))
    return out


def record_expert_findings(conn: sqlite3.Connection, run_id: str, tool_id: str,
                           model_id: str, findings: list[dict],
                           figures: list[dict] | None = None,
                           underived: list[str] | None = None,
                           page_url: str | None = None) -> int:
    """Store the issues an expert brief raised, so they can be listed, sorted
    by severity and linked to their pages instead of living only inside a wall
    of prose.

    Written as source='model-judgement' under an 'EXP:<tool>' dimension, which
    keeps them out of the composite score (scoring reads deterministic
    findings only). They DO enter the state memory, at code level and with a
    flap guard — see recompute_expert_states.

    Fingerprints are code-level (site + tool + code), not instance-level: the
    same model names different example URLs on every run, and an instance
    fingerprint would open and close findings that never changed. Whether
    `opening-hours-missing` afflicts this site is the stable fact worth
    remembering; which node exhibited it today is not.

    **A second page adds; the same page replaces.** This used to open with
    `DELETE FROM findings WHERE run_id=? AND dimension=?` — scoped to the tool
    and not to the page — so briefing `/blocked-drains` and then `/hot-water`
    inside one audit deleted everything the first page raised. Reproduced on a
    migrated database at `486896b`: after page 1 the rows read
    `[('h1-missing', ['…/blocked-drains'])]`, after page 2
    `[('description-missing', ['…/hot-water'])]`. It cost the golden harness
    its measurement — both paid runs of 2026-08-24 were billed for three
    `onpage-hygiene` pages and scored against one. KI-56.

    `QUESTIONS.md` **Q-23**, answered *merge across pages by code* on
    2026-08-25: pool `affected_urls` and join summaries, which is exactly what
    `_merge_by_code` already does when a single call carries both pages. The
    site-grained fingerprint keeps the meaning its own paragraph above argues
    for, and `findings` needs no migration. What a stored `EXP:` row now means
    is an accumulation across this run's calls rather than one call's output —
    that is the price the answer named, and `_contributions_by_page` is where
    the per-call truth is kept so the price is paid once rather than lost.

    `page_url` is what discriminates a re-read from a new page, and `None` and
    `''` are the same page: the site. A caller that never names a page — every
    site-scoped brief, and every test written before this — replaces its own
    rows exactly as it always did.

    Returns the number of findings THIS call raised, not the number now
    stored. The caller is reporting on its own brief.
    """
    from clauditseo.engine.types import fingerprint as make_fingerprint

    stamp = now_iso()
    dimension = f"EXP:{tool_id}"
    page = page_url or ""
    # The figures this brief itself flagged, passed in by the caller that
    # already holds them. This used to read them back out of `expert_reports`
    # — a row every caller writes AFTER this function runs, so the set was
    # always empty and every finding was stamped `figure_unverified: false`
    # for good. The read-back looked correct and could never work; the value
    # travelling with the call cannot fail that way.
    declared = figures

    with conn:
        pages = _contributions_by_page(conn, run_id, dimension)
        # This call's own parts, judged now, against the figure lists THIS
        # call was handed. Stamping the flag per part rather than on the
        # merged summary is what lets a row spanning three pages keep each
        # page's verdict: the merge happens later and a re-judge at that point
        # would have only the newest call's `declared` to judge against, so
        # two pages ago would silently be re-decided by today's list.
        pages[page] = [
            {"code": f["code"], "severity": f["severity"],
             "summary": f.get("summary") or "",
             "affected_urls": list(f.get("affected_urls") or []),
             "figure_unverified": _declares_a_figure(
                 f.get("summary") or "", declared, underived)}
            for f in findings]
        if not pages[page]:
            pages.pop(page)
        conn.execute("DELETE FROM findings WHERE run_id=? AND dimension=?",
                     (run_id, dimension))
        flat = [part for p in sorted(pages) for part in pages[p]]
        for f in _merge_by_code(flat):
            urls = f.get("affected_urls") or []
            code = f["code"]
            from_pages = {p: [part for part in parts if part["code"] == code]
                          for p, parts in sorted(pages.items())}
            from_pages = {p: parts for p, parts in from_pages.items() if parts}
            # `confidence` is 'medium' because the brief's index block has no
            # confidence column — the model never stated one. Recorded in the
            # evidence so nothing downstream presents an invented value as
            # the model's own judgement: every brief finding rendered
            # "(medium confidence)", a signal that never varied and therefore
            # carried no information while looking like it did.
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
                " source, model_id, confidence, summary, affected_urls,"
                " affected_total, evidence,"
                " recommendation, fingerprint, created_at)"
                " VALUES (?, ?, ?, ?, ?, 'model-judgement', ?, 'medium', ?, ?, ?,"
                " ?, '', ?, ?)",
                (create_id(), run_id, dimension, code, f["severity"],
                 model_id, f["summary"], json.dumps(urls),
                 # A brief's list is merged across the pages it read and never
                 # capped, so the frame is its length. Written rather than left
                 # NULL for the reason 0030 gives: NULL means "older than the
                 # column", and a row inserted today must not be able to say
                 # that.
                 len(urls),
                 json.dumps({"confidence_stated": False, "from_brief": tool_id,
                             # The analyst's own declaration that a number in
                             # this finding is derived rather than measured.
                             # It already produced `figures_to_verify` and the
                             # app already shows it; the document did not, so
                             # the product held a correct answer to "which
                             # numbers are unverified" and printed neither it
                             # nor a warning. Written here so the renderer
                             # reads a judgement rather than re-deriving one.
                             # Judged against every figure the extractor
                             # flagged, not only the capped list the panel
                             # shows — see `_declares_a_figure`.
                             #
                             # True if ANY part is, because the merged summary
                             # contains every part's sentence and a caveat
                             # that covers three sentences and drops the
                             # fourth is worse than no caveat. Read off the
                             # parts and not off the join, which also stops
                             # `_merge_by_code`'s own "(+2 more of the same
                             # code…)" contributing a `2` for a flagged figure
                             # to match.
                             "figure_unverified": any(
                                 part["figure_unverified"]
                                 for parts in from_pages.values()
                                 for part in parts),
                             # The per-page parts this row was merged from, so
                             # the next call for one of those pages can
                             # replace its own contribution without touching
                             # the others. See `_contributions_by_page`.
                             "pages": from_pages}),
                 make_fingerprint(dimension, code, "site"), stamp))
    site = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                        (run_id,)).fetchone()
    if site:
        recompute_expert_states(conn, site["site_id"], tool_id)
    return len(findings)


def _merge_by_code(findings: list[dict]) -> list[dict]:
    """One row per code, because the fingerprint is one per code.

    A brief that raises `sitemap-coverage` five times with five different
    bodies produced five rows that all fingerprint to (site, tool, code) —
    so the memory tracked one and the other four were invisible to it, while
    the report showed an id five times that identified none of them. An id
    that does not identify cannot be referenced, tracked across runs, or
    cited in a client report.

    Merged rather than dropped: each instance is a real observation, so the
    summaries are joined and the URLs pooled. Severity takes the worst, since
    that is what the code as a whole is worth.
    """
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    merged: dict[str, dict] = {}
    for f in findings:
        code = f["code"]
        if code not in merged:
            merged[code] = {**f, "affected_urls": list(f.get("affected_urls") or []),
                            "_parts": [f["summary"]]}
            continue
        row = merged[code]
        if order.get(f["severity"], 9) < order.get(row["severity"], 9):
            row["severity"] = f["severity"]
        for u in f.get("affected_urls") or []:
            if u not in row["affected_urls"]:
                row["affected_urls"].append(u)
        if f["summary"] not in row["_parts"]:
            row["_parts"].append(f["summary"])
    out = []
    for row in merged.values():
        parts = row.pop("_parts")
        if len(parts) > 1:
            row["summary"] = (f"{parts[0]} (+{len(parts) - 1} more of the same "
                              f"code: {'; '.join(parts[1:])})")
        out.append(row)
    return out


def brief_fingerprint(dimension: str, check_id: str, page: str) -> str:
    """A contract row's identity: the sweep's own dimension and check, the
    page, and a salt so it never collides with the sweep's instance of the
    same check on the same page - the two are one row each under one check
    group, tagged by source (brief v10 step AF)."""
    from urllib.parse import urlsplit

    from clauditseo.engine.types import fingerprint as make_fingerprint
    try:
        path = urlsplit(page).path or "/"
    except ValueError:
        path = page
    return make_fingerprint(f"brief:{dimension}", check_id, path)


def contract_storage_dimension(tool_id: str, check_id: str,
                               base_dimension: str) -> str:
    """Where a conforming brief's row is stored (Q-56, item 137-answer).

    A content ANALYSIS row goes under `EXP:<brief>`, like every other brief's
    rows, so `_expert_section` renders and caveats its figures - which are
    about the Record and span runs, so they are ungroundable against one run's
    deterministic evidence - instead of `_analyst_section` printing them as
    analyst prose whose numbers G7 then cannot ground, refusing the whole
    document. A FREE content check stays under `CNT`: that is the Free/Analysis
    split (brief v17 step AV) applied to storage, and the split is a property
    of the check, not the brief, so this reads the check's own cost rather than
    naming the four briefs. Every other dimension is returned unchanged - only
    content writes model rows under `CNT`, so only content is moved.

    The one rule, shared by the recorder above and `0046`'s migration of the
    rows already stored, so a re-store and a migrated row land on the same
    dimension and therefore the same fingerprint - which is what lets the
    standing carry across the move.
    """
    # Qualified id: `check_costs()` keys the model checks by their full
    # `CNT/gap`, not the bare `gap` a contract row stores, so the bare lookup
    # reads free and the split silently never fired. The dimension is the row's
    # own, so this is the id the registry knows.
    if base_dimension == "CNT" and _check_cost(f"{base_dimension}/{check_id}") == "model":
        return f"EXP:{tool_id}"
    return base_dimension


def record_contract_findings(conn: sqlite3.Connection, run_id: str, tool_id: str,
                             model_id: str | None, rows: list[dict]) -> int:
    """Store a conforming brief's rows under the sweep's own check ids
    (brief v10 step AF). Dimension and check are the check's - `ONP` and
    `title-length` - not `EXP:<brief>`, so the record groups them with the
    sweep's under one check; `source` stays `model-judgement`, the stored
    vocabulary for "a model said so", which every screen reads as `brief`;
    the replacement copy is the row's recommendation; the evidence JSON
    names the brief, the status the brief gave and its note. Instance
    fingerprints, one per page, since a contract row is a fact about a page.
    The brief's previous rows against this run are replaced."""
    stamp = now_iso()
    with conn:
        conn.execute(
            "DELETE FROM findings WHERE run_id=? AND source='model-judgement'"
            " AND json_extract(evidence, '$.from_brief')=?"
            " AND json_extract(evidence, '$.contract')=1",
            (run_id, tool_id))
        for r in rows:
            page = r["page"]
            # Q-56: a content analysis row is stored under `EXP:<brief>`, a free
            # content check stays `CNT`, every other dimension is unchanged.
            # The fingerprint below reads the SAME dimension, so a row this
            # store writes and a row `0046` migrated share an identity.
            dimension = contract_storage_dimension(tool_id, r["check_id"],
                                                   r["dimension"])
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
                " source, model_id, confidence, summary, affected_urls,"
                " affected_total, evidence, recommendation, fingerprint, created_at)"
                " VALUES (?, ?, ?, ?, ?, 'model-judgement', ?, 'medium', ?, ?, 1, ?, ?, ?, ?)",
                (create_id(), run_id, dimension, r["check_id"], r["severity"],
                 model_id, r.get("evidence") or r["check"], json.dumps([page]),
                 json.dumps({"confidence_stated": False, "from_brief": tool_id,
                             "contract": 1, "status": r.get("status"),
                             "note": r.get("note") or "", "page": page,
                             "group": r.get("group"), "raised": bool(r.get("raised")),
                             # What an image answer carries (brief v15): the
                             # image the row is about, the other checks its
                             # one replacement closes, and whether the change
                             # is one file's, a template's or a pipeline's.
                             "image": r.get("image"), "kind": r.get("kind"),
                             "block": r.get("block"), "where": r.get("where"),
                             "also_resolves": list(r.get("also_resolves") or []),
                             # Brief v20's three row fields (items 147, 148).
                             # `suppressed` is the because-clause naming the
                             # check that owns the verdict -- NOT a flag, and
                             # not `not_assessed`: one says the answer is a row
                             # up, the other says run deeper, and a reader sent
                             # to re-audit for something already answered is
                             # the cost of conflating them.
                             "fix_id": r.get("fix_id"),
                             "suppressed": r.get("suppressed"),
                             "confidence": r.get("confidence"),
                             # The sources a link suggestion proposes, each
                             # with its anchor and the heading it belongs
                             # after (brief v17 step AW). Named rather than
                             # left to the `extra` spread below, which keeps
                             # scalars only.
                             "suggestions": [
                                 s for s in ((r.get("extra") or {}).get("suggestions") or [])
                                 if isinstance(s, dict)],
                             # What a brief said about the work this row
                             # implies (brief v17 step AX). Triage scores
                             # on these rather than re-estimating, so a
                             # row that carried them must still carry them
                             # when Triage reads the record back.
                             "fields": dict(r.get("fields") or {}),
                             # The Security brief's change per layer (brief
                             # v20 step BD) - a list, so named here rather
                             # than left to the scalars-only spread below.
                             "config": [c for c in (r.get("config") or [])
                                        if isinstance(c, dict)],
                             # The AI surface brief's row payloads (item 145
                             # BH): candidates, required sections, profiles,
                             # criteria, deltas, omitted URLs, quoted lines.
                             # Lists and objects, so kept here by name; the
                             # spread below keeps scalars only.
                             **({"payload": {k: v for k, v in (r.get("extra") or {}).items()
                                             if k in AIS_ROW_PAYLOAD
                                             and isinstance(v, (list, dict))}}
                                if dimension == "AIS" else {}),
                             **{k: v for k, v in (r.get("extra") or {}).items()
                                if isinstance(v, (str, int, float, bool))}}),
                 r.get("replacement") or "",
                 brief_fingerprint(dimension, r["check_id"], page), stamp))
    return len(rows)


def _page_path(url: str) -> str:
    """The path alone, for callers grouping by route rather than
    identifying a page. Split out from `_page_key` when that key learned to
    keep the query."""
    from urllib.parse import urlsplit
    try:
        return (urlsplit(url).path or "/").rstrip("/").lower() or "/"
    except ValueError:
        return url


def _page_key(url: str) -> str:
    """Two spellings of the SAME page share this key.

    Host, scheme, case and a trailing slash are spellings. **A query string
    is not.** `/apply` and `/apply?ref=broker` are two pages that happen to
    share a path - the second is a parameter variant of the first, which is
    a thing the canonical checks have an opinion about - and folding them
    together made a request for one return the other's facts.

    That went unnoticed while neither page carried a finding: the map this
    key builds is keyed off `affected_urls`, so a page nothing was raised
    about never entered it. Q-54 gave parameter variants a check, the
    variant entered the map, and `/apply` started resolving to
    `/apply?ref=broker` - a self-canonical page reading as a variant of
    itself.
    """
    from urllib.parse import urlsplit
    try:
        split = urlsplit(url)
        path, query = split.path or "/", split.query
    except ValueError:
        path, query = url, ""
    base = path.rstrip("/").lower() or "/"
    return f"{base}?{query}" if query else base


def _is_brief_only(dimension: str, check_id: str) -> bool:
    """Whether only a model can raise this check (item 237). Content's model
    rows are stored under `EXP:<brief>` and priced as `CNT/<id>`."""
    dim = "CNT" if (dimension or "").startswith("EXP:") else dimension
    return _check_cost(f"{dim}/{check_id}") == "model"


def awaiting_confirmation(conn: sqlite3.Connection, site_id: str) -> set[str]:
    """The site's analysis findings that wait for the operator (item 237): a
    candidate on a check only a model can raise. Not in the hold (which reads
    `open`) and not in a client report until the operator confirms it."""
    out: set[str] = set()
    for r in conn.execute(
            "SELECT s.fingerprint, f.dimension, f.check_id FROM finding_states s"
            f" JOIN findings f ON f.rowid = ({_latest_finding('s.fingerprint', 's.site_id')})"
            " WHERE s.site_id=? AND s.state='candidate' AND f.source='model-judgement'",
            (site_id,)):
        if _is_brief_only(r["dimension"], r["check_id"]):
            out.add(r["fingerprint"])
    return out


def _path_of(url: str) -> str:
    from urllib.parse import urlsplit
    return urlsplit(url).path or "/"


def _fetched_paths(conn: sqlite3.Connection, run_id: str) -> frozenset[str]:
    """The pages a run fetched and could read (item 239 step 4)."""
    reading = Reading.of_stored(conn, run_id)
    return reading.crawled if reading else frozenset()


def _saw(named: set[str] | None, fetched: frozenset[str]) -> bool:
    """Whether a run's silence about a row is evidence (item 239 amendment
    10): only where the run fetched a page the row named. A row naming no
    page is about the site, and any run of the tool looked at that."""
    return not named or bool(named & fetched)


def recompute_contract_states(conn: sqlite3.Connection, site_id: str,
                              tool_id: str) -> None:
    """Derive a conforming brief's finding states from its run history
    (brief v10 step AF, corroboration from brief v11 step AH). The walk is
    `recompute_expert_states`'s over the runs where the brief ran: a row
    the sweep corroborates - a deterministic finding of the same check
    naming the same page in the same run - opens on first sight, since the
    sweep has already measured it; a row nothing corroborates is a model's
    finding like any other and waits as a candidate until a second run
    confirms it. Nothing about the contract exempts it from that rule."""
    ran = conn.execute(
        "SELECT a.id FROM audit_runs a WHERE a.site_id=? AND"
        " EXISTS(SELECT 1 FROM expert_reports er WHERE er.run_id=a.id AND er.tool_id=?)"
        " ORDER BY a.started_at, a.rowid", (site_id, tool_id)).fetchall()
    run_order = [r["id"] for r in ran]
    if not run_order:
        return
    fps_by_run: dict[str, dict[str, bool]] = {}
    # Item 237 (the operator's ruling on 203): the fingerprints on a check no
    # sweep can raise. Their corroboration branch can never fire, and a
    # second run of the same model over the same evidence mostly repeats its
    # first reading, so a second sighting is not corroboration: they wait as
    # candidates for the operator, who confirms one by setting it `open`.
    brief_only: set[str] = set()
    # Item 239 step 4: the pages each row named, and the pages each run
    # fetched. A run that did not fetch a row's page says nothing about it.
    paths_of: dict[str, set[str]] = {}
    fetched = {run: _fetched_paths(conn, run) for run in run_order}
    for run in run_order:
        sweep: dict[str, set[str]] = {}
        for f in conn.execute(
                "SELECT check_id, affected_urls FROM findings WHERE run_id=?"
                " AND source='deterministic'", (run,)):
            sweep.setdefault(f["check_id"], set()).update(
                _page_key(u) for u in json.loads(f["affected_urls"] or "[]"))
        fps_by_run[run] = {}
        for r in conn.execute(
                "SELECT fingerprint, dimension, check_id, affected_urls FROM findings"
                " WHERE run_id=? AND source='model-judgement'"
                " AND json_extract(evidence, '$.from_brief')=?"
                " AND json_extract(evidence, '$.contract')=1", (run, tool_id)):
            named = json.loads(r["affected_urls"] or "[]")
            pages = {_page_key(u) for u in named}
            paths_of.setdefault(r["fingerprint"], set()).update(_path_of(u) for u in named)
            fps_by_run[run][r["fingerprint"]] = bool(pages & sweep.get(r["check_id"], set()))
            if _is_brief_only(r["dimension"], r["check_id"]):
                brief_only.add(r["fingerprint"])
    all_fps = set().union(*(set(m) for m in fps_by_run.values())) if fps_by_run else set()
    stamp = now_iso()
    with conn:
        for fp in sorted(all_fps):
            state: str | None = None
            changed_in = run_order[0]
            for run in run_order:
                present = fp in fps_by_run[run]
                if not present and not _saw(paths_of.get(fp), fetched[run]):
                    continue
                corroborated = fps_by_run[run].get(fp, False)
                if present and corroborated:
                    nxt = {None: "open", "candidate": "open", "open": "open",
                           "fixed": "regressed", "regressed": "regressed"}[state]
                elif present:
                    nxt = {None: "candidate",
                           "candidate": "candidate" if fp in brief_only else "open",
                           "open": "open",
                           "fixed": "regressed", "regressed": "regressed"}[state]
                else:
                    nxt = {None: None, "candidate": None, "open": "fixed",
                           "fixed": "fixed", "regressed": "fixed"}[state]
                if nxt != state:
                    changed_in = run
                state = nxt
            existing = conn.execute(
                "SELECT state, changed_by_run FROM finding_states WHERE site_id=? AND fingerprint=?",
                (site_id, fp)).fetchone()
            if existing and existing["state"] in ("accepted-risk", "withdrawn"):
                continue
            # The operator's confirmation (item 237): `open` with no run
            # behind it. A later run that still reports the row, or stops
            # reporting it, cannot take it back to a candidate or drop it -
            # only the operator, or a sweep reading, moves it from here.
            if (existing and existing["state"] == "open" and existing["changed_by_run"] is None
                    and fp in brief_only and state in (None, "candidate")):
                continue
            if state is None:
                conn.execute("DELETE FROM finding_states WHERE site_id=? AND fingerprint=?",
                             (site_id, fp))
            else:
                conn.execute(
                    "INSERT INTO finding_states (site_id, fingerprint, state,"
                    " changed_by_run, updated_at) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(site_id, fingerprint) DO UPDATE SET"
                    " state=excluded.state, changed_by_run=excluded.changed_by_run,"
                    " updated_at=excluded.updated_at",
                    (site_id, fp, state, changed_in, stamp))


def recompute_expert_states(conn: sqlite3.Connection, site_id: str,
                            tool_id: str) -> None:
    """Derive this tool's finding states from its full run history.

    Recomputed rather than mutated incrementally, so a cache replay, a re-run
    that replaces a run's findings, or running the same evidence twice all
    land on the same answer — the history is the truth and the states are a
    view of it.

    The walk per code, over the runs where this tool actually ran:
      first appearance            -> candidate (model output varies a few
                                     percent run to run; once is not a fact)
      appears again               -> open
      candidate, then absent      -> dropped entirely (noise, not a fix)
      open/regressed, then absent -> fixed
      fixed, then appears         -> regressed
    A run where the tool did not run says nothing and is not part of the walk
    — absence of a check is never evidence of a fix.

    'accepted-risk' is the operator's decision and is never overwritten.
    attempted_at / attempt_note survive every transition: the fix loop needs
    to see "attempted, now fixed" and "attempted, still present" side by side.
    """
    from clauditseo.engine.types import fingerprint as make_fingerprint

    # A run counts as "this tool ran" if it has a stored report OR stored
    # findings — findings are themselves proof the tool ran, and briefs that
    # ran before reports were kept per run must still count, or their history
    # silently vanishes from the memory. Ordered by the audit clock, not the
    # report clock, so both sources share one timeline.
    ran = conn.execute(
        "SELECT a.id FROM audit_runs a WHERE a.site_id=? AND ("
        " EXISTS(SELECT 1 FROM expert_reports er WHERE er.run_id=a.id"
        "        AND er.tool_id=?)"
        " OR EXISTS(SELECT 1 FROM findings f WHERE f.run_id=a.id"
        "           AND f.dimension=?))"
        " ORDER BY a.started_at, a.rowid",
        (site_id, tool_id, f"EXP:{tool_id}")).fetchall()
    run_order = [r["id"] for r in ran]
    if not run_order:
        return
    codes_by_run: dict[str, set[str]] = {}
    # Item 239 step 4: as the contract walk - a code is cleared only by a
    # run that fetched a page the code named.
    paths_of: dict[str, set[str]] = {}
    fetched = {run: _fetched_paths(conn, run) for run in run_order}
    for run in run_order:
        codes_by_run[run] = set()
        for r in conn.execute(
                "SELECT check_id, affected_urls FROM findings WHERE run_id=? AND dimension=?",
                (run, f"EXP:{tool_id}")):
            codes_by_run[run].add(r["check_id"])
            paths_of.setdefault(r["check_id"], set()).update(
                _path_of(u) for u in json.loads(r["affected_urls"] or "[]"))

    all_codes = set().union(*codes_by_run.values()) if codes_by_run else set()
    stamp = now_iso()
    with conn:
        for code in sorted(all_codes):
            state: str | None = None
            changed_in = run_order[0]
            for run in run_order:
                present = code in codes_by_run[run]
                if not present and not _saw(paths_of.get(code), fetched[run]):
                    continue
                if present:
                    nxt = {None: "candidate", "candidate": "open",
                           "open": "open", "fixed": "regressed",
                           "regressed": "regressed"}[state]
                else:
                    nxt = {None: None, "candidate": None, "open": "fixed",
                           "fixed": "fixed", "regressed": "fixed"}[state]
                if nxt != state:
                    changed_in = run
                state = nxt
            fp = make_fingerprint(f"EXP:{tool_id}", code, "site")
            existing = conn.execute(
                "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
                (site_id, fp)).fetchone()
            # `withdrawn` joins `accepted-risk` here for a different reason.
            # This walk replays the STORED history, and for a withdrawn
            # finding that history is the very thing being retracted — the
            # runs that raised it are the ones that could not see the site,
            # so replaying them can only ever agree with itself (DISCIPLINE
            # rule 5). Only a new run reopens a withdrawal, which is what
            # `_apply_states` does with the crawl in front of it.
            if existing and existing["state"] in ("accepted-risk", "withdrawn"):
                continue
            if state is None:
                conn.execute("DELETE FROM finding_states WHERE site_id=?"
                             " AND fingerprint=?", (site_id, fp))
            else:
                conn.execute(
                    "INSERT INTO finding_states (site_id, fingerprint, state,"
                    " changed_by_run, updated_at) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(site_id, fingerprint) DO UPDATE SET"
                    " state=excluded.state, changed_by_run=excluded.changed_by_run,"
                    " updated_at=excluded.updated_at",
                    (site_id, fp, state, changed_in, stamp))


def pages_for_findings(conn: sqlite3.Connection, site_id: str,
                       fingerprints: list[str]) -> dict:
    """The pages and dimensions a verification pass has to cover.

    A verify is only honest if it fetches the page each finding was raised
    on — the state machine will not clear a finding whose page was not
    revisited, so a pass that skipped them would report nothing changed and
    be right for the wrong reason.
    """
    if not fingerprints:
        return {"urls": [], "dimensions": [], "found": []}
    marks = ",".join("?" * len(fingerprints))
    rows = conn.execute(
        f"""SELECT fs.fingerprint, f.affected_urls urls, f.dimension
            FROM finding_states fs
            JOIN findings f ON f.rowid = ({_latest_finding()})
            WHERE fs.site_id=? AND fs.fingerprint IN ({marks})""",
        (site_id, *fingerprints)).fetchall()

    urls: list[str] = []
    dims: set[str] = set()
    for row in rows:
        # An expert finding carries EXP:<tool>; it is judged by re-running the
        # brief, not by a crawl, so it cannot be verified this way.
        if row["dimension"] and not row["dimension"].startswith("EXP:"):
            dims.add(row["dimension"])
        for u in crawlable_urls(json.loads(row["urls"] or "[]")):
            if u not in urls:
                urls.append(u)
    return {"urls": urls, "dimensions": sorted(dims),
            "found": [r["fingerprint"] for r in rows]}


def verify_outcomes(conn: sqlite3.Connection, site_id: str,
                    fingerprints: list[str], run_id: str,
                    crawled: set[str] | frozenset[str] = frozenset(),
                    seen: set[str] | frozenset[str] = frozenset(),
                    traced: set[str] | frozenset[str] = frozenset(),
                    imaged: set[str] | frozenset[str] = frozenset()
                    ) -> list[dict]:
    """What the verification run decided about each finding it was asked to
    check.

    Reported per finding rather than as a new total, because "2 fixed, 1 still
    present" is the answer and a changed count is not: a row that did not
    clear needs to say so on itself, or the operator re-reads the whole list
    looking for what moved.

    Three outcomes, not two. `decided` is False where **the run did not read
    a page this finding names** — which is `_apply_states`' rule at
    `:516-517`, character for character, rather than a second rule that
    happens to agree on most inputs.

    It has been narrower than that once and the gap shipped (WF-69). The
    first version asked `bool(pages_named_by(urls))` alone: does the finding
    name a page. That closed the site-scoped case — a finding naming nothing
    cannot be judged by an eight-page crawl, since no crawl establishes a
    site-wide absence — and left the case where the page IS named and the
    fetch failed. `_apply_states` refuses to clear those; this said the run
    had decided them; so the client received `decided: true, cleared: false`
    and `fixloop.tsx` printed "the page was fetched and the finding was still
    on it — check the template rather than the page" about a page that
    returned 503. Reproduced end to end in
    `test_a_page_the_run_could_not_read_is_not_decided_either`.

    `crawled` therefore has to be the caller's `AuditResult.crawled_paths`
    and nothing reconstructed: `eligible()` builds that set from pages that
    actually came back, which is KI-10's rule, and a `Page` object survives a
    failed fetch. Its default is empty rather than "everything", because a
    caller that cannot say what it read has not established an absence — the
    same direction `_apply_states` fails in.

    **`verified` is not that discriminator and never was**, which is worth
    recording because report 053's WF-66 proposed it. It means "this run wrote
    this row", and `_apply_states` writes a row only when it CLEARS one — a
    finding that was fetched and found still present takes no branch at all.
    Measured on the fixture: of five findings, the two cleared came back
    `verified=True` and the other three `verified=False`, and one of those
    three was the skipped site-scoped one. `verified` therefore partitions
    cleared from not-cleared, which `cleared` already does. It is left on the
    payload because it is true and cheap; it is not what a caller should
    branch on.

    **Four outcomes now, and `seen` is the discriminator the three could not
    supply — WF-100.** `seen` is `emitted_fingerprints(result)`, the set
    `_apply_states` drives the machine from. Without it `still_present` was a
    subtraction, so every finding that took no branch fell into it and the
    operator was told a defect was still there about a crawl that did not
    re-find it. Reproduced read-only over verify run
    `71f0fad2186c4e0b99c782ebe46adfd5`: 28 asked, 22 paths read, `cleared 0,
    not_decided 2, still_present 26`, where the run re-emitted 9.

        still_present  the run re-raised it
        cleared        this run moved it to fixed
        not_checked    no page of it was read, and it was not re-raised
        unchanged      asked about, page read, not re-raised, already fixed

    Order matters and `seen` wins, which is the second direction of the same
    finding: a site-scoped statement about the crawl names no page and so can
    never satisfy `decided`, yet the crawl fetches `/llms.txt` and the sitemap
    on every run and genuinely re-raises it. Reported as `not checked`, that
    told the operator nothing had been looked at while `_apply_states` was
    moving the same row to `regressed` on the same evidence. Whether such a
    finding should take that transition at all is `QUESTIONS.md` Q-21 and is
    deliberately not decided here — this function reports what the run saw,
    and the lifecycle is a separate question.

    `unchanged` is a fourth word rather than a fold into either neighbour
    because it is a real answer: the page was read, the finding was not
    re-raised, and it was already fixed before this run, so nothing moved and
    nothing was missed. Folded into `still_present` it is a false alarm;
    folded into `not_checked` it is a false gap.

    `seen` defaults empty for the same reason `crawled` does — a caller that
    cannot say what its run emitted has established nothing — but it fails in
    the opposite direction, so it is stated rather than left to be inferred:
    with an empty `seen`, nothing is reported `still_present`.

    `traced` is the caller's `AuditResult.traced_paths`, and `decided` also
    requires it for a trace-derived finding (item 159): a page that was read
    but not traced was not looked at for that check, so it is `not_checked`
    rather than `unchanged`. Same default direction as `crawled`.
    """
    if not fingerprints:
        return []
    marks = ",".join("?" * len(fingerprints))
    rows = conn.execute(
        f"""SELECT fs.fingerprint, fs.state, fs.changed_by_run,
                   f.dimension, f.check_id, f.affected_urls AS urls, f.source
            FROM finding_states fs
            JOIN findings f ON f.rowid = ({_latest_finding()})
            WHERE fs.site_id=? AND fs.fingerprint IN ({marks})""",
        (site_id, *fingerprints)).fetchall()
    # Item 240: `decided` is `measured`, the rule `_apply_states` clears by -
    # a verification is never a reading of the whole site.
    reading = Reading(run_id, None, frozenset(crawled), frozenset(traced),
                      frozenset(imaged), site_reading=False)
    out = []
    for r in rows:
        urls = json.loads(r["urls"] or "[]")
        read_one = measured(reading, r["dimension"], r["check_id"], urls,
                            source=r["source"])[0] != "unmeasured"
        cleared = r["state"] == "fixed" and r["changed_by_run"] == run_id
        if r["fingerprint"] in seen:
            outcome = "still_present"
        elif cleared:
            outcome = "cleared"
        elif not read_one:
            outcome = "not_checked"
        else:
            outcome = "unchanged"
        out.append({
            "fingerprint": r["fingerprint"], "state": r["state"],
            "verified": r["changed_by_run"] == run_id,
            # `_apply_states`' own page rule, restated at the reporting end.
            "decided": read_one,
            "cleared": cleared,
            # The word the client renders. Decided here rather than at each
            # reader: `fixloop.tsx` rebuilt it from `decided` and `cleared`,
            # which is one rule written twice in two languages.
            "outcome": outcome,
        })
    return out


def mark_attempt(conn: sqlite3.Connection, site_id: str, fingerprint: str,
                 note: str = "") -> bool:
    """Record that a fix was attempted for a finding. The next run judges it:
    state moves to fixed (attempt verified) or stays open (still present)."""
    stamp = now_iso()
    with conn:
        cur = conn.execute(
            "UPDATE finding_states SET attempted_at=?, attempt_note=?"
            " WHERE site_id=? AND fingerprint=?",
            (stamp, note[:500], site_id, fingerprint))
        if cur.rowcount:
            record_state_event(conn, site_id, fingerprint, "attempt", None, "marked",
                               note[:500], at=stamp)
    return cur.rowcount > 0


def clear_attempt(conn: sqlite3.Connection, site_id: str,
                  fingerprint: str) -> bool:
    """Withdraw a fix-attempt mark. WF-84: the operator could set one and
    could not unset one, under a button reading `clear these marks`.

    The stamp and the note go together — the note is *why this fix was
    attempted*, and keeping it beside a cleared stamp would leave a reason
    for an attempt the record no longer holds.

    `state` is deliberately untouched. The mark is the operator's and the
    state is the run's: a withdrawal that also reset the state would let this
    control undo a verdict a crawl reached.

    Returns whether a row moved, the same contract as :func:`mark_attempt`,
    so the route can answer 404 rather than an ok it did not verify (WF-95).
    Clearing an already-clear mark is a no-op on the columns and still
    reports True — the row exists and now holds what the caller asked for.
    """
    with conn:
        cur = conn.execute(
            "UPDATE finding_states SET attempted_at=NULL, attempt_note=NULL"
            " WHERE site_id=? AND fingerprint=?",
            (site_id, fingerprint))
        if cur.rowcount:
            record_state_event(conn, site_id, fingerprint, "attempt", None, "cleared")
    return cur.rowcount > 0


WATCH_SITEMAP_DRIFT = 0.2      # fraction change in declared entries worth flagging


def _sitemap_delta(previous: dict, latest: dict) -> str:
    """Per-sitemap movement, so a drift alert names a file rather than a sum."""
    def counts(evidence: dict) -> dict[str, int]:
        return {(r.get("url") or "").rsplit("/", 1)[-1]: r.get("entry_count") or 0
                for r in evidence.get("sitemaps") or [] if not r.get("is_index")}

    before, after = counts(previous), counts(latest)
    moved = []
    for name in sorted(before.keys() | after.keys()):
        was, now = before.get(name), after.get(name)
        if was == now:
            continue
        if was is None:
            moved.append(f"{name} appeared with {now}")
        elif now is None:
            moved.append(f"{name} is gone (was {was})")
        else:
            moved.append(f"{name} {was} → {now}")
    if not moved:
        return "No individual sitemap changed, which is odd given the total did."
    return ("Per sitemap: " + "; ".join(moved)
            + ". Both crawls read every sitemap successfully, so this is the "
              "site's own declaration changing, not a failed fetch.")


def _sitemaps_unread(evidence: dict) -> set[str]:
    """Sitemaps this crawl failed to read, described so the reason survives.

    Anything that did not come back 200 contributed zero entries to the
    total, which makes that total a statement about the crawl as much as
    about the site."""
    out: set[str] = set()
    for record in evidence.get("sitemaps") or []:
        status, error = record.get("status"), record.get("error")
        if status == 200 and not error:
            continue
        url = (record.get("url") or "").rsplit("/", 1)[-1] or record.get("url", "?")
        out.add(f"{url} ({error or f'HTTP {status}'})")
    return out


def sitemap_drop_fraction(before_total: int, before_unread: bool,
                          after_total: int, after_unread: bool) -> float | None:
    """The fraction the declared sitemap count FELL, or None when the drop is
    not real (item 137, brief v18 step AZ's `sitemap-regression`).

    One rule, so `watch_changes`'s alert and the sweep check cannot disagree
    about what a regression is. It is None when:
      - either run read a sitemap incompletely (`before/after_unread`) — the
        hard-won guard: a sitemap that timed out contributes zero to the total,
        which once produced "declared entries fell 268 to 117" on a site that
        did nothing;
      - there was no baseline to fall from;
      - the count did not fall (a rise is a different event; `sitemap-missing`
        owns disappearance).
    Otherwise the drop fraction, gated at `WATCH_SITEMAP_DRIFT`.
    """
    if before_unread or after_unread:
        return None
    if not before_total or after_total >= before_total:
        return None
    frac = (before_total - after_total) / before_total
    return frac if frac >= WATCH_SITEMAP_DRIFT else None


def prior_sitemap(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """The previous run's sitemap size and whether it read every sitemap
    cleanly, for the sweep's `sitemap-regression` (brief v18 step AZ).

    `None` where there is no such run — and the caller must treat that as
    "cannot answer", never "unchanged", exactly as `prior_run`'s docstring
    requires: a first run, or a run whose prior predates evidence, has no
    baseline and the check stays silent rather than green.
    """
    if not run_id:
        return None
    ev = get_evidence(conn, run_id)
    if not ev:
        return None
    return {"total": ev.get("sitemap_entry_total") or 0,
            "unread": bool(_sitemaps_unread(ev))}


def watch_changes(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    """Differences in the site's control files between the last two crawls.

    robots.txt, the sitemap inventory and llms.txt are tiny files whose
    accidental change does outsized damage — a dropped robots.txt is the
    highest-damage single event there is, and the cheapest to detect. Computed
    from evidence already stored, so this costs nothing to check.
    """
    rows = conn.execute(
        "SELECT id, crawl_evidence, started_at FROM audit_runs"
        f" WHERE site_id=? AND {status_in(AUDITED_STATUSES)}"
        " AND crawl_evidence IS NOT NULL"
        " AND kind='audit'"          # a 2-page verify is not a comparable crawl
        " ORDER BY started_at DESC, rowid DESC LIMIT 2", (site_id,)).fetchall()
    if len(rows) < 2:
        return []
    latest = json.loads(rows[0]["crawl_evidence"])
    previous = json.loads(rows[1]["crawl_evidence"])
    alerts: list[dict] = []

    def flag(what: str, before, after, severity: str = "high") -> None:
        alerts.append({"what": what, "before": before, "after": after,
                       "severity": severity, "since": rows[1]["started_at"],
                       "seen": rows[0]["started_at"]})

    if previous.get("robots_status") != latest.get("robots_status"):
        flag("robots.txt HTTP status", previous.get("robots_status"),
             latest.get("robots_status"), "critical")
    elif (previous.get("robots_txt") or "") != (latest.get("robots_txt") or ""):
        flag("robots.txt content",
             f"{len(previous.get('robots_txt') or '')} chars",
             f"{len(latest.get('robots_txt') or '')} chars")

    # A declared-entry total is only a fact about the site when both crawls
    # actually read the same sitemaps. It is a sum, and a sitemap that failed
    # to fetch contributes zero to it silently — so a single ReadTimeout on
    # one of two sitemaps looked exactly like the site deleting half its URLs.
    # That is what produced "declared entries fell from 268 to 117; regression
    # requires urgent diagnosis" at HIGH severity on a site that had done
    # nothing of the kind.
    #
    # The total is also tier-dependent (T1 reads only the head of each
    # sitemap), capped at MAX_SITEMAPS, and cut short by the wall clock. None
    # of that is a change in the site, and all of it moves this number.
    before_bad = _sitemaps_unread(previous)
    after_bad = _sitemaps_unread(latest)
    before_n = previous.get("sitemap_entry_total") or 0
    after_n = latest.get("sitemap_entry_total") or 0

    if before_bad or after_bad:
        # Say what happened rather than nothing: a sitemap we could not read
        # is worth knowing about on its own, just not as a site regression.
        alerts.append({
            "what": "sitemap not fully read",
            "before": f"{before_n} entries"
                      + (f", {len(before_bad)} sitemap(s) unread" if before_bad else ""),
            "after": f"{after_n} entries"
                     + (f", {len(after_bad)} sitemap(s) unread" if after_bad else ""),
            "severity": "medium",
            "note": "Counts are not comparable across these two crawls — "
                    + "; ".join(sorted(before_bad | after_bad))
                    + ". A sitemap that did not respond contributes nothing to "
                      "the total, so any difference here may be ours, not the "
                      "site's.",
            "since": rows[1]["started_at"], "seen": rows[0]["started_at"]})
    elif bool(before_n) != bool(after_n):
        flag("sitemap presence", before_n, after_n, "critical")
    elif before_n and abs(after_n - before_n) / before_n >= WATCH_SITEMAP_DRIFT:
        # Which sitemap moved, not just that the sum did. A total is not
        # actionable: "declared entries fell from 268 to 117" sends someone
        # to diagnose a site-wide deletion, where "post-sitemap.xml went 160
        # to 32, page-sitemap barely moved" points at one generator and is
        # checkable in a browser in ten seconds.
        alerts.append({
            "what": "sitemap declared entries", "before": before_n,
            "after": after_n, "severity": "high",
            "note": _sitemap_delta(previous, latest),
            "since": rows[1]["started_at"], "seen": rows[0]["started_at"]})

    if previous.get("llms_txt_status") != latest.get("llms_txt_status"):
        flag("llms.txt HTTP status", previous.get("llms_txt_status"),
             latest.get("llms_txt_status"), "medium")
    return alerts


def biggest_gains(subscores: dict) -> list[dict]:
    """The scoreboard's own answer to "where are the points": every check's
    deduction, weighted onto the composite, biggest first.

    Pure arithmetic on data the engine already records — no model, no tokens,
    no variance. The honest caveat travels with it: a deduction is capped per
    severity and rate-based, so "points on the composite" is the ceiling of
    what fixing every instance recovers, not a promise.

    A dimension that is inapplicable, or that carries no weight, offers no
    gain and is excluded. Accessibility is the second case and is not
    demoted by it: it carries its own total and its own section in the
    deliverable (F-09), which is where it is ranked.
    """
    out = []
    for dim, sub in (subscores or {}).items():
        detail = sub.get("detail") or {}
        weight = sub.get("weight") or 0
        # Inapplicable and unweighted are different states and both offer
        # nothing. Only the first was excluded, so A11Y — applicable, weight
        # 0.0 (`engine/scoring.py`) — had every deduction multiplied by zero,
        # kept, and ranked, reaching the client document as "up to 0.0 points
        # on the composite": a number offered as a gain that cannot be gained.
        # `_score_table` had already settled the same question one section up
        # and prints no figure for a dimension carrying no weight.
        if not sub.get("applicable") or not weight:
            continue
        for check, stats in (detail.get("per_check") or {}).items():
            deduction = stats.get("deduction") or 0
            if deduction <= 0:
                continue
            out.append({
                "check_id": check,
                "dimension": dim,
                "affected": stats.get("affected"),
                # No fallback. This used to read `stats.get("pages",
                # stats.get("affected"))`, so a run that never recorded a page
                # count silently got the finding count instead — and a
                # substituted number is indistinguishable from a measured one,
                # which is exactly how "21 of 20 pages" reached a client-facing
                # table. `None` renders as "—": the reader is told the run did
                # not record it rather than shown a different figure.
                "pages": stats.get("pages"),
                "eligible": stats.get("eligible"),
                "subscore_points": round(deduction, 2),
                "composite_points": round(deduction * weight, 2),
            })
    return sorted(out, key=lambda g: -g["composite_points"])


DOSSIER_RUNS = 6          # crawls of history per page; evidence blobs are big


def page_dossier(conn: sqlite3.Connection, site_id: str, url: str) -> dict:
    """Everything known about one URL, across every run and every brief.

    Clients ask page-first — "what's wrong with our services page?" — and
    until now the answer was scattered per-tool. Assembled from data already
    stored: the crawl history of the page, every finding that names it (with
    its memory state), and every page-scoped brief that read it.
    """
    history = []
    for run in conn.execute(
            "SELECT id, started_at, crawl_evidence FROM audit_runs"
            f" WHERE site_id=? AND {status_in(SCORED_STATUSES)}"
            " AND crawl_evidence IS NOT NULL"
            " ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (site_id, DOSSIER_RUNS)):
        evidence = json.loads(run["crawl_evidence"])
        page = next((p for p in evidence.get("pages", [])
                     if p.get("url") == url), None)
        if page:
            history.append({
                "run_id": run["id"], "at": run["started_at"],
                "source": evidence.get("source", "crawler"),
                "status": page.get("status"),
                "title": page.get("title"),
                "word_count": page.get("word_count"),
                "click_depth": page.get("click_depth"),
                "meta_description": page.get("meta_description"),
                "content_dates": page.get("content_dates") or {},
            })

    # Findings that name this URL, latest instance per check, with the
    # memory's verdict attached. LIKE on the JSON is crude but exact: the
    # stored form is a JSON array of full URLs, so quoting the needle avoids
    # matching /page-two when asked about /page.
    needle = f'%"{url}"%'
    findings = [dict(r) for r in conn.execute(
        "SELECT f.dimension, f.check_id, f.severity, f.summary, f.source,"
        " f.created_at, fs.state, fs.attempted_at"
        " FROM findings f"
        " JOIN audit_runs a ON a.id = f.run_id AND a.site_id=?"
        " LEFT JOIN finding_states fs ON fs.fingerprint = f.fingerprint"
        "   AND fs.site_id = a.site_id"
        " WHERE f.affected_urls LIKE ?"
        " AND f.rowid = (SELECT MAX(f2.rowid) FROM findings f2"
        "   JOIN audit_runs a2 ON a2.id = f2.run_id AND a2.site_id = a.site_id"
        "   WHERE f2.dimension = f.dimension AND f2.check_id = f.check_id"
        "   AND f2.affected_urls LIKE ?)"
        " ORDER BY CASE f.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
        " WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END",
        (site_id, needle, needle))]

    briefs = [dict(r) for r in conn.execute(
        "SELECT er.tool_id, er.model_id, er.created_at, er.tokens, er.findings"
        " FROM expert_reports er JOIN audit_runs a ON a.id = er.run_id"
        " WHERE a.site_id=? AND er.page_url=?"
        " ORDER BY er.created_at DESC", (site_id, url))]
    for brief in briefs:
        brief["findings"] = len(json.loads(brief.pop("findings") or "[]"))

    return {"url": url, "history": history, "findings": findings,
            "page_briefs": briefs,
            "seen": bool(history or findings or briefs)}


WORDCOUNT_SWING = 0.3     # fraction change worth surfacing


def crawl_diff(conn: sqlite3.Connection, site_id: str) -> dict | None:
    """Pages added, removed, status-changed or substantially rewritten
    between the last two crawls. Catches the accidents a score hides:
    a deleted section, a noindex slip, a template that ate the body copy."""
    # `kind='audit'`, the same filter `watch_changes` carries and for the
    # same reason: this compares two crawls, and a narrow run is not a crawl
    # of the site. A one-page refresh (F-06) read against a full audit would
    # report every other page as removed — the sitemap-total bug's shape,
    # arriving as an alert about a site that had not changed at all.
    rows = conn.execute(
        "SELECT crawl_evidence, started_at FROM audit_runs"
        f" WHERE site_id=? AND {status_in(SCORED_STATUSES)}"
        " AND crawl_evidence IS NOT NULL"
        " AND kind='audit'"
        " ORDER BY started_at DESC, rowid DESC LIMIT 2", (site_id,)).fetchall()
    if len(rows) < 2:
        return None
    latest = {p["url"]: p for p in json.loads(rows[0]["crawl_evidence"]).get("pages", [])}
    previous = {p["url"]: p for p in json.loads(rows[1]["crawl_evidence"]).get("pages", [])}

    status_changed, rewritten = [], []
    for url in set(latest) & set(previous):
        now, was = latest[url], previous[url]
        if now.get("status") != was.get("status"):
            status_changed.append({"url": url, "before": was.get("status"),
                                   "after": now.get("status")})
        else:
            a, b = was.get("word_count") or 0, now.get("word_count") or 0
            if a and abs(b - a) / a >= WORDCOUNT_SWING:
                rewritten.append({"url": url, "before": a, "after": b})
    return {
        "since": rows[1]["started_at"], "seen": rows[0]["started_at"],
        "added": sorted(set(latest) - set(previous))[:50],
        "removed": sorted(set(previous) - set(latest))[:50],
        "status_changed": status_changed[:50],
        "rewritten": sorted(rewritten,
                            key=lambda r: -abs(r["after"] - r["before"]))[:50],
    }


def run_spend(conn: sqlite3.Connection, run_id: str) -> dict:
    """What one run cost, and where the money figure cannot be given, why.

    `monthly_spend` answers this per client per month and carries the
    `priced`/`unpriced` frame that makes a partial figure readable. Nothing
    answered it for a single run, so `scripts/run_golden.py` — the instrument
    for "does the deep tier earn its price" — printed a score with no price
    beside it, and the USD comparison between two paid runs had to be done by
    hand outside the tool.

    **A zero is never the answer.** `usd` is None when nothing here can be
    priced, and `usd_absent_because` then says which of the three reasons it
    is: nothing was recorded, no price is stored for the models that ran, or
    the rows were written before a price existed and nothing computes a cost
    backwards. That last sentence is the one `reports.tsx` already gives the
    operator; it is repeated here rather than re-derived because a caller
    printing "0.00" reads as free, and free is the one thing this run was not.

    `is_floor` carries UX-04's rule down to the single run: a figure covering
    a minority of the rows that produced the token count beside it is a floor,
    and the caller has to be able to say so.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS tokens, SUM(actual_cost) AS usd,"
        " COUNT(actual_cost) AS priced,"
        " COUNT(*) - COUNT(actual_cost) AS unpriced, COUNT(*) AS entries"
        " FROM cost_entries WHERE run_id=?", (run_id,)).fetchone()
    out = dict(row)
    out["models"] = [r["model_id"] for r in conn.execute(
        "SELECT DISTINCT model_id FROM expert_reports WHERE run_id=?"
        " AND model_id IS NOT NULL ORDER BY model_id", (run_id,))]
    out["is_floor"] = bool(out["priced"] and out["unpriced"])
    out["usd_absent_because"] = None
    if out["unpriced"] or not out["entries"]:
        from clauditseo.providers.fx import price_for
        unpriced = [m for m in out["models"] if price_for(conn, m) is None]
        if not out["entries"]:
            out["usd_absent_because"] = (
                "no cost was recorded against this run")
        elif unpriced:
            out["usd_absent_because"] = (
                "no price is stored for " + ", ".join(unpriced)
                + " in this database")
        else:
            out["usd_absent_because"] = (
                f"{out['unpriced']} of {out['entries']} cost entries were"
                " written before a price was stored, and nothing computes a"
                " cost backwards")
    return out


def monthly_spend(conn: sqlite3.Connection) -> list[dict]:
    """Token and dollar spend per client per calendar month, newest first.
    Dollars appear only where the operator has supplied rates — a month with
    tokens but no cost means no rates were configured, not zero spend.

    **`usd` is a floor whenever `unpriced` is non-zero, and the two counts are
    here so a caller can say so.** This query never coerced its NULL, so a
    wholly-unpriced month has always reported `usd: None` and the admin table
    has always drawn an em dash for it — honest. The gap UX-04 names is one
    row along: a month that is *partly* priced reports a real number, and
    nothing in the payload said it covered a minority of the rows that
    produced the token count beside it. `priced` and `unpriced` are the same
    frame `_budget_status` carries, for the same reason — one column, two
    aggregations, one rule.
    """
    rows = conn.execute(
        "SELECT substr(ce.created_at, 1, 7) AS month, cl.name AS client,"
        " SUM(ce.quantity) AS tokens, SUM(ce.actual_cost) AS usd,"
        " COUNT(ce.actual_cost) AS priced,"
        " COUNT(*) - COUNT(ce.actual_cost) AS unpriced,"
        " COUNT(*) AS entries"
        " FROM cost_entries ce"
        " JOIN audit_runs r ON r.id = ce.run_id"
        " JOIN sites s ON s.id = r.site_id"
        " JOIN clients cl ON cl.id = s.client_id"
        " GROUP BY month, cl.id ORDER BY month DESC, usd DESC").fetchall()
    return [dict(r) for r in rows]


def expert_delta(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    """Per tool: what changed between its two most recent runs on this site.

    The question a retainer client asks every month. Compared per tool over
    the runs where that tool actually ran — two audit runs where a brief ran
    only once have nothing to compare and say so via since=None.

    **Two most recent RUNS, not two most recent rows.** Migration 0029 let a
    (run, tool) hold one row per page, so an unqualified `LIMIT 2` would
    return two pages of the *same* run for any page-scoped brief read twice —
    and both sides then read `findings` by `run_id`, giving identical code
    sets and a delta of "nothing changed since itself". `GROUP BY er.run_id`
    is what makes the population runs; the sort key is each run's newest row,
    which is the same value it was when a run could only have one.
    """
    tools = [r["tool_id"] for r in conn.execute(
        "SELECT DISTINCT er.tool_id FROM expert_reports er JOIN audit_runs a"
        " ON a.id = er.run_id WHERE a.site_id=?", (site_id,))]
    out = []
    for tool in sorted(tools):
        last_two = conn.execute(
            "SELECT er.run_id, MAX(er.created_at) AS created_at"
            " FROM expert_reports er"
            " JOIN audit_runs a ON a.id = er.run_id"
            " WHERE a.site_id=? AND er.tool_id=?"
            " GROUP BY er.run_id"
            " ORDER BY created_at DESC, MAX(er.rowid) DESC LIMIT 2",
            (site_id, tool)).fetchall()
        codes = [{r["check_id"]: r["severity"] for r in conn.execute(
            "SELECT check_id, severity FROM findings WHERE run_id=?"
            " AND dimension=?", (row["run_id"], f"EXP:{tool}"))}
            for row in last_two]
        if len(codes) < 2:
            out.append({"tool": tool, "since": None,
                        "new": sorted(codes[0]) if codes else [],
                        "resolved": [], "persisting": []})
            continue
        latest, previous = codes[0], codes[1]
        out.append({
            "tool": tool,
            "since": last_two[1]["created_at"],
            "new": sorted(set(latest) - set(previous)),
            "resolved": sorted(set(previous) - set(latest)),
            "persisting": sorted(set(latest) & set(previous)),
        })
    return out


def store_expert_report(conn: sqlite3.Connection, run_id: str, tool_id: str,
                        envelope: dict, page_url: str | None = None,
                        elapsed_ms: int | None = None,
                        pages_crawled: int | None = None) -> None:
    """Keep the report itself against the run, not only its findings.

    The analyst cache is keyed on evidence rather than on the run, so it can
    answer "have I seen this exact bundle before" but not "what did this tool
    last say about this site" — which is the question a client-first view asks
    on every keystroke.

    One row per (run, tool, **page**) since migration 0029 — a page-scoped
    brief run against three pages of one audit now keeps three reports where
    it used to keep the last one and silently discard the rest (KI-56,
    `QUESTIONS.md` Q-19). `page_url or ""` and never NULL: SQLite treats NULLs
    in a primary key as distinct, so a NULL here would make this
    `INSERT OR REPLACE` stop replacing a site-scoped row and start
    accumulating duplicates of it.
    """
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO expert_reports (run_id, tool_id, model_id,"
            " page_url, report, findings, figures, figures_withheld, tokens,"
            " tokens_in, tokens_out, cache_write, cache_read, cost, truncated,"
            " created_at, elapsed_ms, pages_crawled, contract, raw)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, tool_id, envelope.get("model"), page_url or "",
             envelope.get("report") or "",
             json.dumps(envelope.get("findings") or []),
             json.dumps(envelope.get("figures_to_verify") or []),
             # The list without this number cannot say whether it is complete.
             # `.get(...)` and not `or 0`: an envelope that never carried the
             # count stores NULL, which the column's own migration defines as
             # "never recorded" rather than "nothing withheld".
             envelope.get("figures_withheld"),
             # The split as well as the sum. Input and output differ by five
             # times in price, so a total alone cannot be checked against the
             # cost stored beside it.
             envelope.get("tokens"), envelope.get("tokens_in"),
             envelope.get("tokens_out"), envelope.get("cache_write"),
             envelope.get("cache_read"), envelope.get("cost"),
             1 if envelope.get("truncated") else 0, now_iso(),
             elapsed_ms, pages_crawled,
             # What the contract made of the answer (brief v10 step AF);
             # NULL for a brief that answered the legacy index instead.
             json.dumps(envelope["contract"]) if envelope.get("contract") else None,
             # The model's own text (migration 0055); NULL where it was never
             # captured, which includes a replay of a payload cached before it.
             envelope.get("raw")))
        # The newest run of each analysis is the Latest View's (item 239).
        from . import latest_view
        latest_view.apply_analysis(conn, run_id, tool_id)


def expert_report(conn: sqlite3.Connection, run_id: str, tool_id: str,
                  page_url: str | None = None) -> dict | None:
    """One stored brief. `page_url` names which page's, and omitting it means
    the most recent.

    Since migration 0029 a (run, tool) can hold several rows — one per page a
    page-scoped brief read. Before it, it held one, because every earlier page
    had been overwritten; so "the newest" is byte-for-byte what this returned
    the day before the key changed, and the screens reading it through
    `GET /api/runs/{run}/expert/{tool}` are unchanged rather than
    accidentally-unchanged. What moved is that the earlier pages still exist:
    `expert_report_index` lists them all with their `page_url`, and a caller
    that wants one names it here.

    `ORDER BY` and not `fetchone()` on an unordered select — the old query was
    unambiguous because the key made it so, and now it would be whichever row
    SQLite happened to reach.
    """
    row = conn.execute(
        "SELECT * FROM expert_reports WHERE run_id=? AND tool_id=?"
        + (" AND page_url=?" if page_url is not None else "")
        + " ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (run_id, tool_id) + ((page_url,) if page_url is not None else ())
    ).fetchone()
    if not row:
        # No reconstruction. This used to assemble a stand-in report out of
        # whatever findings survived, captioned "run it again to restore the
        # full report" — a report-shaped object that was never written, on a
        # screen with no way to obey the caption. Absent is a real answer and
        # the caller renders it as one.
        return None
    # Parsed once and bound, because three of the four answers below are
    # drawn from the same two columns and a second `json.loads` of `figures`
    # is a second chance for them to disagree.
    stored_findings = json.loads(row["findings"])
    stored_figures = json.loads(row["figures"] or "[]")
    return {"tool": row["tool_id"], "model": row["model_id"],
            "page_url": row["page_url"], "report": row["report"],
            "findings": stored_findings,
            # Re-judged on the way out, never rewritten on disk — CQ-172 and
            # `figures_still_derived`. The panel this feeds says "spot-check
            # these before quoting them to a client", so a value the product
            # itself no longer calls a figure is an instruction to check
            # nothing, and the operator cannot tell which.
            "figures_to_verify": figures_still_derived(
                row["report"], stored_findings, stored_figures),
            # Carried through so the recalled brief and the brief that has just
            # run answer "is this list complete" the same way. NULL stays None
            # for a row written before the count existed; the panel renders a
            # sentence for a positive number and nothing for None or 0, so an
            # unrecorded row reads exactly as it did before.
            "figures_withheld": row["figures_withheld"],
            # What the contract made of the answer (brief v12 step AL): the
            # dropped rows with their reasons and the not-assessable ones
            # are what the report lists, and they live nowhere else.
            "contract": json.loads(row["contract"]) if row["contract"] else None,
            # UX-79. The line above and the line above that are computed under
            # different rules — one at read time by today's judgement, one at
            # run time by the day's — and the panel printed them as one
            # sentence that asserted they summed. They do not: every value the
            # re-judge drops leaves the two short of what the brief flagged.
            #
            # This is the number both were drawn from, so the sentence can say
            # "N of M" instead of guessing at a prefix. Derived and never
            # stored, on the precedent `run_expert`'s cache branch records for
            # `replay_underived`: a stored key would leave every row written
            # before it replaying the defect, and this one needs nothing the
            # row does not already carry. NULL is "never recorded" (migration
            # 0027), so it contributes nothing rather than an invented zero —
            # the total is then the stored list itself, which is honest about
            # a row whose pre-cap count nobody kept.
            "figures_flagged": len(stored_figures)
                               + (row["figures_withheld"] or 0),
            "tokens": row["tokens"], "cost": row["cost"],
            "truncated": bool(row["truncated"]), "created_at": row["created_at"],
            "status": "ok", "stored": True}


def expert_report_figures(conn: sqlite3.Connection, run_id: str,
                          tool_id: str) -> list[dict]:
    """The figure list a stored brief flagged, re-judged, and nothing else.

    `expert_report` answers the same question but carries the brief's whole
    prose back with it, and the only caller that wants this is
    `_expert_section`, which reads it once per tool while rendering and never
    prints the prose. A brief runs to pages; the figure list is a handful of
    `{"value", "context"}` pairs.

    Capped at `FIGURES_TO_VERIFY_CAP` when it was written, which is why
    `figure_is_unverified` describes what it derives from this as a floor.

    An absent row is `[]` and not an error: a finding can outlive the brief
    row that produced it, and "no figure was flagged" is the honest reading of
    a brief whose list nobody kept.
    """
    row = conn.execute(
        "SELECT report, findings, figures FROM expert_reports"
        " WHERE run_id=? AND tool_id=?", (run_id, tool_id)).fetchone()
    if not row or not row["figures"]:
        return []
    # Two columns more than the question needs, because the answer is
    # re-judged rather than read: `figures_still_derived` reconstructs the
    # scan the extractor saw from the prose and the parsed summaries. One rule
    # for what a brief flagged, asked the same way here and on the panel —
    # the narrow read serving the wider read's superseded answer is CQ-172
    # wearing a second hat.
    return figures_still_derived(row["report"],
                                 json.loads(row["findings"] or "[]"),
                                 json.loads(row["figures"]))


def store_page_advice(conn: sqlite3.Connection, run_id: str, url: str,
                      advice: dict, model_id: str | None,
                      tokens: int | None) -> None:
    """Keep the advice against the run and the page, not only against the
    evidence it was derived from (F-04).

    `analyst_cache` can answer "have I seen this exact bundle before"; it
    cannot answer "what was this page advised", because its key includes a
    hash of a bundle assembled from a live fetch. Producing that key costs the
    fetch, and the key stops matching as soon as the operator edits the page
    in response to the advice. This table answers the question the panel
    actually asks when it mounts.

    `advice` is always the full remit. Narrowing is a view taken on the way
    out, so storing a scoped answer would make the next section's re-entry
    read a judgement with its own fields missing.
    """
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO page_advice (run_id, url, model_id,"
            " advice, tokens, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, url, model_id, json.dumps(advice), tokens, now_iso()))


def page_advice(conn: sqlite3.Connection, run_id: str, url: str) -> dict | None:
    """The stored advice for one page of one run, or None.

    None is a real answer and the caller renders it as one -- an offer to
    generate. Nothing is reconstructed from `analyst_cache`: a row assembled
    out of a cache hit would need the bundle hash, which needs the fetch,
    which is the cost this read exists to avoid.
    """
    row = conn.execute(
        "SELECT * FROM page_advice WHERE run_id=? AND url=?",
        (run_id, url)).fetchone()
    if not row:
        return None
    return {"url": row["url"], "model": row["model_id"],
            "advice": json.loads(row["advice"]), "tokens": row["tokens"],
            "created_at": row["created_at"]}


def store_probe_result(conn: sqlite3.Connection, run_id: str,
                       measurement: dict) -> dict:
    """Record what a probe measured against the run whose brief asked (F-05).

    Replaces the previous answer for the same question on the same run
    rather than appending: re-running a probe is how the operator checks a
    fix, and a history that made the stale answer the visible one would
    invert that. `created_at` is therefore when this answer was taken, not
    when the question was first asked, and it is shown beside the value for
    exactly that reason.
    """
    row = {"probe_id": measurement["probe_id"], "target": measurement["target"],
           "status": measurement["status"], "value": measurement["value"],
           "source": measurement["source"],
           "detail": measurement.get("detail") or {},
           "created_at": now_iso()}
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO probe_results (run_id, probe_id, target,"
            " status, value, source, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, row["probe_id"], row["target"], row["status"],
             row["value"], row["source"], json.dumps(row["detail"]),
             row["created_at"]))
    return row


def probe_results(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    """Every probe answer stored against this run, newest first.

    Free to read and it must stay that way: the panel calls this when it
    mounts, so re-entering a brief shows what was already measured instead
    of offering to measure it again.
    """
    rows = conn.execute(
        "SELECT * FROM probe_results WHERE run_id=? ORDER BY created_at DESC",
        (run_id,)).fetchall()
    return [{"probe_id": r["probe_id"], "target": r["target"],
             "status": r["status"], "value": r["value"], "source": r["source"],
             "detail": json.loads(r["detail"] or "{}"),
             "created_at": r["created_at"]} for r in rows]


SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if not ordered:
        return 0.0
    return (ordered[middle] if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2)


def expert_estimates(conn: sqlite3.Connection, pages: int | None = None,
                     site_id: str | None = None) -> dict:
    """What each brief has cost before, scaled to the site being looked at.

    A brief against a 12-page site and the same brief against a 100-page site
    are different jobs, so one flat average predicts badly for both. Where the
    history records how large the crawl was, the estimate is a median cost per
    page multiplied out; where it does not, the plain median is returned and
    marked as unscaled rather than dressed up.

    Medians rather than means: one truncated or runaway brief should not drag
    every future estimate with it.

    `site_id` bounds the *population* the medians are taken over, which is a
    different question from `pages` and settled separately (UX-77, `QUESTIONS.md`
    Q-1). Given one, only that site's stored briefs are read; given none, every
    site's are, which is what a surface not looking at a site wants. The
    operator answered Q-1 **per site** on 22 August 2026, so a site-scoped
    surface passes it: the schedule screen tells the operator the price is
    "what that brief has actually cost here before", and without the filter it
    was a median across every client in the install. Two consequences are
    intended rather than tolerated — a site with no history of a brief now
    shows no price for it instead of another client's, and KI-50's fixture row
    (`seed-normal.test`, a `0.0` brief inside the live population) stops
    reaching a real site's figure by construction rather than by a rule about
    test data.
    """
    per_tool: dict[str, dict] = {}
    # The filter is a subquery on `audit_runs` rather than a join so the
    # column list above stays unqualified and the unscoped call is byte-for-byte
    # the query it always was — the scoped path is the addition, not a rewrite
    # of the path five other callers already depend on.
    rows = conn.execute(
        "SELECT tool_id, tokens, cost, elapsed_ms, pages_crawled FROM"
        " expert_reports WHERE tokens IS NOT NULL AND tokens > 0"
        + (" AND run_id IN (SELECT id FROM audit_runs WHERE site_id=?)"
           if site_id is not None else ""),
        (site_id,) if site_id is not None else ()).fetchall()
    for row in rows:
        entry = per_tool.setdefault(row["tool_id"], {
            "tokens": [], "cost": [], "seconds": [],
            "tokens_per_page": [], "seconds_per_page": []})
        entry["tokens"].append(float(row["tokens"]))
        if row["cost"] is not None:
            entry["cost"].append(float(row["cost"]))
        if row["elapsed_ms"]:
            entry["seconds"].append(row["elapsed_ms"] / 1000)
        if row["pages_crawled"]:
            entry["tokens_per_page"].append(row["tokens"] / row["pages_crawled"])
            if row["elapsed_ms"]:
                entry["seconds_per_page"].append(
                    row["elapsed_ms"] / 1000 / row["pages_crawled"])

    out: dict[str, dict] = {}
    for tool, e in per_tool.items():
        scaled = bool(pages and e["tokens_per_page"])
        out[tool] = {
            "samples": len(e["tokens"]),
            "scaled_to_pages": pages if scaled else None,
            "tokens": round(_median(e["tokens_per_page"]) * pages) if scaled
                      else round(_median(e["tokens"])),
            "seconds": (round(_median(e["seconds_per_page"]) * pages)
                        if scaled and e["seconds_per_page"]
                        else round(_median(e["seconds"])) if e["seconds"] else None),
            # Cost is not scaled: it is only ever present when the operator has
            # supplied rates, and per-page dollars invite more precision than a
            # handful of samples supports.
            "cost": round(_median(e["cost"]), 4) if e["cost"] else None,
            # The scope of `cost`, beside it (UX-74). `samples` counts rows
            # carrying tokens; the median above is taken over rows carrying a
            # non-NULL cost, and those are different populations — on the
            # operator's own data `indexability` is three of the first and one
            # of the second. Reported rather than left for the reader to
            # re-derive, which is the frame clause of the provenance
            # invariant: a share is stored with the scope it was computed
            # under, in one key beside the value.
            "cost_samples": len(e["cost"]),
            # Which population, beside the value, for the same reason
            # `cost_samples` is (UX-77). `None` means install-wide. A caller
            # that reads a figure without this key cannot tell a price scoped
            # to the site in front of the operator from one that happens to
            # agree with it, and every consumer here re-serialises field by
            # field, so a scope that is not carried is a scope that is lost.
            "scoped_to_site": site_id,
        }
    return out


def site_reports(conn: sqlite3.Connection, site_id: str) -> dict:
    """Every brief ever produced for a site, across every run.

    The deliverables were reachable only one run at a time: open a run, click
    each brief. Nothing answered "what have we produced for this client" or
    "what did we spend on it", which are the two questions asked before a
    renewal conversation and the two the data could always have answered.

    Returned flat and newest first rather than nested under runs, because the
    useful comparison is one brief against its own history — did the crawl
    health report say the same thing last month — and that is invisible when
    the rows are grouped by run.
    """
    rows = conn.execute(
        """SELECT er.run_id, er.tool_id, er.model_id, er.page_url, er.tokens,
                  er.cost, er.truncated, er.created_at, er.findings,
                  r.started_at, r.tier, r.composite_score, r.status, r.kind,
                  r.scan_scope, r.crawled_paths
           FROM expert_reports er
           JOIN audit_runs r ON r.id = er.run_id
           WHERE r.site_id = ?
           ORDER BY er.created_at DESC""", (site_id,)).fetchall()

    reports = []
    for row in rows:
        found = json.loads(row["findings"] or "[]")
        worst = None
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        for f in found:
            sev = f.get("severity")
            if sev and (worst is None or order.get(sev, 9) < order.get(worst, 9)):
                worst = sev
        reports.append({
            "run_id": row["run_id"], "tool": row["tool_id"],
            "model": row["model_id"], "page_url": row["page_url"],
            "tokens": row["tokens"], "cost": row["cost"],
            "truncated": bool(row["truncated"]),
            "created_at": row["created_at"],
            "run_started_at": row["started_at"], "run_tier": row["tier"],
            "run_score": row["composite_score"],
            # The composite travels with the status that says whether it may
            # be printed. `hasScore` is decided once on the client and was
            # applied at six render sites; the two on the reports screen could
            # not apply it, because this shape and the one below carried the
            # number and not the fact that qualifies it. Frame is provenance:
            # a blocked run's 80.0 comes from robots.txt and the sitemap with
            # no page fetched, and beside a complete run's score it reads as
            # the same kind of measurement.
            "run_status": row["status"],
            # And the kind, for the same reason and one level further out. A
            # status says whether a score was produced; a kind says whether
            # it describes the site. Both are needed before a screen may
            # print the number beside another run's.
            "run_kind": row["kind"],
            # And the scope, the third of the same argument (added 2026-09-18
            # with the one on the `runs` list below). The "Ran against" column
            # prints `run_score` through `RunScore`, which cannot draw "page
            # scan" without being told the scope - so an analysis run against a
            # one-page audit printed that audit's composite as a site score in
            # the same table as a full crawl's.
            "run_scope": scope_of(row),
            "findings": len(found), "worst_severity": worst,
        })

    # Runs with no brief at all still belong here: "we audited and produced
    # nothing" is an answer, and leaving them out would make the page look
    # like a shorter history than the site actually has.
    runs_with = {r["run_id"] for r in reports}
    bare = conn.execute(
        f"""SELECT id, started_at, tier, composite_score, status, kind,
                  scan_scope, crawled_paths
           FROM audit_runs WHERE site_id=? AND {status_in(AUDITED_STATUSES)}
           ORDER BY started_at DESC, rowid DESC""", (site_id,)).fetchall()

    # How many completed audits have run since the one each analysis read.
    #
    # An analysis describes the crawl it was given, and the site keeps moving
    # underneath it. Every one of these was written against the 12 August
    # audit while three newer ones existed, and nothing said so — an auditor
    # quoting a finding a later audit has already closed is the same failure
    # as the sitemap-coverage bug, arriving through a different door.
    #
    # Counted rather than flagged, because "superseded" is not a boolean an
    # operator can act on: one audit since is a re-read, five is a rewrite.
    # Readings of the site only. "How many audits since this one" is a claim
    # about the site having moved underneath a stored analysis, and a run
    # that fetched eight pages of 224 is not evidence the site moved.
    #
    # Measured before this filter existed, on `www.acme.com.au`: the
    # eight-page verification `d4474b38` was `newest_run_id`, so all 24
    # stored analyses read as superseded by it, and its 86.2 headed the runs
    # table above the 224-page audit's 70.52. The deliverables collector 65
    # lines below has carried `kind='audit'` the whole time — one screen,
    # two answers to one question.
    order = [r["id"] for r in bare if reads_site(r)]  # newest first
    position = {run_id: i for i, run_id in enumerate(order)}
    for r in reports:
        r["audits_since"] = position.get(r["run_id"])
        r["is_latest"] = position.get(r["run_id"]) == 0

    priced = [r["cost"] for r in reports if r["cost"] is not None]
    stale = [r for r in reports if (r["audits_since"] or 0) > 0]
    return {
        "reports": reports,
        # The headline, so a screen does not derive it from the rows and two
        # screens cannot derive it differently.
        "stale_analyses": len(stale),
        "newest_run_id": order[0] if order else None,
        # The list keeps every kind — a verification is real history and
        # hiding it would make the crawl it performed unauditable — but each
        # row now says which it is, so the screen can print a composite for
        # the ones a composite means something for. The client had `status`
        # and nothing else, so `hasScore` was the only gate available to it
        # and a narrow run's score rendered as the site's.
        # And the scope, which is the other half of the argument above and was
        # missing until 2026-09-18. `kind` says a verification is not an audit;
        # `effective_scope` says a one-page audit is not the site. Without it
        # `RunScore` on this screen had nothing to gate on, so run 991401ab - a
        # page scan of 1 of twenty22's 53 pages - printed as "72.8 out of 100,
        # fair" here while the Record's own cell for the same run read "page
        # scan". `_run_dict` has stamped both fields on every other run payload
        # since brief v6 step V2; this list built its own dict and omitted them.
        "runs": [{"id": r["id"], "started_at": r["started_at"], "tier": r["tier"],
                  "score": r["composite_score"], "status": r["status"],
                  "kind": r["kind"], "effective_scope": scope_of(r),
                  "site_reading": reads_site(r),
                  "reports": sum(1 for x in reports if x["run_id"] == r["id"])}
                 for r in bare],
        "total_cost": round(sum(priced), 4) if priced else None,
        "unpriced": sum(1 for r in reports if r["cost"] is None),
        # WHY a cost is missing, which is not the same question as whether
        # one is. The screen said "no dollar rate set" and that was false: a
        # rate is set for sixteen models. These analyses ran before any price
        # was recorded, so no cost was ever computed for them — historical
        # absence, not configuration. Home totals the entries that DO carry a
        # cost and shows $0.70, and the two screens read as contradicting
        # each other about money while both were right about their own rows.
        "rate_is_set": bool(conn.execute(
            "SELECT 1 FROM model_prices LIMIT 1").fetchone()),
        "total_tokens": sum(r["tokens"] or 0 for r in reports),
        "runs_with_reports": len(runs_with),
    }


#: The order that decides which row replaced a document, bound to one name
#: because CQ-199 was two spellings of it drifting apart. `client_reports()`
#: folds the site's rows first-writer-wins and `client_report()` asks SQL for
#: one row, so they cannot share an implementation — but they can share the
#: order, which is the only part that was ever in disagreement.
#:
#: `created_at` is a whole-second ISO string, so ties are ordinary rather than
#: exotic: two presses in one second, or two `POST /api/reports` calls naming
#: the same `supersedes`. `rowid DESC` is what breaks them, and it breaks them
#: toward the later INSERT — the newer replacement, which is what both sites
#: already said in prose they reported.
_REPLACEMENT_ORDER = "created_at DESC, rowid DESC"


def client_reports(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    """Deliverables already generated for this site.

    They were written to disk and recorded in `reports`, and nothing listed
    them: the client rail said "Client report ✓ 2 generated" while both files
    were unreachable from the app that made them. A deliverable you cannot
    open is indistinguishable from one that was never produced — and it is
    the artefact the whole run exists to create.
    """
    from clauditseo.reporting.render import RENDERER_VERSION

    # The treatment analyses already get, for the artefact that actually
    # leaves the building. A deliverable describes one crawl and the site
    # keeps moving underneath it. Counted rather than flagged, because
    # "superseded" is not a boolean an operator can act on: one audit since
    # is a re-read, five is a rewrite.
    order = [r["id"] for r in conn.execute(
        "SELECT id FROM audit_runs WHERE site_id=? AND kind='audit'"
        f" AND {status_in(AUDITED_STATUSES)}"
        " ORDER BY started_at DESC, rowid DESC", (site_id,))]
    position = {run_id: i for i, run_id in enumerate(order)}

    stored = list(conn.execute(
        "SELECT id, run_ids, template, audience, path, created_at,"
        " renderer_version, supersedes FROM reports WHERE site_id=?"
        f" ORDER BY {_REPLACEMENT_ORDER}", (site_id,)))

    # The other direction of `reports.supersedes`, derived rather than stored.
    # The column is written on the *new* row so a regeneration stays one
    # INSERT and never rewrites a row describing a document a client may
    # already hold (`0028_report_supersedes.sql`); the screen needs to ask the
    # old row "were you replaced?", and this is where that costs nothing
    # because every row for the site is already in hand.
    #
    # First writer wins, and the rows arrive in `_REPLACEMENT_ORDER`, so a
    # document regenerated twice reports the newer replacement. Two rows
    # superseding one is not a state the screen can produce — it stops
    # offering the control the moment a replacement exists — but the API takes
    # `supersedes` from any caller, so the ambiguity is resolved here rather
    # than left to row order.
    #
    # The order is shared with `client_report()` rather than restated: until
    # CQ-199 was fixed this query said `created_at DESC` alone, so a
    # same-second tie fell to ascending rowid and this site named the *first*
    # replacement while the document screen named the *second*. The comment
    # above was true of the intent and false of the code.
    replaced_by: dict[str, str] = {}
    for row in stored:
        if row["supersedes"] and row["supersedes"] not in replaced_by:
            replaced_by[row["supersedes"]] = row["id"]

    out = []
    for row in stored:
        path = Path(row["path"]) if row["path"] else None
        run_ids = json.loads(row["run_ids"] or "[]")
        # The most recent audit it covers, so a comparison report is judged
        # on its newer half rather than on its baseline.
        since = [position[r] for r in run_ids if r in position]
        made_by = row["renderer_version"]
        out.append({
            "id": row["id"], "template": row["template"],
            "audience": row["audience"], "created_at": row["created_at"],
            "run_ids": run_ids,
            # Recorded and missing are different states. A row whose file has
            # been moved or cleaned up must say so rather than 404 on click.
            "on_disk": bool(path and path.exists()),
            "bytes": path.stat().st_size if path and path.exists() else None,
            "audits_since": min(since) if since else None,
            "renderer_version": made_by,
            # Three states, not two. NULL means the file predates the record,
            # so the app does not know which renderer wrote it — and calling
            # an unknown "current" is exactly how a superseded document goes
            # out looking fine.
            "renderer": ("current" if made_by == RENDERER_VERSION
                         else "unknown" if made_by is None
                         else "superseded"),
            # Which document this one replaced, and which replaced it. Both
            # directions travel with the row because the screen states both:
            # a replaced row stops being offered `regenerate` and says what
            # took its place, and the replacement says what it was made for.
            # Q-9's answer, whose whole content is that the register can say
            # which document replaced which.
            "supersedes": row["supersedes"],
            "superseded_by": replaced_by.get(row["id"]),
        })
    return out


def client_report(conn: sqlite3.Connection, report_id: str) -> dict | None:
    """One deliverable, read back from where it was written.

    Carries `superseded_by` for the same reason the register does, and on the
    same surface the register's link lands on: this screen answers "what did
    we actually tell them", and a document that has since been replaced is a
    different answer to that question from one that has not. The Deliverables
    table stops offering `regenerate` on a replaced row; a reader who opens
    the document directly reaches none of that, and would have no way to know.
    Derived rather than stored — `reports.supersedes` is written on the newer
    row, see `0028_report_supersedes.sql`.
    """
    row = conn.execute("SELECT * FROM reports WHERE id=?",
                       (report_id,)).fetchone()
    if not row:
        return None
    newer = conn.execute(
        "SELECT id FROM reports WHERE supersedes=?"
        f" ORDER BY {_REPLACEMENT_ORDER} LIMIT 1",
        (report_id,)).fetchone()
    superseded_by = newer["id"] if newer else None
    path = Path(row["path"]) if row["path"] else None
    if not path or not path.exists():
        # Absent is a real answer. Regenerating silently would hand back a
        # document that is not the one that was delivered to the client.
        return {"id": row["id"], "site_id": row["site_id"],
                "template": row["template"],
                "audience": row["audience"], "created_at": row["created_at"],
                "markdown": None, "on_disk": False,
                "supersedes": row["supersedes"],
                "superseded_by": superseded_by,
                "reason": "the file recorded for this report is no longer "
                          "on disk; regenerate to produce a new one"}
    return {"id": row["id"], "site_id": row["site_id"],
            "template": row["template"],
            "audience": row["audience"], "created_at": row["created_at"],
            "run_ids": json.loads(row["run_ids"] or "[]"),
            "markdown": path.read_text(encoding="utf-8"), "on_disk": True,
            "supersedes": row["supersedes"], "superseded_by": superseded_by,
            "path": str(path)}


def expert_report_index(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    """What has been run against this run, for marking up a tool list.

    One source, not two. It used to add a second pass over `findings` for
    briefs whose prose predated per-run report storage, marking them
    `report_retained: False` — a tool listed as run with nothing to read.
    Every brief has stored its report since, so the second pass described a
    shape that no longer exists and only kept the "report not retained"
    branch alive downstream.
    """
    out = []
    for row in conn.execute(
            "SELECT tool_id, model_id, page_url, tokens, cost, truncated,"
            " created_at, findings, contract FROM expert_reports WHERE run_id=?"
            " ORDER BY created_at DESC", (run_id,)):
        found = json.loads(row["findings"])
        contract = json.loads(row["contract"]) if row["contract"] else None
        out.append({"tool": row["tool_id"], "model": row["model_id"],
                    "page_url": row["page_url"], "tokens": row["tokens"],
                    "cost": row["cost"], "truncated": bool(row["truncated"]),
                    "created_at": row["created_at"],
                    # The contract's verdict on the answer (brief v10 step
                    # AF): `needs-input` with the questions where the brief
                    # asked instead of answering; None for a legacy brief.
                    "contract_status": (contract or {}).get("status"),
                    "questions": (contract or {}).get("questions") or [],
                    "findings": len(found),
                    "worst_severity": next((s for s in SEVERITY_ORDER
                                            if any(f.get("severity") == s
                                                   for f in found)), None)})
    return out


def expert_report_texts(conn: sqlite3.Connection, run_id: str) -> list[str]:
    """The prose of every brief stored against this run, newest first.

    For scanning the `[TO CONFIRM: …]` items out of them (F-05). Every brief
    of the run rather than one, because the operator settles a question, not
    a question-in-a-tool: the apex redirect goes unmeasured in the security
    brief and again in the crawl one, and measuring it twice to have
    it shown twice would be the same host answering the same handshake.
    """
    return [row["report"] for row in conn.execute(
        "SELECT report FROM expert_reports WHERE run_id=?"
        " ORDER BY created_at DESC", (run_id,)) if row["report"]]


def expert_findings(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM findings WHERE run_id=? AND dimension LIKE 'EXP:%'"
        " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
        " WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, dimension, rowid",
        (run_id,)).fetchall()
    return [_finding_dict(r) for r in rows]


def _run_pages_fetched(conn: sqlite3.Connection, run_id: str) -> dict:
    """A run's readable-page count and its basis, for a caller assembling a
    frame — `{"pages_fetched": …, "pages_fetched_basis": …}`, spread into it.

    Reads the run's evidence through `_scope`, which is the same derivation
    `get_run` hands the renderer. Deliberately not a second one: CQ-04 is two
    derivations of one row, and answering it with a third would be the defect
    again. Both keys are absent when the run stored no evidence, so a diff
    from such a run says nothing about a page count rather than saying null —
    the distinction `_run_scope`'s docstring draws for its own paths.
    """
    row = conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    raw = row["crawl_evidence"] if row and "crawl_evidence" in row.keys() else None
    if not raw:
        return {}
    scope = _scope(json.loads(raw))
    return {"pages_fetched": scope["pages_fetched"],
            "pages_fetched_basis": scope["pages_fetched_basis"]}


def _run_scope(conn: sqlite3.Connection, run_id: str) -> tuple[set[str] | None, set[str]]:
    """(paths this run fetched, dimensions it ran). Paths is None when unknown.

    NULL means the run predates the `crawled_paths` column, or a caller wrote
    no scope. Unknown is not empty: empty says "fetched nothing", which is a
    real and different answer.
    """
    from urllib.parse import urlsplit

    row = conn.execute(
        "SELECT crawled_paths, dimensions, crawl_evidence FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    if row is None:
        return None, set()
    dims = set(json.loads(row["dimensions"] or "[]"))

    raw = row["crawled_paths"] if "crawled_paths" in row.keys() else None
    if raw:
        return set(json.loads(raw)), dims

    # Every run stored before 0021 has no column value. Most of them do carry
    # the same fact in `crawl_evidence.pages`, written by `store_evidence`, so
    # read it rather than declaring the whole existing history unknowable —
    # which would have made this fix apply only to audits not yet run.
    blob = row["crawl_evidence"] if "crawl_evidence" in row.keys() else None
    if blob:
        pages = (json.loads(blob) or {}).get("pages")
        # `is not None`, not truthiness. Evidence recording `pages: []` is a
        # run saying it fetched nothing, which is the docstring's distinction
        # above and the opposite of never having said. Under `if pages:` that
        # run returned None, and the compare screen rendered the one case with
        # a decisive answer as "an unrecorded number of page(s)".
        if pages is not None:
            return ({urlsplit(pg.get("url") or "").path or "/"
                     for pg in pages if isinstance(pg, dict)}, dims)
    return None, dims


#: How many paths a reason names before it summarises the rest.
_PATHS_SHOWN = 3


def _reason(lead: str, paths=(), overflow: int = 0) -> dict:
    """A reason as parts: `{lead, paths, overflow}`.

    **Parts, not a sentence, because three layers were parsing each other.**
    This value was a formatted string built for one consumer — the client
    document — with backticked paths so `checks.py` would exempt them as
    identifiers and a `(source: …)` clause on the overflow count. The compare
    screen then *reversed* that formatting with three chained regexes so a
    reader would not see backticks, and one of the three matched nothing. A
    format contract spanning persistence, a markdown gate and a React view,
    asserted at neither end, with `tsc` unable to see a change to the phrase.

    So persistence states the facts and each surface formats them:
    `render.py::_reason_markdown` for the document, `views.tsx` for the
    screen. Neither reads the other's output, which is the only version of
    this that a test can hold still.

    `overflow` is a count, not a rendering: how many further paths exist
    beyond the ones named. Whether it appears as "(+8 more)" and whether that
    figure needs a provenance tag are questions about a surface, and they are
    answered where the surface is.
    """
    return {"lead": lead, "paths": list(paths), "overflow": overflow}


def _unfetched_reason(lead: str, paths: set[str]) -> dict:
    """The pages a run did not fetch — the first few by name, the rest counted.

    One helper rather than the same expression in `why_not` and `why_new`.
    They were written a commit apart and the second copied the first, defect
    included, which is how a fault that had been in the not-re-checked side
    since renderer 1.13.0 arrived on the new side too.
    """
    shown = sorted(paths)[:_PATHS_SHOWN]
    return _reason(lead, shown, max(0, len(paths) - _PATHS_SHOWN))


def _paths_of(finding: dict) -> set[str]:
    """The paths a finding is about, normalised to match `crawled_paths`."""
    from urllib.parse import urlsplit
    out = set()
    for url in finding.get("affected_urls") or []:
        path = urlsplit(url).path or "/"
        out.add(path)
    return out


def compare_runs(conn: sqlite3.Connection, run_a: str, run_b: str) -> dict:
    """Diff two runs by fingerprint: new (only in B), resolved (only in A and
    re-checked by B), not_rechecked (only in A because B never looked),
    persisting (both). A is the earlier baseline by convention.

    A finding absent from B means one of two things, and reading it as the
    first cost this product its core claim twice.

    `resolved` was a bare set-difference, `a.keys() - b.keys()`. A narrower
    crawl makes almost everything absent: on stored data, a 20-page follow-up
    to a 100-page baseline reported **352 resolved** where 5 had been
    re-checked, in green, at `confidence: high`, in a document sent to a
    client (round 022).

    The first correction read `finding_states`, and was wrong in both
    directions (round 023). That table holds one row per site and fingerprint
    describing the state *now*, not as of B — so a third, later audit rewrote
    what this pair's comparison said, and it could not tell that run B had
    resolved something a still-later run has since regressed. Its vocabulary
    has five values, so a negative filter admitted `accepted-risk`: a finding
    the operator decided explicitly **not** to fix, counted as fixed.

    So ask the only thing that answers the question — what did B fetch. That
    is what `_apply_states` has always used, and it depends on nothing that
    can change afterwards, which is what makes a comparison reproducible: the
    same pair compared again tomorrow answers the same way, so the document
    already rendered from it keeps its meaning. Nothing keeps the diff itself
    — both callers compute it and discard it — and that is why stability has
    to come from the inputs.
    """
    # Same site first, before a single finding is read. Nothing asked this:
    # not the route, not this function, and not `generate()`, which takes
    # `run_dicts[0]["site_id"]` for the document's heading — so a comparison
    # deliverable spanning two clients was generable and went out under the
    # first one's domain. Measured on the live service: eight findings whose
    # `affected_urls` were one client's, returned as resolved against a run
    # belonging to another. Here rather than at the route because the route is
    # one of two callers and the other one writes the artefact that leaves the
    # building — the same reasoning `generate()` records for its blocked-run
    # refusal, which is also a ValueError the route maps to 422.
    # Deferred for the reason every `clauditseo.reporting` import in this
    # module is deferred: persistence is imported by reporting, so a
    # module-level import here closes the cycle. The key this function writes
    # its frame under is owned there because that is where it is read from —
    # CQ-204, which was the writer spelling it by hand while the constant's
    # own comment claimed nothing could.
    from clauditseo.reporting.render import DIFF_SCOPE_KEY

    scope_rows = {r["id"]: r for r in conn.execute(
        "SELECT id, site_id, status, kind, scan_scope, crawled_paths"
        " FROM audit_runs WHERE id IN (?, ?)",
        (run_a, run_b)).fetchall()}
    site_a = (scope_rows.get(run_a) or {"site_id": None})["site_id"]
    site_b = (scope_rows.get(run_b) or {"site_id": None})["site_id"]
    if site_a != site_b:
        raise ValueError(
            f"Runs {run_a[:8]} and {run_b[:8]} belong to different sites "
            f"({site_a} and {site_b}). A comparison answers 'did this site's "
            "findings get fixed', which has no meaning across two of them.")

    a = {f["fingerprint"]: f for f in run_findings(conn, run_a)
         if f["source"] == "deterministic"}
    b = {f["fingerprint"]: f for f in run_findings(conn, run_b)
         if f["source"] == "deterministic"}

    gone = a.keys() - b.keys()
    crawled, dims_b = _run_scope(conn, run_b)
    b_blocked = (scope_rows.get(run_b) or {"status": None})["status"] == "blocked"
    # Whether each run may be generalised to the site, which is a fourth
    # question `why_not` and `why_new` never asked. `_apply_states` has asked
    # it since the refresh landed; this function is the other rule that
    # decides whether a finding is gone, and the two disagreeing about one
    # finding is the defect the whole `why_not` rewrite exists to remove.
    b_wide = bool(scope_rows.get(run_b)) and reads_site(scope_rows[run_b])
    crawled_a, dims_a = _run_scope(conn, run_a)
    a_blocked = (scope_rows.get(run_a) or {"status": None})["status"] == "blocked"
    a_wide = bool(scope_rows.get(run_a)) and reads_site(scope_rows[run_a])

    def why_not(fp: str) -> str | None:
        """None when B re-checked it; otherwise the reason, derived.

        The reason is computed here rather than written as prose at the
        render site, because a sentence asserting one cause for a bucket
        defined by three of them is wrong for two of its members — which is
        what "outside what this run crawled" was for a page the run *did*
        fetch under a dimension it did not audit.

        One order, asked of every finding — blocked, then dimension, then
        page. The defect this replaces was two orders: the dimension question
        was asked only of site-level findings, so a page-scoped finding whose
        dimension B never ran came back resolved as soon as B refetched its
        page. `_apply_states` refuses that case (`dimension not in dims`), so
        the two rules the previous correction set out to unify ended up
        disagreeing in the opposite direction to the one it fixed.
        """
        f = a[fp]
        if b_blocked:
            # `complete_run` stores `json.dumps([])` for a blocked run and
            # `"[]"` is truthy, so scope came back as an empty set — "fetched
            # nothing" — and a site-level finding then only had to clear the
            # dimension test, which a blocked run passes. `_apply_states`
            # returns before clearing anything on a blocked run; this is that
            # rule, asked where the comparison can see it.
            return _reason("this run's crawl was blocked, so it fetched no pages")
        dim = f.get("dimension")
        if dim not in dims_b:
            return _reason(f"{dim} was not audited by this run")
        if crawled is None:
            # Above the site-level shortcut below, not after it. Putting it
            # after — which is where the previous round's reorder left it —
            # asked this of page-scoped findings only, so a site-level finding
            # from a run that recorded no scope came back resolved. The test
            # written for this state used two page-scoped findings and stayed
            # green through it.
            return _reason("this run did not record what it crawled")
        paths = _paths_of(f)
        if not paths:
            # Site-level: names no page, so the questions above are the whole
            # test — *if* this run read the site. A verification fetches the
            # handful of pages behind named findings, so "the dimension ran"
            # says nothing about a claim covering every page. Executed
            # against the live database before this clause existed, the
            # 224-page audit against the eight-page verification of
            # `www.acme.com.au` returned `resolved: 15`.
            #
            # The same rule `_apply_states` applies when `narrow` is set, and
            # asked in the same order, so the comparison document and the
            # lifecycle table cannot answer it differently.
            if not b_wide:
                return _reason(
                    "this finding names no page, and this run read a named "
                    "handful of pages rather than the site")
            return None
        # ANY overlap, not full containment — because `_apply_states` uses
        # `pages & crawled` and it is the rule that wrote the stored states.
        # Requiring containment here made the comparison disagree with the
        # lifecycle table about two findings run B had genuinely cleared, and
        # two rules answering one question is the defect this whole change
        # exists to remove. Verified against stored data: all five findings
        # `finding_states` records as fixed carry `changed_by_run` = run B.
        #
        # Residual, recorded rather than silently third-guessed: on a finding
        # spanning five pages where the run fetched one, both rules call it
        # re-checked. That is the same over-claim in miniature and belongs to
        # `_apply_states`, not here; fixing it here alone would reintroduce
        # the disagreement.
        if paths & crawled:
            return None
        return _unfetched_reason("not fetched by this run", paths)

    def why_new(fp: str) -> str | None:
        """None when the baseline was in a position to see it; else the reason.

        The mirror of `why_not`, and it exists for the same reason in the
        other direction. `new` was `b.keys() - a.keys()`, which asks whether
        the baseline *reported* a finding and never whether it *looked*. A
        first audit at 20 pages followed by a full one at 100 therefore
        reports eighty pages of pre-existing findings as new — under
        `## New issues` in a document sent to the client, and in red on the
        compare screen. The product telling a fee-paying reader that the work
        made things worse.

        Same order as `why_not`, asked of the baseline: blocked, then
        dimension, then page. Kept identical deliberately — the two buckets
        are one question asked from either end, and the last time they were
        allowed to diverge they ended up disagreeing about the same finding.
        """
        f = b[fp]
        if a_blocked:
            return _reason("the baseline's crawl was blocked, so it fetched no pages")
        dim = f.get("dimension")
        if dim not in dims_a:
            return _reason(f"{dim} was not audited by the baseline")
        if crawled_a is None:
            return _reason("the baseline did not record what it crawled")
        paths = _paths_of(f)
        if not paths:
            # The mirror, kept identical on purpose — the note on `why_not`
            # about the two buckets being one question asked from either end
            # applies to this clause as much as to the three above it.
            if not a_wide:
                return _reason(
                    "this finding names no page, and the baseline read a "
                    "named handful of pages rather than the site")
            return None
        if paths & crawled_a:
            return None
        return _unfetched_reason("not fetched by the baseline", paths)

    reasons = {fp: why_not(fp) for fp in gone}

    def tagged(fp: str) -> dict:
        return {**a[fp], "not_rechecked_reason": reasons[fp]}

    return {
        # `new_reason` is present on every entry and `None` on most: a
        # consumer that reads it has one shape to handle, and a finding the
        # baseline could see is new to the site with no qualifier — saying
        # otherwise would be the same over-claim pointing the other way.
        "new": [{**b[fp], "new_reason": why_new(fp)}
                for fp in b.keys() - a.keys()],
        "resolved": [a[fp] for fp in gone if reasons[fp] is None],
        "not_rechecked": [tagged(fp) for fp in gone if reasons[fp] is not None],
        "persisting": [b[fp] for fp in a.keys() & b.keys()],
        # WF-02: the diff carries the scope it was computed under, so no
        # surface has to restate it and none can restate it differently.
        #
        # CQ-04: both counts, because there are two and they are not the same
        # quantity. `pages_crawled` is the distinct paths run B touched — the
        # figure the buckets above are decided by, since `why_not` and
        # `why_new` ask whether a finding's *path* was crawled. `pages_fetched`
        # is how many pages a check could read, which is the figure the
        # coverage ratio beside the composite is computed from. A site serving
        # one page under two URL forms makes them differ, and until this round
        # the document stated one of them and the ratio the other, four lines
        # apart, both under the word "fetched".
        #
        # WF-28 and UX-22, which report 091 pairs as one residue seen from two
        # sides. Three of the four counts above are decided by run B and are
        # framed by the keys on the line below. `new` and `resolved` are not:
        # `why_new` and `why_not` read `crawled_a` and `dims_a`, so a finding
        # is new when the baseline was in a position to see it and did not.
        # Those two values were computed twenty lines up and dropped on the
        # floor, and the count they decide reached a client with its frame
        # nowhere on the page — `## New issues — 825` against a baseline that
        # had crawled 99 paths, measured on `8fdeb042` in report 091.
        #
        # Every baseline key carries the `_baseline` suffix rather than a
        # `baseline_` prefix, so the two frames sort together per quantity
        # and a reader comparing them is not reading down two lists.
        DIFF_SCOPE_KEY: {
            "pages_crawled": None if crawled is None else len(crawled),
            **_run_pages_fetched(conn, run_b),
            "dimensions": sorted(dims_b),
            "pages_crawled_baseline":
                None if crawled_a is None else len(crawled_a),
            **{f"{key}_baseline": value for key, value
               in _run_pages_fetched(conn, run_a).items()},
            "dimensions_baseline": sorted(dims_a)},
    }


#: The run kinds a `PRIOR_RUN` may be, per `_CONTRACT.md`.
#:
#: **Deliberately wider than `SITE_READING_KINDS`, and the difference is the
#: point.** That constant answers "may this run's RESULT be generalised to the
#: site" - scored onto the trend, counted as the latest audit. This one answers
#: "may this run's stored EVIDENCE be read as what the site looked like last
#: time". A re-check re-reads the site's record, so it can answer the second
#: while still having no business answering the first (operator ruling,
#: 2026-09-07).
#:
#: An allow-list for the same reason as its neighbour: the day someone adds a
#: kind they have to come to this line and say which of the two questions it
#: may answer, rather than inheriting an answer nobody chose for it.
PRIOR_RUN_KINDS = ("audit", "refresh")

#: The `scan_scope` values that crawled the whole site. `page` is the narrow
#: one the contract excludes.
#:
#: NULL is not in this set and does not need to be: every `refresh` row stores
#: NULL here and every `audit` row stores a real value, so `kind` already
#: decides those and no run is left with an unrecorded extent. Checked on the
#: live database, 2026-09-07: 27 rows, NULL scope on exactly the 7 refreshes.
PRIOR_RUN_SCOPES = ("site", "full")


def _snippet(title, meta_description):
    from clauditseo.modules.onp import snippet

    return snippet(title, meta_description)


def title_lengths_payload(conn: sqlite3.Connection,
                          run_id: str | None) -> dict | None:
    """Every page's title and description width, in crawl order (brief v16i
    Part C).

    One bar per page per strip. The width and the state are `onp.snippet`'s,
    the same function the checks and the page-scope card read - the strips
    cannot disagree with the card a bar opens onto.

    In crawl order, not sorted: the strip's whole argument is "where on the
    site do the long ones cluster", and a sorted strip answers a different
    question. `first crawled ... last crawled` is the axis.
    """
    if not run_id:
        return None
    from urllib.parse import urlsplit

    from clauditseo.modules.onp import GUIDELINES, cut_of, snippet

    evidence_raw = evidence_text(conn, run_id)
    if not evidence_raw:
        return None
    try:
        pages = (parsed_evidence(evidence_raw) or {}).get("pages") or []
    except (TypeError, ValueError):
        return None
    pages = [p for p in pages if p.get("status") == 200
             and (p.get("content_type") or "text/html").startswith("text/html")]
    if not pages:
        return None

    bars = []
    for p in pages:
        snip = snippet(p.get("title"), p.get("meta_description"))
        # The whole snippet field per side, not just px + state: the strip's
        # detail panel draws the same result card Part B draws (item 146), and
        # it reads the text, the fall-off words and the character count from
        # here rather than re-fetching per hover. `snippet` already measured
        # them, so carrying them is free of a second measurement.
        bars.append({
            "url": p.get("url"),
            "path": urlsplit(p.get("url") or "/").path or "/",
            "title": snip["title"],
            "description": snip["description"],
        })
    return {
        "pages": len(bars),
        "bars": bars,
        # The width each check fires at and its viewport (item 152), from the
        # one helper the checks read, so the strip cannot draw another cut.
        "title_cut_px": cut_of(GUIDELINES["title"])[0],
        "title_cut_viewport": cut_of(GUIDELINES["title"])[1],
        "desc_cut_px": cut_of(GUIDELINES["meta_description"])[0],
        "desc_cut_viewport": cut_of(GUIDELINES["meta_description"])[1],
    }


#: A heading with fewer than this many words under it, before the next
#: heading of equal or higher level, is `thin` (item 136o Part A).
THIN_WORD_FLOOR = 50

#: The share of a run's rendered pages a block must appear on to be
#: boilerplate. The item's number.
BOILERPLATE_SHARE = 0.90

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def _screens_for_run(conn, run_id) -> dict[str, dict]:
    """Every page the rendered pass photographed, `{url: shot}`, off the A11Y
    rows that record it. One reader for the Accessibility overlay and the
    Content tab's (item 245): the boxes on both come from the same render as
    the picture, so they share its coordinates."""
    screens: dict[str, dict] = {}
    for r in conn.execute("SELECT evidence FROM findings WHERE run_id=? AND dimension='A11Y'",
                          (run_id,)):
        try:
            ev = json.loads(r["evidence"] or "{}")
        except ValueError:
            continue
        if ev.get("screens"):
            screens.update(ev["screens"])
    return screens


def _screen_of(run_id: str, page_url: str, shot: dict) -> dict:
    """The picture's address and the document size its boxes were measured in."""
    from clauditseo import axe
    return {"screenshot": (f"/api/runs/{run_id}/screens/{axe.page_hash(page_url)}.png")
                          if shot.get("screenshot_path") else None,
            "doc": {"w": shot.get("screenshot_w") or 0, "h": shot.get("screenshot_h") or 0}}


def _text_blocks_for_run(conn, run_id):
    """Every rendered page's stored text blocks, `{url: [block, ...]}`.

    Read off whichever A11Y row carries them - the `axe-sampled` coverage
    row, or the coverage note when the whole crawl was rendered. One place
    writes them (item 136o Part A) so one place reads them.
    """
    rows = conn.execute(
        "SELECT evidence FROM findings WHERE run_id=? AND dimension='A11Y'",
        (run_id,)).fetchall()
    for r in rows:
        try:
            ev = json.loads(r["evidence"] or "{}")
        except ValueError:
            continue
        if ev.get("text_blocks"):
            return ev["text_blocks"]
    return {}


#: Schema types that DECLARE an entity, per 136o Tab 4. A node of another
#: type that happens to carry the name is not a declaration.
_DECLARING_TYPES = ("service", "person", "localbusiness", "place",
                    "organization")


def entity_matrix_payload(conn: sqlite3.Connection, run_id: str | None,
                          site) -> dict | None:
    """The site's entities against where each is named (item 136o Tab 4).

    Rows are the record's own entities - each sub-service, the location, the
    service area, each author, the brand - plus every Coverage `gap` node.
    Columns are page counts: URL, Title, H1, Anchors (pages whose internal
    anchor text names it), Schema (nodes declaring it), Map (a Coverage node).
    Body is added when a body-text signal exists (a separate decision); until
    then it is omitted rather than shown as a false zero.

    **The row verdict is the engine's, and it does not depend on Body:**
    owned (>= 1 page names it in URL AND Title AND H1), mentioned (named
    somewhere, no page owns it), absent (zero everywhere). The same
    URL+Title+H1 rule `CNT/entity-page-verdict` uses, so the matrix and the
    per-page verdict cannot disagree.

    Matching is case-insensitive, whole-word, on the name and any recorded
    aliases; no stemming beyond a trailing plural `s`. Stated in the report.
    """
    if not run_id or site is None:
        return None
    from clauditseo.modules.links import _entity_rows, _mentions, _visible

    evidence_raw = evidence_text(conn, run_id)
    if not evidence_raw:
        return None
    try:
        pages = [pp for pp in (parsed_evidence(evidence_raw) or {}).get("pages")
                 or [] if pp.get("status") == 200]
    except (TypeError, ValueError):
        return None

    entities, _no_hub = _entity_rows(site)
    named = [{"entity": e["entity"], "kind": e["kind"], "hub": e.get("hub") or ""}
             for e in entities]

    # Coverage gap nodes become rows too - the other axis of the map. Read
    # from the run's own findings so the matrix and Coverage agree on what a
    # gap is.
    have = {e["entity"].lower() for e in named}
    gap_pages: dict[str, set] = {}
    for f in conn.execute(
            # `gap` is content-coverage's, and Q-56 moved it to
            # `EXP:content-coverage`; both are matched so the matrix reads the
            # same before and after the migration (and on a run stored either
            # way). `gap` is this one brief's, so the check id alone is the row.
            "SELECT check_id, summary, evidence, affected_urls FROM findings"
            " WHERE run_id=? AND check_id='gap'"
            "   AND dimension IN ('CNT', 'EXP:content-coverage')", (run_id,)):
        try:
            ev = json.loads(f["evidence"] or "{}")
        except ValueError:
            ev = {}
        node = (ev.get("node") or ev.get("entity") or "").strip()
        if node and node.lower() not in have:
            named.append({"entity": node, "kind": "from Coverage \u00b7 gap"})
            have.add(node.lower())
        if node:
            gap_pages.setdefault(node.lower(), set())

    aliases = getattr(site, "entity_variants", None) or {}

    def names_of(entity):
        return [entity] + list(aliases.get(entity, []) or [])

    def any_named(text, entity):
        return any(_mentions(text, n) for n in names_of(entity))

    from clauditseo.modules.cnt import _URL_STOPWORDS
    from urllib.parse import urlsplit

    def named_in_url(page_url, ent):
        """The same rule `CNT/entity-page-verdict` uses: the page IS the
        entity's hub, or a significant word of the name is in the slug. A
        slug rarely carries a multi-word name whole, so a whole-phrase test
        would call every hub page 'not owned'."""
        hub = ent.get("hub") or ""
        try:
            if hub and (urlsplit(hub).path or "/").rstrip("/").lower()                     == (urlsplit(page_url).path or "/").rstrip("/").lower():
                return True
        except ValueError:
            pass
        slug = (urlsplit(page_url).path or "/").replace("-", " ").replace("_", " ").lower()
        for alias in names_of(ent["entity"]):
            words = [w for w in alias.lower().split()
                     if w not in _URL_STOPWORDS and len(w) > 2]
            if any(_mentions(slug, w) for w in words):
                return True
        return False

    if not named:
        # No entities on the record and no Coverage gaps: the tab shows its
        # absent-state ("set the record's entities") rather than an empty
        # table. `None`, not a matrix with no rows.
        return None
    pages_with_opening = sum(1 for pp in pages if pp.get("opening"))
    rows = []
    for ent in named:
        name = ent["entity"]
        url_hits = title_hits = h1_hits = anchor_hits = schema_hits = 0
        body_hits = 0
        owned_pages = []
        for pp in pages:
            title = pp.get("title") or ""
            h1 = pp.get("h1") or ""
            in_url = named_in_url(pp.get("url") or "", ent)
            # Body: the page's own prose, from what the crawl stores on every
            # page - the opening sixty words where present, and the forty
            # words the outline keeps after each heading. NOT the rendered
            # block names (which exist for the sampled pages only), so the
            # count is uniform across crawled pages rather than making the
            # five rendered ones look entity-rich by construction. Undercounts
            # a mention buried past those windows; the note says so, and the
            # verdict does not depend on it.
            body = pp.get("opening") or ""
            for entry in (pp.get("outline") or []):
                if len(entry) > 3 and entry[3]:
                    body += " " + str(entry[3])
            in_title = any_named(title, name)
            in_h1 = any_named(h1, name)
            url_hits += 1 if in_url else 0
            title_hits += 1 if in_title else 0
            h1_hits += 1 if in_h1 else 0
            if in_url and in_title and in_h1:
                owned_pages.append(pp.get("url"))
            if any_named(body, name):
                body_hits += 1
            # Anchors: any internal anchor whose text names the entity.
            for lk in (pp.get("links") or []):
                if any_named(lk.get("anchor") or "", name):
                    anchor_hits += 1
                    break
            # Schema: a declaring node whose name matches.
            for node in (pp.get("schema_inventory") or []):
                t = str(node.get("type") or "").lower()
                nm = str((node.get("properties") or {}).get("name") or "")
                if t in _DECLARING_TYPES and any_named(nm, name):
                    schema_hits += 1
                    break

        in_map = ent["kind"].startswith("from Coverage") or name.lower() in gap_pages
        cells = {"url": url_hits, "title": title_hits, "h1": h1_hits,
                 "body": body_hits, "anchors": anchor_hits,
                 "schema": schema_hits, "map": 1 if in_map else 0}
        anywhere = any(cells.values())
        verdict = ("owned" if owned_pages else "mentioned" if anywhere else "absent")
        rows.append({
            "entity": name, "kind": ent["kind"],
            "cells": cells, "verdict": verdict,
            "owned_by": owned_pages[0] if owned_pages else None,
        })

    summ = {
        "entities": len(rows),
        "owned": sum(1 for r in rows if r["verdict"] == "owned"),
        "mentioned": sum(1 for r in rows if r["verdict"] == "mentioned"),
        "absent": sum(1 for r in rows if r["verdict"] == "absent"),
        "with_schema": sum(1 for r in rows if r["cells"]["schema"] > 0),
    }
    return {
        "rows": rows,
        "summary": summ,
        "reading": _matrix_reading(rows, summ),
        "columns": ["url", "title", "h1", "body", "anchors", "schema", "map"],
        "matcher": "case-insensitive whole-word on name and recorded aliases; "
                   "plural s only",
        "body_basis": (f"from each page's opening and the text after its "
                       f"headings ({pages_with_opening} of {len(pages)} pages "
                       "carry an opening); a mention buried past those windows "
                       "is not counted"),
    }


def _matrix_reading(rows, summ) -> str:
    """The generated sentence beneath the matrix (item 136o Tab 4).

    Leads with Schema where every service is owned and none is declared -
    the cross-reference Structured data raises from the other side - else
    with the first absent service, else with a mentioned-not-owned place.
    """
    services = [r for r in rows if r["kind"] in ("sub_services", "service", "sub-service")]
    owned_services = [r for r in services if r["verdict"] == "owned"]
    if services and len(owned_services) == len(services) and summ["with_schema"] == 0:
        people = [r for r in rows if r["kind"] == "authors"]
        tail = (f"; {len(people)} people carry E-E-A-T and none has a Person node"
                if people else "")
        return ("every service is owned by a page and none is declared as a "
                f"Service{tail} \u2014 the same finding Structured data raises "
                "from the other side.")
    absent_service = next((r for r in services if r["verdict"] == "absent"), None)
    if absent_service:
        return (f"{absent_service['entity']} is a service on the record and no "
                "page names it in its URL, title and H1.")
    place = next((r for r in rows if r["kind"] in ("locations", "location")
                  and r["verdict"] == "mentioned"), None)
    if place:
        return (f"{place['entity']} is mentioned but no page owns it \u2014 a "
                "location without a page of its own.")
    return "every named entity is owned by a page."


def page_entity_verdict(conn: sqlite3.Connection, run_id: str | None,
                        page_url: str) -> dict | None:
    """One page's entity verdict, from the `CNT/entity-page-verdict` finding
    the run already emitted (item 136o Tab 4, page scope).

    Read from the finding rather than recomputed: the check is the one
    definition of what a page is about, so the tab and the record cannot
    disagree - the same reason the site matrix reuses the check's rule.
    """
    if not run_id or not page_url:
        return None
    from urllib.parse import urlsplit
    want = (urlsplit(page_url).path or "/").rstrip("/").lower()
    for r in conn.execute(
            "SELECT summary, evidence, affected_urls FROM findings"
            " WHERE run_id=? AND dimension='CNT' AND check_id='entity-page-verdict'",
            (run_id,)):
        for u in json.loads(r["affected_urls"] or "[]"):
            if (urlsplit(u).path or "/").rstrip("/").lower() == want:
                try:
                    ev = json.loads(r["evidence"] or "{}")
                except ValueError:
                    ev = {}
                return {"verdict": ev.get("verdict"), "status": ev.get("status"),
                        "entities": ev.get("entities") or [],
                        "about": ev.get("about"), "owns": ev.get("owns"),
                        "contested": ev.get("contested") or []}
    return None


def content_blocks_payload(conn: sqlite3.Connection, run_id: str | None,
                           page_url: str) -> dict | None:
    """One page's text blocks, classified, with the page's totals.

    **The classes are what the run already knows, not a new judgement.**
    `boilerplate` is a landmark block or one that repeats across the run;
    `shared` is `duplicate-content`'s data at block grain - the same hash on
    another page - and it names those pages; `thin` is a heading with too few
    words under it; `unique` is the rest. Every hash is `cnt.content_hash`,
    the one the site-wide index uses, so `shared` and the check cannot
    disagree about whether two pages carry the same paragraph.
    """
    if not run_id or not page_url:
        return None
    blocks_by_page = _text_blocks_for_run(conn, run_id)
    if not blocks_by_page:
        return None
    mine = blocks_by_page.get(page_url)
    if mine is None:
        # The page was crawled but not rendered: the overlay says so rather
        # than drawing an empty page.
        return {"rendered": False, "pages_rendered": len(blocks_by_page)}

    # How many of the run's rendered pages each hash appears on.
    seen: dict[str, set] = {}
    for url, blocks in blocks_by_page.items():
        for b in blocks:
            seen.setdefault(b.get("hash", ""), set()).add(url)
    total_pages = len(blocks_by_page)

    classed = []
    for b in mine:
        h = b.get("hash", "")
        on = seen.get(h, {page_url})
        others = sorted(u for u in on if u != page_url)
        landmark = b.get("landmark") or "none"
        why = None
        if landmark in ("header", "nav", "footer"):
            klass, why = "boilerplate", "landmark"
        elif total_pages and len(on) / total_pages >= BOILERPLATE_SHARE:
            klass, why = "boilerplate", "repeated"
        elif len(on) >= 2:
            klass = "shared"
        else:
            klass = "unique"
        # Item 245: which rule made it furniture, and over how many of the
        # rendered pages, so the row can say "repeated on 44 of 45 pages"
        # rather than a bare "site furniture".
        classed.append({**b, "klass": klass, "other_pages": others,
                        "boilerplate_why": why, "on_pages": len(on)})

    _mark_thin(classed)

    # `thin` is a marker on a heading, not a word class, and is excluded from
    # every sum (the item is explicit). So all four totals draw from the
    # non-thin blocks, and `words` = unique + shared by construction.
    counted = [b for b in classed if not b.get("thin")]
    uniq = sum(b.get("words", 0) for b in counted if b["klass"] == "unique")
    shared = sum(b.get("words", 0) for b in counted if b["klass"] == "shared")
    boiler = sum(b.get("words", 0) for b in counted if b["klass"] == "boilerplate")
    words = uniq + shared
    allw = uniq + shared
    return {
        "rendered": True,
        "pages_rendered": total_pages,
        # The rendered pass's picture of this page (item 245): the regions'
        # rects were measured in the same render.
        **_screen_of(run_id, page_url, _screens_for_run(conn, run_id).get(page_url) or {}),
        "blocks": classed,
        "totals": {
            "words": words, "unique": uniq, "shared": shared,
            "boilerplate": boiler,
            "unique_pct": round(100 * uniq / allw) if allw else 0,
        },
    }


def _mark_thin(blocks: list) -> None:
    """Flag each heading with fewer than THIN_WORD_FLOOR words of
    non-boilerplate text before the next heading of equal or higher level.

    Structural, from the captured blocks in document order. The item said
    "same detector as question-unanswered", but that is a MODEL check about
    whether a question is answered, a different thing from "too few words
    under a heading" - so thin is computed from the outline the run already
    has, and the difference is stated in the report rather than papered over.
    """
    def level(tag):
        return int(tag[1]) if tag in _HEADING_TAGS else 0

    for i, b in enumerate(blocks):
        lv = level(b.get("tag", ""))
        if lv == 0 or lv == 1:                 # only h2-h6 can be thin
            continue
        run = 0
        for nxt in blocks[i + 1:]:
            nl = level(nxt.get("tag", ""))
            if nl and nl <= lv:                # next equal-or-higher heading
                break
            if nxt["klass"] != "boilerplate":
                run += nxt.get("words", 0)
        b["thin"] = run < THIN_WORD_FLOOR


def prior_run(conn: sqlite3.Connection, site_id: str,
              before_run: str | None = None) -> dict | None:
    """The previous site-wide run of this site, whatever its tier or engine.

    The contract's `PRIOR_RUN`. **The run before this one in TIME, not the
    nearest run on the same basis** - that second relation belongs to the
    Score trend, is named `partner_run_id` there, and conflating them is what
    this function exists to stop. On the operator's own data the two resolve
    to different runs, which is the shape the test fixture reproduces.

    Excluded: page scans (`scan_scope='page'`), blocked runs, and runs that
    finished without a score. An unscored run is one whose result nobody can
    read, so reading its evidence as "what the site looked like last time"
    would compare against a state the record never accepted.

    `None` where there is no such run. The caller must treat that as "cannot
    answer" and not as "unchanged" - the contract says so, because reporting
    half of a two-condition rule as the whole is the over-firing the second
    condition exists to stop.
    """
    kinds = ",".join("?" * len(PRIOR_RUN_KINDS))
    scopes = ",".join("?" * len(PRIOR_RUN_SCOPES))
    row = conn.execute(
        "SELECT id, tier, engine_version, dimensions, kind, scan_scope,"
        " COALESCE(started_at, created_at) AS captured_at"
        " FROM audit_runs"
        f" WHERE site_id=? AND kind IN ({kinds})"
        # A refresh records no scope of its own; an audit must have crawled
        # the whole site. Written as one clause rather than two queries so
        # the ordering below is over a single eligible set.
        f" AND (kind='refresh' OR scan_scope IN ({scopes}))"
        f" AND {status_in(('complete',))}"
        " AND composite_score IS NOT NULL"
        # BEFORE the reference run, not merely "not it". Excluding by id
        # alone and taking the newest of the rest returns a run that came
        # AFTER, whenever the reference is not the newest - which is exactly
        # what a check reading history does when it asks about an older run.
        # Ordered by the same expression the comparison uses, with `rowid` as
        # the tiebreak for two runs that share a timestamp.
        + (" AND (COALESCE(started_at, created_at),  rowid) <"
           "     (SELECT COALESCE(started_at, created_at), rowid"
           "        FROM audit_runs WHERE id=?)" if before_run else "")
        + " ORDER BY COALESCE(started_at, created_at) DESC, rowid DESC"
        " LIMIT 1",
        (site_id, *PRIOR_RUN_KINDS, *PRIOR_RUN_SCOPES,
         *((before_run,) if before_run else ()))).fetchone()
    if not row:
        return None
    try:
        dims = json.loads(row["dimensions"]) or []
    except (TypeError, ValueError):
        dims = []
    return {"run_id": row["id"], "captured_at": row["captured_at"],
            "tier": row["tier"], "engine_version": row["engine_version"],
            "dimensions": list(dims)}


def content_hashes(conn: sqlite3.Connection,
                   run_id: str | None) -> dict[str, str] | None:
    """What one run recorded as each page's content hash.

    Split out of `prior_content_hashes` at item 136p, which deleted that
    function. The two questions it answered - WHICH run is the previous one,
    and WHAT did it record - are now separate, because the first has an
    owner: `prior_run`, the contract's `PRIOR_RUN`. Answering both here was
    how `stale` came to compare against a different set of runs than the
    contract defines: this selected `kind='audit'`, which excludes a refresh
    (the contract includes it) and includes a page scan (the contract does
    not).

    `None` where the run stored no evidence, or stored it before the hash
    existed. That is not an empty map, and `stale` treats it as "cannot
    answer" rather than "unchanged" - reporting half of a two-condition rule
    as the whole is the over-firing the second condition exists to stop.
    """
    if not run_id:
        return None
    evidence_raw = evidence_text(conn, run_id)
    if not evidence_raw:
        return None
    try:
        blob = parsed_evidence(evidence_raw) or {}
    except (TypeError, ValueError):
        return None
    hashes = {p["url"]: p["content_hash"]
              for p in (blob.get("pages") or [])
              if isinstance(p, dict) and p.get("url") and p.get("content_hash")}
    return hashes or None


#: The AI surface brief's row payload fields (`ai-surface.md` FORMAT): what a
#: fix card draws beyond `replacement`.
AIS_ROW_PAYLOAD = ("candidates", "required_sections", "profiles", "criteria",
                   "type_delta", "jsonld_delta", "omitted", "lines", "uas")


def site_states(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT fs.fingerprint, fs.state, fs.updated_at, fs.changed_by_run,"
        " fs.attempted_at, fs.attempt_note,"
        " f.dimension, f.check_id, f.severity, f.summary, f.affected_urls,"
        # Needed by the fix loop: a brief's finding is judged by re-running
        # the brief, so a crawl cannot verify it and it gets no tick.
        " f.source, f.recommendation, f.evidence, f.run_id AS finding_run"
        " FROM finding_states fs"
        f" JOIN findings f ON f.rowid = ({_latest_finding()})"
        " WHERE fs.site_id=?"
        " ORDER BY CASE fs.state WHEN 'regressed' THEN 0 WHEN 'open' THEN 1"
        " WHEN 'accepted-risk' THEN 2 ELSE 3 END, f.severity",
        (site_id,)).fetchall()
    from clauditseo import anatomy

    # Item 239 step 4: when the automatic ledger cleared each (check, page),
    # so an analysis row read before that can say it has been overtaken.
    when = {r["id"]: r["finished_at"] or r["started_at"] for r in conn.execute(
        "SELECT id, started_at, finished_at FROM audit_runs WHERE site_id=?", (site_id,))}
    cleared: dict[tuple[str, str], str] = {}
    for r in rows:
        if r["source"] == "deterministic" and r["state"] == "fixed" and when.get(r["changed_by_run"]):
            for u in json.loads(r["affected_urls"] or "[]"):
                key = (r["check_id"], _page_key(u))
                cleared[key] = max(cleared.get(key, ""), when[r["changed_by_run"]])

    out = []
    for r in rows:
        d = dict(r)
        d["affected_urls"] = json.loads(d["affected_urls"] or "[]")
        finding_run = d.pop("finding_run", None)
        d["superseded_on"] = None
        if d["source"] == "model-judgement" and d["affected_urls"] and when.get(finding_run):
            since = [cleared.get((d["check_id"], _page_key(u))) for u in d["affected_urls"]]
            if all(s and s > when[finding_run] for s in since):
                d["superseded_on"] = max(since)
        # The specialist that judges this check, or None (FEATURES.md F-02).
        # Same decision as `_finding_dict` makes for the run-scoped shape:
        # the server decides, so a row cannot offer a control the server
        # would refuse.
        d["specialist"] = anatomy.specialist_for(d.get("check_id") or "")
        # Whether a crawl could look again at this one, decided by the rule
        # the verify route refuses on. Same argument as `specialist` above:
        # the row says what the server would accept, so the screen never
        # offers a tick that a POST answers 422.
        d["names_a_page"] = names_a_page(d["affected_urls"])
        # Not a finding (brief v5 step S): the screens read this rather than
        # each keeping a copy of the rule.
        d["coverage_note"] = is_coverage_note(d["check_id"], d.get("severity"))
        # The source as a word (brief v10 step AF): `sweep` or `brief`, a
        # column and not a prefix on the check id. A conforming brief's row
        # also carries the copy it proposed and the status it gave.
        ev = json.loads(d.pop("evidence") or "{}") if d.get("evidence") else {}
        d["source_word"] = "brief" if d["source"] == "model-judgement" else "sweep"
        # A row that waives its check's registered blocker verdict says so in
        # its own evidence (item 145 BG: an AI block the policy chose).
        d["row_blocker"] = ev.get("blocker") if isinstance(ev.get("blocker"), bool) else None
        d["brief"] = ev.get("from_brief")
        d["proposed"] = (d.get("recommendation") or None) if ev.get("contract") else None
        d["brief_status"] = ev.get("status") if ev.get("contract") else None
        # A duplicate row's shared string (brief v11 step AH), from either
        # source: the record's group line counts the groups.
        d["group"] = ev.get("group") or None
        d["raised"] = bool(ev.get("raised"))
        # An image row's own fields (brief v15), for the part page that
        # renders one card per replacement rather than one per check.
        d["image"] = ev.get("image")
        # Every image a finding covers (item 246, ruling a): one finding per
        # check per page names each image failing it there.
        # Only a list of files: `img-duplicate-links` has always used
        # `images` for a count ("2 images link to /events"), and reading
        # that as a list made the site's page a 500 (2026-09-29).
        listed = ev.get("images")
        d["images"] = ([i for i in listed if isinstance(i, str)] if isinstance(listed, list)
                       else [ev["image"]] if isinstance(ev.get("image"), str) else [])
        # The structured-data block a row is about, and where the change
        # goes in the operator's words (brief v16 steps AS and AT).
        d["block"] = ev.get("block")
        d["where"] = ev.get("where")
        d["kind"] = ev.get("kind")
        # The URL template a per-template row is about (items 217, 222): the
        # row is filed on that template's traced page, and the card names
        # the template as its subject, not the one page it was filed on.
        d["template"] = ev.get("template") if isinstance(ev.get("template"), str) else None
        d["also_resolves"] = list(ev.get("also_resolves") or [])
        d["suggestions"] = [s for s in (ev.get("suggestions") or [])
                            if isinstance(s, dict)]
        d["fields"] = ev.get("fields") if isinstance(ev.get("fields"), dict) else {}
        # The AI surface brief's row payload and its two scalars (item 145 BH).
        if d.get("dimension") == "AIS" and ev.get("contract"):
            d["payload"] = {**(ev.get("payload") if isinstance(ev.get("payload"), dict) else {}),
                            **{k: ev[k] for k in ("passage", "place") if isinstance(ev.get(k), str)}}
        # A Security brief row's rollout (brief v20 step BD): the change per
        # layer, what deploying it risks, how to verify it, how to roll it
        # back, and its place and schedule in the rollout. None where the row
        # is not one - a sweep row has no rollout of its own.
        if ev.get("contract") and (ev.get("config") or ev.get("verify") or ev.get("rollback")):
            d["rollout"] = {k: ev.get(k) for k in (
                "domain", "impact", "config", "deploy_risk", "verify", "rollback",
                "order", "staged")}
        d.pop("recommendation", None)
        out.append(d)
    return out


def set_state(conn: sqlite3.Connection, site_id: str, fingerprint: str,
              state: str, run_id: str | None = None) -> bool:
    """Manual override (e.g. accepted-risk) from the dashboard.

    Returns whether a row matched. WF-95: this was a bare UPDATE returning
    None, so a call naming a fingerprint with no row wrote nothing and the
    route above it answered an unconditional ok — a success indistinguishable
    from one that happened. `mark_attempt` on the same resource has always
    returned this bool and its route has always raised 404 on it; the shape
    here is that one's, deliberately, rather than a second spelling.
    """
    stamp = now_iso()
    with conn:
        before = conn.execute("SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
                              (site_id, fingerprint)).fetchone()
        cur = conn.execute(
            "UPDATE finding_states SET state=?, changed_by_run=?, updated_at=?"
            " WHERE site_id=? AND fingerprint=?",
            (state, run_id, stamp, site_id, fingerprint))
        # Item 239: an operator's judgement is an event the Latest View's
        # replay applies, not a state it can recompute from the runs.
        if cur.rowcount and run_id is None:
            record_state_event(conn, site_id, fingerprint, "state",
                               before["state"] if before else None, state, at=stamp)
    return cur.rowcount > 0


def record_state_event(conn: sqlite3.Connection, site_id: str, fingerprint: str,
                       kind: str, from_state: str | None, to_state: str | None,
                       note: str | None = None, at: str | None = None) -> None:
    """One operator judgement, in order (item 239): `state` for a state the
    operator set, `attempt` for a fix-attempt mark ("marked" / "cleared").
    The caller holds the transaction."""
    conn.execute("INSERT INTO state_events (site_id, fingerprint, kind, from_state,"
                 " to_state, note, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (site_id, fingerprint, kind, from_state, to_state, note, at or now_iso()))


def is_per_dimension_metric(metric_key: str) -> bool:
    """Whether this series is one dimension's own score rather than a figure
    over the whole run.

    One owner for the split, because `site_trend` keys on it and a reader that
    decided it independently could disagree with the writer. The writer is
    `_snapshot_metrics`, which builds per-dimension keys as
    `f"{dim.lower()}.subscore"` and writes exactly two site-level keys beside
    them — `composite_score` and `measured_share`. Asked as "is it a
    dimension's own" rather than listed as "the two aggregates", so a third
    site-level metric is on the right side of the split the day it is added.

    It exists so the dimension term of the comparability key can be scoped.
    `onp.subscore` is ONP's own score from ONP's own checks: whether the run
    beside it also measured A11Y changes nothing about that number, so the
    run's dimension set is not that value's frame. Putting the term in every
    key would look like extra rigour and would mark eight series incomparable
    at every narrow run — a false alarm, and a flag that cries wolf is the
    state WF-48 describes, where noise is what hides a real miss.
    """
    return metric_key.endswith(".subscore")


#: `f"{dim.lower()}.subscore"` is what `_snapshot_metrics` writes, so this is
#: that expression read backwards. Kept beside `is_per_dimension_metric` rather
#: than inlined, because the two halves of one convention drifting apart is the
#: defect this whole finding is made of.
_SUBSCORE_SUFFIX = ".subscore"


def _recoverable_dimension_sets(conn: sqlite3.Connection,
                                site_id: str) -> dict[str, tuple[str, ...]]:
    """The dimension set each capture recorded, read off its own rows.

    `_snapshot_metrics` writes one `{dim}.subscore` row per *measured*
    dimension - applicable, with coverage - at the same `site_id` and
    `captured_at` as the composite, in the same transaction and under the same
    predicate the frame's own `dimensions` term is built from. So for a point
    whose frame predates that term, the population is not missing: it is in
    the sibling rows, and this reads it back.

    Sorted and upper-cased, because that is the shape `_snapshot_metrics`
    stores - `sorted(...)` over `result.subscores` keys, which are upper - and
    a recovered set that did not compare equal to a recorded one would split
    a series at the moment the term was introduced rather than at a real
    change.

    Membership is decided by `is_per_dimension_metric` and not by a `LIKE` in
    the SQL, for the reason that predicate exists at all: one owner for the
    split, so a third site-level metric cannot be read here as a dimension
    named "measured_share".

    **An ambiguous stamp is refused rather than merged, and this is the whole
    reason the function returns less than it could.** `metric_snapshots` has
    no run column - `(site_id, captured_at)` is the only handle - and
    `captured_at` is second-resolution, so two runs of one site finishing in
    the same second write their rows into one group. Merging them would
    produce a set no run measured and hand it to the operator as provenance,
    which is the defect this whole finding is made of, one rung down. Found by
    the fixture rather than reasoned about: two audits driven back to back in
    a test both stamp `2026-08-23T23:56:00+00:00`.

    Two signals, because one does not cover it:

      - a per-dimension key appearing **twice** at one stamp is two runs that
        both measured that dimension;
      - more than one `composite_score` at one stamp is two runs whose
        measured sets may be disjoint, which the first signal cannot see.

    The residue, stated rather than papered over: two runs at one second where
    neither produced a composite and their dimension sets do not overlap would
    still merge. Such a run contributes no trend point of its own, so the
    merged set can only be read for a point some *third* run wrote at that same
    second - and that third run would trip the second signal.
    """
    dims: dict[str, list[str]] = {}
    composites: dict[str, int] = {}
    for row in conn.execute(
            "SELECT captured_at, metric_key FROM metric_snapshots"
            " WHERE site_id=?", (site_id,)):
        key, stamp = row["metric_key"], row["captured_at"]
        if is_per_dimension_metric(key):
            dims.setdefault(stamp, []).append(
                key[:-len(_SUBSCORE_SUFFIX)].upper())
        elif key == "composite_score":
            composites[stamp] = composites.get(stamp, 0) + 1
    return {stamp: tuple(sorted(found))
            for stamp, found in dims.items()
            if len(found) == len(set(found)) and composites.get(stamp, 0) <= 1}


def _run_ids_by_capture(conn: sqlite3.Connection, site_id: str) -> dict[str, str]:
    """Which run finished at each stamp, for rows written before 0044.

    Migration 0044 stores the id on the snapshot, and every row written since
    carries it. This is the rung below, and only that: the join
    `run_measured_share` already makes — `captured_at` is the same value
    `mark_complete` writes to `finished_at`, so the join is exact rather than
    nearest-in-time — with the refusal `_recoverable_dimension_sets` already
    makes, because the stamp is second-resolution and two runs of one site
    finishing in one second are one group in it.

    A stamp naming two runs yields no id at all rather than the first one
    found. The id is what a screen builds a comparison link from, and a link
    to the wrong audit is worse than no link: the operator cannot see that it
    is wrong, and the comparison it opens will be rendered in full.

    Site-reading kinds only, and that is not a formality here: only a
    site-reading run wrote a snapshot in the first place, so a verification
    finishing in the same second as an audit is not a candidate — and asking
    the question narrows the ambiguity as well as the answer. Without it that
    pair would collide, and the audit would lose the id of the run that made
    it to a run that never wrote a row.
    """
    found: dict[str, str | None] = {}
    for row in conn.execute(
            "SELECT id, finished_at FROM audit_runs"
            f" WHERE site_id=? AND finished_at IS NOT NULL"
            f" AND {kind_is_site_reading()}", (site_id,)):
        stamp = row["finished_at"]
        found[stamp] = None if stamp in found else row["id"]
    return {stamp: run for stamp, run in found.items() if run}


def basis_key(tier: str | None, engine_version: str | None,
              share_basis_: str | None,
              dimensions: list[str] | tuple[str, ...] | None,
              keys_on_dimensions: bool = True) -> str:
    """The four terms that decide whether two points measure the same thing,
    as one string a screen can group by.

    Brief v16f. The terms are not new — `site_trend` has keyed comparability
    on `(engine_version, basis, tier, dimensions)` since WF-58 — and neither
    is the argument for any of them; what is new is that the key has a name
    and travels on the payload. Before this, the only thing a client could be
    told was whether *this* step broke, so a chart that wanted to say "these
    two are the same measurement" had to re-derive the key in TypeScript from
    four fields, which is the second opinion `TrendPoint`'s own docstring
    refuses to allow.

    Rendered rather than returned as a tuple because it crosses JSON, and
    strings compare by value on both sides. `?` stands for a term the row
    never recorded — a pre-0022 row with no basis, a point whose population
    could be neither read nor recovered — and two unknowns compare equal,
    which is the answer the tuple comparison has always given them.

    `keys_on_dimensions` is `is_per_dimension_metric` read backwards, passed
    in rather than decided here so the split keeps its one owner: `onp.subscore`
    is ONP's own score and the run's other dimensions are not its frame.
    """
    terms = [tier or "?", engine_version or "?", share_basis_ or "?"]
    if keys_on_dimensions:
        terms.append(",".join(dimensions) if dimensions is not None else "?")
    return "|".join(terms)


def site_trend(conn: sqlite3.Connection, site_id: str,
               metric_key: str = "composite_score") -> list[dict]:
    rows = conn.execute(
        "SELECT value, source, confidence, captured_at, tier, engine_version, scope,"
        " run_id FROM metric_snapshots WHERE site_id=? AND metric_key=?"
        " ORDER BY captured_at, rowid", (site_id, metric_key)).fetchall()
    out = [dict(r) for r in rows]
    # Mark the points either side of an engine change, so a chart can say
    # where a comparison stops being one. The version alone would leave the
    # reader to diff a column; `comparable` is the fact they actually need.
    #
    # The basis joins the version in that test. A `measured_share` computed
    # against a declared site total and one computed without one are two
    # measurements, and one engine version does not make them one — the same
    # argument 0012 made for the version, applied to the column 0022 added.
    # Rows written before 0022 carry `scope` NULL and so keep a basis of
    # None: unknown, comparable with each other and with nothing else.
    #
    # Tier joins them both, and it was the term left out while being the one
    # that decides most. It has sat in this row since the first migration. A
    # T2 crawl and a T3 crawl of one site measure two different populations
    # of pages, so their composites are two measurements for exactly the
    # reason the version and the basis are — the argument does not change
    # because the column is older. Found in the operator's own history rather
    # than by reading: `91.06 T2 0.8.0` followed by `70.52 T3 0.8.0` came back
    # `comparable: True`, a 20-point collapse across a tier boundary asserted
    # to be like-for-like by the one function that exists to deny that.
    #
    # The dimension set joins them all, and it was the term missing longest —
    # WF-58, carried from report 051 to 097. The other three say which engine
    # measured, whether breadth was applied and how deep the crawl went; none
    # of them says *which dimensions ran*, and that is the largest population
    # change the launcher can make. Reproduced against a migrated database: a
    # composite of 91.0 over eight dimensions and one of 62.0 over one, same
    # tier, same version, same basis, both `comparable: True`.
    #
    # For a site-level series only. `onp.subscore` is one dimension's own score
    # and the run's other dimensions are not its frame, so including the term
    # there would split eight series at every narrow run for a difference their
    # values do not carry. `is_per_dimension_metric` owns that split, so the
    # reader cannot disagree with the writer about which keys are which.
    #
    # Rows written before the term existed carry no `dimensions` key on their
    # frame, and the set is recovered from the per-dimension rows
    # `_snapshot_metrics` wrote beside them at the same `captured_at` - the
    # same population, by the same predicate, in the same transaction. Which
    # rung a point's set came from travels with it as `dimensions_basis`,
    # `recorded` or `derived`, for the reason `_pages_fetched` carries the
    # same distinction one table over: a derived figure that cannot be told
    # from a stored one is a provenance breach even when it is right.
    #
    # A read-time recovery, not a backfill. Nothing is written, so a point
    # that records its own set overrides nothing and reverting this restores
    # every prior answer.
    #
    # WF-58 was recorded closed at round 097 on the opposite claim - that a
    # backfill would invent a population nobody recorded. It would not. The
    # population *is* written down; it was written in eight rows instead of
    # one. The operator's own history is the proof, and it is what report 098
    # re-measured: `2026-08-15T03:55:10` measured six dimensions and
    # `06:01:36` measured seven, both stored as `{dim}.subscore` rows, and the
    # pair still came back `comparable: True` because the key read a frame
    # with no term rather than the rows that had one.
    #
    # A point with no per-dimension rows at all keeps None: unknown,
    # comparable with each other and with nothing else, the same answer this
    # key gives a pre-0022 row with no basis. That is the case where the set
    # genuinely was not recorded, and after this it is the only one.
    keys_on_dimensions = not is_per_dimension_metric(metric_key)
    for point in out:
        point["scope"] = json.loads(point["scope"]) if point["scope"] else None
    # One query, and only when a point actually needs it. Asked after the
    # frames are parsed rather than before, so a site whose every point
    # records its own set pays nothing for the rung.
    recoverable: dict[str, tuple[str, ...]] = {}
    if keys_on_dimensions and any((p["scope"] or {}).get("dimensions") is None
                                  for p in out):
        recoverable = _recoverable_dimension_sets(conn, site_id)
    prev = None
    for point in out:
        frame = point["scope"] or {}
        # A tuple, so `None` stays an unambiguous "nothing before this one":
        # a key is always a tuple, even when every one of its terms is unknown.
        key = (point.get("engine_version"), frame.get("basis"),
               point.get("tier"))
        if keys_on_dimensions:
            dimensions = frame.get("dimensions")
            # The rung, named beside the value rather than inferred from its
            # presence. `recorded` is a set the run stated on its own frame;
            # `derived` is one read back off the rows it wrote at the same
            # instant; None is neither, and only None is unknown.
            basis = "recorded" if dimensions is not None else None
            if dimensions is None:
                recovered = recoverable.get(point["captured_at"])
                if recovered is not None:
                    dimensions, basis = list(recovered), "derived"
            if dimensions is not None:
                # The frame travels with the value, so a recovered set is put
                # where a recorded one would be and the client reads one
                # shape. A row that stored no frame at all gets one built here
                # rather than staying None - it has a population now, and a
                # `None` scope would hide it behind a key the client tests
                # with `?.`. Nothing is fabricated: `basis` says which rung it
                # came from, and a point with neither stays exactly as stored.
                if point["scope"] is None:
                    point["scope"] = frame = {}
                frame["dimensions"] = dimensions
            if point["scope"] is not None:
                frame["dimensions_basis"] = basis
            # A tuple rather than the list JSON hands back, so the comparison
            # against `prev` is by value and cannot be defeated by two equal
            # lists being two objects.
            key += (tuple(dimensions) if dimensions is not None else None,)
        point["comparable"] = prev is None or key == prev
        prev = key
        # The same key, named. `comparable` above answers "did *this step*
        # break"; the string below is the thing itself, so a screen can group
        # points by it — shade the stretch that shares the latest one, join a
        # point to the last one that measured the same way — without reaching
        # its own verdict from four fields. Built from `key` rather than
        # beside it: two derivations of one fact is how the writer and the
        # reader came to disagree about the dimension set in the first place.
        point["basis_key"] = basis_key(
            point.get("tier"), point.get("engine_version"), frame.get("basis"),
            key[3] if keys_on_dimensions else None, keys_on_dimensions)
        # Whether this point's population was read back rather than recorded,
        # said in one field instead of left inside the frame for each screen
        # to interpret. `dimensions_basis` is still the owner — this is that
        # value, judged once, by the reader that performed the recovery.
        point["basis_recovered"] = frame.get("dimensions_basis") == "derived"
    # Which earlier point each one reads against: the nearest before it that
    # measured the same way, with the runs between it and them ignored.
    #
    # Brief v16f, and the defect it closes was visible on the operator's own
    # history. Nine scored runs of one site produced eight breaks in eight
    # steps, and `2026-09-02 02:37` was called non-comparable against
    # `02:22` — same tier, same engine, same basis, same dimension set — for
    # no reason except that a T2 run happened at `02:26` between them. A
    # comparison is a property of the two things compared; a third thing that
    # happened in between is not one of them.
    #
    # "The nearest earlier POINT", never "the nearest earlier run". Only a
    # completed site-wide audit writes a snapshot at all, so a verification,
    # a refresh, a narrow scan and a blocked run are excluded here by never
    # having entered — which is the pairing WF-60 was measured on, refused
    # one layer further out than it used to be.
    #
    # One pass with the last index per key, rather than a backward scan per
    # point: the answer is the same and a site with a long history does not
    # pay quadratically for a chart.
    last_seen: dict[str, int] = {}
    fallback: dict[str, str] | None = None
    for i, point in enumerate(out):
        if point["run_id"] is None:
            # A pre-0044 row. Asked for once, and only when a row needs it.
            if fallback is None:
                fallback = _run_ids_by_capture(conn, site_id)
            point["run_id"] = fallback.get(point["captured_at"])
        partner = last_seen.get(point["basis_key"])
        point["partner_index"] = partner
        point["partner_run_id"] = out[partner]["run_id"] if partner is not None else None
        point["partner_captured_at"] = (out[partner]["captured_at"]
                                        if partner is not None else None)
        last_seen[point["basis_key"]] = i
    return out


def log_cost(conn: sqlite3.Connection, run_id: str, provider: str, operation: str,
             units: str, quantity: float, est_cost: float | None = None,
             actual_cost: float | None = None) -> None:
    with conn:
        conn.execute(
            "INSERT INTO cost_entries (id, run_id, provider, operation, units, quantity,"
            " est_cost, actual_cost, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (create_id(), run_id, provider, operation, units, quantity,
             est_cost, actual_cost, now_iso()))


def _run_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # The server's classification, on the wire (brief v6 step V2), so no
    # screen keeps a heuristic of its own.
    d["effective_scope"] = scope_of(row)
    d["site_reading"] = reads_site(row)
    d["dimensions"] = json.loads(d["dimensions"])
    d["subscores"] = json.loads(d["subscores"]) if d["subscores"] else None
    d["analyst_enabled"] = bool(d["analyst_enabled"])
    d["progress"] = json.loads(d.get("progress") or "[]")
    raw = d.pop("crawl_evidence", None)
    evidence = json.loads(raw) if raw else None
    d["has_evidence"] = bool(evidence)
    # The blob stays out of the dict — it is megabytes and every caller of a
    # run would carry it — but the three facts describing what the crawl
    # actually reached come with it. Reducing the whole thing to a boolean
    # left the renderer with no way to say a crawl fetched nothing, which is
    # how a scored document for an unvisited site became possible. None means
    # "not recorded", never "zero": a run with no evidence stored has not
    # told us its scope, and that is not the same as telling us it saw none.
    d["scope"] = _scope(evidence) if evidence else None
    return d


def _pages_fetched(evidence: dict) -> tuple[int | None, str]:
    """How many pages a check could read, and how that was established.

    Three rungs, tried in order, because only the first is a count the crawler
    took with the pages in hand:

      `recorded`   `stats["eligible"]`, written by `crawler/crawl.py` since
                   engine 0.9.0 and exact.
      `derived`    the stored page list, counted through the one eligibility
                   rule in `crawler/types.py`. Available for every run stored
                   before 0.9.0, because the evidence keeps each page's
                   `status` and `content_type`.
      `attempted`  `stats["fetched"]` — URLs **tried**. A DNS failure leaves a
                   page object, so three unresolvable URLs are three attempts
                   and nought pages. This was the only fallback until CQ-04,
                   which meant a run that resolved nothing reported every
                   attempt as a page read, under the key the client-facing
                   coverage ratio is computed from.

    The derived rung is refused where the stored list is short of the attempt
    count, because `_scope`'s docstring is right that `pages` can be trimmed
    for size and counting a trimmed list would understate a large crawl. An
    understatement that says `derived` would be worse than an attempt count
    that says `attempted`: both are wrong, and only one admits it.

    Measured over `data/clauditseo.db` before this landed: four runs record
    `eligible` and take rung one unchanged; the derived rung agrees with the
    recorded count on all four, which is what makes it trustworthy for the
    seven that have no recorded count; and on those seven it returns the same
    figure the attempt count did, because every page they fetched resolved.
    So no stored number moves — what changes is the run that resolves nothing.
    """
    from clauditseo.crawler.types import stored_page_is_eligible

    recorded = (evidence.get("stats") or {}).get("eligible")
    if recorded is not None:
        return recorded, "recorded"

    attempted = (evidence.get("stats") or {}).get("fetched")
    pages = evidence.get("pages") or []
    if pages and attempted in (None, len(pages)):
        return sum(1 for p in pages
                   if isinstance(p, dict) and stored_page_is_eligible(p)), "derived"
    return (attempted if attempted is not None else len(pages)), "attempted"


def _scope(evidence: dict) -> dict:
    """What the crawl reached, from the counts the crawler recorded.

    `stats` is authoritative: `robots_blocked` in the blob is capped at 100
    for size and `pages` can be trimmed, so counting either would understate
    a large crawl. The lengths are the fallback for evidence written before
    stats were stored.

    The page count is the one exception and `_pages_fetched` holds the reason:
    the stats key that means "pages a check could read" is newer than most of
    the stored runs, and standing the attempt count in for it is a claim the
    evidence itself contradicts. That fallback counts the list only where the
    list is whole, which is the trimming case this paragraph is about.
    """
    stats = evidence.get("stats") or {}
    fetched, basis = _pages_fetched(evidence)
    # `sitemap_entry_total` is the site's own declaration of its size, counted
    # before the stored entry list is capped. None when no sitemap was read:
    # the crawl frontier's own count would be "what we had found by the time
    # we stopped", which on a truncated crawl is a function of the budget
    # rather than of the site, and reads as a total while being nothing of
    # the kind.
    return {
        # How many pages a check could actually read, and — beside it, in one
        # key — which of the three ways that was arrived at. CQ-04: this
        # figure and `len(crawled_paths)` are two different counts of what a
        # run read, and a consumer that cannot tell a recorded count from a
        # stood-in one cannot say which it is holding.
        "pages_fetched": fetched,
        "pages_fetched_basis": basis,
        "discovered": evidence.get("sitemap_entry_total") or None,
        # CQ-70, open since report 034. The numerator above has carried its
        # basis since CQ-04 and the denominator carried nothing, so the ratio
        # rendered as `235 of 272 discovered pages` — one noun over two
        # populations, pages a check could read against URLs the site
        # declared. Q-14 settled that neither figure moves; this is the same
        # answer's other half, which is that each end says what it counted.
        #
        # One value today, by construction: `sitemap_entry_total` is the only
        # source this figure has ever had. The key is still worth its line —
        # it is what the clause names the population from, and the day a
        # second source appears (a crawl frontier count, say) a reader can
        # tell which they are holding. None where there is no total, which is
        # the case `_breadth_absence` renders as silence rather than a ratio,
        # so nothing claims a basis for a figure that is not there.
        "discovered_basis": (
            "sitemap" if evidence.get("sitemap_entry_total") else None),
        "robots_blocked": stats.get(
            "blocked_by_robots", len(evidence.get("robots_blocked") or [])),
        "truncated_by": evidence.get("truncated_by"),
    }


def _finding_dict(row: sqlite3.Row) -> dict:
    from clauditseo import anatomy

    d = dict(row)
    d["affected_urls"] = json.loads(d["affected_urls"] or "[]")
    d["evidence"] = json.loads(d["evidence"] or "{}")
    # The specialist that judges this check, or None (FEATURES.md F-02).
    # Carried on the row rather than looked up on the screen, so the client
    # cannot invent an offer the server would refuse — None here and no
    # control there are the same decision, made once.
    d["specialist"] = anatomy.specialist_for(d.get("check_id") or "")
    return d


#: When a client report stopped being buildable over an unassessed Critical or
#: High: 1efbe9a, item 150, brief v23 step BL. A report made before it is a
#: legacy row, not a live failure, and the Deliver chapter must not word it as
#: something the product would allow again (channel ruling 20260917-0250).
REPORT_GUARD_SINCE = "2026-09-13T06:23:42+00:00"


def report_state(conn: sqlite3.Connection, site_id: str) -> dict | None:
    """The newest client report and what it was built over (item 170).

    Read from the numbers recorded at generation (migration 0064), never
    derived afterwards. Three cases the Deliver chapter tells apart:

    - `predates_guard`: made before a report could be refused over an
      unassessed Critical or High. Nothing is known about what it was built
      over, and it is not a thing that can happen now.
    - `recorded` with `unassessed_below` > 0: passed the guard, and went out
      with Medium, Low or Info findings still open - the case the threshold
      deliberately leaves to the operator ("Not 100%, which will never hold").
    - after the guard but `recorded` false: generated before migration 0064,
      or adopted from disk; it passed the guard, and how much else was open
      was not written down.

    `None` where the site has no client report.
    """
    from datetime import datetime

    row = conn.execute(
        "SELECT id, run_ids, created_at, unassessed_severe, unassessed_total, assessed_pct"
        " FROM reports WHERE site_id=? AND audience='client'"
        " ORDER BY created_at DESC, rowid DESC LIMIT 1", (site_id,)).fetchone()
    if row is None:
        return None

    def _at(iso: str) -> datetime | None:
        try:
            return datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        except ValueError:
            return None

    made, guard = _at(row["created_at"]), _at(REPORT_GUARD_SINCE)
    recorded = row["unassessed_total"] is not None
    severe = row["unassessed_severe"]
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "run_ids": json.loads(row["run_ids"] or "[]"),
        "predates_guard": bool(made and guard and made < guard),
        "recorded": recorded,
        "unassessed_severe": severe,
        "unassessed_below": (row["unassessed_total"] - (severe or 0)) if recorded else None,
        "assessed_pct": row["assessed_pct"],
    }


def current_state(conn: sqlite3.Connection, site_id: str) -> dict:
    """The site's standing position: everything outstanding, not one run's
    output.

    The screen this feeds has always read `finding_states` by site — a
    finding raised three audits ago and never fixed is still open, and counts
    here. But it sat under an audit selector that scoped nothing, so it read
    as "what the last crawl found". It is not; it is the running total.

    Also returns what the tree deliberately leaves out, because a total that
    silently excludes two states is a total nobody can reconcile:

      candidate      seen once. Model output varies run to run, so one
                     sighting is not yet a fact and is not counted as open.
      accepted-risk  excluded by the operator's own decision, never
                     reinstated automatically.
      withdrawn      the finding was never true — the audit that raised it
                     could not see the site. Not outstanding because there is
                     nothing to fix, and not `fixed` because nothing was.
    """
    by_state = standing_by_state(conn, site_id)

    # 'blocked' counts as an audit that happened. It fetched no page, so it
    # cleared nothing — but it is the site's standing position, and excluding
    # it would silently roll the fix loop back to a crawl that may be weeks
    # old while the screen said nothing had changed.
    latest = conn.execute(
        "SELECT id, started_at FROM audit_runs WHERE site_id=?"
        f" AND {status_in(AUDITED_STATUSES)}"
        " AND kind='audit' ORDER BY started_at DESC, rowid DESC LIMIT 1",
        (site_id,)).fetchone()
    moved = {}
    if latest:
        # Coverage notes excluded, by the predicate `standing_by_state` above
        # applies to the same table (item 180's ruling 20260918-0400). This was
        # a bare GROUP BY four lines under that call until 2026-09-18, so the
        # landing rendered "First audit +36 -0" beside its own "It found 32
        # findings in this audit. 4 coverage notes not counted." and a strip
        # reading "SUMS TO 32" - one population in three figures and a fourth
        # counting something else. Four of seven seeded sites showed it
        # (36/32, 51/47, 56/52 and 177/176 - four sites, four pairs that
        # should have been one figure), and `standing_by_state`'s own docstring
        # is the rule it
        # broke: the record, the parts and the standing count one population.
        for r in conn.execute(
                "SELECT fs.state, COUNT(*) n FROM finding_states fs"
                f" JOIN findings f ON f.rowid = ({_latest_finding()})"
                f" WHERE fs.site_id=? AND fs.changed_by_run=? AND NOT {coverage_note_sql()}"
                " GROUP BY fs.state",
                (site_id, latest["id"])):
            moved[r["state"]] = r["n"]

    # UX-92. The counts above are a GROUP BY over the whole of
    # `finding_states`, whatever moved each row — so `latest`, which is the
    # last full AUDIT, is the wrong thing to stamp them with. On the
    # operator's database the pane read `2026-08-23` over counts a verify of
    # `2026-08-24` had moved ten of, and a day's difference reads as "nothing
    # has happened since".
    #
    # `last_audit` is not redirected, because three other readers want
    # precisely the last full audit and are right today: `moved` is counted
    # against it, the site's `last ran` line is about audits, and
    # `useFixLoop`'s `judged` gate exists to stop a two-page verify settling a
    # mark it never covered. Two facts, because they answer two questions.
    #
    # Decided by whether a row exists rather than by a status: a run that
    # wrote a `finding_states` row moved the position, and the row is the
    # evidence for that. A status is structure standing in for it, and gets
    # the answer wrong in the direction that matters — a run can reach a
    # terminal status having touched nothing.
    # guard-exempt(site-reading): UX-92. This is the one query here whose
    # whole subject is that a verification IS a reading of the site's
    # standing position. `current_state` reports counts taken over the whole
    # of `finding_states`, whatever moved each row; the pane over them was
    # stamped with the last full audit, and on the operator's database that
    # read 2026-08-23 above counts a verify of 2026-08-24 had moved ten of.
    #
    # Beside THIS query and not on the function, because `current_state`
    # also holds the `kind='audit'` query feeding `last_audit` and `moved`,
    # and a function-level exemption would wave that one through the day it
    # stopped asking.
    mover = conn.execute(
        "SELECT r.id, r.kind, r.started_at FROM audit_runs r"
        " WHERE r.site_id=? AND EXISTS ("
        "   SELECT 1 FROM finding_states fs"
        "   WHERE fs.site_id=r.site_id AND fs.changed_by_run=r.id)"
        " ORDER BY r.started_at DESC, r.rowid DESC LIMIT 1",
        (site_id,)).fetchone()

    outstanding = (by_state.get("open", {}).get("n", 0)
                   + by_state.get("regressed", {}).get("n", 0))
    # The three facts the suggested order needs that nothing else reported.
    # Counts over tables already here — this widens an API response, not the
    # stored run shape, so it is deliberately not an ENGINE_VERSION event.
    #
    # `analyses` counts expert briefs and `client_reports` counts rendered
    # deliverables, which are different things the UI has one word for. The
    # Reports page lists the first and calls them "written analyses"; the
    # second is what `POST /api/reports` produces. Conflating them would put
    # two numbers under one label on two screens.
    awaiting = conn.execute(
        "SELECT COUNT(*) FROM finding_states WHERE site_id=?"
        " AND attempted_at IS NOT NULL AND state IN ('open','regressed')",
        (site_id,)).fetchone()[0]
    analyses = conn.execute(
        "SELECT COUNT(*) FROM expert_reports er"
        " JOIN audit_runs a ON a.id = er.run_id WHERE a.site_id=?",
        (site_id,)).fetchone()[0]
    client_reports = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE site_id=?", (site_id,)).fetchone()[0]
    oldest = min((v["oldest"] for k, v in by_state.items()
                  if k in ("open", "regressed") and v["oldest"]), default=None)
    # The client plan, and whether the Record has moved under it (brief v18
    # step AY). Two facts rather than one verdict, because "current" is a
    # judgement the screen makes and the count is what makes it: a tile
    # reading `plan predates 11 rows` says what has to be re-read, and a
    # boolean would only say that something has.
    #
    # The latest ACCEPTED plan, and acceptance is asked of the contract
    # rather than of the row: a plan whose summary cited nothing was
    # refused, no document exists, and a tile saying one was generated
    # would be pointing at nothing. `json_extract` rather than a Python
    # pass over every report on the site — this runs on every read of the
    # client screen.
    plan = conn.execute(
        "SELECT er.created_at FROM expert_reports er"
        " JOIN audit_runs a ON a.id = er.run_id"
        " WHERE a.site_id=? AND er.tool_id='plan'"
        "   AND er.contract IS NOT NULL"
        "   AND json_extract(er.contract, '$.generator') IS NOT NULL"
        " ORDER BY er.created_at DESC, er.rowid DESC LIMIT 1",
        (site_id,)).fetchone()
    plan_at = plan["created_at"] if plan else None
    plan_stale_rows = conn.execute(
        "SELECT COUNT(*) FROM finding_states WHERE site_id=? AND updated_at > ?",
        (site_id, plan_at)).fetchone()[0] if plan_at else 0
    return {
        "plan_generated_at": plan_at,
        "plan_stale_rows": plan_stale_rows,
        "outstanding": outstanding,
        "open": by_state.get("open", {}).get("n", 0),
        "regressed": by_state.get("regressed", {}).get("n", 0),
        "candidate": by_state.get("candidate", {}).get("n", 0),
        "accepted_risk": by_state.get("accepted-risk", {}).get("n", 0),
        "withdrawn": by_state.get("withdrawn", {}).get("n", 0),
        "fixed": by_state.get("fixed", {}).get("n", 0),
        "oldest_outstanding": oldest,
        "awaiting_a_look": awaiting,
        "analyses": analyses,
        "client_reports": client_reports,
        # What the newest client report was built over, as recorded when it
        # was built (item 170). The Deliver chapter's sentence reads it.
        "report_state": report_state(conn, site_id),
        # What the most recent audit actually changed, which is the only part
        # of this screen that IS about one run — and was nowhere on it.
        "last_audit": latest["started_at"] if latest else None,
        "moved": {"opened": moved.get("open", 0), "fixed": moved.get("fixed", 0),
                  "regressed": moved.get("regressed", 0)},
        # The run the counts above were last moved by, and its kind — which
        # the screen has to name, because "2026-08-24" alone cannot say
        # whether a site-wide audit or a two-page verification put it there.
        "last_move": ({"at": mover["started_at"], "kind": mover["kind"],
                       "run_id": mover["id"]} if mover else None),
    }


def _finding_evidence(evidence: str | None) -> dict:
    """A finding's evidence JSON as an object, `{}` for every way it is not one.

    Empty, not JSON, and JSON that is not an object (a list parses fine and has
    no `.get`) all read as `{}`: each field read below then answers None or
    False, which is what each of them answered from its own parse. Parsed once
    per finding and handed to all three - `anatomy_view` parsed the same string
    three times per row.
    """
    try:
        ev = json.loads(evidence) if evidence else {}
    except (TypeError, ValueError):
        return {}
    return ev if isinstance(ev, dict) else {}


#: The only fields of a finding's evidence the anatomy view reads, as each
#: appears in stored JSON text: a key is written quoted.
_VIEW_EVIDENCE_NEEDLES = tuple(f'"{k}"' for k in (
    "outline_index", "contract", "status", "from_brief", "block"))


def _view_evidence(evidence: str | None) -> dict:
    """`_finding_evidence`, for the anatomy view, skipping text that cannot
    hold a field the view reads.

    Evidence runs to 334 KB on an accessibility coverage row - the page text
    blocks it was measured over - and the view parsed all of it for five small
    fields: on twenty22 two such rows were 0.67 MB of the 0.9 MB it read, and
    neither names any of the five. An object holding one of those keys holds
    its quoted name in its text, so text without any of the names reads `{}`,
    which is what the parse answered for every field the view takes from it -
    valid or not, object or not. A substring search is far cheaper than a
    parse. It would miss a key written with escaped ASCII letters, which no
    writer produces: every writer of `findings.evidence` stores `json.dumps`
    of a dict, and `json.dumps` escapes only control and non-ASCII characters.
    """
    if not evidence or not any(n in evidence for n in _VIEW_EVIDENCE_NEEDLES):
        return {}
    return _finding_evidence(evidence)


def _outline_index(evidence: str | dict | None) -> int | None:
    """The stored position of a finding's fault in the page outline, or None.

    None for every way it can be absent — no evidence, evidence that is not
    JSON, a finding raised before the check recorded a position, or a
    position that is not a whole number. The caller sends nothing at all in
    those cases, so a screen cannot mistake a default for a measurement.
    Takes the stored string, or the object :func:`_finding_evidence` made of it.
    """
    stored = evidence if isinstance(evidence, dict) else _finding_evidence(evidence)
    value = stored.get("outline_index")
    # `bool` is an `int` in Python and would sail through `isinstance`.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _evidence_key(evidence: str | dict | None, key: str):
    """One field out of a finding's evidence JSON, or `None`.

    Evidence is stored as a JSON string and read in three places with three
    copies of the same four-line try/except. This is the fourth, written as
    a function rather than a fourth copy.
    """
    ev = evidence if isinstance(evidence, dict) else _finding_evidence(evidence)
    return ev.get(key)


def _contract_marks(evidence: str | dict | None) -> dict:
    """What a finding's evidence says about its brief (brief v10 step AF):
    whether it is a contract row, the status the brief gave, the brief."""
    ev = evidence if isinstance(evidence, dict) else _finding_evidence(evidence)
    return {"contract": bool(ev.get("contract")),
            "brief_status": ev.get("status") if ev.get("contract") else None,
            "brief": ev.get("from_brief")}


def _audits_since(conn: sqlite3.Connection, site_id: str, run_id: str) -> int | None:
    """Readings of the site completed after the one `run_id` names.

    The part page's twin of the count `site_reports` puts on every stored
    analysis. Readings only, for the reason recorded there: a verification
    that fetched eight pages of 224 is not evidence the site moved.

    `None` where the run is not a reading (an analysis run by hand against a
    page scan), which the screen states rather than counting to zero — zero
    is "this audit", and that would be a claim this cannot make.
    """
    # The kind question is asked here, in the query, not only by `reads_site`
    # below: this reader wants readings and nothing else, so it has no claim
    # on `site_reports`' exemption, whose `bare` query must keep every kind to
    # feed the runs payload. The scope half stays in Python, where the row is.
    order = [r["id"] for r in conn.execute(
        "SELECT id, kind, status, scan_scope, crawled_paths, tier FROM audit_runs"
        f" WHERE site_id=? AND {status_in(AUDITED_STATUSES)}"
        f" AND {kind_in_site_reading_kinds()}"
        " ORDER BY started_at DESC, rowid DESC", (site_id,)) if reads_site(r)]
    return {rid: i for i, rid in enumerate(order)}.get(run_id)


def _read_and_since(conn: sqlite3.Connection, site_id: str, run_id: str,
                    checks: list[str]) -> dict:
    from . import latest_view
    row = conn.execute("SELECT started_at, finished_at FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    crawl_at = (row["finished_at"] or row["started_at"]) if row else None
    newest = None
    for dim in sorted({c.split("/")[0] for c in checks if "/" in c}):
        ref = latest_view.reference(conn, site_id, dim)
        if ref and ref.get("at") and (newest is None or ref["at"] > newest):
            newest = ref["at"]
    return {"crawl_at": crawl_at,
            "checked_since": newest if newest and crawl_at and newest > crawl_at else None}


def anatomy_view(conn: sqlite3.Connection, site_id: str,
                 page_url: str | None = None) -> dict:
    """Open work for a site, sorted by how a page is built.

    A lens over the same finding states the rest of the app counts, so the
    categories always sum to the same total — the alternative is two screens
    counting independently and disagreeing, which has happened here before.

    `page_url` narrows everything to one page. Co-occurrence is not computed
    in that mode: on a single page every category trivially shares it, so the
    signal would fire everywhere and mean nothing.
    """
    from clauditseo import anatomy as an

    rows = conn.execute(
        f"""SELECT f.check_id, f.dimension, f.severity, f.summary, f.source,
                  f.affected_urls, f.affected_total, f.recommendation,
                  f.evidence, fs.state,
                  fs.fingerprint, fs.attempted_at, fs.attempt_note
           FROM finding_states fs
           JOIN findings f ON f.rowid = ({_latest_finding()})
           WHERE fs.site_id = ? AND fs.state IN ('open', 'regressed')""",
        (site_id,)).fetchall()

    buckets: dict[str, list[dict]] = {c.key: [] for c in an.CATEGORIES}
    from . import age as _age, latest_view
    ages = {k: v for k, v in _age.thresholds(conn).items() if k != "defaults"}
    # Every check a brief writing to the part may emit (brief v11 step AH):
    # the part page lists them all, `0` where the record holds nothing.
    from clauditseo import briefs as _briefs
    from clauditseo.modules import onp as _onp
    brief_checks: dict[str, list[str]] = {}
    for b in _briefs.catalogue():
        if b.part not in _briefs.PARTLESS:
            for c in b.checks:
                if c not in brief_checks.setdefault(b.part, []):
                    brief_checks[b.part].append(c)
    # What the latest run of each brief writing to a part made of its
    # answer (brief v12 step AL, brief v13 step AO): the rows it dropped,
    # the rows it could not assess with what each needs, when it ran and
    # at what, and its own summary sentence. The part page states the run
    # rather than marking it with a dot, and gives a held check a card
    # naming the input instead of a bracketed placeholder.
    part_of = {b.id: b.part for b in _briefs.catalogue()
               if b.part not in _briefs.PARTLESS}
    brief_dropped: dict[str, int] = {}
    #: Item 209: the dropped rows themselves - check, page, reason - beside
    #: their count. The count alone printed "19 rows dropped — see report"
    #: with no report to see on the page: the AI surface run returned 29 rows,
    #: the contract kept 10, and the reasons for the other 19 were stored and
    #: shown nowhere.
    brief_dropped_rows: dict[str, list[dict]] = {}
    brief_not_assessable: dict[str, int] = {}
    brief_held: dict[str, list[dict]] = {}
    brief_eligibility: dict[str, list[dict]] = {}
    brief_map: dict[str, list[dict]] = {}
    brief_clusters: dict[str, list[dict]] = {}
    brief_entity: dict[str, dict] = {}
    # Brief v20's block keys (items 147, 148), beside the four above and for
    # the same reason: each is a fact about a GROUP of pages -- a template, a
    # locale set, a fix that serves several templates -- and no row about one
    # page can carry it.
    brief_templates: dict[str, list[dict]] = {}
    brief_locales: dict[str, dict] = {}
    brief_fixes: dict[str, list[dict]] = {}
    brief_schema: dict[str, str] = {}
    #: The Security brief's "now" (item 143 step BD), newest brief per part.
    brief_security: dict[str, dict] = {}
    #: The AI surface brief's block beside its rows (item 145 BH), newest run's.
    brief_ai_surface: dict[str, dict] = {}
    brief_run: dict[str, dict] = {}
    brief_summary: dict[str, str] = {}
    #: Item 210: the assessment section whole, as the model wrote it, for a
    #: disclosure. `brief_summary` was its first three sentences printed at
    #: data weight under the table, and it disagreed with the table on ten
    #: parts of eighteen - it was written before the contract kept, merged,
    #: held and dropped rows, so it describes a different set.
    brief_prose: dict[str, str] = {}
    seen_tools: set[str] = set()
    for er in conn.execute(
            """SELECT er.tool_id, er.contract, er.model_id, er.created_at, er.cost,
                      er.report, er.run_id FROM expert_reports er
               JOIN audit_runs r ON r.id = er.run_id
               WHERE r.site_id = ? AND er.contract IS NOT NULL
               ORDER BY er.created_at DESC, er.rowid DESC""", (site_id,)):
        if er["tool_id"] in seen_tools or er["tool_id"] not in part_of:
            continue
        seen_tools.add(er["tool_id"])
        try:
            c = json.loads(er["contract"]) or {}
        except (TypeError, ValueError):
            continue
        part = part_of[er["tool_id"]]
        brief_dropped[part] = brief_dropped.get(part, 0) + len(c.get("dropped") or [])
        for d in (c.get("dropped") or []):
            if not isinstance(d, dict):
                continue
            row = d.get("row") if isinstance(d.get("row"), dict) else {}
            brief_dropped_rows.setdefault(part, []).append({
                "check": str(row.get("check") or ""), "page": row.get("page") or row.get("url"),
                "reason": str(d.get("reason") or "no reason was recorded")})
        # Item 211, on read as well as on parse: a contract stored before
        # the rule still holds its variable-name reasons and its passes, and
        # a re-parse is not the only way a reader should see them fixed.
        from clauditseo.analysts import contract as _contract
        cleaned = _contract.clean_holds(_contract.Parsed(
            status=_contract.READ,
            not_assessable=[h for h in (c.get("not_assessable") or []) if isinstance(h, dict)]))
        held = cleaned.not_assessable
        for d in cleaned.dropped:
            brief_dropped[part] = brief_dropped.get(part, 0) + 1
            brief_dropped_rows.setdefault(part, []).append({
                "check": str((d.get("row") or {}).get("check") or ""),
                "page": (d.get("row") or {}).get("page"), "reason": d["reason"]})
        brief_not_assessable[part] = brief_not_assessable.get(part, 0) + len(held)
        # `needs` is the input a held check waits on (brief v15 step AQ). The
        # brief v20 schemas write a different shape - `scope` and `reason`,
        # no `needs` - and reading only `needs` stored "" for every one of
        # them. The card keys "held" on `needs`, so each rendered as an
        # empty `info` card with no body: Acme International drew a second,
        # blank "Hreflang target" and four more beside the real rows. The
        # reason is what a reader needs from a held card, so it stands in,
        # with the scope it was held over.
        def _needs(h: dict) -> str:
            if h.get("needs"):
                return str(h["needs"])
            reason = str(h.get("reason") or "")
            scope = str(h.get("scope") or "")
            return f"{reason} ({scope})" if reason and scope else reason
        brief_held.setdefault(part, []).extend(
            {"check": str(h.get("check") or ""), "page": str(h.get("page") or ""),
             "needs": _needs(h)} for h in held)
        brief_run.setdefault(part, {
            "tool": er["tool_id"], "model": er["model_id"], "at": er["created_at"],
            "run_id": er["run_id"], "rows": len(c.get("rows") or []),
            "cost": er["cost"], "status": c.get("status"),
            # How many readings of the site have run since the audit this
            # analysis read — `site_reports` computes the same number for the
            # Reports screen, off the same rule, and the two must not disagree.
            # Without it a part page reading today's sweep printed a two-day-old
            # analysis as "· 11:06" and a reader took it for this audit's: the
            # staleness `test_report_currency` exists to stop, arriving through
            # the part page's door.
            "audits_since": _audits_since(conn, site_id, er["run_id"]),
            # Item 239 step 4: the crawl this analysis read, and the newest
            # automatic measurement of the part's checks after it - "analysis
            # read the crawl of 18 Sept; automatic checks since".
            **_read_and_since(conn, site_id, er["run_id"], brief_checks.get(part) or [])})
        # The two verdicts that are not findings (brief v16 step AS):
        # eligibility per (page, rich result), and the site's own entity
        # shape. Neither belongs among the rows - a page can be ineligible
        # for a rich result with nothing wrong with its markup - so the
        # part page renders them above the fixes rather than in them.
        brief_eligibility.setdefault(part, []).extend(
            e for e in (c.get("eligibility") or []) if isinstance(e, dict))
        # Coverage's topical map and Cannibalisation's clusters (brief v17
        # step AX). Facts about groups of pages, so they ride beside the
        # rows the way eligibility and the entity verdict do.
        for name, into in (("map", brief_map), ("clusters", brief_clusters),
                           ("templates", brief_templates),
                           ("fixes", brief_fixes)):
            into.setdefault(part, []).extend(
                x for x in (c.get(name) or []) if isinstance(x, dict))
        # The schema version the block declared. Carried so a screen can tell
        # which shape it is drawing, rather than inferring it from which keys
        # happen to be present.
        if c.get("schema") and part not in brief_schema:
            brief_schema[part] = str(c["schema"])
        # `locales` is an OBJECT in the installed schema, not a list, so it is
        # taken whole rather than extended -- extending it iterated the
        # object's keys, found no dicts, and dropped it. The newest run's wins,
        # which is what the reports query above orders by.
        if isinstance(c.get("locales"), dict) and part not in brief_locales:
            brief_locales[part] = c["locales"]
        if isinstance(c.get("entity"), dict) and part not in brief_entity:
            brief_entity[part] = c["entity"]
        if part not in brief_ai_surface and isinstance(c.get("ai_surface"), dict):
            brief_ai_surface[part] = {**c["ai_surface"], "run_id": er["run_id"]}
        if part not in brief_security and (c.get("compromise") or c.get("ledger")):
            brief_security[part] = {k: c.get(k) for k in (
                "compromise", "ledger", "transport", "headers", "cookies",
                "scripts", "do_not_spend_on")}
        summary = _brief_summary(er["report"])
        if summary:
            brief_summary.setdefault(part, summary)
        prose = brief_assessment(er["report"])
        if prose:
            brief_prose.setdefault(part, prose)
    # One page is one page, however the row naming it spelled the URL.
    # A brief's legacy findings table stores what the model wrote, and a
    # model writes `/about`; the sweep stores `https://host/about`. Left
    # alone, the narrow picker offers Birch's twelve pages twice and the
    # part page posts a hostless `/` to a route that compares hosts -
    # which is the refusal the operator met.
    #
    # Canonicalised here rather than only at write time because this
    # function reads OPEN findings site-wide, not one run's: a row raised
    # by an older run and never fixed is still open and still counted, so
    # no number of re-audits can clear a spelling already stored. The
    # write-side fix stops new ones; only this repairs what exists.
    #
    # The absolute spelling wins where the site has one, because that is
    # what every consumer needs - the refresh route compares hosts, and
    # `page_facts` is keyed by URL. Where a page is only ever named by
    # path, the path stands: dropping the row would lose the finding, and
    # inventing a host for it would be a guess about which host.
    # Each row's URL list, parsed once for both passes below.
    affected = [json.loads(r["affected_urls"] or "[]") for r in rows]
    canonical: dict[str, str] = {}
    for urls_stored in affected:
        for u in urls_stored:
            key = _page_key(u)
            absolute = u.startswith(("http://", "https://"))
            held = canonical.get(key)
            if held is None or (absolute and not held.startswith(("http://", "https://"))):
                canonical[key] = u

    def _canonical(urls: list[str]) -> list[str]:
        seen: list[str] = []
        for u in urls:
            c = canonical.get(_page_key(u), u)
            if c not in seen:
                seen.append(c)
        return seen

    # And the narrow itself, so a link or a bookmark carrying the old
    # spelling lands on the page rather than on nothing. Without this the
    # rows resolve (they are compared by key below) but `page_facts` does
    # not, and the card reads "the crawl recorded nothing about this page"
    # over a page the crawl recorded fully.
    if page_url and page_facts(conn, site_id, page_url) is None:
        # Only where the spelling asked for is not a page in its own right.
        # The rewrite exists so a bookmark carrying an OLD spelling lands
        # somewhere; a spelling the crawl actually recorded is not old, and
        # rewriting it hands back a different page's facts.
        #
        # Q-54 is where that showed. `/how-it-works` and `/how-it-works/`
        # are two crawled pages here, and they share a key because a
        # trailing slash is a spelling. While the variant carried no
        # finding it never entered the map; once it did, the healthy page
        # resolved to it and a self-canonical page read as a variant of
        # itself.
        page_url = canonical.get(_page_key(page_url), page_url)

    pages: dict[str, set[str]] = {c.key: set() for c in an.CATEGORIES}
    all_pages: set[str] = set()
    #: Findings this page filter set aside because they are about the site as
    #: one subject rather than any page (audit F15). Zero in site mode.
    site_only = 0
    # Which check ids were raised by both a sweep and a brief. The two answer
    # different questions and are meant to differ; shown side by side with no
    # label, they read as one number contradicting itself.
    sources_per_check: dict[str, set[str]] = {}

    for r, urls_stored in zip(rows, affected):
        urls = _canonical(urls_stored)
        all_pages |= set(urls)
        # By key, not by string: the narrow carries one spelling and the
        # row may have been written in the other, and a filter that missed
        # a brief's rows would report a page as clean because the only
        # thing that judged it spelled its own URL differently.
        if page_url and _page_key(page_url) not in {_page_key(u) for u in urls}:
            # A row naming no page at all is not another page's finding: it is
            # about the site as one subject - `AIS/llms-txt-missing`, the Local
            # rows - and page mode has no population for it, so it is dropped.
            # Counted, so the screen can say so (audit F15): twenty22's page
            # mode read 29 against a site figure of 32, on the ONLY page the
            # audit crawled, with nothing to explain the three.
            if not urls and not is_coverage_note(r["check_id"], r["severity"]):
                site_only += 1
            continue
        sources_per_check.setdefault(r["check_id"], set()).add(r["source"])
        cat = an.categorise(r["check_id"], r["dimension"])
        ev = _view_evidence(r["evidence"])
        fault = _outline_index(ev)
        buckets[cat].append({
            "fingerprint": r["fingerprint"], "check_id": r["check_id"],
            "dimension": r["dimension"], "severity": r["severity"],
            "summary": r["summary"], "state": r["state"],
            "source": r["source"],
            # The fix loop's first half, built long ago and never surfaced:
            # "I have fixed this, check it next time". It is deliberately not
            # a state — nothing the operator asserts changes the record, only
            # a crawl that looks again.
            "attempted_at": r["attempted_at"], "attempt_note": r["attempt_note"],
            "recommendation": r["recommendation"],
            # A conforming brief's row (brief v10 step AF): the copy it
            # proposed is the recommendation, and these say so.
            **_contract_marks(ev),
            # The structured-data block the row is about (brief v16 step
            # AS), which is the only anchor the rows carry and so the only
            # thing that can pin a finding to a node in the picture (brief
            # v16a step AT-b, RENDER_RULES section 7).
            #
            # `site_states` has extracted this since v16 and this payload
            # never did, which is why the fix cards could show a block
            # reference the picture could not: the dashboard reads them
            # from two different payloads. The picture is built here, so it
            # had to be here too - it was reading a key that was never on
            # the dict, dropping every anchor, and drawing every node
            # clean. Found by the rendered guard, which is what a browser
            # assertion is for: nothing about the source said so.
            "block": _evidence_key(ev, "block"),
            "pages": len(urls), "urls": urls[:10],
            # What the check found before its own cap, or None where the row
            # predates the column (migration 0030). Three numbers rather than
            # two, and that is the point: `total` is what was found, `pages`
            # is what the emitter kept, `urls` is what this payload carries.
            # The disclosure used to state the third against the second and
            # call it the first (UX-93, Q-26).
            "total": r["affected_total"],
            # Neither count above answers it: `pages` counts entries that may
            # not be URLs at all and `urls` is truncated to ten. The tick
            # branches on this, and only the server may decide it.
            "names_a_page": names_a_page(urls),
            # Where in the page's outline the fault is (FEATURES.md F-07).
            # Only `heading-skip` records one, and only since it began to:
            # a finding stored before that carries no position, and the key
            # is absent rather than guessed at — the screen leaves the
            # outline unopened for those, which is the honest answer.
            **({"outline_index": fault} if fault is not None else {}),
        })
        pages[cat] |= set(urls)

    contested = {c for c, srcs in sources_per_check.items() if len(srcs) > 1}

    order = {sev: i for i, sev in enumerate(
        ("critical", "high", "medium", "low", "info"))}
    # The pages the narrow may name, computed here rather than in the return
    # dict because it is now also a denominator (item 155): the part's page
    # count is a count over the RECORD, and a count states the population it
    # was counted over. Same expression, moved up.
    record_page_list = sorted(all_pages | set(_canonical([
        u for (urls,) in conn.execute(
            f"""SELECT f.affected_urls FROM finding_states fs
                JOIN findings f ON f.rowid = ({_latest_finding()})
                WHERE fs.site_id = ? AND fs.state = 'candidate'""", (site_id,))
        for u in json.loads(urls or "[]")])))
    # Seen once, per part (item 180, ruling 20260918-0401). A candidate never
    # counts into open, anywhere; but a bare 0 on a part whose analysis has
    # filed rows nobody has confirmed yet is a lie of omission, so the figure
    # carries its companion. Coverage notes are set aside as they are above.
    seen_once: dict[str, int] = {}
    if not page_url:
        for r in conn.execute(
                f"""SELECT f.check_id, f.dimension, f.severity FROM finding_states fs
                    JOIN findings f ON f.rowid = ({_latest_finding()})
                    WHERE fs.site_id = ? AND fs.state = 'candidate'""", (site_id,)):
            if is_coverage_note(r["check_id"], r["severity"]):
                continue
            key = an.categorise(r["check_id"], r["dimension"])
            seen_once[key] = seen_once.get(key, 0) + 1
    categories = []
    for c in an.CATEGORIES:
        items = sorted(buckets[c.key],
                       key=lambda f: (order.get(f["severity"], 9), -f["pages"]))
        # Coverage notes are listed among the part's findings - the causes
        # table shows them - but never counted (brief v5 step S): the
        # total, and so the sidebar's badge, is what the record counts.
        counted = [f for f in items if not is_coverage_note(f["check_id"], f["severity"])]
        categories.append({
            "key": c.key, "label": c.label, "group": c.group, "blurb": c.blurb,
            # Whether the catalogue lists any analysis for this part (the
            # channel, 20260924-0220-180). A part whose analyses no lane
            # offers - `workflow`, whose one runnable analysis is the client
            # plan, from Reports - cannot be read from where "not read"
            # sends the reader, so it is neither read nor unread.
            "catalogued": c.key in set(part_of.values()),
            # The findings counts, each carrying the population it was
            # gathered over (item 156, completing 155). Integers until now,
            # and 155's own report said what that left open: a component
            # written next month could read `part.total` and render it bare,
            # and no test would notice, because the rule lived in a convention
            # about which field to read rather than in the type of the field.
            # That is the exact shape of 139a - a rule that was true, written
            # down, and invisible to the next block written against it.
            #
            # `of` is None on all three: a findings count is not a subset of a
            # page set, so `12 of 68` here would divide two different things.
            # The renderer states the value plain and names where it came from.
            #
            # `notes` stays an integer deliberately. It is not a count the
            # screen draws - it rides in the sidebar badge's TITLE as "N
            # coverage notes not counted", which is a sentence about the
            # badge's own number rather than a figure of its own. A population
            # on it would be a fourth field nothing renders.
            "open": count(sum(1 for f in counted if f["state"] == "open"),
                          "record"),
            "regressed": count(
                sum(1 for f in counted if f["state"] == "regressed"), "record"),
            "total": count(len(counted), "record"),
            "seen_once": count(seen_once.get(c.key, 0), "record"),
            "notes": len(items) - len(counted),
            # A count over the RECORD, said so (item 155). This is the pages
            # carrying an open finding across every run, not the pages this
            # run fetched — the docstring below has always said so and the
            # screen had no way to know it. `record` is legal here: "the parts
            # that share these pages" is a what-we-know statement, not a fault
            # rate. Prevalence is computed per check against the crawl.
            #
            # And `of` is gone (audit F7, 2026-09-18), because the reasoning
            # above was sound and the field contradicted it. A non-null `of` IS
            # the ratio form by `Counted`'s own contract, so the record became
            # a visible denominator and the Analyses headline read "affect the
            # same 1 of 1 pages in the record" - 100% - about a 53-page site.
            # `POPULATION_BASIS` says of this population, in as many words:
            # "Never a prevalence denominator." A what-we-know statement
            # renders plain, which is what dropping `of` makes it.
            "pages": count(len(pages[c.key]), "record"),
            "tools": an.tools_for(c.key),
            "brief_checks": brief_checks.get(c.key, []),
            # Every check id the engine filed under this part on the rows in
            # scope, uncapped (brief v25 step BP). The Fixes block's "belongs"
            # read the brief's enumeration and the part's prefixes only, so a
            # sweep row filed here that no brief names - Crawl's
            # `http-status-error`, Indexability's `canonical-missing` on
            # twenty22 - had no card when those parts moved to three blocks.
            "filed_checks": sorted({f["check_id"] for f in counted}),
            # The prefixes whose dynamically-named checks belong to this part
            # (item 136o). `axe-<rule>` is minted from axe-core's rule set at
            # run time, so no enumeration can list them - the ENGINE already
            # knows this and files them by prefix (`CHECK_PREFIX_CATEGORY`).
            # The Fixes block was the one place still using an enumerated
            # list, and so had no card for a barrier the overlay boxed. It
            # reads this now, so one rule decides "belongs to this part".
            "check_prefixes": [pre for pre, cat in an.CHECK_PREFIX_CATEGORY
                               if cat == c.key],
            # What each of those costs to answer (brief v17 step AV1):
            # `free` where the sweep emits it, `model` where only a brief
            # can. The part page splits its table and its fixes on this,
            # and the operator is owed the distinction before they press
            # anything - "here is what we found for nothing" is the first
            # half of every conversation about an audit.
            "check_cost": {ch: _check_cost(ch) for ch in brief_checks.get(c.key, [])},
            # The checks of this part that can only ever be held, and what
            # each is held for (brief v15 step AR). Sent whether or not a
            # brief has run: a check nothing can assess has no pass to
            # report, and the page must not read its absence as one.
            "brief_held_only": [
                {"check": ch, "needs": _onp.HELD_ONLY_NEEDS[ch.split("/")[-1]]}
                for ch in brief_checks.get(c.key, [])
                if ch.split("/")[-1] in _onp.HELD_ONLY_NEEDS],
            "brief_dropped": brief_dropped.get(c.key, 0),
            "brief_dropped_rows": brief_dropped_rows.get(c.key, [])[:200],
            "brief_not_assessable": brief_not_assessable.get(c.key, 0),
            # Brief v13 step AO: the held rows themselves, the run that
            # produced them, and the brief's own verdict sentence.
            # `*` is what a brief writes where it could not assess a check
            # anywhere on the site, and a site-wide answer is an answer
            # about this page too. Narrowing dropped those rows, and the
            # part page then counted the check among the ones that pass on
            # the page - observed on Birch, where `img-sitemap-missing`
            # read as passing on the home page while the brief was saying
            # site-wide that it could not judge it.
            "brief_held": [h for h in brief_held.get(c.key, [])
                           if not page_url or h["page"] in ("*", "")
                           or _page_key(h["page"]) == _page_key(page_url)],
            "brief_eligibility": brief_eligibility.get(c.key, []),
            "brief_map": brief_map.get(c.key, []),
            "brief_clusters": brief_clusters.get(c.key, []),
            # Brief v20 (items 147, 148). `brief_fixes` is shared by both
            # parts and is why the fix is stored once and pointed at by
            # `fix_id` on each row: one change repeated per row is how a
            # single markup fix came to read as six on the Images part.
            "brief_templates": brief_templates.get(c.key, []),
            "brief_locales": brief_locales.get(c.key),
            "brief_fixes": brief_fixes.get(c.key, []),
            "brief_schema": brief_schema.get(c.key),
            "brief_security": brief_security.get(c.key),
            "brief_ai_surface": brief_ai_surface.get(c.key),
            "brief_entity": brief_entity.get(c.key),
            "brief_run": brief_run.get(c.key),
            "brief_summary": brief_summary.get(c.key),
            "brief_prose": brief_prose.get(c.key),
            # The smallest run this section can ask for, and what else it
            # moves (FEATURES.md F-06's present-capability fallback). Null
            # means no sweep refreshes this section at all — the
            # `ANALYSIS_ONLY` case — which is a different answer from "not
            # measured" and is why the key is present rather than omitted:
            # the screen states it rather than falling silent.
            "refresh": an.refresh_for(c.key),
            # Item 212: the audit that last measured THIS part - the one its
            # provenance line names - by the dimension that line prints.
            "sweep_run": (sweep := _latest_sweep(conn, site_id, (dim := (
                an.refresh_for(c.key) or {}).get("dimension")))),
            # Item 239 step 6: the dates the part's items were measured on,
            # and the ages at which a date says it may be, or is, out of date.
            "measured_range": latest_view.part_range(conn, site_id, dim, sweep),
            "age_thresholds": ages,
            # Item 243: the page in view has left the site as this part's
            # reference crawls saw it - "not seen since <date>", in place of
            # an age. None at site scope, and for a page still on the site.
            "gone_since": (latest_view.gone(conn, site_id, dim).get(_path_of(page_url))
                           if page_url and dim else None),
            "findings": items[:50],
            "contested": sorted({f["check_id"] for f in items
                                 if f["check_id"] in contested}),
        })

    facts = page_facts(conn, site_id, page_url) if page_url else None
    # The Structured data picture (brief v16a step AT-b). Built here rather
    # than in the category loop above because it needs both halves - the
    # page's blocks and the part's rows - and only this point has both. One
    # part carries it: a graph of JSON-LD nodes is not a shape the Headings
    # or Images parts have anything to draw.
    for c in categories:
        if c["key"] == "schema":
            # The page's own eligibility rows (item 242). The part's list is
            # every page the analysis judged; handed over whole, the page view
            # drew ~55 unnamed rows under `/` that read as one line repeated.
            c["graph"] = schema_graph_payload(
                facts, c["findings"],
                [e for e in c["brief_eligibility"]
                 if page_url and _path_of(str(e.get("page") or "")) == _path_of(page_url)],
                _page_type_of(conn, site_id, page_url) if page_url else "")
        # Item 224: the site view has no page in hand, so the Headings card
        # diffed the brief's corrected outline against nothing and tagged all
        # 38 lines of /website-seo/ `[proposed]`. The outline the crawl kept
        # for each page an analysis row names is the baseline it needs.
        if c["key"] == "headings" and not page_url:
            c["page_outlines"] = _page_outlines(
                conn, site_id, [ch.split("/")[-1] for ch in c.get("brief_checks") or []])

    return {
        "groups": list(an.GROUPS) + [an.WORKFLOW],
        "categories": categories,
        # Which scoring dimensions actually fed each category, on THIS site.
        # The two vocabularies sit on the same screen — a category is how you
        # fix something, a dimension is how it scores — with nothing joining
        # them, so a reader seeing "Headings" had no way to know it lands in
        # ONP. Derived from the findings rather than from a static table, so
        # it describes the data in front of the reader and cannot drift.
        "category_dimensions": {
            c["key"]: sorted({f["dimension"].split(":")[0]
                              for f in c["findings"] if f.get("dimension")})
            for c in categories},
        "total": sum(c["total"]["value"] for c in categories),
        # What the page filter left out because it belongs to no page (audit
        # F15). The screen states it; without it, page mode's total was a
        # smaller number than the site's with nothing accounting for the
        # difference, and `population.tsx` says of this population that a
        # site-scoped count "sits inline with the part's other counts rather
        # than outside the rule" - in page mode it sat outside the rule
        # entirely, by being removed.
        "site_only": site_only,
        # Only meaningful across a whole site; see the docstring.
        "related": ({} if page_url
                    else {c.key: an.related(pages, c.key) for c in an.CATEGORIES}),
        # The headline the dashboard used to compute for itself. Served so the
        # client report can carry the same sentence and the same number.
        "shared_cause": (None if page_url else an.shared_cause(
            pages, {c["key"]: c["total"]["value"] for c in categories},
            sum(c["total"]["value"] for c in categories))),
        # Pages carrying at least one open finding — NOT pages crawled, and
        # not scoped to one run. Open state is site-scoped: a finding raised
        # by an older run and never fixed is still open, and its page counts
        # here. The client screen used to label this "pages seen" while the
        # Tools header showed the selected run's crawl size, so the same site
        # reported 101 on one screen and 187 on the other with nothing saying
        # they were different questions. Both labels now name their scope.
        # The pages the narrow may name (brief v12 step AM): those with
        # something open, and those a brief's candidate row names - the
        # replacement table shows candidates, so the narrow can reach them.
        "pages": record_page_list,
        # The standing position, not the last run's output. This screen never
        # was run-scoped; now it says so.
        "current": current_state(conn, site_id),
        # The sweep behind the counts (brief v13 step AO): the part page
        # names the run rather than showing a dot for it.
        "sweep_run": _latest_sweep(conn, site_id),
        "page": page_url,
        "facts": facts,
    }


#: A finding's severity as RENDER_RULES §7 names it. `critical` maps to
#: High because the picture has four open levels and the register has five;
#: a Critical drawn in a ring of its own would be a fifth colour nothing
#: else in the design uses, and the row itself still says "critical".
_GRAPH_SEV = {"critical": "High", "high": "High", "medium": "Medium",
              "low": "Low", "info": "Info"}


def _graph_anchors(row: dict, inventory: list[dict]) -> list[str]:
    """Where a part row lands in the picture, from what the row already says.

    RENDER_RULES §7 names five anchor forms. The rows carry exactly one of
    them today: `block`, written as `Type#n` by brief v16 step AT, where `n`
    indexes the flattened inventory. That is mapped to the node's `@id` here
    - the model keys top-level nodes by `@id` - and everything else is left
    to the checks that will emit it.

    **Derived, not invented.** §7's own rule is that an anchor resolving to
    nothing is dropped rather than guessed at, and the same reasoning applies
    one level up: a row with no `block` gets no anchor, and its fix card is
    reachable from the checklist rather than pinned to a node the row never
    named. Pinning by `@type` alone would put a finding about one of three
    Organization nodes on all three.
    """
    ref = row.get("block")
    if not isinstance(ref, str) or "#" not in ref:
        return []
    try:
        n = int(ref.rsplit("#", 1)[1])
    except ValueError:
        return []
    if not 1 <= n <= len(inventory):
        return []
    entry = inventory[n - 1]
    node_id = entry.get("id")
    return [node_id] if node_id else []


#: The keys a registered identifier arrives under in schema.org markup, in the
#: order a suggestion lists them. `identifier` is last because it is the
#: generic one and often carries something that is not a registration at all.
ID_KEYS = ("taxID", "vatID", "leiCode", "duns", "identifier")


def _id_strings(raw: dict) -> list[str]:
    """Registered identifiers as strings, from whichever key holds them.

    Never validated and never reshaped: the format differs by jurisdiction,
    and an ABN rewritten into groups of three is no longer the string the
    operator would recognise. A `PropertyValue` contributes
    `name: value` so the reader can see which registry it names.
    """
    out = []
    for key in ID_KEYS:
        value = raw.get(key)
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("propertyID") or "").strip()
                text = str(item.get("value") or "").strip()
                text = f"{name}: {text}" if name and text else text
            else:
                text = str(item or "").strip()
            if text and text not in out:
                out.append(f"{key}: {text}" if key == "identifier" and ":" not in text else text)
    return out


def entity_record_suggestions(conn: sqlite3.Connection, site_id: str) -> dict:
    """What the site's own structured data says about the three record fields
    migration 0063 added (item 145 step BH).

    A suggestion, never a value. The operator accepts each one in Admin and
    nothing here writes to the record, for a reason the brief's own checks
    turn on: `entity-unresolvable` judges the node's `sameAs` against the
    record's identifiers, and `entity-footprint-unlinked` judges the record's
    profiles against what the pages link and pin. A record filled from the
    markup it is compared against makes both of them agree with themselves,
    which is worse than an empty field — an empty field is honest and says so.

    Read from the newest run that stored a crawl, off the home page's graph
    model, which is the same model `schema-island` and `AIS/entity-*` read.
    Empty everywhere is the ordinary answer: most sites name none of this.
    """
    from urllib.parse import urlsplit

    from clauditseo import schema_graph as _sg

    run = None
    # A reading of the site, not any run that stored a crawl: a verification
    # or a page scan carries the pages it was pointed at, and this reads the
    # home page. Without the question the fallback below would offer an
    # arbitrary page's entity node as though it were the site's.
    for row in conn.execute(
            "SELECT id, started_at, crawl_evidence FROM audit_runs"
            " WHERE site_id=? AND crawl_evidence IS NOT NULL"
            f" AND {kind_is_site_reading()}"
            " ORDER BY started_at DESC, rowid DESC", (site_id,)):
        try:
            blob = json.loads(row["crawl_evidence"]) or {}
        except (TypeError, ValueError):
            continue
        if blob.get("pages"):
            run = (row["id"], row["started_at"], blob)
            break
    empty = {"run_id": None, "measured_at": None, "home": None, "entity_type": None,
             "legal_name": None, "registered_ids": [], "external_profiles": []}
    if run is None:
        return empty
    run_id, started_at, blob = run
    start = (blob.get("start_url") or "").rstrip("/")
    home = next((p for p in blob["pages"]
                 if (p.get("url") or "").rstrip("/") == start), None) or blob["pages"][0]
    facts = page_facts(conn, site_id, home.get("url") or "")
    blocks = []
    for entry in ((facts or {}).get("jsonld_raw") or []):
        if not isinstance(entry, dict):
            continue
        try:
            blocks.append({"source": entry.get("source") or "inline",
                           "json": json.loads(entry.get("text") or "")})
        except (TypeError, ValueError):
            continue
    out = dict(empty, run_id=run_id, measured_at=started_at, home=home.get("url"))
    if not blocks:
        return out
    host = urlsplit(home.get("url") or "").netloc.lower().removeprefix("www.")
    model = _sg.build_model(blocks, None, {"host": host, "page": "/", "page_type": "home"}, [])
    node = model.node(model.entity_key) if model.entity_key else None
    if node is None:
        return out
    raw = node.raw or {}
    same_as = raw.get("sameAs") or []
    out["entity_type"] = "/".join(node.types) or None
    out["legal_name"] = str(raw.get("legalName") or "").strip() or None
    out["registered_ids"] = _id_strings(raw)
    # `claimed` is the operator's statement and is never guessed here: a pin
    # in `sameAs` says the site asserts the profile, not that anyone claimed
    # it on the platform.
    out["external_profiles"] = [{"url": str(u).strip(), "claimed": None}
                                for u in (same_as if isinstance(same_as, list) else [same_as])
                                if str(u).strip()]
    return out


def schema_graph_payload(facts: dict | None, items: list[dict],
                         eligibility: list[dict],
                         page_type: str = "") -> dict | None:
    """The Structured data picture as a model, built here and only drawn
    by the dashboard (brief v16a step AT-b).

    Server-side because the picture has to be reproducible from what a crawl
    stored, months later, without the page being fetched again - a model
    built in the browser would be a drawing of whatever the browser could
    see. `schema_graph.build_model` is the same call the sweep makes for
    `schema-island`, so the row and the picture cannot disagree.

    `None` where the run predates `jsonld_raw`: the part page then draws the
    block cards it drew before, which is a smaller answer rather than a
    wrong one.
    """
    from clauditseo import schema_graph as _sg

    raw = (facts or {}).get("jsonld_raw")
    if not raw:
        return None
    blocks = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            blocks.append({"source": entry.get("source") or "inline",
                           "json": json.loads(entry.get("text") or "")})
        except (TypeError, ValueError):
            # The block does not parse. `schema-invalid-json` is the finding
            # that says so; drawing nothing for it here is the picture
            # agreeing with the row rather than a second opinion.
            continue
    if not blocks:
        return None
    inventory = (facts or {}).get("schema_inventory") or []
    shaped = []
    for i, row in enumerate(items):
        held = bool(row.get("needs"))
        shaped.append({
            "n": i + 1,
            "sev": "Held" if held else _GRAPH_SEV.get(row.get("severity"), "Info"),
            "name": row.get("summary") or row.get("check_id") or "",
            # Qualified `DIM/check`, which is the form the fix cards and the
            # prompt registry both use. A bare id here would look right and
            # join with nothing: the card's own `check` carries the
            # dimension, and section 7's agreement between a badge and a
            # card is exactly this string matching.
            "checks": ([f"{row['dimension']}/{row['check_id']}"]
                       if row.get("check_id") and row.get("dimension")
                       else [row["check_id"]] if row.get("check_id") else []),
            "src": "analysis" if row.get("source") == "model-judgement" else "free",
            "anchors": _graph_anchors(row, inventory),
        })
    model = _sg.build_model(
        blocks, None,
        {"host": _graph_host((facts or {}).get("url") or ""),
         "page": (facts or {}).get("url") or "",
         "page_type": page_type,
         "footer_profile_links": (facts or {}).get("profile_links") or []},
        shaped, eligibility)
    return model.as_dict()


def _page_type_of(conn: sqlite3.Connection, site_id: str, url: str) -> str:
    """What the site record calls this page, or "" where it says nothing.

    The same reading `onp._page_type_for` makes, for the same reason: the
    page-type map is what decides which expected-but-absent ghosts may be
    drawn (RENDER_RULES §6), and guessing a type would put a ghost in the
    "not on the page" zone that the map never asked for. The site root is
    the exception and is the home page - a fact about the URL rather than an
    inference about content.
    """
    from urllib.parse import urlsplit
    from .repo import get_site

    site = get_site(conn, site_id) or {}
    types = site.get("page_types") or {}
    if not isinstance(types, dict):
        types = {}
    try:
        path = urlsplit(url).path or "/"
    except ValueError:
        return ""
    return str(types.get(path) or types.get(url) or ("home" if path == "/" else ""))


#: The clicks past which a page is hard for a crawler to keep fresh and hard
#: for a person to find. The dashed rule on the depth block sits between this
#: depth and the next, and the dashboard reads the number from the payload
#: rather than repeating the 3 in a second file.
DEEP_CLICKS = 3


#: A step's label, per check. `{n}` is the number of distinct normalised
#: selectors in the group - what the operator actually has to touch - and
#: not the instance count, which is how many times they touch it.
FIX_PHRASES = {
    "link-name-missing": "Name the {n} link{s}",
    "link-text-generic": "Rewrite the {n} generic link text{s}",
    "duplicate-id": "Make the {n} id{s} unique",
    "form-control-unlabelled": "Label the {n} control{s}",
    "landmark-main-missing": "Add a main landmark",
    "button-name-missing": "Name the {n} button{s}",
    "iframe-title-missing": "Title the {n} iframe{s}",
    "tabindex-positive": "Remove the positive tabindex from {n} element{s}",
    "aria-reference-broken": "Repair {n} broken aria reference{s}",
    "axe-color-contrast": "Contrast on {n} element{s}",
}

#: A group on fewer than this many assessed pages is never called a
#: template, whatever its ratio. Two of two pages is 100% and means nothing;
#: the classification is a claim about repetition and three is the least
#: that can evidence one.
TEMPLATE_MIN_PAGES = 3
#: Chrome is the site's furniture: everywhere, or in the furniture regions.
CHROME_SHARE = 0.90
CHROME_LANDMARKS = frozenset({"header", "nav", "footer"})
#: A template group repeats within one template and not across the site.
TEMPLATE_SHARE = 0.60
#: Steps drawn before the rest is rolled into one. A waterfall of forty bars
#: is a list, and a list is what the record already is.
MAX_STEPS = 10


def _plural(n: int) -> str:
    return "" if n == 1 else "s"


def fix_order_payload(conn: sqlite3.Connection, site_id: str,
                      run_id: str | None) -> dict | None:
    """Open A11Y instances grouped into the order they are worth fixing in.

    **Instances, not rows.** Every count here is the sum of
    `evidence.count` over the rows involved (136j Part A). One row saying
    "12 links on / have no accessible name" is twelve instances and one
    fix; before 136j the number lived in that sentence and this block could
    not have been built at all.

    A step is one `(check, normalised selector)` group - the normalised
    form, so a framework's generated ids do not split one repeated element
    into one group per page. Steps are classified by where their instances
    sit and on how many of the pages *that check assessed*:

    * **chrome** - every instance in a header, nav or footer, or the group
      on at least 90% of assessed pages. The site's furniture: one edit,
      every page.
    * **template** - at least 60% of assessed pages and under the chrome
      share. One edit, one template's worth of pages.
    * **page by page** - the rest, rolled up per check.

    **The denominator is pages the check assessed, not pages crawled**, and
    the two differ by two orders of magnitude here. The static checks read
    every crawled page; `axe-*` reads only what the rendered pass visited -
    5 of 227 on Acme at T2. Calling a group "on every page" because it
    appears on the five pages a sampler chose would be the block's worst
    possible lie, so an `axe-*` group carries its own denominator and says
    it.
    """
    rows = conn.execute(
        f"""SELECT f.check_id, f.evidence, f.affected_urls, f.severity
            FROM finding_states fs
            JOIN findings f ON f.rowid = ({_latest_finding()})
            WHERE fs.site_id = ? AND fs.state = 'open' AND f.dimension = 'A11Y'""",
        (site_id,)).fetchall()
    if not rows:
        return None

    # How many pages each kind of check looked at. The rendered sample is
    # recorded by `axe-sampled` where the pass sampled at all; where it did
    # not, every crawled page was rendered.
    crawled, rendered = _assessed_pages(conn, site_id, run_id)

    groups: dict[tuple[str, str], dict] = {}
    per_check_loose: dict[str, dict] = {}
    total = 0
    for r in rows:
        try:
            ev = json.loads(r["evidence"] or "{}")
        except ValueError:
            continue
        instances = ev.get("instances")
        if not isinstance(instances, list):
            continue
        count = ev.get("count")
        if not isinstance(count, int):
            continue
        total += count
        urls = json.loads(r["affected_urls"] or "[]")
        page = urls[0] if urls else ""
        for inst in instances:
            if not isinstance(inst, dict):
                continue
            key = (r["check_id"], inst.get("selector_norm") or inst.get("selector") or "")
            g = groups.setdefault(key, {
                "check": r["check_id"], "selector": key[1], "instances": 0,
                "pages": set(), "landmarks": set(), "severity": r["severity"],
                "example": page, "rects": 0})
            g["instances"] += 1
            if page:
                g["pages"].add(page)
            g["landmarks"].add(inst.get("landmark") or "none")
            if inst.get("rect"):
                g["rects"] += 1
        # A row whose instances do not add to its own count has lost some on
        # the way; the difference is kept against the check so the steps
        # still sum. `landmark-main-missing` is the designed case - its
        # count is 0 and its instances are context, per 136j.
        drift = count - len([i for i in instances if isinstance(i, dict)])
        if drift:
            loose = per_check_loose.setdefault(
                r["check_id"], {"check": r["check_id"], "instances": 0,
                                "pages": set(), "severity": r["severity"],
                                "example": page})
            loose["instances"] += drift
            if page:
                loose["pages"].add(page)

    steps = []
    for g in groups.values():
        assessed = rendered if g["check"].startswith("axe-") else crawled
        share = (len(g["pages"]) / assessed) if assessed else 0.0
        marks = g["landmarks"] - {"none"}
        chrome_by_region = bool(marks) and marks <= CHROME_LANDMARKS
        if assessed < TEMPLATE_MIN_PAGES:
            kind = "page"
        elif chrome_by_region or share >= CHROME_SHARE:
            kind = "chrome"
        elif share >= TEMPLATE_SHARE:
            kind = "template"
        else:
            kind = "page"
        steps.append({
            "check": g["check"], "selector": g["selector"], "kind": kind,
            "instances": g["instances"], "pages": len(g["pages"]),
            "assessed": assessed, "share": round(share, 3),
            "landmarks": sorted(marks), "severity": g["severity"],
            "example": g["example"], "rects": g["rects"],
            "label": _fix_label(g["check"], 1, sorted(marks), kind),
        })

    # One step per (check, kind), not per selector.
    #
    # The item groups by `(check, normalised selector)` to CLASSIFY, and its
    # phrase table then asks for "{n} links" where n is "distinct normalised
    # selectors in the group". Those two only fit together if the steps are
    # merged after classification: a group of one selector always has n = 1,
    # which would make the phrase table's parameter dead and draw six
    # identical bars reading "Make the 1 id unique in the nav" - measured on
    # Acme before this merge, and the reason it is here.
    #
    # Kind stays in the key. A chrome edit and a page-by-page edit of the
    # same check are different pieces of work - one touches a template, the
    # other touches forty pages - and merging them would be the block
    # claiming a single fix where there are two.
    by_step: dict[tuple[str, str], dict] = {}
    for st in steps:
        key = (st["check"], st["kind"])
        r = by_step.get(key)
        if r is None:
            by_step[key] = {**st, "selector": "", "selectors": 1,
                            "pages_seen": set(), "marks": set(st["landmarks"])}
            by_step[key]["pages_seen"].add(st["pages"])
        else:
            r["instances"] += st["instances"]
            r["pages"] = max(r["pages"], st["pages"])
            r["selectors"] += 1
            r["marks"] |= set(st["landmarks"])
            r["rects"] += st["rects"]
    for check, loose in per_check_loose.items():
        key = (check, "page")
        r = by_step.get(key)
        if r is None:
            by_step[key] = {
                "check": check, "selector": "", "kind": "page",
                "instances": loose["instances"], "pages": len(loose["pages"]),
                "assessed": rendered if check.startswith("axe-") else crawled,
                "share": 0.0, "landmarks": [], "marks": set(),
                "severity": loose["severity"], "example": loose["example"],
                "rects": 0, "selectors": 0}
        else:
            r["instances"] += loose["instances"]
    rolled: list[dict] = []
    for r in by_step.values():
        r["landmarks"] = sorted(r.pop("marks", set()) or [])
        r.pop("pages_seen", None)
        rolled.append(r)

    for st in rolled:
        st["label"] = _fix_label(st["check"], st.get("selectors", 1),
                                 st.get("landmarks") or [], st["kind"])
    rolled.sort(key=lambda st: (-st["instances"], st["check"], st["selector"]))

    # Cap, with the tail rolled into one so the sum still holds.
    shown, tail = rolled[:MAX_STEPS], rolled[MAX_STEPS:]
    if tail:
        shown.append({
            "check": "", "selector": "", "kind": "page",
            "instances": sum(t["instances"] for t in tail),
            "pages": 0, "assessed": crawled, "share": 0.0, "landmarks": [],
            "severity": "info", "example": "", "rects": 0, "selectors": 0,
            "label": f"Everything else ({len(tail)} more fixes)"})

    # Where the remainder crosses three quarters: the item's "after step K".
    running, k = total, None
    for i, st in enumerate(shown, 1):
        running -= st["instances"]
        if k is None and total and (total - running) / total >= 0.75:
            k = i
    return {"total": total, "steps": shown, "clears_75_at": k,
            "crawled": crawled, "rendered": rendered,
            # The sum is asserted by a test rather than trusted, and the
            # payload carries it so a screen can say when it does not hold
            # instead of drawing bars that quietly do not add up.
            "sum": sum(st["instances"] for st in shown)}


def _fix_label(check: str, selectors: int, landmarks: list[str], kind: str) -> str:
    phrase = FIX_PHRASES.get(check)
    if not phrase:
        return check or "Everything else"
    text = phrase.format(n=selectors, s=_plural(selectors))
    if kind == "chrome" and landmarks:
        where = " and ".join(landmarks[:2])
        return f"{text} in the {where}"
    return text


def _assessed_pages(conn: sqlite3.Connection, site_id: str,
                    run_id: str | None) -> tuple[int, int]:
    """(pages the static checks read, pages the rendered pass read).

    They are the same number only when the sampler took everything. The
    second is what an `axe-*` share is a share OF, and reading the first for
    both is how a group on five sampled pages becomes "on every page".
    """
    crawled = rendered = 0
    row = conn.execute(
        "SELECT evidence FROM findings WHERE run_id=? AND check_id='axe-sampled'"
        " LIMIT 1", (run_id,)).fetchone() if run_id else None
    if row:
        try:
            ev = json.loads(row["evidence"] or "{}")
            crawled = int(ev.get("crawled") or 0)
            rendered = int(ev.get("rendered") or 0)
        except (ValueError, TypeError):
            pass
    if not crawled and run_id:
        # No `axe-sampled` row, which is what a run that rendered everything
        # it crawled looks like - including a one-page scan. The run's own
        # evidence is then the population, read the way
        # `crawl_depth_payload` reads it.
        evidence_raw = evidence_text(conn, run_id)
        if evidence_raw:
            try:
                pages = (parsed_evidence(evidence_raw) or {}).get("pages") or []
                crawled = len([p for p in pages if p.get("status") == 200])
            except (ValueError, TypeError):
                pass
    return crawled, (rendered or crawled)


def a11y_page_payload(conn: sqlite3.Connection, site_id: str,
                      run_id: str | None, page_url: str,
                      order: dict | None = None) -> dict | None:
    """One page's accessibility barriers, and the picture to draw them on.

    **The absent case is the common one and is not an error.** The rendered
    pass samples - 5 of 227 pages on Acme at T2 - so most pages have no
    screenshot and no rects, and this returns the counts that let the screen
    say which run and tier decided that rather than showing an empty canvas.

    Static instances draw too where they can. They carry a selector but no
    rect (nothing measured them), so they are listed with "position not
    recorded" and no box. The item is explicit that the page is NOT
    re-rendered to find them: a second render would be a second page, and
    boxes from one page drawn over a picture of another is worse than no
    boxes.
    """
    if not run_id or not page_url:
        return None

    rows = conn.execute(
        "SELECT check_id, severity, summary, evidence, affected_urls"
        " FROM findings WHERE run_id=? AND dimension='A11Y'", (run_id,)).fetchall()

    # Which pages the pass photographed, off the row that already records
    # what it rendered.
    screens: dict[str, dict] = {}
    rendered = crawled = 0
    for r in rows:
        try:
            ev = json.loads(r["evidence"] or "{}")
        except ValueError:
            continue
        if ev.get("screens"):
            screens.update(ev["screens"])
        if r["check_id"] == "axe-sampled":
            rendered = int(ev.get("rendered") or 0)
            crawled = int(ev.get("crawled") or 0)

    shot = screens.get(page_url) or {}
    # Chrome groups, so a row can say "on every page" without the screen
    # recomputing the classification Block 1 already made.
    chrome = {st["check"] for st in ((order or {}).get("steps") or [])
              if st.get("kind") == "chrome"}

    barriers: list[dict] = []
    for r in rows:
        urls = json.loads(r["affected_urls"] or "[]")
        if page_url not in urls:
            continue
        try:
            ev = json.loads(r["evidence"] or "{}")
        except ValueError:
            continue
        for inst in (ev.get("instances") or []):
            if not isinstance(inst, dict):
                continue
            barriers.append({
                "check": r["check_id"],
                "selector": inst.get("selector") or "",
                "impact": _impact_of(r["severity"]),
                "help": (ev.get("help") or r["summary"] or "")[:200],
                "chrome": r["check_id"] in chrome,
                **({"rect": inst["rect"]} if inst.get("rect") else {}),
            })
    # Numbered after ordering, so the badge on a box and the badge on its row
    # are the same number and both are stable across a redraw.
    barriers.sort(key=lambda b: (0 if b.get("rect") else 1,
                                 b["check"], b["selector"]))
    for n, b in enumerate(barriers, 1):
        b["n"] = n

    return {
        **_screen_of(run_id, page_url, shot),
        "barriers": barriers,
        "rendered": rendered or (1 if shot else 0),
        "crawled": crawled or 0,
    }


def _impact_of(severity: str) -> str:
    """axe's word for our severity, because the overlay's two tones are
    axe's four impacts folded in half and the rows show the word."""
    return {"critical": "critical", "high": "serious",
            "medium": "moderate", "low": "minor"}.get(severity or "", "minor")


#: A first path segment with at least this many pages is a template. The
#: rule is `anatomy.tsx`'s `templatesOf`, which groups FINDINGS; this groups
#: PAGES, so the rule is expressed twice and neither can call the other -
#: one runs in the browser over a finding list, the other here over a crawl.
#: Named rather than left implicit: if one moves, the grid and the cause
#: tables would group the same site differently and nothing would say so.
TEMPLATE_MIN_PAGES_IN_GROUP = 10


def _template_group(path: str) -> str:
    seg = [p for p in path.split("/") if p]
    return f"/{seg[0]}/" if seg else "/"


def security_headers_payload(conn: sqlite3.Connection,
                             run_id: str | None) -> dict | None:
    """The response headers every fetched page carried, by template group.

    **The column count is the number of groups that DISAGREE, minimum one.**
    That is the block's whole argument: a site serving the same headers
    everywhere is one column and eight rows, and one that does not is fanned
    only on the rows where it does not. A grid that always drew one column
    per group would make a uniform site look like a table of differences.

    Cells come from `security_headers.cell_state`, which the sweep's own
    `security-headers` check also calls, so the grid and the finding cannot
    disagree about the three rows they share. The other five have no check
    behind them and `covered_by_check` says so per row rather than letting a
    reader assume one.
    """
    if not run_id:
        return None
    from clauditseo import security_headers as sh

    evidence_raw = evidence_text(conn, run_id)
    if not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw) or {}
    except (ValueError, TypeError):
        return None

    # 200s only. A redirect is not a page and the brief keeps it out of this
    # grid; HSTS-on-a-redirect is a v20 check and would need the chain, not
    # the destination. Counted so the report can say how many there were.
    pages = [p for p in (evidence.get("pages") or []) if p.get("status") == 200]
    redirects = len([p for p in (evidence.get("pages") or [])
                     if 300 <= int(p.get("status") or 0) < 400])
    if not pages:
        return {"recorded": False, "pages": 0, "redirects": redirects,
                "groups": [], "rows": [], "fanned": False}
    if not any(p.get("headers") for p in pages):
        # The contract's absent-data state, not an empty grid: a run that
        # stored no headers is a different answer from a site that sets none.
        return {"recorded": False, "pages": len(pages), "redirects": redirects,
                "groups": [], "rows": [], "fanned": False}

    by_group: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for p in pages:
        # `_page_path`, not `_page_key`: the key keeps the query string
        # since it must tell a parameter variant from its base page, and a
        # group is about the first path segment.
        counts[_template_group(_page_path(p.get("url") or "/"))] = counts.get(
            _template_group(_page_path(p.get("url") or "/")), 0) + 1
    heads = {g for g, n in counts.items()
             if n >= TEMPLATE_MIN_PAGES_IN_GROUP and g != "/"}
    for p in pages:
        g = _template_group(_page_path(p.get("url") or "/"))
        by_group.setdefault(g if g in heads else "", []).append(p)

    groups = sorted(by_group, key=lambda g: (g == "", -len(by_group[g]), g))
    rows = []
    for key, label in sh.ROWS:
        anywhere = sh.anywhere_on_site(pages, key)
        cells = {}
        for g in groups:
            states = set()
            value = None
            for p in by_group[g]:
                headers = p.get("headers") or {}
                sets_cookies = bool(sh.observed(headers, "set-cookie")) or key != "set-cookie"
                states.add(sh.cell_state(key, headers, anywhere, sets_cookies))
                value = value or sh.observed(headers, key)
            # A group that is not uniform within itself takes its worst
            # state: the grid's claim is about the group, and saying "set"
            # because most of it is set would be the claim it is not making.
            order = [sh.MISSING, sh.WEAK, sh.ABSENT, sh.NA, sh.SET]
            cells[g] = next(s for s in order if s in states) if states else sh.NA
            cells[f"{g}\u0000value"] = value or ""
        agree = len({cells[g] for g in groups}) == 1
        rows.append({
            "key": key, "label": label, "agree": agree,
            "covered_by_check": key in sh.COVERED_BY_CHECK,
            "cells": {g: cells[g] for g in groups},
            "value": next((cells[f"{g}\u0000value"] for g in groups
                           if cells[f"{g}\u0000value"]), ""),
        })

    fanned = [r for r in rows if not r["agree"]]
    involved = [g for g in groups
                if any(len({r["cells"][x] for x in groups}) > 1
                       and r["cells"][g] != _majority(r, groups) for r in fanned)]
    return {
        "recorded": True,
        "pages": len(pages),
        "redirects": redirects,
        "fanned": bool(fanned),
        "groups": [{"key": g, "label": g or "everything else",
                    "pages": len(by_group[g])} for g in groups],
        "columns": ([g for g in groups if g in involved]
                    + [""] if fanned else []) if fanned else [],
        "rows": rows,
        "odd": _odd_route(fanned, groups, by_group),
        "in_place": len([r for r in rows if all(v == sh.SET for v in r["cells"].values())]),
        "absent_everywhere": [r["label"] for r in rows
                              if all(v == sh.ABSENT for v in r["cells"].values())],
    }


def _majority(row: dict, groups: list[str]) -> str:
    seen: dict[str, int] = {}
    for g in groups:
        seen[row["cells"][g]] = seen.get(row["cells"][g], 0) + 1
    return max(seen, key=lambda k: seen[k])


def _odd_route(fanned: list[dict], groups: list[str],
               by_group: dict[str, list[dict]]) -> dict | None:
    """The group that disagrees with the rest, and what it lacks.

    Named only where exactly one group is the odd one out. Two groups
    disagreeing in different directions is not "the odd route" and a
    sentence claiming it were would be the block inventing a story.
    """
    from clauditseo import security_headers as sh

    if not fanned:
        return None
    odd: dict[str, list[str]] = {}
    for r in fanned:
        for g in groups:
            if r["cells"][g] in (sh.MISSING, sh.WEAK) and r["cells"][g] != _majority(r, groups):
                odd.setdefault(g, []).append(r["label"])
    if len(odd) != 1:
        return None
    g, lacks = next(iter(odd.items()))
    pages = by_group.get(g) or []
    return {"group": g or "everything else", "lacks": lacks,
            "pages": len(pages),
            # A route that takes a customer's details is the one to fix
            # first, and the crawl already recorded whether the page posts.
            "form": any(p.get("has_post_form") for p in pages)}


def indexability_now_payload(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """The Indexability part's site-level "now" (item 137, brief v18 step BA).

    The canonical map and the headline counts, read off one stored run's crawl
    evidence. Per reached page, exactly one canonical bucket — `missing` (no
    canonical), `self` (canonical resolves to the page), `elsewhere_404`
    (canonical points at a page the crawl reached with a 4xx/5xx), or
    `elsewhere_200` (canonical points elsewhere and the target is not a reached
    error) — plus `conflicts_sitemap` as a cross-cut (a page the sitemap lists
    whose canonical points at another URL). The four headline counts are
    reached · indexable · noindex · canonical-elsewhere, with the redirect
    tally beside them.

    **What a stored crawl can and cannot say about redirects.** The evidence
    keeps each page's `redirect_chain` (the URLs before the final), so the
    number of redirects and how many take two or more hops are exact. It does
    NOT keep each hop's status, so `temporary` (a 302/303/307 on a permanent
    move) and `to_404` are not decidable here — they are the brief's job over a
    richer redirect log a live run captures, and are returned null rather than
    guessed. The URL convention is the scheme/host/trailing-slash the majority
    of reached 200s use, derived here so the brief and the part page read one.

    **A canonical target the crawl did not reach is counted optimistically**
    (as `elsewhere_200`, not `elsewhere_404`): only a target the crawl actually
    saw return an error is a `canonical-to-404`, and inventing a 404 for an
    unseen page is the fabrication the brief forbids. The rigorous dead-target
    call is the `canonical-to-404` check, not this snapshot.

    Returns None where there is no run or no stored crawl to read.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id FROM audit_runs WHERE id=?", (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None
    from urllib.parse import urlsplit
    from clauditseo.crawler.types import stored_page_is_eligible

    def _key(u: str) -> tuple[str, str]:
        # Host + path, trailing slash normalised: a self-canonical differing
        # only by scheme or a slash is still self, not a cross-URL canonical.
        s = urlsplit(u)
        p = s.path or "/"
        return (s.netloc, p if p == "/" else p.rstrip("/"))

    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    reached = [p for p in pages if stored_page_is_eligible(p)]
    # Every page the crawl saw, by key, with its status — for canonical-target
    # lookup (was the target reached, and with what status).
    status_by_key: dict[tuple[str, str], int] = {}
    for p in pages:
        st = p.get("status")
        if isinstance(st, int):
            status_by_key.setdefault(_key(p["url"]), st)

    sitemap_keys = {_key(u) for u in (evidence.get("sitemap_entries") or [])}

    def _noindex(p: dict) -> bool:
        blob = f"{p.get('meta_robots') or ''} {p.get('x_robots_tag') or ''}".lower()
        return "noindex" in blob

    cmap = {"self": 0, "param_variant": 0, "elsewhere_200": 0, "elsewhere_404": 0,
            "missing": 0, "conflicts_sitemap": 0}
    indexable = noindex = canonical_elsewhere = 0
    for p in reached:
        ni = _noindex(p)
        if ni:
            noindex += 1
        canon = p.get("canonical") or p.get("link_header_canonical")
        own = _key(p["url"])
        if not canon:
            cmap["missing"] += 1
            bucket = "missing"
        elif _key(canon) == own and urlsplit(canon).query != urlsplit(p["url"]).query:
            # Item 180 (ruling 20260918-0403): `/apply?product_type=loc`
            # canonicalising to `/apply` is not self - the host-and-path key
            # dropped the query, so the map counted it as self and read
            # "Elsewhere 0" beside a canonical chain drawing that very pointer.
            # It canonicalises elsewhere, to its own parameterless address.
            cmap["param_variant"] += 1
            canonical_elsewhere += 1
            bucket = "elsewhere"
            if own in sitemap_keys:
                cmap["conflicts_sitemap"] += 1
        elif _key(canon) == own:
            cmap["self"] += 1
            bucket = "self"
        else:
            canonical_elsewhere += 1
            tgt = status_by_key.get(_key(canon))
            if tgt is not None and tgt >= 400:
                cmap["elsewhere_404"] += 1
            else:
                cmap["elsewhere_200"] += 1
            bucket = "elsewhere"
            # A sitemap-listed page whose canonical sends indexation elsewhere.
            if own in sitemap_keys:
                cmap["conflicts_sitemap"] += 1
        # Indexable: reached 200, not noindex, and owning its own indexation.
        if p.get("status") == 200 and not ni and bucket in ("self", "missing"):
            indexable += 1

    # Redirects: exact from the stored chains; per-hop shapes are the brief's.
    with_redirect = [p for p in pages if p.get("redirect_chain")]
    chains = [p for p in with_redirect if len(p.get("redirect_chain") or []) >= 2]

    # URL convention: the scheme/host/slash the majority of reached 200s use.
    oks = [p for p in reached if p.get("status") == 200]
    scheme = _most_common(urlsplit(p["url"]).scheme for p in oks) or "https"
    host = _most_common(urlsplit(p["url"]).netloc for p in oks) or urlsplit(
        evidence.get("start_url") or "").netloc
    slash = _most_common((urlsplit(p["url"]).path or "/").endswith("/") for p in oks)

    return {
        "run_id": row["id"],
        "reached": len(reached),
        "indexable": indexable,
        "noindex": noindex,
        "canonical_elsewhere": canonical_elsewhere,
        "canonical_map": cmap,
        "redirects": {
            "total": len(with_redirect),
            "chains": len(chains),
            # Not decidable from a stored crawl — the brief's over a live log.
            "temporary": None,
            "to_404": None,
        },
        "convention": {"scheme": scheme, "host": host,
                       "trailing_slash": bool(slash)},
    }


def _most_common(values) -> object | None:
    """The most common value over an iterable, or None when it is empty.

    Named apart from `_majority` above, which is the response-headers grid's
    two-argument helper (a row and its groups) — a collision between the two
    silently shadowed that one at import and broke every payload that called
    it (item 137)."""
    from collections import Counter
    c = Counter(values)
    return c.most_common(1)[0][0] if c else None


#: The most pages whose outline the site view carries for the Headings cards
#: (item 224). A brief row names one page each and the headings brief returned
#: 24 on twenty22; past this, a card says its baseline was not loaded.
OUTLINE_PAGES_CAP = 40


def _page_outlines(conn: sqlite3.Connection, site_id: str, checks: list[str]) -> dict:
    """URL -> the outline the crawl kept for it, for every page a live
    analysis row on `checks` names that carries a replacement (item 224)."""
    if not checks:
        return {}
    marks = ",".join("?" * len(checks))
    urls = [r["u"] for r in conn.execute(
        "SELECT DISTINCT json_extract(f.affected_urls, '$[0]') AS u FROM findings f"
        " JOIN finding_states s ON s.fingerprint = f.fingerprint AND s.site_id = ?"
        " JOIN audit_runs a ON a.id = f.run_id AND a.site_id = ?"
        " WHERE f.source = 'model-judgement' AND COALESCE(f.recommendation, '') != ''"
        " AND s.state IN ('open', 'regressed', 'candidate')"
        f" AND f.check_id IN ({marks}) ORDER BY u", (site_id, site_id, *checks))
        if r["u"]][:OUTLINE_PAGES_CAP]
    out: dict[str, dict] = {}
    for u in urls:
        facts = page_facts(conn, site_id, u)
        if facts and (facts.get("outline") or facts.get("headings")):
            out[u] = {"outline": facts.get("outline"), "headings": facts.get("headings")}
    return out


def crawl_now_payload(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """The Crawl part's site-level "now" (item 137, brief v18 step AZ).

    Four counts and the set they decompose into, read off one stored run's
    crawl evidence, plus the UA matrix when the run captured one. The four are
    `published`, `in_sitemap`, `reached` and `render_only`; the venn is the
    three regions the brief names — reached-but-not-in-sitemap, in-sitemap-and-
    reached, and published-but-not-reached (the declared pages a crawl never
    fetched).

    **`published` is what the crawl can see, not a number the CMS knows.** No
    crawl learns how many pages a site has; the honest proxy is the union of
    the URLs the crawl reached and the URLs the sitemap declared, on this
    site's own host. So `published >= reached` and `published >= in_sitemap`
    by construction, and the shortfall of either against it is a venn region,
    not a hidden fourth set. A page counts once, by normalised path, so a
    trailing slash does not split it across two regions.

    **The UA matrix is the one part a stored run need not carry.** It is new
    crawler behaviour (task 4) whose rows only come from a live run's per-agent
    probes, so `ua_matrix` is `None` on a run that predates or skipped the matrix
    pass — the screen states that rather than drawing an empty table. When it is
    present, `_ua_matrix_display` reshapes the crawler's rows into what the table
    draws (a status per named fetched URL, and a note), recomputing the probe
    URLs the crawler stored only the statuses of.

    Returns None where there is no run or no stored crawl to read at all.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id FROM audit_runs WHERE id=?", (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None
    from urllib.parse import urlsplit
    from clauditseo.crawler.types import stored_page_is_eligible

    start = evidence.get("start_url") or ""
    host = urlsplit(start).netloc

    def _path(u: str) -> str:
        p = urlsplit(u).path or "/"
        return p if p == "/" else p.rstrip("/")

    def _on_site(u: str) -> bool:
        # A relative or same-host URL only; the sitemap can list another host,
        # which is that host's page and not a count of this site's.
        net = urlsplit(u).netloc
        return net == "" or net == host

    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    reached = {_path(p["url"]) for p in pages if stored_page_is_eligible(p)}
    in_sitemap = {_path(u) for u in (evidence.get("sitemap_entries") or [])
                  if _on_site(u)}
    published = reached | in_sitemap

    render_only = conn.execute(
        "SELECT COUNT(*) c FROM findings WHERE run_id=? AND check_id='render-only'",
        (run_id,)).fetchone()["c"]

    sitemap_files = len([s for s in (evidence.get("sitemaps") or [])])

    return {
        "run_id": row["id"],
        "published": len(published),
        # Item 229: the header's "N known" for the same run - declared plus
        # everything the crawl found, fetched or linked - so the block can say
        # how its own `published` relates to it rather than sit 40 px under a
        # second size of the site with no word between them.
        "known": site_size(evidence)["size"],
        "in_sitemap": len(in_sitemap),
        "reached": len(reached),
        "render_only": render_only,
        "sitemap_files": sitemap_files,
        "venn": {
            # reached, on this host, that the sitemap does not list.
            "reached_not_in_sitemap": len(reached - in_sitemap),
            "in_sitemap_and_reached": len(reached & in_sitemap),
            # declared in a sitemap and never fetched — the unreachable set.
            "published_not_reached": len(in_sitemap - reached),
        },
        # Reshaped to what the matrix table draws; None on a run with no matrix.
        "ua_matrix": _ua_matrix_display(evidence),
        # The parity probe (item 151); None on a run that did not probe, which
        # the screen states as not assessed rather than as parity holding.
        "mobile_parity": _mobile_parity_display(conn, run_id, evidence),
    }


# --- The Speed part's site-level "now" (brief v19 step BC) ------------------

#: How many of a template's traced pages the ledger and the waterfall are read
#: off. One — the representative page — and the reason is the brief's own: the
#: sub-part bar must SUM to the LCP it explains, and an average of four pages'
#: sub-parts sums to an average that is no page's LCP. So the strip's gauges
#: are the template's medians (a template-wide reading, which is what a gauge
#: is for) and every picture BELOW the strip is one real page traced end to
#: end, named on the page so nobody reads it as the template's average.
_SPEED_FRAME_CAP = 10
#: Resources drawn in the waterfall, by blocking cost.
_SPEED_RESOURCE_ROWS = 12
#: Hosts drawn in the third-party ledger.
_SPEED_HOST_ROWS = 10


def _bare_host(url: str) -> str:
    """A URL's host without `www.`. The first party and its own resources are
    routinely spelled both ways - the apex redirects to `www.`, or the other
    way round - and a comparison treating them as two hosts charges the site as
    a third party to itself."""
    from urllib.parse import urlsplit
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _trace_metric(trace: dict, key: str) -> float | None:
    """One gauge's figure off a trace, or None where the browser could not
    supply it. `UNAVAILABLE` is a value, not an absence (item 154), so it is
    filtered here rather than crashing the median."""
    from clauditseo.perf import UNAVAILABLE
    if key == "lcp":
        raw = (trace.get("lcp") or {}).get("ms")
    elif key == "cls":
        raw = (trace.get("cls") or {}).get("value")
    else:
        raw = trace.get(key)
    if raw is None or raw == UNAVAILABLE or isinstance(raw, (dict, list, str)):
        return None
    return float(raw)


def _resource_cost(r: dict) -> tuple[str, float | None]:
    """A resource's cost type and its BLOCKING time in milliseconds — the two
    things the waterfall draws (brief v19 step BC: "blocks-render red,
    blocks-main-thread-later amber, fine blue, so the three cost types are
    three colours").

    `blocking` is the browser's own render-blocking status where Chrome gave
    one. A script that is neither async nor defer is charged as blocking the
    main thread later rather than the render, which is the amber case.

    **A `fine` resource's blocking time is None, not its duration.** The table
    is headed "resources by blocking time", and a 1.4-second image that blocks
    nothing put the longest bar in it under that heading — measured on the
    first live Birch trace. Its duration is still carried, and the row shows a
    dash where there is no blocking cost, which is what the mockup draws for
    the deferred script.
    """
    dur = r.get("duration_ms")
    ms = float(dur) if isinstance(dur, (int, float)) else 0.0
    if r.get("blocking"):
        return "render", ms
    if r.get("type") == "script" and not r.get("async") and not r.get("defer"):
        return "main-thread", ms
    return "fine", None


def not_assessed_payload(conn: sqlite3.Connection, run_id: str | None, *,
                         checks_by_part: dict[str, list[str]]) -> dict[str, dict[str, str]]:
    """Which of each part's checks this run cannot report a pass for, and why
    (item 157).

    **The rule this exists to enforce is stated once, in `playbook.py`: a check
    may be reported as passing only if the run measured it; absence of a finding
    is not a pass.** This is that rule's reader for one stored run.

    Returns `{part_key: {"DIM/check": reason}}`. A check named here is neither a
    pass nor a fault: it is unmeasured, and the reason is the because-clause the
    screen renders. One state with a reason rather than a state per cause, which
    is the shape `playbook._dark_note` already has -- a status enum grows a
    member per cause and every call site that switches on it has to learn each
    one (channel 20260912-0940).

    Two reasons today, and the first is most of the defect:

    * **The dimension did not run.** Read off the run's own `dimensions`. On the
      operator's data, `19eeb42e` of `www.acme.com.au` recorded
      `["TEC","ONP","AIS","CNT"]`, and the Speed part rendered *"18 checks pass"*
      -- including `cwv-not-assessed`, the finding whose whole job is to say a
      measurement did not happen. Links claimed 12 with LNK absent, and Crawl
      certified its LNK half.
    * **The instrument did not run.** A dimension that ran but whose capture did
      not: the thirteen trace checks on a run holding no `pages[].perf`.

    **Rung 2 is read from the run's stored evidence, never from the current
    config**, and that is the load-bearing decision here. The anatomy of a
    finished run is a historical fact: those checks are unmeasured on
    `19eeb42e` because that run holds no traces, and that stays true forever.
    Deriving it from what is installed today would let tomorrow's `pip install
    clauditseo[render]` silently rewrite what a June run claims to have
    measured -- the same class of lie this whole item is about. The workbench,
    which has no run to read, uses the capability predicate instead
    (`playbook.resolved`); same vocabulary, two call sites, different inputs.

    A run this cannot read -- no id, or a row with no dimension list -- returns
    `{}` rather than a guess. That is a third silence and it is deliberate: this
    reader may say "unmeasured", and it may say nothing, but it may never
    manufacture a pass.
    """
    if not run_id:
        return {}
    row = conn.execute(
        "SELECT dimensions, engine_version FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    if row is None:
        return {}
    try:
        dims = set(json.loads(row["dimensions"] or "[]"))
    except (TypeError, ValueError):
        return {}
    if not dims:
        return {}

    # Rung 2's input: did this run's capture produce a trace at all? Read from
    # the evidence, per the docstring. `{"traced": False}` is the pass having
    # run and failed on that page, which is still not a measurement.
    # Parsed once for every rung below: on twenty22 the evidence is 1.8 MB and
    # each parse 13 ms, and this function read it three times.
    evidence_raw = evidence_text(conn, run_id)
    try:
        evidence = parsed_evidence(evidence_raw) if evidence_raw else {}
    except (TypeError, ValueError):
        evidence = {}
    evidence = evidence if isinstance(evidence, dict) else {}
    traced_any = False
    # Item 240: whether the browser image pass weighed anything on this run.
    imaged_any = bool(evidence) and _images_measured(
        evidence, evidence.get("pages") or []) is True
    if evidence:
        pages = evidence.get("pages") or []
        traced_any = any(isinstance(p.get("perf"), dict)
                         and p["perf"].get("traced") is not False
                         for p in pages)

    from clauditseo.checks import LABEL_ONLY_REGISTRIES, brief_only_checks
    from clauditseo.modules import prf as _prf
    from clauditseo.modules import tec as _tec
    # Every module's trace-derived checks, not only PRF's. Mobile's six are
    # TEC, and reading PRF's set alone let them read clean on an untraced run.
    from clauditseo.modules import sec as _sec_module
    trace_derived = (_prf.TRACE_DERIVED_CHECKS | _tec.TRACE_DERIVED_CHECKS
                     | _sec_module.TRACE_DERIVED_CHECKS)
    # Item 168: an untraced run created before migration 0054 was applied
    # measured `page-weight` with the HTML-bytes proxy, so it is not reported
    # unmeasured there. Read from this database's own migration record, since
    # 0054 carried no engine version bump.
    page_weight_by_proxy = False
    applied = conn.execute("SELECT applied_at FROM schema_migrations WHERE filename=?",
                           (_prf.PAGE_WEIGHT_PROXY_UNTIL,)).fetchone()
    created = conn.execute("SELECT created_at FROM audit_runs WHERE id=?",
                           (run_id,)).fetchone()
    if applied and created and created[0]:
        # applied_at is "YYYY-MM-DD HH:MM:SS" (UTC); created_at is ISO UTC.
        page_weight_by_proxy = str(created[0]).replace("T", " ")[:19] < str(applied[0])[:19]

    # Rung 3's input: which brief-only checks some brief has actually answered
    # for this site. A brief-only check is by definition one no sweep raises, so
    # the dimension having run says nothing about it -- only a brief run can
    # measure it. Read per SITE, not per audit, because that is how the part
    # page shows brief rows: from the newest brief for the part, whichever run
    # it was taken against.
    label_only = {code for code, _sev, _only in LABEL_ONLY_REGISTRIES}
    brief_only = brief_only_checks()
    answered: set[str] = set()
    site_row = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                            (run_id,)).fetchone()
    if site_row:
        from clauditseo import briefs as _briefs
        ran_tools = {r["tool_id"] for r in conn.execute(
            "SELECT DISTINCT er.tool_id FROM expert_reports er"
            " JOIN audit_runs r ON r.id = er.run_id WHERE r.site_id = ?",
            (site_row["site_id"],))}
        for b in _briefs.catalogue():
            if b.id in ran_tools:
                answered.update(b.checks)

    from clauditseo.modules.sec import HELD as _sec_held
    from clauditseo.modules.sec import NOT_YET_COLLECTED as _sec_planned
    from clauditseo.modules.sec import WELL_KNOWN_CHECKS as _sec_well_known
    from clauditseo.modules.sec import COLLECTED_SINCE as _sec_since
    from clauditseo.modules.tec import COLLECTED_SINCE as _tec_since
    _since_by_dim = {"SEC": _sec_since, "TEC": _tec_since}

    def _older(version: str | None, than: str) -> bool:
        """Whether a run's engine predates `than`. An unstamped run is older."""
        try:
            return tuple(int(x) for x in (version or "0").split(".")) < \
                tuple(int(x) for x in than.split("."))
        except ValueError:
            return True
    run_engine = row["engine_version"]
    from clauditseo.modules.sec import dns_verdicts as _sec_dns_verdicts

    # Whether this run's crawl ran the well-known path sweep (item 143 step BD):
    # read from the evidence, like `traced_any`.
    well_known_ran = bool(evidence.get("well_known"))
    # And whether it ran the parity probe (item 151). A clean probe is a block
    # with a negative statement; no block is not assessed.
    parity_ran = bool((evidence.get("mobile_parity") or {}).get("probed"))
    # And which DNS checks the lookups could not answer, from the same reader
    # the module raises from.
    _, dns_skipped = _sec_dns_verdicts(evidence.get("dns"))
    # And whether the UA matrix fingerprinted Googlebot's bodies, which is what
    # SEC/cloaking compares (item 143 step BD). A pulse crawl has no matrix.
    _matrix = evidence.get("ua_matrix")
    googlebot_bodies = any(r.get("bodies") for r in (_matrix or []) if isinstance(r, dict))
    # And whether that matrix asked as the agent list (item 145 step BG). A
    # matrix from before it visited as eight agents, most of the AI classes
    # never among them, so an edge block on those agents was not looked for.
    matrix_classed = any(isinstance(r, dict) and r.get("agent_class") for r in (_matrix or []))
    # A free check that needs a site-record field to answer (channel
    # 20260915-2045): not assessed when the field is empty and the run raised
    # no row for it. Read from the site record as it stands; the record is not
    # stored per run.
    from clauditseo.modules.ais import RECORD_FIELDS as _ais_record_fields
    raised_ais = {r["check_id"] for r in conn.execute(
        "SELECT DISTINCT check_id FROM findings WHERE run_id=? AND dimension='AIS'",
        (run_id,))}
    _record = {}
    if site_row:
        from clauditseo.persistence.repo import get_site, site_record
        _record = site_record(get_site(conn, site_row["site_id"])) or {}

    def _site_record_value(field: str):
        v = _record.get(field)
        return v not in (None, "", [], {})

    out: dict[str, dict[str, str]] = {}
    for part, checks in checks_by_part.items():
        for full in checks:
            dim, _, bare = full.partition("/")
            if not bare:                      # an unprefixed id names no dimension
                continue
            # RUNG 1 does not apply to a label-only dimension. `INT` names where
            # a finding came from and owns no sweep, so it is NEVER in any run's
            # dimension list -- and "INT did not run in this audit" was said on
            # every site forever, including one whose International brief had
            # run, and directly beneath a gate card saying "Not applicable".
            # Found on screen when International moved to the three-block
            # layout. Its checks are brief-only and rung 3 answers for them.
            if dim not in dims and dim not in label_only:
                out.setdefault(part, {})[full] = (
                    f"{dim} did not run in this audit")
            # Security's staged build (item 143 step BD). A held check needs an
            # input or an authorisation this build never acts on, and a planned
            # one has no collector yet; either way SEC ran and measured nothing
            # of it, which rungs 2 and 3 cannot see.
            elif dim == "SEC" and bare in _sec_held:
                out.setdefault(part, {})[full] = f"held: {_sec_held[bare]}"
            elif dim == "SEC" and bare in _sec_planned:
                out.setdefault(part, {})[full] = (
                    f"not collected yet: {_sec_planned[bare]}")
            elif dim == "SEC" and bare in dns_skipped:
                out.setdefault(part, {})[full] = f"not assessed: {dns_skipped[bare]}"
            elif dim == "SEC" and bare == "cloaking" and not googlebot_bodies:
                out.setdefault(part, {})[full] = (
                    "this run did not fetch pages as Googlebot, which is what "
                    "cloaking is compared from")
            elif (dim == "AIS" and bare in _ais_record_fields and bare not in raised_ais
                  and not any(_site_record_value(f) for f in _ais_record_fields[bare])):
                out.setdefault(part, {})[full] = (
                    " and ".join(_ais_record_fields[bare]) + " on the site record "
                    + ("is" if len(_ais_record_fields[bare]) == 1 else "are")
                    + " empty; set it on Admin › Sites")
            elif dim == "AIS" and bare == "edge-blocks-ai-ua" and not matrix_classed:
                out.setdefault(part, {})[full] = (
                    "this run did not fetch pages as the AI crawlers, which is what a "
                    "firewall block is read from" if not _matrix else
                    "this run's crawler access test predates the crawler list, so most AI "
                    "crawlers were never asked as")
            elif dim == "TEC" and bare in _tec.PARITY_CHECKS and not parity_ran:
                out.setdefault(part, {})[full] = (
                    "this run did not fetch pages as a phone and as "
                    "Googlebot-smartphone, which is what parity is compared from")
            elif dim == "SEC" and bare in _sec_well_known and not well_known_ran:
                out.setdefault(part, {})[full] = (
                    "this run did not fetch the well-known paths, which is what "
                    "these are read from")
            elif (bare in trace_derived and not traced_any
                  and not (dim == "PRF" and bare == "page-weight" and page_weight_by_proxy)):
                out.setdefault(part, {})[full] = (
                    "this run took no performance trace, which is what these "
                    "are measured from")
            # Item 240: the image pass, the same register `measured` asks.
            elif image_derived(dim, bare) and not imaged_any:
                out.setdefault(part, {})[full] = (
                    "this run weighed no images, which is what these are "
                    "measured from")
            # After the trace rung: a run that took no trace owes that reason
            # first; a traced run from an older engine owes this one.
            elif bare in _since_by_dim.get(dim, {}) and _older(run_engine, _since_by_dim[dim][bare]):
                out.setdefault(part, {})[full] = (
                    f"not assessed: this run's engine ({run_engine or 'unstamped'}) predates "
                    f"this check, first collected in {_since_by_dim[dim][bare]}; a re-check measures it")
            # RUNG 3: a check only a brief can raise, whose brief has not run.
            # The fourth instance of item 157's class, and the one its first two
            # rungs could not see: Mobile's three analysis checks read "3 checks
            # clean" on a site where no Mobile brief had ever run, because TEC
            # ran (rung 1 silent) and none of them is trace-derived (rung 2
            # silent). A brief-only check with no brief behind it was measured by
            # nothing, so absence of a finding there is not a pass.
            elif full in brief_only and full not in answered:
                out.setdefault(part, {})[full] = (
                    "no analysis has run for this part yet, and only an analysis "
                    "can judge these")
    return out


def speed_now_payload(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """The Speed part's site-level "now" (brief v19 step BC): the per-template
    vitals strip and the five pictures beneath it.

    Everything is read back off the per-page performance traces the browser
    pass stored on the crawl evidence (`perf` on each page record) — nothing
    here measures, and nothing here judges. Pages are grouped by BB's URL
    pattern table, which is what makes the rows per template rather than per
    page, and every count carries its population (item 155): a template's page
    count is a count over the CRAWL, because a template's pages are the ones
    this run fetched and traced.

    Returns None where there is no run or no stored crawl, and
    `{"recorded": False}` where the run stored no trace at all — which is the
    common case until the Speed part's own depth pills turn the pass on, and is
    a different sentence from "traced and found nothing".
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id, site_id FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None

    from urllib.parse import urlsplit
    from clauditseo import urlshape
    from clauditseo.modules import prf
    from clauditseo.perf import DEVICE_PROFILE, UNAVAILABLE

    from clauditseo.crawler.types import stored_page_is_eligible

    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    # The pages the pass COULD have traced: the readable HTML the crawl
    # reached. Deliberately NOT filtered by the start URL's host - the first
    # live Birch trace started at the apex and every page came back on `www.`,
    # so a host filter made the denominator 0 and the strip read `12 of 0`.
    # The crawl is same-site by construction; that is the crawler's rule and
    # not this function's to re-apply.
    readable = [p for p in pages if stored_page_is_eligible(p)]
    traced = [p for p in pages if (p.get("perf") or {}).get("traced") is not False
              and (p.get("perf") or {}).get("device_profile")]
    base = {
        "recorded": bool(traced),
        # Stated on every run, per the brief - and it states the throttling
        # METHOD too, because our applied throttle reads lower than a client's
        # own PageSpeed run and the report must not look like a disagreement.
        "device_profile": (traced[0]["perf"]["device_profile"] if traced
                           else DEVICE_PROFILE),
        "traced": count(len(traced), "crawl", of=len(readable)),
        # WHICH pages were traced, stated beside the device profile and for
        # the same reason (operator ruling 2026-09-11): the brief's "per page"
        # predates the CPU 4x / Slow-4G session, a T3 at five hundred
        # throttled traces is a different audit, and a reader cannot check a
        # figure whose sample they cannot see. Written by `perf.sample` at run
        # time; derived below for a run stored before it existed, because
        # "this run did not record its sample" is a better answer than
        # silence and a worse one than the sample.
        "sample": (evidence.get("perf_sample")
                   or _derived_sample(traced, readable)),
        # The gauges' thresholds, from the engine's registry - Google's, never
        # ours (brief v19 step BC).
        "bands": {k: {"label": v["label"], "name": v["name"], "good": v["good"],
                      "poor": v["poor"], "unit": v["unit"], "proxy": v["proxy"]}
                  for k, v in prf.GAUGE_BANDS.items()},
        # Visual (2): the field distribution. Empty today - no CrUX key and no
        # GSC connection - and it renders greyed with what to connect rather
        # than as a zero, because a zero here would read as "no real user had a
        # good experience".
        "field_data": _speed_field_data(conn, row["site_id"]),
        "templates": [],
        # Every readable page's template, by `derive_pattern` - the same rule
        # the templates below are grouped by - so a template narrow on the
        # part page reads the server's membership rather than a second
        # implementation of the rule in the browser (brief v25 step BP).
        "pattern_of": {p["url"]: urlshape.derive_pattern(urlsplit(p["url"]).path or "/") or "/"
                       for p in readable},
    }
    if not traced:
        return base

    # The first party, read off a page the crawl actually reached rather than
    # off the start URL, and compared without `www.`: the start URL was the
    # apex and every page came back on `www.`, so the ledger charged the site's
    # own host as a third party. Measured on the first live Birch trace.
    first_party = _bare_host(traced[0]["url"])
    groups: dict[str, list[dict]] = {}
    for p in traced:
        # `derive_pattern` takes a PATH - its own signature says so. Handed a
        # whole URL it produced `/https:/www.beacon.com.au/<slug>`, a
        # template nothing on the site matches. Same live trace found it.
        pattern = urlshape.derive_pattern(urlsplit(p["url"]).path or "/") or "/"
        groups.setdefault(pattern, []).append(p)

    for pattern, members in groups.items():
        strip = []
        for key, spec in prf.GAUGE_BANDS.items():
            vals = [v for v in (_trace_metric(m["perf"], spec["trace"])
                                for m in members) if v is not None]
            med = _median(vals)
            strip.append({
                "key": key, "label": spec["label"],
                "value": None if med is None else round(med, 4 if key == "cls" else 1),
                "unit": spec["unit"],
                "band": None if med is None else prf.gauge_band(key, med),
                # Lab, on every one of them, until a field source is connected.
                # The brief's accept says so in as many words: "every vital
                # labelled lab".
                "basis": "lab",
                "proxy": spec["proxy"],
                # The population the median was taken over, stated as data
                # (item 155): these pages, of the pages traced.
                "over": count(len(vals), "crawl", of=len(members)),
            })
        # The representative page: the one whose LCP is nearest the template's
        # median. Every picture below the strip is THIS page - see
        # `_SPEED_FRAME_CAP`'s note on why an average would not sum.
        lcps = [(m, _trace_metric(m["perf"], "lcp")) for m in members]
        have = [(m, v) for m, v in lcps if v is not None]
        med_lcp = _median([v for _m, v in have])
        rep = (min(have, key=lambda mv: abs(mv[1] - med_lcp))[0]
               if have and med_lcp is not None else members[0])
        tr = rep["perf"]

        lcp = dict(tr.get("lcp") or {})
        sub = lcp.get("sub_parts")
        if isinstance(sub, dict):
            # Which sub-part to highlight: the largest. The fix card's estimate
            # is read off this bar, so the dominant part is the payload's call
            # and not the renderer's - two components picking a maximum is two
            # chances to pick differently.
            lcp["dominant"] = max(sub, key=lambda k: sub.get(k) or 0)
            lcp["sub_total"] = round(sum(v for v in sub.values()
                                         if isinstance(v, (int, float))), 1)
        else:
            lcp["dominant"] = None
            lcp["sub_total"] = None

        frames = tr.get("frames")
        strip_frames = ([{"name": f["name"], "t_ms": f["t_ms"],
                          "label": f.get("label") or "loading"}
                         for f in frames[:_SPEED_FRAME_CAP]]
                        if isinstance(frames, list) else UNAVAILABLE)

        resources = []
        for r in (tr.get("resources") or []):
            kind, ms = _resource_cost(r)
            dur = r.get("duration_ms")
            resources.append({
                "url": r.get("url"), "type": r.get("type"),
                "bytes": r.get("bytes"), "transfer": r.get("transfer"),
                "cost": kind,
                # The blocking cost, which is what the table is headed by, and
                # None where there is none.
                "ms": None if ms is None else round(ms, 1),
                # And how long it took, which is a different question kept
                # beside it rather than substituted for it.
                "duration_ms": round(float(dur), 1) if isinstance(dur, (int, float)) else None,
                "async": r.get("async"), "defer": r.get("defer"),
                "is_lcp": bool(lcp.get("url")) and r.get("url") == lcp.get("url"),
            })
        # By blocking cost, render-blocking first: the order the brief asks for
        # ("resources by blocking ms"), and the order a reader fixes in. Within
        # `fine`, which has no blocking cost at all, by how long it took - so
        # the order is stable and still says something.
        rank = {"render": 0, "main-thread": 1, "fine": 2}
        resources.sort(key=lambda r: (rank[r["cost"]],
                                      -(r["ms"] if r["ms"] is not None
                                        else r["duration_ms"] or 0)))

        members_all = [m["perf"] for m in members]
        ledger: dict[str, dict] = {}
        for one in members_all:
            for entry in prf.third_party_ledger(one, first_party):
                got = ledger.setdefault(
                    entry["host"], {"host": entry["host"], "bytes": 0,
                                    "main_thread_ms": 0.0, "pages": 0})
                got["bytes"] += entry["bytes"]
                got["main_thread_ms"] += entry["main_thread_ms"]
                got["pages"] += 1
        third = sorted(ledger.values(),
                       key=lambda r: -(r["bytes"] + r["main_thread_ms"] * 1000))
        for entry in third:
            entry["main_thread_ms"] = round(entry["main_thread_ms"], 1)

        base["templates"].append({
            "pattern": pattern,
            "depth": urlshape.analyse_url(rep["url"]).get("depth"),
            # A count over the crawl: the pages of this template THIS RUN
            # traced, of the pages it traced (item 155).
            #
            # The basis is overridden because the denominator is the TRACED
            # subset, not the crawl: with `POPULATION_BASIS["crawl"]` this
            # rendered `1 of 12 pages crawled` on a run that crawled 48.
            # Sampling is what exposed it — every page used to be traced, so
            # the two sets were one and the word was true by accident.
            "pages": count(len(members), "crawl", of=len(traced),
                           basis="traced"),
            "vitals": strip,
            # Named, so nobody reads the pictures below the strip as the
            # template's average.
            "page": rep["url"],
            "lcp": lcp,
            "frames": strip_frames,
            "resources": resources[:_SPEED_RESOURCE_ROWS],
            "resources_total": len(resources),
            "third_parties": third[:_SPEED_HOST_ROWS],
            "fonts": tr.get("fonts") or [],
            "head_rendered": tr.get("head_rendered"),
            "head_fetched": tr.get("head_fetched"),
        })
    # Largest template first: the one most of the site is built from is the one
    # worth reading, and it is what the part opens on.
    base["templates"].sort(key=lambda t: -t["pages"]["value"])
    return base


def _derived_sample(traced: list[dict], readable: list[dict]) -> str:
    """What the sample looks to have been, for a run that did not record it.

    Structural rather than guessed at a count: if every template among the
    traced pages contributed exactly one, that IS one per template, whatever
    the pass intended. Said as an observation ("looks like") rather than as
    the rule, because a run stored before `perf.sample` existed cannot tell us
    what it meant to do.
    """
    from urllib.parse import urlsplit
    from clauditseo import urlshape

    if not traced:
        return "no page on this run carries a trace"
    if len(traced) == len(readable):
        return f"every readable page ({len(traced)})"
    groups: dict[str, int] = {}
    for p in traced:
        pattern = urlshape.derive_pattern(urlsplit(p["url"]).path or "/") or "/"
        groups[pattern] = groups.get(pattern, 0) + 1
    shape = ("one page per template" if set(groups.values()) == {1}
             else "a sample")
    return (f"not recorded on this run; looks like {shape} "
            f"({len(traced)} of {len(readable)} readable)")


def _speed_field_data(conn: sqlite3.Connection, site_id: str) -> dict:
    """The field distribution, and what to connect where it is empty (brief v19
    step BC visual 2).

    `field_data_source` is the site record's column and is empty today — no
    CrUX key, no GSC connection — so this returns `connected: False` with the
    sentence the greyed bar carries. Deliberately not zeros: `good 0 · NI 0 ·
    poor 0` would read as "no real user had a good experience", which is a
    claim about the site rather than about our data.
    """
    source = None
    try:
        row = conn.execute("SELECT field_data_source FROM sites WHERE id=?",
                           (site_id,)).fetchone()
        source = (row["field_data_source"] or "").strip() if row else None
    except sqlite3.Error:
        source = None
    if not source:
        return {"connected": False, "source": None,
                "good": None, "needs_improvement": None, "poor": None,
                "note": "not connected — connect CrUX or Search Console on "
                        "Admin › Sites to show the share of real visits that "
                        "were good, needs improvement or poor. Until then "
                        "every figure above is lab."}
    # No provider serves this yet; the column existing is the hook, and the
    # block says so rather than inventing a distribution for a configured key
    # nothing reads.
    return {"connected": False, "source": source,
            "good": None, "needs_improvement": None, "poor": None,
            "note": f"{source} is named on the site record and no provider "
                    "here reads it yet, so every figure above is still lab."}


def urls_now_payload(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """The URLs & parameters part's site-level "now" (item 141, brief v19 step
    BB): the four-count strip, the convention, and the two tables the part
    draws — the pattern table (template · count · depth) and the parameter
    inventory (key · seen · class · canonical present).

    Everything is derived by `urlshape` from what the crawl already stored: the
    reached URLs give the pattern table and the convention, and the parameter
    inventory reads the unstripped `href` on every link (the reached set has
    the tracking keys stripped, so it would never show them — see the
    `urlshape` module). A parameter's class comes from the site record's
    `parameter_rules`; canonical presence from whether the variant was reached
    and declares a canonical, the same signal Indexability's map holds.

    Returns None where there is no run or no stored crawl.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id, site_id FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None
    from urllib.parse import urlsplit
    from clauditseo import urlshape
    from clauditseo.crawler.crawl import normalise_url
    from clauditseo.crawler.types import stored_page_is_eligible

    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    oks = [p for p in pages if stored_page_is_eligible(p)]
    reached_urls = [p["url"] for p in oks]

    # Parameter rules and thresholds from the site record (text JSON columns).
    param_rules, thresholds = _url_site_fields(conn, row["site_id"])

    # canonical present on a variant: reached and declaring a canonical.
    has_canon: dict[str, bool] = {}
    for p in pages:
        has_canon[normalise_url(p["url"])] = bool(p.get("canonical"))

    def canonical_present(variant: str) -> bool:
        return has_canon.get(normalise_url(variant), False)

    hrefs = list(reached_urls)
    for p in pages:
        for link in (p.get("links") or []):
            href = link.get("href") or link.get("url")
            if href:
                hrefs.append(href)

    patterns = urlshape.pattern_table(reached_urls)
    max_depth = thresholds["max_depth"]
    for row_p in patterns:
        row_p["note"] = (f"depth {row_p['depth']}, over {max_depth}"
                         if row_p["depth"] > max_depth else "")

    inventory = urlshape.parameter_inventory(hrefs, canonical_present)
    unclassified = 0
    for param in inventory:
        cls = urlshape.classify(param["key"], param_rules)
        param["class"] = cls or "unclassified"
        if cls is None and param["canonical_present"] == 0:
            unclassified += 1

    # Convention over the reached 200s.
    scheme = _most_common(urlsplit(u).scheme for u in reached_urls) or "https"
    host = _most_common(urlsplit(u).netloc for u in reached_urls) or urlsplit(
        evidence.get("start_url") or "").netloc
    slash = _most_common((urlsplit(u).path or "/").endswith("/") for u in reached_urls)
    lower = not any(c.isupper() for u in reached_urls for c in (urlsplit(u).path or ""))
    conform = sum(1 for u in reached_urls
                  if (urlsplit(u).path or "/").endswith("/") == bool(slash)
                  and not any(c.isupper() for c in (urlsplit(u).path or "")))

    return {
        "run_id": row["id"],
        "urls": len(reached_urls),
        "patterns": patterns,
        # Each reached URL's template (brief v25 step BP), from the same
        # `derive_pattern` the table above is counted with.
        "pattern_of": {u: urlshape.derive_pattern(urlsplit(u).path or "/") for u in reached_urls},
        "pattern_count": len(patterns),
        "parameters": inventory,
        "parameters_seen": len(inventory),
        "unclassified": unclassified,
        "convention": {"scheme": scheme, "host": host,
                       "trailing_slash": bool(slash),
                       "case": "lowercase" if lower else "mixed",
                       "conform": conform, "total": len(reached_urls)},
        "thresholds": thresholds,
    }


def _url_site_fields(conn: sqlite3.Connection, site_id):
    """The site record's parameter_rules and the four URL thresholds, for the
    URLs "now" payload — read straight off the sites row so the payload does
    not depend on the repo layer. Blank thresholds fall back to `urlshape`'s
    defaults."""
    from clauditseo import urlshape
    rules = None
    thresholds = {
        "url_max_chars": urlshape.DEFAULT_URL_MAX_CHARS,
        "slug_max_words": urlshape.DEFAULT_SLUG_MAX_WORDS,
        "max_depth": urlshape.DEFAULT_MAX_DEPTH,
        "rename_inlink_cap": urlshape.DEFAULT_RENAME_INLINK_CAP,
    }
    if site_id is None:
        return rules, thresholds
    try:
        srow = conn.execute(
            "SELECT parameter_rules, url_max_chars, slug_max_words, max_depth, "
            "rename_inlink_cap FROM sites WHERE id=?", (site_id,)).fetchone()
    except sqlite3.OperationalError:
        return rules, thresholds
    if srow is None:
        return rules, thresholds
    raw = srow["parameter_rules"]
    if isinstance(raw, str) and raw:
        try:
            rules = json.loads(raw)
        except ValueError:
            rules = None
    for key in thresholds:
        val = srow[key]
        try:
            if val not in (None, ""):
                thresholds[key] = int(str(val).strip())
        except (TypeError, ValueError):
            pass
    return rules, thresholds


# --- The three headline numbers, each with its denominator (brief v23 step BJ) ---
#
# Site size, coverage and assessed replace the old header's three unrelated
# figures (record / published / crawl), which every count elsewhere silently
# picked one of. The rule (item 155) is that a count states its population;
# these are the site-scoped denominators it states against.

def _host_path(u: str, host: str) -> str | None:
    """A URL's on-host path key (trailing slash normalised), or None when the
    URL is off this host — so the union counts this site's pages, not another's.

    **`www.` is not a different site**, and this compared hosts as written until
    BJ's numbers were rendered. The site record held the apex, so the crawl
    started at `https://beacon.com.au/` and every page came back on
    `www.beacon.com.au`: every path keyed to None, `site_size` returned
    `declared 0 · discovered 0 · size 0` with `unknown` FALSE, and the header
    drew a confident `0 on the site` for a site of twelve pages that had just
    been crawled in full. Coverage degraded to "not computable" rather than
    dividing by zero, which is the one mercy in it — the number was wrong, not
    absurd, which is exactly how it would have survived.

    A subdomain that is not `www.` stays off-host on purpose: `blog.example.com`
    is a different property to crawl and count, and collapsing it would put
    another site's pages in this site's denominator — the opposite defect.
    """
    from urllib.parse import urlsplit
    parts = urlsplit(u or "")
    bare = lambda h: (h or "").lower().removeprefix("www.")  # noqa: E731
    if parts.netloc and bare(parts.netloc) != bare(host):
        return None
    p = parts.path or "/"
    return p if p == "/" else p.rstrip("/")


def site_size(evidence: dict, *, retrieval_ok: bool = True) -> dict:
    """Site size = declared ∪ discovered, per run (brief v23 step BJ).

    Declared is the sitemap's URLs on this host; discovered is the crawled pages
    and their on-host link targets. **Never `crawled ÷ declared`** — dividing by
    the declaration makes coverage rise when the declaration fails.

    `unknown` is the fourth state the size carries: when the declaration's
    source failed, the size is not a number and coverage is not computable. It
    is set here from `retrieval_ok=False` (a `suspected-retrieval-issue`, whose
    PRODUCTION is the separately-filed crawl-layer re-fetch) or from a visibly
    unread sitemap. A short-body sitemap that read 200 is indistinguishable in
    the stored bytes and is the re-fetch item's job, not this function's.
    """
    from urllib.parse import urlsplit
    host = urlsplit(evidence.get("start_url") or "").netloc
    declared, discovered = set(), set()
    for u in (evidence.get("sitemap_entries") or []):
        k = _host_path(u, host)
        if k is not None:
            declared.add(k)
    for p in (evidence.get("pages") or []):
        if not p.get("url"):
            continue
        k = _host_path(p["url"], host)
        if k is not None:
            discovered.add(k)
        for t in (p.get("outlinks") or []):
            tk = _host_path(t, host)
            if tk is not None:
                discovered.add(tk)
    unknown = (not retrieval_ok) or bool(_sitemaps_unread(evidence))
    union = declared | discovered
    return {
        "size": None if unknown else len(union),
        "declared": len(declared),
        "discovered": len(discovered),
        # discovered-but-not-declared: the site that exists minus the site the
        # owner declares. Promoted from a header parenthetical to its own number.
        "gap": len(discovered - declared),
        "unknown": unknown,
        "unknown_reason": "source failed" if unknown else None,
    }


def run_coverage(evidence: dict, *, retrieval_ok: bool = True) -> dict:
    """Coverage = crawled ÷ site size, per run (brief v23 step BJ). `pct` is
    None (not zero, not 100) when the size is unknown, and is capped at 100
    since the reached set is a subset of the size by construction."""
    from clauditseo.crawler.types import stored_page_is_eligible
    from urllib.parse import urlsplit
    host = urlsplit(evidence.get("start_url") or "").netloc
    ss = site_size(evidence, retrieval_ok=retrieval_ok)
    reached = {k for p in (evidence.get("pages") or [])
               if p.get("url") and stored_page_is_eligible(p)
               for k in [_host_path(p["url"], host)] if k is not None}
    crawled = len(reached)
    if ss["unknown"] or not ss["size"]:
        return {"crawled": crawled, "size": ss["size"], "pct": None,
                "unknown": ss["unknown"], "unknown_reason": ss["unknown_reason"]}
    return {"crawled": crawled, "size": ss["size"],
            "pct": min(100, round(crawled / ss["size"] * 100)), "unknown": False,
            "unknown_reason": None}


def run_assessed(conn: sqlite3.Connection, run_id: str, site_id: str) -> dict:
    """Assessed = findings in the run not in state `open` ÷ findings in the run
    (brief v23 step BJ). Unweighted — a Low looked at counts as much as a
    Critical, because this measures how much of the audit has been *been
    through*, not progress toward fixed. Only `open` is unassessed; `fixed`,
    `regressed`, `candidate`, `accepted-risk` and `withdrawn` all count.

    Coverage notes are not findings and are not counted, by the same rule
    `standing_by_state` below applies to the standing position (brief v5 step
    S, channel ruling 20260918-0400). They were counted here until 2026-09-18,
    and the landing read "It found 36 findings in this audit" and "36 not yet
    assessed" beside its own lane reading 32 open - twenty22 run 991401ab,
    whose 36 rows held four `*-not-assessed` and `*-coverage` notes. A note
    cannot be assessed either, so while it sat in the denominator the
    percentage could not reach 100 for the life of the run.

    `notes` is what was set aside, so a screen stating the count can state
    what it left out rather than leaving a reader to find the difference."""
    rows = conn.execute(
        "SELECT f.fingerprint, %s AS note FROM findings f WHERE f.run_id=?"
        % coverage_note_sql(), (run_id,)).fetchall()
    notes = sum(1 for r in rows if r["note"])
    fps = [r["fingerprint"] for r in rows if not r["note"]]
    total = len(fps)
    if not total:
        return {"assessed": 0, "total": 0, "pct": None, "notes": notes}
    distinct = list({fp for fp in fps if fp})
    states: dict[str, str] = {}
    for chunk in (distinct[i:i + 400] for i in range(0, len(distinct), 400)):
        q = ("SELECT fingerprint, state FROM finding_states WHERE site_id=? "
             "AND fingerprint IN (%s)" % ",".join("?" * len(chunk)))
        for r in conn.execute(q, (site_id, *chunk)).fetchall():
            states[r["fingerprint"]] = r["state"]
    open_n = sum(1 for fp in fps if states.get(fp, "open") == "open")
    assessed = total - open_n
    return {"assessed": assessed, "total": total, "notes": notes,
            "pct": round(assessed / total * 100)}


#: The severities a client report may not go out with unassessed (brief v23
#: step BL). A threshold, not a gradient: the assessed percentage is for the
#: client; this is the operator's one condition under which sending is
#: defensible. Not 100%, which will never hold.
INTEGRITY_SEVERITIES = ("critical", "high")


def ledger_findings(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    """The site's open findings in the running ledger, each the latest row
    of its fingerprint in the shape `get_run` gives a run's, with `state` and
    `measured_at` - the date of the run that last measured it (item 239 step
    7: what a client report built from the Latest View lists)."""
    rows = conn.execute(
        "SELECT f.*, fs.state AS state,"
        " COALESCE(r.finished_at, r.started_at) AS measured_at"
        " FROM finding_states fs"
        f" JOIN findings f ON f.rowid = ({_latest_finding()})"
        " JOIN audit_runs r ON r.id = f.run_id"
        " WHERE fs.site_id=? AND fs.state IN ('open','regressed')"
        " ORDER BY CASE lower(f.severity) WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
        " WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, f.check_id",
        (site_id,)).fetchall()
    return [_finding_dict(r) for r in rows]


def analyst_insights(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    """The analyst layer's findings from the newest audit that ran it (item
    239 step 7). The layer runs inside an audit and keeps no ledger state -
    its findings are the run's own - so a report built from the Latest View
    takes them as it takes every analysis: the newest run of it, dated."""
    row = conn.execute(
        "SELECT f.run_id, COALESCE(r.finished_at, r.started_at) at FROM findings f"
        " JOIN audit_runs r ON r.id = f.run_id"
        " WHERE r.site_id=? AND f.source='model-judgement' AND f.dimension NOT LIKE 'EXP:%'"
        " AND json_extract(f.evidence, '$.from_brief') IS NULL"
        " ORDER BY r.started_at DESC, r.rowid DESC LIMIT 1", (site_id,)).fetchone()
    if row is None:
        return []
    return [{**_finding_dict(r), "measured_at": row["at"]} for r in conn.execute(
        "SELECT * FROM findings WHERE run_id=? AND source='model-judgement'"
        " AND dimension NOT LIKE 'EXP:%' AND json_extract(evidence, '$.from_brief') IS NULL",
        (row["run_id"],))]


def open_severe(conn: sqlite3.Connection, site_id: str) -> dict:
    """The site's open Critical and High findings in the running ledger - the
    Latest View's (item 239 step 7, the operator's ruling: "the report hold is
    the open Critical and High in that copy").

    It replaced `unassessed_severe`, which counted ONE run's rows still
    `open`: a finding a newer run cleared, or one only an older run raised,
    moved the hold with whichever audit was picked. Open or regressed, as the
    glossary counts open; coverage notes are not findings; a candidate is not
    yet a finding the record stands behind."""
    marks = ",".join("?" * len(INTEGRITY_SEVERITIES))
    by: dict[str, int] = {s: 0 for s in INTEGRITY_SEVERITIES}
    for r in conn.execute(
            "SELECT lower(f.severity) sev, COUNT(*) n FROM finding_states fs"
            f" JOIN findings f ON f.rowid = ({_latest_finding()})"
            " WHERE fs.site_id=? AND fs.state IN ('open','regressed')"
            f" AND NOT {coverage_note_sql()} AND lower(f.severity) IN ({marks})"
            " GROUP BY lower(f.severity)", (site_id, *INTEGRITY_SEVERITIES)):
        by[r["sev"]] = r["n"]
    return {"count": sum(by.values()), **by}

def run_fingerprints(conn: sqlite3.Connection, run_id: str) -> list[str]:
    """The distinct fingerprints a run raised (item 207).

    What the record narrows to when it is opened from a figure that counted
    ONE audit: the landing's "Critical or High unassessed" is this run's rows
    (`unassessed_severe` above), and the record is every audit's. One per
    fingerprint because the record is one row per fingerprint. Measured on
    stored twenty22, the record narrowed to these, to `open` and to Critical
    and High equals `unassessed_severe` on all four runs."""
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT fingerprint FROM findings WHERE run_id=? "
        "AND fingerprint IS NOT NULL AND fingerprint != '' ORDER BY fingerprint",
        (run_id,)).fetchall()]


def client_report_hold(conn: sqlite3.Connection, site_id: str) -> str | None:
    """Why a client report cannot go out for this run, or None (brief v23 step
    BL's threshold; item 178).

    One sentence with one owner, because two places act on it: `generate()`
    refuses the document, and the plan route refuses to write the plan a client
    report would carry before it makes the model call - so a held report never
    pays for its plan and is then refused (UI audit 08-2).

    Item 239 step 7: over the site's running record, which is what a client
    report is a copy of - not over one run."""
    severe = open_severe(conn, site_id)
    if not severe["count"]:
        return None
    return (f"The site has {severe['count']} Critical or High "
            f"finding{'s' if severe['count'] != 1 else ''} still open "
            f"({severe['critical']} Critical, {severe['high']} High). A client "
            "report cannot go out ahead of the work: mark each accepted risk "
            "or withdrawn, or fix it and re-check, then generate it.")


def standing_by_state(conn: sqlite3.Connection, site_id: str) -> dict:
    """The site's finding states counted by state, coverage notes excluded -
    the one count of the standing position (item 180, channel ruling
    20260918-0400).

    Coverage notes are not findings and are not counted (brief v5 step S): the
    record, the parts and the standing count one population. Home counted
    `finding_states` raw and read "1741 open, 3 seen once" beside a landing
    reading 1740 and 2; the difference was coverage notes. Both read this now.
    `notes` is the count set aside, so a screen can say what it left out."""
    rows = conn.execute(
        "SELECT fs.state, COUNT(*) n, MIN(fs.updated_at) oldest"
        f" FROM finding_states fs JOIN findings f ON f.rowid = ({_latest_finding()})"
        f" WHERE fs.site_id=? AND NOT {coverage_note_sql()} GROUP BY fs.state",
        (site_id,)).fetchall()
    out = {r["state"]: {"n": r["n"], "oldest": r["oldest"]} for r in rows}
    notes = conn.execute(
        "SELECT COUNT(*) FROM finding_states fs"
        f" JOIN findings f ON f.rowid = ({_latest_finding()})"
        f" WHERE fs.site_id=? AND fs.state IN ('open','regressed') AND {coverage_note_sql()}",
        (site_id,)).fetchone()[0]
    out["_notes"] = {"n": notes, "oldest": None}
    return out


def headline_numbers(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """The three numbers the client header states, each with its denominator
    (brief v23 step BJ): what was audited (crawled), how much of the site that
    was (coverage over site size), and how much has been through
    (assessed). The record count stays elsewhere as bookkeeping — it is not a
    headline denominator. Returns None only where there is no run.

    **A run with no stored crawl evidence still knows what it fetched.**
    `crawled_paths` is on the run row and `crawl_evidence` is a separate write
    that three real runs are missing — `93bdd2b2`, `8fdeb042` and `d9c14277`,
    named in `cli.py`'s own note about the branch that stored it at neither
    exit. Returning None for those drew NO figures at all, which is worse than
    the honest answer: what the run fetched is known, the size of the site is
    not, and the two are different claims. So the fallback states the crawl
    from the row and marks the size `unknown` with the reason — the same fourth
    state a failed sitemap produces, reached by a different road.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id, site_id, crawled_paths FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None:
        return None
    ev = None
    if evidence_raw:
        try:
            ev = parsed_evidence(evidence_raw)
        except (TypeError, ValueError):
            ev = None
    if not ev:
        try:
            fetched = len(json.loads(row["crawled_paths"] or "[]"))
        except (TypeError, ValueError):
            fetched = 0
        return {
            "run_id": row["id"],
            "site_size": {"size": None, "declared": 0, "discovered": fetched,
                          "gap": 0, "unknown": True,
                          "unknown_reason": "this run stored no crawl evidence"},
            "coverage": {"crawled": fetched, "size": None, "pct": None,
                         "unknown": True,
                         "unknown_reason": "this run stored no crawl evidence"},
            "assessed": run_assessed(conn, run_id, row["site_id"]),
            "integrity": open_severe(conn, row["site_id"]),
            "audited": fetched,
        }
    ss = site_size(ev)
    cov = run_coverage(ev)
    return {
        "run_id": row["id"],
        "site_size": ss,
        "coverage": cov,
        "assessed": run_assessed(conn, run_id, row["site_id"]),
        # Brief v23 step BL's integrity line: the threshold `generate()`
        # refuses a client report on, stated where the operator reads the run
        # rather than first met as a 422.
        "integrity": open_severe(conn, row["site_id"]),
        "audited": cov["crawled"],
    }


# --- Every count carries its population (item 155) --------------------------
#
# The defect this fixes is the denominator, not a missing label. The check
# table's `35 of 68` was already a ratio; 23 of those 68 were never fetched,
# and a page nobody looked at cannot be evidence that the fault is absent.
# Labelling the 68 does not repair the inference a reader draws from a fault
# rate computed over pages that were never assessed.
#
# So a count is data rather than a number with prose around it, and the
# population is the field that decides how it renders: one matching the page's
# scope renders plain, one that differs renders `N of M` with its basis named.
# On a full-coverage T3 run the labels correctly disappear because there is
# nothing to disambiguate; on a T1 pulse every count reads `3 of 3 crawled`
# under a header reading `3 of 53 on the site`.
POPULATIONS = ("crawl", "site", "record")

#: How each population is named on screen. The wording is the server's because
#: two components naming the same population differently is the whole class of
#: defect this item closes.
POPULATION_BASIS = {
    # What this run fetched. The default for anything reporting what was
    # found, and the ONLY legal denominator for fault prevalence.
    "crawl": "crawled",
    # The site as one subject rather than a page set — `siteScope` parts
    # (security, content) and BC's `cwv-not-assessed`. A site-scoped count has
    # a population like any other, it simply is not a page set, which is why
    # this population carries no size: it is never dressed as a page ratio.
    "site": "across the site",
    # Everything stored for the site. Legal on the page and the right
    # population for what-we-know and what-changed statements — how much of
    # what we know this run covered, what has gone since last crawl, a trend —
    # and never a prevalence denominator.
    "record": "in the record",
}


def count(value: int, population: str, *, of: int | None = None,
          basis: str | None = None) -> dict:
    """A count as data: `{value, population, basis, of}`.

    `of` is the denominator the value is a subset of, and is None wherever it
    is not one of a page set — a findings count, or a site-scoped count. The
    renderer then states the value plain rather than inventing a ratio, which
    is the difference between `35 of 45 crawled` and `12 findings of 68 pages`.

    `basis` names the denominator IN WORDS and defaults to the population's own
    (`POPULATION_BASIS`). Override it only where `of` is a **subset** of the
    population rather than its whole extent, because then the population's word
    describes the wrong set.

    The case that forced this, and the reader should know it is narrow: a Speed
    template's page count is the pages of that template THIS RUN TRACED, over
    the pages it traced. Those are crawled pages, so the population is `crawl`
    and must stay `crawl` — but the denominator is the traced subset, and
    `POPULATION_BASIS["crawl"]` is "crawled", so the strip rendered
    `1 of 12 pages crawled` about a run that crawled 48. **Invisible until the
    trace began sampling**: before 935d8c0 every readable page was traced, so
    traced and crawled were the same set and the sentence was true by accident.
    Birch, one template and every page traced, could not show it.

    This is not a fourth population. The population still says which of the
    three legal sets the value lives in — what `matchesScope` reads, and what
    forbids a `site` ratio. Only the WORD for the denominator moves.
    """
    if population not in POPULATIONS:
        raise ValueError(f"not a legal population: {population!r}")
    if basis is not None and of is None:
        # A basis with no denominator describes nothing and would render as a
        # bare word beside a plain number.
        raise ValueError("a basis override needs an `of` to describe")
    return {"value": value, "population": population,
            "basis": basis or POPULATION_BASIS[population], "of": of}


def crawled_paths(evidence: dict) -> list[str]:
    """The on-host path keys this run actually fetched, trailing slash
    normalised — the `crawl` population, as a set rather than a size.

    Sent to the screen as well as counted because prevalence is affected OF
    ASSESSED: the numerator has to be intersected with this, or a record that
    has accumulated across runs can report more affected pages than the run
    fetched and the ratio reads above 100%.
    """
    from clauditseo.crawler.types import stored_page_is_eligible
    from urllib.parse import urlsplit
    host = urlsplit(evidence.get("start_url") or "").netloc
    keys = set()
    for p in (evidence.get("pages") or []):
        if not p.get("url") or not stored_page_is_eligible(p):
            continue
        k = _host_path(p["url"], host)
        if k is not None:
            keys.add(k)
    return sorted(keys)


def populations_payload(conn: sqlite3.Connection, run_id: str | None, *,
                        record_pages: int, page_url: str | None = None) -> dict:
    """The three populations a count may be counted over, and the page's own
    scope — which is what decides whether a count renders plain or as a ratio.

    The scope's extent is 150 BJ's site size, not the record: the part header
    states coverage once from BJ (`45 of 53 on the site`), and a count whose
    population covers exactly that much has nothing to disambiguate.
    """
    crawled: list[str] = []
    site_pages: int | None = None
    have_run = False
    if run_id:
        evidence_raw = evidence_text(conn, run_id)
        if evidence_raw:
            try:
                ev = parsed_evidence(evidence_raw)
            except (TypeError, ValueError):
                ev = None
            if ev:
                have_run = True
                crawled = crawled_paths(ev)
                site_pages = site_size(ev)["size"]
    return {
        "crawl": {"size": len(crawled) if have_run else None,
                  "basis": POPULATION_BASIS["crawl"], "paths": crawled},
        # No size, by construction — see POPULATION_BASIS.
        "site": {"size": None, "basis": POPULATION_BASIS["site"], "paths": []},
        "record": {"size": record_pages, "basis": POPULATION_BASIS["record"],
                   "paths": []},
        # Narrowed to one page the scope is that page, so every count states
        # its population: on a screen that says it is one page, a site-wide
        # ratio rendered plain would read as the page's own.
        "scope": ({"pages": 1, "basis": "on this page"} if page_url
                  else {"pages": site_pages, "basis": "on the site"}),
    }


#: The probe-page cap the crawler's UA matrix uses (crawler.ua_matrix.PROBE_PAGES).
_UA_PROBE_PAGES = 2


#: The agents the parity block keys its documents by, in the order the
#: screen draws them (crawler.parity.PARITY_AGENTS).
_PARITY_AGENT_KEYS = ("desktop", "iphone", "googlebot-smartphone")


def _mobile_parity_display(conn: sqlite3.Connection, run_id: str,
                           evidence: dict) -> dict | None:
    """The stored parity block (item 151) in the shape the Crawl part's "now"
    draws: one sentence, the two pair verdicts, a row per probed page, and the
    parity findings this run raised.

    **Server half only.** The part page is being rebuilt (items 162/163), so
    nothing draws this yet; it is shaped for a sentence and a small table, not
    for a layout.

    None where the run did not probe - a run from before 0.27.0, a
    verification - which is not assessed, never "no divergence". A block that
    probed nothing (every fetch failed, or the clock ran out first) is returned
    with `probed: 0` and its own statement, because that is a run that tried.
    Each row keeps only what a reader needs: the verdict and which fields
    differed, with both values, and each agent's status and size. Hashes and
    raw head fields stay in the evidence.
    """
    block = evidence.get("mobile_parity")
    if not isinstance(block, dict):
        return None
    from clauditseo.modules.tec import PARITY_CHECKS

    def pair(p: dict | None) -> dict:
        p = p or {}
        return {"verdict": p.get("verdict") or "not_assessed",
                "differs": [{"field": x.get("field"), "base": x.get("base"),
                             "other": x.get("other")}
                            for x in (p.get("named") or []) + (p.get("size") or [])]}

    start = evidence.get("start_url") or ""
    rows = []
    for r in block.get("pages") or []:
        docs = r.get("documents") or {}
        rows.append({
            "url": r.get("url"),
            "path": _short_path(r.get("url") or "", start),
            "agents": {k: {"status": (docs.get(k) or {}).get("status"),
                           "bytes": (docs.get(k) or {}).get("bytes")}
                       for k in _PARITY_AGENT_KEYS},
            "device": pair(r.get("device")),
            "bot": {**pair(r.get("bot")),
                    "compared_with": r.get("bot_compared_with") or "iphone"},
        })
    raised = {row["check_id"]: {"severity": row["severity"], "summary": row["summary"]}
              for row in conn.execute(
                  "SELECT check_id, severity, summary FROM findings WHERE run_id=?"
                  f" AND dimension='TEC' AND check_id IN ({','.join('?' * len(PARITY_CHECKS))})",
                  (run_id, *sorted(PARITY_CHECKS)))}
    return {
        "statement": block.get("statement"),
        "mode": block.get("mode"),
        "sample_rule": block.get("sample_rule"),
        "probed": block.get("probed") or 0,
        "fetches": block.get("fetches") or 0,
        "truncated_by": block.get("truncated_by"),
        "device": (block.get("device") or {}).get("verdict") or "not assessed",
        "bot": (block.get("bot") or {}).get("verdict") or "not assessed",
        "javascript_executed": bool(block.get("javascript_executed")),
        "covers": block.get("covers"),
        "agents": list(_PARITY_AGENT_KEYS),
        "pages": rows,
        "raised": raised,
    }


def _short_path(url: str, start: str) -> str:
    """A probed URL as the path a table row shows; the full URL where it is
    on another host than the run's start."""
    from urllib.parse import urlsplit
    u, s = urlsplit(url), urlsplit(start)
    if u.netloc and s.netloc and u.netloc.lower().removeprefix("www.") != \
            s.netloc.lower().removeprefix("www."):
        return url
    return (u.path or "/") + (f"?{u.query}" if u.query else "")


def _ua_matrix_display(evidence: dict) -> list[dict] | None:
    """The stored UA matrix in the shape the "now" table draws (item 137, brief
    v18 step AZ, task 4).

    The crawler stores each row as `{agent, robots, home_status, probe_status,
    headers, error, agent_class, sent, ...}`; the screen wants `{agent, class,
    sent, robots, fetched: [{url, status}], note}` — a status per fetched URL,
    with the URLs named. A row stored before 145 BG has no class or `sent`: the
    class resolves by name from the agent list and `sent` defaults true, which
    is what that matrix did. The probe
    URLs are not stored on the row (only their statuses), so they are recomputed
    from the crawl's own pages by the crawler's rule (same-host reached HTML,
    not home, capped) — the same selection `crawler.ua_matrix.probe_urls` makes,
    read off the stored page dicts. Returns None on a run that captured no
    matrix.
    """
    rows = evidence.get("ua_matrix")
    if not rows:
        return None
    from urllib.parse import urlsplit as _split

    start = evidence.get("start_url") or ""
    host = _split(start).netloc.lower()
    home_path = (_split(start).path or "/").rstrip("/") or "/"
    probes: list[str] = []
    for p in (evidence.get("pages") or []):
        url = p.get("url") or ""
        if p.get("status") != 200 or not str(p.get("content_type") or "").startswith("text/html"):
            continue
        s = _split(url)
        if s.netloc.lower() != host or ((s.path or "/").rstrip("/") or "/") == home_path:
            continue
        probes.append(url)
        if len(probes) >= _UA_PROBE_PAGES:
            break
    urls = [start] + probes
    from clauditseo.crawler.ua_matrix import agent_class

    out = []
    for r in rows:
        sent = r.get("sent", True) is not False
        statuses = [r.get("home_status")] + list(r.get("probe_status") or [])
        if not sent:
            statuses = [None] * len(urls)
        fetched = [{"url": u, "status": s} for u, s in zip(urls, statuses)]
        refused = (r.get("robots") == "allow"
                   and any(isinstance(s, int) and s >= 400 for s in statuses))
        if not sent:
            note = ("a robots token, never sent as a crawler name"
                    + ("; blocked at the rule" if r.get("robots") != "allow" else ""))
        elif r.get("robots") != "allow":
            note = "blocked at the rule"
        elif refused:
            hint = ", ".join(sorted((r.get("headers") or {}).keys()))
            note = ("allowed by robots, refused by the server"
                    + (f" — {hint}" if hint else " — server-side filtering?"))
        elif r.get("error"):
            note = r["error"]
        else:
            note = None
        out.append({"agent": r.get("agent"),
                    "class": r.get("agent_class") or agent_class(r.get("agent") or ""),
                    "sent": sent, "robots": r.get("robots"),
                    "fetched": fetched, "note": note})
    return out


def crawl_depth_payload(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """Pages by clicks from the home page, for one stored run (brief v16b).

    Read off `click_depth`, which `crawler.evidence.click_depth` computes from
    the whole link graph and writes onto every page record. That field is the
    only depth this product stores and this reader does not add a second one:
    the expert reports, the link suggester and the brief target picker all
    quote it, and a chart disagreeing with those would be a second answer to
    the same question.

    **Pages with no click path from the home page are the block's own
    subject, and they are not the shape the item expected.** The item says
    "pages at depth 0 that are not the entry URL arrived only through the
    sitemap". That is what an *imported* run looks like - a Screaming Frog
    CSV can spell any page's crawl depth 0 - and what a crawler run never
    looks like: `click_depth` seeds one page at 0 and walks outward, so a
    page the sitemap put in the frontier and no internal link points at
    comes back `None`, not `0`. Both are the same claim, so both are counted
    here, and both land on the home bar the item puts them on. Measured on
    Acme's 227-page run of 2026-09-06: one page at 0, and seventeen at
    `None` - seventeen pages a reader taking the field literally would have
    dropped without saying so, out of a block whose whole subject is
    reachability.

    `None` on every page is the one case that is not this: the walk starts
    at `home_of`, so a run whose home page was never fetched has no depth
    anywhere. That is absent data, and `recorded` is False rather than one
    enormous home bar claiming the whole site arrived by sitemap.

    Returns None where there is no run or no stored crawl to read at all,
    which is different again from a crawl that stored no depths.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id, kind, scan_scope, crawled_paths"
        " FROM audit_runs WHERE id=?", (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None
    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    if not pages:
        return None

    from clauditseo.crawler.evidence import home_of
    start = evidence.get("start_url") or ""
    home = home_of(start, pages)
    stored = {p["url"]: p.get("click_depth") for p in pages}
    base = {"run_id": row["id"], "scope": scope_of(row),
            "entry": home or start or None, "crawled": len(pages),
            # Item 229: the chart counts every stored page, error pages too,
            # so its population is not the "reached" beside it. Said, not
            # hidden: the note names both.
            "errored": sum(1 for p in pages if (p.get("status") or 0) >= 400),
            "deep_from": DEEP_CLICKS + 1}
    if not any(isinstance(d, int) for d in stored.values()):
        return {**base, "recorded": False, "bars": [], "at": {}}

    # The home bar's two populations: the home page, and every page that
    # reached this crawl without a click path from it.
    sitemap_only = sorted(url for url, d in stored.items()
                          if url != home and (d is None or d == 0))
    orphans = set(sitemap_only)
    at = {url: (0 if url in orphans else int(d))
          for url, d in stored.items() if url in orphans or d is not None}
    counts: dict[int, int] = {}
    for d in at.values():
        counts[d] = counts.get(d, 0) + 1
    # Contiguous from 0 to the deepest depth present, so a depth nothing sits
    # at is a gap in the picture rather than a bar the axis skips over. No
    # tail past the deepest: an axis padded to a round number would say the
    # crawl looked further than it did.
    bars = [{"depth": d, "pages": counts.get(d, 0),
             "sitemap_only": len(sitemap_only) if d == 0 else 0}
            for d in range(max(at.values()) + 1)]
    return {**base, "recorded": True, "bars": bars, "at": at}


def heading_shapes_payload(conn: sqlite3.Connection,
                           run_id: str | None) -> dict | None:
    """Which heading fault each page of one run carries (brief v16d).

    The site-scope half of the Headings blocks. It carries **the shape and
    nothing else** - `H2 → H4`, `no H1` - because the shape is the only
    part of the row a client cannot work out for itself: what a template is
    is already decided once, in `anatomy.tsx`'s `templatesOf`, and grouping
    226 pages by (shape, template) here would put a second implementation of
    "a template is a first segment ten or more pages share" in a second
    language. The client groups the URLs this returns with the function it
    already has, so the table below the checks and the templates named on the
    check group line above it cannot disagree about what a template is.

    The item allowed for the shape being derived rather than stored, and it
    is derived: `heading-skip` stores `sequence` and `outline_index` in its
    evidence, so the shape *is* recoverable from a stored finding - but only
    for the fifty rows the anatomy payload carries, against the 226 pages the
    record counts. It is read here from each page's own stored heading list
    through `onp.heading_outline_state`, which is the function the check
    itself calls, so a shape on the table and the summary on the finding are
    one decision seen twice.

    Keyed by URL and coded rather than labelled, because a site with two
    hundred faulted pages would otherwise ship two hundred copies of the same
    sentence: `labels` carries one entry per distinct code, with the check it
    belongs to and the token it draws in.

    Returns None where there is no run or no stored crawl. `recorded` is
    False where the run stored no heading list on any page - absent, not
    clean, and the block says so rather than drawing an empty table.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id, kind, scan_scope FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None
    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    if not pages:
        return None

    from clauditseo.modules import onp as _onp
    base = {"run_id": row["id"], "scope": scope_of(row), "crawled": len(pages)}
    # Item 180 (ruling 20260918-0402): the picture reads the pages the checks
    # read. On Acme it drew "no H1 · 4" beside `h1-missing` "3 of 99", because
    # it also read `/apply?product_type=loc` - a page whose canonical points at
    # `/apply`, so the checks judge the canonical page and not the variant. The
    # pages left out are named rather than living as a silent difference
    # between two blocks.
    from urllib.parse import urlsplit as _split

    def _own(p: dict) -> bool:
        canon = p.get("canonical") or p.get("link_header_canonical")
        if not canon:
            return True
        a, b = _split(p["url"]), _split(canon)
        norm = lambda s: (s.netloc, (s.path or "/").rstrip("/") or "/", s.query)
        return norm(a) == norm(b)

    elsewhere = [p["url"] for p in pages if not _own(p)]
    read = [p for p in pages if _own(p)
            and (p.get("outline") is not None or p.get("headings") is not None)]
    base["not_checked"] = elsewhere
    if not read:
        return {**base, "recorded": False, "pages": 0, "at": {}, "labels": {}}

    labels: dict[str, dict] = {}
    at: dict[str, list[str]] = {}
    for page in read:
        state = _onp.heading_outline_state(page.get("outline")
                                           or page.get("headings") or [])
        fires = state["fires"]
        codes: list[str] = []
        # Order is the order the table reads best in and not an order of
        # severity: a page with no H1 that also skips a level is one page on
        # two rows, and the missing H1 is the thing to say first.
        if fires["h1-missing"]:
            codes.append("h1-missing")
            labels.setdefault("h1-missing", {"label": "no H1", "tone": "bad",
                                             "check": "h1-missing"})
        if fires["h1-multiple"]:
            codes.append("h1-multiple")
            labels.setdefault("h1-multiple", {"label": "more than one H1",
                                              "tone": "bad", "check": "h1-multiple"})
        skip = fires["heading-skip"]
        if skip:
            code = f"skip:{skip['from']}>{skip['to']}"
            codes.append(code)
            labels.setdefault(code, {"label": _onp.skip_shape(skip),
                                     "tone": "warn", "check": "heading-skip"})
        if codes:
            at[page["url"]] = codes
    return {**base, "recorded": True, "pages": len(read), "at": at,
            "labels": labels}


#: How many chains the site-scope block draws before it says it has
#: stopped (brief v16g). Eight is the item's number, and it is a number for
#: a block whose whole subject is the exception: a site with eight broken
#: canonicals has a template problem, and the ninth card says nothing the
#: eighth did not. Measured before taking it: Acme's 227-page run of
#: 2026-09-06 has exactly one chain that is not the healthy case.
CANONICAL_CHAINS_CAP = 8

#: Worst first. `bad` is a chain that ends where nothing can be indexed;
#: `warn` is one that points somewhere real; `mute` is the variant no check
#: raises. `ok` never reaches this list.
CHAIN_ORDER = {"bad": 0, "warn": 1, "mute": 2, "ok": 3}

#: The checks the record holds about canonicals, so the block's "N more"
#: link and the check id in a card's sub-line narrow to the same rows. One
#: list, here, because a second copy on the client would drift the first
#: time a check is added.
CANONICAL_CHECKS = ["canonical-mismatch", "canonical-missing",
                    "canonical-missing-variant"]


def canonical_nodes(evidence: dict) -> dict:
    """Every URL one stored run knows about, as the canonical walk needs it.

    Keyed twice - by the URL as the crawl spells it and by path - because a
    canonical is written by hand and a hand writes `https://site/x`,
    `//site/x` and `/x` for the same page. `crawl_depth_payload`'s
    `pagesAtDepth` makes the same allowance on the client and for the same
    reason.

    Each node carries only what the sweep already recorded, and nothing is
    re-derived: status and `canonical` off the page record, `noindex` off
    the two directives that carry one, `robots_blocked` off the run's own
    list of URLs it declined to fetch, `in_sitemap` off the entries it read.

    **`noindex` is read from `x_robots_tag` as well as `meta_robots`,
    the same two signals `TEC/noindex-linked` reads since item 137.** That
    check is about a page linked internally and told not to count; this is a
    label on the end of a chain, and a header that noindexes the target is
    exactly as binding on a crawler as a meta tag. The difference is here
    in writing rather than silently, and it moves no finding: a chain
    ending on a noindexed node already carries `canonical-mismatch` on its
    first node, which is the finding the block's agreement test compares
    against.
    """
    from urllib.parse import urlsplit

    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    blocked = {_chain_key(u) for u in (evidence.get("robots_blocked") or [])}
    sitemap = {_chain_key(u) for u in (evidence.get("sitemap_entries") or [])}
    nodes: dict[str, dict] = {}
    for page in pages:
        url = page["url"]
        path = urlsplit(url).path or "/"
        directives = " ".join(str(page.get(k) or "")
                              for k in ("meta_robots", "x_robots_tag")).lower()
        node = {
            "url": url, "path": path, "in_crawl": True,
            "status": page.get("status"),
            "canonical": page.get("canonical"),
            "noindex": "noindex" in directives,
            "robots_blocked": _chain_key(url) in blocked,
            "in_sitemap": _chain_key(url) in sitemap,
        }
        nodes[url] = node
        # The path key never overwrites a URL key, and the first page wins
        # where two spellings share a path: the alternative is a lookup
        # whose answer depends on the order the crawl happened to store.
        nodes.setdefault(path, node)
        nodes.setdefault(path.rstrip("/") or "/", node)
    # A URL robots.txt forbade was never fetched, so it is in no page
    # record - but a chain ending on one has to say `robots-blocked` and
    # not `not crawled`, which are different instructions to the reader.
    for url in (evidence.get("robots_blocked") or []):
        path = urlsplit(url).path or "/"
        node = {"url": url, "path": path, "in_crawl": True, "status": None,
                "canonical": None, "noindex": False, "robots_blocked": True,
                "in_sitemap": _chain_key(url) in sitemap}
        nodes.setdefault(url, node)
        nodes.setdefault(path, node)
    return nodes


def _chain_key(url: str) -> str:
    """How this reader decides two spellings are one URL: host and path,
    trailing slash removed. The same tolerance `pagesAtDepth` applies."""
    from urllib.parse import urlsplit

    split = urlsplit(url)
    return f"{split.netloc.lower()}{(split.path or '/').rstrip('/') or '/'}"


def canonical_chains_payload(conn: sqlite3.Connection,
                             run_id: str | None) -> dict | None:
    """The site's canonical chains that are not the healthy case (brief v16g).

    The site-scope half of the Indexability blocks. Every crawled HTML page
    is walked through `onp.canonical_chain_state` - the function the
    canonical checks themselves read their decision from - and everything
    that comes back `ok` is dropped, because a card per self-canonical page
    is 226 identical loops on Acme and says nothing.

    Worst first: the chains that end where nothing can be indexed, then the
    ones that point somewhere real, then the variants no check raises;
    within a kind, the longest chain first and then by path so the order is
    stable between two readings of one run.

    `healthy` and `total` are carried whole rather than left to be counted
    from `chains`, because `chains` is capped: a block that said "8 of 8"
    about a site with forty broken canonicals would be the cap lying about
    the measurement.

    Returns None where there is no run or no stored crawl. `recorded` is
    False where no page of the run stored a canonical field at all - absent,
    not clean, and the block says so rather than declaring the site healthy
    on a measurement nobody made.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id, kind, scan_scope FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None
    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    if not pages:
        return None

    from clauditseo.modules import onp as _onp
    base = {"run_id": row["id"], "scope": scope_of(row), "crawled": len(pages),
            "cap": CANONICAL_CHAINS_CAP, "checks": CANONICAL_CHECKS}
    # Exactly what `onp.html_pages` hands the checks: status 200 and HTML.
    # Not a near-enough filter - a 404 page draws a chain card here and can
    # never carry a canonical finding, so widening this by one status code
    # would break the agreement the whole block is built on. Non-200 pages
    # are still *targets*: a chain ending on one is how `404` gets onto the
    # terminal node.
    html = [p for p in pages
            if p.get("status") == 200
            and str(p.get("content_type", "")).startswith("text/html")]
    read = [p for p in html if "canonical" in p]
    if not read:
        return {**base, "recorded": False, "chains": [], "healthy": 0,
                "total": 0, "more": 0}

    nodes = canonical_nodes(evidence)
    walked = [_onp.canonical_chain_state(p["url"], nodes) for p in read]
    healthy = sum(1 for c in walked if c["kind"] == "ok")
    unhealthy = sorted((c for c in walked if c["kind"] != "ok"),
                       key=lambda c: (CHAIN_ORDER[c["kind"]], -c["hops"], c["path"]))
    return {**base, "recorded": True, "total": len(walked), "healthy": healthy,
            "chains": unhealthy[:CANONICAL_CHAINS_CAP],
            "more": max(len(unhealthy) - CANONICAL_CHAINS_CAP, 0)}

#: How many dots the bytes-for-pixels scatter will draw before it says it
#: has stopped. Only images the scatter *can* draw are in the list this
#: bounds - a weight the browser saw, against a box it measured - so the
#: number to compare it with is not a run's image count but its measured
#: one. Measured before choosing it: Acme's 227-page run of 2026-09-06
#: stores 6,008 images and 0 measured weights; Birch's stores 252 and 147.
#: Two thousand is past both and short of a scatter no browser can lay out.
IMAGE_DOTS_CAP = 2000


def image_budget_defaults(conn: sqlite3.Connection, site_id: str) -> dict:
    """The three budget numbers for one site: the record's, or the check's
    own defaults where the record names none.

    One reader, because two blocks now apply them - the scatter and the
    thumbnail wall - and a default spelled twice is how a picture comes to
    disagree with the finding it is drawn beside.
    """
    from clauditseo.modules.onp import (BUDGET_IMAGE_KB, BYTES_PER_PIXEL_CAP,
                                        PER_PIXEL_FLOOR_KB)
    row = conn.execute(
        "SELECT budget_image_kb, bytes_per_pixel, budget_image_floor_kb"
        " FROM sites WHERE id=?", (site_id,)).fetchone()

    def num(field, fallback):
        try:
            return type(fallback)((row and row[field]) or fallback)
        except (TypeError, ValueError, IndexError):
            return fallback

    return {"floor_kb": num("budget_image_floor_kb", PER_PIXEL_FLOOR_KB),
            "image_kb": num("budget_image_kb", BUDGET_IMAGE_KB),
            "bytes_per_pixel": num("bytes_per_pixel", BYTES_PER_PIXEL_CAP)}


def image_state(record: dict, budget: dict) -> dict:
    """What one stored image is, weighed against what it is drawn at.

    The one place a dot's colour and a tile's frame are decided (brief
    v16c). Both blocks on the Images part page read this, and the verdict
    inside it is `onp.image_weight_state` - the function `img-heavy` itself
    calls - so a dot and the finding beside it cannot disagree, whatever a
    later edit does to the check.

    **A weight of zero is not a light image.** `imaging._RESOURCES_JS` reads
    `encodedBodySize || transferSize || 0`, and a cross-origin image served
    without `Timing-Allow-Origin` reports both as zero, so a stored 0 is the
    browser saying it could not see the bytes. `image_weight_state` has
    always read it that way and so does this.

    **`alt_missing` is `img-alt-missing`'s rule and not a second opinion.**
    That check fires on an absent alt and on a blank one alike and says
    nothing about `role`, so neither does this. `decorative` is carried
    beside it rather than folded into it: a tile that stopped framing what
    the check still raises would be the disagreement this function exists
    to prevent.
    """
    from clauditseo.modules.onp import image_weight_state
    # The widest box the page was measured at, taken the way the check
    # takes it, so a dot's x is the x the finding measured against.
    shown = max(((v[0], v[1]) for v in (record.get("rendered") or {}).values()),
                default=(0, 0))
    pixels = shown[0] * shown[1]
    weight = record.get("weight_kb")
    state, per_pixel = image_weight_state(weight, pixels, budget["image_kb"],
                                          budget["bytes_per_pixel"], budget["floor_kb"])
    alt = record.get("alt")
    missing = alt is None or not str(alt).strip()
    return {
        "drawn_w": shown[0] or None, "drawn_h": shown[1] or None,
        "kb": weight if state != "unmeasured" else None,
        "bytes_per_pixel": per_pixel,
        "alt_missing": missing,
        "decorative": str(record.get("role") or "").lower() == "presentation",
        "weight_state": state,
        # The four tones the legend names. `bad` is over budget and missing
        # alt, which is the pair worth looking at first; `unmeasured` is
        # none of the four and draws no dot at all.
        "state": ("bad" if state == "over" and missing
                  else "warn" if state == "over"
                  else "mute" if state == "unscored"
                  else "ok" if state == "ok" else "unmeasured"),
    }


def image_budget_payload(conn: sqlite3.Connection, run_id: str | None) -> dict | None:
    """Every image the crawl could weigh, for the bytes-for-pixels scatter.

    Brief v16c. One dot per image that has both halves of the picture - a
    weight the browser saw, and a box it measured - because an image
    missing either has nowhere to be drawn. The ones left out are counted
    rather than dropped: `unmeasured` is how many carried no weight and
    `unplaced` how many carried one with no rendered box, and the block
    says both. A scatter quietly showing 147 of a site's 252 images would
    read as a site with 147 images.

    **No join.** The item allows for the rendered box and the transferred
    bytes being stored apart and asks for a join on the resolved URL. They
    are not: `crawler.evidence.snapshot` merges `imaging.measure`'s output
    into each `image_inventory` row as it writes it, so the box and the
    bytes are already fields of one record. Joining here would be a second
    merge of the same two things.

    **The dots, and not the wall's rows.** The wall is one page's images in
    DOM order, and `page_facts` already carries that page's whole inventory
    with `image_state` stamped on each row by this same function. Shipping
    every image of every page here as well would put Acme's 6,008 records
    on a payload the anatomy screen re-fetches on every refresh, to draw at
    most sixty of them.

    Returns None where there is no run or no stored crawl to read, which is
    a different answer from a crawl that stored images nobody measured.
    """
    if not run_id:
        return None
    row = conn.execute(
        "SELECT id, site_id, kind, scan_scope, crawled_paths, tier, started_at"
        " FROM audit_runs WHERE id=?", (run_id,)).fetchone()
    evidence_raw = evidence_text(conn, run_id)
    if row is None or not evidence_raw:
        return None
    try:
        evidence = parsed_evidence(evidence_raw)
    except (TypeError, ValueError):
        return None
    pages = [p for p in (evidence.get("pages") or []) if p.get("url")]
    if not pages:
        return None
    budget = image_budget_defaults(conn, row["site_id"])

    # Item 241: one dot per distinct image - the same file drawn at the same
    # size - carrying the pages it is on. Twenty22's header logo is three
    # placements on each of 26 pages, and 78 dots on one point read as one
    # image in both views, which is why the site and the page looked alike.
    from urllib.parse import urljoin, urlsplit
    groups: dict[tuple, dict] = {}
    total = unmeasured = unplaced = capped = placed = 0
    weighed_pages: set[str] = set()
    for page in pages:
        path = urlsplit(page["url"]).path or "/"
        for record in (page.get("image_inventory") or []):
            total += 1
            if record.get("rendered"):
                weighed_pages.add(path)
            got = image_state(record, budget)
            if got["state"] == "unmeasured":
                unmeasured += 1
                continue
            if not (got["drawn_w"] and got["drawn_h"]):
                unplaced += 1
                continue
            placed += 1
            # The file, absolute (item 246): `resolved` is what the browser
            # loaded, and for a lazy image it never swapped in - weighed by
            # its header - that is the shared `data:` placeholder, which put
            # every such thumbnail on one dot.
            resolved = record.get("resolved") or ""
            file = (resolved if resolved and not resolved.startswith("data:")
                    else urljoin(page["url"], record.get("lazy_src") or record.get("src") or ""))
            key = (file, got["drawn_w"], got["drawn_h"])
            if key in groups:
                g = groups[key]
                g["placements"] += 1
                if path not in g["paths"]:
                    g["paths"].append(path)
                continue
            # The cap sits between the field and the list, which is the
            # bound the real-data-scale invariant looks for and the place a
            # reader of this line would look for it.
            if len(groups) >= IMAGE_DOTS_CAP:
                capped += 1
                continue
            # The file, not a lazy loader's placeholder (item 241): the dot's
            # name and tooltip read this.
            groups[key] = {"src": record.get("lazy_src") or record.get("src") or "",
                           "page": page["url"],
                           "paths": [path], "placements": 1,
                           "weight_source": record.get("weight_source"),
                           "w": got["drawn_w"], "h": got["drawn_h"],
                           "kb": got["kb"], "bytes_per_pixel": got["bytes_per_pixel"],
                           "alt_missing": got["alt_missing"],
                           "decorative": got["decorative"], "state": got["state"]}
    dots = list(groups.values())
    return {
        "run_id": row["id"], "scope": scope_of(row), "budget": budget,
        "dots": dots, "total": total, "drawable": len(dots) + capped,
        "unmeasured": unmeasured, "unplaced": unplaced, "pages": len(pages),
        # Item 241: placements drawn, and on how many pages the browser pass
        # looked at all - "78 placements of 1 distinct image; weighed on 40
        # of 45 pages".
        "placements": placed, "weighed_pages": len(weighed_pages),
        # Whether the crawl found images at all, and whether any of them can
        # be drawn. Two questions, because "this site has no images" and
        # "nobody weighed this site's images" are different sentences and
        # the block prints a different one for each.
        "recorded": bool(total),
        # Item 205: whether the audit MEASURED, not whether anything came out
        # of it - True, False, or "unavailable" (no renderer). Evidence stored
        # before the run recorded it is read from the images themselves: a
        # pass that ran leaves a rendered box, and a crawl nobody measured
        # leaves none anywhere.
        "measured": _images_measured(evidence, pages),
        # The audit these numbers are, named on the block (item 205): the
        # chart "disappeared" when the picked audit changed under it.
        "tier": row["tier"], "started_at": row["started_at"],
    }


def _images_measured(evidence: dict, pages: list[dict]) -> bool | str:
    got = evidence.get("images_measured")
    if got in (True, False, "unavailable"):
        return got
    return any((r.get("rendered") or r.get("weight_kb"))
               for p in pages for r in (p.get("image_inventory") or []))


def _graph_host(url: str) -> str:
    """A URL's host without `www.`, or "" where it has none. The model reads
    it to decide whether an `@id` is local (RENDER_RULES §1) and what the
    site's locale is (§7a)."""
    from urllib.parse import urlsplit
    try:
        return urlsplit(str(url)).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


#: The readable half's first section, whose opening lines are the brief's
#: own verdict on the set (brief v13 step AO). Taken rather than
#: re-derived: the engine counts rows, and this is what the brief said.
_ASSESSMENT = re.compile(r"^#+\s*[^\n]*assessment[^\n]*$", re.I | re.M)


def _latest_sweep(conn: sqlite3.Connection, site_id: str,
                  dimension: str | None = None) -> dict | None:
    """What a part's automatic counts were measured by (brief v13 step AO;
    item 212): the reference crawl of `dimension`, read from the Latest View
    (item 239 step 2) - the newest reading of the whole site that measured
    it. `None` asks about the site as a whole: the newest reading of the
    whole site, of any dimension - as item 212 read it, and still the ONP-only
    T2 on twenty22.

    Item 212 first read the newest audit whose dimensions named the part's,
    which is the same answer for twenty22 and a different one wherever a
    verify, a refresh or a page scan was the newest run to name it: none of
    those is a reading of the site."""
    from . import latest_view
    ref = (latest_view.newest_reading(conn, site_id) if dimension is None
           else latest_view.reference(conn, site_id, dimension))
    return {k: ref[k] for k in ("run_id", "at", "tier", "dimensions")} if ref else None


def _check_cost(check: str) -> str:
    """One check's cost, cached for the length of a view.

    `check_costs()` reads the registry and the playbook and is not free to
    build; a view asks it once per check of every part.
    """
    from clauditseo.checks import check_costs

    global _COSTS
    if _COSTS is None:
        _COSTS = check_costs()
    return _COSTS.get(check) or _COSTS.get(check.split("/")[-1]) or "free"


#: Built on first use and kept: the registry does not change inside a
#: process, and rebuilding it per check made a view of eighteen parts read
#: the module source eighteen times over.
_COSTS: dict[str, str] | None = None


def brief_assessment(report: str | None, cap: int = 8000) -> str | None:
    """The report's assessment section, whole and as markdown (item 210): from
    the assessment heading to the next heading at its own level or above.

    Whole, because the three-sentence cut split "(e.g." on its full stop and
    dropped the sections the brief exists to produce (Headings' verdict,
    Schema's "Patterns"). As markdown, because it is rendered as the model's
    words, where a backtick is code rather than a character on the page."""
    if not report:
        return None
    m = _ASSESSMENT.search(report)
    if not m:
        return None
    level = len(m.group(0)) - len(m.group(0).lstrip("#"))
    rest = report[m.end():]
    stop = re.search(r"^#{1,%d}\s" % level, rest, re.M)
    body = (rest[:stop.start()] if stop else rest).strip()
    return body[:cap] or None


def _brief_summary(report: str | None, sentences: int = 3) -> str | None:
    """The first few sentences under the report's assessment heading."""
    if not report:
        return None
    m = _ASSESSMENT.search(report)
    if not m:
        return None
    rest = report[m.end():].lstrip()
    # A section that opens with a table or a list has no verdict sentence
    # to quote, and a row of pipes is not one.
    if re.match(r"[|\-*]", rest):
        return None
    # Stop at the next heading; a table or list under it is not prose.
    body = re.split(r"\n#+\s|\n\||\n[-*]\s", rest, maxsplit=1)[0].strip()
    body = " ".join(body.split())
    if not body:
        return None
    parts = re.split(r"(?<=[.!?])\s+", body)
    return " ".join(parts[:sentences]).strip() or None


#: How many of each list the part page is given. Twenty-five was the old
#: `link_sample` cut and is kept for the outgoing list; the incoming list
#: is what decides `inlinks-low`, so it carries more before it bites.
LINKS_SHOWN = 40


def _links_out(links: list) -> list[dict]:
    """This page's own links, body first."""
    return sorted((link for link in links if isinstance(link, dict)),
                  key=lambda link: link.get("region") != "body")[:LINKS_SHOWN]


def _links_in(blob: dict, url: str) -> list[dict]:
    """Every link in the crawl that points at this page, body first.

    Counted from the same evidence the page itself was read from, so the
    number here and the number `inlinks-low` raised cannot disagree: two
    walks of one graph is how a badge comes to say 2 above a list of
    three.
    """
    out: list[dict] = []
    for record in (blob.get("pages") or []):
        if not isinstance(record, dict) or record.get("url") == url:
            continue
        for link in (record.get("links") or []):
            if isinstance(link, dict) and link.get("url") == url:
                out.append({"source": record["url"],
                            "anchor": link.get("anchor") or "",
                            "rel": link.get("rel") or "",
                            "region": link.get("region") or "body"})
    out.sort(key=lambda link: link["region"] != "body")
    return out[:LINKS_SHOWN]


def _weighed_inventory(conn: sqlite3.Connection, site_id: str,
                       inventory: list | None) -> list | None:
    """One page's stored images, each stamped with what it is against the
    site's budget (brief v16c).

    Stamped at read time rather than at crawl time, and that is the point:
    the budget is on the site record and an operator may change it after
    the run, so a verdict frozen into the evidence would go on saying what
    the numbers used to mean. Every value comes from `image_state`, which
    is the same function the scatter's dots come from and which calls the
    same `onp.image_weight_state` that raises `img-heavy` - so the tile's
    frame, the dot's colour and the finding row are one decision seen
    three times.

    The records are copied rather than written through: `pick` hands back
    the object parsed out of the stored evidence, and stamping it in place
    would edit a run's evidence in memory for every later reader of it.
    """
    if not inventory:
        return inventory
    budget = image_budget_defaults(conn, site_id)
    return [{**record, **image_state(record, budget)} for record in inventory]


def page_facts(conn: sqlite3.Connection, site_id: str, url: str) -> dict | None:
    """What the crawler actually saw on one page - the title it read, the
    outline, the images, the headers - read from the site's Latest View
    (item 239 step 3).

    A finding says a heading level was skipped; this says which heading. The
    two answer different halves of the same question, and an operator having
    to open the page to find the second half is the gap this closes.

    **Page-intrinsic fields** are the Latest View's page item: each written by
    the newest run that measured it (`latest_view.PAGE_FIELDS`), and dated.
    This used to pick each field from the newest run that *recorded* it,
    whatever that run measured; a run's evidence holds every field of a page
    it fetched, so an ONP-only audit supplied TEC's status and an unweighed
    crawl the image record. The per-field rule now lives in the write path.

    **Crawl-relative facts** - who links in, the canonical chain, click depth,
    how the crawl found the page, the site-wide fields - are read whole from
    the reference crawl of their dimension (amendment 4), never merged: a
    chain is how a set of pages pointed at each other at one moment.
    """
    from urllib.parse import urlsplit

    from clauditseo.modules import onp as _onp

    from . import latest_view
    path = urlsplit(url).path or "/"
    item = latest_view._get(conn, site_id, "page", path)
    if not item:
        return None
    ats = {cell["at"] for cell in item.values() if cell.get("at")}
    latest_at = max(ats) if ats else None
    latest_run = next((c["run_id"] for c in item.values() if c.get("at") == latest_at), None)
    dated: dict[str, str] = {f: c["at"][:10] for f, c in item.items()
                             if c.get("at") and c["at"] != latest_at}

    def pick(field: str, default=None):
        cell = item.get(field)
        return default if cell is None or cell.get("value") is None else cell["value"]

    def reference_blob(*keys: str) -> dict:
        run = latest_view.reference_run(conn, site_id, *keys)
        return (get_evidence(conn, run) or {}) if run else {}

    tec = reference_blob("TEC")
    lnk = reference_blob("LNK", "TEC")
    tec_page = next((p for p in tec.get("pages") or []
                     if isinstance(p, dict) and p.get("url") == url), {})

    def pick_site(field: str, default=None):
        return tec.get(field) if tec.get(field) is not None else default

    # The markup half of each image and what the image pass weighed, rejoined.
    weights = pick("image_weights", {}) or {}
    inventory = pick("image_inventory")
    if inventory is not None:
        inventory = [{**r, **weights.get(r.get("lazy_src") or r.get("src") or "", {})}
                     for r in inventory]
    levels = pick("heading_levels", []) or []
    headers = pick("headers", {}) or {}
    links = pick("links", []) or []
    return {
        "from_run": latest_run, "captured_at": latest_at, "url": url,
        # Item 243: dimension -> the date its reference crawls last fetched
        # this page, where the page has since left the site.
        "gone": (latest_view._get(conn, site_id, "presence", path) or {}).get("gone") or {},
        # Which values are older than the newest measurement, and how old.
        "dated": dated,
        "title": pick("title"), "meta_description": pick("meta_description"),
        # The snippet as a result will cut it (brief v16i Part B). Measured
        # here, off the same `onp.snippet` the length checks share, so the
        # card the page draws and the finding beside it cannot disagree.
        "snippet": _snippet(pick("title"), pick("meta_description")),
        "h1": pick("h1"),
        "heading_counts": {f"h{i}": levels.count(i) for i in range(1, 7)},
        "headings": pick("headings"),
        # The outline as the parser saw it (brief v11 step AJ); a run crawled
        # before that recorded only levels and text, so the reader falls back
        # to `headings` and says the region is unknown (brief v14 step AP).
        "outline": pick("outline"), "main_region": pick("main_region"),
        "heading_total": pick("heading_total", len(levels)),
        # The ladder the Headings part page draws (brief v16d), decided by
        # `onp.heading_outline_state`, the one function the checks call.
        "heading_outline": _onp.heading_outline_state(
            pick("outline") or pick("headings") or []),
        "images": pick("images"), "image_total": pick("image_total"),
        # The inventory the Images part page renders (brief v15), stamped
        # against the site's budget at read time (`_weighed_inventory`).
        "image_inventory": _weighed_inventory(conn, site_id, inventory),
        "word_count": pick("word_count"), "content_dates": pick("content_dates"),
        # The first sixty words, as the crawl recorded them (brief v17 AX).
        "opening": pick("opening") or "",
        "schema_types": pick("schema_types"), "jsonld_blocks": pick("jsonld_blocks"),
        # Every block as parsed, and the page's links to profile hosts
        # (brief v16 step AS); and unflattened, for the picture (AT-b).
        "schema_inventory": pick("schema_inventory"),
        "jsonld_raw": pick("jsonld_raw"),
        "profile_links": pick("profile_links"),
        "lang": pick("lang"), "a11y": pick("a11y"),
        "outlinks": len(pick("outlinks", []) or []),
        "link_sample": links[:25],
        # Crawl-relative: the reference crawl's (amendment 4).
        "click_depth": tec_page.get("click_depth"),
        # The two lists the Links part page draws (brief v17 step AW): what
        # this page links to (the page's own), and what links to it - the
        # half every check of this part is about, read whole from the links
        # reference crawl.
        "link_inventory": _links_out(links),
        "inlinks": _links_in(lnk, url),
        "canonical": pick("canonical"), "meta_robots": pick("meta_robots"),
        # This page's canonical chain (brief v16g), walked over the TEC
        # reference crawl by `onp.canonical_chain_state` - never over merged
        # page records, which would draw a chain that never existed.
        "canonical_chain": _onp.canonical_chain_state(url, canonical_nodes(tec)),
        "x_robots_tag": pick("x_robots_tag"),
        "link_header_canonical": pick("link_header_canonical"),
        "indexability": pick("indexability"),
        "status": pick("status"), "redirect_chain": pick("redirect_chain"),
        "discovered_via": tec_page.get("discovered_via"),
        "elapsed_ms": pick("elapsed_ms"), "cache_control": headers.get("cache-control"),
        "security_headers": {h: headers.get(h) for h in
                             ("strict-transport-security", "content-security-policy",
                              "x-content-type-options", "referrer-policy",
                              "permissions-policy", "x-frame-options")},
        "server": headers.get("server"),
        "viewport_tags": pick("viewport_tags"), "hreflang": pick("hreflang"),
        "nap_mentions": pick("nap_mentions"),
        "local_schema_blocks": len(pick("local_schema", []) or []),
        "site": {
            "robots_status": pick_site("robots_status"),
            "robots_txt_bytes": len(pick_site("robots_txt", "") or ""),
            "llms_txt_status": pick_site("llms_txt_status"),
            "sitemaps": pick_site("sitemaps"),
            "sitemap_entry_total": pick_site("sitemap_entry_total"),
            "duplicate_forms": pick_site("duplicate_forms"),
            "transport": pick_site("transport"),
        },
        # Never measured by any run - as opposed to measured and empty.
        "missing": [k for k in ("headings", "images", "schema_types", "lang", "a11y")
                    if k not in item],
        "observations": len({c["run_id"] for c in item.values()}),
    }
