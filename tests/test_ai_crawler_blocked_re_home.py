"""`ai-crawler-blocked` re-homed AIS -> TEC (item 137, brief v18 step AZ).

A robots.txt rule blocking the AI retrieval agents is a crawl-access failure by
cause, so the operator moved its weight from the AI-surface subscore to the
technical one. Four things are held, and together they are the acceptance the
channel asked for — the check moved dimension, its blocker verdict did not, its
triage rank did not, and the rows already stored moved with it:

  - TEC emits it now and AIS does not, so the technical subscore carries the
    deduction and the AI-surface subscore no longer does;
  - it is still a registered blocker, under its new full id;
  - migration 0048 moves the stored rows and carries their `finding_states`,
    so the standing reconciles exactly;
  - 0048 rewrites only the rows whose fingerprint its fixed subject reproduces.

The triage-order half is held in `test_memory.py`
(`test_triage_is_handed_rows_rather_than_score_tables`), which now asserts the
row ranks first under `TEC/ai-crawler-blocked` — the re-home does not change the
verdict.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.checks import blocker_checks, is_blocker
from clauditseo.crawler.types import CrawlResult
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Severity, Tier, fingerprint
from clauditseo.modules.ais import AiSurfaceModule
from clauditseo.modules.tec import TechnicalModule
from clauditseo.persistence import repo, runs

_BLOCKING_ROBOTS = "User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n"


def _blocking_crawl() -> CrawlResult:
    return CrawlResult(start_url="https://x.test/", tier=Tier.T2,
                       robots_txt=_BLOCKING_ROBOTS, robots_status=200)


# ---- the check moved dimension ---------------------------------------------

def test_tec_emits_ai_crawler_blocked_high():
    findings = TechnicalModule()._site_checks(_blocking_crawl())
    hit = [f for f in findings if f.check_id == "ai-crawler-blocked"]
    assert len(hit) == 1, [f.check_id for f in findings]
    assert hit[0].dimension == "TEC"
    assert hit[0].severity is Severity.HIGH
    assert hit[0].subject == "ai-crawler-access:GPTBot"  # one row per agent (item 145 BG)


def test_ais_no_longer_emits_ai_crawler_blocked():
    crawl = _blocking_crawl()
    findings = AiSurfaceModule().run(crawl.pages, Tier.T2, {"crawl": crawl})
    assert not any(f.check_id == "ai-crawler-blocked" for f in findings), (
        "AIS still emits the re-homed check — the move did not take, so its "
        "weight is counted twice")


# ---- the blocker verdict did not -------------------------------------------

def test_still_a_blocker_under_the_new_id():
    assert is_blocker("TEC/ai-crawler-blocked")
    assert "TEC/ai-crawler-blocked" in blocker_checks()
    assert "AIS/ai-crawler-blocked" not in blocker_checks(), (
        "the old full id is still registered — a stored AIS row or a stale "
        "prompt would match a blocker id nothing emits any more")


# ---- the stored rows moved with it -----------------------------------------

_MIG = (Path(__file__).resolve().parent.parent / "clauditseo" / "db"
        / "migrations" / "0048_ai_crawler_blocked_to_tec.py")


def _apply_0048(conn):
    spec = importlib.util.spec_from_file_location("mig_0048", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.apply(conn)


@pytest.fixture
def seeded(tmp_path):
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    yield conn, site_id
    conn.close()


def _seed_finding(conn, site_id, dimension, check_id, subject, severity="high"):
    run_id = runs.create_run(conn, site_id, ["AIS"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run_id,))
    fp = fingerprint(dimension, check_id, subject)
    from clauditseo.persistence.repo import create_id, now_iso
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
        " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, ?, ?, ?,"
        " 'deterministic', ?, ?, ?, ?)",
        (create_id(), run_id, dimension, check_id, severity,
         f"{check_id} on {subject}", '["https://x.test/"]', fp, now_iso()))
    conn.execute(
        "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
        " updated_at) VALUES (?, ?, 'accepted-risk', ?, ?)",
        (site_id, fp, run_id, now_iso()))
    return fp


def test_0048_moves_the_stored_row_and_carries_its_state(seeded):
    conn, site_id = seeded
    old_fp = _seed_finding(conn, site_id, "AIS", "ai-crawler-blocked",
                           "ai-crawler-access")
    new_fp = fingerprint("TEC", "ai-crawler-blocked", "ai-crawler-access")
    assert old_fp != new_fp

    _apply_0048(conn)

    row = conn.execute(
        "SELECT dimension, fingerprint FROM findings WHERE check_id='ai-crawler-blocked'"
    ).fetchone()
    assert row["dimension"] == "TEC"
    assert row["fingerprint"] == new_fp
    # The standing followed the finding to its new identity — nothing left at
    # the old id, the accepted state intact at the new one.
    assert conn.execute("SELECT COUNT(*) c FROM finding_states WHERE fingerprint=?",
                        (old_fp,)).fetchone()["c"] == 0
    state = conn.execute("SELECT state FROM finding_states WHERE fingerprint=?",
                         (new_fp,)).fetchone()
    assert state["state"] == "accepted-risk"


def test_0048_leaves_an_unrelated_row_alone(seeded):
    conn, site_id = seeded
    # Same check id but a subject its fixed-subject guard cannot reproduce: a
    # row 0048 must not touch, or the guard is not doing its job.
    other_fp = _seed_finding(conn, site_id, "AIS", "ai-crawler-blocked",
                             "/some-page")

    _apply_0048(conn)

    row = conn.execute("SELECT dimension, fingerprint FROM findings"
                       " WHERE fingerprint=?", (other_fp,)).fetchone()
    assert row is not None and row["dimension"] == "AIS", (
        "0048 rewrote a row whose fingerprint its subject does not reproduce")
