"""SCHEMA-J — structured-data auditor and remediation specialist.

Diagnoses before it prescribes: Part 1 reports what the page has, lacks and
can legitimately support; Part 2 supplies the corrected JSON-LD. The split is
enforced by the output shape, not merely requested.

Two things keep it honest. Deprecation facts are supplied as evidence from
`schema_rules`, so the model cannot recommend markup Google stopped
rewarding — the failure that prompted this module was an advisor cheerfully
suggesting FAQPage for rich-result eligibility. And every marked-up value
must correspond to content visible on the page: anything unsupported must be
emitted as `[TO CONFIRM: property]` rather than invented, which the ingest
check enforces.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from clauditseo.config import Settings
from clauditseo.engine.types import evidence_hash
from clauditseo.modules.pagefacts import extract_facts
from clauditseo.schema_rules import (DEPRECATED_FEATURES, DEPRECATED_RICH_RESULTS,
                                    PRODUCT_CLASSES, RECOMMENDED_PROPERTIES,
                                    REQUIRED_ONE_OF, REQUIRED_PROPERTIES,
                                    SEARCH_ACTION_NOTE, audit_entities, parse_blocks,
                                    types_of, verification_note)

__all__ = ["TASK", "SYSTEM_PROMPT", "FINDINGS_PROMPT", "FIXES_PROMPT",
           "build_schema_bundle", "parse_audit", "validate_audit", "audit_schema"]

TASK = "SCHEMA-J"
PAGE_TEXT_CAP = 5000
# Generous: the answer carries a full JSON-LD document, and the model may
# spend output budget reasoning before it writes anything.
OUTPUT_TOKENS = 16000

SYSTEM_PROMPT = (
    "You are a structured data auditor and remediation specialist working in "
    "Schema.org vocabulary with JSON-LD output, validated against Google "
    "Search's structured data requirements. You know the difference between "
    "what Schema.org permits and what Google actually requires for rich "
    "result eligibility, and you treat the latter as binding.\n\n"
    "FINDINGS BEFORE FIXES is a hard rule. Diagnose the page completely "
    "before proposing any markup.\n\n"
    "RULES:\n"
    "- NO FABRICATION. Never invent prices, ratings, review counts, dates, "
    "authors, IDs or image URLs. Any value the page does not supply must be "
    "written as a placeholder in the form [TO CONFIRM: property.path]. A "
    "fabricated value is a policy violation, not a formatting shortcut.\n"
    "- Markup must correspond to content visible to users on the page. If a "
    "property would require content the page does not show, say so and flag "
    "the manual-action risk instead of emitting it.\n"
    "- CONFLICT RULE: where Schema.org permits something Google restricts, "
    "Google governs; where Google is silent, Schema.org governs. Say which "
    "applied whenever they diverge.\n"
    "- The evidence bundle contains a `google_rich_result_status` table of "
    "types Google has deprecated or narrowed. Prefer it over your own "
    "recollection: it is maintained against Google's own pages and each entry "
    "carries the URL it came from and the date it was last read. Never "
    "present a deprecated type as a route to rich-result eligibility; report "
    "the deprecation, name what the markup is still good for, and do not emit "
    "dead markup as a fix.\n"
    "- That table is not infallible and its own currency is the thing most "
    "likely to be wrong with it. `verified_status` says when it was last "
    "checked. If you have specific reason to believe an entry is out of date, "
    "SAY SO EXPLICITLY in the report — name the entry, what you believe "
    "changed, and that it needs confirming — rather than either silently "
    "following it or silently overriding it. A disagreement surfaced is "
    "useful; a disagreement suppressed is how a table like this rots.\n"
    "- Do not mark up an entity the page is not primarily about.\n"
    "- Severity is assigned against Google's documented requirements, not "
    "taste: BLOCKER prevents eligibility, DEGRADES weakens it, ADVISORY has "
    "no eligibility impact. Do not inflate an advisory into a blocker.\n"
    "- ISO 8601 dates and durations, ISO 4217 currency codes, absolute URLs, "
    "@id for entity references. Australian English prose; never translate "
    "Schema.org property names.\n"
    "- Every issue in the register must appear exactly once in the fix map.\n\n"
    "BE BRIEF in prose fields: one or two sentences each, never a paragraph. "
    "The JSON-LD may be as long as it needs to be. A complete answer that "
    "fits is worth more than a thorough one truncated mid-object.\n\n"
)

# The audit is produced in two calls, mirroring its own findings-before-fixes
# rule. One call cannot fit both halves: a full validation table plus a
# complete JSON-LD document exceeds any sane output cap, and a truncated
# answer is worth nothing.
FINDINGS_PROMPT = SYSTEM_PROMPT + (
    "\nThis is PART 1: DIAGNOSIS ONLY. Do not propose fixes or write markup — "
    "a later call will do that. Cover the properties that matter for the "
    "target rich results, Required first then Recommended, at most 20 rows.\n"
    "Respond with ONE JSON object and no prose around it:\n"
    "{\"assumptions\": [str],\n"
    " \"verdict\": [{\"rich_result\": str, \"status\": "
    "\"ELIGIBLE\"|\"NOT ELIGIBLE\"|\"ELIGIBLE BUT DEGRADED\"|\"NOT AVAILABLE\", "
    "\"reason\": str}],\n"
    " \"current_state\": [str],\n"
    " \"content_readiness\": {\"supported\": [str], \"needs_new_content\": [str], "
    "\"hidden_markup_risk\": [str]},\n"
    " \"validation\": [{\"property\": str, \"status\": "
    "\"PASS\"|\"WARNING\"|\"ERROR\"|\"MISSING\", \"requirement\": "
    "\"Required\"|\"Recommended\"|\"Optional\", \"finding\": str}],\n"
    " \"issues\": [{\"n\": int, \"severity\": \"BLOCKER\"|\"DEGRADES\"|"
    "\"ADVISORY\", \"issue\": str}]}"
)

FIXES_PROMPT = SYSTEM_PROMPT + (
    "\nThis is PART 2: REMEDIATION. The diagnosis is supplied in the bundle "
    "as `part_1_findings`. Address every numbered issue from it exactly once "
    "in the fix map. Emit the corrected JSON-LD as a STRING in the "
    "corrected_jsonld field.\n"
    "Respond with ONE JSON object and no prose around it:\n"
    "{\"type_selection\": str,\n"
    " \"corrected_jsonld\": str,\n"
    " \"fix_map\": [{\"n\": int, \"severity\": str, \"fix\": str, \"where\": "
    "\"markup\"|\"on-page content\"|\"CMS config\"|\"no fix available\"}],\n"
    " \"on_page_changes\": [str],\n"
    " \"implementation\": [str],\n"
    " \"revalidation\": [str]}"
)


def build_schema_bundle(page, page_findings: list[dict], site: Any,
                        cms: str | None = None) -> dict:
    """Parsed structured data, the deterministic issues already found, and the
    Google status table — so the model audits real entities rather than
    re-parsing HTML, and cannot mis-remember a deprecation."""
    facts = extract_facts(page)
    entities, parse_errors = parse_blocks(facts.jsonld_blocks)
    declared_types = sorted({t for e in entities for t in types_of(e)})

    return {
        "task": TASK,
        "page": {
            "url": page.url,
            "path": facts.path,
            "title_tag": facts.title,
            "meta_description": facts.meta_description,
            "headings": facts.headings,
            "word_count": facts.word_count,
            "image_count": len(facts.images),
            "untrusted_page_text": facts.text[:PAGE_TEXT_CAP],
        },
        "existing_structured_data": {
            "block_count": len(facts.jsonld_blocks),
            "parse_errors": parse_errors,
            "declared_types": declared_types,
            "entities": entities[:25],
        },
        "deterministic_schema_issues": audit_entities(entities),
        "deterministic_page_findings": page_findings,
        "google_rich_result_status": {
            "deprecated_or_restricted": DEPRECATED_RICH_RESULTS,
            # Features Google withdrew whose @type is still legitimate for
            # something else. Given to the model so its prose is right, and
            # never matched deterministically, because flagging every Course
            # or VideoObject as dead markup would be a false positive.
            "withdrawn_features_not_matched_by_type": DEPRECATED_FEATURES,
            "sitelinks_search_box": SEARCH_ACTION_NOTE,
            "product_experiences": PRODUCT_CLASSES,
            # How old this table is, in the table itself. Asking a model to
            # defer to a fact without telling it how stale the fact might be
            # is how a stale entry silences a model that knew better.
            "verified_status": verification_note(),
            "note": "Preferred over recollection for this audit. A type listed "
                    "here must not be presented as a route to rich-result "
                    "eligibility. Each entry names its Google source and the "
                    "date it was last read; flag anything you believe has "
                    "changed since rather than following it silently.",
        },
        "google_requirements": {
            "required": REQUIRED_PROPERTIES,
            "required_one_of": REQUIRED_ONE_OF,
            "recommended": RECOMMENDED_PROPERTIES,
        },
        "site": {
            "domain": getattr(site, "domain", ""),
            "locale": getattr(site, "locale", "en-AU"),
            "business_type": getattr(site, "business_type", None),
        },
        "cms": cms or "unknown",
    }


def parse_audit(raw: str, require: str = "verdict") -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or require not in data:
        return None
    return data


def validate_audit(audit: dict, bundle: dict) -> list[str]:
    """Reject markup that would put invented values on a client's page, or
    that recommends a deprecated type as an eligibility route."""
    problems: list[str] = []
    jsonld = str(audit.get("corrected_jsonld") or "")

    if jsonld.strip():
        try:
            json.loads(jsonld)
        except json.JSONDecodeError as exc:
            problems.append(f"the corrected JSON-LD does not parse: {exc}")

    # Figures in proposed markup must come from the page, unless flagged
    # [TO CONFIRM: ...] — placeholders are the sanctioned way to say "unknown".
    from clauditseo.numbers import extract_numbers, ungrounded
    page_text = json.dumps(bundle["page"], ensure_ascii=False, default=str)
    existing = json.dumps(bundle["existing_structured_data"], ensure_ascii=False,
                          default=str)
    allowed = extract_numbers(page_text + existing)
    stripped = re.sub(r"\[TO CONFIRM:[^\]]*\]", "", jsonld)
    # Dates and times are structural encodings, not claims about the business:
    # "opens": "07:00" is the ISO rendering of a visible "7am", which no
    # literal match against page text could ever confirm.
    stripped = re.sub(r"\d{4}-\d{2}-\d{2}(?:T[\d:+.Zz-]+)?", "", stripped)
    stripped = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", "", stripped)
    bad = ungrounded(stripped, allowed)
    if bad:
        problems.append("proposed markup contains figure(s) not present on the "
                        f"page and not marked [TO CONFIRM]: {', '.join(bad[:5])}")

    # A deprecated type may be discussed, but must not be sold as eligibility,
    # however the model phrases the rich result's name.
    for type_name, info in DEPRECATED_RICH_RESULTS.items():
        aliases = [a.strip() for a in
                   (info.get("aliases") or type_name).lower().split(",") if a.strip()]
        for entry in audit.get("verdict") or []:
            label = str(entry.get("rich_result", "")).lower()
            if any(alias in label for alias in aliases) \
                    and str(entry.get("status", "")).upper() == "ELIGIBLE":
                problems.append(
                    f"claims {type_name} rich-result eligibility, which Google "
                    f"{info['status']} in {info['changed']}")
    return problems


def audit_schema(conn: sqlite3.Connection, run_id: str, url: str, site: Any,
                 cfg: Settings, provider, cms: str | None = None) -> dict:
    """On-demand structured-data audit for one page."""
    from clauditseo.crawler.fetch import Fetcher
    from clauditseo.crawler.robots import RobotsPolicy, robots_url_for
    from clauditseo.crawler.types import USER_AGENT
    from clauditseo.persistence import runs as runs_repo

    from .base import cache_version

    if provider is None:
        return {"status": "unavailable",
                "reason": "no LLM provider configured — set ANTHROPIC_API_KEY"}

    stored = runs_repo.run_findings(conn, run_id)
    page_findings = [
        {"check_id": f["check_id"], "severity": f["severity"], "summary": f["summary"]}
        for f in stored
        if f["source"] == "deterministic" and url in f["affected_urls"]
    ]

    with Fetcher(timeout_s=15) as fetcher:
        robots_page = fetcher.fetch(robots_url_for(url))
        policy = RobotsPolicy(robots_page.url, robots_page.status or None,
                              robots_page.content)
        if not policy.allows(url, USER_AGENT):
            return {"status": "unavailable",
                    "reason": "robots.txt disallows fetching this page"}
        page = fetcher.fetch(url)

    if page.error or page.status != 200:
        return {"status": "unavailable",
                "reason": f"could not fetch the page ({page.error or page.status})"}

    bundle = build_schema_bundle(page, page_findings, site, cms)
    bundle_hash = evidence_hash(bundle)
    cache_key = f"{TASK}#{cache_version()}"
    cached = conn.execute(
        "SELECT result FROM analyst_cache WHERE task=? AND model_id=? AND bundle_hash=?"
        " AND created_at > datetime('now', '-30 days')",
        (cache_key, provider.model_id, bundle_hash)).fetchone()
    if cached:
        stored_audit = json.loads(cached["result"])
        return {"status": "ok", "cached": True, "tokens": 0,
                "model": provider.model_id, "audit": stored_audit,
                "warnings": validate_audit(stored_audit, bundle)}

    totals = {"in": 0, "out": 0}   # accumulated across both phases

    def ask(prompt: str, payload: dict, require: str) -> tuple[dict | None, int, str]:
        try:
            if hasattr(provider, "run_agent"):
                response = provider.run_agent(prompt, payload, None,
                                              cfg.llm_budget_page,
                                              max_output=OUTPUT_TOKENS)
            else:
                response = provider.analyse(payload, TASK, cfg.llm_budget_page)
        except Exception as exc:  # a provider failure is reportable, not a 500
            return None, 0, f"the model provider failed: {type(exc).__name__}: {exc}"
        totals["in"] += response.tokens_in
        totals["out"] += response.tokens_out
        used = response.tokens_in + response.tokens_out
        parsed = parse_audit(response.text, require)
        if parsed is not None:
            return parsed, used, ""
        if response.stop == "max_tokens":
            why = "the model ran out of output budget before finishing"
        elif not (response.text or "").strip():
            why = f"the model returned no text (stop reason: {response.stop})"
        else:
            why = "the model's answer was not valid JSON"
        return None, used, why

    # Part 1: diagnosis.
    findings, spent, why = ask(FINDINGS_PROMPT, bundle, "verdict")
    if findings is None:
        return {"status": "empty", "tokens": spent, "model": provider.model_id,
                "reason": why}

    # Part 2: remediation, given the diagnosis. A failure here still leaves a
    # useful audit, so the findings are returned rather than discarded.
    fixes, fix_spent, fix_why = ask(FIXES_PROMPT,
                                    {**bundle, "part_1_findings": findings},
                                    "corrected_jsonld")
    spent += fix_spent
    audit = dict(findings)
    if fixes is None:
        audit["fixes_unavailable"] = fix_why
    else:
        audit.update(fixes)

    # Warn rather than discard. Unlike the page advisor's copy, this markup is
    # not applied automatically — the operator pastes it deliberately — so a
    # complete diagnosis plus a loud "verify these values" is worth more than
    # throwing the whole audit away over one unverifiable figure.
    warnings = validate_audit(audit, bundle)

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO analyst_cache (task, model_id, bundle_hash,"
            " result, tokens_in, tokens_out, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (cache_key, provider.model_id, bundle_hash, json.dumps(audit),
             totals["in"], totals["out"]))
    from clauditseo.persistence.runs import log_cost
    prices = cfg.model_prices.get(provider.model_id)
    log_cost(conn, run_id, getattr(provider, "name", "llm"),
             f"{TASK}:{urlsplit(url).path or '/'}", "tokens", spent,
             actual_cost=(round(totals["in"] / 1e6 * prices[0]
                                + totals["out"] / 1e6 * prices[1], 6)
                          if prices else None))
    return {"status": "ok", "cached": False, "tokens": spent,
            "model": provider.model_id, "audit": audit, "warnings": warnings}
