"""TEC joins the check registry (brief v18 step AZ, foundational).

TEC set its severities inline and kept no registry table, so `_registries()`
knew ONP, LNK and CNT only and the crawl brief could not be costed or
severity-checked against the registry the other briefs answer to. Adding a
`DEFAULT_SEVERITY` table changes no firing — the values are exactly what the
sweep already emits — and the operator's own caution is the load-bearing test
here: **a check that was free must stay free.** `check_costs()` derives cost
from `default_severities()` plus a fallback, and moving TEC onto the registry
path must not tip a sweep check into `model`.
"""

from __future__ import annotations

import re
from pathlib import Path

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.checks import check_cost, default_severities
from clauditseo.modules import tec


def test_every_tec_check_stays_free():
    """The operator's cost-invariance check. TEC raises every one of these
    through its own sweep, so none costs a model call; the table must not
    change that for a single one, by full id or bare."""
    for check in tec.DEFAULT_SEVERITY:
        assert check_cost(f"TEC/{check}") == "free", check
        assert check_cost(check) == "free", check


def test_the_table_is_exactly_what_the_sweep_emits():
    """Drift guard, both directions. A check id the sweep emits with no table
    entry would carry no registered default; a table entry the sweep never
    emits is a severity for a check that does not exist. The set on each side
    must be the same."""
    src = Path(tec.__file__).read_text(encoding="utf-8")
    emitted = set(re.findall(r'check_id="([a-z0-9-]+)"', src))
    assert set(tec.DEFAULT_SEVERITY) == emitted, (
        f"table-only: {sorted(set(tec.DEFAULT_SEVERITY) - emitted)}; "
        f"sweep-only: {sorted(emitted - set(tec.DEFAULT_SEVERITY))}")


def test_the_registered_defaults_are_the_current_severities():
    """The severities are named, not changed. Pinned so a later commit that
    wires the emitters to read the table cannot quietly move one."""
    ds = default_severities()
    expected = {
        "links-behind-js": "medium", "robots-missing": "high",
        "sitemap-missing": "medium",
        "sitemap-coverage": "medium", "unreachable": "medium",
        "unreachable-not-assessed": "info",
        # `not-https` and `security-headers` left for SEC at item 143 step BD.
        "internal-link-tracking-params": "medium",
        "http-status-error": "high", "redirect-chain": "medium",
        # Item 147, brief v20: `mobile-viewport` became `viewport-missing` and
        # rose to HIGH — a page with no viewport tag does not render
        # responsively at all. Five parse-only siblings joined it; the other
        # nine of the brief's fifteen need a capture that does not exist and
        # are in BRIEF_ONLY_CHECKS, so they are deliberately NOT here.
        "viewport-missing": "high",
        "zoom-suppressed": "high",
        "viewport-width": "medium",
        "viewport-scale": "medium",
        "viewport-duplicate": "medium",
        "viewport-legacy": "medium",
        # noindex-page split at item 137 (brief v18 step BA).
        "noindex-linked": "high", "noindex-in-sitemap": "low",
        "redirect-to-404": "high", "meta-robots-conflict": "medium",
        "redirect-temporary": "low",
        "canonical-to-404": "high", "canonical-loop": "high",
        "canonical-sitemap-conflict": "medium",
        # Crawl & sitemaps (brief v18 step AZ).
        "sitemap-invalid": "high", "sitemap-lastmod-stale": "low",
        "sitemap-404s": "medium", "sitemap-noindex": "medium",
        "sitemap-regression": "high", "render-only": "medium",
    }
    for check, sev in expected.items():
        assert ds[f"TEC/{check}"] == sev, (check, ds.get(f"TEC/{check}"))


def test_tec_now_answers_the_registry():
    """The whole point: TEC is one of the modules `_registries()` reads, so
    the registry can speak for its checks like it does for ONP's."""
    from clauditseo.checks import _registries

    codes = {code for code, _t, _o in _registries()}
    assert "TEC" in codes
