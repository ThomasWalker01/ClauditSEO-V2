"""Which model each brief tier runs on.

A tool declares the tier it needs — `fast` for applying a fixed checklist,
`standard` for analysis with judgement at the edges, `deep` where the
judgement is the product — and the tier resolves to a model. That mapping was
three environment variables, which put the most consequential decision in the
product behind a deployment step: the difference between the cheapest and the
most capable model here is five times the price and, on a judgement-heavy
brief, the difference between a list of observations and a platitude.

A stored choice overrides the environment for that tier. Absence means the
environment still decides, so an install that never opens the screen behaves
exactly as it did before.
"""

from __future__ import annotations

import dataclasses
import sqlite3

from clauditseo.config import Settings, settings

TIERS = ("fast", "standard", "deep")

#: What the tiers are for, in the operator's words rather than the config's.
TIER_PURPOSE: dict[str, str] = {
    "fast": "applying a fixed checklist",
    "standard": "analysis with judgement at the edges",
    "deep": "where the judgement is the product",
}

#: The recommendation, and the reason for it. Offered as a button rather than
#: enforced: an operator running a cost-sensitive month may legitimately want
#: everything a tier cheaper, and an operator preparing a pitch may want the
#: opposite. What they should not have to do is remember the model IDs.
RECOMMENDED: dict[str, str] = {
    "fast": "claude-haiku-4-5-20251001",
    "standard": "claude-sonnet-5",
    "deep": "claude-opus-5",
}

_COLUMN = {"fast": "llm_model_fast", "standard": "llm_model",
           "deep": "llm_model_deep"}


def chosen(conn: sqlite3.Connection) -> dict[str, str]:
    """Stored choices only — a tier with no row is absent, not defaulted."""
    return {r["tier"]: r["model"] for r in
            conn.execute("SELECT tier, model FROM tier_models")}


def settings_for(conn: sqlite3.Connection, cfg: Settings | None = None) -> Settings:
    """Configuration with the operator's tier choices applied.

    Returns a copy rather than mutating: the process-wide Settings is shared,
    and a request that quietly rewrote it would change which model every other
    request in flight was using.
    """
    base = cfg or settings()
    picks = chosen(conn)
    if not picks:
        return base
    return dataclasses.replace(base, **{
        _COLUMN[t]: m for t, m in picks.items() if t in _COLUMN})


def known_models(conn: sqlite3.Connection, cfg: Settings | None = None) -> list[str]:
    """What an operator may choose between.

    The priced models, plus whatever the configuration and the current choices
    already name. Restricted rather than free text because a mistyped model ID
    fails at call time with a provider error that says nothing about the
    typo — and it fails after the operator has committed to a run.
    """
    base = cfg or settings()
    out = {r["model"] for r in conn.execute("SELECT model FROM model_prices")}
    out.update(chosen(conn).values())
    out.update(base.model_for_tier(t) for t in TIERS)
    return sorted(x for x in out if x)


def set_tier(conn: sqlite3.Connection, tier: str, model: str,
             operator_id: str | None = None) -> None:
    from clauditseo.persistence.repo import now_iso

    if tier not in TIERS:
        raise ValueError(f"tier must be one of {', '.join(TIERS)}")
    if not model or not model.strip():
        raise ValueError("model is required")
    if model not in known_models(conn):
        raise ValueError(
            f"{model} is not a model this install knows about — read the "
            "published prices first, or check the id")
    with conn:
        conn.execute(
            "INSERT INTO tier_models (tier, model, chosen_at, chosen_by)"
            " VALUES (?, ?, ?, ?) ON CONFLICT(tier) DO UPDATE SET"
            " model=excluded.model, chosen_at=excluded.chosen_at,"
            " chosen_by=excluded.chosen_by",
            (tier, model.strip(), now_iso(), operator_id))


def use_recommended(conn: sqlite3.Connection, operator_id: str | None = None) -> dict:
    """Set every tier to the recommendation, skipping any this install cannot
    run — a recommendation that names a model the operator has no price or
    access for is worse than leaving the tier alone."""
    available = set(known_models(conn))
    applied, skipped = {}, {}
    for tier, model in RECOMMENDED.items():
        if model in available:
            set_tier(conn, tier, model, operator_id)
            applied[tier] = model
        else:
            skipped[tier] = model
    return {"applied": applied, "skipped": skipped}


# ---- per-brief defaults (brief v4 Item 3g) ----------------------------------

def brief_choices(conn: sqlite3.Connection) -> dict[str, str]:
    """Stored per-brief defaults only - a brief with no row is absent, and
    its tier decides."""
    return {r["tool"]: r["model"] for r in
            conn.execute("SELECT tool, model FROM brief_models")}


def priced_models(conn: sqlite3.Connection) -> list[str]:
    """What a brief default may be chosen from: models with a price on file.
    Narrower than `known_models` on purpose - a default is what run-all
    totals against, and a model with no price makes the total a guess."""
    return sorted(r["model"] for r in conn.execute("SELECT model FROM model_prices"))


def set_brief(conn: sqlite3.Connection, tool: str, model: str,
              operator_id: str | None = None) -> None:
    from clauditseo.analysts.expert import EXPERT_TOOLS
    from clauditseo.persistence.repo import now_iso

    if tool not in EXPERT_TOOLS:
        raise ValueError(f"{tool} is not an analysis")
    if not model or not model.strip():
        raise ValueError("model is required")
    if model not in priced_models(conn):
        raise ValueError(
            f"{model} has no price on file - an analysis default is what a batch "
            "is totalled against, so it must be a priced model")
    with conn:
        conn.execute(
            "INSERT INTO brief_models (tool, model, chosen_at, chosen_by)"
            " VALUES (?, ?, ?, ?) ON CONFLICT(tool) DO UPDATE SET"
            " model=excluded.model, chosen_at=excluded.chosen_at,"
            " chosen_by=excluded.chosen_by",
            (tool, model.strip(), now_iso(), operator_id))


def clear_brief(conn: sqlite3.Connection, tool: str) -> None:
    """Hand the brief back to its tier."""
    with conn:
        conn.execute("DELETE FROM brief_models WHERE tool=?", (tool,))


def clear(conn: sqlite3.Connection) -> None:
    """Hand the decision back to the environment."""
    with conn:
        conn.execute("DELETE FROM tier_models")
