"""Q-56 (item 137-answer): Content's analysis rows are stored under
`EXP:<brief>`, its free checks stay under `CNT`, and the move of the rows
already in the record preserves the standing exactly.

Two things are held:

  - the recorder routes a content ANALYSIS row to `EXP:<brief>` and a FREE
    content check to `CNT`, by the check's own cost — the Free/Analysis split
    applied to storage;
  - migration 0046 moves the rows already stored the old way and carries their
    finding_states with them, so the part-page category (which buckets by
    check id, not dimension) and the standing reconcile exactly, and the free
    rows — the only ones the score reads — are untouched.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo import anatomy
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


_MIG = (Path(__file__).resolve().parent.parent / "clauditseo" / "db"
        / "migrations" / "0046_content_analysis_to_exp.py")


def _apply_0046(conn):
    spec = importlib.util.spec_from_file_location("mig_0046", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.apply(conn)


def _row(check_id, page, severity="high"):
    return {"check": f"CNT/{check_id}", "check_id": check_id, "dimension": "CNT",
            "page": page, "severity": severity, "status": "FAIL",
            "evidence": f"{check_id} on {page}", "replacement": "do the thing"}


@pytest.fixture
def seeded(tmp_path):
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    yield conn, site_id
    conn.close()


def _complete(conn, site_id):
    run_id = runs.create_run(conn, site_id, ["CNT"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run_id,))
    conn.commit()
    return run_id


# --- the recorder routes by the check's cost --------------------------------

def test_the_recorder_splits_content_analysis_from_free(seeded):
    conn, site_id = seeded
    run_id = _complete(conn, site_id)
    runs.record_contract_findings(conn, run_id, "content-coverage", "m-1", [
        _row("gap", "https://x.test/a"),          # analysis -> EXP
        _row("intent-gap", "https://x.test/b"),   # analysis -> EXP
        _row("thin", "https://x.test/c"),         # free -> CNT
    ])
    got = {r["check_id"]: r["dimension"] for r in conn.execute(
        "SELECT check_id, dimension FROM findings WHERE run_id=?", (run_id,))}
    assert got["gap"] == "EXP:content-coverage"
    assert got["intent-gap"] == "EXP:content-coverage"
    assert got["thin"] == "CNT", "a free content check stays under CNT"


def test_storage_dimension_is_the_one_rule():
    assert runs.contract_storage_dimension("content-substance", "eeat", "CNT") \
        == "EXP:content-substance"
    assert runs.contract_storage_dimension("content-substance", "stale", "CNT") \
        == "CNT"
    # Every other dimension is returned unchanged — only content writes model
    # rows under CNT.
    assert runs.contract_storage_dimension("onpage-hygiene", "title-length",
                                           "ONP") == "ONP"


# --- the migration moves the old rows and keeps the standing ----------------

def _seed_old_way(conn, site_id, monkeypatch):
    """Store content-analysis rows as the pre-Q56 recorder did — under CNT —
    by neutralising the routing for the length of the store, then walk their
    states. This is the faithful 'before' the migration transforms."""
    run_id = _complete(conn, site_id)
    monkeypatch.setattr(runs, "contract_storage_dimension",
                        lambda tool, check, base: base)
    runs.record_contract_findings(conn, run_id, "content-coverage", "m-1", [
        _row("gap", "https://x.test/a"),
        _row("intent-gap", "https://x.test/b"),
        _row("thin", "https://x.test/c"),   # free — must be left under CNT
    ])
    monkeypatch.undo()
    # A deterministic free finding + its state — what the score reads, and
    # what must not move.
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
        " summary, affected_urls, fingerprint, created_at)"
        " VALUES (?, ?, 'CNT', 'thin', 'low', 'deterministic', 't', ?, ?, ?)",
        (repo.create_id(), run_id, json.dumps(["https://x.test/c"]),
         "det-thin-fp", repo.now_iso()))
    conn.execute(
        "INSERT INTO finding_states (site_id, fingerprint, state, updated_at)"
        " VALUES (?, 'det-thin-fp', 'open', ?)", (site_id, repo.now_iso()))
    conn.commit()
    runs.recompute_contract_states(conn, site_id, "content-coverage")
    return run_id


def _standing_by_category(conn, site_id):
    """The part page's own reading: the state of each row keyed by the things
    that do not change in the move — its category (which buckets by check id),
    its check, whether it is a brief or sweep row, and the page it names. The
    dimension and the fingerprint are deliberately not in the key: those are
    exactly what 0046 changes, and the standing must read the same without
    them."""
    out = {}
    for s in runs.site_states(conn, site_id):
        cat = anatomy.categorise(s["check_id"], s["dimension"])
        key = (cat, s["check_id"], s["source_word"], tuple(s["affected_urls"]))
        out[key] = s["state"]
    return out


def test_the_migration_moves_the_rows_and_keeps_the_standing(seeded, monkeypatch):
    conn, site_id = seeded
    _seed_old_way(conn, site_id, monkeypatch)

    before = _standing_by_category(conn, site_id)
    # Every content row is under CNT before the move.
    dims_before = {r["check_id"]: r["dimension"] for r in conn.execute(
        "SELECT check_id, dimension FROM findings WHERE source='model-judgement'")}
    assert set(dims_before.values()) == {"CNT"}, dims_before

    # Apply the migration by hand: migrate() already ran it on the empty DB
    # at fixture time, so call it directly against the seeded rows.
    _apply_0046(conn)
    conn.commit()

    after = _standing_by_category(conn, site_id)
    # The standing reconciles exactly: same categories, same checks, same
    # states. This is the whole of "reconcile exactly".
    assert after == before, f"standing changed\nbefore={before}\nafter={after}"

    dims_after = {r["check_id"]: r["dimension"] for r in conn.execute(
        "SELECT check_id, dimension FROM findings WHERE source='model-judgement'")}
    assert dims_after["gap"] == "EXP:content-coverage"
    assert dims_after["intent-gap"] == "EXP:content-coverage"
    # The free content check (model source, but a free check) stays.
    assert dims_after["thin"] == "CNT"
    # The deterministic free row and its state — what the score reads — are
    # untouched.
    det = conn.execute("SELECT dimension FROM findings WHERE fingerprint='det-thin-fp'"
                       ).fetchone()
    assert det["dimension"] == "CNT"
    assert conn.execute("SELECT state FROM finding_states WHERE fingerprint='det-thin-fp'"
                        ).fetchone()["state"] == "open"


def test_a_migrated_row_matches_a_natively_stored_one(seeded, monkeypatch):
    """The migration and the recorder agree: a row moved by 0046 lands on the
    same dimension and fingerprint a fresh run would give it, so the standing
    continues across the move rather than restarting."""
    conn, site_id = seeded
    _seed_old_way(conn, site_id, monkeypatch)
    _apply_0046(conn)
    conn.commit()
    migrated = conn.execute(
        "SELECT dimension, fingerprint FROM findings"
        " WHERE check_id='gap' AND source='model-judgement'").fetchone()

    # Store the same row natively (routing on) in a second run.
    run2 = _complete(conn, site_id)
    runs.record_contract_findings(conn, run2, "content-coverage", "m-1",
                                  [_row("gap", "https://x.test/a")])
    native = conn.execute(
        "SELECT dimension, fingerprint FROM findings"
        " WHERE check_id='gap' AND run_id=?", (run2,)).fetchone()
    assert migrated["dimension"] == native["dimension"] == "EXP:content-coverage"
    assert migrated["fingerprint"] == native["fingerprint"]


# --- the deliverable: content analysis renders caveated, under Analysis -----

def test_a_content_analysis_row_renders_in_the_briefs_not_analyst_insights(seeded):
    """After the move, a content-analysis figure reaches the client document
    through `_expert_section` — under **Analysis**, caveated where the run
    cannot ground it — instead of `_analyst_section`, whose stricter grounding
    refused the whole document. G7 passes rather than raising."""
    from clauditseo.reporting import generate as gen

    conn, site_id = seeded
    run_id = runs.create_run(conn, site_id, ["CNT"], "T2")
    runs.store_evidence(conn, run_id, {
        "start_url": "https://x.test/", "started_at": repo.now_iso(),
        "pages": [{"url": "https://x.test/", "status": 200, "title": "T",
                   "canonical": "https://x.test/"}]})
    runs.record_contract_findings(conn, run_id, "content-coverage", "claude-sonnet-5",
                                  [_row("gap", "https://x.test/")
                                   | {"evidence": "22 service nodes have no page"}])
    runs.store_expert_report(conn, run_id, "content-coverage", {
        "model": "claude-sonnet-5", "report": "## Coverage\n22 nodes absent.",
        "findings": [{"severity": "high", "code": "gap",
                      "summary": "22 service nodes have no page"}],
        "contract": {"status": "read"}})
    runs.recompute_contract_states(conn, site_id, "content-coverage")
    runs.mark_complete(conn, run_id, repo.now_iso())
    conn.commit()

    # Item 237: `gap` is a check no sweep can raise, so its row waits for the
    # operator and reaches the client only once confirmed.
    waiting = gen.generate(conn, "run", "client", [run_id])["markdown"]
    assert "22 service nodes have no page" not in waiting
    for fp in runs.awaiting_confirmation(conn, site_id):
        runs.set_state(conn, site_id, fp, "open")
    md = gen.generate(conn, "run", "client", [run_id])["markdown"]  # G7 runs here
    assert "## Specialist briefs" in md
    briefs = md.split("## Specialist briefs", 1)[1]
    assert "22 service nodes have no page" in briefs
    # Under Analysis, not Free checks — it is a model finding.
    analysis = briefs.split("**Analysis**", 1)
    assert len(analysis) == 2 and "22 service nodes" in analysis[1].split("**", 1)[0]
    # Caveated, because the cross-run figure is not in this run's evidence.
    row = [ln for ln in briefs.splitlines() if "22 service nodes" in ln][0]
    assert "[TO CONFIRM" in row
    # Not double-rendered into Analyst insights.
    if "## Analyst insights" in md:
        ai = md.split("## Analyst insights", 1)[1].split("## ", 1)[0]
        assert "22 service nodes" not in ai
