"""A cause built from a brief's check list says its stored row's sentence,
and a site-level automatic clearing overtakes an analysis row on every page.

Screen audits round 4, Local UX-01 and AC-01 (High): three "to confirm" rows
on Local read as bare check ids (`nap-inconsistent`, `nap-missing`,
`thin-location-page`) over sentences stored in the record; and the local
analysis's `localbusiness-schema-missing` stood open on six pages, its only
corroboration a site-level sweep row fixed on 25 Sept and never raised again.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

ANAT = (Path(__file__).resolve().parent.parent / "dashboard" / "src" / "anatomy.tsx").read_text(
    encoding="utf-8")


def test_a_bare_cause_takes_its_rows_sentence():
    assert 'if (!g.summary) g.summary = mine.find((st) => st.summary)?.summary ?? "";' in ANAT


def test_a_site_level_clearing_overtakes_every_page():
    src = inspect.getsource(runs.site_states)
    assert "cleared_site[r[\"check_id\"]] = max(" in src
    assert "or cleared_site.get(d[\"check_id\"])" in src
