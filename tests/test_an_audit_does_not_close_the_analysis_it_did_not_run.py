"""Item 223 (Title & description, change 2): an audit does not close an
analysis row it still raises.

The filing asked whether the 36 missing replacements were never written or
lost on the way to the card. Neither: the stored twenty22 contract holds 42
rows, every one with a replacement. They were CLOSED. `_apply_states` clears
every open row of an audited dimension whose fingerprint the run did not
emit, and a brief row's fingerprint is its own - no sweep ever emits it. So
the ONP-only T2 of 2026-09-23 moved 36 title-desc rows to `fixed` while
re-raising the same check on the same pages, and `fixesOf` (open, regressed
and candidate only) drew the sweep's cards without the analysis's copy.

The rule now (item 240, which tightened what this item first built): a sweep
never clears an analysis row. Its state is its brief's walk
(`recompute_contract_states`); an audit that did not run the analysis has not
looked for it, whether or not the sweep still raises the same check on the
page. `runs.measured` holds the rule.
"""

from __future__ import annotations

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import AuditResult
from clauditseo.engine.types import Finding, Severity, Site, Tier
from clauditseo.persistence import repo, runs

BASE = "https://closes.test"
A, B = BASE + "/a/", BASE + "/b/"


def _sweep(check, url):
    return Finding(dimension="ONP", check_id=check, severity=Severity.MEDIUM,
                   summary=f"{check} on {url}", subject=f"{check}:{url}", affected_urls=[url])


def _audit(conn, site, findings):
    run = runs.create_run(conn, site, ["ONP"], "T2")
    runs.complete_run(conn, run, AuditResult(
        site=Site(domain=BASE + "/"), tier=Tier.T2, dimensions=["ONP"], findings=findings,
        crawled_paths={"/a/", "/b/"}))
    return run


def _brief(conn, site, run, rows):
    runs.store_expert_report(conn, run, "title-desc", {
        "model": "m-1", "cost": 0.2, "report": "## Title & description", "findings": [],
        "contract": {"status": "read", "part": "title-desc", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run, "title-desc", "m-1", rows)
    runs.recompute_contract_states(conn, site, "title-desc")


def _row(check, page):
    return {"check": f"ONP/{check}", "dimension": "ONP", "check_id": check, "page": page,
            "status": "WARN", "severity": "medium", "evidence": "x",
            "replacement": "A new description of the right length for this page, "
                           "naming the service and the place it is offered in.",
            "note": ""}


def _states(conn, site):
    return {(r["check_id"], r["url"]): r["state"] for r in conn.execute(
        "SELECT f.check_id, json_extract(f.affected_urls, '$[0]') AS url, s.state"
        " FROM findings f JOIN finding_states s ON s.fingerprint=f.fingerprint AND s.site_id=?"
        " WHERE f.source='model-judgement'", (site,))}


def _setup(tmp_path):
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "closes.test")
    first = _audit(conn, site, [_sweep("meta-desc-length", A), _sweep("meta-desc-length", B)])
    _brief(conn, site, first, [_row("meta-desc-length", A), _row("meta-desc-length", B),
                               _row("title-entity-alignment", A)])
    return conn, site


def test_the_analysis_rows_open_on_the_audit_that_corroborates_them(tmp_path):
    conn, site = _setup(tmp_path)
    got = _states(conn, site)
    assert got[("meta-desc-length", A)] == "open", got
    assert got[("title-entity-alignment", A)] == "candidate", got


def test_a_later_audit_that_re_raises_the_check_leaves_the_analysis_open(tmp_path):
    conn, site = _setup(tmp_path)
    _audit(conn, site, [_sweep("meta-desc-length", A), _sweep("meta-desc-length", B)])
    got = _states(conn, site)
    assert got[("meta-desc-length", A)] == "open", got
    assert got[("meta-desc-length", B)] == "open", got


def test_a_later_audit_that_no_longer_raises_it_on_that_page_leaves_it_too(tmp_path):
    """223 first let this audit close the row - the corroborating reading
    gone. Item 240 withholds that too: the audit did not run the analysis."""
    conn, site = _setup(tmp_path)
    _audit(conn, site, [_sweep("meta-desc-length", B)])
    got = _states(conn, site)
    assert got[("meta-desc-length", A)] == "open", got
    assert got[("meta-desc-length", B)] == "open", got


def test_a_check_only_a_model_raises_is_not_closed_by_an_audit(tmp_path):
    conn, site = _setup(tmp_path)
    before = _states(conn, site)[("title-entity-alignment", A)]
    # Promote it to open the way a second brief run would, then audit again.
    conn.execute("UPDATE finding_states SET state='open' WHERE site_id=? AND fingerprint IN"
                 " (SELECT fingerprint FROM findings WHERE check_id='title-entity-alignment')",
                 (site,))
    conn.commit()
    _audit(conn, site, [_sweep("meta-desc-length", A)])
    assert before == "candidate"
    assert _states(conn, site)[("title-entity-alignment", A)] == "open"


def test_the_migration_reopens_what_the_old_rule_closed_and_only_that(tmp_path):
    """0065 repairs the stored record: a row an audit closed while re-raising
    it is reopened; one it closed because the reading was gone stays fixed."""
    import importlib.util
    from pathlib import Path
    conn, site = _setup(tmp_path)
    later = _audit(conn, site, [_sweep("meta-desc-length", B)])
    # What the old rule wrote: both rows closed by an audit that ran no brief.
    conn.execute("UPDATE finding_states SET state='fixed', changed_by_run=? WHERE site_id=?"
                 " AND fingerprint IN (SELECT fingerprint FROM findings"
                 " WHERE source='model-judgement' AND check_id='meta-desc-length')",
                 (later, site))
    conn.commit()
    path = (Path(__file__).resolve().parents[1] / "clauditseo" / "db" / "migrations"
            / "0065_analysis_rows_an_audit_closed.py")
    spec = importlib.util.spec_from_file_location("m0065", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.apply(conn)
    got = _states(conn, site)
    assert got[("meta-desc-length", B)] == "open", got     # re-raised: wrongly closed
    # Not re-raised: 223's migration left this closed. Item 240's re-derive,
    # not this migration, decides it now.
    assert got[("meta-desc-length", A)] == "fixed", got
    mod.apply(conn)
    assert _states(conn, site) == got, "the repair is not idempotent"
