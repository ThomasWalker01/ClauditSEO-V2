"""The page verdict says the site's too, and names the check that disagrees
(item 270, row 12).

Page mode printed "Entity: CONSOLIDATED (this page's markup)" on a site the
analysis called FRAGMENTED, and "automatic checks disagree" named no check.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "schema_graph.tsx"


def test_both_verdicts_and_the_check():
    src = SRC.read_text(encoding="utf-8")
    assert "· site: <b>{part.brief_entity.verdict}</b>" in src
    assert "{dispute.checks[0].split(\"/\").pop()} (#{dispute.n})" in src
