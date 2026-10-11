"""Redirect shapes are counted where the crawl stored them (item 277, row 8).

The Indexability "now" said `temporary` and `to_404` were not decidable from
a stored crawl, while the crawl had stored every hop's status since the fetch
recorded `redirect_statuses`. They are counted where every redirected page
carries it, and the caveat names the gap only where it applies.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_counted_where_stored():
    src = (ROOT / "clauditseo" / "persistence" / "runs.py").read_text(encoding="utf-8")
    body = src.split("def indexability_now_payload", 1)[1].split("\ndef ", 1)[0]
    assert '"temporary": temporary,' in body and '"per_hop": per_hop,' in body
    assert "{302, 303, 307}" in body
    tsx = (ROOT / "dashboard" / "src" / "indexability_now.tsx").read_text(encoding="utf-8")
    assert "!now.redirects.per_hop" in tsx
