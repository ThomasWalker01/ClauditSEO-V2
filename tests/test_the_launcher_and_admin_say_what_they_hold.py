"""The launcher, Admin and the glossary say what they hold (screen audits
round 4: audit launch UX-01, UX-05, AC-02, IP-01; Admin UX-05; Glossary
UX-02, IP-02).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


def test_the_launcher_precheck_knows_it_is_stale_and_its_field_is_named():
    v = (SRC / "views.tsx").read_text(encoding="utf-8")
    assert "compare={precheckCompare ?? null}" in v
    assert 'aria-label="Start URL override (optional, for staging or local)"' in v


def test_the_site_size_is_said_as_the_crawls():
    s = (SRC / "scanmatrix.tsx").read_text(encoding="utf-8")
    assert "the site's size from its latest audit's" in s
    assert "<b>Scans</b>" in (SRC / "legend_strip.tsx").read_text(encoding="utf-8")


def test_a_price_that_does_not_parse_is_refused():
    a = (SRC / "admin.tsx").read_text(encoding="utf-8")
    assert "Number(inUsd) || 0" not in a
    assert "Number.isFinite(n) && n >= 0" in a


def test_the_glossary_has_an_index_and_defines_the_provenance_phrases():
    g = (SRC / "glossary.tsx").read_text(encoding="utf-8")
    assert 'aria-label="Glossary groups"' in g
    text = (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8")
    json.loads(text)
    for term in ("earlier-brief", "unseen-since", "reread", "audits-since"):
        assert f'"id": "{term}"' in text, term
