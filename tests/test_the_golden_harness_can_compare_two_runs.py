"""Two golden runs, and the question the harness exists to answer.

`scripts/run_golden.py` told the operator to pass a run id to `--compare` on
the next model. There was no such flag, so "does the deep tier earn its price"
was answered by reading two JSON blobs side by side and doing the arithmetic
by hand.

What a comparison has to say, and the tests here are one per clause:

  - which labels the candidate caught that the baseline missed,
  - **which it lost** — the direction a "which model is better" tool will
    quietly omit if nobody asserts it,
  - which both missed, so a shared blind spot is not read as agreement,
  - what each one cost, in tokens and in money where money is knowable.

The vocabulary is `expert_delta`'s — `new` / `resolved` / `persisting` — because
this is the same shape over a different population, and a second word for the
same relation is how two readers of one report end up disagreeing. `lost` is
the one addition: a catch that disappears is not a resolution.

The last test is the reason a comparison can be worse than no comparison. KI-56
deletes all but the last page of a page-scoped brief, so a run billed for three
pages stores one. A tool that reported the resulting difference as a model
difference would launder a persistence bug into a purchasing decision — which
is exactly what nearly happened to the two paid runs of 2026-08-24.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.golden import compare
from clauditseo.persistence import repo, runs

LABELS = {
    "expected": [
        {"tool": "onpage-hygiene", "page": "/blocked-drains",
         "mentions": ["h1"]},
        {"tool": "onpage-hygiene", "page": "/hot-water",
         "mentions": ["description"]},
        {"tool": "crawl", "code": "sitemap-coverage"},
    ],
    "known_absent": [
        {"tool": "hreflang", "code": "missing-return-tags"},
    ],
}


@pytest.fixture
def two_runs(tmp_path):
    conn = connect(tmp_path / "golden.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "G"),
                            "http://127.0.0.1/")

    def make(model: str):
        run_id = runs.create_run(conn, site, ["TEC"], "T2")

        def report(tool, page=None):
            runs.store_expert_report(
                conn, run_id, tool,
                {"model": model, "report": "r", "tokens": 100}, page_url=page)
            conn.execute(
                "UPDATE expert_reports SET model_id=? WHERE run_id=? AND tool_id=?",
                (model, run_id, tool))

        def raise_finding(tool, check_id, summary, url=None):
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id,"
                " severity, source, confidence, summary, affected_urls,"
                " fingerprint, created_at) VALUES (?, ?, ?, ?, 'medium',"
                " 'model-judgement', 'medium', ?, ?, ?, datetime('now'))",
                (f"{run_id}{check_id}{url}", run_id, f"EXP:{tool}", check_id,
                 summary, json.dumps([f"http://127.0.0.1{url}"] if url else []),
                 f"fp{run_id}{check_id}{url}"))
            conn.commit()

        return run_id, report, raise_finding

    return conn, make


def test_a_label_only_the_candidate_caught_is_named(two_runs):
    conn, make = two_runs
    base, report_a, raise_a = make("claude-sonnet-5")
    report_a("onpage-hygiene")
    cand, report_b, raise_b = make("claude-opus-5")
    report_b("onpage-hygiene")
    raise_b("onpage-hygiene", "heading-structure-broken",
            "No h1 anywhere in the document.", "/blocked-drains")

    out = compare(conn, base, cand, LABELS)

    assert out["caught"]["new"] == ["onpage-hygiene:/blocked-drains[h1]"]
    assert out["caught"]["lost"] == []


def test_a_label_the_candidate_lost_is_named(two_runs):
    """The direction that gets omitted. A comparison reporting only gains
    makes every newer model look better than the one it replaces."""
    conn, make = two_runs
    base, report_a, raise_a = make("claude-sonnet-5")
    report_a("onpage-hygiene")
    raise_a("onpage-hygiene", "h1-missing", "No h1 present.", "/blocked-drains")
    cand, report_b, _ = make("claude-opus-5")
    report_b("onpage-hygiene")

    out = compare(conn, base, cand, LABELS)

    assert out["caught"]["lost"] == ["onpage-hygiene:/blocked-drains[h1]"]
    assert out["caught"]["new"] == []


def test_a_label_both_missed_is_reported_as_a_shared_blind_spot(two_runs):
    """Two runs agreeing is not two runs being right, and a difference of
    zero must not read as coverage."""
    conn, make = two_runs
    base, report_a, _ = make("claude-sonnet-5")
    report_a("onpage-hygiene")
    cand, report_b, _ = make("claude-opus-5")
    report_b("onpage-hygiene")

    out = compare(conn, base, cand, LABELS)

    assert "onpage-hygiene:/blocked-drains[h1]" in out["caught"]["missed_by_both"]
    assert "onpage-hygiene:/hot-water[description]" in out["caught"]["missed_by_both"]


def test_a_trap_the_candidate_stopped_raising_is_named_as_resolved(two_runs):
    """A false positive dropped is worth as much as a catch gained, and the
    scorer counts them separately, so the comparison must too."""
    conn, make = two_runs
    base, report_a, raise_a = make("claude-sonnet-5")
    report_a("hreflang")
    raise_a("hreflang", "missing-return-tags", "No return tags found.")
    cand, report_b, _ = make("claude-opus-5")
    report_b("hreflang")

    out = compare(conn, base, cand, LABELS)

    assert out["false_positives"]["resolved"] == [
        "hreflang:missing-return-tags"]
    assert out["false_positives"]["new"] == []


def test_the_comparison_states_what_each_run_cost(two_runs):
    conn, make = two_runs
    base, report_a, _ = make("claude-sonnet-5")
    report_a("crawl")
    runs.log_cost(conn, base, "anthropic", "EXPERT:crawl", "tokens",
                  48216, actual_cost=0.10)
    cand, report_b, _ = make("claude-opus-5")
    report_b("crawl")
    runs.log_cost(conn, cand, "anthropic", "EXPERT:crawl", "tokens",
                  60486, actual_cost=0.30)

    out = compare(conn, base, cand, LABELS)

    assert out["baseline"]["spend"]["tokens"] == 48216
    assert out["candidate"]["spend"]["usd"] == pytest.approx(0.30)
    assert out["tokens_ratio"] == pytest.approx(60486 / 48216, rel=1e-3)
    assert out["usd_ratio"] == pytest.approx(3.0)
    assert out["baseline"]["models"] == ["claude-sonnet-5"]


def test_a_run_with_no_price_is_compared_on_tokens_and_says_why_not_on_money(
        two_runs):
    conn, make = two_runs
    base, report_a, _ = make("claude-sonnet-5")
    report_a("crawl")
    runs.log_cost(conn, base, "anthropic", "EXPERT:crawl", "tokens", 100)
    cand, report_b, _ = make("claude-opus-5")
    report_b("crawl")
    runs.log_cost(conn, cand, "anthropic", "EXPERT:crawl", "tokens", 200)

    out = compare(conn, base, cand, LABELS)

    assert out["usd_ratio"] is None
    assert out["tokens_ratio"] == pytest.approx(2.0)
    assert out["baseline"]["spend"]["usd_absent_because"]


def test_a_brief_billed_for_three_pages_that_stored_one_report_is_caveated(
        two_runs):
    """KI-56, detected from the evidence rather than warned about in prose.

    `cost_entries` holds one row per call and `expert_reports` is keyed
    `(run_id, tool_id)`, so three calls leaving one report is the deletion
    happening, visible without knowing the bug exists. Without this the
    comparison of the two paid runs of 2026-08-24 reports a tier difference
    that is entirely a persistence defect.
    """
    conn, make = two_runs
    base, report_a, _ = make("claude-sonnet-5")
    report_a("onpage-hygiene", page="http://127.0.0.1/hot-water")
    for _ in range(3):
        runs.log_cost(conn, base, "anthropic", "EXPERT:onpage-hygiene",
                      "tokens", 6000)
    cand, report_b, _ = make("claude-opus-5")
    report_b("onpage-hygiene", page="http://127.0.0.1/hot-water")

    out = compare(conn, base, cand, LABELS)

    assert any("onpage-hygiene" in c and "KI-56" in c
               for c in out["caveats"]), out["caveats"]


def test_a_clean_pair_carries_no_caveat(two_runs):
    """Or the caveat is decoration rather than a finding."""
    conn, make = two_runs
    base, report_a, _ = make("claude-sonnet-5")
    report_a("crawl")
    runs.log_cost(conn, base, "anthropic", "EXPERT:crawl", "tokens", 100)
    cand, report_b, _ = make("claude-opus-5")
    report_b("crawl")
    runs.log_cost(conn, cand, "anthropic", "EXPERT:crawl", "tokens", 100)

    assert compare(conn, base, cand, LABELS)["caveats"] == []
