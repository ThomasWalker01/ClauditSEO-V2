"""Adaptive staging policy: deterministic results decide what runs next.

Pure functions only — no crawling, no API calls, no LLM. The same scores and
states always produce the same escalation plan, and every escalation carries
its reasons so runs and reports can show why money or depth was spent.

Bands (operator-chosen, stricter preset):
    >= 95  HEALTHY   stop; snapshot only
    80-94  WATCH     full T2 crawl, free checks only
    60-79  CONCERN   T2 + the dimension's analyst task
    < 60   CRITICAL  T3 depth, paid APIs where keyed, analyst task
Overrides, in order: regression lifts to at least CONCERN; a critical-severity
finding lifts one band; hysteresis caps at WATCH when the previous run was
already deep and the score barely moved.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import IntEnum


class Band(IntEnum):
    NONE = 0
    WATCH = 1
    CONCERN = 2
    CRITICAL = 3


@dataclass(frozen=True)
class StagingConfig:
    healthy: float = 95.0
    watch: float = 80.0
    concern: float = 60.0
    hysteresis_delta: float = 5.0

    @classmethod
    def from_env(cls) -> "StagingConfig":
        # Through the shared lookup rather than os.environ. These four were
        # read directly, which made them the only settings that did not
        # accept the legacy prefix — so renaming them here would have
        # silently stopped reading thresholds an operator had already set,
        # and moved every site's band without saying anything.
        from clauditseo.config import from_environment

        def f(name: str, default: float) -> float:
            try:
                return float(from_environment(name) or default)
            except ValueError:
                return default
        return cls(healthy=f("CLAUDITSEO_BAND_HEALTHY", 95.0),
                   watch=f("CLAUDITSEO_BAND_WATCH", 80.0),
                   concern=f("CLAUDITSEO_BAND_CONCERN", 60.0),
                   hysteresis_delta=f("CLAUDITSEO_BAND_HYSTERESIS", 5.0))


@dataclass
class Escalation:
    dimension: str
    band: Band
    reasons: list[str] = field(default_factory=list)
    #: Whether this escalation is a reason to buy a deeper crawl. False only
    #: for a dimension escalated *purely* because it measured nothing, and
    #: only where the deeper crawl could not obtain that coverage anyway — it
    #: is still escalated, still reported and still never banded HEALTHY, it
    #: just does not decide the tier on its own. An override lifts the band on
    #: evidence (a regression, a critical finding); it does not set this back
    #: to True on its own, because a futile crawl stays futile whatever
    #: raised the band. `_depth_could_obtain` decides, from the settled band.
    buys_depth: bool = True


# Dimensions with a matching analyst judgement task.
ANALYST_TASK_FOR_DIM = {"CNT": "CNT-J", "ONP": "ONP-J", "AIS": "AIS-J"}
DEEP_TIERS = ("T2", "T3")


def band_for_score(score: float, cfg: StagingConfig) -> Band:
    if score >= cfg.healthy:
        return Band.NONE
    if score >= cfg.watch:
        return Band.WATCH
    if score >= cfg.concern:
        return Band.CONCERN
    return Band.CRITICAL


def _depth_could_obtain(dim: str, band: Band, crawl_blind_dims: set[str],
                        crawl_obtained_pages: bool) -> bool:
    """Whether a deeper crawl could plausibly obtain the coverage this
    escalation is about. A property of the run, not only of the module.

    Two ways it cannot, and `crawl_blind_dims` can only express the first.

    **The module cannot obtain it at any depth.** OFP's coverage comes from
    backlink provider signals and `paid_provider_dims` authorises those only
    at CRITICAL, so below that band the crawl reads no backlink signal however
    deep it goes. At CRITICAL it does — which is why this is asked of the
    settled band rather than answered once with False.

    **This run's crawl obtained nothing.** Every other dimension derives its
    coverage from `scoring.page_coverage`, which is 1.0 on any eligible page
    and 0.0 on none. So a crawl that fetched no eligible page leaves all of
    them uncovered at once, and a second, larger crawl of the same site meets
    the same refusal — three of this repository's eleven stored runs are
    `blocked`. The per-module flag cannot say that: it is a constant, and this
    is a fact about one run.
    """
    if dim in crawl_blind_dims:
        return band is Band.CRITICAL
    return crawl_obtained_pages


def plan(
    scores: dict[str, float],
    regressed_dims: set[str],
    critical_dims: set[str],
    uncovered_dims: set[str],
    crawl_blind_dims: set[str],
    previous: dict | None,
    cfg: StagingConfig,
    *,
    crawl_obtained_pages: bool,
    can_widen: bool = True,
) -> dict[str, Escalation]:
    """Escalations for every dimension that needs one. `scores` holds only
    applicable dimensions; `uncovered_dims` names those among them whose
    score is not a measurement; `previous` is the last complete run's record
    ({"tier": ..., "subscores": {dim: {"score": ...}}}) or None.

    `crawl_blind_dims` names those whose coverage no crawl can obtain at any
    depth — `registry.crawl_blind_dims` derives it. `crawl_obtained_pages`
    says whether *this run's* crawl fetched any eligible page, which is the
    other half of the same question: the module-level flag is a constant and
    cannot express "the crawl this run actually ran obtained nothing, so a
    larger one would meet the same refusal". An uncovered dimension failing
    either test escalates — it is reported and never banded HEALTHY — but
    carries `buys_depth=False`, so it cannot on its own commission a crawl
    that provably cannot change the input that triggered it.

    `can_widen` says whether a deeper crawl would be allowed to fetch more
    pages than this one did. It is False under a page or nav scope, where
    the escalated crawl fetches the same set by construction (relay item
    136a) - so an escalation raised on an absence would commission a crawl
    that provably cannot change the input that triggered it, which is the
    thing the other two clauses of this rule already refuse. Defaulted True
    because every caller before scope existed could widen.

    `crawl_obtained_pages` is keyword-only and required. Required for the
    reason the two sets below are; keyword-only because it is a bool arriving
    behind five `set[str]` parameters, where a transposition would type-check
    and silently restore the defect.

    All are required arguments, not defaulted ones. A dimension
    that read nothing scores 100.0 — the fixture site's OFP does, at every
    tier — and `band_for_score` reads that as HEALTHY, so the one dimension
    the audit is blind to is the one it never looks harder at. A default would
    let the next call site inherit that silently, which is how the defect
    survived fifteen rounds; `runs._snapshot_metrics` has required
    `applicable and coverage` since round 025 and this is the same rule at the
    other consumer.
    """
    out: dict[str, Escalation] = {}
    prev_deep = bool(previous) and previous.get("tier") in DEEP_TIERS
    prev_scores = (previous or {}).get("subscores") or {}

    for dim, score in sorted(scores.items()):
        uncovered = dim in uncovered_dims
        if uncovered:
            # WATCH, not CONCERN: the lowest band that still escalates. It buys
            # the deeper crawl that obtains coverage for a page-derived
            # dimension, without also commissioning an analyst judgement or a
            # paid provider call on the strength of an absence.
            band = Band.WATCH
            reasons = ["no coverage: the dimension measured nothing at this "
                       "tier, so its score is not evidence"]
        else:
            band = band_for_score(score, cfg)
            reasons = [f"score {score:g} → {band.name} band"]

        # An override fires on evidence — a finding that came back, or a
        # critical-severity one in hand — so it lifts the band. It does not
        # decide depth. Whether the crawl that band would buy can obtain
        # anything is settled once, below, from the band this leaves behind:
        # a regression on a dimension no crawl can read is still a regression
        # worth reporting, and still not a reason to crawl.
        if dim in regressed_dims and band < Band.CONCERN:
            band = Band.CONCERN
            reasons.append("regression override: a previously fixed issue is back")
        if dim in critical_dims and band < Band.CRITICAL:
            band = Band(band + 1)
            reasons.append("critical-finding override: escalated one band")

        # Hysteresis reuses a previous deep run's standing analysis. There is
        # none to reuse for a dimension that measured nothing, and comparing
        # two fabricated 100.0s would always fall inside the delta.
        if (band >= Band.CONCERN and prev_deep and not uncovered
                and dim not in regressed_dims):
            prev = prev_scores.get(dim, {}).get("score")
            if prev is not None and abs(prev - score) < cfg.hysteresis_delta:
                band = Band.WATCH
                reasons.append(
                    f"hysteresis: score within {cfg.hysteresis_delta:g} of the "
                    "previous deep run — reusing standing analysis")

        # The depth decision, made once and from the band that survived the
        # overrides and the hysteresis. Only an escalation raised *on an
        # absence* can fail it: a score that is a measurement is a reason to
        # look harder whatever the crawl obtained. Written here rather than
        # beside the band so a reason explaining a refusal cannot outlive the
        # refusal — that note is the operator's only record of the decision.
        buys_depth = True
        if uncovered:
            buys_depth = (can_widen
                          and _depth_could_obtain(dim, band, crawl_blind_dims,
                                                  crawl_obtained_pages))
            if not buys_depth and not can_widen:
                reasons.append(
                    "and the scope fixes the page set, so a deeper crawl "
                    "would read the same pages and meet the same absence")
            elif not buys_depth and dim in crawl_blind_dims:
                reasons.append(
                    "and no crawl can obtain it, so this alone does not buy "
                    "a deeper crawl")
            elif not buys_depth:
                reasons.append(
                    "and this run's crawl fetched no eligible page, so a "
                    "deeper crawl of the same site would repeat the refusal "
                    "rather than obtain it")

        if band > Band.NONE:
            out[dim] = Escalation(dimension=dim, band=band, reasons=reasons,
                                  buys_depth=buys_depth)
    return out


def escalated_tier(escalations: dict[str, Escalation]) -> str | None:
    """T3 when an escalation that buys depth is CRITICAL, T2 when one buys
    depth at any lower band, else None — including when there are escalations
    but none of them buys depth.

    Escalating and buying depth were the same thing until round 047, and that
    made the free stop-at-pulse path unreachable for the product's own default
    dimension list. OFP reads no backlink data at T1 by contract, so round
    046's rule banded it WATCH on every default run, and any escalation
    returned "T2" — up to 100 pages against a client site, on a trigger the
    crawl could not clear, on a product whose stated constraint is
    cost-sensitivity. Saying "this score is not evidence" and saying "look
    harder" are two claims, and only the second costs money.

    The CRITICAL branch used to run before the `buys_depth` test rather than
    inside it, so the guard was computed correctly and then ignored on the one
    tier that costs the most: a dimension both uncovered and lifted to
    CRITICAL by the overrides returned "T3" while its own stored reason said a
    deeper crawl would repeat the refusal. Filtering first makes the two
    branches read the same field, so a state that cannot buy T2 cannot buy T3
    either.
    """
    buying = [e for e in escalations.values() if e.buys_depth]
    if not buying:
        return None
    return "T3" if any(e.band is Band.CRITICAL for e in buying) else "T2"


def analyst_tasks(escalations: dict[str, Escalation]) -> list[str]:
    """Tasks for dimensions at CONCERN or worse that buy depth; PRI-J joins
    whenever any of those needs judgement, so a run that commissions
    judgement always gets a sequencing narrative. Returned in the canonical
    priority order.

    `buys_depth`, because a model task is a spend and the WATCH band's stated
    guarantee — an absence is reported "without also commissioning an analyst
    judgement or a paid provider call" — was asserted in a comment and
    implemented nowhere. An escalation raised purely on an absence the crawl
    cannot fill has nothing for an analyst to read: the input it would judge
    is the fabricated score that triggered it.
    """
    from clauditseo.analysts.base import TASKS

    judging = [(d, e) for d, e in escalations.items()
               if e.band >= Band.CONCERN and e.buys_depth]
    wanted = {ANALYST_TASK_FOR_DIM[d] for d, _ in judging
              if d in ANALYST_TASK_FOR_DIM}
    if judging:
        wanted.add("PRI-J")
    return [t for t in TASKS if t in wanted]


def paid_provider_dims(escalations: dict[str, Escalation]) -> set[str]:
    """Dimensions whose CRITICAL band authorises paid provider calls — and
    only where the escalation buys depth, since a paid call bought by an
    absence buys the same absence again. For a crawl-blind dimension that is
    no restriction at all: `_depth_could_obtain` returns True for it exactly
    at CRITICAL, which is the band that authorises the spend.
    """
    return {d for d, e in escalations.items()
            if e.band is Band.CRITICAL and e.buys_depth}
