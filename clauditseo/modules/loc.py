"""LOC — Local dimension.

Only applicable to businesses with a local footprint (the site's
business_type says so); otherwise its weight redistributes. Checks NAP
consistency across pages, LocalBusiness structured data, opening-hours and
map signals, and location-page substance.
"""

from __future__ import annotations

import json
import re
from typing import Any

from clauditseo.crawler.types import CrawlResult
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier

from .pagefacts import extract_facts, html_pages

LOCAL_TYPES = {"local-service", "local", "brick-and-mortar", "service-area", "hybrid-local"}
# AU phone shapes. The previous pattern matched landlines only: it required a
# 3-or-4 digit group straight after the area code, which "0400 111 222" does not
# have. Mobiles are how most local businesses publish their number, so the check
# reported nap-missing on sites showing a phone in plain sight. Longest
# alternatives first so a 1300 number is not clipped to a 13 number.
PHONE_RE = re.compile(
    r"(?<![\d])("
    r"\+61[\s-]?\(?0?\)?[\s-]?4\d{2}[\s-]?\d{3}[\s-]?\d{3}"   # +61 400 111 222
    r"|\+61[\s-]?\(?0?\)?[\s-]?[2-8][\s-]?\d{4}[\s-]?\d{4}"   # +61 3 9111 2222
    r"|\(0[2-8]\)[\s-]?\d{4}[\s-]?\d{4}"                      # (03) 9111 2222
    r"|04\d{2}[\s-]?\d{3}[\s-]?\d{3}"                         # 0400 111 222
    r"|0[2-8][\s-]?\d{4}[\s-]?\d{4}"                          # 03 9111 2222
    r"|1[38]00[\s-]?\d{3}[\s-]?\d{3}"                         # 1300 555 111
    r"|13[\s-]?\d{2}[\s-]?\d{2}"                              # 13 11 14
    r")(?![\d])")
THIN_LOCATION_WORDS = 100


def _phones(text: str) -> set[str]:
    return {re.sub(r"[^\d]", "", m) for m in PHONE_RE.findall(text)}


# schema.org LocalBusiness subtypes seen in the wild on Australian trade and
# service sites. Naming only "Plumber" — as this check previously did — meant a
# correctly marked-up roofer or electrician was reported as having no
# LocalBusiness schema at all.
LOCAL_BUSINESS_TYPES = {
    "localbusiness", "homeandconstructionbusiness", "professionalservice",
    "roofingcontractor", "plumber", "electrician", "generalcontractor",
    "hvacbusiness", "houseandpainter", "painter", "locksmith", "movingcompany",
    "cleaningservice", "landscaper", "pestcontrol", "automotivebusiness",
    "autorepair", "dentist", "physician", "medicalbusiness", "veterinarycare",
    "legalservice", "attorney", "accountingservice", "financialservice",
    "insuranceagency", "realestateagent", "foodestablishment", "restaurant",
    "cafeorcoffeeshop", "bakery", "bar", "healthandbeautybusiness",
    "hairsalon", "beautysalon", "dayspa", "healthclub", "sportsactivitylocation",
    "childcare", "school", "store", "lodgingbusiness", "travelagency",
    "emergencyservice", "selfstorage", "entertainmentbusiness",
}


def is_local_business(type_value: Any) -> bool:
    """Whether a JSON-LD @type is a LocalBusiness or one of its subtypes."""
    name = str(type_value).rsplit("/", 1)[-1].strip().lower()
    return name in LOCAL_BUSINESS_TYPES or "localbusiness" in name


class LocalModule:
    code = "LOC"
    name = "Local"
    default_weight = scoring.DEFAULT_WEIGHTS["LOC"]
    #: **The argued one** (Q-17 named this dimension as genuinely
    #: ambiguous, at 1 page-naming finding against 8 site-scoped in the
    #: operator's data). Three of five checks are site-scoped by
    #: construction: `nap-missing`, `localbusiness-schema-missing` and
    #: `opening-hours-missing` are all "no page in the crawl had this", which
    #: one page cannot answer. A fourth, `nap-inconsistent`, lists pages but
    #: asserts a *cross-page* property — that N different phone numbers
    #: appear across the site — and re-reading one of them cannot settle it.
    #: That is four checks a page refresh cannot move, and it is why the
    #: stored split is 1/8.
    #:
    #: True nonetheless, on the strength of the fifth: `thin-location-page`
    #: is a word count on one location page, attributed to that page, and a
    #: single-URL re-read re-measures it exactly. The rule is "can a page
    #: refresh move *any* of this dimension's findings", not "most" — the
    #: same rule that keeps PRF and TEC page-capable despite each carrying
    #: site-scoped `-not-assessed` notes. Declaring False here would withdraw
    #: a working control from every location page to spare the four, which is
    #: the expensive direction Q-17 rejected. See `registry.page_blind_dims`.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return (site.business_type or "").lower() in LOCAL_TYPES

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        facts = [extract_facts(p) for p in html_pages(crawl.pages)]
        findings: list[Finding] = []

        # Every check below reads a fetched page, and each states its result
        # as an absence — "No phone number found on any crawled page", "No
        # LocalBusiness structured data found on any crawled page". With no
        # crawled page those sentences are true only by vacuity, and a client
        # reads them as defects on their own site. The run's scope limit
        # already says nothing was fetched; saying it again as three
        # medium-severity findings is the opposite of honest.
        if not facts:
            return findings

        phones_by_page = {f.path: _phones(f.text) for f in facts if _phones(f.text)}
        distinct = set().union(*phones_by_page.values()) if phones_by_page else set()
        if len(distinct) > 1:
            findings.append(Finding(
                dimension=self.code, check_id="nap-inconsistent", severity=Severity.MEDIUM,
                summary=f"{len(distinct)} different phone numbers appear across the site.",
                subject="nap-phone",
                affected_urls=[f.url for f in facts if f.path in phones_by_page][:10],
                affected_total=len([f for f in facts if f.path in phones_by_page]),
                evidence={"numbers": sorted(distinct),
                          "by_page": {k: sorted(v) for k, v in phones_by_page.items()}},
                recommendation="Standardise one primary phone number everywhere it "
                               "appears (site, GBP, citations).",
            ))
        elif not distinct:
            findings.append(Finding(
                dimension=self.code, check_id="nap-missing", severity=Severity.MEDIUM,
                summary="No phone number found on any crawled page.",
                subject="nap-phone", affected_urls=[],
                evidence={"pages_checked": len(facts)},
                recommendation="Publish NAP (name, address, phone) consistently, ideally "
                               "in the footer and contact page.",
            ))

        has_local_schema = False
        has_hours = False
        for f in facts:
            for block in f.jsonld_blocks:
                try:
                    data = json.loads(block)
                except json.JSONDecodeError:
                    continue
                items = data if isinstance(data, list) else [data]
                # Item 233: descend `@graph`, as `pagefacts.schema_inventory`
                # does. Yoast and most CMS plugins emit every node inside one
                # graph, so the top level holds no `@type` at all - on twenty22
                # this reported "No LocalBusiness structured data found on any
                # crawled page" over a `#local_business` node on /contact-us/.
                items = [n for i in items
                         for n in ([i, *i["@graph"]] if isinstance(i, dict)
                                   and isinstance(i.get("@graph"), list) else [i])]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    type_value = item.get("@type", "")
                    types = type_value if isinstance(type_value, list) else [type_value]
                    if any(is_local_business(t) for t in types):
                        has_local_schema = True
                        if item.get("openingHours") or item.get("openingHoursSpecification"):
                            has_hours = True
        if not has_local_schema:
            findings.append(Finding(
                dimension=self.code, check_id="localbusiness-schema-missing",
                severity=Severity.MEDIUM,
                summary="No LocalBusiness structured data found on any crawled page.",
                subject="localbusiness-schema", affected_urls=[],
                evidence={"pages_checked": len(facts)},
                recommendation="Add LocalBusiness JSON-LD (name, address, phone, "
                               "geo, openingHoursSpecification) to the homepage or "
                               "contact page.",
            ))
        elif not has_hours:
            findings.append(Finding(
                dimension=self.code, check_id="opening-hours-missing",
                severity=Severity.LOW,
                summary="LocalBusiness schema present but without opening hours.",
                subject="opening-hours", affected_urls=[],
                evidence={},
                recommendation="Add openingHoursSpecification so hours can surface in "
                               "search.",
            ))

        for f in facts:
            if "/location" in f.path or "/areas" in f.path:
                if 0 < f.word_count < THIN_LOCATION_WORDS:
                    findings.append(Finding(
                        dimension=self.code, check_id="thin-location-page",
                        severity=Severity.LOW,
                        summary=f"Location page {f.path} has only {f.word_count} words.",
                        subject=f.path, affected_urls=[f.url],
                        evidence={"word_count": f.word_count},
                        recommendation="Give each location page genuinely local content: "
                                       "team, jobs done nearby, service specifics, "
                                       "directions — not a swapped suburb name.",
                    ))
        return findings

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # Wholly page-derived: every check here reads a fetched page, so a
        # crawl that fetched none measured none of this dimension.
        return scoring.subscore(self.code, findings, self.default_weight, context,
                                coverage=scoring.page_coverage(context))


registry.register(LocalModule())
