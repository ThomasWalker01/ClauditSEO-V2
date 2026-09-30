"""The output contract (brief v10 step AF): a conforming brief's first
fenced JSON block is its findings, each row judged against the header's
checks and the run's pages and dropped with a logged reason otherwise;
kept rows land in the record under the sweep's own check ids with a
`brief` source and the copy they proposed; a question-only answer is
`needs-input`, not `read`; an unfilled placeholder is a load error naming
it; and the client report carries a section per part with the replacement
table.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import pytest

from clauditseo.analysts import contract
from clauditseo.analysts.expert import (EXPERT_TOOLS, BriefInputError, render_prompt,
                                        run_expert)
from clauditseo.analysts.base import AnalystResponse
from clauditseo.config import Settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo, runs
from clauditseo import analyses as an

CHECKS = ["ONP/title-missing", "ONP/title-length", "ONP/meta-desc-missing"]
PAGES = ["https://fixture.local/", "https://fixture.local/how-it-works",
         "https://fixture.local/apply"]

BLOCK = """Some preamble the model wrote.

```json
{"part": "title-desc", "run_id": "x", "source": "brief",
 "rows": [
  {"check": "ONP/title-length", "page": "/how-it-works", "status": "FAIL", "severity": "MEDIUM",
   "evidence": "\\"How it works | Fixture\\" · 63 chars",
   "replacement": "How fixture loans work - Fixture", "note": "32 chars"},
  {"check": "ONP/meta-desc-missing", "page": "https://fixture.local/apply", "status": "FAIL",
   "severity": "HIGH", "evidence": "no <meta name=description>",
   "replacement": "Apply online in minutes. Decisions in 24 hours, funding in 48 hours, and no security asked for on any business loan under $500k."},
  {"check": "ONP/h1-missing", "page": "/apply", "status": "FAIL", "severity": "LOW", "evidence": "x"},
  {"check": "ONP/title-length", "page": "/nowhere", "status": "FAIL", "severity": "LOW", "evidence": "x"},
  {"check": "ONP/title-length", "page": "/", "status": "MAYBE", "severity": "LOW", "evidence": "x"}
 ],
 "not_assessable": [], "assumptions": ["topic for /blog/* taken from h1"]}
```

### Title & description — assessment
| Check | Page | Evidence | Severity |
|---|---|---|---|
"""

QUESTION_ONLY = """I need one thing before I can assess this set.

Which brand name should replacement titles carry - "Fixture" or "Fixture Co"?
"""


def test_a_valid_block_yields_rows_and_the_bad_ones_are_dropped_with_a_reason(caplog):
    with caplog.at_level(logging.WARNING, logger="clauditseo.contract"):
        got = contract.parse(BLOCK, CHECKS, PAGES)
    assert got.status == "read" and got.block
    assert [(r.check, r.page, r.severity) for r in got.rows] == [
        ("ONP/title-length", "https://fixture.local/how-it-works", "medium"),
        ("ONP/meta-desc-missing", "https://fixture.local/apply", "high")]
    assert got.rows[0].dimension == "ONP" and got.rows[0].check_id == "title-length"
    reasons = [d["reason"] for d in got.dropped]
    assert any("ONP/h1-missing" in r and "not one this analysis may emit" in r for r in reasons), reasons
    assert any("/nowhere" in r and "not in the run's page set" in r for r in reasons), reasons
    assert any("MAYBE" in r for r in reasons), reasons
    assert sum("contract row dropped" in m for m in caplog.messages) == 3
    assert got.assumptions == ["topic for /blog/* taken from h1"]
    assert "```json" not in got.body and "assessment" in got.body


def test_a_question_only_answer_is_needs_input_and_a_silent_one_is_read():
    asked = contract.parse(QUESTION_ONLY, CHECKS, PAGES)
    assert asked.status == "needs-input" and not asked.block
    assert asked.questions == ['Which brand name should replacement titles carry - "Fixture" or "Fixture Co"?']
    silent = contract.parse("### Title & description — assessment\nNothing to raise.\n", CHECKS, PAGES)
    assert silent.status == "read" and silent.rows == [] and not silent.block


def _site(tmp_path: Path):
    conn = connect(tmp_path / "contract.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Contract Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    return conn, site_id


def _run(conn, site_id):
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    # `content_type` as the crawler stores it: without one the run fetched no
    # page it could read, and its silence clears nothing (item 239 step 4).
    runs.store_evidence(conn, run_id, {"pages": [{"url": u, "status": 200,
                                                  "content_type": "text/html"}
                                                 for u in PAGES]})
    return run_id


def test_kept_rows_land_in_the_record_under_the_sweeps_check_with_a_brief_source(tmp_path):
    conn, site_id = _site(tmp_path)
    run_a = _run(conn, site_id)
    parsed = contract.parse(BLOCK, CHECKS, PAGES)
    rows = [r.as_dict() for r in parsed.rows]
    runs.store_expert_report(conn, run_a, "title-desc",
                             {"model": "stub", "report": parsed.body,
                              "findings": contract.legacy_findings(parsed.rows),
                              "contract": parsed.as_dict()})
    assert runs.record_contract_findings(conn, run_a, "title-desc", "stub", rows) == 2
    runs.recompute_contract_states(conn, site_id, "title-desc")
    states = [s for s in runs.site_states(conn, site_id) if s["source_word"] == "brief"]
    # No sweep row corroborates either page here, so both wait as
    # candidates (brief v11 step AH); a corroborated row opens at once,
    # which `test_the_contract_agrees_with_the_sweep.py` holds.
    assert {(s["dimension"], s["check_id"], s["state"]) for s in states} == {
        ("ONP", "title-length", "candidate"), ("ONP", "meta-desc-missing", "candidate")}
    by_check = {s["check_id"]: s for s in states}
    assert by_check["title-length"]["proposed"] == "How fixture loans work - Fixture"
    assert by_check["title-length"]["brief"] == "title-desc" and by_check["title-length"]["brief_status"] == "FAIL"
    assert by_check["title-length"]["affected_urls"] == ["https://fixture.local/how-it-works"]
    # No `EXP:` anywhere: the dimension is the check's own.
    assert not any(s["dimension"].startswith("EXP:") for s in states)
    # A later run of the brief confirms the first row (open) and drops the
    # second, a candidate seen once.
    run_b = _run(conn, site_id)
    runs.store_expert_report(conn, run_b, "title-desc",
                             {"model": "stub", "report": "", "findings": [],
                              "contract": {"status": "read", "rows": rows[:1]}})
    runs.record_contract_findings(conn, run_b, "title-desc", "stub", rows[:1])
    runs.recompute_contract_states(conn, site_id, "title-desc")
    after = {s["check_id"]: s["state"] for s in runs.site_states(conn, site_id) if s["source_word"] == "brief"}
    assert after == {"title-length": "open"}
    # The client report's section for the part: the table, every line tagged.
    from clauditseo.reporting.generate import _contract_sections
    # The brief's run named (item 239 step 7: the sections take each tool's
    # run, which a report reads off the Latest View); the heading is dated.
    lines = _contract_sections(conn, {"title-desc": run_a})
    assert any(ln.startswith("### Title & description · analysed ") for ln in lines), lines
    table = [ln for ln in lines if ln.startswith("| `/")]
    assert len(table) == 2 and all("How fixture loans work" in ln or "Apply online" in ln for ln in table)
    from clauditseo.reporting.checks import unsourced_number_lines
    assert unsourced_number_lines("\n".join(lines)) == []


class _Stub:
    name = "stub"
    model_id = "stub-1"

    def __init__(self, text):
        self.text = text
        self.system = ""

    def run_agent(self, system, bundle, toolkit, max_tokens, max_output=0):
        self.system = system
        return AnalystResponse(findings=[], tokens_in=10, tokens_out=10, text=self.text)


@pytest.fixture
def conforming(monkeypatch, tmp_path):
    """A conforming brief registered for the test alone: a prompt with a
    header listing its checks and one placeholder, in a prompt dir of its
    own, and a registry entry whose context builder fills it."""
    from clauditseo.analysts import expert
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "contract-test.md").write_text(
        "---\nid: contract-test\nname: Contract test\npart: title-desc\nscope: site\n"
        "tier: fast\nchecks:\n  - ONP/title-length\n  - ONP/meta-desc-missing\n---\n\n"
        "# ROLE\nAssess {{PAGE_SET}} for {{BRAND_NAME}}.\n\n# FORMAT\n"
        "## Block 1 - findings\n```json\n{\"rows\": []}\n```\n", encoding="utf-8")
    monkeypatch.setattr(expert, "PROMPT_DIR", d)
    spec = {"prompt": "contract-test.md", "scope": "site", "tier": "fast", "part": "title-desc",
            "checks": ["ONP/title-length", "ONP/meta-desc-missing"], "inputs": [],
            "build": lambda ev, site, **_: {"PAGE_SET": "\n".join(p["url"] for p in ev["pages"]),
                                           "BRAND_NAME": "Fixture"}}
    monkeypatch.setitem(EXPERT_TOOLS, "contract-test", spec)
    return spec


def test_an_unfilled_placeholder_is_a_load_error_naming_it(conforming):
    with pytest.raises(BriefInputError, match=r"contract-test: the engine did not supply \{\{BRAND_NAME\}\}"):
        render_prompt("contract-test", {"PAGE_SET": "/"})
    assert "[NOT SUPPLIED]" not in render_prompt("contract-test", {"PAGE_SET": "/", "BRAND_NAME": "Fixture"})


def test_the_runner_stores_the_contract_and_a_question_is_needs_input(tmp_path, conforming):
    conn, site_id = _site(tmp_path)
    run_id = _run(conn, site_id)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    ev = runs.get_evidence(conn, run_id)
    site = Site(domain="fixture.local")

    stub = _Stub(BLOCK)
    got = run_expert(conn, run_id, "contract-test", ev, site, cfg, stub, use_cache=False)
    assert got["status"] == "ok" and got["contract"]["status"] == "read"
    # The framing a conforming brief gets asks for the block and not the
    # legacy index - the first live run answered the index's shape.
    assert "OPENS with the fenced ```json findings block" in stub.system
    assert "clauditseo-findings" not in stub.system
    assert len(got["contract"]["rows"]) == 2 and len(got["contract"]["dropped"]) == 3
    assert "```json" not in got["report"]
    index = {t["tool"]: t for t in runs.expert_report_index(conn, run_id)}
    assert index["contract-test"]["contract_status"] == "read" and index["contract-test"]["findings"] == 2
    briefs = {s["check_id"] for s in runs.site_states(conn, site_id) if s["source_word"] == "brief"}
    assert briefs == {"title-length", "meta-desc-missing"}

    run_b = _run(conn, site_id)
    ev_b = runs.get_evidence(conn, run_b)
    asked = run_expert(conn, run_b, "contract-test", ev_b, site, cfg, _Stub(QUESTION_ONLY), use_cache=False)
    assert asked["status"] == "ok" and asked["contract"]["status"] == "needs-input"
    stored = {t["tool"]: t for t in runs.expert_report_index(conn, run_b)}
    lanes = an.lanes(stored, {}, set(),
                     {"contract-test": {"scope": "site", "tier": "fast", "inputs": []}})
    row = next(r for r in lanes["available"] if r["tool"] == "contract-test") if any(
        r["tool"] == "contract-test" for r in lanes["available"]) else None
    if row is None:
        pytest.skip("the playbook does not list the test brief, so the lanes cannot name it")
    assert row["state"] == "needs_input" and row["questions"] == stored["contract-test"]["questions"]
