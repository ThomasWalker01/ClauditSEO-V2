"""A policy row is the site's (item 277, row 10).

The parameter-policy row ("canonicalise tracking parameters") was filed on
the page the model wrote beside it, so PAGES counted that page and the card
named it. A `kind: policy` row is stored site-level with the page in its
evidence; its card says site-wide and PAGES reads a dash.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_site_level():
    src = (ROOT / "clauditseo" / "analysts" / "contract.py").read_text(encoding="utf-8")
    assert 'if str(raw.get("kind") or "").strip().lower() == "policy" and page_raw:' in src
    page = (ROOT / "dashboard" / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert 'mineCards.every((f) => f.kind === "policy")' in page
    assert '<span className="muted fix-page">site-wide</span>' in page
