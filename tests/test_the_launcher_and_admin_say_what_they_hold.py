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
    assert '"Start URL override (optional, for staging or local)"' in v
    # The Page scope names its page there (audit launch UX-04).
    assert '"Which page to audit (the home page where empty)"' in v
    # The adaptive bands in the radios' own scope words (AC-03).
    assert "80–94 get a Site-scope crawl" in v


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


def test_the_landing_says_why_its_to_confirm_counts_differ():
    """Landing IP-01: 75 on the parts band beside "To confirm 79"."""
    c = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "of them on the parts; " in c and "the other is a verdict" in c
    g = (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8")
    assert '{"id": "to-confirm", "kind": "term", "vocabulary": "finding states",' in g


def test_coverage_notes_and_the_content_band_are_said_as_what_they_are():
    """Record IP-03 (one audit's history listed coverage notes as issues),
    Images UX-03 (the content band had no head)."""
    c = (SRC / "components.tsx").read_text(encoding="utf-8")
    assert "groupFindings(findings.filter((f) => !isCoverageNote(f)))" in c
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert '<h5 className="img-band-head">' in p


def test_page_mode_drops_say_they_are_the_sites():
    """Title & description IP-03."""
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "from the analysis of the whole site, ${here} of them on this page" in p


def test_copy_anchor_is_offered_only_for_an_anchor():
    """Links UX-01: it copied instruction sentences as anchors."""
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert '&& !/\//.test(fix.replacement ?? ""))),' in p
