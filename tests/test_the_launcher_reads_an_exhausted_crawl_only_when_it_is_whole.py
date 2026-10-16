"""The launcher states the last crawl's page count as the site's only when
that crawl ran out of links, was not cut short, and fetched every page.

Screen audits round 4, audit launch AC-01 (High): "Full · 74 pages · nothing
sampled out" counted 16 numbered duplicate forms and a CDN path among the 74,
on a site whose Full scan read 45. And a crawl with 22 fetch errors also "ran
out of links", at 31 pages.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_exhaustive_needs_an_empty_queue_no_truncation_and_no_errors():
    app = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'stats.get("queue_remaining") == 0 and not stats.get("errors")' in app
    assert 'not stats.get("truncated_by")' in app


def test_the_grid_and_the_tile_read_it():
    scan = (ROOT / "dashboard" / "src" / "scanmatrix.tsx").read_text(encoding="utf-8")
    assert ": pre.exhaustive && pre.audited\n          ? pre.audited" in scan
    pre = (ROOT / "dashboard" / "src" / "precheck.tsx").read_text(encoding="utf-8")
    assert "read by the last crawl, which ran out of links" in pre
