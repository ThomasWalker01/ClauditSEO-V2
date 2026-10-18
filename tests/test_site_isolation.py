"""A fingerprint identifies a finding within a site, never across sites.

``fingerprint = sha256(dimension:check_id:subject)`` and the subject is a URL
path, so two clients that both lack a title on ``/`` hold the same
fingerprint. That is deliberate — ``finding_states`` is keyed on
``(site_id, fingerprint)``, so the site is half the key.

Every read that turned a fingerprint back into its summary and URLs had
dropped that half, joining on the fingerprint alone and taking whichever row
was written last anywhere in the database. On the operator's own data, 13
rows of one client's record showed another client's URLs. The same join fed
the verify (which would have fetched the wrong site's pages), the
fixed-detection sweep (which would have cleared findings by looking at
another site) and the IndexNow ping (which would have submitted a third
party's URLs to a search engine).

These tests seed two sites whose findings genuinely collide, then check that
each read returns only its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite

FAST = TierBudget(max_pages=10, request_timeout_s=5, wall_clock_s=30, delay_s=0)

#: Identical structure on both sites, so the paths — and therefore the
#: fingerprints — are the same. Only the host differs, which is the whole
#: point: the fingerprint cannot tell them apart, so the query must.
BAD = ("<html lang=en><head></head><body><main><h1>h</h1>"
       "<img src=/i.png><p>x</p></main></body></html>")
ROUTES = {"/robots.txt": (200, {"Content-Type": "text/plain"},
                          "User-agent: *\nAllow: /\n"),
          "/": (200, {}, BAD), "/a": (200, {}, BAD)}


def _audit(conn, client, site) -> str:
    site_id = repo.create_site(conn, client, site.base_url + "/")
    crawled = crawl(site.base_url + "/", Tier.T2, budget=FAST)
    result = run_audit(Site(domain=site.base_url + "/"), crawled, ["ONP"], Tier.T2)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.complete_run(conn, run_id, result)
    return site_id


def _two_sites(tmp: Path):
    """Two clients, two servers, one audit each — and colliding fingerprints."""
    one, two = FixtureSite(ROUTES).start(), FixtureSite(ROUTES).start()
    conn = connect(tmp / "iso.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    a = _audit(conn, repo.create_client(conn, op, "A"), one)
    b = _audit(conn, repo.create_client(conn, op, "B"), two)
    return conn, (a, one), (b, two), (one, two)


def _hosts(urls) -> set[str]:
    from urllib.parse import urlsplit
    return {urlsplit(u).netloc for u in urls if u.startswith("http")}


def test_the_two_sites_really_do_share_fingerprints(tmp_path):
    """Guards the guard. If a later change puts the host into the subject,
    these fingerprints stop colliding and every test below passes for the
    wrong reason."""
    conn, (a, _), (b, _), servers = _two_sites(tmp_path)
    try:
        fa = {r["fingerprint"] for r in conn.execute(
            "SELECT fingerprint FROM finding_states WHERE site_id=?", (a,))}
        fb = {r["fingerprint"] for r in conn.execute(
            "SELECT fingerprint FROM finding_states WHERE site_id=?", (b,))}
        assert fa & fb, "the fixture no longer collides; the tests below are moot"
    finally:
        for s in servers:
            s.stop()


def test_the_record_shows_only_this_site(tmp_path):
    conn, (a, one), (b, two), servers = _two_sites(tmp_path)
    try:
        for site_id, own in ((a, one), (b, two)):
            urls = [u for r in runs.site_states(conn, site_id)
                    for u in r["affected_urls"]]
            assert urls, "nothing to check"
            assert _hosts(urls) == _hosts([own.base_url + "/"])
    finally:
        for s in servers:
            s.stop()


def test_the_current_tab_shows_only_this_site(tmp_path):
    conn, (a, one), (b, two), servers = _two_sites(tmp_path)
    try:
        for site_id, own in ((a, one), (b, two)):
            anat = runs.anatomy_view(conn, site_id)
            urls = [u for c in anat["categories"] for f in c["findings"]
                    for u in f["urls"]]
            assert urls, "nothing to check"
            assert _hosts(urls) == _hosts([own.base_url + "/"])
    finally:
        for s in servers:
            s.stop()


def test_a_verification_targets_only_this_site_pages(tmp_path):
    """The sharpest edge: this list is what the crawler is then handed."""
    conn, (a, one), (b, two), servers = _two_sites(tmp_path)
    try:
        for site_id, own in ((a, one), (b, two)):
            fps = [r["fingerprint"] for r in conn.execute(
                "SELECT fingerprint FROM finding_states"
                " WHERE site_id=? AND state='open'", (site_id,))]
            target = runs.pages_for_findings(conn, site_id, fps)
            assert target["urls"], "nothing to check"
            assert _hosts(target["urls"]) == _hosts([own.base_url + "/"])
    finally:
        for s in servers:
            s.stop()


def test_one_site_being_fixed_does_not_clear_the_other(tmp_path):
    """Both sites hold the same fingerprints, so a repair on A must move only
    A's rows.

    This one passes with the join un-scoped too, and is kept for what it does
    prove: the UPDATE carries the site. The cross-site read in
    ``_apply_states`` is genuinely hard to trip, because the fingerprint is
    made from the path — so a colliding finding names the same path on both
    sites and the comparison lands the same either way. It bites only where
    ``affected_urls`` holds more than the subject, which the operator's data
    showed (``/contact-us`` against ``/contact-us/``) and this fixture cannot
    reproduce. Scoped anyway: a query that is right for a reason no test
    covers is a query waiting to be wrong.
    """
    conn, (a, one), (b, _), servers = _two_sites(tmp_path)
    try:
        before = _states(conn, b)
        # Repaired in place, so the host and port — and therefore the site
        # row — stay exactly as they were.
        fixed = ("<html lang=en><head><title>A perfectly reasonable title</title>"
                 "<meta name=description content='"
                 + "A description that is comfortably long enough to pass. " * 2
                 + "'></head><body><main><h1>h</h1>"
                 "<img src=/i.png alt='a picture'><p>x</p></main></body></html>")
        one.routes["/"] = one.routes["/a"] = (200, {}, fixed)

        crawled = crawl(one.base_url + "/", Tier.T2, budget=FAST)
        result = run_audit(Site(domain=one.base_url + "/"), crawled, ["ONP"],
                           Tier.T2)
        runs.complete_run(conn, runs.create_run(conn, a, ["ONP"], "T2"), result)

        assert "fixed" in _states(conn, a).values(), "site A should have moved"
        assert _states(conn, b) == before, "site B's record was touched"
    finally:
        for s in servers:
            s.stop()


def _states(conn, site_id) -> dict[str, str]:
    return {r["fingerprint"]: r["state"] for r in conn.execute(
        "SELECT fingerprint, state FROM finding_states WHERE site_id=?",
        (site_id,))}


def test_indexnow_is_offered_only_this_site_urls(tmp_path):
    """It posts to a search engine, so a cross-site URL here is a disclosure
    rather than a display bug. Checked at the query, since the ping itself is
    skipped without a configured key."""
    conn, (a, one), (b, _), servers = _two_sites(tmp_path)
    try:
        # Site A, audited first — so for a shared fingerprint the globally
        # newest findings row is B's. Asking about B would have been right by
        # accident.
        conn.execute("UPDATE finding_states SET state='fixed' WHERE site_id=?", (a,))
        conn.commit()
        rows = conn.execute(
            "SELECT DISTINCT f.affected_urls FROM finding_states fs"
            f" JOIN findings f ON f.rowid = ({runs._latest_finding()})"
            " WHERE fs.site_id=? AND fs.state='fixed'", (a,)).fetchall()
        urls = [u for r in rows for u in json.loads(r["affected_urls"] or "[]")]
        assert urls, "nothing to check"
        assert _hosts(urls) == _hosts([one.base_url + "/"])
    finally:
        for s in servers:
            s.stop()
