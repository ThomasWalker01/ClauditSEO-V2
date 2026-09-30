"""One state model for "an analysis you can run against an audit".

The problem this exists to end: a single concept had four states — never run,
running, has a report, needs input — and the dashboard used eight verbs for
it across five screens (`run`, `run all`, `run most`, `re-run`, `show`,
`hide`, `open`, `investigate`). Nothing shared computed it, so Tools, the
workbench, the run page and the client screen each invented their own answer
and could disagree about what the same tool was doing. One of those
disagreements cost money: a control labelled to read a stored report in fact
re-ran it.

So the states, the type, and the price are decided here, once, server-side,
and every screen renders what it is given.

The two axes are separate on purpose:

  STATE  what is true of this analysis right now, for this audit
  TYPE   what kind of thing it is, which does not change

Type matters because the kinds genuinely behave differently, and each
difference is one an operator gets caught by:

  triage   produces no findings about the site at all — it reads the
           scoreboard and returns a ranking. It is the only kind whose
           output goes stale when a newer audit lands, so it is the only
           kind that carries a staleness warning.
  page     cannot run until a page is chosen, which is why a bare "run"
           control on one of these did nothing useful.
  report   assembles what has already run rather than analysing anything;
           running it first is legal and produces a thin deliverable.
  monitor  is worth running repeatedly or not at all; one run says little.
  site     the ordinary case — reads the whole stored crawl.
"""

from __future__ import annotations

from clauditseo import anatomy
from clauditseo import briefs as brief_catalogue
from clauditseo.playbook import PLAYBOOK

#: State names. Ordered by how an operator reads them, not alphabetically.
READY = "ready"          # a stored report exists for this audit — free to open
RUNNING = "running"      # executing right now
NEEDS_INPUT = "needs_input"   # blocked on context a crawl cannot supply
NOT_RUN = "not_run"      # never run against this audit

#: One verb per state. The whole point: a screen renders this, it does not
#: choose its own word.
VERB = {READY: "read", RUNNING: "stop", NEEDS_INPUT: "supply", NOT_RUN: "run"}

#: Tools whose type is not simply their playbook `kind`. Declared rather than
#: inferred from the id, so renaming a tool cannot silently reclassify it.
TYPE_OVERRIDE = {
    "triage": "triage",
    "prioritisation": "triage",
    "reporting": "report",
    "regression-monitoring": "monitor",
    "measurement-validation": "monitor",
}

TYPE_LABEL = {
    "triage": "Decides what to run next",
    "site": "Analyses the whole site",
    "page": "Analyses one page",
    "report": "Client deliverable",
    "monitor": "Watches for change",
}


def type_of(tool_id: str, kind: str) -> str:
    """Marker type for a tool. `kind` is the playbook's invocation kind; a
    brief's is its header's scope (brief v10 step AD), which is where the
    catalogue listed `onpage-hygiene` as `site` while its prompt said "a
    single web page"."""
    if tool_id in TYPE_OVERRIDE:
        return TYPE_OVERRIDE[tool_id]
    brief = brief_catalogue.by_id().get(tool_id)
    if brief is not None:
        return brief.scope
    return "page" if kind == "page" else "site"


def _catalogue() -> dict[str, dict]:
    """Every runnable tool, keyed by the id its brief is stored under.

    A tool may carry its brief under another id — the mobile sweep's is
    `mobile-viewport` — and keying on the wrong one hid briefs entirely from
    a menu once already.
    """
    out: dict[str, dict] = {}
    for phase in PLAYBOOK:
        for tool in phase["tools"]:
            if tool["status"] == "planned":
                continue
            brief_id = tool.get("expert", tool["id"])
            brief = brief_catalogue.by_id().get(brief_id)
            out[brief_id] = {
                "tool": brief_id,
                # The header's name where there is one (brief v10 step AD):
                # the playbook's is the tool's, the header's is the brief's.
                "name": brief.name if brief else tool["name"],
                "phase": phase["phase"],
                "kind": tool["kind"], "does": tool.get("does", ""),
                "type": type_of(brief_id, tool["kind"]),
                "part": brief.part if brief else None,
                "part_label": part_labels().get(brief.part) if brief else None,
                "order": brief.order if brief else None,
            }
    return out


def part_labels() -> dict[str, str]:
    return {c.key: c.label for c in anatomy.CATEGORIES}


def tool_status() -> dict[str, str]:
    """Playbook status per tool id: ready | needs_key | planned.

    Read rather than inferred. A first cut classified anything left over in a
    section's tool list as a sweep, which put "link-gap runs in every audit"
    on screen — link-gap is not built. The playbook already knows; nothing
    else should be guessing.
    """
    out = {}
    for phase in PLAYBOOK:
        for t in phase["tools"]:
            out[t["id"]] = t["status"]
            # A tool whose brief is stored under another id - the mobile
            # sweep's is `mobile-viewport` - answers to that id too, since
            # the anatomy files the brief under its part by the brief's id
            # (brief v10 step AD).
            if t.get("expert"):
                out.setdefault(t["expert"], t["status"])
    return out


#: How a brief's tokens split between what it reads and what it writes, for
#: pricing an estimate at a model that has not run it yet (brief v4 Item
#: 3f). A brief's prompt carries the crawl evidence and its answer is a
#: report of a few thousand tokens, so the split is input-heavy; the stored
#: history keeps one token count, not two, and this is the assumption the
#: total is priced under. Said here once, and beside the figure on screen.
INPUT_SHARE = 0.9


def cost_at(tokens: int | float | None, price: tuple[float, float] | None) -> float | None:
    """USD for `tokens` at a model priced `(input_usd, output_usd)` per
    million, under `INPUT_SHARE`; None where either is unknown."""
    if not tokens or not price:
        return None
    inp, out = price
    return round(tokens * (INPUT_SHARE * inp + (1 - INPUT_SHARE) * out) / 1_000_000, 4)


def lanes(stored: dict[str, dict], estimates: dict[str, dict],
          in_flight: set[str], briefs: dict[str, dict]) -> dict:
    """Split every analysis into what is free to read and what would spend.

    `stored` is what has run against this audit, `estimates` the measured
    price of each, `in_flight` what is executing, `briefs` the expert
    metadata (scope, inputs) from the analyst layer.

    Free and paid are separated because that is the distinction an operator
    most needs and the one the old layout hid: a control that read a stored
    report looked exactly like one that would buy a new one.
    """
    catalogue = _catalogue()
    ready, available = [], []

    # The sidebar's order (brief v10 step AD): group, then part, then name;
    # tools with no brief after them, by id.
    def _order(item):
        meta = item[1]
        return (meta.get("order") is None, meta.get("order") or 0, item[0])

    for tool_id, meta in sorted(catalogue.items(), key=_order):
        brief = briefs.get(tool_id)
        if brief is None:
            continue                      # no written brief: not runnable here
        est = estimates.get(tool_id) or {}
        row = {
            **meta,
            "est_tokens": est.get("tokens"), "est_cost": est.get("cost"),
            "est_seconds": est.get("seconds"),
            "inputs": brief.get("inputs") or [],
            "scope": brief.get("scope"), "tier": brief.get("tier"),
        }
        record = stored.get(tool_id)
        if tool_id in in_flight:
            row.update(state=RUNNING, verb=VERB[RUNNING])
            available.append(row)
        elif record and record.get("contract_status") == "needs-input":
            # The brief asked instead of answering (brief v10 step AF): not
            # read, and the questions are what the operator sees.
            row.update(state=NEEDS_INPUT, verb=VERB[NEEDS_INPUT],
                       ran_at=record.get("created_at"),
                       questions=record.get("questions") or [],
                       tokens=record.get("tokens"), cost=record.get("cost"))
            available.append(row)
        elif record:
            row.update(state=READY, verb=VERB[READY],
                       ran_at=record.get("created_at"),
                       findings=record.get("findings"),
                       tokens=record.get("tokens"), cost=record.get("cost"),
                       worst=record.get("worst_severity"),
                       truncated=record.get("truncated"))
            ready.append(row)
        elif any(i.get("required") for i in row["inputs"]):
            row.update(state=NEEDS_INPUT, verb=VERB[NEEDS_INPUT])
            available.append(row)
        else:
            row.update(state=NOT_RUN, verb=VERB[NOT_RUN])
            available.append(row)

    # Ready newest first — the thing just run is the thing being looked for.
    ready.sort(key=lambda r: r.get("ran_at") or "", reverse=True)
    # Two different unknowns, and conflating them produced a sentence that
    # contradicted itself: "~1004k tokens for all 16 · 16 never run here, so
    # not in that figure". Tokens were known for all sixteen; only the dollar
    # rate was missing. `unestimated` counts what has no measurement AT ALL.
    priced = [r["est_cost"] for r in available if r.get("est_cost") is not None]
    return {
        "ready": ready,
        "available": available,
        # The sidebar's parts in order, each with the briefs filed under it
        # - including the parts no brief writes to, which the drawer shows
        # as a header reading "no brief yet" (brief v10 step AD).
        "parts": brief_catalogue.parts(),
        "outstanding_cost": round(sum(priced), 4) if priced else None,
        "outstanding_tokens": sum(r.get("est_tokens") or 0 for r in available),
        "unestimated": sum(1 for r in available if r.get("est_tokens") is None),
        "no_dollar_rate": sum(1 for r in available
                              if r.get("est_tokens") is not None
                              and r.get("est_cost") is None),
    }


#: The order a rank is read in, worst first. `runs.SEVERITY_ORDER` is the
#: same tuple; it is imported at call time rather than at module scope
#: because `persistence.runs` imports this module's neighbours and a
#: top-level import here closes the cycle.
_SEVERITY = ("critical", "high", "medium", "low", "info")


def _sev_rank(value: str | None) -> int:
    """Where a severity sits, with anything unrecognised ranked last.

    One function because there are two readers - the aggregation that picks
    the worst severity a check carries, and the sort - and the first version
    had the guard in the sort only. A finding whose severity the tuple does
    not name (the record has carried `held`) then raised ValueError out of
    `/lanes`, and every screen that loads lanes failed with it: 169 errors and
    192 failures, in blocks the size of whole files.

    Unrecognised ranks LAST rather than raising: a rank is an ordering, and
    an ordering that refuses to order something is worse than one that puts
    the unknown thing at the end.
    """
    try:
        return _SEVERITY.index((value or "").lower())
    except ValueError:
        return len(_SEVERITY)


def audit_ranking(findings: list[dict], ran_at: str | None, from_run: str | None,
                  runnable: set[str] | None = None,
                  already: set[str] | None = None) -> dict:
    """The ranking the audit produces itself, from its own findings.

    Item 196, the operator's decision (b). What stood here was a `fast`-tier
    model call whose own ROLE said "You buy nothing, find nothing new" - it
    sorted rows the sweep and the briefs had already produced. It was a
    purchase, it was a numbered step between Audit and Analyses, it went
    stale the moment a newer audit landed, and it invited a re-run to make
    the sections agree again. The operator's words for what that cost:
    "they will more than likely spend on trying to get a consistent result
    across the sections".

    A sort does not need a model. The order here is three rules, in this
    order, and each is already the product's:

      1. **Blockers first**, by `checks.is_blocker` - the registry's rule,
         which the prompt-era ranking also deferred to ("Blockers are ranked
         first whatever they score, and the rule is the registry's rather
         than the model's"). A blocker is a thing that stops the page being
         reached at all, so no score beats it.
      2. **Then severity**, worst first, in the order the record stores.
      3. **Then how many findings the check carries**, most first: between
         two mediums, the one failing on forty pages is the one to open.

    Ties fall back to the check id, so the order is stable across runs and a
    rank that moved means something moved.

    **What is NOT here, deliberately.** No points-recoverable score, and no
    cluster ranking. Those were the model's, they were never derivable from
    the record, and item 196's scope is "keep the ranking, lose the button" -
    not "reproduce the model's judgement without the model". The panel's
    `ranking` key is empty for the same reason it was empty before when a
    report carried no contract: an absent ranking is honest, an invented one
    is not.

    **Never stale.** The ranking is computed from the run it describes, so
    `stale` is False by construction and `from_run` is that run. The staleness
    warning existed because a stored ranking could outlive its audit; nothing
    can now.
    """
    runnable = runnable or set()
    already = already or set()
    catalogue = _catalogue()

    from clauditseo.checks import is_blocker

    # One entry per check, not per finding: triage ranked checks, and the
    # screens that read this map a rank onto a part through the check.
    by_check: dict[str, dict] = {}
    for f in findings:
        check = f.get("check_id") or f.get("code") or ""
        if not check:
            continue
        seen = by_check.get(check)
        sev = (f.get("severity") or "info").lower()
        if seen is None:
            by_check[check] = {"check": check, "severity": sev,
                               "summary": f.get("summary"), "n": 1}
            continue
        seen["n"] += 1
        # The worst severity the check carries, so a check that fails
        # critically on one page and quietly on thirty ranks as critical.
        if _sev_rank(sev) < _sev_rank(seen["severity"]):
            seen["severity"] = sev
            seen["summary"] = f.get("summary")

    def rank_key(row: dict) -> tuple:
        return (0 if is_blocker(row["check"]) else 1,
                _sev_rank(row["severity"]),
                -row["n"],
                row["check"])

    ranked = []
    for row in sorted(by_check.values(), key=rank_key):
        check = row["check"]
        category = anatomy.CHECK_CATEGORY.get(check)
        acts = []
        for tool in (anatomy.tools_for(category) if category else []):
            if tool not in catalogue:
                continue
            action = ("read" if tool in already
                      else "run" if tool in runnable else "sweep")
            acts.append({"tool": tool, "action": action,
                         "name": catalogue[tool]["name"],
                         "type": catalogue[tool]["type"]})
        order = {"run": 0, "read": 1, "sweep": 2}
        acts.sort(key=lambda a: (order[a["action"]], a["tool"]))
        ranked.append({"check": check, "severity": row["severity"],
                       "summary": row["summary"], "category": category,
                       "findings": row["n"], "tools": acts[:4]})

    return {
        "ran_at": ran_at,
        "from_run": from_run,
        "stale": False,
        "ranking": [],
        "ranked": ranked,
        "derivation": "Ranked by the audit itself: checks that block first, "
                      "then by severity, then by how many findings the check "
                      "carries. The tools beside each row are the ones that "
                      "investigate that check's category.",
    }
