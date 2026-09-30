"""Analyst layer orchestration: task loop, cache, budgets, ingest validation.

Runs after the deterministic modules and before persistence, so security
notes join the normal state machine while analyst findings stay commentary.
T1 never invokes this layer. Cache hits spend zero tokens and are logged as
such so the cost log can prove it.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from clauditseo.config import Settings
from clauditseo.crawler.types import CrawlResult
from clauditseo.engine.core import AuditResult
from clauditseo.engine.types import Finding, Tier

from .anthropic_provider import AnthropicAnalyst
from .base import (TASK_DIMENSION, TASKS, AnalystFindingDraft, AnalystProvider,
                   build_bundle, draft_to_finding, validate_draft)

EST_OUTPUT_TOKENS = 1000


def provider_from_settings(cfg: Settings,
                           model: str | None = None) -> AnalystProvider | None:
    """`model` overrides the configured default for one run. The mock
    provider ignores it (its output is model-independent by design)."""
    if cfg.llm_provider == "mock":
        from .mock import MockAnalyst
        return MockAnalyst()
    if cfg.anthropic_api_key:
        return AnthropicAnalyst(cfg.anthropic_api_key, model or cfg.llm_model)
    return None


@dataclass
class TaskSpend:
    task: str
    cached: bool = False
    skipped: str | None = None      # reason, when the budget cut this task
    tokens_in: int = 0
    tokens_out: int = 0
    accepted: int = 0
    rejected: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    stop: str | None = None         # end_turn | budget | max_rounds (fresh runs)


@dataclass
class AnalystOutcome:
    ran: bool
    findings: list[Finding] = field(default_factory=list)
    security_findings: list[Finding] = field(default_factory=list)
    spends: list[TaskSpend] = field(default_factory=list)
    estimated_tokens: int = 0
    spent_tokens: int = 0
    reason_not_run: str | None = None


#: Characters per token for the content this layer sends (item 141 step BC,
#: 2026-09-12). Four was the figure here for the layer's whole life and it is a
#: PROSE ratio; what actually goes into a bundle is crawl data — URLs, numbers,
#: header names, punctuation — which tokenises far worse.
#:
#: **Measured**, on the Speed brief's rendered prompt against twenty22 run
#: `95ac5495`: 124,256 characters became **53,225** billed tokens, a ratio of
#: **2.33**. At four, the same prompt estimates 31,064 — a 1.71× under-read.
#:
#: **Rounded DOWN to 2.3, and the direction is the whole point.** Chars per
#: token is a DIVISOR, so a larger ratio yields FEWER estimated tokens: 2.4
#: estimates 51,773 for that prompt, which is 2.7% BELOW what it billed. I wrote
#: 2.4 first, for safety, having got that backwards — the asymmetric bound in
#: `test_the_token_estimate_is_within_reach_of_what_a_real_run_billed` is what
#: caught it, and it is asymmetric for exactly this reason.
#:
#: Why low is the dangerous direction: `run_analyst_layer` gates each task on
#: `spent + est > budget_cap`. An estimate that reads low does not merely
#: mislead a display — it lets a task through the cap that should have been
#: skipped, so the cap is overrun in the one direction nobody is watching.
#: Over-reading skips a task that would have fitted, which is visible and
#: recoverable; under-reading spends money nobody authorised. 2.3 estimates
#: 54,024 against a billed 53,225: over by 1.5%, on the safe side.
#:
#: **One measurement is a thin basis for a constant and this comment is the
#: warning label.** It is one prompt, on one site, from one brief. It replaces a
#: figure that had no measurement at all and is wrong in the safe direction, so
#: it is an improvement rather than an answer. A second measurement on a real
#: analyst bundle should replace it.
CHARS_PER_TOKEN = 2.3


def estimate_tokens(bundle_text_len: int) -> int:
    """Tokens one bundle is expected to cost, input plus output.

    `EST_OUTPUT_TOKENS` is deliberately NOT changed by the same finding. The
    17.5× output under-read measured on 2026-09-12 was the **Speed brief's**,
    and that brief does not come through here — it is priced from stored
    history by `runs.expert_estimates`. This layer's own tasks return one
    findings list each, which is the shape 1,000 was chosen for. Carrying a
    measurement across from a different code path is how a thin constant
    becomes two thin constants.
    """
    return int(bundle_text_len / CHARS_PER_TOKEN) + EST_OUTPUT_TOKENS


def run_analyst_layer(
    conn: sqlite3.Connection,
    run_id: str,
    site_domain: str,
    result: AuditResult,
    crawl: CrawlResult,
    cfg: Settings,
    provider: AnalystProvider | None = None,
    enabled: bool = True,
    announce=None,
    tasks: list[str] | None = None,
) -> AnalystOutcome:
    if result.tier is Tier.T1:
        return AnalystOutcome(ran=False, reason_not_run="T1 never invokes the analyst layer")
    if not enabled:
        return AnalystOutcome(ran=False, reason_not_run="analyst layer disabled for this run")
    provider = provider or provider_from_settings(cfg)
    if provider is None:
        return AnalystOutcome(ran=False,
                              reason_not_run="no LLM provider configured — suite fully "
                                             "functional without it")

    budget_cap = cfg.llm_budget_t3 if result.tier is Tier.T3 else cfg.llm_budget_t2
    outcome = AnalystOutcome(ran=True)
    spent = 0

    # Toolkit: lets the agent fetch pages, re-run checks and query history.
    # Shared across tasks so the fetch budget is layer-global. Only passed to
    # providers whose analyse() accepts it.
    import inspect

    from .tools import AnalystToolkit
    site_row = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                            (run_id,)).fetchone()
    toolkit = AnalystToolkit(crawl, conn=conn,
                             site_id=site_row["site_id"] if site_row else None)
    provider_takes_toolkit = "toolkit" in inspect.signature(provider.analyse).parameters

    selected = [t for t in TASKS if tasks is None or t in tasks]
    bundles = {}
    for task in selected:
        bundle, security = build_bundle(task, site_domain, result, crawl)
        bundles[task] = bundle
        if not outcome.security_findings and security:
            outcome.security_findings = security  # identical across tasks; keep one set
        outcome.estimated_tokens += estimate_tokens(len(bundle.text))

    # Estimated spend is announced before any token is spent.
    if announce:
        announce(f"analyst layer: estimated spend ~{outcome.estimated_tokens} tokens "
                 f"across {len(selected)} task(s); cap {budget_cap} "
                 f"({result.tier.value}); cache consulted first")

    for task in selected:  # priority order preserved; tail cut first on budget
        bundle = bundles[task]
        spend = TaskSpend(task=task)
        outcome.spends.append(spend)

        from .base import cache_version
        # Prompt/tool changes rotate the key; entries expire after 30 days
        # because the web moves under an SEO judgement.
        cache_task_key = f"{task}#{cache_version()}"
        cached = conn.execute(
            "SELECT result, tokens_in, tokens_out FROM analyst_cache"
            " WHERE task=? AND model_id=? AND bundle_hash=?"
            " AND created_at > datetime('now', '-30 days')",
            (cache_task_key, provider.model_id, bundle.bundle_hash)).fetchone()
        if cached:
            # Cache holds post-validation drafts; replay without re-validating
            # (tool evidence from the original run is not reconstructable).
            spend.cached = True
            accepted = [AnalystFindingDraft(**d) for d in json.loads(cached["result"])]
            _log(conn, run_id, provider.name, f"{task}:cache-hit", 0)
            if announce:
                announce(f"Analyst {task}: cache hit — zero tokens")
        else:
            est = estimate_tokens(len(bundle.text))
            if spent + est > budget_cap:
                spend.skipped = (f"budget: {spent} spent + ~{est} estimated exceeds "
                                 f"cap {budget_cap}")
                _log(conn, run_id, provider.name, f"{task}:skipped-budget", 0)
                continue
            if announce:
                announce(f"Analyst {task}: analysing ({provider.model_id})")
            try:
                if provider_takes_toolkit:
                    response = provider.analyse(bundle.payload, task,
                                                max_tokens=budget_cap - spent,
                                                toolkit=toolkit)
                else:
                    response = provider.analyse(bundle.payload, task,
                                                max_tokens=budget_cap - spent)
            except Exception as exc:
                spend.skipped = f"provider error: {exc}"
                _log(conn, run_id, provider.name, f"{task}:error", 0)
                continue
            spend.tokens_in = response.tokens_in
            spend.tokens_out = response.tokens_out
            spend.tool_calls = list(response.tool_calls)
            spend.stop = response.stop
            spent += response.tokens_in + response.tokens_out
            prices = cfg.model_prices.get(provider.model_id)
            actual_cost = (round(response.tokens_in / 1e6 * prices[0]
                                 + response.tokens_out / 1e6 * prices[1], 6)
                           if prices else None)
            from clauditseo.persistence.runs import log_cost
            log_cost(conn, run_id, provider.name, f"{task}:analyse", "tokens",
                     response.tokens_in + response.tokens_out,
                     actual_cost=actual_cost)

            accepted = []
            for draft in response.findings:
                reason = validate_draft(draft, bundle,
                                        extra_ids=toolkit.issued_ids,
                                        extra_text=toolkit.evidence_text())
                if reason:
                    spend.rejected.append(reason)
                else:
                    accepted.append(draft)
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO analyst_cache"
                    " (task, model_id, bundle_hash, result, tokens_in, tokens_out,"
                    " created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                    (cache_task_key, provider.model_id, bundle.bundle_hash,
                     json.dumps([d.__dict__ for d in accepted]),
                     response.tokens_in, response.tokens_out))

        for draft in accepted:
            outcome.findings.append(
                draft_to_finding(draft, task, TASK_DIMENSION[task], provider.model_id))
            spend.accepted += 1

    # SEC findings raised by tool fetches join the bundle-scan ones.
    outcome.security_findings.extend(toolkit.security_findings)
    outcome.spent_tokens = spent
    return outcome


def _log(conn: sqlite3.Connection, run_id: str, provider: str, operation: str,
         tokens: int) -> None:
    from clauditseo.persistence.runs import log_cost
    log_cost(conn, run_id, provider, operation, "tokens", tokens)
