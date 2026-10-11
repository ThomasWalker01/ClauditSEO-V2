"""A hold beside a pass for the same check is dropped unless it names an
input (item 277, row 7).

The Indexability analysis returned PASS rows and holds for the same check and
page: assessed and not assessable at once. The prompt states the status
vocabulary; the contract keeps the pass's answer (a pass is silence) and
drops the hold, unless the hold names something the operator can supply.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.analysts import contract
from clauditseo.analysts.contract import Parsed, Rules, enforce

ROOT = Path(__file__).resolve().parents[1]


def _parsed(needs: str) -> Parsed:
    p = Parsed(status="read", rows=[],
               not_assessable=[{"check": "TEC/redirect-chain", "page": "/a/", "needs": needs}])
    p.dropped.append({"row": {"check": "TEC/redirect-chain", "page": "/a/", "status": "PASS"},
                      "reason": "status 'PASS' is not one of FAIL/WARN/PASS-OVERRIDE"})
    return p


def test_dropped_without_an_input():
    got = enforce(_parsed("the hop statuses"), Rules())
    assert got.not_assessable == []
    assert any("beside a pass" in d["reason"] for d in got.dropped)


def test_kept_with_an_input():
    got = enforce(_parsed("the migration map on the site record"), Rules())
    assert len(got.not_assessable) == 1


def test_the_prompt_says_the_vocabulary():
    text = (ROOT / "clauditseo" / "prompts" / "indexability.md").read_text(encoding="utf-8")
    assert "Never return a PASS row or a\n  HELD row" in text
    assert contract.STATUSES == ("FAIL", "WARN", "PASS-OVERRIDE")
