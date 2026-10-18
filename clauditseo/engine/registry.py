"""Dimension-module registry.

Adding a new audit dimension means writing one module file that calls
``register()`` at import time — zero changes here or in the engine core.
Gate G3 proves that with a toy EXT module in the test suite.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import Finding, Site, SubScore, Tier


@runtime_checkable
class AuditModule(Protocol):
    """Common interface every dimension implements."""

    code: str          # e.g. "TEC"
    name: str          # e.g. "Technical"
    default_weight: float

    # Two optional declarations, read by `crawl_blind_dims` and
    # `page_blind_dims` above. Deliberately not required members here: this
    # Protocol is `runtime_checkable` and `tests/test_engine_registry.py`
    # isinstance-checks a toy module against it, so a required data member
    # would make gate G3's "one module file, zero changes here" claim false.
    # The built-ins are held to `measured_per_page` by a test, not by typing.

    def applicable(self, site: Site) -> bool: ...
    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]: ...
    def score(self, findings: list[Finding], context: dict) -> SubScore: ...


_MODULES: dict[str, AuditModule] = {}


def register(module: AuditModule) -> AuditModule:
    if module.code in _MODULES:
        raise ValueError(f"dimension {module.code} already registered")
    _MODULES[module.code] = module
    return module


def get(code: str) -> AuditModule:
    return _MODULES[code]


def all_modules() -> dict[str, AuditModule]:
    return dict(_MODULES)


def crawl_blind_dims(codes: list[str] | None = None) -> set[str]:
    """Codes whose coverage no crawl can obtain, however deep it goes.

    Every dimension but one derives its coverage from
    `scoring.page_coverage(context)`, so fetching more pages raises it. OFP
    does not: its coverage is `1.0 - len(dark)/len(SIGNALS)` over backlink
    provider signals, and `run_adaptive` clears the backlink providers at any
    band below CRITICAL. A crawl bought on OFP's absence therefore cannot
    change the input that triggered it.

    Declared per module as `coverage_from_crawl`, defaulting to True, and
    read here rather than listed in the planner — a hard-coded list of one is
    how the next dimension with a provider-derived coverage inherits the
    defect silently. `tests/test_staging_depth.py` enumerates the registry
    and checks each declaration against whether the module's own source
    calls `page_coverage`.
    """
    wanted = _MODULES if codes is None else {c: _MODULES[c] for c in codes
                                             if c in _MODULES}
    return {code for code, m in wanted.items()
            if not getattr(m, "coverage_from_crawl", True)}


def page_blind_dims(codes: list[str] | None = None) -> set[str]:
    """Codes whose findings no single-page re-read can move.

    A page refresh re-reads one URL and re-measures one dimension against it.
    A dimension none of whose checks can be measured against a single page
    cannot be cleared that way, however many times the control is pressed —
    so the offer must be withheld and the route must refuse it.

    Declared per module as `measured_per_page`, and unlike
    `coverage_from_crawl` it is **not defaulted**: every built-in dimension
    states it outright and `tests/test_page_scope_is_declared.py` fails a
    module that does not. A default is how the next dimension inherits an
    answer nobody wrote, and this fact has no safe default — guessing True
    bills for a crawl that cannot change anything, guessing False withdraws a
    control that works.

    **Not the same fact as `coverage_from_crawl`, which is what this used to
    read.** That one answers "can fetching more pages raise this dimension's
    coverage"; this one answers "can re-reading one page move one of its
    findings". They agree on every dimension at HEAD because OFP happens to
    be the only member of either set, and that coincidence is exactly why the
    proxy survived: a future dimension that is crawl-blind but page-capable
    (or the reverse) would have inherited the wrong answer silently. Split
    per `QUESTIONS.md` Q-17.
    """
    wanted = _MODULES if codes is None else {c: _MODULES[c] for c in codes
                                             if c in _MODULES}
    return {code for code, m in wanted.items()
            if not getattr(m, "measured_per_page", True)}


def unregister(code: str) -> None:
    """Test helper so toy modules don't leak between tests."""
    _MODULES.pop(code, None)
