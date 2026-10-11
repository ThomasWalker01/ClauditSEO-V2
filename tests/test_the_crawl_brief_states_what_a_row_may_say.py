"""The Crawl brief states what a row may say (item 275, row 4).

Of 24 rows the round-2 run returned, 17 were dropped, all for reasons the
brief and the contract caused: six PASS rows and three NOT_ASSESSABLE rows
refused as "not one of FAIL/WARN/PASS-OVERRIDE", a statement the brief never
made. It also told the model to hold an AI agent's 403 as `ua-server-refusal`
(the engine files it as `AIS/edge-blocks-ai-ua`), and listed `depth-deep`
among its per-page rows on a check it says it does not own; the run wrote 17
depth-deep cards in prose.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.analysts import contract

CRAWL = Path(__file__).resolve().parents[1] / "clauditseo" / "prompts" / "crawl.md"


def test_the_brief_names_the_statuses_the_contract_reads():
    text = CRAWL.read_text(encoding="utf-8")
    *head, last = contract.STATUSES
    said = ", ".join(f"`{s}`" for s in head) + f" or `{last}`"
    assert f"`status` is {said} and nothing else" in text, said
    assert "there is no PASS row" in text and "there is no NOT_ASSESSABLE or HELD row" in text


def test_an_ai_agents_refusal_is_not_this_briefs_hold():
    text = CRAWL.read_text(encoding="utf-8")
    assert "`AIS/edge-blocks-ai-ua`, filed by the AI surface part" in text
    assert "403 to a known crawler" not in text


def test_depth_deep_is_read_not_written_and_a_fix_is_an_artefact():
    text = CRAWL.read_text(encoding="utf-8")
    assert "`LNK/depth-deep` is read here, not written" in text
    assert "per-page rows (`render-only`,\n  `unreachable`)" in text
    assert "Never advice" in text and "never an item or step\n  number" in text
