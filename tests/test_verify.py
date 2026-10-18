"""Targeted verification: re-crawl only the pages behind chosen findings.

The loop this closes: an operator fixes four titles, ticks them, and asks for
those four pages to be looked at again. "I fixed it" and "it is fixed" are
different claims, and only the second one is allowed to change the record —
so a verification has to genuinely fetch the pages, and the state machine
judges what it finds.
"""

from __future__ import annotations

from pathlib import Path

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import runs
from tests.conftest import FixtureSite

FAST = TierBudget(max_pages=10, request_timeout_s=5, wall_clock_s=30, delay_s=0)

BAD = ("<html lang=en><head><title>t</title></head><body><main><h1>h</h1>"
       "<img src=/i.png><p>x</p></main></body></html>")
GOOD = ("<html lang=en><head><title>A perfectly reasonable page title</title>"
        "</head><body><main><h1>h</h1><img src=/i.png alt='a picture'>"
        "<p>x</p></main></body></html>")
#: `BAD`, plus the one link that makes a seed crawl from "/" reach "/a".
#: Every finding `BAD` raises is raised on both pages.
LINKING = BAD.replace("<p>x</p>", "<p>x</p><a href=/a>a</a>")


def _routes(home=BAD, a=BAD):
    return {"/robots.txt": (200, {"Content-Type": "text/plain"},
                            "User-agent: *\nAllow: /\n"),
            "/": (200, {}, home), "/a": (200, {}, a)}


# --- the crawl restriction -------------------------------------------------

def test_a_targeted_crawl_fetches_those_pages_and_follows_nothing():
    """A verification that wandered off would be a small audit, not a check of
    the thing that was fixed."""
    site = FixtureSite({**_routes(),
                        "/b": (200, {}, BAD), "/c": (200, {}, BAD)}).start()
    try:
        from urllib.parse import urlsplit
        only = crawl(site.base_url + "/", Tier.T2, budget=FAST,
                     only_urls=[site.base_url + "/a"])
        paths = {urlsplit(p.url).path or "/" for p in only.pages}
        assert paths == {"/a"}
        assert only.scope == "verify"
    finally:
        site.stop()


def test_a_targeted_crawl_declares_itself_partial():
    """Anything comparing a crawl against the whole site has to know this one
    held two pages by choice — the same reason nav crawls carry a scope."""
    site = FixtureSite(_routes()).start()
    try:
        result = crawl(site.base_url + "/", Tier.T2, budget=FAST,
                       only_urls=[site.base_url + "/"])
        assert result.scope != "site"
    finally:
        site.stop()


# --- what a verification has to cover --------------------------------------

def _seeded(tmp: Path, site, domain: str | None = None,
            dims: list[str] | None = None):
    """A site with one completed audit, and its open fingerprints.

    `domain` is what goes in the `sites` row, and it defaults to the shape
    every test here used before CQ-95: an absolute URL. Five of the six live
    sites hold a bare authority instead (`www.acme.com.au`), which is the
    one shape in which `normalise_url` is not a no-op — so a test that only
    ever seeds the absolute form cannot see what the narrow-run endpoints do
    with the other. The seed audit itself always crawls the absolute URL,
    because it stands for a run `launch_audit` started, and that entry point
    builds a scheme before it crawls.

    `dims` defaults to ONP alone, which produces only page-scoped findings.
    Pass a wider set to get a mixed one: AIS's `llms-txt-missing` carries an
    empty `affected_urls`, so it is the cheapest site-scoped finding the
    fixture can raise without an external provider.
    """
    from clauditseo.persistence import repo

    db = tmp / "verify.db"
    conn = connect(db)
    from clauditseo.db.migrate import migrate
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site_id = repo.create_site(conn, client, domain or site.base_url + "/")
    crawled = crawl(site.base_url + "/", Tier.T2, budget=FAST)
    dims = dims or ["ONP"]
    result = run_audit(Site(domain=site.base_url + "/"), crawled, dims, Tier.T2)
    run_id = runs.create_run(conn, site_id, dims, "T2")
    runs.complete_run(conn, run_id, result)
    fps = [r["fingerprint"] for r in conn.execute(
        "SELECT fingerprint FROM finding_states WHERE site_id=? AND state='open'",
        (site_id,))]
    return db, conn, site_id, fps


def test_the_target_set_is_the_pages_and_dimensions_of_those_findings(tmp_path):
    site = FixtureSite(_routes()).start()
    try:
        _, conn, site_id, fps = _seeded(tmp_path, site)
        target = runs.pages_for_findings(conn, site_id, fps)
        assert target["dimensions"] == ["ONP"]
        assert target["urls"]
        assert len(target["found"]) == len(fps)
    finally:
        site.stop()


def test_an_expert_finding_cannot_be_verified_by_a_crawl(tmp_path):
    """It carries `EXP:<tool>` and is judged by running the brief again. A
    crawl would fetch the page, find the brief's finding absent because no
    brief ran, and clear it — a false pass produced by checking the wrong
    thing."""
    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, _ = _seeded(tmp_path, site)
        run_id = conn.execute(
            "SELECT id FROM audit_runs WHERE site_id=?", (site_id,)).fetchone()["id"]
        runs.record_expert_findings(
            conn, run_id, "onpage-hygiene", "m",
            [{"code": "invented", "severity": "high", "summary": "s",
              "affected_urls": [site.base_url + "/"]}])
        fp = conn.execute(
            "SELECT fingerprint FROM findings WHERE dimension='EXP:onpage-hygiene'"
        ).fetchone()["fingerprint"]
        target = runs.pages_for_findings(conn, site_id, [fp])
        assert target["dimensions"] == []
    finally:
        site.stop()


# --- the loop, end to end --------------------------------------------------

def test_a_fix_clears_and_an_unfixed_page_stays_open(tmp_path):
    """The whole point: the crawl decides, not the operator. Two findings on
    a page that was genuinely fixed clear; the ones still present stay, and
    say so."""
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site)
        assert len(fps) >= 2
        site.routes["/"] = (200, {}, GOOD)     # the operator's fix

        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": fps})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cleared"] >= 1
        assert body["cleared"] + body["still_present"] == len(fps)
        # Reported per finding, so a row that did not clear can say so on
        # itself rather than leaving the operator to re-read the list.
        assert {o["fingerprint"] for o in body["outcomes"]} == set(fps)
    finally:
        site.stop()


def test_a_verification_says_what_it_declined_to_decide(tmp_path):
    """A narrow run may not clear a site-scoped finding, and it must not
    report one as still present either.

    `_apply_states` skips every finding with no page when the run is narrow
    (`persistence/runs.py`, `if narrow and not pages: continue`) — an
    eight-page crawl cannot establish a site-wide absence, which is right.
    What was wrong is what the operator was then told: the endpoint counted
    every finding that did not clear into `still_present`, and the mark bar
    printed "the page was fetched and the finding was still on it — check
    the template rather than the page". No page was fetched for it and the
    run declined to look.

    THE DEAD END, recorded here because report 053's WF-66 names it as the
    fix and it does not work. WF-66 says the endpoint should "return
    `verified` to the client" — `verify_outcomes` has always carried it, as
    `changed_by_run == run_id`. Branching on it was tried and measured on
    this fixture: of five findings, `verified` was True for exactly the two
    that CLEARED and False for the other three, one of which was the skipped
    site-scoped one. `_apply_states` writes a row only when it clears one, so
    a finding that was fetched and found still present takes no branch and
    looks identical to one nobody looked at. `verified` partitions cleared
    from not-cleared, which `cleared` already does.

    The discriminator is the rule `_apply_states` itself skips on — the
    finding names no page — so `pages_named_by()` now owns it and both call
    sites read it. That is the CQ-105 lesson: a rule with one owner rather
    than a copy at each consumer.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site, dims=["ONP", "AIS"])
        site_scoped = [r["fingerprint"] for r in conn.execute(
            "SELECT fingerprint FROM findings WHERE dimension='AIS'"
            " AND (affected_urls IS NULL OR affected_urls IN ('', '[]'))")]
        assert site_scoped, (
            "the fixture raised no site-scoped finding, so it cannot express "
            "the defect under test — see the dead end recorded below")
        site.routes["/"] = (200, {}, GOOD)     # the operator's fix
        # THE SECOND DEAD END, and it is this fixture's own. Until WF-100 this
        # line was absent and the test still passed — for the wrong reason.
        # `llms-txt-missing` is site-scoped, so it could never satisfy
        # `decided`; but the crawl fetches `/llms.txt` on EVERY run, verify
        # included, so a 404 meant the run genuinely re-raised the finding it
        # was being reported as not having looked at. The assertions below
        # were true of a finding the run had actually re-found, which is the
        # opposite of what they say. Serving the file makes the run genuinely
        # silent about it, which is the case this test was written for: a
        # narrow crawl may not establish a site-wide absence, so it must
        # decline rather than guess. A finding the crawl DOES re-raise is
        # `still_present` and is the sibling below.
        site.routes["/llms.txt"] = (200, {"Content-Type": "text/plain"},
                                    "# llms\n")

        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": fps})
        assert resp.status_code == 200, resp.text
        body = resp.json()

        by_fp = {o["fingerprint"]: o for o in body["outcomes"]}
        for fp in site_scoped:
            o = by_fp[fp]
            assert o["verified"] is False, (
                "the run judged a finding it has no evidence for")
            assert o["cleared"] is False

        # The count the screen reads, asserted first and on its own, because
        # this is the defect: a finding the run skipped must not be inside
        # the number the mark bar turns into "still there".
        expected_still = len(fps) - body["cleared"] - len(site_scoped)
        assert body["still_present"] == expected_still, (
            f"{len(site_scoped)} finding(s) named no page, so the run did not "
            f"look at them; still_present={body['still_present']} counts them "
            f"as present out of {len(fps)} asked about, "
            f"{body['cleared']} cleared")
        assert body["not_decided"] == len(site_scoped)
        assert (body["still_present"] + body["cleared"]
                + body["not_decided"]) == len(fps)
    finally:
        site.stop()


def test_a_page_the_run_could_not_read_is_not_decided_either(tmp_path):
    """WF-69. `decided` must mean the run READ the page, not that the finding
    named one.

    The sibling above closed the site-scoped door: a finding naming no page is
    reported as not-decided rather than as still present. This is the same
    sentence at the second door. `verify_outcomes` asked
    `bool(pages_named_by(urls))` while `_apply_states` asks `pages & crawled`
    before it will clear anything, so a finding whose page was requested and
    came back 503 satisfied the first question and failed the second: it was
    handed to the client as `decided: true, cleared: false`, which
    `fixloop.tsx` maps to "the page was fetched and the finding was still on
    it -- check the template rather than the page". The page was not fetched.

    A 503 is what makes this observable rather than a 404 or a timeout: the
    URL is in `target["urls"]` so the crawl genuinely attempts it, and
    `eligible()` (`engine/core.py:90-97`) keeps it out of `crawled_paths`
    because a `Page` object survives a failed fetch. That is KI-10's rule
    doing its job one layer down -- attempted is not fetched -- and it is the
    only reason the two predicates can be told apart from outside.

    The endpoint's own payload already knew: it returns `pages` alongside
    `pages_attempted`, and on this fixture they are 1 and 2.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    # DEAD END, recorded because the first version of this test looked
    # correct and could not express its own defect. `_seeded` crawls from "/"
    # and follows links; `_routes()`'s home is `BAD`, which links nowhere, so
    # the seed audit reached one page and raised nothing on /a. The
    # precondition assert below is what said so -- without it this test would
    # have passed vacuously the moment the fix landed, because a finding set
    # that is empty is trivially all-not-decided. `LINKING` exists only to
    # make the seed crawl two pages.
    site = FixtureSite(_routes(home=LINKING)).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site)
        # Findings naming /a AND NOT / -- the second clause is load-bearing.
        # SECOND DEAD END, and the more useful one. The first selector took
        # every finding naming /a and the fix left exactly one of five still
        # `decided`: `title-duplicate`, which names ['/', '/a'] because a
        # duplicate title is a statement about a pair. `/` WAS read, so
        # `pages & crawled` is non-empty and the run did decide it -- which
        # is `_apply_states:516-517` answering the same way, and mirroring
        # that rule is the entire fix. A test asserting otherwise would have
        # been asserting that the two rules should DISAGREE, in the test
        # written to make them agree. Whether a multi-page finding ought to
        # be judged on one of its pages is report 055's second open question
        # and is not settled here.
        on_a = [r["fingerprint"] for r in conn.execute(
            "SELECT fingerprint FROM findings WHERE affected_urls LIKE ?"
            " AND affected_urls NOT LIKE ?",
            (f'%"{site.base_url}/a"%', f'%"{site.base_url}/"%'))]
        assert on_a, (
            "the fixture raised no finding on /a, so it cannot express the "
            "defect under test -- the seed audit must reach both pages")

        # Not a fix and not a removal: the page is still named by the findings
        # and is still asked for, and the server refuses to serve it. That is
        # the whole distinction between attempted and fetched.
        site.routes["/a"] = (503, {}, "")

        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": fps})
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["pages_attempted"] > body["pages"], (
            "the fixture did not produce an unread page: "
            f"attempted={body['pages_attempted']} read={body['pages']}")

        by_fp = {o["fingerprint"]: o for o in body["outcomes"]}
        undecidable = [fp for fp in on_a if by_fp[fp]["decided"]]
        assert not undecidable, (
            f"{len(undecidable)} finding(s) on /a came back decided, but /a "
            f"returned 503 and was never read: pages={body['pages']} of "
            f"{body['pages_attempted']} attempted")

        # The count the mark bar turns into a sentence, asserted on its own.
        assert body["not_decided"] >= len(on_a), (
            f"not_decided={body['not_decided']} does not account for the "
            f"{len(on_a)} finding(s) on the page that was not read")
        assert (body["still_present"] + body["cleared"]
                + body["not_decided"]) == len(fps)
    finally:
        site.stop()


def test_a_verification_is_not_scored_as_an_audit(tmp_path):
    """A composite over two pages is not comparable with one over the site.
    Letting it into the trend would put a cliff in the chart every time
    someone ticked a box, and `watch_changes` would compare a two-page crawl
    against a full one — the shape of the sitemap-total bug."""
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site)
        before = conn.execute(
            "SELECT COUNT(*) n FROM metric_snapshots").fetchone()["n"]

        client = TestClient(create_app(db_path=db))
        body = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": fps}).json()

        assert conn.execute("SELECT kind FROM audit_runs WHERE id=?",
                            (body["run_id"],)).fetchone()["kind"] == "verify"
        after = conn.execute(
            "SELECT COUNT(*) n FROM metric_snapshots").fetchone()["n"]
        assert after == before, "a verification added a point to the trend"
    finally:
        site.stop()


def test_the_run_to_run_watch_ignores_verifications(tmp_path):
    """It reads the last two crawls. A two-page verification is not one."""
    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, _ = _seeded(tmp_path, site)
        verify_id = runs.create_run(conn, site_id, ["ONP"], "T2",
                                    kind="verify")
        runs.store_evidence(conn, verify_id, {"sitemaps": [],
                                              "sitemap_entry_total": 0})
        with conn:
            conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?",
                         (verify_id,))
        rows = conn.execute(
            "SELECT id FROM audit_runs WHERE site_id=? AND status='complete'"
            " AND crawl_evidence IS NOT NULL AND kind='audit'",
            (site_id,)).fetchall()
        assert verify_id not in {r["id"] for r in rows}
    finally:
        site.stop()


def test_a_verification_reports_what_the_run_re_emitted_not_who_wrote_the_row(tmp_path):
    """WF-100, both directions. A verification's outcome is decided by what
    the run *found*, not by which run last wrote the `finding_states` row.

    `_apply_states` writes a row only when it CLEARS one. A finding that was
    already `fixed` before this run takes no branch, so `changed_by_run` still
    names the older run, so `cleared` is False, so it fell into
    `still_present` by subtraction at `api/app.py` — and the operator was told
    a defect is still there about a crawl that did not re-find it. The other
    direction is the same predicate from the other side: a site-scoped finding
    the crawl DID re-raise was reported `not checked`, because `decided` asks
    whether a page of it was read and a finding naming no page can never
    satisfy that.

    Reproduced on the live database before this guard was written, read-only
    over verify run `71f0fad2186c4e0b99c782ebe46adfd5` (28 asked, 22 paths):
    `cleared 0, not_decided 2, still_present 26`, where the run re-emitted
    exactly 9 of the 28 and both `not_decided` rows were among those 9.

    Four words, not three, because "asked about, page read, not re-found,
    and it was already fixed before this run" is a real answer and neither
    `still present` nor `not checked` says it.

    THE DEAD END, recorded because the next reader will meet the same wall:
    `seen` cannot be reconstructed from `finding_states`. Every candidate
    there — `changed_by_run`, `verified`, `state` — is a record of a
    *transition*, and a re-emitted finding that was already open takes no
    transition at all. The only honest source is the run's own emitted
    findings, which is why `_apply_states` builds `current` and why this
    module now hands the same derivation to both readers rather than letting
    each compute it.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    from clauditseo.db.migrate import migrate  # noqa: F401  (already applied)

    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site, dims=["ONP", "AIS"])

        # A full audit against a repaired site moves the whole set to `fixed`
        # — the state this finding is about. It has to be a WIDE run: a narrow
        # one may not clear a finding that names no page, so the site-scoped
        # half could never reach `fixed` through the verify endpoint.
        site.routes["/"] = (200, {}, GOOD)
        site.routes["/a"] = (200, {}, GOOD)
        site.routes["/llms.txt"] = (200, {"Content-Type": "text/plain"},
                                    "# llms\n")
        repaired = crawl(site.base_url + "/", Tier.T2, budget=FAST)
        result = run_audit(Site(domain=site.base_url + "/"), repaired,
                           ["ONP", "AIS"], Tier.T2)
        wide = runs.create_run(conn, site_id, ["ONP", "AIS"], "T2")
        runs.complete_run(conn, wide, result)

        fixed = {r["fingerprint"] for r in conn.execute(
            "SELECT fingerprint FROM finding_states"
            " WHERE site_id=? AND state='fixed'", (site_id,))}
        # The population, derived from the database rather than asserted as a
        # literal: with nothing `fixed` this test cannot express the defect.
        assert fixed, "no finding reached `fixed`, so the defect has no subject"

        # llms.txt goes away again. The verify crawl fetches it on every run,
        # so this finding is genuinely re-raised by the run — while naming no
        # page, which is what made it unreportable under the old predicate.
        del site.routes["/llms.txt"]

        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": sorted(fps)})
        assert resp.status_code == 200, resp.text
        body = resp.json()

        re_emitted = {r["fingerprint"] for r in conn.execute(
            "SELECT fingerprint FROM findings"
            " WHERE run_id=? AND source='deterministic'", (body["run_id"],))}
        by_fp = {o["fingerprint"]: o for o in body["outcomes"]}

        raised_again = sorted(fixed & re_emitted)
        quiet = sorted(fixed - re_emitted)
        assert raised_again, (
            "the verify run re-emitted nothing that stood `fixed`, so the "
            "'not checked when the crawl re-found it' half has no subject")
        assert quiet, (
            "nothing stood `fixed` and stayed quiet, so the 'still there "
            "about a crawl that did not re-find it' half has no subject")

        # The count the operator reads, asserted first and against the run's
        # own output, because it is the defect: `still_present` is a
        # subtraction, and every finding that took no branch in
        # `_apply_states` lands in it.
        asked_and_refound = set(fps) & re_emitted
        assert body["still_present"] == len(asked_and_refound), (
            f"of the {len(fps)} findings asked about, the run re-raised "
            f"{len(asked_and_refound)}; {len(quiet)} stood `fixed` and were "
            f"not re-raised; still_present={body['still_present']}")
        assert body["not_decided"] == 0, (
            f"every finding asked about had either a page read or was "
            f"re-raised by the run; not_decided={body['not_decided']}")

        # --- direction 2: re-found, and it names no page ------------------
        for fp in raised_again:
            assert by_fp[fp]["outcome"] == "still_present", (
                f"{fp[:8]} was re-raised by this very run and is reported "
                f"{by_fp[fp]['outcome']!r}")

        # --- direction 1: fixed before the run, page read, not re-found ---
        for fp in quiet:
            assert by_fp[fp]["outcome"] == "unchanged", (
                f"{fp[:8]} stood fixed, its page was read and this run did "
                f"not re-find it; reported {by_fp[fp]['outcome']!r}")

        # The four words partition the set the operator was shown.
        assert (body["cleared"] + body["still_present"] + body["unchanged"]
                + body["not_decided"]) == len(fps)
    finally:
        site.stop()
