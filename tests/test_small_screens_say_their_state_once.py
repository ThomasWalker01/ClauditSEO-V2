"""Round 4 Mediums on the smaller screens (screen audits round 4):
Workbench UX-01 (a redirect replaces its history entry), Local UX-02 (each
candidate state its own word), Backlinks IP-01 and AC-03 (an Info row is a
note; "needs a key" opens Provider keys), Run views IP-02 and AC-03 (the
current audit is said as current; a regressed row says since when), Shop
IP-01 (a row read on an earlier audit is not "not read").
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
read = lambda name: (SRC / name).read_text(encoding="utf-8")


def test_a_redirect_replaces_its_entry():
    assert "goto(to, { replace: true })" in read("App.tsx")
    assert "if (replace) window.location.replace(next);" in read("nav.ts")


def test_each_candidate_state_has_its_word():
    a = read("anatomy.tsx")
    assert "to confirm or seen once {cause" not in a
    assert "{candidateWord(true)} {cause.toConfirm}" in a


def test_an_info_row_is_a_note_and_a_key_has_a_door():
    a = read("anatomy.tsx")
    assert 'cause.severity === "info" ? "note" : "finding"' in a
    assert '>Provider keys</a></>' in a


def test_the_current_audit_and_a_regressed_row_are_dated_as_they_are():
    assert "This is the current audit, {named}, as it ran" in read("views.tsx")
    assert "back since {day(f.state_at)}" in read("dossier.tsx")


def test_a_row_read_earlier_is_not_called_not_read():
    assert 'word: "read on an earlier audit"' in read("catalogue.tsx")


def test_a_corroborated_card_is_not_unseen_and_lcp_cards_reach_images():
    """Links AC-04, Speed UX-02."""
    p = read("part_page.tsx")
    assert '!fix.sources.includes("sweep") && !fix.corroboratedBy?.length && (' in p
    assert r'/^lcp-/.test(fix.checkId) && /\bimage/i.test(' in p
    assert "\x08" not in p


def test_a_blocked_audit_is_said_blocked_and_quick_asks_no_provider():
    """Home IP-03, Backlinks AC-06."""
    assert '? <span className="home-not-audited">audit blocked</span>' in read("home.tsx")
    assert "and at Quick it asks no provider either" in read("reaudit.tsx")
