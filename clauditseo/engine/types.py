"""Typed results the audit engine produces and the persistence layer stores.

The engine never touches the database; these types are the contract between
the layers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Tier(str, Enum):
    T1 = "T1"  # Pulse: homepage + robots + sitemap head, < 2 min, no paid APIs
    T2 = "T2"  # Standard: up to 100 pages, all applicable free checks
    T3 = "T3"  # Deep: full crawl to 500 pages, paid APIs where keys exist


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def fingerprint(dimension: str, check_id: str, subject: str) -> str:
    """Stable identity of an issue across runs.

    `subject` is the normalised thing the finding is about (usually a URL path
    or a duplicate-group key), lower-cased and stripped so cosmetic changes
    don't break continuity.
    """
    norm = subject.strip().lower().rstrip("/") or "/"
    return hashlib.sha256(f"{dimension}:{check_id}:{norm}".encode()).hexdigest()[:24]


@dataclass
class Finding:
    dimension: str
    check_id: str
    severity: Severity
    summary: str
    subject: str                      # normalised subject; drives the fingerprint
    affected_urls: list[str] = field(default_factory=list)
    #: How many URLs this finding is about, before the emitter capped the
    #: list beside it. `None` means no cap was applied and `affected_urls` is
    #: whole — which is the ordinary case and why it is the default.
    #:
    #: `QUESTIONS.md` Q-26, answered *store the frame* on 2026-08-29. Four
    #: emitters slice this list (`tec.sitemap-coverage`, `loc.nap-inconsistent`,
    #: `prf.caching-headers`, `prf.third-party-scripts`) and `anatomy_view`
    #: slices what they stored a second time. Neither cut carried a frame, so
    #: by the time the section screen wrote a sentence the two were
    #: indistinguishable: `www.acme.com.au` read *"51 of 272 sitemap URL(s)
    #: were not reachable"*, `PAGES 20`, and *"Showing 10 of 20 — the rest are
    #: stored"*, of which the last clause was false for 31 of the 51 (UX-93).
    #:
    #: Set by the EMITTER, like `scope_statement` and for the same reason: the
    #: code that cut the list is the only code that ever saw the whole of it.
    #: Stored — unlike `scope_statement` — because the consumer is a screen
    #: reading a row back weeks later rather than `_apply_states` at emission.
    affected_total: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    source: str = "deterministic"     # deterministic | model-judgement
    model_id: str | None = None
    confidence: Confidence = Confidence.HIGH
    #: This finding states something about the AUDIT — how far it reached,
    #: what it had no key or renderer for, what it recorded for reference —
    #: rather than a condition of the site. The lifecycle needs it: `fixed ->
    #: regressed` means "a defect we verified gone has come back", and that
    #: word is never true of a scope statement. A narrower run re-raises the
    #: statement that it is narrower, and on 24 August 2026 the 24-page verify
    #: of `www.acme.com.au` recorded two of those as regressions of a fixed
    #: defect (Q-21, WF-101).
    #:
    #: The test is: does this finding appear because of HOW THE RUN WAS MADE —
    #: its scope, tier, crawl, keys, renderer, providers — or because of what
    #: the site contains? Only the first is flagged. `extractability-not-assessed`
    #: and `axe-render-failed` are deliberately NOT, despite naming a
    #: non-assessment: both appear because of the page, so a page that was
    #: server-rendered and stopped being so is a real regression and must
    #: still fire.
    #:
    #: Set by the EMITTER and never inferred by a consumer. `severity == info`
    #: was the obvious inference and it is wrong in both directions — five of
    #: the six standing `info` rows on that site describe the run and one does
    #: not, and `sitemap-coverage-not-assessed` is not the only non-`info`
    #: candidate. The operator's answer to Q-21 named the mechanism as well as
    #: the rule: "the code that raises a scope statement knows it is one:
    #: carry an explicit flag from the emitter rather than inferring from
    #: severity" (2026-08-25).
    #:
    #: Not stored on the `findings` row. The only consumer is `_apply_states`,
    #: which runs at emission with the `AuditResult` in hand, so a column would
    #: be a migration for a value nothing reads back. The `-not-assessed`
    #: suffix tests in `reporting/render.py` and `playbook.py` ask a narrower
    #: question — "did this check measure nothing" — and are left alone; a
    #: guard enumerates the two sets against each other.
    scope_statement: bool = False

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.dimension, self.check_id, self.subject)


@dataclass
class SubScore:
    dimension: str
    score: float            # 0-100
    weight: float           # weight actually used (post-redistribution)
    applicable: bool = True
    # How much of what this dimension is meant to measure it actually
    # measured, 0-1. Below 1 when a signal needs a provider key that is not
    # configured. A score of 100 out of a coverage of 0.5 means "half of this
    # was clean and the other half was never looked at" — two very different
    # statements that used to render as the same number.
    coverage: float = 1.0
    unmeasured: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Site:
    """What a module needs to know about the site under audit."""
    domain: str
    locale: str = "en-AU"
    business_type: str | None = None
    target_market: str | None = None
    #: The brand the site's copy carries (brief v11 step AI); None means not
    #: set on the record.
    brand: str | None = None
    #: The local-SEO record the briefs read (brief v11 step AI); None means
    #: not set, and each prompt states its fallback.
    gbp_primary_category: str | None = None
    service_area_entity: str | None = None
    title_strategy: str | None = None
    neighbourhoods: list | None = None
    entity_variants: dict | None = None
    sub_services: list | None = None
    location_pages: list | None = None
    page_types: dict | None = None
    #: What the Images brief reads (brief v15 step AQ). Empty is not an
    #: error: the prompt states a fallback for each and lists the
    #: inference under the run's assumptions.
    platform: str | None = None
    cdn_or_image_pipeline: str | None = None
    breakpoints: list | None = None
    budget_lcp_kb: str | None = None
    budget_page_kb: str | None = None
    review_provenance: str | None = None
    priority_internal_targets: list | None = None
    #: What "too heavy" is for one image, and what the re-encode probe
    #: encodes at when it measures the saving (brief v16 step AU7). The
    #: page budget above is a budget for a page: a heavy image below the
    #: fold of an otherwise light page sits inside it and says nothing.
    budget_image_kb: str | None = None
    bytes_per_pixel: str | None = None
    reencode_quality: str | None = None
    #: The smallest file the bytes-per-pixel rule speaks about, as a
    #: stated parameter rather than a constant (operator, 2026-09-06).
    #: `None` means the engine's own default, which `images.md` states.
    budget_image_floor_kb: str | None = None
    #: What the Structured data brief reads (brief v16 step AS): the exact
    #: NAP, the profiles the entity controls against the places that merely
    #: mention it, whether the business is one node or many, and the `@id`
    #: everything is meant to point at.
    nap: str | None = None
    sameas_sources: list | None = None
    #: Item 145 step BH (migration 0063): the three fields `ai-surface.md`
    #: names. `legal_name` is the registered entity where it differs from
    #: `brand`; `registered_ids` are free strings; `external_profiles` are
    #: `{"url", "claimed"}` maps, `claimed` being the operator's word.
    legal_name: str | None = None
    registered_ids: list | None = None
    external_profiles: list | None = None
    citation_sources: list | None = None
    locations: str | None = None
    id_page_uri: str | None = None
    canonical_id: str | None = None
    target_rich_results: dict | None = None
    #: What the Content prompts read (brief v17 step AX). The two floors
    #: override the engine's placeholders: 300 words for a service page is
    #: a number somebody chose, and a client whose service pages are two
    #: hundred words of specifics is not a client with fifty findings.
    #: `authors` and `proof_assets` are what a replacement may draw on -
    #: without them a row that would have named a credential returns
    #: `kind: content-first` naming the fact the client must supply, which
    #: is the difference between writing copy and inventing qualifications
    #: for somebody. The last four are Benchmark's prerequisites and are
    #: empty until an operator fills them; every Benchmark row is held
    #: until they are.
    word_floors: dict | None = None
    mandatory_formats: dict | None = None
    authors: list | None = None
    proof_assets: list | None = None
    competitors: list | None = None
    keyword_data: dict | None = None
    top10_corpus: dict | None = None
    publish_history: dict | None = None
    #: What the client plan reads (brief v18 step AY). These are the only
    #: brief inputs that are decisions rather than measurements: how much
    #: effort goes to existing pages, what the horizons are called, which
    #: workstreams the client recognises, what they can absorb, and what
    #: can be measured at all. All empty by default, and the prompt prints
    #: its own fallback as an assumption - which it can only do while
    #: absence stays legible, so nothing is defaulted here.
    optimisation_ratio: str | None = None
    horizons: list | None = None
    workstreams: list | None = None
    capacity: str | None = None
    measure_sources: list | None = None
    #: The CDN/WAF in front of the origin (brief v18 step AZ, task 4). Names
    #: where a UA refusal is enforced, so the crawl brief can open
    #: `ua-server-refusal` against an address; empty keeps it HELD. Carried on
    #: the Site because `site_of` builds one from every `SITE_TEXT_FIELDS` key.
    cdn_or_waf: str | None = None
    #: The indexability brief's three fields (brief v18 step BA), each gating a
    #: held analysis check until it is set. Two lists and an old->new map,
    #: carried here for the same reason as the fields above: `site_of` builds a
    #: Site from every `SITE_JSON_FIELDS` key.
    intended_noindex: list | None = None
    migration_map: dict | None = None
    parameter_rules: list | None = None
    #: The URLs & parameters brief's four thresholds (brief v19 step BB),
    #: stored as text like the budget fields and parsed on use. Blank keeps
    #: `urlshape`'s defaults (75 chars / 6 slug words / depth 3 / rename cap
    #: 20). Carried here because `site_of` builds a Site from every
    #: `SITE_TEXT_FIELDS` key.
    url_max_chars: str | None = None
    slug_max_words: str | None = None
    max_depth: str | None = None
    rename_inlink_cap: str | None = None
    #: The Speed brief's vital budgets and framework (brief v19 step BC), stored
    #: as text and parsed on use; blank keeps Google's own thresholds. The page
    #: weight budget is the existing `budget_page_kb`. `third_party_map` is the
    #: host -> what it is -> business purpose map third-party-policy reads.
    lcp_good: str | None = None
    cls_good: str | None = None
    inp_good: str | None = None
    ttfb_good: str | None = None
    framework: str | None = None
    #: The Security brief's stack, as the operator states it (item 143 step
    #: BD): origin, edge and CMS. Blank means inferred from headers.
    stack: str | None = None
    #: The Security brief's held-domain inputs (brief v20 step BD). Recorded
    #: and shown to the brief; nothing in this build acts on any of them.
    active_probing_authorised: str | None = None
    reputation_source: str | None = None
    plugin_directory_feed: str | None = None
    third_party_map: dict | None = None
    #: Where real-user Core Web Vitals come from for this site — a CrUX API key
    #: or a Search Console connection (brief v19 step BC). Empty on every site
    #: today, and the Speed part's field-distribution bar renders greyed with
    #: what to connect rather than as zeros: `good 0 · NI 0 · poor 0` is a
    #: claim about the site, not about our data.
    field_data_source: str | None = None
    #: The client's stated policy on AI agents, 'allow' / 'block' / None (item
    #: 145 step BG). `ai-crawler-blocked` reads it for its severity.
    ai_crawler_policy: str | None = None
    #: Where per-agent server counts come from (145 addendum); empty today.
    ai_field_data_source: str | None = None
    #: Agents refused at the edge on purpose, comma-separated tokens (item 145
    #: BG, migration 0062). `edge-blocks-ai-ua` reads it for its severity.
    ai_edge_blocked_agents: str | None = None


def evidence_hash(payload: Any) -> str:
    """Canonical hash of an evidence bundle — the analyst cache key input."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
