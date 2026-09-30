"""Report generation: render, run the honesty checks, persist to disk and DB.

A report that fails a check is never written — the error surfaces instead,
because a wrong report is worse than no report.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from clauditseo.config import ROOT
from clauditseo.persistence import latest_view, repo, runs

from .checks import assert_report_honest, ungrounded_uncaveated_lines
from .render import (ANALYST_FIGURE_NOTE, au_date, provenance_tag, section_provenance,
                     render_comparison_report,
                     render_run_report, render_trend_report)

OUT_DIR = ROOT / "reports" / "out"
#: `run-free` is the run report without its two model sections (brief
#: v17 step AV6). A template rather than a flag, because the choice has to
#: survive the document: the filename is the register's key and the
#: artefact's identity, and a `free only` that lived only in a column
#: would produce two files a client could not tell apart - with the
#: reindexer, which reads documents back off disk, left to guess.
TEMPLATES = ("run", "run-free", "comparison", "monthly-trend")

#: The templates that render a single audit. `run-free` differs from `run`
#: in one thing - whether the paid half is printed - so it shares the
#: branch rather than growing a second copy of it that would drift.
RUN_TEMPLATES = ("run", "run-free")
AUDIENCES = ("client", "internal")


def _evidence_text(run_dicts: list[dict]) -> str:
    """What the analyst's narrative is checked AGAINST — measured only.

    This serialised `run["findings"]` wholesale, including the
    `source='model-judgement'` rows `_analyst_section` writes the narrative
    from, so `assert_report_honest` compared a text against itself and could
    only return clean. Audit 013 reproduced it end to end: a planted finding
    reading "Organic sessions fell 47318 percent" passed the check and
    printed into a client document carrying `confidence: medium`.

    The allowed set was also widened by the analyst's declared figures, on the
    stated grounds that such a figure "renders carrying ANALYST_FIGURE_NOTE,
    which is what makes admitting it honest rather than convenient". It does
    not, and it cannot: `narrative` is built by `_analyst_section`, which
    excludes `EXP:*`, and the only findings that carry declared figures ARE
    `EXP:*`. So the widening admitted brief figures into a check over text
    that can never contain a brief finding — covering no real case while
    letting a fabricated number through, which audit 014 reproduced end to
    end. The commit that added it recorded that it never bit: "62 passed in
    test_reporting_g7.py with no legitimate figure needing an allow-list
    entry."

    Removed rather than repaired. The declared figures still do their work,
    at the place they can: `record_expert_findings` marks the brief finding
    itself, and `_expert_section` renders the marker beside it.
    """
    payload = [{k: r.get(k) for k in ("composite_score", "subscores")}
               | {"findings": [f for f in (r.get("findings") or [])
                               if f.get("source") == "deterministic"]}
               for r in run_dicts]
    return json.dumps({"measured": payload}, default=str, ensure_ascii=False)


SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")


def tool_runs_for(conn: sqlite3.Connection, site_id: str) -> dict[str, str]:
    """Each analysis tool's newest run on the site, from the Latest View (item
    239 step 7), the plan aside: what the report's brief sections read."""
    return {t: a["run_id"] for t, a in latest_view.analyses(conn, site_id).items()
            if t != "plan"}


def _contract_sections(conn: sqlite3.Connection, tool_runs: dict[str, str]) -> list[str]:
    """One section per part for the conforming briefs that ran against this
    run (brief v10 step AF): the count of rows the brief proposed copy for,
    and the replacement table - page, what is there, what to put there.
    Every line carries the model's provenance tag, as the brief table above
    does, because the gate holds every number in the document to one."""
    from urllib.parse import urlsplit

    from clauditseo import briefs as brief_catalogue
    from clauditseo.analyses import part_labels

    labels = part_labels()
    out: list[str] = []
    # Item 237: a replacement for a finding that waits for the operator's
    # confirmation is not handed to the client either.
    from clauditseo.persistence.runs import (awaiting_confirmation, brief_fingerprint,
                                            contract_storage_dimension)
    # Item 239 step 7: each brief's newest run on the site, not one run's.
    first = next(iter(tool_runs.values()), None)
    site = conn.execute("SELECT site_id FROM audit_runs WHERE id=?", (first,)).fetchone()
    awaiting = awaiting_confirmation(conn, site["site_id"]) if site else set()
    stored = [conn.execute(
        "SELECT tool_id, model_id, contract, created_at FROM expert_reports"
        " WHERE run_id=? AND tool_id=? AND contract IS NOT NULL"
        " ORDER BY created_at DESC LIMIT 1", (rid, tool)).fetchone()
        for tool, rid in tool_runs.items()]
    for row in sorted((r for r in stored if r), key=lambda r: r["created_at"]):
        contract = json.loads(row["contract"] or "{}")
        rows = [r for r in contract.get("rows") or [] if r.get("replacement")
                and brief_fingerprint(
                    contract_storage_dimension(row["tool_id"], r.get("check_id") or "",
                                               r.get("dimension") or ""),
                    r.get("check_id") or "", r.get("page") or "") not in awaiting]
        if contract.get("status") != "read" or not rows:
            continue
        brief = brief_catalogue.by_id().get(row["tool_id"])
        part = contract.get("part") or (brief.part if brief else None)
        label = labels.get(part) or (brief.name if brief else row["tool_id"])
        tag = provenance_tag(f"model judgement ({row['model_id'] or 'unknown model'})",
                             "not stated by the model")
        out.extend(["", f"### {label} · analysed {au_date(row['created_at'])}", "",
                    f"{len(rows)} replacement{'s' if len(rows) != 1 else ''} proposed by "
                    f"`{row['tool_id']}` across {len({r['page'] for r in rows})} "
                    f"page{'s' if len({r['page'] for r in rows}) != 1 else ''} {tag}", "",
                    "| Page | Check | Current | Replacement | Provenance |",
                    "|---|---|---|---|---|"])
        for r in rows:
            try:
                path = urlsplit(r["page"]).path or "/"
            except ValueError:
                path = r["page"]
            cur = (r.get("evidence") or "").replace("|", "/").replace("\n", " ")
            rep = (r.get("replacement") or "").replace("|", "/").replace("\n", " ")
            out.append(f"| `{path}` | `{r['check']}` | {cur} | {rep} | {tag} |")
        out.append("")
    return out


#: What the report says where the plan brief ran and its document was
#: refused. Named rather than written inline because two readers need the
#: same sentence: the document, and the operator's warning beside it.
PLAN_REFUSED = ("_A client plan could not be generated for this run. "
                "The sections below are the audit's own measured findings._")


def _plan_section(conn: sqlite3.Connection, run_id: str,
                  evidence_text: str) -> tuple[str, str, str | None]:
    """The client plan as the front of the deliverable (brief v18 step AY).

    Returns (markdown, narrative, warning). `narrative` is the plan's prose
    for gate G7, for the reason `_expert_section` returns its own: the text
    the gate grounds and the text the reader sees have to be one text, or
    the caveat rule is decided in one place and checked in another.

    **Every line carrying a number is tagged or caveated, per line.** The
    plan is model-written prose about numbers the Record holds, and the
    deliverable's measured evidence is one run's deterministic findings -
    so a plan sentence quoting a count that is open across three runs is
    ungroundable here and correctly says so. That is not a defect in the
    plan; it is the difference between what the audit measured today and
    what the site still owes, and the document has to state which it is.

    Three endings, and they are not the same:
      - the plan never ran            -> nothing, and no warning
      - the plan ran and was refused  -> the refusal line, and a warning
      - the plan ran and was accepted -> the document
    """
    row = conn.execute(
        "SELECT report, contract, model_id, created_at FROM expert_reports"
        " WHERE run_id=? AND tool_id='plan'"
        " ORDER BY created_at DESC, rowid DESC LIMIT 1", (run_id,)).fetchone()
    if not row:
        return "", "", None
    contract = json.loads(row["contract"]) if row["contract"] else {}
    if not contract.get("generator"):
        reasons = "; ".join(str(d.get("reason") or "")
                            for d in (contract.get("dropped") or []))
        return PLAN_REFUSED, "", (
            "The client plan was generated and refused, so the document "
            "carries the per-part sections only"
            + (f" - {reasons}" if reasons else "") + ".")
    body = (row["report"] or "").strip()
    if not body:
        return "", "", None
    src = f"model judgement ({row['model_id']})"
    # Q-57: the plan's provenance stated once, under its heading, not on each
    # of its thirty-odd number lines. The gate reads this line as sourcing
    # the plan block beneath it up to the report's next H1/H2 heading — the
    # plan's own sub-headings are H3, so they do not close it. A line whose
    # figure this document cannot ground still carries its own [TO CONFIRM],
    # because that caveat is per claim, not per section: the plan writes about
    # the Record, which spans runs, and a count open across three runs is not
    # groundable against one run's deterministic evidence and must say so.
    out = [section_provenance(src, "not stated by the model",
                              scope="in this plan"), ""]
    narrative = []
    for line in body.splitlines():
        if ungrounded_uncaveated_lines(line, evidence_text):
            line = f"{line} {ANALYST_FIGURE_NOTE}"
        out.append(line)
        if line.strip():
            narrative.append(line.strip())
    return "\n".join(out), "\n".join(narrative), None


def _expert_section(conn: sqlite3.Connection, tool_runs: dict[str, str], site_id: str,
                    audience: str,
                    evidence_text: str | None = None) -> tuple[str, str]:
    """Specialist briefs in the deliverable. Returns (markdown, narrative).

    The most expensive analysis the suite produces previously never reached
    the document handed to the client. Findings only, severity-ordered per
    tool — the full prose reports stay in the app, because a deliverable that
    pastes nine briefs verbatim runs to fifty pages nobody reads.

    **The second return value is CQ-09, and it is a second value rather than a
    second function.** `narrative` is the model-written summaries this section
    rendered, one per line, carrying whatever caveat the row carries — the text
    `assert_report_honest` grounds against the deliverable's measured evidence.
    Deriving it by re-reading the rows from a sibling function would put the
    caveat decision in one place and the text the gate checks in another, and
    two implementations of one rule drifting apart is the most repeated defect
    in this codebase. Re-parsing it back out of the rendered table would be
    worse: the row also carries the model id, and `claude-opus-5` is a number
    to any reader that only has the line.

    `evidence_text` is what a brief's numbers are grounded against — the
    deliverable's own measured evidence, `_evidence_text` above. `None` means
    the caller is not asking the grounding question, and the caveat is decided
    by the brief's own flag alone. **`None` rather than `""`, deliberately**:
    an empty evidence set grounds nothing, so defaulting to one would caveat
    every number in every brief and call it a rule. The product always passes
    the real text; the callers that pass nothing are asking about the flag.
    """
    # Item 239 step 7 (amendment 10): each tool's newest run on the site,
    # from the Latest View, so the document lists what the part pages do.
    tools = []
    for tool_id, rid in sorted(tool_runs.items()):
        for t in runs.expert_report_index(conn, rid):
            if t["tool"] == tool_id:
                tools.append({**t, "run_id": rid})
    if not tools:
        return "", ""
    narrative: list[str] = []
    lines = ["", "", "## Specialist briefs", ""]
    ran = [t for t in tools if t["findings"] or t["worst_severity"]]
    clean = [t["tool"] for t in tools if not t["findings"]]
    # Sidebar order, not severity order (brief v18 step AY). A client
    # reading the document beside the app meets the parts in the same
    # sequence on both, and "worst first" put the same audit in a different
    # order every run — so two documents about one site could not be
    # compared by eye. Severity still decides INSIDE a part, where it is
    # the question actually being asked.
    from clauditseo import briefs as brief_catalogue
    from clauditseo.analyses import part_labels
    from clauditseo.analysts.expert import EXPERT_TOOLS
    from clauditseo.checks import check_cost

    catalogue = brief_catalogue.by_id()
    labels = part_labels()
    from clauditseo.persistence.runs import awaiting_confirmation
    awaiting = awaiting_confirmation(conn, site_id)
    for tool in sorted(ran, key=lambda t: (
            catalogue[t["tool"]].order if t["tool"] in catalogue else 10_000,
            t["tool"])):
        rows = [r for r in conn.execute(
            "SELECT check_id, severity, summary, affected_urls, model_id,"
            " confidence, evidence, fingerprint FROM findings"
            " WHERE run_id=? AND dimension=?"
            " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
            " WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END",
            (tool["run_id"], f"EXP:{tool['tool']}")).fetchall()
            # Item 237: an analysis finding no sweep can raise reaches the
            # client only once the operator has confirmed it.
            if r["fingerprint"] not in awaiting]
        if not rows:
            continue
        part = labels.get(catalogue[tool["tool"]].part) if tool["tool"] in catalogue else None
        when = conn.execute("SELECT MAX(created_at) FROM expert_reports WHERE run_id=?"
                            " AND tool_id=?", (tool["run_id"], tool["tool"])).fetchone()[0]
        dated = f" · analysed {au_date(when)}" if when else ""
        lines.append(f"### {part} — {tool['tool']}{dated}" if part
                     else f"### {tool['tool']}{dated}")
        lines.append("")
        # Read once per tool, not once per row: every finding under this
        # heading came from this one brief, so they are judged against the
        # same flagged list. It is the capped one — see `figure_is_unverified`
        # for why that makes the fallback below a floor.
        declared = runs.expert_report_figures(conn, tool["run_id"], tool["tool"])
        # Free checks, then Analysis (brief v17 step AV3, reaching the
        # deliverable at brief v18 step AY). The heading is the point of the
        # split and not decoration: "here is what we found for nothing" is
        # the first half of every conversation about an audit, and one table
        # mixing the two answers a question the client has not been allowed
        # to ask yet. A group with nothing in it is omitted rather than
        # printed empty — the part page states a clean section in one line,
        # and a document is not a screen.
        grouped: dict[str, list] = {"free": [], "model": []}
        # Cost by the check's FULL id, not the bare one a contract row stores.
        # `check_costs()` keys a registered check by `CNT/gap`, so `check_cost`
        # on the bare `gap` reads free and a content analysis row was filed
        # under "Free checks" — the split inverted for exactly the rows Q-56
        # moved here. The brief's header lists its checks by full id, so that
        # is the qualifier; a code the brief did not declare falls back to the
        # bare id, its old behaviour.
        full_of = {c.split("/")[-1]: c
                   for c in EXPERT_TOOLS.get(tool["tool"], {}).get("checks", [])}
        for r in rows:
            grouped[check_cost(full_of.get(r["check_id"], r["check_id"]))].append(r)
        for cost, heading in (("free", "Free checks"), ("model", "Analysis")):
            if not grouped[cost]:
                continue
            # The count is measured — it is the length of the table under
            # it — so it carries the engine's tag like every other number
            # in the document. G7 caught this the first time the heading
            # was written without one, which is the gate doing exactly
            # what it is for.
            n = len(grouped[cost])
            lines.append(f"**{heading}** — {n} row{'s' if n != 1 else ''} "
                         f"({provenance_tag()})")
            lines.append("")
            _brief_table(lines, narrative, grouped[cost], tool, declared,
                         evidence_text)
            lines.append("")
    lines.extend(_contract_sections(conn, tool_runs))
    if clean:
        lines.append("Briefs run with nothing to raise: "
                     + ", ".join(f"`{t}`" for t in sorted(clean)) + ".")
        lines.append("")
    if audience == "internal":
        counts: dict[str, int] = {}
        for row in conn.execute(
                "SELECT state, COUNT(*) n FROM finding_states WHERE site_id=?"
                " GROUP BY state", (site_id,)):
            counts[row["state"]] = row["n"]
        if counts:
            # Counted from the state table, and every count is a number on a
            # line — the same rule that blocked the rows above blocked this
            # sentence, so the internal deliverable stayed ungeneratable after
            # the table was tagged. One tag at the end, as the shared-cause
            # sentence does, keeps it readable.
            lines.append("Finding memory for this site: "
                         + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
                         + ". Candidates are model findings seen once, not yet "
                           "confirmed by a second run "
                           f"({provenance_tag('finding memory')}).")
            lines.append("")
    return "\n".join(lines), "\n".join(narrative)


def _brief_table(lines: list[str], narrative: list[str], rows, tool: dict,
                 declared, evidence_text: str | None) -> None:
    """One cost group's table for one brief, appended in place.

    Split out of `_expert_section` by brief v18 step AY, which gives each
    part two headings. The caveat decision, the provenance tag and the
    narrative the gate grounds are one piece of code with one behaviour, and
    a copy per heading is how the two groups would come to caveat differently.

    Q-57: the provenance is hoisted. Every row in a brief is model judgement,
    so the same tag stood in every row's last cell; it is now stated once
    under the heading and the cell is dropped where a row shares it. A row
    whose provenance differs — a confidence the model actually stated, beside
    rows where it did not — still carries its own tag, in a Provenance column
    that appears only when a group is mixed. The `[TO CONFIRM]` note is per
    claim and untouched.
    """
    # First pass: each row's rendered summary (with the note where the figure
    # is unverified or ungroundable here) and its provenance pair. Computed
    # before anything is emitted, because the section tag is the group's
    # common provenance and the header shape depends on whether all rows share
    # it — both of which need every row's pair in hand.
    prepared = []
    for r in rows:
        summary = (r["summary"] or "").replace("|", "/")
        src = f"model judgement ({r['model_id'] or tool['model']})"
        # The stored 'medium' is a placeholder: a brief's index block has
        # no confidence column, so record_expert_findings stamps one and
        # records confidence_stated=False to say it did. Printing the
        # placeholder into a client's document presents an invented signal
        # as the model's own judgement.
        ev = json.loads(r["evidence"] or "{}")
        conf = (r["confidence"] if ev.get("confidence_stated") is not False
                else "not stated by the model")
        # `figure_is_unverified` owns the "judged and grounded" vs "recorded
        # before the judgement existed" distinction; this must not
        # re-implement it. The second clause asks whether THIS document can
        # ground the number — a different question, the one the gate holds the
        # rendered row to. Either is enough for the same note; `or`
        # short-circuits so a declared figure never pays for the second check.
        if (runs.figure_is_unverified(ev, r["summary"] or "", declared)
                or (evidence_text is not None
                    and ungrounded_uncaveated_lines(r["summary"] or "",
                                                    evidence_text))):
            summary = f"{summary} {ANALYST_FIGURE_NOTE}"
        prepared.append((r, summary, src, conf))

    # The group's provenance is its most common (src, conf). One tag under the
    # heading states it; the gate reads that line as sourcing the rows beneath
    # it, up to the report's next H1/H2 heading.
    from collections import Counter
    counts = Counter((src, conf) for _, _, src, conf in prepared)
    sec_src, sec_conf = counts.most_common(1)[0][0]
    mixed = len(counts) > 1
    lines.append(section_provenance(sec_src, sec_conf,
                                    scope="in the rows below"))
    lines.append("")
    if mixed:
        lines.append("| Severity | Issue | Summary | Provenance |")
        lines.append("|---|---|---|---|")
    else:
        lines.append("| Severity | Issue | Summary |")
        lines.append("|---|---|---|")
    for r, summary, src, conf in prepared:
        row = f"| {r['severity']} | `{r['check_id']}` | {summary} "
        if mixed:
            # Its own tag only where it differs from the section's; the
            # matching rows are sourced by the hoisted line and leave the
            # cell blank.
            cell = ("" if (src, conf) == (sec_src, sec_conf)
                    else provenance_tag(src, conf))
            row += f"| {cell} "
        lines.append(row + "|")
        # The gate's text, taken here rather than parsed back out of the line
        # above: one newline per finding, the caveat rule being per line.
        narrative.append(summary.replace("\n", " "))
    lines.append("")


def generate(conn: sqlite3.Connection, template: str, audience: str,
             run_ids: list[str], out_dir: Path | None = None,
             supersedes: str | None = None) -> dict:
    """Render, check and store a deliverable. Returns its id, path and text.

    `supersedes` names the stored deliverable this one replaces, and is what
    the Deliverables screen's `regenerate` control passes. `QUESTIONS.md` Q-9,
    answered **supersede** on 23 August 2026: a regeneration is a new document
    that records which one it replaced, never an edit of the old row and never
    a deletion of it. The old row stays listed and readable because it is the
    artefact a client was actually sent; what changes is that the screen stops
    asking for it to be regenerated again, and the register can say which
    document replaced which. See `0028_report_supersedes.sql` for the two
    answers not taken.

    Left `None` by every other caller, which is the honest value: a document
    written from scratch replaces nothing.

    `out_dir` defaults to `OUT_DIR`, the operator's own output directory. A
    caller writing a throwaway document — a seeding script pointed at a
    scratch database, a test — passes its own path, because a module-level
    constant meant every such run wrote into the directory holding real
    deliverables. Cleaning up after one then meant globbing a directory with
    live files in it, which destroyed the operator's stored deliverables
    twice.

    The path is stored on the `reports` row, so out_dir also decides where a
    document can be found later: point it at a temp directory only when the
    database is temporary too, or the row will outlive the file it names.
    """
    if template not in TEMPLATES:
        raise ValueError(f"template must be one of {TEMPLATES}")
    if audience not in AUDIENCES:
        raise ValueError(f"audience must be one of {AUDIENCES}")

    run_dicts = []
    for run_id in run_ids:
        run = runs.get_run(conn, run_id)
        if not run:
            raise ValueError(f"run {run_id} not found")
        # A blocked run has findings worth reading on screen and nothing worth
        # sending: the document would lead with a composite for a site that was
        # never retrieved, and a deliverable is the artefact that leaves the
        # building. Refusing is cheaper to explain than a caveat a client reads
        # past.
        #
        # Here rather than in the API route, which is where it started. The
        # route is one of three callers — `cli.py report` and
        # `scripts/seed_dev_data.py` are the others — so a rule enforced there
        # is a rule two paths walk past, and the CLI produced the exact
        # artefact the API refused. A ValueError because that is what this
        # function already raises for a request it cannot honour, and the
        # route already maps it to 422.
        #
        # `client` only, which every sentence above was already about — WF-05,
        # carried twelve rounds. Sending and leaving the building are the whole
        # of the reasoning, and neither reaches the internal audience: that
        # document is the operator's own reading copy. Unconditional, the rule
        # meant the one run most needing a written account was the only run
        # that could not produce one, including the account of why it was
        # blocked. Three such runs are stored on the live service, and
        # `test_the_document_states_what_the_crawl_fetched` had to call
        # `render_run_report` directly to render exactly this document.
        #
        # The composite the refusal protects against is not shipped by
        # allowing this: `render_run_report` already states a blocked crawl as
        # its own scope limit ("0 pages fetched"), and RENDERER_VERSION 1.16.0
        # is the entry recording that a blocked run reports its own cause.
        if audience == "client" and run["status"] == "blocked":
            raise ValueError(
                f"Run {run_id[:8]} fetched no pages — the crawl was blocked, "
                "so there is nothing to report on. Re-run the audit once the "
                "site allows crawling.")
        # Brief v23 step BL's integrity line, and here for the reason the
        # blocked refusal above is: three callers, and a rule enforced at one
        # of them is a rule the other two walk past. A threshold, not a
        # gradient - no Critical or High finding may be unassessed when a
        # client report is generated. `client` only: the internal document is
        # the operator's reading copy, and is how they do the assessing.
        if audience == "client":
            hold = runs.client_report_hold(conn, run["site_id"])
            if hold:
                raise ValueError(hold)
        run_dicts.append(run)
    site = repo.get_site(conn, run_dicts[0]["site_id"])
    # Checked here rather than only at the route, for the reason the
    # blocked-run refusal above is: this function has three callers and a rule
    # enforced at one of them is a rule the other two walk past. A row on
    # another site would put a "replaced by" link on one client's register
    # pointing at another client's document, which is worse than the
    # duplicate it was meant to fix.
    if supersedes is not None:
        replaced = conn.execute("SELECT site_id FROM reports WHERE id=?",
                                (supersedes,)).fetchone()
        if not replaced:
            raise ValueError(f"report {supersedes[:8]} not found, so this "
                             "document cannot say it replaced one")
        if replaced["site_id"] != site["id"]:
            raise ValueError(
                f"report {supersedes[:8]} belongs to another site — a "
                "deliverable can only supersede one for the same client")
    #: Things the operator should know about the document that was just made,
    #: rather than reasons not to make it. Returned alongside it so they are
    #: read at the moment they apply.
    warnings: list[str] = []
    # Once, here, because `_expert_section` now grounds against it as well as
    # the gate below — and two calls could not disagree today but would be two
    # places to change the day `_evidence_text` takes an argument.
    evidence_text = _evidence_text(run_dicts)
    # Only the `run` template has a brief section; the other two leave this
    # empty, which is the same thing as having nothing to ground.
    brief_narrative = ""

    if template in RUN_TEMPLATES:
        # Brief v17 step AV6: the free half alone. Nothing about the audit
        # changes - the scores, the findings and the accessibility section
        # are what the sweep measured either way; what is dropped is the
        # two sections a model wrote.
        free_only = template == "run-free"
        # Item 239 step 7: the document is a frozen copy of the Latest View.
        # Its score is the current audit's composite; its findings are the
        # ledger's open ones, each dated by the run that last measured it;
        # its analyses are each tool's newest run. The request's run names
        # the site, not the content.
        copy = latest_view.frozen_copy(conn, site["id"])
        # No current composite: the document says so (NO_COMPOSITE), framed
        # by the audit it was asked for, and claims no score from it.
        score_run = (runs.get_run(conn, copy["composite"]["run_id"]) if copy["composite"]
                     else {**run_dicts[0], "composite_score": None})
        view_run = {**score_run, "findings": runs.ledger_findings(conn, site["id"])
                    + runs.analyst_insights(conn, site["id"])}
        tool_runs = tool_runs_for(conn, site["id"])
        evidence_text = _evidence_text([view_run])
        # Computed by the same function the client screen reads, so the
        # report and the screen cannot quote different numbers.
        view = runs.anatomy_view(conn, site["id"])
        cause = view.get("shared_cause")
        if cause:
            cause = {**cause, "grand_total": view["total"]}
        from clauditseo import brand as branding
        mark = dict(branding.get(conn))
        # Said when it matters, not on a settings screen the operator has no
        # reason to open. The document is about to go to a client under the
        # supplier's name — which is a decision, not an error, so this warns
        # and still produces the report.
        if audience == "client" and not mark.get("name_is_set"):
            warnings.append(
                f"This report carries the product name, {mark['name']}, "
                "because no operator name is set. Set one under Branding on "
                "Admin if it should go out under your own.")
        # The document references the logo as a sibling file. An absolute
        # path renders only on the machine that made it, and it would put the
        # operator's home directory into a client's document.
        if mark.get("logo_path"):
            mark["logo_file"] = Path(mark["logo_path"]).name
        # The plan is model-written like the two sections below it, so
        # `run-free` drops it for the reason it drops those: the free
        # document is what the audit answered without spending anything,
        # and a client holding both has to be able to tell them apart.
        front, plan_narrative, plan_warning = ("", "", None)
        if not free_only:
            front, plan_narrative, plan_warning = _plan_section(
                conn, (copy["analyses"].get("plan") or {}).get("run_id"), evidence_text)
            if plan_warning:
                warnings.append(plan_warning)
        # The sweep's own record of what it requested, for the disclosure line
        # (143 addendum). Not a `get_run` column: that shape is guarded.
        view_run["well_known"] = runs.run_well_known(conn, view_run["id"])
        markdown, narrative = render_run_report(site, view_run, audience,
                                                shared_cause=cause,
                                                brand=mark, free_only=free_only,
                                                front=front, as_of=copy)
        if not free_only:
            section, brief_narrative = _expert_section(
                conn, tool_runs, site["id"], audience,
                evidence_text=evidence_text)
            markdown += section
            # One text for the gate, because the plan's prose is judged by
            # exactly the rule the briefs' prose is: a number in it is
            # grounded in the deliverable's measured evidence or it is
            # caveated on its own line.
            brief_narrative = "\n".join(x for x in (brief_narrative, plan_narrative) if x)
    elif template == "comparison":
        if len(run_dicts) != 2:
            raise ValueError("comparison needs exactly two run ids (baseline, current)")
        diff = runs.compare_runs(conn, run_dicts[0]["id"], run_dicts[1]["id"])
        markdown, narrative = render_comparison_report(site, run_dicts[0], run_dicts[1],
                                                       diff, audience)
    else:
        trend = runs.site_trend(conn, site["id"])
        # The two arguments below are printed on the same page of a client's
        # document — "Completed runs on record: N" above the trend table — and
        # only audits write to `site_trend`. Executed against the live
        # database before this line changed, for `www.acme.com.au`: the
        # sentence said 5 and the table had 4 rows.
        all_runs = runs.site_readings(conn, site["id"])
        markdown, narrative = render_trend_report(site, trend, all_runs, audience)

    # A client reading a document has no disclosure to open, so the client
    # document carries the registry's definitions of the terms it uses and no
    # others (item 166). Before the gate, so the gate reads what is sent.
    if audience == "client":
        from clauditseo import glossary
        markdown += glossary.appendix(markdown)

    # Gate G7's three checks run on every generation, not just in tests. The
    # third is CQ-09: the specialist briefs are model-written prose and were
    # the one text neither of the other two ever grounded.
    assert_report_honest(markdown, narrative, evidence_text,
                         brief_narrative=brief_narrative)

    out = Path(out_dir) if out_dir is not None else OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    report_id = repo.create_id()
    # CQ-124, carried from report 061 to 073: one timestamp, read once. The
    # filename used to come from `date.today()` — the operator's local date —
    # and the row from `repo.now_iso()`, which is UTC, two lines apart. For an
    # en-AU operator that is UTC+10, so every generation between midnight and
    # 10am local produced a document whose name and whose register row named
    # different days, with no zone on either. The nine orphaned comparison
    # documents in the live `reports/out` are exactly that: named
    # `…-2026-08-17-…` with an mtime of `2026-08-16T22:27Z`.
    #
    # The register's frame wins, because every row already written is UTC and
    # the screen sorts and labels from the row. The filename now states the
    # register's day rather than a second opinion about it.
    created_at = repo.now_iso()
    # What the document was built over, written down now because it cannot be
    # read back later (item 170, channel ruling 20260917-0250): `finding_states`
    # keeps one current row per fingerprint and no history. The same rule the
    # refusal above enforces - unassessed is state `open` on the run's
    # fingerprints - so the stored figures and the live integrity line cannot
    # mean different things. The document's current run is the last named: the
    # only one for a run report, `(baseline, current)` for a comparison.
    described = run_dicts[-1]
    # Item 239 step 7: the hold's own count - the site's open Critical and
    # High, in the copy a run report was built from.
    at_generation_severe = (copy["hold"] if template in RUN_TEMPLATES
                            else runs.open_severe(conn, site["id"]))["count"]
    at_generation = runs.run_assessed(conn, described["id"], described["site_id"])
    from clauditseo.crawler.crawl import site_host
    slug = "".join(c if c.isalnum() else "-"
                   for c in site_host(site["domain"])).strip("-")
    path = out / (f"{slug}-{template}-{audience}-"
                  f"{created_at[:10]}-{report_id[:8]}.md")
    from clauditseo.reporting.render import RENDERER_VERSION
    # WF-75: the file and the row are one fact. The write is INSIDE the
    # transaction and after the insert, which is the only ordering that makes
    # both failure directions safe — sqlite rolls back the row but cannot roll
    # back a filesystem write, so the unrollbackable half goes last and inside.
    # An insert that raises happens before any file exists; a write that raises
    # aborts the transaction and takes the row with it. Written the other way
    # round for the product's whole life, which is how `reports/out` came to
    # hold 35 documents against 13 rows.
    with conn:
        conn.execute(
            "INSERT INTO reports (id, site_id, run_ids, template, audience, path,"
            " created_at, renderer_version, supersedes,"
            " unassessed_severe, unassessed_total, assessed_pct, latest_view_copy)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (report_id, site["id"], json.dumps(run_ids), template, audience,
             str(path), created_at, RENDERER_VERSION, supersedes,
             at_generation_severe,
             at_generation["total"] - at_generation["assessed"],
             at_generation["pct"],
             json.dumps(copy, default=str) if template in RUN_TEMPLATES else None))
        path.write_text(markdown, encoding="utf-8")
    # The image goes next to the document, so the pair survives being zipped
    # or emailed as a folder. Deliberately OUTSIDE the transaction above: a
    # missing or unreadable logo must not orphan a document that is otherwise
    # complete, and the pair is a convenience rather than part of the record.
    from clauditseo import brand as _branding
    _branding.copy_logo_beside(conn, path)

    pdf_path = _maybe_pdf(markdown, path)
    return {"id": report_id, "path": str(path), "pdf_path": pdf_path,
            "markdown": markdown, "warnings": warnings}


#: `{slug}-{template}-{audience}-{YYYY-MM-DD}-{id8}.md`, which is the name
#: `generate()` builds above. `.+` is greedy and backtracks onto the template
#: alternation, so a slug containing hyphens (`www-acme-com-au`) and a
#: template containing one (`monthly-trend`) are both parsed correctly.
#: `run-free` is listed before `run` for the reader rather than for the
#: engine - the alternation backtracks either way - so that the longer name
#: is not read as the shorter one plus a stray word.
_DOCUMENT_NAME = re.compile(
    r"^(?P<slug>.+)-(?P<template>run-free|run|comparison|monthly-trend)"
    r"-(?P<audience>client|internal)-(?P<date>\d{4}-\d{2}-\d{2})"
    r"-(?P<id8>[0-9a-f]{8})$")

#: A run id as the documents themselves print it. Comparison documents open
#: "Baseline run `<id>` versus current run `<id>`"; every id found anywhere in
#: a document is checked against `audit_runs` for that site before it is used,
#: so a hex string that is not a run of that site is discarded rather than
#: trusted. That check is what stops this reading its own answer.
_RUN_ID = re.compile(r"`([0-9a-f]{32})`")


def adopt_orphans(conn: sqlite3.Connection, out_dir: Path | None = None,
                  dry_run: bool = False) -> dict:
    """Reconcile `reports/out` against the `reports` table. One-shot, idempotent.

    WF-75. Until the change above, `generate()` wrote the document before and
    outside the transaction that recorded it, so anything interrupting the
    insert left a file the product could never see again. Measured on the
    operator's own instance on 21 August 2026: 35 documents on disk, 13 rows,
    and 9 of the 22 orphans are client-facing comparison documents for a live
    client. Fixing the write forward does nothing for those 22; this does.

    **Run ids come from the document's text, not from its name.** Report 073's
    remedy proposed parsing the filename, and a filename cannot yield
    `run_ids` — which is `NOT NULL`, and is what `site_client_reports` reads
    to compute the Deliverables screen's "Still current?" column. A row
    adopted with `run_ids=[]` renders there as "audit no longer in history",
    which is a false reason rather than an absent one. The body carries the
    real ids and they are validated against `audit_runs` before use.

    **A document that cannot be adopted is returned, never passed over.** The
    13 `fixture-test-*` documents in the live directory belong to no site in
    `sites` and must not gain rows; silence about them is the same failure
    that produced the 22 in the first place.

    **Not wired into startup**, though report 073 suggested it. A pass that
    writes rows on every boot is a mutation nobody asked for, and under test
    each process's own redirected `OUT_DIR` would be adopted into its own
    database. It is a script the operator runs — `scripts/adopt_reports.py` —
    and its result is read from the `reports` table, not from its own output.

    **`dry_run` is a parameter here and not a caller's `BEGIN`/`rollback`,
    because that dead end was walked and measured.** `scripts/adopt_reports.py`
    first implemented `--dry-run` as "open a transaction, call this, roll
    back", on the reasoning that one code path cannot disagree with itself.
    It cannot work: the `with conn:` below commits, so the outer transaction
    is closed by the first adoption and the rollback has nothing left to
    undo. Run against the operator's database on 21 August 2026 it printed
    "dry run — nothing written" and wrote all nine rows; `SELECT COUNT(1) FROM
    reports` read 22 immediately after. The flag gates the insert alone —
    every parse, resolution and validation above still runs, so the report a
    dry run prints is produced by the same code that would do the work.

    Returns `{"adopted": [...], "skipped": [{"path", "reason"}, ...]}`.
    """
    from clauditseo.crawler.crawl import site_host

    out = Path(out_dir) if out_dir is not None else OUT_DIR
    if not out.is_dir():
        return {"adopted": [], "skipped": []}

    known = {str(row["path"]) for row in conn.execute("SELECT path FROM reports")}
    by_slug: dict[str, str] = {}
    for row in conn.execute("SELECT id, domain FROM sites"):
        slug = "".join(c if c.isalnum() else "-"
                       for c in site_host(row["domain"])).strip("-")
        by_slug[slug] = row["id"]

    adopted: list[dict] = []
    skipped: list[dict] = []
    for path in sorted(out.glob("*.md")):
        if str(path) in known:
            continue
        name = _DOCUMENT_NAME.match(path.stem)
        if not name:
            skipped.append({"path": str(path),
                            "reason": "filename is not a deliverable name"})
            continue
        site_id = by_slug.get(name["slug"])
        if site_id is None:
            skipped.append({"path": str(path),
                            "reason": f"no site in this database has host "
                                      f"{name['slug']!r}"})
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        seen: list[str] = []
        for candidate in _RUN_ID.findall(text):
            if candidate in seen:
                continue
            owned = conn.execute(
                "SELECT 1 FROM audit_runs WHERE id=? AND site_id=?",
                (candidate, site_id)).fetchone()
            if owned:
                seen.append(candidate)
        if not seen:
            # Deliberately a skip rather than an empty-`run_ids` adoption. A
            # `run` document does not print its own run id, so this is the
            # expected outcome for that template until the renderer states it;
            # recording the reason is what makes that visible rather than
            # looking like the directory was clean.
            skipped.append({"path": str(path),
                            "reason": "the document names no run this site owns, "
                                      "so its register row would have no provenance"})
            continue

        # The filename's own 8 hex are kept as the row id's prefix, because
        # `generate()` derives the name from `report_id[:8]` and a reader
        # comparing the two would otherwise see a mismatch this pass invented.
        report_id = name["id8"] + repo.create_id()[8:]
        # The file's mtime, in the register's frame. Not the filename's date:
        # that is local (CQ-124) and every other row in this table is UTC, so
        # adopting from the name would put nine permanently mis-framed rows
        # into a client-facing register. The two are the same instant — the
        # nine live orphans are named 2026-08-17 and have an mtime of
        # 2026-08-16T22:27Z, which is 08:27 on the 17th at UTC+10.
        created_at = datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        # `renderer_version` is left NULL on purpose: nothing on disk records
        # which renderer wrote the document, and the screen already has a
        # third state for exactly that — "predates renderer tracking". Guessing
        # the current version would call a superseded document current.
        if not dry_run:
            with conn:
                conn.execute(
                    "INSERT INTO reports (id, site_id, run_ids, template, audience,"
                    " path, created_at, renderer_version)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                    (report_id, site_id, json.dumps(seen), name["template"],
                     name["audience"], str(path), created_at))
        adopted.append({"id": report_id, "path": str(path), "run_ids": seen,
                        "template": name["template"], "audience": name["audience"],
                        "created_at": created_at})

    return {"adopted": adopted, "skipped": skipped}


def _maybe_pdf(markdown: str, md_path: Path) -> str | None:
    """PDF is optional: rendered only when weasyprint (and its GTK deps on
    Windows) happen to be installed. Absence is normal, never an error."""
    try:
        import weasyprint  # type: ignore
    except Exception:
        return None
    try:
        html = "<pre style='font-family: sans-serif; white-space: pre-wrap'>" \
               + markdown.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
        pdf_path = md_path.with_suffix(".pdf")
        weasyprint.HTML(string=html).write_pdf(str(pdf_path))
        return str(pdf_path)
    except Exception:
        return None
