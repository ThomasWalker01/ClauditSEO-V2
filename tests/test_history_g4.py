"""Gate G4: fingerprint lifecycle and trend history.

Scripted sequence run(defect) → run(fixed) → run(defect again) must yield
open → fixed → regressed for the same fingerprint, and the composite trend
series must have three points. Also covers run comparison by fingerprint.
"""

from __future__ import annotations

import json

import clauditseo.modules  # noqa: F401
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier, fingerprint
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite

FAST = TierBudget(max_pages=20, request_timeout_s=5, wall_clock_s=30, delay_s=0)
DIMS = ["TEC", "ONP"]

GOOD_PROMO = ("<html><head><title>Promo Page With A Fine Title</title>"
              '<meta name="description" content="A perfectly reasonable promo page.">'
              '<meta name="viewport" content="width=device-width">'
              '<link rel="canonical" href="/promo"></head>'
              "<body><h1>Promo</h1></body></html>")
BROKEN_PROMO = ("<html><head>"
                '<meta name="description" content="A perfectly reasonable promo page.">'
                '<meta name="viewport" content="width=device-width">'
                '<link rel="canonical" href="/promo"></head>'
                "<body><h1>Promo</h1></body></html>")  # <-- no <title>


def _routes(promo_html: str) -> dict:
    home = ("<html><head><title>History Fixture Home Page</title>"
            '<meta name="description" content="Home of the history fixture.">'
            '<meta name="viewport" content="width=device-width">'
            '<link rel="canonical" href="/"></head>'
            '<body><h1>Home</h1><a href="/promo">promo</a></body></html>')
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/": (200, {}, home),
        "/promo": (200, {}, promo_html),
    }


def _do_run(conn, site_id: str, promo_html: str) -> str:
    server = FixtureSite(_routes(promo_html)).start()
    try:
        crawl_result = crawl(server.base_url + "/", Tier.T2, budget=FAST)
        result = run_audit(Site(domain="history.fixture"), crawl_result, DIMS, Tier.T2)
        run_id = runs.create_run(conn, site_id, DIMS, "T2")
        runs.complete_run(conn, run_id, result)
        return run_id
    finally:
        server.stop()


def _state(conn, site_id: str, fp: str) -> str | None:
    row = conn.execute(
        "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
        (site_id, fp)).fetchone()
    return row["state"] if row else None


def test_open_fixed_regressed_lifecycle_and_trend(tmp_path):
    conn = connect(tmp_path / "g4.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "History Co")
    site_id = repo.create_site(conn, client, "history.fixture")
    fp = fingerprint("ONP", "title-missing", "/promo")

    run1 = _do_run(conn, site_id, BROKEN_PROMO)
    assert _state(conn, site_id, fp) == "open"

    run2 = _do_run(conn, site_id, GOOD_PROMO)
    assert _state(conn, site_id, fp) == "fixed"

    run3 = _do_run(conn, site_id, BROKEN_PROMO)
    assert _state(conn, site_id, fp) == "regressed"

    trend = runs.site_trend(conn, site_id)
    assert len(trend) == 3
    assert trend[1]["value"] > trend[0]["value"], "fixed run should score higher"
    assert trend[2]["value"] < trend[1]["value"], "regressed run should score lower"

    diff = runs.compare_runs(conn, run2, run3)
    assert fp in {f["fingerprint"] for f in diff["new"]}
    diff_back = runs.compare_runs(conn, run1, run2)
    assert fp in {f["fingerprint"] for f in diff_back["resolved"]}

    regressed = [s for s in runs.site_states(conn, site_id) if s["state"] == "regressed"]
    assert [s["check_id"] for s in regressed] == ["title-missing"]
    assert regressed[0]["changed_by_run"] == run3
    conn.close()


def test_accepted_risk_is_never_auto_changed(tmp_path):
    conn = connect(tmp_path / "g4b.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Risk Co")
    site_id = repo.create_site(conn, client, "history.fixture")
    fp = fingerprint("ONP", "title-missing", "/promo")

    _do_run(conn, site_id, BROKEN_PROMO)
    runs.set_state(conn, site_id, fp, "accepted-risk")
    _do_run(conn, site_id, GOOD_PROMO)     # absence must not flip accepted-risk to fixed
    assert _state(conn, site_id, fp) == "accepted-risk"
    _do_run(conn, site_id, BROKEN_PROMO)   # reappearance must not flip it either
    assert _state(conn, site_id, fp) == "accepted-risk"
    conn.close()


# --- withdrawn: the finding was never true ---------------------------------
#
# The sibling of the accepted-risk test above, and the opposite claim.
# `accepted-risk` says the condition is there and will be tolerated, so nothing
# may move it. `withdrawn` says the condition was never there, so absence must
# not read as a repair — but a later run that actually SEES it must reopen it,
# or the state is a mute button rather than a retraction.


def test_withdrawn_is_not_cleared_by_absence(tmp_path):
    conn = connect(tmp_path / "g4w1.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Withdrawn Co")
    site_id = repo.create_site(conn, client, "history.fixture")
    fp = fingerprint("ONP", "title-missing", "/promo")

    _do_run(conn, site_id, BROKEN_PROMO)
    runs.set_state(conn, site_id, fp, "withdrawn")
    _do_run(conn, site_id, GOOD_PROMO)     # absent, but nothing was ever fixed
    assert _state(conn, site_id, fp) == "withdrawn"
    conn.close()


def test_a_later_run_that_sees_it_reopens_a_withdrawn_finding(tmp_path):
    conn = connect(tmp_path / "g4w2.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Withdrawn Co")
    site_id = repo.create_site(conn, client, "history.fixture")
    fp = fingerprint("ONP", "title-missing", "/promo")

    _do_run(conn, site_id, BROKEN_PROMO)
    runs.set_state(conn, site_id, fp, "withdrawn")
    run3 = _do_run(conn, site_id, BROKEN_PROMO)
    # `open`, not `regressed`: a regression asserts a fix and a relapse, and
    # a withdrawal is neither.
    assert _state(conn, site_id, fp) == "open"
    row = conn.execute("SELECT changed_by_run FROM finding_states"
                       " WHERE site_id=? AND fingerprint=?",
                       (site_id, fp)).fetchone()
    assert row["changed_by_run"] == run3
    conn.close()


def test_withdrawn_is_reported_and_is_not_outstanding(tmp_path):
    conn = connect(tmp_path / "g4w3.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Withdrawn Co")
    site_id = repo.create_site(conn, client, "history.fixture")
    fp = fingerprint("ONP", "title-missing", "/promo")

    _do_run(conn, site_id, BROKEN_PROMO)
    before = runs.current_state(conn, site_id)
    runs.set_state(conn, site_id, fp, "withdrawn")
    after = runs.current_state(conn, site_id)

    assert after["outstanding"] == before["outstanding"] - 1
    # Reported rather than merely subtracted — the same reason candidate and
    # accepted-risk are returned: a total that silently drops a state is a
    # total nobody can reconcile.
    assert after["withdrawn"] == 1
    conn.close()


# --- the sitemap watch must not invent a regression ------------------------

def _run_with_sitemaps(conn, site_id, sitemaps, started_at):
    """A completed run carrying only the sitemap evidence the watch reads."""
    import json as _json
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    total = sum(s.get("entry_count") or 0 for s in sitemaps if not s.get("is_index"))
    with conn:
        conn.execute(
            "UPDATE audit_runs SET status='complete', started_at=?,"
            " crawl_evidence=? WHERE id=?",
            (started_at, _json.dumps({"sitemaps": sitemaps,
                                      "sitemap_entry_total": total,
                                      "robots_status": 200}), run_id))
    return run_id


def test_an_unread_sitemap_is_not_a_site_regression(tmp_path):
    """The defect: a sitemap total is a SUM, and a sitemap that failed to
    fetch contributes zero silently. One ReadTimeout on one of two sitemaps
    looked identical to the site deleting half its URLs, and was reported at
    HIGH as "regression requires urgent diagnosis". Seen in real data: a run
    reported 108 declared entries when the true answer was "we could not read
    one of the two sitemaps"."""
    conn = connect(tmp_path / "watch.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    ok = [{"url": "https://x.test/page-sitemap.xml", "status": 200,
           "entry_count": 108, "is_index": False},
          {"url": "https://x.test/post-sitemap.xml", "status": 200,
           "entry_count": 160, "is_index": False}]
    timed_out = [dict(ok[0]),
                 {"url": "https://x.test/post-sitemap.xml", "status": None,
                  "entry_count": 0, "is_index": False,
                  "error": "ReadTimeout: the read operation timed out"}]

    _run_with_sitemaps(conn, site, ok, "2026-08-01T00:00:00")
    _run_with_sitemaps(conn, site, timed_out, "2026-08-02T00:00:00")

    alerts = runs.watch_changes(conn, site)
    drift = [a for a in alerts if a["what"] == "sitemap declared entries"]
    assert not drift, "a failed fetch was reported as the site losing URLs"
    unread = [a for a in alerts if a["what"] == "sitemap not fully read"]
    assert unread, "the failed fetch should still be reported, just not as a regression"
    assert unread[0]["severity"] == "medium"
    assert "not comparable" in unread[0]["note"]


def test_a_genuine_drift_names_the_sitemap_that_moved(tmp_path):
    """A total is not actionable. "268 to 117" sends someone to diagnose a
    site-wide deletion; "post-sitemap 160 to 32" points at one generator."""
    conn = connect(tmp_path / "drift.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    before = [{"url": "https://x.test/page-sitemap.xml", "status": 200,
               "entry_count": 108, "is_index": False},
              {"url": "https://x.test/post-sitemap.xml", "status": 200,
               "entry_count": 160, "is_index": False}]
    after = [{"url": "https://x.test/page-sitemap.xml", "status": 200,
              "entry_count": 85, "is_index": False},
             {"url": "https://x.test/post-sitemap.xml", "status": 200,
              "entry_count": 32, "is_index": False}]

    _run_with_sitemaps(conn, site, before, "2026-08-01T00:00:00")
    _run_with_sitemaps(conn, site, after, "2026-08-02T00:00:00")

    drift = next(a for a in runs.watch_changes(conn, site)
                 if a["what"] == "sitemap declared entries")
    assert (drift["before"], drift["after"]) == (268, 117)
    assert "post-sitemap.xml 160" in drift["note"]
    assert "read every sitemap successfully" in drift["note"]


def test_a_page_that_was_never_crawled_is_not_declared_fixed(tmp_path):
    """The rule was "its dimension ran and it did not reappear". That is only
    true if the page was looked at. A 20-page nav crawl of a 100-page site
    marked 456 findings on the 80 pages it never fetched as fixed — and each
    would have returned as a REGRESSION on the next full crawl, so one error
    became a false clearance and then a false alarm.
    """
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier

    conn = connect(tmp_path / "scope.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    def finding(path):
        return Finding(dimension="ONP", check_id="img-alt-missing",
                       severity=Severity.MEDIUM, summary=f"alt missing on {path}",
                       subject=path, affected_urls=[f"https://x.test{path}"],
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    def store(findings, crawled):
        run_id = runs.create_run(conn, site, ["ONP"], "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=["ONP"],
            findings=findings, crawled_paths=set(crawled)))
        return run_id

    def state(path):
        fp = finding(path).fingerprint
        row = conn.execute(
            "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
            (site, fp)).fetchone()
        return row["state"] if row else None

    # A full crawl finds a problem on two pages.
    store([finding("/a"), finding("/b")], ["/a", "/b"])
    assert state("/a") == state("/b") == "open"

    # A narrow crawl visits only /a, and /a is genuinely fixed.
    store([], ["/a"])
    assert state("/a") == "fixed", "a page that was revisited and came back clean"
    assert state("/b") == "open", "a page that was never fetched is not evidence"

    # A crawl that fetched nothing at all changes nothing at all. The guard
    # above used to read `pages and crawled and not (pages & crawled)`, so an
    # empty crawl made it falsy and cleared what a narrow crawl correctly
    # spared — the same error as the 456-finding case, at its worst input.
    store([], [])
    assert state("/b") == "open", "nothing was fetched, so nothing was verified"
    assert state("/a") == "fixed", "and nothing already settled is disturbed"


def test_a_crawl_that_fetched_nothing_clears_nothing(tmp_path):
    """A blanket `Disallow: /`, a 5xx on robots.txt or an unreachable host all
    produce a run with zero crawled paths. Every open page-scoped finding was
    marked fixed by it, and would have come back as a regression on the next
    real audit — a false clearance and a false alarm, written into stored
    state rather than shown on a screen, from a run that measured nothing."""
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier

    conn = connect(tmp_path / "blocked.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    def finding(path):
        return Finding(dimension="ONP", check_id="img-alt-missing",
                       severity=Severity.MEDIUM, summary=f"alt missing on {path}",
                       subject=path, affected_urls=[f"https://x.test{path}"],
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    def store(findings, crawled):
        run_id = runs.create_run(conn, site, ["ONP"], "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=["ONP"],
            findings=findings, crawled_paths=set(crawled)))

    def state(path):
        row = conn.execute(
            "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
            (site, finding(path).fingerprint)).fetchone()
        return row["state"] if row else None

    store([finding("/a"), finding("/b")], ["/a", "/b"])
    assert state("/a") == state("/b") == "open"

    store([], [])
    assert state("/a") == state("/b") == "open", \
        "a run that fetched no page is not evidence that anything was fixed"


def test_a_site_scoped_finding_still_clears_without_a_page(tmp_path):
    """The page rule must not defang the ordinary case: a finding that names
    no page — robots missing, no HTTPS — is cleared by its dimension running.
    """
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier

    conn = connect(tmp_path / "sitewide.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    robots = Finding(dimension="TEC", check_id="robots-missing",
                     severity=Severity.MEDIUM, summary="no robots.txt",
                     subject="site", affected_urls=["https://x.test/"],
                     evidence={}, confidence=Confidence.HIGH, recommendation="")

    def store(findings, crawled):
        run_id = runs.create_run(conn, site, ["TEC"], "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=["TEC"],
            findings=findings, crawled_paths=set(crawled)))

    store([robots], ["/"])
    store([], ["/"])
    row = conn.execute(
        "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
        (site, robots.fingerprint)).fetchone()
    assert row["state"] == "fixed"


def test_the_repair_reopens_only_what_was_never_looked_at(tmp_path):
    """`scripts/repair_unlooked_fixes.py` undoes the damage the guard above
    now prevents — the rows already sitting at `fixed` when it shipped.

    It has to read the same rule from the other side. The guard asks "may I
    clear this?" against the crawl in hand; the repair asks "should this ever
    have been cleared?" against the crawl stored on the run that cleared it.
    If the two ever disagree the repair either misses damage or reopens a
    real fix, so this pins them to the same answer on the same three cases:
    a page that was fetched, a page that was not, and a finding that names no
    page at all.
    """
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.repair_unlooked_fixes import unlooked

    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier

    conn = connect(tmp_path / "repair.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    def finding(path, urls=None):
        return Finding(dimension="ONP", check_id="img-alt-missing",
                       severity=Severity.MEDIUM, summary=f"alt missing on {path}",
                       subject=path,
                       affected_urls=[f"https://x.test{path}"] if urls is None
                       else urls,
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    def store(findings, crawled):
        run_id = runs.create_run(conn, site, ["ONP"], "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=["ONP"],
            findings=findings, crawled_paths=set(crawled)))
        # The repair reads the run's stored evidence, not the result object,
        # because by the time it runs the result is long gone.
        runs.store_evidence(conn, run_id, {
            "pages": [{"url": f"https://x.test{p}"} for p in crawled]})
        return run_id

    site_wide = Finding(dimension="ONP", check_id="no-canonical-policy",
                        severity=Severity.LOW, summary="site-wide",
                        subject="site", affected_urls=[], evidence={},
                        confidence=Confidence.HIGH, recommendation="")

    store([finding("/a"), finding("/b"), site_wide], ["/a", "/b"])
    # A narrow crawl of /a only. The guard clears /a and the site-wide one;
    # /b is left open because nothing looked at it.
    narrow = store([], ["/a"])

    def state(fp):
        row = conn.execute(
            "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
            (site, fp)).fetchone()
        return row["state"] if row else None

    assert state(finding("/a").fingerprint) == "fixed"
    assert state(site_wide.fingerprint) == "fixed"
    assert state(finding("/b").fingerprint) == "open"

    # With the guard in place there is nothing to repair.
    assert unlooked(conn, site) == []

    # Now reproduce the damage the guard used to allow: /b cleared by a run
    # that never fetched it. The id comes from `store`, not from a query
    # ordered by `started_at` — both runs are created inside the same second
    # and the tie picked the wrong one, which quietly made this assert about
    # a run that had fetched /b after all.
    conn.execute("UPDATE finding_states SET state='fixed', changed_by_run=?"
                 " WHERE site_id=? AND fingerprint=?",
                 (narrow, site, finding("/b").fingerprint))
    conn.commit()

    found = unlooked(conn, site)
    assert [r["fingerprint"] for r in found] == [finding("/b").fingerprint], (
        "only the page that was never fetched: a re-read page's fix is real, "
        "and a site-scoped finding names no page to re-read")
    assert json.loads(found[0]["affected_urls"]) == ["https://x.test/b"]


def test_a_comparison_does_not_resolve_what_the_later_run_never_looked_at(tmp_path):
    """`compare_runs` was a bare fingerprint set-difference.

    `resolved = a.keys() - b.keys()` says "absent from the later run" and
    treats that as "fixed". A narrower crawl makes almost everything absent,
    so the comparison reports the whole difference as resolutions — on stored
    data, 352 of them, of which 347 sat on pages the later run never fetched
    and were recorded `open` in this product's own `finding_states` table.
    That table already applies the rule: `_apply_states` refuses to clear a
    page-scoped finding from a crawl that did not visit it, which is the fix
    round 006 landed and round 010 fenced.

    The comparison is the surface the whole product exists for — prove at the
    next run that the fix landed — and its number reaches a client document
    at `confidence: high`.
    """
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier

    conn = connect(tmp_path / "cmp.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    def finding(path):
        return Finding(dimension="ONP", check_id="img-alt-missing",
                       severity=Severity.MEDIUM, summary=f"alt missing on {path}",
                       subject=path, affected_urls=[f"https://x.test{path}"],
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    def store(findings, crawled):
        run_id = runs.create_run(conn, site, ["ONP"], "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=["ONP"],
            findings=findings, crawled_paths=set(crawled)))
        return run_id

    baseline = store([finding("/a"), finding("/b")], ["/a", "/b"])
    # The later run fetches only /a, and /a is genuinely fixed. /b is absent
    # because it was never looked at.
    current = store([], ["/a"])

    diff = runs.compare_runs(conn, baseline, current)
    resolved = {f["fingerprint"] for f in diff["resolved"]}
    not_rechecked = {f["fingerprint"] for f in diff.get("not_rechecked", [])}
    fp_a, fp_b = finding("/a").fingerprint, finding("/b").fingerprint

    assert resolved == {fp_a}, (
        "only the finding on the page the later run actually fetched was "
        f"re-checked; got {len(resolved)} resolved")
    assert not_rechecked == {fp_b}, (
        "a finding on a page the later run never visited must be reported as "
        f"not re-checked rather than resolved; got {len(not_rechecked)}")
    conn.close()


# --- a comparison must ask what run B looked at ----------------------------

def _compare_fixture(tmp_path, name):
    """Baseline crawls /a and /b; run B crawls /a only, and /a is fixed."""
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Confidence, Finding, Severity, Site, Tier

    conn = connect(tmp_path / name)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    def finding(path):
        return Finding(dimension="ONP", check_id="img-alt-missing",
                       severity=Severity.MEDIUM, summary=f"alt missing on {path}",
                       subject=path, affected_urls=[f"https://x.test{path}"],
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    def store(findings, crawled):
        run_id = runs.create_run(conn, site, ["ONP"], "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=["ONP"],
            findings=findings, crawled_paths=set(crawled)))
        return run_id

    baseline = store([finding("/a"), finding("/b")], ["/a", "/b"])
    current = store([], ["/a"])
    return conn, site, store, finding, baseline, current


def test_a_later_run_does_not_change_an_earlier_comparison(tmp_path):
    """A comparison of (A, B) must depend only on A and B.

    Reading `finding_states` broke that: it holds one row per site and
    fingerprint describing the state *now*, so a third audit that clears /b
    made the stored comparison of baseline against B claim B fixed it — and B
    never fetched /b, which is the round-022 Critical's exact claim.
    """
    conn, site, store, finding, baseline, current = _compare_fixture(tmp_path, "later.db")
    fp_b = finding("/b").fingerprint

    before = {f["fingerprint"] for f in runs.compare_runs(conn, baseline, current)["resolved"]}
    store([], ["/b"])          # a third run re-crawls /b and clears it
    after = {f["fingerprint"] for f in runs.compare_runs(conn, baseline, current)["resolved"]}

    assert before == after, (
        f"a third run changed an earlier pair's answer; {sorted(before)} -> {sorted(after)}")
    assert fp_b not in after, "run B never fetched /b, so it cannot have resolved it"
    conn.close()


# `test_a_finding_the_operator_accepted_is_not_a_resolution` stood here. It
# asserted that `accepted-risk` — the operator saying explicitly that this one
# will not be fixed — is not counted as a resolution, which was a real defect:
# the predicate was a negative filter over a five-value vocabulary, and the
# miscount reached a document sent to the client paying for the fix.
#
# Round 023 then removed the `finding_states` read altogether, because that
# table describes the state *now* and let a later run change an earlier pair's
# answer. That took the test's subject with it: `set_state` cannot move a value
# the code never reads, and `/b` reached `not_rechecked` on the path rule
# whatever state it held. Deleting the `set_state` call left it green.
#
# Replaced rather than deleted. The property that survives is stronger and is
# the one round 023 actually established — a comparison of (A, B) depends on A
# and B alone — and it is asserted by
# `test_a_comparison_does_not_consult_the_lifecycle_table` below, which moves
# every state in the vocabulary and requires the answer not to move. That one
# fails the day anything reads the table again; this one could not.


def test_a_run_with_no_recorded_scope_resolves_nothing(tmp_path):
    """Rows predating the scope column, and any caller that stored none.

    Unknown scope is not evidence of a re-check. The conservative direction
    is the honest one here: the whole defect was reading absence as proof.
    """
    conn, site, store, finding, baseline, current = _compare_fixture(tmp_path, "noscope.db")
    with conn:
        conn.execute("UPDATE audit_runs SET crawled_paths=NULL WHERE id=?", (current,))

    diff = runs.compare_runs(conn, baseline, current)
    assert not diff["resolved"], (
        "a run whose scope was never recorded cannot have re-checked anything; "
        f"got {len(diff['resolved'])} resolved")
    assert len(diff["not_rechecked"]) == 2
    conn.close()


# --- one order of questions, asked of every finding -------------------------
#
# Each of these builds its own fixture rather than sharing one. The three
# tests above share `_compare_fixture`, in which run B never fetched `/b`, so
# `/b` reaches `not_rechecked` on the path rule alone and the two tests about
# `finding_states` pass whether or not their subject is consulted. Round 025's
# CQ-03 measured that: removing the `set_state` call from
# `test_a_finding_the_operator_accepted_is_not_a_resolution` leaves it green.
# A fixture that can only fail one way cannot guard four rules.

def _pair(tmp_path, name, *, domain="https://x.test/"):
    """A site and a `store(findings, crawled, dims, stats)` helper for it."""
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Site, Tier

    conn = connect(tmp_path / name)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, domain)

    def store(findings, crawled, dims=("ONP",), stats=None):
        run_id = runs.create_run(conn, site, list(dims), "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain=domain), tier=Tier.T2, dimensions=list(dims),
            findings=findings, crawled_paths=set(crawled), stats=stats or {}))
        return run_id

    return conn, site, store


def _f(dimension, check_id, path):
    from clauditseo.engine.types import Confidence, Finding, Severity
    return Finding(dimension=dimension, check_id=check_id,
                   severity=Severity.MEDIUM,
                   summary=f"{check_id} on {path or 'site'}",
                   subject=path or "site",
                   affected_urls=[f"https://x.test{path}"] if path else [],
                   evidence={}, confidence=Confidence.HIGH, recommendation="")


def test_a_dimension_the_later_run_never_audited_is_not_resolved(tmp_path):
    """The page rule and the dimension rule are both required, not either.

    `why_not` applied the dimension test only to site-level findings. A
    page-scoped finding took the `paths & crawled` branch with no dimension
    test, so a finding whose dimension run B never ran came back **resolved**
    the moment B refetched its page — the ordinary case, not a narrow one.
    `_apply_states` has always refused exactly this (`dimension not in dims`),
    so the two rules the correction set out to unify disagreed in the opposite
    direction to before.

    Observed on live data before the fix: `/api/compare` returned eight
    resolutions for a run whose dimension list held no A11Y, four of them
    A11Y findings, rendered green at `confidence: high`.
    """
    conn, site, store = _pair(tmp_path, "dim.db")
    onp = _f("ONP", "img-alt-missing", "/a")
    tec = _f("TEC", "canonical-missing", "/a")

    baseline = store([onp, tec], ["/a"], dims=("ONP", "TEC"))
    current = store([], ["/a"], dims=("ONP",))     # refetched /a, audited ONP only

    diff = runs.compare_runs(conn, baseline, current)
    resolved = {f["fingerprint"] for f in diff["resolved"]}
    not_rechecked = {f["fingerprint"]: f["not_rechecked_reason"]
                     for f in diff["not_rechecked"]}

    assert resolved == {onp.fingerprint}, (
        "only the finding whose dimension run B actually audited was "
        f"re-checked; got {len(resolved)} resolved")
    assert tec.fingerprint in not_rechecked, (
        "a finding whose dimension run B never ran cannot have been resolved "
        "by it")
    assert "TEC" in not_rechecked[tec.fingerprint]["lead"], (
        f"the reason must name the dimension; got "
        f"{not_rechecked[tec.fingerprint]!r}")
    conn.close()


def test_a_blocked_run_resolves_nothing(tmp_path):
    """A run whose crawl was refused fetched no page and cleared no finding.

    `complete_run` writes `json.dumps([])` for a blocked run, and `"[]"` is a
    truthy string, so `_run_scope` returned an empty set — "fetched nothing" —
    rather than a signal to stop. `why_not` then fell to the site-level branch
    and asked only whether the dimension ran, which for a blocked run it did.
    `_apply_states` returns before clearing anything on a blocked run; this is
    the same rule, asked in the same place.

    Cohort entry `/api/compare has no blocked-run guard`, open 11 rounds and
    recorded retired by `90bf442` against code that did not close it.
    """
    conn, site, store = _pair(tmp_path, "blocked.db")
    nap = _f("LOC", "nap-missing", None)          # site-level: names no page
    alt = _f("ONP", "img-alt-missing", "/a")

    baseline = store([nap, alt], ["/a"], dims=("LOC", "ONP"))
    current = store([], [], dims=("LOC", "ONP"), stats={"pages_eligible": 0})

    assert runs.get_run(conn, current)["status"] == "blocked", "fixture precondition"

    diff = runs.compare_runs(conn, baseline, current)
    assert not diff["resolved"], (
        "a run that fetched nothing resolved something; "
        f"{[f['check_id'] for f in diff['resolved']]}")
    assert len(diff["not_rechecked"]) == 2
    reasons = [f["not_rechecked_reason"]["lead"] for f in diff["not_rechecked"]]
    assert all("crawl" in r or "blocked" in r for r in reasons), (
        f"the reason must say the crawl was refused; got {reasons}")
    conn.close()


def test_a_pair_from_two_different_sites_is_refused(tmp_path):
    """Comparing across sites diffs one client's findings against another's.

    Nothing compared `site_id` — not the route, not `compare_runs`, not
    `generate()`, which takes `run_dicts[0]["site_id"]` for the document's
    heading. So a comparison deliverable spanning two clients is generable and
    is headed with the first one's domain. Round 024 drove such a pair and
    round 025 measured the live API returning eight resolutions across two.
    """
    import pytest

    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Site, Tier

    conn, _, store_x = _pair(tmp_path, "two.db")
    op = repo.ensure_default_operator(conn)
    other_client = repo.create_client(conn, op, "D")
    other_site = repo.create_site(conn, other_client, "https://y.test/")

    a = store_x([_f("ONP", "img-alt-missing", "/a")], ["/a"])
    b = runs.create_run(conn, other_site, ["ONP"], "T2")
    runs.complete_run(conn, b, AuditResult(
        site=Site(domain="https://y.test/"), tier=Tier.T2, dimensions=["ONP"],
        findings=[], crawled_paths={"/a"}))

    with pytest.raises(ValueError) as exc:
        runs.compare_runs(conn, a, b)
    assert "site" in str(exc.value).lower(), (
        f"the refusal must say why; got {str(exc.value)!r}")
    conn.close()


def test_a_recorded_empty_crawl_is_not_an_unknown_one(tmp_path):
    """`_run_scope`'s own docstring: "Unknown is not empty."

    The fallback read `crawl_evidence.pages` under `if pages:`, so evidence
    recording an empty page list returned `None` — the value reserved for a
    run that never recorded its scope. The compare screen renders that as
    "Current run fetched an unrecorded number of page(s)" for the one run
    where the answer is decisive: it fetched none.
    """
    conn, site, store = _pair(tmp_path, "empty.db")
    baseline = store([_f("ONP", "img-alt-missing", "/a")], ["/a"])
    current = store([], [])
    with conn:
        conn.execute("UPDATE audit_runs SET crawled_paths=NULL,"
                     " crawl_evidence=? WHERE id=?",
                     (json.dumps({"pages": []}), current))

    diff = runs.compare_runs(conn, baseline, current)
    assert diff["scope"]["pages_crawled"] == 0, (
        "a run whose stored evidence records an empty page list fetched zero "
        f"pages; got {diff['scope']['pages_crawled']!r}")
    assert not diff["resolved"], "and it therefore resolved nothing"
    conn.close()


def test_unknown_scope_stops_a_site_level_finding_too(tmp_path):
    """Unknown scope is asked of every finding, not only page-scoped ones.

    `test_a_run_with_no_recorded_scope_resolves_nothing` above covers the same
    rule with two page-scoped findings, so it stayed green when round 025's
    reorder moved `crawled is None` below the `if not paths` shortcut and a
    site-level finding with no recorded scope came back resolved. Its docstring
    was true for half its subject and nothing said so.

    Reachable today only through rows predating migration 0021 —
    `complete_run` always writes `crawled_paths`, and `"[]"` is truthy — which
    is exactly the population the fallback in `_run_scope` exists to serve.
    """
    conn, site, store = _pair(tmp_path, "unknown-site.db")
    nap = _f("LOC", "nap-missing", None)          # names no page
    alt = _f("ONP", "img-alt-missing", "/a")

    baseline = store([nap, alt], ["/a"], dims=("LOC", "ONP"))
    current = store([], ["/a"], dims=("LOC", "ONP"))
    with conn:
        conn.execute("UPDATE audit_runs SET crawled_paths=NULL,"
                     " crawl_evidence=NULL WHERE id=?", (current,))

    diff = runs.compare_runs(conn, baseline, current)
    assert diff["scope"]["pages_crawled"] is None, "fixture precondition"
    assert not diff["resolved"], (
        "a run that never recorded what it crawled cannot have re-checked a "
        "site-level finding either; got "
        f"{[(f['dimension'], f['check_id']) for f in diff['resolved']]}")
    assert {f["check_id"] for f in diff["not_rechecked"]} == {"nap-missing",
                                                              "img-alt-missing"}
    conn.close()


def test_a_comparison_does_not_consult_the_lifecycle_table(tmp_path):
    """The property that replaced "accepted-risk is not a resolution".

    That test asserted a real defect: a negative filter over a five-value
    vocabulary counted `accepted-risk` — the operator saying explicitly that
    this one will not be fixed — as fixed. Round 023 then removed the
    `finding_states` read entirely, because the table describes the state
    *now* and made an earlier pair's comparison change when a later run
    landed. So the old assertion lost its subject: `set_state` cannot move a
    finding the code never reads, and it stayed green with the call deleted.

    The rule that survives is stronger and is what round 023 actually
    established — a comparison of (A, B) depends on A and B alone. Asserted
    here by moving every state the vocabulary has and requiring the answer not
    to move, so the day anything reads that table again this fails.
    """
    conn, site, store = _pair(tmp_path, "nostate.db")
    alt_a, alt_b = _f("ONP", "img-alt-missing", "/a"), _f("ONP", "img-alt-missing", "/b")
    nap = _f("LOC", "nap-missing", None)

    baseline = store([alt_a, alt_b, nap], ["/a", "/b"], dims=("LOC", "ONP"))
    current = store([], ["/a"], dims=("LOC", "ONP"))

    def answer():
        d = runs.compare_runs(conn, baseline, current)
        return {k: sorted(f["fingerprint"] for f in d[k])
                for k in ("new", "resolved", "not_rechecked", "persisting")}

    before = answer()
    assert before["resolved"], "fixture precondition: something must resolve"

    for state in ("accepted-risk", "regressed", "fixed", "open"):
        for fp in (alt_a.fingerprint, alt_b.fingerprint, nap.fingerprint):
            runs.set_state(conn, site, fp, state)
        assert answer() == before, (
            f"setting every finding to {state!r} changed the comparison; a "
            "pair's answer must depend on the two runs alone")
    conn.close()


def test_a_finding_on_a_page_the_baseline_never_fetched_is_not_new_to_the_site(tmp_path):
    """`new` was `b.keys() - a.keys()` with no question asked of run A.

    The mirror of the bucket beside it. `not_rechecked` exists because a
    finding absent from B can mean B did not look; `new` had no equivalent,
    so a finding present in B can mean **A** did not look, and that reads as
    the site having got worse.

    Its own fixture rather than the shared one, deliberately: the widening
    direction needs a baseline narrower than the later run, and every other
    fixture in this file narrows the other way.

    The direction matters because of who reads it. A first audit at 20 pages
    followed by a full one at 100 reports eighty pages of pre-existing
    findings under `## New issues` in a document sent to the client — the
    product telling a fee-paying reader that the work made things worse.
    """
    conn, site, store = _pair(tmp_path, "widened.db")
    old = _f("ONP", "img-alt-missing", "/a")
    unseen = _f("ONP", "img-alt-missing", "/b")

    baseline = store([old], ["/a"])              # only ever looked at /a
    current = store([old, unseen], ["/a", "/b"])  # wider: /b examined first time

    diff = runs.compare_runs(conn, baseline, current)
    new = {f["fingerprint"]: f for f in diff["new"]}

    assert unseen.fingerprint in new, "fixture precondition: it is in the bucket"
    assert new[unseen.fingerprint].get("new_reason"), (
        "a finding on a page the baseline never fetched is new to the record, "
        "not new to the site, and must carry the reason saying which — got "
        f"{new[unseen.fingerprint].get('new_reason')!r}")
    assert "/b" in new[unseen.fingerprint]["new_reason"]["paths"], (
        "the reason must name the page the baseline did not fetch; got "
        f"{new[unseen.fingerprint]['new_reason']!r}")
    conn.close()


def test_a_finding_on_a_page_the_baseline_did_fetch_is_new_without_qualification(tmp_path):
    """The negative half, so the reason cannot simply be set on everything.

    A regression the baseline was in a position to see is new to the site,
    and qualifying it would be the same over-claim in the other direction —
    telling the reader a real deterioration might be an artefact of scope.
    """
    conn, site, store = _pair(tmp_path, "same-scope.db")
    old = _f("ONP", "img-alt-missing", "/a")
    fresh = _f("TEC", "canonical-missing", "/a")

    baseline = store([old], ["/a"], dims=("ONP", "TEC"))
    current = store([old, fresh], ["/a"], dims=("ONP", "TEC"))

    diff = runs.compare_runs(conn, baseline, current)
    new = {f["fingerprint"]: f for f in diff["new"]}

    assert fresh.fingerprint in new
    assert not new[fresh.fingerprint].get("new_reason"), (
        "the baseline fetched /a, so this finding is new to the site and must "
        f"carry no qualifier; got {new[fresh.fingerprint].get('new_reason')!r}")
    conn.close()


def test_a_compare_reason_carries_no_markup(tmp_path):
    """The payload is data; markdown belongs to whoever renders markdown.

    `_unfetched_phrase` formatted a persistence value for the *document's*
    honesty gate — backticked paths so `checks.py` would exempt them, and a
    `(source: …)` clause on the overflow count. The compare screen then
    reversed that with three chained regexes so a reader would not see
    backticks, and one of the three matched nothing. A format contract across
    persistence, a markdown gate and a React view, with a test at neither end.

    So the reason travels as parts and each surface formats its own. This
    asserts the producer's half: nothing in the payload is markup, in any of
    the five shapes `why_not` and `why_new` can return.
    """
    conn, site, store = _pair(tmp_path, "nomarkup.db")
    many = [f"/blog/page-{i}" for i in range(1, 7)]
    spread = _f("ONP", "img-alt-missing", many[0])
    spread.affected_urls = [f"https://x.test{p}" for p in many]

    baseline = store([spread, _f("LOC", "nap-missing", None)], ["/a"],
                     dims=("ONP", "LOC"))
    current = store([], ["/a"], dims=("ONP",))

    diff = runs.compare_runs(conn, baseline, current)
    reasons = [f["not_rechecked_reason"] for f in diff["not_rechecked"]]
    reasons += [f["new_reason"] for f in diff["new"] if f.get("new_reason")]
    assert reasons, "fixture precondition: the pair must produce reasons"

    for reason in reasons:
        assert isinstance(reason, dict), (
            f"a reason must be parts, not a formatted string; got {reason!r}")
        assert set(reason) == {"lead", "paths", "overflow"}, (
            f"unexpected reason keys: {sorted(reason)}")
        blob = reason["lead"] + "".join(reason["paths"])
        for markup in ("`", "source:", "(+"):
            assert markup not in blob, (
                f"{markup!r} is document formatting and has no business in the "
                f"payload: {reason!r}")
    conn.close()


def test_every_reason_shape_survives_the_document_gate(tmp_path):
    """The consumer's half, at the end where the formatting exists.

    Five shapes reach the renderer — blocked, unaudited dimension, unrecorded
    scope, a short path list, and a list long enough to overflow. Each is
    rendered the way `render_comparison_report` renders it and put through the
    real gate, so a change to either side is caught by the side it breaks.
    """
    from clauditseo.reporting.checks import unsourced_number_lines
    from clauditseo.reporting.render import _reason_markdown

    shapes = [
        {"lead": "this run's crawl was blocked, so it fetched no pages",
         "paths": [], "overflow": 0},
        {"lead": "ONP was not audited by this run", "paths": [], "overflow": 0},
        {"lead": "this run did not record what it crawled",
         "paths": [], "overflow": 0},
        {"lead": "not fetched by this run",
         "paths": ["/blog/7-5m-for-smes", "/success-stories/70k-line"],
         "overflow": 0},
        {"lead": "not fetched by the baseline",
         "paths": ["/blog/q3-2026-review", "/guides/top-10", "/a"],
         "overflow": 8},
    ]
    for shape in shapes:
        line = f"- not re-checked: {_reason_markdown(shape)}"
        assert unsourced_number_lines(line) == [], (
            f"this reason shape does not survive the honesty gate: {line!r}")
