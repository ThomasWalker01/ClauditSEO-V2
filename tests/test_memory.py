"""The expert memory: code-level states, the fix loop, diffs, the watch,
spend, scheduling and the golden harness.

The property that binds them: model output varies run to run, so every rule
here exists to stop that variance masquerading as change - and to stop real
change being missed because a tool simply did not run.
"""

from __future__ import annotations

from pathlib import Path

import datetime
import re

import pytest

import clauditseo.modules  # noqa: F401
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import fingerprint as make_fingerprint
from clauditseo.persistence import repo, runs


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "memory.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Memory Co")
    site_id = repo.create_site(conn, client, "memory.test")
    yield conn, site_id
    conn.close()


def _run_tool(conn, site_id, tool, codes):
    """Simulate one audit run on which `tool` ran and raised `codes`."""
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, tool,
                             {"model": "m", "report": "r", "tokens": 10})
    runs.record_expert_findings(conn, run_id, tool, "m", [
        {"severity": "high", "code": c, "summary": f"{c} present",
         "affected_urls": []} for c in codes])
    return run_id


def fp(tool, code):
    return make_fingerprint(f"EXP:{tool}", code, "site")


def state_of(conn, site_id, tool, code):
    row = conn.execute("SELECT state FROM finding_states WHERE site_id=?"
                       " AND fingerprint=?", (site_id, fp(tool, code))).fetchone()
    return row["state"] if row else None


# --- the state walk ----------------------------------------------------------

def test_one_appearance_is_a_candidate_not_an_open_finding(db):
    conn, site = db
    _run_tool(conn, site, "local-signals", {"nap-missing"})
    assert state_of(conn, site, "local-signals", "nap-missing") == "candidate"


def test_a_second_appearance_opens_it(db):
    conn, site = db
    _run_tool(conn, site, "local-signals", {"nap-missing"})
    _run_tool(conn, site, "local-signals", {"nap-missing"})
    assert state_of(conn, site, "local-signals", "nap-missing") == "open"


def test_a_candidate_that_fails_to_reappear_is_dropped_not_remembered(db):
    """One appearance then gone is the flap the benchmark measured - noise,
    not a finding, and not a fix either."""
    conn, site = db
    _run_tool(conn, site, "local-signals", {"nap-missing"})
    _run_tool(conn, site, "local-signals", set())
    assert state_of(conn, site, "local-signals", "nap-missing") is None


def test_open_then_absent_is_fixed_and_reappearance_is_regressed(db):
    conn, site = db
    for codes in ({"x"}, {"x"}, set()):
        _run_tool(conn, site, "t", codes)
    assert state_of(conn, site, "t", "x") == "fixed"
    _run_tool(conn, site, "t", {"x"})
    assert state_of(conn, site, "t", "x") == "regressed"


def test_a_run_where_the_tool_did_not_run_says_nothing(db):
    """Absence of a check is never evidence of a fix."""
    conn, site = db
    _run_tool(conn, site, "t", {"x"})
    _run_tool(conn, site, "t", {"x"})            # open
    runs.create_run(conn, site, ["TEC"], "T2")   # audit run, tool absent
    runs.recompute_expert_states(conn, site, "t")
    assert state_of(conn, site, "t", "x") == "open"


def test_recompute_is_idempotent_and_replay_safe(db):
    conn, site = db
    _run_tool(conn, site, "t", {"x"})
    for _ in range(3):                            # cache replays re-record
        runs.recompute_expert_states(conn, site, "t")
    assert state_of(conn, site, "t", "x") == "candidate", \
        "replaying one run must not count as a second appearance"


def test_accepted_risk_is_the_operators_decision_and_survives(db):
    conn, site = db
    _run_tool(conn, site, "t", {"x"})
    _run_tool(conn, site, "t", {"x"})
    runs.set_state(conn, site, fp("t", "x"), "accepted-risk")
    _run_tool(conn, site, "t", {"x"})
    assert state_of(conn, site, "t", "x") == "accepted-risk"


def test_a_replay_of_stored_history_does_not_undo_a_withdrawal(db):
    """The runs that raised a withdrawn finding are the ones being retracted.

    `recompute_expert_states` walks the stored history from scratch, so
    without this the withdrawal would be reversed by re-reading the very
    evidence it was a judgement about - a check whose evidence cannot
    disagree with it (DISCIPLINE rule 5). Only a new run reopens it, and
    that path is `_apply_states`, guarded in test_history_g4.
    """
    conn, site = db
    _run_tool(conn, site, "t", {"x"})
    _run_tool(conn, site, "t", {"x"})
    runs.set_state(conn, site, fp("t", "x"), "withdrawn")
    for _ in range(3):
        runs.recompute_expert_states(conn, site, "t")
    assert state_of(conn, site, "t", "x") == "withdrawn"


def test_deterministic_sweeps_never_touch_expert_states(db):
    """_apply_states marks absent fingerprints fixed - but only within the
    dimensions it audited, which EXP:* can never be."""
    conn, site = db
    _run_tool(conn, site, "t", {"x"})
    _run_tool(conn, site, "t", {"x"})

    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Site, Tier
    result = AuditResult(site=Site(domain="memory.test"), tier=Tier.T2,
                         dimensions=["TEC"])
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.complete_run(conn, run_id, result)
    assert state_of(conn, site, "t", "x") == "open"


# --- fix loop ----------------------------------------------------------------

def test_an_attempt_survives_the_verdict_either_way(db):
    conn, site = db
    _run_tool(conn, site, "t", {"x"})
    _run_tool(conn, site, "t", {"x"})
    assert runs.mark_attempt(conn, site, fp("t", "x"), "swapped the template")

    _run_tool(conn, site, "t", set())            # verdict: fixed
    row = conn.execute("SELECT state, attempted_at, attempt_note FROM"
                       " finding_states WHERE site_id=? AND fingerprint=?",
                       (site, fp("t", "x"))).fetchone()
    assert row["state"] == "fixed"
    assert row["attempted_at"] and row["attempt_note"] == "swapped the template"


def test_marking_an_attempt_on_nothing_says_so(db):
    conn, site = db
    assert runs.mark_attempt(conn, site, "no-such-fp") is False


# --- diff --------------------------------------------------------------------

def test_expert_delta_reports_new_resolved_and_persisting(db):
    conn, site = db
    _run_tool(conn, site, "t", {"a", "b"})
    _run_tool(conn, site, "t", {"b", "c"})
    delta = {d["tool"]: d for d in runs.expert_delta(conn, site)}["t"]
    assert delta["new"] == ["c"]
    assert delta["resolved"] == ["a"]
    assert delta["persisting"] == ["b"]
    assert delta["since"] is not None


def test_expert_delta_with_one_run_has_nothing_to_compare(db):
    conn, site = db
    _run_tool(conn, site, "t", {"a"})
    delta = runs.expert_delta(conn, site)[0]
    assert delta["since"] is None and delta["new"] == ["a"]


# --- watch -------------------------------------------------------------------

def _complete_run_with_evidence(conn, site_id, evidence):
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_evidence(conn, run_id, evidence)
    with conn:
        conn.execute("UPDATE audit_runs SET status='complete',"
                     " started_at=?, finished_at=? WHERE id=?",
                     (repo.now_iso(), repo.now_iso(), run_id))
    return run_id


def test_watch_flags_robots_and_llms_changes_between_crawls(db):
    conn, site = db
    base = {"robots_status": 200, "robots_txt": "User-agent: *", "pages": [],
            "llms_txt_status": 404, "sitemap_entry_total": 100}
    _complete_run_with_evidence(conn, site, base)
    _complete_run_with_evidence(conn, site, {**base, "robots_status": 404,
                                             "llms_txt_status": 200})
    alerts = {a["what"]: a for a in runs.watch_changes(conn, site)}
    assert alerts["robots.txt HTTP status"]["severity"] == "critical"
    assert alerts["llms.txt HTTP status"]["before"] == 404


def test_watch_needs_two_crawls_and_stays_quiet_on_no_change(db):
    conn, site = db
    base = {"robots_status": 200, "robots_txt": "x", "llms_txt_status": 404,
            "sitemap_entry_total": 50, "pages": []}
    _complete_run_with_evidence(conn, site, base)
    assert runs.watch_changes(conn, site) == []
    _complete_run_with_evidence(conn, site, dict(base))
    assert runs.watch_changes(conn, site) == []


# --- scheduler ---------------------------------------------------------------

def test_due_sites_respects_interval_running_guard_and_first_run_rule(db):
    from clauditseo.scheduler import due_sites
    conn, site = db
    with conn:
        conn.execute("UPDATE sites SET schedule='weekly' WHERE id=?", (site,))
    now = datetime.datetime.now()

    # Never crawled: the first run belongs to the operator.
    assert due_sites(conn, now) == []

    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    with conn:
        conn.execute("UPDATE audit_runs SET status='complete', started_at=?"
                     " WHERE id=?",
                     ((now - datetime.timedelta(days=8)).isoformat(), run_id))
    assert [s["id"] for s in due_sites(conn, now)] == [site]

    # An audit already running means skip, not stack.
    runs.create_run(conn, site, ["TEC"], "T2")
    assert due_sites(conn, now) == []


# --- spend and budget --------------------------------------------------------

def test_monthly_spend_groups_by_client_and_month(db):
    conn, site = db
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.log_cost(conn, run_id, "llm", "EXPERT:t", "tokens", 1000,
                  actual_cost=0.5)
    runs.log_cost(conn, run_id, "llm", "EXPERT:u", "tokens", 2000,
                  actual_cost=1.0)
    ledger = runs.monthly_spend(conn)
    assert len(ledger) == 1
    assert ledger[0]["client"] == "Memory Co"
    assert ledger[0]["tokens"] == 3000 and ledger[0]["usd"] == 1.5


# --- golden ------------------------------------------------------------------

def test_golden_scores_catch_rate_misses_and_traps(db):
    from clauditseo.golden import score
    conn, site = db
    run_id = _run_tool(conn, site, "local-signals",
                       {"nap-missing", "thin-location-page"})
    labels = {"expected": [
                  {"tool": "local-signals", "code": "nap-missing"},
                  {"tool": "local-signals", "code": "opening-hours-missing"},
                  {"tool": "hreflang", "code": "missing-return-tags"}],
              "known_absent": [
                  {"tool": "local-signals", "code": "thin-location-page"}]}
    result = score(conn, run_id, labels)
    tool = result["tools"]["local-signals"]
    assert tool["caught"] == ["nap-missing"]
    assert tool["missed"] == ["opening-hours-missing"]
    assert tool["false_positives"] == ["thin-location-page"]
    assert tool["catch_rate"] == 0.5
    # hreflang never ran: not scored, not punished.
    assert result["tools"]["hreflang"]["scored"] is False
    assert result["total_false_positives"] == 1


# --- optional external enhancers ---------------------------------------------
#
# The rule they all share: configured means fetched automatically, absent
# means silent — the briefs already say what they cannot see, and no UI
# offers a run it cannot perform.

def test_gsc_table_puts_the_worst_click_movers_first():
    from clauditseo.analysts.expert import _gsc_table
    table = _gsc_table({
        "property": "sc-domain:x.test", "window_days": 28,
        "previous": {"https://x.test/a": {"clicks": 100, "impressions": 900},
                     "https://x.test/b": {"clicks": 5, "impressions": 50}},
        "current": {"https://x.test/a": {"clicks": 40, "impressions": 700},
                    "https://x.test/b": {"clicks": 25, "impressions": 300}}})
    assert "measured not estimated" in table
    a, b = table.index("https://x.test/a"), table.index("https://x.test/b")
    assert a < b, "the page that lost 60 clicks outranks the one that gained"
    assert "| -60 |" in table and "| +20 |" in table


def test_freshness_uses_gsc_when_supplied_and_says_so_when_not(db):
    from clauditseo.analysts.expert import _freshness_context

    from clauditseo.engine.types import Site
    ev = {"start_url": "https://x.test/", "pages": []}
    without = _freshness_context(ev, Site(domain="x.test"))
    assert "cannot be observed here" in without["PERFORMANCE_DATA"]

    gsc = {"property": "sc-domain:x.test", "window_days": 28,
           "previous": {"https://x.test/a": {"clicks": 9, "impressions": 90}},
           "current": {"https://x.test/a": {"clicks": 2, "impressions": 40}}}
    with_data = _freshness_context(ev, Site(domain="x.test"), gsc=gsc)
    assert "Search Console" in with_data["PERFORMANCE_DATA"]
    assert "| -7 |" in with_data["PERFORMANCE_DATA"]


def test_review_series_needs_two_snapshots_before_it_speaks(db):
    from clauditseo.analysts.expert import build_context
    from clauditseo.engine.types import Site
    ev = {"start_url": "https://x.test/", "pages": []}

    one = build_context("review-signals", ev, Site(domain="x.test"),
                        review_series=[
                            {"captured_at": "2026-08-01T00:00:00",
                             "metric_key": "gbp.review_count", "value": 77.0},
                            {"captured_at": "2026-08-01T00:00:00",
                             "metric_key": "gbp.rating", "value": 4.8}])
    assert "REVIEW COUNT OVER TIME" not in one["REVIEW_EXPORT"], \
        "one snapshot is a point, not a series"

    two = build_context("review-signals", ev, Site(domain="x.test"),
                        review_series=[
                            {"captured_at": "2026-08-01T00:00:00",
                             "metric_key": "gbp.review_count", "value": 77.0},
                            {"captured_at": "2026-08-01T00:00:00",
                             "metric_key": "gbp.rating", "value": 4.8},
                            {"captured_at": "2026-09-01T00:00:00",
                             "metric_key": "gbp.review_count", "value": 85.0},
                            {"captured_at": "2026-09-01T00:00:00",
                             "metric_key": "gbp.rating", "value": 4.8}])
    assert "REVIEW COUNT OVER TIME" in two["REVIEW_EXPORT"]
    assert "per month" in two["REVIEW_EXPORT"]


def test_unconfigured_providers_refuse_rather_than_guess():
    import dataclasses

    import pytest as _pytest

    from clauditseo.config import Settings
    from clauditseo.providers.base import NotConfigured
    from clauditseo.providers.google import CruxHistory, SearchConsole
    bare = dataclasses.replace(Settings(), crux_api_key="",
                               google_service_account="")
    assert CruxHistory(bare).available() is False
    with _pytest.raises(NotConfigured):
        CruxHistory(bare).series("https://x.test/")
    assert SearchConsole(bare).available() is False


def test_indexnow_is_silent_without_a_key(db):
    """complete_run must not reach for the network when no key is set —
    the submission is an enhancer, never a dependency."""
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Site, Tier
    conn, site = db
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.complete_run(conn, run_id, AuditResult(
        site=Site(domain="memory.test"), tier=Tier.T2, dimensions=["TEC"]))
    progress = conn.execute("SELECT progress FROM audit_runs WHERE id=?",
                            (run_id,)).fetchone()["progress"]
    assert "IndexNow" not in (progress or "")


# --- imported crawls and the remaining internals -----------------------------

SF_CSV = (
    '"Internal - All"\n'
    '"Address","Content Type","Status Code","Indexability","Title 1",'
    '"Meta Description 1","H1-1","Word Count","Crawl Depth","Canonical Link Element 1",'
    '"Meta Robots 1"\n'
    '"https://x.test/","text/html; charset=utf-8","200","Indexable","Home",'
    '"Welcome","Main heading","540","0","https://x.test/","index,follow"\n'
    '"https://x.test/services/","text/html","200","Indexable","Services",'
    '"","Services","1200","1","https://x.test/services/",""\n'
    '"https://x.test/old/","text/html","404","Non-Indexable","","","","0","2","",""\n'
)


def test_sf_import_becomes_a_scoreless_run_with_readable_evidence(db):
    from clauditseo.importers import import_crawl
    conn, site = db
    out = import_crawl(conn, site, SF_CSV)
    assert out["pages"] == 3 and out["truncated"] is False

    run = conn.execute("SELECT status, composite_score FROM audit_runs"
                       " WHERE id=?", (out["run_id"],)).fetchone()
    assert run["status"] == "complete" and run["composite_score"] is None

    ev = runs.get_evidence(conn, out["run_id"])
    assert ev["source"] == "screamingfrog"
    assert ev["start_url"] == "https://x.test/"        # depth 0 wins
    home = next(p for p in ev["pages"] if p["url"] == "https://x.test/")
    assert home["word_count"] == 540 and home["click_depth"] == 0
    # Absent capture is absent-key, never present-and-empty: the local briefs
    # must see "not captured", not "checked and clean".
    assert "nap_mentions" not in home and "local_schema" not in home
    assert "robots_txt" not in ev


def test_sf_import_refuses_what_it_cannot_recognise(db):
    from clauditseo.importers import parse_screamingfrog_csv
    with pytest.raises(ValueError):
        parse_screamingfrog_csv("just,a,random\ncsv,file,here\n")


def test_crawl_diff_catches_removals_status_flips_and_rewrites(db):
    conn, site = db
    old = {"robots_status": 200, "robots_txt": "x", "llms_txt_status": 404,
           "sitemap_entry_total": 3, "pages": [
               {"url": "https://x.test/", "status": 200, "word_count": 1000},
               {"url": "https://x.test/gone/", "status": 200, "word_count": 300},
               {"url": "https://x.test/thin/", "status": 200, "word_count": 900}]}
    new = {**old, "pages": [
        {"url": "https://x.test/", "status": 404, "word_count": 1000},
        {"url": "https://x.test/thin/", "status": 200, "word_count": 200},
        {"url": "https://x.test/fresh/", "status": 200, "word_count": 100}]}
    _complete_run_with_evidence(conn, site, old)
    _complete_run_with_evidence(conn, site, new)

    diff = runs.crawl_diff(conn, site)
    assert diff["removed"] == ["https://x.test/gone/"]
    assert diff["added"] == ["https://x.test/fresh/"]
    assert diff["status_changed"] == [{"url": "https://x.test/",
                                       "before": 200, "after": 404}]
    assert diff["rewritten"] == [{"url": "https://x.test/thin/",
                                  "before": 900, "after": 200}]


def test_findings_export_is_a_checklist_worst_first(db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    client = TestClient(create_app(db_path=tmp_path / "export.db"))
    site_id = client.post("/api/clients", json={"name": "C"}).json()["id"]
    site = client.post(f"/api/clients/{site_id}/sites",
                       json={"domain": "x.test"}).json()["id"]
    text = client.get(f"/api/sites/{site}/export/findings.md").text
    assert text.startswith("# Open findings — x.test")
    assert "0 item(s)" in text


def test_notes_are_kept_with_the_site(db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    client = TestClient(create_app(db_path=tmp_path / "notes.db"))
    cid = client.post("/api/clients", json={"name": "C"}).json()["id"]
    site = client.post(f"/api/clients/{cid}/sites",
                       json={"domain": "x.test"}).json()["id"]
    client.post(f"/api/sites/{site}/notes",
                json={"note": "client says leave the pricing page alone"})
    detail = client.get(f"/api/sites/{site}").json()
    assert [n["body"] for n in detail["notes"]] == \
        ["client says leave the pricing page alone"]
    assert client.post(f"/api/sites/{site}/notes",
                       json={"note": "  "}).status_code == 422


def test_the_real_sf_export_parses_not_just_the_synthetic_one():
    """A genuine export from the user's own Screaming Frog, committed as a
    fixture. Header layouts drift across SF versions; this is the one that
    must never break."""
    from pathlib import Path

    from clauditseo.importers import parse_screamingfrog_csv
    text = Path(__file__).with_name("internal_all.csv").read_text(
        encoding="utf-8-sig", errors="replace")
    ev = parse_screamingfrog_csv(text)
    assert ev["stats"]["pages"] == 193
    assert ev["start_url"] == "https://www.acme.com.au/"
    home = ev["pages"][0]
    assert home["word_count"] == 2205 and home["click_depth"] == 0
    assert sum(1 for p in ev["pages"] if p["status"] == 301) == 6


# --- link suggestions and the page dossier -----------------------------------

def _page_rec(url, title, h1=None, outlinks=(), depth=1, words=400):
    return {"url": url, "status": 200, "content_type": "text/html",
            "title": title, "h1": h1 or title, "outlinks": list(outlinks),
            "click_depth": depth, "word_count": words}


def test_link_suggestions_target_underlinked_pages_with_real_anchors():
    from clauditseo.linksuggest import suggest_links
    home = "https://x.test/"
    ev = {"start_url": home, "pages": [
        _page_rec(home, "Roof Co", outlinks=[
            "https://x.test/roof-repairs/", "https://x.test/gutters/"], depth=0),
        _page_rec("https://x.test/roof-repairs/", "Roof Repairs Melbourne | Roof Co",
                  outlinks=[home, "https://x.test/gutters/"]),
        _page_rec("https://x.test/gutters/", "Gutter Cleaning | Roof Co",
                  outlinks=[home]),
        _page_rec("https://x.test/emergency-roof-repairs/",
                  "Emergency Roof Repairs After Storms",
                  outlinks=[home], depth=2),
    ]}
    ev["pages"][1]["outlinks"].append("https://x.test/emergency-roof-repairs/")

    got = {s["url"]: s for s in suggest_links(ev)}
    weak = got["https://x.test/emergency-roof-repairs/"]
    assert weak["inlinks"] == 1
    # The anchor is the page's own title, never an invented phrase.
    assert weak["anchor"] == "Emergency Roof Repairs After Storms"
    sources = [s["url"] for s in weak["sources"]]
    # The repairs page shares tokens but ALREADY links there — not suggested.
    assert "https://x.test/roof-repairs/" not in sources


def test_no_link_graph_means_no_suggestions_not_wrong_ones():
    """An imported crawl carries no outlinks; inventing inlink counts from
    nothing would make every page look orphaned."""
    from clauditseo.linksuggest import suggest_links
    ev = {"start_url": "https://x.test/", "pages": [
        {"url": "https://x.test/", "status": 200, "content_type": "text/html",
         "title": "Home", "click_depth": 0}]}
    assert suggest_links(ev) == []


def test_dossier_gathers_history_findings_and_briefs_for_one_url(db):
    conn, site = db
    url = "https://memory.test/services/"
    base = {"robots_status": 200, "robots_txt": "x", "llms_txt_status": 404,
            "sitemap_entry_total": 1, "pages": [
                {"url": url, "status": 200, "content_type": "text/html",
                 "title": "Services", "word_count": 900, "click_depth": 1}]}
    _complete_run_with_evidence(conn, site, base)
    run2 = _complete_run_with_evidence(conn, site, {**base, "pages": [
        {**base["pages"][0], "word_count": 300}]})

    runs.store_expert_report(
        conn, run2, "onpage-hygiene",
        {"model": "m", "report": "r", "tokens": 5,
         "findings": [{"severity": "high", "code": "title-length",
                       "summary": "Title too long", "affected_urls": [url]}]},
        page_url=url)
    runs.record_expert_findings(conn, run2, "onpage-hygiene", "m", [
        {"severity": "high", "code": "title-length", "summary": "Title too long",
         "affected_urls": [url]}])

    d = runs.page_dossier(conn, site, url)
    assert d["seen"] is True
    assert [h["word_count"] for h in d["history"]] == [300, 900]  # newest first
    assert d["findings"][0]["check_id"] == "title-length"
    assert d["findings"][0]["state"] == "candidate"       # seen once, honest
    assert d["page_briefs"][0]["tool_id"] == "onpage-hygiene"
    assert d["page_briefs"][0]["findings"] == 1


def test_dossier_quoting_does_not_match_a_prefix_url(db):
    """Asking about /page must not surface findings for /page-two."""
    conn, site = db
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, "t", {"model": "m", "report": "r",
                                                 "tokens": 1})
    runs.record_expert_findings(conn, run_id, "t", "m", [
        {"severity": "low", "code": "c", "summary": "s",
         "affected_urls": ["https://memory.test/page-two/"]}])
    d = runs.page_dossier(conn, site, "https://memory.test/page")
    assert d["findings"] == [] and d["seen"] is False


def test_sf_drop_folder_matches_by_filename_host_and_quarantines_the_rest(db, tmp_path):
    """One site's crawl landing on another's history is the failure mode
    worse than a file left unprocessed — so matching is by filename host,
    never guessed from contents, and failures are quarantined with a reason."""
    from clauditseo.importers import collect_drop_folder
    conn, site = db          # site domain is memory.test

    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "memory.test.csv").write_text(SF_CSV, encoding="utf-8")
    (drop / "unknown-site.com.csv").write_text(SF_CSV, encoding="utf-8")
    (drop / "memory.test.txt").write_text("ignored", encoding="utf-8")

    outcomes = {o["file"]: o for o in collect_drop_folder(conn, drop)}
    assert outcomes["memory.test.csv"]["status"] == "imported"
    assert outcomes["memory.test.csv"]["pages"] == 3
    assert outcomes["unknown-site.com.csv"]["status"] == "failed"
    assert "no site matches" in outcomes["unknown-site.com.csv"]["reason"]

    assert (drop / "done" / "memory.test.csv").exists()
    assert (drop / "failed" / "unknown-site.com.csv").exists()
    assert "no site matches" in (drop / "failed" / "unknown-site.com.reason"
                                 ).read_text(encoding="utf-8")
    assert (drop / "memory.test.txt").exists()      # non-CSV left alone

    # The import is a real run this site's briefs can read.
    run = conn.execute("SELECT id FROM audit_runs WHERE site_id=?"
                       " AND status='complete'", (site,)).fetchone()
    assert runs.get_evidence(conn, run["id"])["source"] == "screamingfrog"


def test_sf_drop_folder_matches_www_variants(db, tmp_path):
    from clauditseo.importers import collect_drop_folder
    conn, site = db
    with conn:
        conn.execute("UPDATE sites SET domain='https://www.memory.test/'"
                     " WHERE id=?", (site,))
    drop = tmp_path / "drop2"
    drop.mkdir()
    (drop / "memory.test.csv").write_text(SF_CSV, encoding="utf-8")
    out = collect_drop_folder(conn, drop)
    assert out[0]["status"] == "imported"


def test_biggest_gains_is_the_scoreboards_own_arithmetic():
    """No model, no tokens: the deduction table the engine already records,
    weighted onto the composite and sorted. Inapplicable dimensions and
    clean checks contribute nothing."""
    subscores = {
        "ONP": {"weight": 0.22, "applicable": True, "detail": {"per_check": {
            "img-alt-missing": {"affected": 99, "eligible": 99, "deduction": 12.0},
            "title-length": {"affected": 39, "eligible": 99, "deduction": 1.97},
            "clean-check": {"affected": 0, "eligible": 99, "deduction": 0}}}},
        "CNT": {"weight": 0.16, "applicable": True, "detail": {"per_check": {
            "duplicate-content": {"affected": 52, "eligible": 99, "deduction": 6.3}}}},
        "LOC": {"weight": 0.06, "applicable": False, "detail": {"per_check": {
            "nap-missing": {"affected": 1, "eligible": 1, "deduction": 50.0}}}},
    }
    gains = runs.biggest_gains(subscores)
    assert [g["check_id"] for g in gains] == \
        ["img-alt-missing", "duplicate-content", "title-length"]
    assert gains[0]["composite_points"] == 2.64      # 12.0 x 0.22
    assert gains[1]["composite_points"] == 1.01      # 6.3 x 0.16
    assert all(g["check_id"] != "nap-missing" for g in gains), \
        "an inapplicable dimension cannot offer gains"
    assert runs.biggest_gains({}) == []


def test_a_dimension_weighted_zero_offers_no_composite_gain():
    """`applicable` was the only exclusion, and it is not the only one.

    A11Y is applicable and carries weight 0.0 (`engine/scoring.py:41`), so
    every accessibility deduction was multiplied by zero, kept, and ranked —
    reaching the client document as "up to 0.0 points on the composite".
    Inapplicable and unweighted are different states and both contribute
    nothing; the arithmetic only excluded the first.
    """
    subscores = {
        "ONP": {"weight": 0.27, "applicable": True, "detail": {"per_check": {
            "img-alt-missing": {"affected": 99, "eligible": 99,
                                "deduction": 12.0}}}},
        "A11Y": {"weight": 0.0, "applicable": True, "detail": {"per_check": {
            "link-name-missing": {"affected": 41, "eligible": 41,
                                  "deduction": 34.6}}}},
    }
    gains = runs.biggest_gains(subscores)
    assert [g["check_id"] for g in gains] == ["img-alt-missing"],         "a deduction worth zero on the composite is not a gain"
    assert all(g["composite_points"] > 0 for g in gains)


# --- triage ------------------------------------------------------------------
def test_triage_refuses_a_run_that_does_not_exist(db, tmp_path, monkeypatch):
    """Renamed from `test_triage_data_excludes_accepted_risk_and_its_own_tool`,
    which is not what it asserts and never was.

    It builds a client and a site, then checks a 404 on a run id that does not
    exist; `_triage_data` is never called, so neither half of the old name was
    exercised by a single line of it. The two properties the old name claimed
    are now asserted for real, through `_triage_data`, by
    `test_a_withdrawn_finding_is_not_handed_to_the_dispatcher_as_memory`.

    Kept rather than deleted: the refusal is a real property — triaging a run
    that does not exist would triage air — and it is asserted here honestly.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    client = TestClient(create_app(db_path=tmp_path / "triage.db"))
    cid = client.post("/api/clients", json={"name": "C"}).json()["id"]
    site = client.post(f"/api/clients/{cid}/sites",
                       json={"domain": "x.test"}).json()["id"]
    # No completed run: the endpoint refuses honestly rather than triaging air.
    fake = client.post(f"/api/runs/nope/expert/triage", json={})
    assert fake.status_code == 404


# --- the state vocabulary and who is allowed to see it -----------------------
#
# `withdrawn` was the sixth value of an enum that had five when the dispatcher's
# memory filter was written, and the filter is negative — `!= "accepted-risk"` —
# so it admitted the new value silently. `runs.py`'s own docstring records the
# same thing happening to `accepted-risk` one value earlier: "Its vocabulary has
# five values, so a negative filter admitted `accepted-risk`."
#
# The vocabulary lived only in the schema's CHECK constraint, so every consumer
# re-derived it and each one that re-derived it negatively admitted the next
# value added. These two guards are the pair: one asserts the owner still spans
# what the database enforces, the other asserts the filter behaves.


def _states_the_schema_allows(conn) -> set[str]:
    """The vocabulary as the database enforces it, read from the CHECK
    constraint rather than from any list in Python.

    Read from `sqlite_master` and not from the migration file on purpose: a
    later migration that rebuilds the table is what the product runs against,
    and a guard reading the 0023 text would keep passing after 0031 narrowed
    it. This is the evidence that can disagree.
    """
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table'"
        " AND name='finding_states'").fetchone()["sql"]
    clause = sql.split("CHECK (state IN (", 1)[1].split("))", 1)[0]
    return set(re.findall(r"'([^']+)'", clause))


def test_every_state_the_schema_allows_is_classified_for_the_model(db):
    """A seventh state cannot be added without deciding whether the dispatcher
    may see it.

    This is the guard the negative filter never had. It does not test that the
    current classification is right — that is the test below — it tests that
    the classification is *total*, so the next value added to the CHECK
    constraint fails here rather than arriving in a model's memory unnoticed.
    """
    conn, _ = db
    allowed = _states_the_schema_allows(conn)

    assert set(runs.ALL_STATES) == allowed, (
        "the owner in runs.py and the schema's CHECK constraint disagree; "
        f"schema has {sorted(allowed)}, runs.ALL_STATES has "
        f"{sorted(runs.ALL_STATES)}")

    live = set(runs.LIVE_STATES)
    blind = set(runs.MODEL_BLIND_STATES)
    assert live | blind == allowed, (
        f"unclassified state(s): {sorted(allowed - (live | blind))} — every "
        "value the schema allows must be either live memory or withheld")
    assert not (live & blind), f"state in both halves: {sorted(live & blind)}"


def test_a_withdrawn_finding_is_not_handed_to_the_dispatcher_as_memory(db):
    """WF-67. `withdrawn` means the finding was never true — the audit that
    raised it could not see the site. Handing one to the triage model as
    memory is the fabricated finding propagating through the state invented
    to stop it propagating.

    Driven through `_triage_data` rather than through a hand-built context.
    The two tests that already named this property both stopped short of it:
    one asserted a 404 on a run that does not exist, the other built `memory`
    as its own dict — so the filter has never been exercised by anything.
    """
    from clauditseo.api.app import _triage_data
    from clauditseo.config import settings

    conn, site = db
    _run_tool(conn, site, "local-signals", {"nap-missing"})
    _run_tool(conn, site, "local-signals", {"nap-missing"})          # -> open
    run_id = _run_tool(conn, site, "crawl", {"robots-missing",
                                                    "not-https"})
    _run_tool(conn, site, "crawl", {"robots-missing", "not-https"})
    runs.set_state(conn, site, fp("crawl", "robots-missing"), "withdrawn")
    runs.set_state(conn, site, fp("crawl", "not-https"), "accepted-risk")

    run = dict(runs.get_run(conn, run_id))
    site_row = repo.get_site(conn, site)
    data = _triage_data(conn, run, site_row, settings(), {"pages": []})

    seen = {(m["check_id"], m["state"]) for m in data["memory"]}
    assert ("nap-missing", "open") in seen, (
        "an open finding is what the dispatcher is for; it must still arrive")
    assert not [s for s in seen if s[1] == "withdrawn"], (
        f"a withdrawn finding reached the model as memory: {sorted(seen)}")
    assert not [s for s in seen if s[1] == "accepted-risk"], (
        f"an accepted-risk finding reached the model as memory: {sorted(seen)}")

    # The other half of the name the hollow guard carried: triage never offers
    # itself as a brief to buy.
    assert "triage" not in {b["tool"] for b in data["available_briefs"]}
