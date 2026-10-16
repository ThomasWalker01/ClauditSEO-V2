"""The dossier counts and dates as the record does (screen audits round 4,
Pages IP-01 to IP-04, IP-06, AC-03 to AC-05, UX-01, UX-04, UX-05, UX-07 to
UX-09, UI-01, UI-04, US-03).

On twenty22's home page a fixed row read "fixed · measured 11 Oct" beside its
old failing figure; two Links-only re-checks read "T2 · site"; a coverage
note was an open finding; an analysis PASS was offered to Confirm; there was
no Source column, no legend, and no count to check the Pages table's "58"
against. The table and the dossier now count one per check, and the dossier
states the table's number.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_payload_carries_what_the_rows_are():
    src = inspect.getsource(runs.page_dossier)
    for key in ('"source_word"', '"coverage_note"', '"brief_status"', '"state_at"',
                '"part_only"', '"open_checks"'):
        assert key in src, key
    assert "part_only_runs(conn, site_id)" in src
    assert "open_by_page(conn, site_id)" in src


def test_the_dossier_draws_them():
    d = (SRC / "dossier.tsx").read_text(encoding="utf-8")
    # A re-check of some parts is named as one.
    assert "re-check · ${h.part_only}" in d
    # A PASS is not offered for confirmation.
    assert '/^PASS/i.test(f.brief_status' in d and "passed by the analysis" in d
    assert "!passed(f)" in d
    # Coverage notes under the table, not in it.
    assert "f.coverage_note" in d and "Not findings, so not counted" in d
    # A fixed row is dated by when it was cleared.
    assert "cleared {day(f.state_at)}" in d
    # One legend, the answers explained there and not under every row.
    assert "<Legend" in d and "TO_CONFIRM_LEGEND" in d and "explain={false}" in d
    # The record's words and tones; "Memory" and the retired classes are gone.
    assert "<th>State</th>" in d and "<th>Memory</th>" not in d
    assert "<SeverityTag" in d and "sev sev-" not in d
    assert "<th>Source</th>" in d
    # The analyses above the findings heading, so it heads the table.
    assert d.index("<ExpertPanel") < d.index("<h3>Findings naming this page</h3>")
    # The table's number, and the way back to it.
    assert "data.open_checks" in d and "?tab=pages" in d
    # The crawl history's title, with a change mark, at minute precision.
    assert "title changed" in d and "{stamp(h.at)}" in d


def test_the_pages_pane_lost_its_navigating_select():
    v = (SRC / "views.tsx").read_text(encoding="utf-8")
    assert "Open the dossier for a page" not in v
    assert "The page list did not load" in v and "try again" in v
    assert "maxLength={NOTE_MAX}" in v and "The note was not saved" in v
    assert "No notes on this site yet." in v
