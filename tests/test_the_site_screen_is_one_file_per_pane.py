"""The site screen is routing and shell in `views.tsx`, and one file per pane.

Brief step 8 (`_plans/site-screen-reorg-brief-2026-09-03.md`, CQ-02).
`views.tsx` was 2,675 lines and `SiteDetailView` ~900 of them, holding
every pane's body; the Audit, Analyses and Record panes are
`pane_audit.tsx`, `pane_analyse.tsx` and `pane_record.tsx` now, and the
screen mounts them. No behaviour changed - the rendered-output tests of
each pane are the proof of that - so this reads the source: the shell holds
no pane body, each pane file exports its one component, and the screen
mounts all three.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

PANES = {
    # Brief v4 Item 3b: the precheck pane, tile 1, in its own file.
    "pane_precheck.tsx": ("PrecheckPane", ("<PrecheckPanel",)),
    "pane_audit.tsx": ("AuditPane", ("runs-table", "<ScanMatrix", "<ScoreTrend")),
    # The catalogue is the shell's drawer since brief v4 Item 3e, outside
    # the pane's body.
    # `<LinkSuggestions` left with brief v17 step AW, which moved the
    # question onto the Links part page; the pane holds the view alone now.
    "pane_analyse.tsx": ("AnalysePane", ("<AnatomyView",)),
    "pane_record.tsx": ("RecordPane", ("state-filters", "group-row", "<MarkBar")),
}


def _component_body(source: str, name: str, whole_file: bool = False) -> str:
    """From the declaration to the first column-zero close brace - or, for a
    file that holds nothing after its component, to the last one: a moved
    comment may quote a brace at column zero."""
    opener = f"export function {name}("
    assert opener in source, f"{name} is not defined where this reads it"
    rest = source.split(opener, 1)[1]
    # A brace closing the declaration's own props list (`}) {`) is not the
    # component's end; the end is a brace alone on its line.
    return rest.rsplit("\n}\n", 1)[0] if whole_file else rest.split("\n}\n", 1)[0]


def test_each_pane_file_exports_its_one_component_and_holds_its_body():
    for file, (name, marks) in PANES.items():
        src = (SRC / file).read_text(encoding="utf-8")
        exported = re.findall(r"^export function (\w+)\(", src, re.M)
        assert exported == [name], (file, exported)
        # Every pane file holds its component and nothing after it since
        # brief v17 step AW took `LinkSuggestions` out of the Analyses one.
        body = _component_body(src, name, whole_file=True)
        missing = [m for m in marks if m not in body]
        assert not missing, f"{file}: {name} does not hold {missing}"


def test_the_shell_mounts_the_panes_and_holds_no_pane_body():
    views = (SRC / "views.tsx").read_text(encoding="utf-8")
    shell = _component_body(views, "SiteDetailView")
    for name in ("AuditPane", "AnalysePane", "RecordPane"):
        assert f"<{name} " in shell, f"the screen does not mount {name}"
    for _, marks in PANES.values():
        for m in marks:
            assert m not in shell, f"the shell still holds {m!r}"
    # The screen keeps what the address decides: the pane, the filter, the
    # grouping - and hands the rest down.
    for kept in ("TAB_ALIAS[raw]", "rememberState(", "rememberGroup(", "setShown(PAGE)"):
        assert kept in shell, f"the shell lost {kept!r}"
    lines = shell.count("\n")
    assert lines < 400, f"SiteDetailView is {lines} lines; the panes did not leave it"
