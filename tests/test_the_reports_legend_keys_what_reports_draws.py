"""The Reports legend keys what the screen draws (screen audits round 4,
Reports IP-02): it listed "next step", which no control carries, and its
"regressed" definition pointed at the red-outlined "N audits since" pill.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_audits_since_has_its_own_term_and_tone():
    r = (ROOT / "dashboard" / "src" / "reports.tsx").read_text(encoding="utf-8")
    assert '"audits-since", "report-held"]' in r
    assert '"action-primary", "sev-critical"' not in r
    assert '<Pill tone="state-regressed">\n                    {r.audits_since}' not in r
    g = json.loads((ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))
    assert "audits-since" in json.dumps(g)


def test_the_deliverables_say_empty_and_failed_and_the_success_line_names_them():
    """Reports UX-01, UX-03."""
    r = (ROOT / "dashboard" / "src" / "reports.tsx").read_text(encoding="utf-8")
    assert "Nothing has been delivered for this site yet." in r
    assert "The deliverables did not load: ${loadError}" in r
    assert '}}>Client deliverables</a> below.</>' in r


def test_the_plan_spend_is_priced_and_open_is_defined_as_the_record_holds_it():
    """Reports UX-04, Record IP-06."""
    r = (ROOT / "dashboard" / "src" / "reports.tsx").read_text(encoding="utf-8")
    assert 'r.tool === "plan" && r.cost != null' in r
    g = (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8")
    assert "A page the latest crawl did not read keeps its open faults" in g


def test_a_score_basis_is_dated_and_admin_ceilings_say_their_scope():
    """Record IP-08, Admin AC-02."""
    v = (ROOT / "dashboard" / "src" / "views.tsx").read_text(encoding="utf-8")
    assert "pages the site declared when this audit ran" in v
    a = (ROOT / "dashboard" / "src" / "admin.tsx").read_text(encoding="utf-8")
    assert "a Site-scope audit (T2):" in a
