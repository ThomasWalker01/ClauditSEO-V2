"""Adaptive audit orchestration (tier "auto", the default mode).

Flow:
1. Pulse (T1, free) → provisional sub-scores + overrides from history.
2. If nothing escalated on evidence: done — the pulse IS the run. A dimension
   that measured nothing is still escalated and still recorded, but where the
   escalated crawl could not obtain its coverage — no crawl can, or this run's
   crawl reached no eligible page — it does not on its own buy the second crawl.
3. Otherwise one escalated crawl (T3 if anything is CRITICAL, else T2), with
   paid providers enabled only for the dimensions whose CRITICAL band
   authorises the spend.
4. Final sub-scores are re-banded; analyst tasks run automatically for
   dimensions at CONCERN or worse (auto up to the tier's token ceiling —
   operator's chosen policy), PRI-J included whenever judgement ran.
5. Every escalation is recorded as an info finding carrying its reasons.
"""

from __future__ import annotations

import sqlite3

from clauditseo.analysts.layer import provider_from_settings, run_analyst_layer
from clauditseo.config import Settings
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget, eligible
from clauditseo.engine import registry, staging
from clauditseo.engine.core import AuditResult, run_audit
from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier
from clauditseo.persistence import runs
from clauditseo.providers.base import ProviderHub

#: The dimensions whose checks read the performance trace: Speed's thirteen,
#: Technical's mobile six, and Security's trackers-before-consent. An adaptive
#: run without one of these takes no trace - a throttled browser pass costs
#: minutes, and nothing else would read it (operator, 2026-09-14).
TRACE_DIMS = frozenset({"PRF", "TEC", "SEC"})


def _trace(crawl_result, run_id: str, report) -> tuple[dict, str]:
    from clauditseo import perf
    report("Tracing performance in a throttled browser" if perf.available()
           else "No renderer installed: performance not traced")
    traced, rule = perf.trace_for_run(crawl_result, run_id)
    report(f"Traced {len(traced)} page(s) - {rule}")
    return traced, rule


#: The dimensions whose evidence is the whole site rather than a page.
#: A CRITICAL on one of these while the operator asked for a single page
#: is the case worth telling them about: the finding may be real and the
#: crawl that would confirm it is not the crawl they asked for.
_SITE_WIDE_DIMS = frozenset({"TEC", "OFP", "AIS", "LOC"})


def scope_note(scope: str | None, dimension: str) -> Finding | None:
    """The escalation this run declined to make, as a finding.

    Relay item 136a: where the pulse suggests the site-level picture
    matters and the operator asked for a page or the navigation, that is
    recorded and surfaced as a suggestion - never executed. A product that
    quietly widens a crawl because its own evidence looked alarming has
    taken a spending decision that was not its to take.

    `None` where there is nothing to decline: an unnamed scope, a scope
    that already covers the site, or a dimension a page can answer.
    """
    if scope not in ("page", "nav") or dimension not in _SITE_WIDE_DIMS:
        return None
    from clauditseo.scanscope import SCOPES

    label = SCOPES[scope].label.lower()
    return Finding(
        dimension=dimension, check_id="adaptive-scope-held",
        severity=Severity.INFO,
        summary=(f"Escalation to site scope suggested by {dimension} and not "
                 f"taken: scope is {label}. {dimension} reads the whole site, "
                 "and this run was asked for "
                 + ("one page" if scope == "page" else "the navigation set")
                 + " — run a site scan to settle it."),
        subject=f"adaptive-scope-{scope}",
        affected_urls=[],
        recommendation=("Run a Site or Full scan if this dimension matters "
                        "here. The scan matrix's scope is yours; an audit "
                        "never widens it on its own."),
        confidence=Confidence.HIGH,
        scope_statement=True)


def escalation_label(tier: Tier, scope: str | None) -> str:
    """What the progress line calls the escalated crawl.

    `Escalated crawl (T3)` said how hard and not how many, which is the
    whole confusion relay item 136a is about: an operator watching a page
    scan read "T3" and saw 145 pages arrive.
    """
    if not scope:
        return f"Escalated crawl ({tier.value})"
    return f"Escalated crawl ({tier.value}, {scope} scope)"


def run_adaptive(
    conn: sqlite3.Connection,
    run_id: str,
    site: Site,
    site_id: str,
    start_url: str,
    cfg: Settings,
    dims: list[str],
    model: str | None = None,
    # Whether the analyst layer may run at stage 3. True is the historical
    # behaviour and stays the default, so every caller that says nothing gets
    # the run it always got. False is what makes a bounded adaptive run
    # possible (WF-59): the breadth is still chosen by the bands, and no model
    # is invoked. The bands are still computed either way — the escalation
    # notes an operator reads are not a side effect of the analysts.
    analyst: bool = True,
    announce=None,
    provider=None,
    budgets: dict[Tier, TierBudget] | None = None,
    # The operator's choice of *how many pages*, which is not this
    # function's to change (relay item 136a). `None` is an audit that
    # named no scope and behaves exactly as it always did.
    #
    # It was missing, and the cost was a 145-page crawl of a site the
    # operator had asked one page of: both crawls below fell back to the
    # tier's own budget, and a tier's budget is a page count - T3's is the
    # whole site. Scope and tier were separated at `scanscope.py` so that
    # "look harder" and "look at more pages" stopped being one control,
    # and this path was left on the old side of that line.
    scope: str | None = None,
    #: Asked once per page, at the top of the crawl loop. `None` is a run
    #: nobody can stop, which is every caller that says nothing.
    should_stop=None,
) -> tuple[AuditResult, dict[str, staging.Escalation]]:
    """Run the adaptive audit and persist it. Returns (result, escalations)."""
    budgets = budgets or {}
    from clauditseo.scanscope import crawl_kwargs

    def _for(tier: Tier) -> dict:
        """The crawl arguments for a tier under the operator's scope.

        The scope's restriction wins over the tier's budget wherever they
        disagree, which is the whole rule: a tier says how hard to look
        and a scope says at what.
        """
        out: dict = {}
        if budgets.get(tier) is not None:
            out["budget"] = budgets[tier]
        out.update(crawl_kwargs(scope, tier, start_url))
        if should_stop is not None:
            out["should_stop"] = should_stop
        return out

    def report(label: str, replace_last: bool = False) -> None:
        runs.add_progress(conn, run_id, label, replace_last)
        if announce:
            announce(label)

    say = report
    band_cfg = staging.StagingConfig.from_env()

    # -- stage 1: pulse ------------------------------------------------------
    report("Pulse (T1): crawling homepage, robots and sitemap head")
    # The well-known path sweep runs once per run, on the pulse, and only when
    # SEC is asked for (item 143 step BD). The deep crawl inherits it below
    # rather than fetching the same paths again: the client report tells the
    # site each was requested once.
    # The parity probe (item 151) runs on both crawls: the pulse probes its
    # three pages, which is the whole answer when the run stops at T1, and the
    # deep crawl probes one page per template. Full mode where the previous
    # run diverged.
    parity = runs.parity_mode(conn, site_id, run_id)
    pulse_crawl = crawl(start_url, Tier.T1,
                        on_progress=lambda n: report(
                            f"Pulse (T1): {n} page(s) fetched", replace_last=n > 1),
                        security_paths="SEC" in dims,
                        mobile_parity=parity,
                        **_for(Tier.T1))
    report("Pulse (T1): scoring all dimensions")
    pulse = run_audit(site, pulse_crawl, dims, Tier.T1)

    states = runs.site_states(conn, site_id)
    regressed = {s["dimension"] for s in states
                 if s["state"] == "regressed" and s["dimension"] in dims}
    critical = {f.dimension for f in pulse.findings
                if f.severity is Severity.CRITICAL}
    # The baseline the drop check is computed against, so it has to be
    # comparable with the pulse: `staging.plan` reads `prev_deep` from its
    # tier and `prev_scores` from its subscores, and both are claims about the
    # site. On `www.acme.com.au` this picked the eight-page verification
    # `d4474b38` — `T2 in DEEP_TIERS` true, six dimensions measured over eight
    # pages of 224 — and the tier the next audit ran at was decided partly by
    # a measurement not comparable with it.
    previous = next((r for r in runs.site_readings(conn, site_id)
                     if r["status"] in runs.SCORED_STATUSES
                     and r["id"] != run_id), None)

    blind = registry.crawl_blind_dims(dims)
    pulse_scores, pulse_uncovered = _band_inputs(pulse.subscores)
    # `eligible`, not `len(pages)`: a DNS failure leaves a page object behind,
    # so three URLs that all fail to resolve would otherwise read as a crawl
    # that reached the site. This is the same predicate `scoring.page_coverage`
    # divides by, which is what makes the answer agree with `pulse_uncovered`.
    escalations = staging.plan(pulse_scores, regressed, critical,
                               pulse_uncovered, blind, previous, band_cfg,
                               crawl_obtained_pages=bool(eligible(pulse_crawl.pages)),
                               # A page or nav scope fixes the set, so an
                               # escalation raised on an absence cannot buy
                               # a crawl that would fill it (item 136a).
                               can_widen=scope not in ("page", "nav"))
    tier_name = staging.escalated_tier(escalations)

    wants_trace = bool(TRACE_DIMS & set(dims))
    if tier_name is None:
        # The stop at pulse still reads the trace-derived checks: the pulse was
        # scored before anyone knew it would be the last stage, so it is
        # scored again with the traces rather than tracing every pulse that
        # goes on to escalate. Nothing has been added to its findings yet.
        traced, trace_rule = ({}, None)
        if wants_trace:
            traced, trace_rule = _trace(pulse_crawl, run_id, report)
            if traced:
                pulse = run_audit(site, pulse_crawl, dims, Tier.T1,
                                  context={"perf_traces": traced})
        # Two ways to get here, and they must not be reported as one. Nothing
        # escalated at all is the HEALTHY stop. Escalations that none of which
        # buys depth is a stop with something to say: the dimension measured
        # nothing, no crawl can fill that, and the operator has to be told
        # rather than shown an "all healthy" note that is not true.
        for esc in escalations.values():
            say(f"adaptive: {esc.dimension} → {esc.band.name} "
                f"({'; '.join(esc.reasons)})")
            pulse.findings.append(_escalation_note(esc))
        if escalations:
            say("adaptive: no escalation buys a deeper crawl — stopping at T1")
        else:
            say("adaptive: every dimension is HEALTHY at pulse — stopping at T1")
            pulse.findings.append(_stage_note("none", "all dimensions in HEALTHY "
                                                      "band at pulse; no escalation"))
        from clauditseo.crawler.evidence import snapshot
        evidence = snapshot(pulse_crawl, None, traced, trace_rule)
        # The pulse is three pages and is never weighed (item 205): said, so
        # the Images part does not read the absence as a CDN.
        evidence["images_measured"] = False
        runs.store_evidence(conn, run_id, evidence)
        runs.set_tier(conn, run_id, Tier.T1.value)
        runs.complete_run(conn, run_id, pulse)
        return pulse, escalations

    for esc in escalations.values():
        say(f"adaptive: {esc.dimension} → {esc.band.name} ({'; '.join(esc.reasons)})")
    say(f"adaptive: escalating to {tier_name}")

    # -- stage 2: one escalated crawl ---------------------------------------
    tier = Tier(tier_name)
    hub = ProviderHub.from_settings(cfg)
    paid_dims = staging.paid_provider_dims(escalations)
    if "PRF" not in paid_dims:
        hub.cwv_providers = []
    if "OFP" not in paid_dims:
        hub.backlink_providers = []

    label = escalation_label(tier, scope)
    report(f"{label}: starting")
    # The scope goes with it. An escalation raises the tier and never the
    # page set (relay item 136a): what changes between these two crawls is
    # how hard each page is looked at, not how many there are.
    # The deep crawl is the audit's own, so it buys the UA matrix (item 137
    # task 4) — the one crawl per run that answers "how does the server treat
    # each named crawler's user-agent". The pulse and any incidental crawl do
    # not; `crawl` runs the pass only at T2+ site scope regardless.
    deep_crawl = crawl(start_url, tier,
                       on_progress=lambda n: report(
                           f"{label}: {n} page(s) fetched", replace_last=n > 1),
                       ua_matrix=True,
                       mobile_parity=parity,
                       **_for(tier))
    deep_crawl.well_known = pulse_crawl.well_known
    deep_crawl.dns = pulse_crawl.dns
    # What the scope stopped, said once rather than done silently. A
    # CRITICAL on a dimension whose evidence is the whole site, while the
    # operator asked for one page, is worth telling them; it is not worth
    # spending their crawl on without being asked.
    for esc in escalations.values():
        note = scope_note(scope, esc.dimension)
        if note is not None and esc.band.name == "CRITICAL":
            say(note.summary)
            pulse.findings.append(note)
            break
    report(f"Running deterministic checks at {tier.value} "
           f"({len(dims)} dimension(s))")
    traced, trace_rule = (_trace(deep_crawl, run_id, report) if wants_trace else ({}, None))
    # Item 205: the browser image pass the fixed launcher takes, on the
    # escalated crawl (never the three-page pulse), where Images is being
    # measured at all. It was absent from this path, so every adaptive audit
    # stored images nobody weighed.
    measured, images_state = {}, False
    if "ONP" in dims:
        from clauditseo import imaging
        from clauditseo.persistence import repo
        measured, images_state = imaging.measure_for_run(
            deep_crawl, repo.site_record(repo.get_site(conn, site_id)) or {}, report)
    result = run_audit(site, deep_crawl, dims, tier,
                       context={"providers": hub, "perf_traces": traced,
                                "image_measurements": measured})

    # -- stage 3: final bands drive the analysts -----------------------------
    final_scores, final_uncovered = _band_inputs(result.subscores)
    final_esc = staging.plan(final_scores, regressed, critical,
                             final_uncovered, blind, previous, band_cfg,
                             crawl_obtained_pages=bool(eligible(deep_crawl.pages)))
    tasks = staging.analyst_tasks(final_esc)

    if tasks and not analyst:
        # Said, not silently dropped. "No task escalated" and "a task
        # escalated and the caller declined it" are different facts about
        # this run and neither is visible in the findings, so the progress
        # log is the only place the difference can be read.
        say(f"adaptive: analyst tasks wanted ({', '.join(tasks)}) but not "
            f"run: the caller asked for no analyst")
        tasks = []

    if tasks:
        outcome = run_analyst_layer(
            conn, run_id, site.domain, result, deep_crawl, cfg,
            provider=provider or provider_from_settings(cfg, model),
            enabled=True, announce=report, tasks=tasks)
        if outcome.ran:
            result.findings.extend(outcome.security_findings)
            result.findings.extend(outcome.findings)
            say(f"adaptive: analyst tasks {', '.join(tasks)} — "
                f"{outcome.spent_tokens} tokens, "
                f"{len(outcome.findings)} insight(s)")
        else:
            say(f"adaptive: analyst tasks wanted ({', '.join(tasks)}) but "
                f"not run: {outcome.reason_not_run}")

    for esc in (final_esc or escalations).values():
        result.findings.append(_escalation_note(esc))

    report("Saving results and updating finding states")
    from clauditseo.crawler.evidence import snapshot
    evidence = snapshot(deep_crawl, measured or None, traced, trace_rule)
    evidence["images_measured"] = images_state
    runs.store_evidence(conn, run_id, evidence)
    runs.set_tier(conn, run_id, tier.value)
    runs.complete_run(conn, run_id, result)
    return result, final_esc


def _band_inputs(subscores) -> tuple[dict[str, float], set[str]]:
    """The planner's two inputs, derived in one place because the rule has two
    call sites and a rule with two implementations is how this one drifted.

    `applicable` says the dimension was in scope; `coverage` says whether any
    of it was obtained, and only the second makes the score evidence. A
    dimension with neither still carries a score — the fixture site's OFP
    reads 100.0 at coverage 0.0 at every tier — so the second return value
    names the dimensions whose number must not be banded.
    """
    scores = {d: s.score for d, s in subscores.items() if s.applicable}
    uncovered = {d for d, s in subscores.items()
                 if s.applicable and not s.coverage}
    return scores, uncovered


def _escalation_note(esc: staging.Escalation) -> Finding:
    return Finding(
        dimension=esc.dimension, check_id="adaptive-escalation",
        severity=Severity.INFO, scope_statement=True,
        summary=f"Adaptive staging escalated {esc.dimension} to "
                f"{esc.band.name}: {'; '.join(esc.reasons)}.",
        subject=f"adaptive-{esc.dimension.lower()}",
        # `buys_depth` beside the band because this note is the operator's
        # only record of a spend decision, and the band alone no longer
        # predicts it: two escalations at the same band spend differently
        # depending on whether a deeper crawl could obtain what they escalated
        # for. Without it a stored escalation cannot be audited for cost after
        # the fact.
        evidence={"band": esc.band.name, "reasons": esc.reasons,
                  "buys_depth": esc.buys_depth},
        confidence=Confidence.HIGH,
        recommendation="",
    )


def _stage_note(band: str, text: str) -> Finding:
    return Finding(
        dimension="TEC", check_id="adaptive-no-escalation", severity=Severity.INFO,
        scope_statement=True,
        summary=f"Adaptive staging: {text}.",
        subject="adaptive-none", evidence={"band": band},
        confidence=Confidence.HIGH, recommendation="",
    )
