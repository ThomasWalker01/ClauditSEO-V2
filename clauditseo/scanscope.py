"""How much of a site a scan visits — the axis that was tangled with depth.

A scan is two decisions: **how much of the site** to visit, and **how hard to
look** at each page. The product had one control for both. `tier` is a page
budget — `T1` is three pages, which `adaptive.py` uses as a pulse — so asking
for "a shallow site scan" asked for three pages and called the result a site.
Every honest combination of the two axes was unavailable, and several
dishonest ones were offered.

This module owns the first axis only. The second is expressed with parameters
that already exist: whether the analyst layer runs, and on which model.

**Scope does not replace tier.** `tier` still decides how much of a sitemap is
read and how long a fetch may take, and an audit that names no scope behaves
exactly as it did before. Scope overrides the *page budget* and the frontier,
which is the part that was doing two jobs.
"""

from __future__ import annotations

from dataclasses import dataclass

from clauditseo.crawler.types import TIER_BUDGETS, Tier, TierBudget

#: What "everything" means in practice. A cap is still needed — a crawler with
#: no ceiling is a way to spend an afternoon on a site that generates URLs —
#: but it is set far above the largest site this product has measured rather
#: than at a tier's sample size. `truncated_by` reports it if it is ever hit,
#: so a full scan that was not full says so.
FULL_MAX_PAGES = 5000


@dataclass(frozen=True)
class Scope:
    key: str
    label: str
    #: What the operator is choosing, in their words.
    what: str
    #: None means "the tier's own budget", which is what an audit that names
    #: no scope has always used.
    max_pages: int | None
    nav_only: bool = False
    #: Page scope fetches exactly the URL it is given and follows nothing.
    single_url: bool = False


SCOPES: dict[str, Scope] = {
    "page": Scope("page", "Page", "One URL you name.", max_pages=1,
                  single_url=True),
    "nav": Scope("nav", "Nav",
                 "The pages the site puts in its header and footer — its own "
                 "claim about what matters.",
                 max_pages=None, nav_only=True),
    "site": Scope("site", "Site", "A representative sample, capped.",
                  max_pages=TIER_BUDGETS[Tier.T2].max_pages),
    "full": Scope("full", "Full", "Every reachable page, nothing sampled out.",
                  max_pages=FULL_MAX_PAGES),
}


#: Which tier's *timeouts* a scope needs. Not a page budget — the scope owns
#: that — but a wall clock and a per-request timeout proportionate to the work.
#:
#: This exists because leaving it to the caller reintroduces the problem the
#: scope was added to solve: a Full scan carrying T2's fifteen-minute wall
#: clock stops on time rather than on pages, reports `truncated_by=wall_clock`,
#: and is a Full scan in name only. The operator should not have to know that.
_TIER_FOR_SCOPE = {
    "page": Tier.T1,   # one fetch; the sitemap head limit is irrelevant here
    "nav":  Tier.T2,
    "site": Tier.T2,
    "full": Tier.T3,   # the only tier whose hour is long enough to finish
}


def tier_for_scope(scope_key: str) -> Tier:
    """The tier whose timeouts suit this scope."""
    return _TIER_FOR_SCOPE[scope_key]


def crawl_kwargs(scope_key: str | None, tier: Tier,
                 start_url: str) -> dict:
    """The crawl arguments a scope implies, on top of the tier's own.

    Returns `{}` for an unnamed scope so the existing call is untouched: an
    audit that never mentions scope must keep behaving exactly as it did, or
    every stored run's comparability changes under the operator.
    """
    if not scope_key:
        return {}
    scope = SCOPES[scope_key]
    out: dict = {}
    if scope.nav_only:
        out["nav_only"] = True
    if scope.single_url:
        # `only_urls` restricts the frontier rather than the budget: the
        # crawler fetches these and follows nothing, which is what "this page"
        # means. A max_pages of 1 alone would fetch one page of a crawl that
        # was still trying to be a crawl.
        out["only_urls"] = [start_url]
    if scope.max_pages is not None:
        base = TIER_BUDGETS[tier]
        out["budget"] = TierBudget(
            max_pages=scope.max_pages,
            request_timeout_s=base.request_timeout_s,
            wall_clock_s=base.wall_clock_s,
            delay_s=base.delay_s)
    return out


#: The second axis, kept here beside the first so the pair is readable in one
#: place — but note these are not new parameters. `analyst` and `model` are
#: what the audit already took; a depth is a name for a combination of them.
#:
#: `quick` runs no model at all, which is why it is free and why it is the
#: honest first pass on a large site: a checklist over every page beats
#: judgement over a sample when the fault is template-level.
DEPTHS: dict[str, dict] = {
    "quick":    {"label": "Quick",    "analyst": False, "tier": None,
                 "what": "Applies a fixed checklist. No model judgement."},
    "standard": {"label": "Standard", "analyst": True,  "tier": "standard",
                 "what": "Analysis with judgement at the edges."},
    "deep":     {"label": "Deep",     "analyst": True,  "tier": "deep",
                 "what": "Where the judgement is the product."},
}


def depth_settings(depth_key: str | None) -> dict:
    """`{analyst, model_tier}` for a depth, or `{}` for an unnamed one."""
    if not depth_key:
        return {}
    d = DEPTHS[depth_key]
    return {"analyst": d["analyst"], "model_tier": d["tier"]}
