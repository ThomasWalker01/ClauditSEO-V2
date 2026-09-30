"""OFP — Off-Page dimension.

Consumes the merged backlink snapshot from the provider hub. Anything not
supplied is reported as not-assessed — never estimated.

Reporting is per *signal*, not per snapshot. Providers differ in what they
return, and treating "a provider answered" as "the dimension was measured"
hid a bad case: with only the free OpenPageRank key configured the hub
returns a snapshot carrying nothing but a domain-authority number, which no
check here consumes. The dimension then produced no findings at all and
suppressed the note saying so — configuring the free key made the audit less
honest than having no key, while measuring exactly as much.
"""

from __future__ import annotations

from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Confidence, Finding, Severity, Site, SubScore, Tier

TOXIC_ANCHOR_TERMS = ("casino", "viagra", "porn", "payday loan", "replica")
EXACT_MATCH_LIMIT = 0.4   # share of anchors that are one repeated commercial phrase
LOW_REFERRING_DOMAINS = 10

# The signals this dimension scores on, and what supplies each. Domain
# authority is deliberately absent: it is a vendor's rounded proxy, it drives
# no check, and counting it as coverage would let the cheapest key claim the
# most ground.
SIGNALS: dict[str, str] = {
    "referring domains": "Moz or DataForSEO",
    "anchor text distribution": "Moz or DataForSEO",
}


class OffPageModule:
    code = "OFP"
    #: This dimension's coverage comes from backlink provider signals, not
    #: from pages, so no crawl depth can raise it — and `run_adaptive` clears
    #: the backlink providers at any band below CRITICAL. Read by
    #: `registry.crawl_blind_dims`, which the staging planner uses to keep an
    #: absence it cannot fill from buying a crawl. Every other dimension
    #: derives coverage from `scoring.page_coverage` and leaves this True.
    coverage_from_crawl = False
    name = "Off-Page"
    default_weight = scoring.DEFAULT_WEIGHTS["OFP"]
    #: **The one False**, and the only one at HEAD. All five checks read the
    #: domain's backlink profile from a provider snapshot —
    #: `backlinks-not-assessed`, `domain-authority-reported`,
    #: `referring-domains-reported`, `low-referring-domains`, `toxic-anchor-pattern`,
    #: `anchor-overoptimisation` — and every one of them constructs its
    #: `Finding` with a literal `affected_urls=[]`. Nothing this dimension
    #: measures is a property of any page of the site, so a page refresh here
    #: buys a crawl and a provider call and cannot move a single finding.
    #: That is UX-39, reproduced at the running product.
    #:
    #: Distinct from `coverage_from_crawl` above even though this module is
    #: the only member of both sets: that one says no crawl can raise this
    #: dimension's *coverage*, this one says no single page can move its
    #: *findings*. Two facts that coincide here and need not coincide in the
    #: next dimension. See `registry.page_blind_dims`.
    measured_per_page = False

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        site: Site = context["site"]
        hub = context.get("providers")
        # T1 makes no external API calls by contract.
        snap = None
        if hub is not None and tier is not Tier.T1:
            snap = hub.backlink_snapshot(site.domain)

        findings: list[Finding] = []

        # Which of the scored signals actually arrived, whatever answered.
        dark = list(SIGNALS)
        if snap is not None:
            if snap.referring_domains:
                dark.remove("referring domains")
            if snap.anchors:
                dark.remove("anchor text distribution")

        if dark:
            what = ", ".join(dark)
            # Scoped to this dimension's own providers, as `prf.py`'s
            # `cwv_names` already does.
            #
            # **Cited by symbol rather than by line, deliberately.** This
            # address was `:176-181`, then `:215-219`, then `:228-232`, then
            # `:306-310` — four corrections in one item, every one of them
            # because a constant was added above it in `prf.py` and none of
            # them because anything about this reasoning changed. The guard
            # that catches the drift says so itself: "replace it with the
            # symbol name, which cannot go stale."
            #
            # `hub.failures` is hub-wide, so a CWV provider
            # answering 400 made this BACKLINKS finding assert that a provider
            # exists and is refusing when none is configured for backlinks —
            # and it is the route by which a PageSpeed credential reached a
            # `backlinks-not-assessed` row. The two modules were otherwise
            # byte-identical here; the asymmetry was the defect.
            own = {getattr(p, "name", type(p).__name__)
                   for p in (hub.backlink_providers if hub is not None else [])}
            mine = {n: d for n, d in (hub.failures.items()
                                      if hub is not None else {}.items())
                    if n in own}
            failed = hub.failure_note(only=own) if hub is not None else ""
            needs = sorted({SIGNALS[s] for s in dark})
            findings.append(Finding(
                dimension=self.code, check_id="backlinks-not-assessed",
                severity=Severity.INFO, scope_statement=True,
                # Three different reasons, and they used to read as one.
                # A provider that was asked and refused is not an absent
                # provider, and telling a client "none is configured" when
                # one is configured and returning 403 is a false statement
                # in a report — the operator then goes looking for a setting
                # that is already set.
                summary=(f"Not assessed: {what}. " + (
                    failed if failed else
                    "No backlink data provider is configured." if snap is None
                    else f"The configured provider "
                         f"({', '.join(snap.sources) or 'unknown'}) does not "
                         f"supply {'it' if len(dark) == 1 else 'them'}.")),
                subject="backlinks", affected_urls=[],
                evidence={"unmeasured": dark, "needs": needs,
                          "providers_answering": (snap.sources if snap else []),
                          "providers_failing": list(mine.values())},
                confidence=Confidence.LOW,
                recommendation=(
                    "Check the credentials for the provider above — it is "
                    "configured and refusing." if failed else
                    f"Configure {' or '.join(needs)} to assess {what}."),
            ))

        if snap is None:
            return findings

        # Recorded because an operator paid for it, but it drives no check —
        # say so rather than let a number on screen imply it was scored.
        if snap.domain_authority:
            da = snap.domain_authority
            findings.append(Finding(
                dimension=self.code, check_id="domain-authority-reported",
                severity=Severity.INFO, scope_statement=True,
                summary=f"Domain authority {da.value:.0f}/100 ({da.source}). "
                        "Recorded for reference — a third-party proxy metric, "
                        "so it affects no score here.",
                subject="domain-authority", affected_urls=[],
                evidence={"domain_authority": da.value, "source": da.source,
                          "confidence": da.confidence},
                confidence=Confidence(da.confidence),
                recommendation="Track the direction it moves over time rather "
                               "than the absolute figure.",
            ))

        conf = Confidence(snap.referring_domains.confidence) if snap.referring_domains else Confidence.LOW

        # Item 236: the count, whatever it is, as the authority figure above is
        # reported. `low-referring-domains` fires only under the floor, so a
        # site above it had its one paid-for backlink number recorded nowhere
        # the Backlinks part draws - the page read as though nothing was known.
        if snap.referring_domains:
            rd = snap.referring_domains
            findings.append(Finding(
                dimension=self.code, check_id="referring-domains-reported",
                severity=Severity.INFO, scope_statement=True,
                summary=f"{rd.value} referring domains ({rd.source}). Recorded for "
                        "reference; the check below says whether it is low.",
                subject="referring-domains-count", affected_urls=[],
                evidence={"referring_domains": rd.value, "source": rd.source,
                          "confidence": rd.confidence},
                confidence=conf,
                recommendation="Track the direction it moves over time.",
            ))

        if snap.referring_domains and snap.referring_domains.value < LOW_REFERRING_DOMAINS:
            findings.append(Finding(
                dimension=self.code, check_id="low-referring-domains",
                severity=Severity.MEDIUM,
                summary=f"Only {snap.referring_domains.value} referring domains "
                        f"({snap.referring_domains.source}).",
                subject="referring-domains", affected_urls=[],
                evidence={"referring_domains": snap.referring_domains.value,
                          "source": snap.referring_domains.source,
                          "all_sources": snap.sources},
                confidence=conf,
                recommendation="Earn links through genuinely citable content, local "
                               "partnerships and digital PR — never bought links.",
            ))

        if snap.anchors:
            total = sum(snap.anchors.values())
            toxic = {a: c for a, c in snap.anchors.items()
                     if any(t in a.lower() for t in TOXIC_ANCHOR_TERMS)}
            if toxic:
                findings.append(Finding(
                    dimension=self.code, check_id="toxic-anchor-pattern",
                    severity=Severity.HIGH,
                    summary=f"{sum(toxic.values())} of {total} anchors match known toxic "
                            "patterns.",
                    subject="toxic-anchors", affected_urls=[],
                    evidence={"toxic_anchors": toxic, "total_anchors": total,
                              "sources": snap.sources},
                    confidence=conf,
                    recommendation="Review these links; disavow only after manual "
                                   "confirmation they are spam.",
                ))
            top_share = max(snap.anchors.values()) / total if total else 0
            if total >= 10 and top_share > EXACT_MATCH_LIMIT:
                top_anchor = max(snap.anchors, key=lambda a: snap.anchors[a])
                findings.append(Finding(
                    dimension=self.code, check_id="anchor-overoptimisation",
                    severity=Severity.MEDIUM,
                    summary=f'"{top_anchor}" makes up {top_share:.0%} of the anchor '
                            "profile — an unnatural pattern.",
                    subject="anchor-distribution", affected_urls=[],
                    evidence={"top_anchor": top_anchor, "share": round(top_share, 3),
                              "total_anchors": total, "sources": snap.sources},
                    confidence=conf,
                    recommendation="Diversify link acquisition; branded and natural "
                                   "anchors should dominate.",
                ))
        return findings

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # The not-assessed finding carries the list, so the score cannot drift
        # out of step with what the run reported.
        note = next((f for f in findings
                     if f.check_id == "backlinks-not-assessed"), None)
        dark = tuple((note.evidence or {}).get("unmeasured", ())) if note else ()
        return scoring.subscore(
            self.code, findings, self.default_weight, context,
            coverage=1.0 - len(dark) / len(SIGNALS),
            unmeasured=dark,
        )


registry.register(OffPageModule())
