"""Accessibility's checks that filed nothing are said clean (item 279, row 7).

The table knew a check only if a row named it, so nine of Accessibility's
registered checks - ran, filed nothing - were said nowhere, and the "N checks
clean" line never fired for them. The payload now carries every registered
check that measures something; Accessibility lists them.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo import anatomy as an
from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_registered_checks_leave_the_notes_out():
    got = sorted(k for k, v in an.CHECK_CATEGORY.items()
                 if v == "a11y" and not runs.is_note_name(k))
    assert "axe-sampled" not in got and "axe-coverage" not in got
    assert "contrast-not-assessed" not in got
    # The nine silent on twenty22, with the two that filed rows there and the
    # run-failure note the screen leaves out.
    assert set(got) - {"link-name-missing", "link-text-generic", "axe-render-failed"} == {
        "aria-reference-broken", "button-name-missing", "duplicate-id",
        "form-control-unlabelled", "html-lang-missing", "iframe-title-missing",
        "landmark-main-missing", "tabindex-positive", "table-headers-missing"}


def test_the_payload_and_the_table_carry_them():
    import inspect
    assert '"registered_checks": sorted(' in inspect.getsource(runs.anatomy_view)
    page = SRC.read_text(encoding="utf-8")
    assert 'if (part.key === "a11y") {' in page
    assert "for (const id of part.registered_checks ?? []) {" in page
