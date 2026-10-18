"""A gated part says its checks cannot have findings (item 274, row 13).

International on a one-locale site listed eleven bare check ids under
"Analysis · 0 ... not applicable". It now says "11 checks cannot have
findings on this site" with the reason, and keeps the ids in a closed
disclosure.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_said_once_with_the_ids_behind_a_disclosure():
    src = SRC.read_text(encoding="utf-8")
    assert "{MEASURE_WORD.cannot} on" in src
    assert '<details className="cause-dark-line" key={reason}>' in src
