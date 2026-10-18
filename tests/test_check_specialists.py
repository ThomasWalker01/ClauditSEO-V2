"""Running the specialist that judges one finding.

`FEATURES.md` F-02. The operator is looking at a single finding and wants the
specialist that judges *that check* to run against it. The only run verbs on
the screen targeted the whole page, and nothing mapped a `check_id` to the
tool that judges it.

**Ordinary tests, not guards**, per `FEATURES.md`: the behaviour did not exist,
so there was nothing to observe failing first. DISCIPLINE rule 1 does not apply
and is not being skipped quietly.

The half that matters most is the refusal. A control that ran the wrong tool
would return a real, fluent judgement about something other than what the
operator clicked — worse than offering nothing, because it looks like an
answer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import anatomy
from clauditseo.analysts.page_advisor import resolve_check_scope

MODULES = Path(__file__).resolve().parents[1] / "clauditseo" / "modules"


def _checks_the_modules_raise() -> set[str]:
    """Read from source, so a renamed check breaks the map rather than
    silently leaving a row with a control that resolves to nothing."""
    found: set[str] = set()
    for path in MODULES.glob("*.py"):
        found |= set(re.findall(r'check_id="([a-z0-9-]+)"',
                                path.read_text(encoding="utf-8-sig")))
    return found


# --- the map is declared, and has to stay true ------------------------------

def test_every_mapped_check_is_one_the_modules_actually_raise() -> None:
    raised = _checks_the_modules_raise()
    unknown = sorted(c for c in anatomy.CHECK_SPECIALISTS if c not in raised)
    assert not unknown, (
        "these checks have a specialist but no module raises them — a rename "
        f"left the map behind: {unknown}")


def test_every_specialist_is_a_panel_that_can_actually_be_opened() -> None:
    for check, tool in anatomy.CHECK_SPECIALISTS.items():
        assert tool in anatomy.PAGE_PANELS, \
            f"{check} names {tool}, which is not a page panel"


def test_every_specialist_covers_the_category_of_the_check_it_claims() -> None:
    """The invariant that stops the map drifting into nonsense.

    It caught one while the map was being written: `localbusiness-schema-
    missing` reads like schema work and is filed under `local`, which neither
    page panel covers. It correctly has no specialist.
    """
    for check, tool in anatomy.CHECK_SPECIALISTS.items():
        category = anatomy.CHECK_CATEGORY.get(check)
        assert category in anatomy.TOOL_CATEGORIES[tool], (
            f"{check} is filed under '{category}' but {tool} covers "
            f"{anatomy.TOOL_CATEGORIES[tool]}")


def test_a_check_with_no_specialist_answers_none_rather_than_guessing() -> None:
    """None is an answer. The caller offers no control for it."""
    assert anatomy.specialist_for("not-https") is None
    assert anatomy.specialist_for("robots-missing") is None
    assert anatomy.specialist_for("localbusiness-schema-missing") is None
    assert anatomy.specialist_for("") is None
    assert anatomy.specialist_for("invented-check") is None


# --- resolving a finding to a run -------------------------------------------

def test_a_finding_resolves_to_the_scope_of_its_own_check() -> None:
    scope, problem = resolve_check_scope("heading-skip", "page-advisor")
    assert problem is None
    assert scope == "headings", "the answer is about the heading, not the page"

    scope, problem = resolve_check_scope("meta-desc-missing", "page-advisor")
    assert problem is None and scope == "title-desc"


def test_a_check_no_specialist_judges_is_refused_with_a_reason() -> None:
    scope, problem = resolve_check_scope("not-https", "page-advisor")
    assert scope is None
    assert "no specialist judges" in problem and "not-https" in problem


def test_a_check_another_tool_owns_is_refused_rather_than_answered() -> None:
    """The acceptance signal's second half, at the resolver.

    `jsonld-invalid` has a specialist — the schema auditor. Asking the page
    advisor for it must refuse and name the right tool, not answer about the
    heading because that is what it happens to do.
    """
    scope, problem = resolve_check_scope("jsonld-invalid", "page-advisor")
    assert scope is None
    assert "schema-auditor" in problem

    scope, problem = resolve_check_scope("jsonld-invalid", "schema-auditor")
    assert problem is None, "its own specialist accepts it"


@pytest.mark.parametrize("check", sorted(anatomy.CHECK_SPECIALISTS))
def test_every_mapped_check_resolves_cleanly_for_its_own_tool(check: str) -> None:
    """No entry in the map may be unrunnable. Parametrised so a bad entry
    names itself instead of hiding in a loop."""
    tool = anatomy.CHECK_SPECIALISTS[check]
    scope, problem = resolve_check_scope(check, tool)
    if tool == "page-advisor":
        assert problem is None and scope in anatomy.ADVICE_SCOPES
    else:
        assert problem is None


# --- what a findings row is given -------------------------------------------

def test_a_stored_finding_carries_its_specialist() -> None:
    """Decided on the server, so the screen cannot invent an offer the server
    would then refuse."""
    import sqlite3

    from clauditseo.persistence.runs import _finding_dict

    def row(check_id):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT ? AS check_id, '[]' AS affected_urls, '{}' AS evidence",
            (check_id,)).fetchone()

    assert _finding_dict(row("heading-skip"))["specialist"] == "page-advisor"
    assert _finding_dict(row("jsonld-invalid"))["specialist"] == "schema-auditor"
    assert _finding_dict(row("not-https"))["specialist"] is None
