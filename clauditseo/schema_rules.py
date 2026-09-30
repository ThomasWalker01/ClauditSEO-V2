"""Structured-data knowledge: what Google actually requires, and what it has
stopped rewarding.

Kept deterministic and in one place on purpose. Rich-result eligibility
changes by announcement, not by reasoning, so an analyst model must not be
the thing that remembers it — these tables are handed to the advisor as
evidence and it is told to prefer them over its own recollection.

Where Schema.org permits something Google restricts, Google governs; where
Google is silent, Schema.org governs.

WHY EVERY ENTRY CARRIES source AND verified
-------------------------------------------
This file's whole purpose is to stop a model reciting stale facts, and it
had the same disease it was built to cure. Three dates were wrong, and wrong
in a way that gives the game away: the sitelinks search box was recorded as
November 2023 when it went in November 2024, HowTo as August 2023 when full
deprecation was September 2023, and FAQPage frozen in its 2023 "restricted to
government and health sites" state long after May 2026, when it stopped
appearing for anyone at all. Those are the dates a language model produces
from training data — written down once, never checked.

The failure was structural, not careless. An entry that names *when* a thing
changed but not *where* that was published cannot be checked; and the advisor
was told to treat this table as "above your own recollection", so a stale
entry actively silenced a model that may well have known better. The table
inverted the very risk it existed to manage.

So: every entry names the Google page it came from and the day someone last
read that page. `stale_entries()` reports anything past REVIEW_AFTER_DAYS and
a test fails on it. That cannot detect that Google changed something — nothing
here can — but it refuses to let a fact table age silently past its own review
window, which is the same reason CI fails when the accessibility sweep skips.

What is checkable, and what is archaeology
------------------------------------------
`status` is the operative fact and it is cheap to verify: a type either
appears in Google's supported-features gallery or it does not. `changed` is
history, and the announcement posts are JS-rendered and hard to read
mechanically. So the gallery is the primary source for whether something
still earns a rich result, and the announcement URL is context for when it
stopped.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

#: How long an entry may go unchecked before the suite calls it stale.
#: Google's structured-data changes land a few times a year, so a quarter is
#: short enough to catch drift and long enough not to become noise a reviewer
#: learns to skip past.
REVIEW_AFTER_DAYS = 90

#: The one page that answers "does this still earn a rich result", which is
#: the question every entry below is really about.
GALLERY = "https://developers.google.com/search/docs/appearance/structured-data/search-gallery"

# Types that still validate as Schema.org but no longer earn the rich result
# most people add them for. Emitting them is harmless; RELYING on them is the
# mistake, so the finding is informational and says so.
DEPRECATED_RICH_RESULTS: dict[str, dict[str, str]] = {
    "FAQPage": {
        "changed": "7 May 2026",
        "status": "removed",
        # How a person or model might name this rich result in prose, so an
        # eligibility claim is caught however it is phrased.
        "aliases": "faqpage, faq",
        "detail": "FAQ rich results no longer appear in Google Search at all. "
                  "Between 2023 and 2026 they were limited to well-known "
                  "government and health sites; since 7 May 2026 they are shown "
                  "for nobody, including those sites. The markup is still valid "
                  "Schema.org and produces no rich result for anyone.",
        "instead": "Keep the FAQ content for users and answer-engine extraction; "
                   "do not count on a SERP enhancement from it.",
        "source": "https://developers.google.com/search/docs/appearance/"
                  "structured-data/faqpage",
        "verified": "2026-08-09",
    },
    "HowTo": {
        # Two announcements, not one. August 2023 cut HowTo to desktop only;
        # September 2023 removed it from desktop as well. Recording only the
        # first made the entry read as though the August change was the end
        # of it.
        "changed": "September 2023",
        "status": "deprecated",
        "aliases": "howto, how-to, how to",
        "detail": "Google limited HowTo rich results to desktop in August 2023 "
                  "and removed them from desktop too in September 2023, which "
                  "deprecated the feature outright. The markup validates and "
                  "renders nothing.",
        "instead": "Structure the steps as clear on-page headings for answer "
                   "extraction rather than for a SERP enhancement.",
        "source": "https://developers.google.com/search/blog/2023/08/"
                  "howto-faq-changes",
        "verified": "2026-08-09",
    },
    # --- withdrawn 12 June 2025, "Simplifying the search results page" ------
    # Only the types whose *sole* purpose was the withdrawn feature are listed
    # here, because this table matches on a bare @type and a false positive
    # costs a client an unnecessary rewrite. See DEPRECATED_FEATURES below for
    # the ones that cannot be matched that way.
    "ClaimReview": {
        "changed": "12 June 2025",
        "status": "removed",
        "aliases": "claimreview, claim review, fact check, fact-check",
        "detail": "Fact-check rich results were withdrawn. ClaimReview exists "
                  "only to drive them, so the markup now has no Search effect.",
        "instead": "Keep it if downstream fact-check consumers read it; expect "
                   "nothing from Google Search.",
        "source": "https://developers.google.com/search/blog/2025/06/"
                  "simplifying-search-results",
        "verified": "2026-08-09",
    },
    "SpecialAnnouncement": {
        "changed": "12 June 2025",
        "status": "removed",
        "aliases": "specialannouncement, special announcement",
        "detail": "The special-announcement rich result was withdrawn. The type "
                  "was introduced for it and has no other Search use.",
        "instead": "Put the announcement in ordinary page content where both "
                   "users and answer engines can read it.",
        "source": "https://developers.google.com/search/blog/2025/06/"
                  "simplifying-search-results",
        "verified": "2026-08-09",
    },
}

# Features Google withdrew that this table deliberately does NOT match by
# @type, because the type is still supported for something else and flagging
# it would be a false positive:
#
#   Course Info      uses `Course`      — but Course *list* is still supported
#   Learning Video   uses `VideoObject` — but Video is still supported
#   Estimated Salary uses `Occupation`  — also legitimate outside salary data
#   Vehicle Listing  uses `Vehicle`/`Car` — general automotive markup
#
# A review of this file once proposed adding all of them as deprecated types.
# Doing so would have told every site with a Course or a VideoObject that its
# markup was dead. They are recorded here so the advisor knows the features
# are gone without the deterministic pass raising a finding it cannot justify.
#
# The same review listed Book Actions among the withdrawn types. It was not
# withdrawn — its deprecation banner was removed because a Search feature
# still consumes the markup — so it is absent on purpose. Please do not add it
# back without checking the source below first.
DEPRECATED_FEATURES: dict[str, dict[str, str]] = {
    "Course Info": {
        "changed": "12 June 2025", "status": "removed",
        "types": "Course",
        "detail": "The course-info rich result was withdrawn. Course *list* "
                  "remains supported, so the type itself is still useful.",
        "source": "https://developers.google.com/search/blog/2025/06/"
                  "simplifying-search-results",
        "verified": "2026-08-09",
    },
    "Learning Video": {
        "changed": "12 June 2025", "status": "removed",
        "types": "VideoObject with learningResourceType",
        "detail": "Learning-video enhancements were withdrawn. Ordinary video "
                  "rich results are unaffected.",
        "source": "https://developers.google.com/search/blog/2025/06/"
                  "simplifying-search-results",
        "verified": "2026-08-09",
    },
    "Estimated Salary": {
        "changed": "12 June 2025", "status": "removed",
        "types": "Occupation",
        "detail": "The estimated-salary rich result was withdrawn.",
        "source": "https://developers.google.com/search/blog/2025/06/"
                  "simplifying-search-results",
        "verified": "2026-08-09",
    },
    "Vehicle Listing": {
        "changed": "12 June 2025", "status": "removed",
        "types": "Vehicle, Car",
        "detail": "The vehicle-listing rich result was withdrawn.",
        "source": "https://developers.google.com/search/blog/2025/06/"
                  "simplifying-search-results",
        "verified": "2026-08-09",
    },
}

# Sitelinks search box: the WebSite + SearchAction pattern. Detected
# separately because it is a property pattern, not a bare @type.
#
# Recorded as November 2023 for a long time. It was announced in October 2024
# and the element came out of results from 21 November 2024 — a year out, and
# the giveaway that these dates were recalled rather than read.
SEARCH_ACTION_NOTE = {
    "changed": "November 2024",
    "detail": "The sitelinks search box was withdrawn: announced October 2024 "
              "and removed from results globally from 21 November 2024. "
              "WebSite/potentialAction SearchAction markup no longer drives a "
              "search box.",
    "source": "https://developers.google.com/search/blog/2024/10/"
              "sitelinks-search-box",
    "verified": "2026-08-09",
}

# Google's REQUIRED properties per type for the relevant rich result. Kept
# deliberately short — only properties Google documents as required, so a
# WARNING here is defensible rather than a matter of taste.
REQUIRED_PROPERTIES: dict[str, list[str]] = {
    # `name` only: Product splits into two experiences with different
    # requirements (see PRODUCT_CLASSES), and `name` is the floor both share.
    # Asserting merchant-listing requirements here would raise a blocker on
    # every product page that is not trying to be a merchant listing.
    "Product": ["name"],
    "Article": ["headline"],
    "NewsArticle": ["headline"],
    "BlogPosting": ["headline"],
    "LocalBusiness": ["name", "address"],
    "Organization": ["name"],
    "Event": ["name", "startDate", "location"],
    "Recipe": ["name", "image"],
    # description and jobLocation were missing. Google documents five required
    # properties and this listed three, so a posting could pass here and still
    # be ineligible for the job experience.
    "JobPosting": ["title", "datePosted", "description", "hiringOrganization",
                   "jobLocation"],
    "VideoObject": ["name", "thumbnailUrl", "uploadDate"],
    "BreadcrumbList": ["itemListElement"],
    "Review": ["itemReviewed", "reviewRating", "author"],
    "AggregateRating": ["ratingValue"],
}

#: Where a type's requirements depend on which experience it is aiming at.
#: Handed to the advisor so its recommendation can be specific, and
#: deliberately not enforced by the deterministic pass, which cannot tell from
#: markup alone which experience a page is going for.
PRODUCT_CLASSES = {
    "product snippet": {
        "when": "a product page where the product cannot be bought directly",
        "required": "name, plus one of review, aggregateRating or offers",
    },
    "merchant listing": {
        "when": "a page where the customer can buy the product from you",
        "required": "name, image, and an Offer (not AggregateOffer) carrying "
                    "price greater than zero and priceCurrency",
    },
    "source": "https://developers.google.com/search/docs/appearance/"
              "structured-data/merchant-listing",
    "verified": "2026-08-09",
}

#: Property-level source notes for requirement lists that were checked
#: against Google directly rather than carried over.
REQUIREMENT_SOURCES: dict[str, dict[str, str]] = {
    "JobPosting": {
        "source": "https://developers.google.com/search/docs/appearance/"
                  "structured-data/job-posting",
        "verified": "2026-08-09",
    },
    "Product": {
        "source": "https://developers.google.com/search/docs/appearance/"
                  "structured-data/product",
        "verified": "2026-08-09",
    },
}

# Types where Google requires at least one of a set (documented as "one of").
REQUIRED_ONE_OF: dict[str, list[str]] = {
    "Product": ["offers", "review", "aggregateRating"],
}

# Recommended (not required) — absence degrades rather than blocks.
RECOMMENDED_PROPERTIES: dict[str, list[str]] = {
    "Article": ["image", "datePublished", "author"],
    "NewsArticle": ["image", "datePublished", "author"],
    "BlogPosting": ["image", "datePublished", "author"],
    "Product": ["image", "description", "brand"],
    "LocalBusiness": ["telephone", "openingHoursSpecification", "geo", "url"],
    "Event": ["endDate", "image", "offers", "description"],
    "Organization": ["url", "logo"],
}

LOCAL_BUSINESS_SUBTYPES = ("LocalBusiness", "Plumber", "Roofing", "RoofingContractor",
                           "HomeAndConstructionBusiness", "ProfessionalService",
                           "Restaurant", "Store", "Dentist", "LegalService",
                           "MedicalBusiness", "AutomotiveBusiness")


def dated_entries() -> dict[str, dict[str, str]]:
    """Every fact in this file that claims a source and a verification date,
    flattened into one mapping so nothing can be added without being covered.

    Keyed by a label that identifies where to look, because the failure this
    supports has to tell a reviewer which page to open."""
    out: dict[str, dict[str, str]] = {}
    for name, info in DEPRECATED_RICH_RESULTS.items():
        out[f"DEPRECATED_RICH_RESULTS[{name!r}]"] = info
    for name, info in DEPRECATED_FEATURES.items():
        out[f"DEPRECATED_FEATURES[{name!r}]"] = info
    for name, info in REQUIREMENT_SOURCES.items():
        out[f"REQUIREMENT_SOURCES[{name!r}]"] = info
    out["SEARCH_ACTION_NOTE"] = SEARCH_ACTION_NOTE
    out["PRODUCT_CLASSES"] = PRODUCT_CLASSES
    return out


def stale_entries(today: date | None = None,
                  window_days: int = REVIEW_AFTER_DAYS) -> list[tuple[str, int, str]]:
    """Entries not checked against their source inside the review window.

    Returns (label, days since verified, source URL), oldest first. This
    cannot tell whether Google has changed anything — no offline check can.
    What it can do is refuse to let a table whose whole job is currency go
    unexamined indefinitely, which is the failure that actually happened:
    three dates recalled rather than read, and nothing in the system with an
    opinion about how old a fact was allowed to get.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=window_days)
    stale: list[tuple[str, int, str]] = []
    for label, info in dated_entries().items():
        checked = datetime.strptime(info["verified"], "%Y-%m-%d").date()
        if checked < cutoff:
            stale.append((label, (today - checked).days, info["source"]))
    return sorted(stale, key=lambda row: -row[1])


def verification_note() -> str:
    """One line for the advisor's evidence bundle saying how old this table
    is, so a model is not asked to defer to it blindly.

    The advisor is told to prefer this table over its own recollection, which
    is right while the table is fresh and exactly wrong once it is not — a
    stale entry would otherwise silence a model that knew the current answer.
    """
    dates = sorted(info["verified"] for info in dated_entries().values())
    stale = stale_entries()
    if not stale:
        return (f"Every entry was checked against its Google source between "
                f"{dates[0]} and {dates[-1]}.")
    return (f"Checked between {dates[0]} and {dates[-1]}, but {len(stale)} "
            f"entr{'y is' if len(stale) == 1 else 'ies are'} past the "
            f"{REVIEW_AFTER_DAYS}-day review window "
            f"({', '.join(label for label, _, _ in stale[:4])}). Treat those as "
            "possibly out of date: if you believe one has changed, say so in "
            "the report rather than silently following it.")


def parse_blocks(blocks: list[str]) -> tuple[list[dict], list[str]]:
    """Flatten every JSON-LD block into a list of entities, expanding @graph
    and top-level arrays. Returns (entities, parse_errors)."""
    entities: list[dict] = []
    errors: list[str] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        entities.extend(_flatten(data))
    return entities, errors


def _flatten(data: Any) -> list[dict]:
    out: list[dict] = []
    if isinstance(data, list):
        for item in data:
            out.extend(_flatten(item))
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, (list, dict)):
            out.extend(_flatten(graph))
            rest = {k: v for k, v in data.items() if k != "@graph"}
            if any(k for k in rest if not k.startswith("@")):
                out.append(rest)
        else:
            out.append(data)
    return out


def types_of(entity: dict) -> list[str]:
    value = entity.get("@type", "")
    values = value if isinstance(value, list) else [value]
    return [str(v) for v in values if v]


def normalise_type(type_name: str) -> str:
    """Map a LocalBusiness subtype onto its requirement set."""
    if type_name in REQUIRED_PROPERTIES:
        return type_name
    if type_name in LOCAL_BUSINESS_SUBTYPES:
        return "LocalBusiness"
    return type_name


def audit_entities(entities: list[dict]) -> list[dict]:
    """Deterministic structured-data issues. Each is a dict with kind, type,
    severity_hint and a human summary — the module turns them into Findings
    and the advisor receives them as evidence."""
    issues: list[dict] = []
    seen_ids: dict[str, int] = {}

    for entity in entities:
        raw_types = types_of(entity)
        if not raw_types:
            issues.append({
                "kind": "untyped-entity", "type": None, "severity_hint": "medium",
                "summary": "A JSON-LD entity declares no @type, so search engines "
                           "cannot interpret it.",
            })
            continue

        entity_id = entity.get("@id")
        if isinstance(entity_id, str):
            seen_ids[entity_id] = seen_ids.get(entity_id, 0) + 1

        for raw in raw_types:
            type_name = normalise_type(raw)

            if raw in DEPRECATED_RICH_RESULTS:
                info = DEPRECATED_RICH_RESULTS[raw]
                issues.append({
                    "kind": "deprecated-rich-result", "type": raw,
                    "severity_hint": "info",
                    "changed": info["changed"],
                    "summary": f"{raw} no longer earns a rich result "
                               f"({info['changed']}): {info['detail']}",
                    "instead": info["instead"],
                })

            missing = [p for p in REQUIRED_PROPERTIES.get(type_name, [])
                       if not entity.get(p)]
            if missing:
                issues.append({
                    "kind": "missing-required", "type": raw,
                    "severity_hint": "medium", "properties": missing,
                    "summary": f"{raw} is missing Google-required propert"
                               f"{'y' if len(missing) == 1 else 'ies'}: "
                               f"{', '.join(missing)}.",
                })

            one_of = REQUIRED_ONE_OF.get(type_name, [])
            if one_of and not any(entity.get(p) for p in one_of):
                issues.append({
                    "kind": "missing-one-of", "type": raw,
                    "severity_hint": "medium", "properties": one_of,
                    "summary": f"{raw} needs at least one of: {', '.join(one_of)}.",
                })

            recommended = [p for p in RECOMMENDED_PROPERTIES.get(type_name, [])
                           if not entity.get(p)]
            if recommended:
                issues.append({
                    "kind": "missing-recommended", "type": raw,
                    "severity_hint": "low", "properties": recommended,
                    "summary": f"{raw} omits recommended propert"
                               f"{'y' if len(recommended) == 1 else 'ies'}: "
                               f"{', '.join(recommended)}.",
                })

        if raw_types and "WebSite" in raw_types:
            action = entity.get("potentialAction")
            actions = action if isinstance(action, list) else [action]
            if any(isinstance(a, dict) and "SearchAction" in str(a.get("@type", ""))
                   for a in actions if a):
                issues.append({
                    "kind": "deprecated-rich-result", "type": "SearchAction",
                    "severity_hint": "info",
                    "changed": SEARCH_ACTION_NOTE["changed"],
                    "summary": "The sitelinks search box was deprecated "
                               f"({SEARCH_ACTION_NOTE['changed']}); this "
                               "WebSite/SearchAction markup no longer produces one.",
                    "instead": "Harmless to keep, but do not expect a search box.",
                })

    for entity_id, count in sorted(seen_ids.items()):
        if count > 1:
            issues.append({
                "kind": "duplicate-id", "type": None, "severity_hint": "low",
                "properties": [entity_id],
                "summary": f"@id {entity_id} is declared by {count} entities, so "
                           "references resolve ambiguously.",
            })
    return issues
