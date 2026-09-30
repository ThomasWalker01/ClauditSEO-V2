"""The three headline numbers, each with its denominator (brief v23 step BJ):
site size = declared ∪ discovered (never declared alone), coverage = crawled ÷
site size (not computable when the source failed, never over 100%, per run),
and assessed = findings not `open` ÷ findings in the run (unweighted).

The sitemap re-fetch that PRODUCES `suspected-retrieval-issue` is crawl-layer
work filed separately (the brief's own note), so `unknown (source failed)` is
exercised here through the stub — `retrieval_ok=False` and a visibly unread
sitemap — not through a second read.
"""

from __future__ import annotations

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import runs, repo


def _ev(start="https://x.test/", sitemap=(), pages=()):
    return {"start_url": start,
            "sitemap_entries": list(sitemap),
            "sitemaps": [{"url": start + "sitemap.xml", "status": 200,
                          "is_index": False, "error": None}],
            "pages": [{"url": u, "status": 200, "content_type": "text/html",
                       "content": "<html></html>", "outlinks": list(o)}
                      for u, o in pages]}


def test_site_size_is_declared_union_discovered_never_declared_alone():
    # Declared /a /b; crawled / and /a, / links to /c (undeclared). Union of
    # declared {a,b} and discovered {/, a, c} = {/, a, b, c} = 4.
    ev = _ev(sitemap=["https://x.test/a", "https://x.test/b"],
             pages=[("https://x.test/", ["https://x.test/c"]),
                    ("https://x.test/a", [])])
    ss = runs.site_size(ev)
    assert ss["size"] == 4 and ss["declared"] == 2 and ss["discovered"] == 3
    # The gap is discovered-but-not-declared: / and /c (a is declared).
    assert ss["gap"] == 2 and ss["unknown"] is False


def test_coverage_is_crawled_over_site_size_per_run():
    ev = _ev(sitemap=["https://x.test/a", "https://x.test/b", "https://x.test/c"],
             pages=[("https://x.test/", []), ("https://x.test/a", [])])
    # size = {a,b,c} ∪ {/,a} = 4; crawled 200s = 2 → 50%.
    cov = runs.run_coverage(ev)
    assert cov["crawled"] == 2 and cov["size"] == 4 and cov["pct"] == 50


def test_coverage_is_not_computable_when_its_source_failed():
    ev = _ev(sitemap=["https://x.test/a"], pages=[("https://x.test/", [])])
    cov = runs.run_coverage(ev, retrieval_ok=False)
    assert cov["pct"] is None and cov["unknown"] is True
    assert runs.site_size(ev, retrieval_ok=False)["size"] is None


def test_a_visibly_unread_sitemap_makes_the_size_unknown():
    ev = _ev(sitemap=["https://x.test/a"], pages=[("https://x.test/", [])])
    ev["sitemaps"] = [{"url": "https://x.test/sitemap.xml", "status": 500,
                       "is_index": False, "error": "timeout"}]
    ss = runs.site_size(ev)
    assert ss["unknown"] is True and ss["size"] is None


def test_www_is_not_a_different_site_from_the_apex():
    """The defect BJ's own render surfaced, and the reason it survived review.

    Every site record in this install holds a bare domain, so the crawl starts
    at the apex — `https://beacon.com.au/` — and the site redirects to
    `www.`, so every page comes back on the other spelling. Comparing hosts as
    written keyed every path to None: `declared 0 · discovered 0 · size 0`,
    with `unknown` **False**, and the header drew a confident `0 on the site`
    for a twelve-page site that had just been crawled in full. Coverage
    degraded to "not computable" rather than dividing by zero, and that is how
    it would have survived: the number was wrong, not absurd.

    The brief predicts this site's figure by hand — *"Birch: 10 plus 2 = 12"* —
    so that is what is asserted, in the shape that failed.
    """
    ev = _ev(start="https://birch.test/",
             sitemap=[f"https://www.birch.test/p{i}" for i in range(1, 11)],
             pages=[("https://www.birch.test/", ["https://www.birch.test/p1"]),
                    *[(f"https://www.birch.test/p{i}", []) for i in range(1, 11)],
                    ("https://www.birch.test/unlisted", [])])
    ss = runs.site_size(ev)
    assert ss["declared"] == 10, ss
    assert ss["size"] == 12, (
        f"the apex and `www.` are being counted as two sites: {ss}")
    # `/` and `/unlisted` are reached and not declared.
    assert ss["gap"] == 2 and ss["unknown"] is False, ss
    cov = runs.run_coverage(ev)
    assert cov["crawled"] == 12 and cov["pct"] == 100, cov

    # And a genuinely different subdomain stays off-host: collapsing it would
    # put another property's pages in this site's denominator, which is the
    # opposite defect and the worse one for a client-facing ratio.
    other = _ev(start="https://birch.test/",
                sitemap=["https://birch.test/a"],
                pages=[("https://birch.test/", ["https://blog.birch.test/post"])])
    assert runs.site_size(other)["size"] == 2, runs.site_size(other)


def test_coverage_never_exceeds_one_hundred_percent():
    # Every declared page also crawled, plus the crawl found more — reached is a
    # subset of the size, so the ratio cannot exceed 1.
    ev = _ev(sitemap=["https://x.test/a"],
             pages=[("https://x.test/", []), ("https://x.test/a", [])])
    assert runs.run_coverage(ev)["pct"] <= 100


def test_coverage_is_scoped_to_its_run():
    small = runs.run_coverage(_ev(sitemap=["https://x.test/a", "https://x.test/b"],
                                  pages=[("https://x.test/", [])]))
    full = runs.run_coverage(_ev(sitemap=["https://x.test/a"],
                                 pages=[("https://x.test/", []), ("https://x.test/a", [])]))
    # Same site, different runs → different coverage; the figure is the run's.
    assert small["pct"] != full["pct"]


def _db(tmp_path):
    conn = connect(tmp_path / "bj.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "BJ Co")
    site_id = repo.create_site(conn, client, "x.test")
    return conn, site_id


def _seed_findings(conn, site_id, run_id, states):
    """states: list of (fingerprint, state). Writes a findings row and a
    finding_states row for each."""
    for i, (fp, state) in enumerate(states):
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, "
            "summary, affected_urls, evidence, fingerprint, created_at) VALUES "
            "(?,?,?,?,?,?,?,?,?,?)",
            (f"f{i}", run_id, "TEC", "c", "high", "s", "[]", "{}", fp, "2026-09-11T00:00:00"))
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run, updated_at) "
            "VALUES (?,?,?,?,?)", (site_id, fp, state, run_id, "2026-09-11T00:00:00"))
    conn.commit()


def test_assessed_counts_accepted_and_withdrawn_and_fixed_only_open_does_not(tmp_path):
    conn, site_id = _db(tmp_path)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    _seed_findings(conn, site_id, run_id, [
        ("fp1", "open"), ("fp2", "accepted-risk"), ("fp3", "withdrawn"),
        ("fp4", "fixed"), ("fp5", "open")])
    a = runs.run_assessed(conn, run_id, site_id)
    # 5 findings, 2 open → 3 assessed (accepted, withdrawn, fixed).
    assert a["total"] == 5 and a["assessed"] == 3 and a["pct"] == 60


def test_assessed_weights_a_low_the_same_as_a_critical(tmp_path):
    conn, site_id = _db(tmp_path)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    # Two findings both assessed; severity does not enter the ratio.
    for i, (fp, sev, state) in enumerate([("a", "low", "fixed"), ("b", "critical", "fixed")]):
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, "
            "summary, affected_urls, evidence, fingerprint, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"f{i}", run_id, "TEC", "c", sev, "s", "[]", "{}", fp, "2026-09-11T00:00:00"))
        conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run, updated_at) "
                     "VALUES (?,?,?,?,?)", (site_id, fp, state, run_id, "2026-09-11T00:00:00"))
    conn.commit()
    assert runs.run_assessed(conn, run_id, site_id)["pct"] == 100
