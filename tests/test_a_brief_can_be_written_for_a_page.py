"""`Write a brief for this page` — the generator's two doors (brief v17
step AX).

The engine has been able to write one since the generator kind landed;
what was missing was anywhere to press. The brief names two places, and
they are the two ways an operator arrives at "this page needs writing":
reading the part, and reading the record.

It is a **generator**, so the clauses below hold two things a findings
brief would not need — that pressing it adds no Record rows, and that the
control says what it produces rather than what it checks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_control_is_offered_on_both_doors_the_brief_names():
    part = (UI / "part_page.tsx").read_text(encoding="utf-8")
    record = (UI / "pane_record.tsx").read_text(encoding="utf-8")
    assert "export function WriteBrief" in part, (
        "the generator has no control at all")
    assert "<WriteBrief" in part, "the part page does not offer it"
    assert "<WriteBrief" in record, (
        "a Record row does not offer it, so an operator reading the record "
        "has to go and find the part page to write a brief for the page "
        "they are looking at")


def test_it_is_offered_only_where_there_is_a_page_to_write_about():
    """"Write a brief" with no page is a question about which page, and a
    control that has to ask is a control that should not be offered."""
    part = (UI / "part_page.tsx").read_text(encoding="utf-8")
    body = part[part.index("export function WriteBrief"):]
    body = body[:body.index("\n}")]
    assert "if (!page || !runId) return null;" in body, body[:400]


def test_the_record_offers_it_only_on_a_content_row_that_names_a_page():
    record = (UI / "pane_record.tsx").read_text(encoding="utf-8")
    call = record[record.index("{runId && s.dimension ===") :]
    call = call[:call.index(")}") + 2]
    assert 's.dimension === "CNT"' in call, call
    assert "affected_urls[0]" in call, call


def test_the_control_names_what_it_makes_and_not_what_it_checks():
    """A generator emits no findings. A button reading "run" beside the
    two that re-check the page would put a third check on the row."""
    part = (UI / "part_page.tsx").read_text(encoding="utf-8")
    body = part[part.index("export function WriteBrief"):]
    body = body[:body.index("\n}")]
    assert "Write a brief for this page" in body, body[:400]
    # Item 178: SpendButton draws the mark.
    assert "<SpendButton" in body, "it spends, and the mark is how that is said"
    # UX-66: the caption is the accessible name and does not change.
    # Item 204: the words are wrapped live, and they are still the words.
    assert '{busy ? <Working>writing…</Working>' in body, body[:600]
    assert 'aria-live="polite"' in body, body[:600]


def test_pressing_it_posts_the_page_to_the_generator_and_nothing_else():
    part = (UI / "part_page.tsx").read_text(encoding="utf-8")
    body = part[part.index("export function WriteBrief"):]
    body = body[:body.index("\n}")]
    assert "expert/content-brief" in body, body[:600]
    assert "{ url: page }" in body, (
        "the page has to travel with the request; without it the generator "
        "writes a brief for whatever page the run started at")


def test_the_generator_emits_no_findings_so_none_can_reach_the_record():
    """The engine half of the same claim, held here so the two cannot
    drift: a brief with no checks may emit no rows, and the parser is what
    enforces it."""
    from clauditseo import briefs

    brief = briefs.by_id()["content-brief"]
    assert brief.kind == "generator", brief.kind
    assert brief.checks == (), brief.checks


def test_a_generator_block_is_read_as_a_document_not_as_an_empty_result():
    """An empty `rows` list on a findings brief means "nothing is wrong".
    On a generator it means "this is not that kind of answer", and reading
    one as the other would report a written brief as a clean page."""
    import json

    from clauditseo.analysts.contract import parse

    block = {"part": "content", "brief": "content-brief", "run_id": "r",
             "source": "generator", "page": "/pricing", "document_id": None,
             "assumptions": ["priority from nav order"]}
    parsed = parse("```json\n" + json.dumps(block) + "\n```\n\n### Working title\nX\n",
                   checks=[], page_set=["https://x.test/pricing"])
    assert parsed.generator is not None, parsed
    assert parsed.generator["page"] == "/pricing", parsed.generator
    assert parsed.rows == [] and parsed.dropped == [], (parsed.rows, parsed.dropped)
    assert parsed.assumptions == ["priority from nav order"], parsed.assumptions


# --- a ranking survives the contract parser --------------------------
# Item 196 retired the triage brief and the pane that spent on it. The
# clause below is not about either: it is about `analysts/contract.parse`
# holding a ranking block intact, and the contract format outlives the
# prompt that used to fill it. Its example block is historical.

def test_triages_ranking_and_its_scoring_model_survive_the_parser():
    """A score without the rule that produced it is a number an operator
    has to take on trust, and step 3 is where they decide what to buy."""
    import json

    from clauditseo.analysts.contract import parse

    block = {"part": "triage", "run_id": "r", "source": "brief",
             "model": {"business_value": "high 3 · med 2 · low 1",
                       "severity": "HIGH 3 · MEDIUM 2 · LOW 1"},
             "ranking": [{"rank": 1, "blocker": True, "check": "TEC/noindex-linked",
                          "part": "indexability", "pages": 2, "score": 9,
                          "inputs": {"business_value": 2, "severity": 3},
                          "why": "two pages noindexed", "quick_win": False,
                          "moved": "new"}]}
    parsed = parse("```json\n" + json.dumps(block) + "\n```\n\n## Ranking\n",
                   checks=[], page_set=["https://x.test/"])
    assert parsed.dropped == [], parsed.dropped
    assert len(parsed.ranking) == 1, parsed.ranking
    assert parsed.model["severity"].startswith("HIGH 3"), parsed.model
    assert parsed.as_dict()["model"] == parsed.model, (
        "the scoring model is filled by the parser and dropped by "
        "`as_dict`, so it exists only in memory and reaches no screen")
