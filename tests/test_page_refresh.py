"""F-06: re-measure one page for the dimension covering one section.

The engine's unit is `(url, dims)` and it always was — `crawl_site` takes
`only_urls`, `run_audit` takes a dimension list, and the verify path has been
assembling exactly that call since `0011_run_kind.sql`. So this feature is not
a new capability; it is an entry point plus **the rules about what a narrow
run may claim**, and those rules are what these tests are about:

  * it reads the one page it was given, and nothing it links to;
  * it records everything the dimension emits for that page — not a filtered
    slice matching the section, because a suppressed finding and a finding
    that stopped firing are indistinguishable afterwards, and the resolution
    rule cannot tell them apart either;
  * it closes only findings whose page it actually revisited, and not the
    site-scoped ones it never measured;
  * it writes no comparable composite, so the site's trend does not move;
  * it inherits the tier of the audit it refreshes, because tier is a term in
    the comparability key (WF-56) and a T2 refresh over a T3 audit would
    reintroduce that defect through a new door.

**Ordinary tests, not guards**, per the rule `FEATURES.md` states for its
entries and `test_section_refresh.py` records for the coarse control: the
behaviour did not exist, so there was no prior failure to observe and
DISCIPLINE rule 1 does not apply. `/api/sites/{id}/refresh` answered 404 and
`kind='refresh'` appeared nowhere in the tree.

**Three exceptions are real guards**, and they are what checking the first of
those rules produced rather than assuming it. The trend was guarded when
`verify` arrived; three other readers of "the site's last run" were not, and
they took the new kind straight away — `test_the_home_card_reports_the_audits_score_not_a_refreshs`,
`test_a_refresh_does_not_postpone_the_scheduled_audit` and
`test_a_refresh_is_not_read_as_the_site_losing_its_pages` all failed against
the tree before the readers were narrowed to `kind='audit'`. Each failed for
a `verify` run too, invisibly, for as long as `verify` has existed.

The screen's half of this feature is in `test_section_refresh.py`, with the
coarse control it narrows and the browser fixture that reads it. The split is
by what the clause needs, not by what it is about: everything here answers
from stored state, and nothing here needs a browser.

The fixture site and the seeded audit are `test_verify.py`'s — a refresh is
the same shape of narrow run, and two fixtures for one shape is how the two
drift apart — with the home page linked to `/a`, for the reason recorded on
`LINKED` below.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo import anatomy as an
from clauditseo.api.app import create_app
from clauditseo.persistence import runs
from tests.conftest import FixtureSite
from tests.test_verify import BAD, GOOD, _routes, _seeded

#: `test_verify.py`'s home page with one link added, because the audit this
#: feature refreshes has to have *reached* the page being refreshed. Without
#: the link the fixture crawl stops at `/` and every finding sits there, so a
#: refresh of `/a` re-measures a page nothing was ever recorded against —
#: which passes a "clears only what it revisited" test by clearing nothing.
#: The evidence has to be able to disagree with the claim.
LINKED = BAD.replace("<p>x</p>", "<p>x</p><a href='/a'>a</a>")

#: `/a` differs from `/` on purpose. Findings that name only the home page
#: are what "every other page is untouched" is measured against, and a
#: fixture whose two pages are identical produces one aggregate finding
#: across both and nothing to compare.
PAGE_A = ("<html lang=en><head><title>A page with a reasonable title</title>"
          "<meta name=description content='A description long enough to pass "
          "the length check that the home page fails on'></head><body><main>"
          "<h1>h</h1><img src=/i.png><p>x</p></main></body></html>")


def _fixture():
    return FixtureSite(_routes(home=LINKED, a=PAGE_A))


def _client_and_site(tmp_path, site):
    """A site with one completed T2 ONP audit over both pages, and a client
    onto it."""
    db, conn, site_id, _fps = _seeded(tmp_path, site)
    return TestClient(create_app(db_path=db)), conn, site_id


def _refresh(client, site_id: str, url: str, section: str = "headings"):
    return client.post(f"/api/sites/{site_id}/refresh",
                       json={"url": url, "section": section})


def _pages_by_fingerprint(conn) -> dict[str, set[str]]:
    """Every fingerprint's pages, as paths — the same reduction
    `_apply_states` makes when it decides whether a page was revisited."""
    out: dict[str, set[str]] = {}
    for row in conn.execute("SELECT fingerprint, affected_urls FROM findings"):
        out.setdefault(row["fingerprint"], set()).update(
            urlsplit(u).path or "/"
            for u in json.loads(row["affected_urls"] or "[]")
            if u.startswith("http"))
    return out


def _states(conn, site_id: str) -> dict[str, tuple]:
    return {r["fingerprint"]: (r["state"], r["updated_at"], r["changed_by_run"])
            for r in conn.execute(
                "SELECT fingerprint, state, updated_at, changed_by_run"
                " FROM finding_states WHERE site_id=?", (site_id,))}


# --- the unit: one page, one dimension --------------------------------------

def test_a_refresh_reads_the_one_page_it_was_given(tmp_path):
    """The whole unit, in one assertion set: the section names a dimension,
    the operator names a page, and the crawl fetches that page and follows
    nothing out of it."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        resp = _refresh(client, site_id, site.base_url + "/a")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["dimension"] == "ONP", body
        assert body["pages"] == 1, body
        row = conn.execute(
            "SELECT kind, tier, crawled_paths FROM audit_runs WHERE id=?",
            (body["run_id"],)).fetchone()
        assert row["kind"] == "refresh", "a refresh recorded itself as an audit"
        assert json.loads(row["crawled_paths"]) == ["/a"], (
            "the refresh read more than the page it was asked for")
    finally:
        site.stop()


def test_the_dimension_comes_from_the_section_not_from_the_caller(tmp_path):
    """One way to configure a run, and it is the one the section offered.
    The body carries a section; `anatomy.refresh_for` decides what runs, from
    the same table the screen's offer is built from."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        body = _refresh(client, site_id, site.base_url + "/a",
                        section="indexability").json()
        # TEC covers four categories, ONP five, so indexability offers TEC —
        # the smallest covering run, decided by `refresh_for` rather than
        # here.
        assert body["dimension"] == an.refresh_for("indexability")["dimension"]
        assert json.loads(conn.execute(
            "SELECT dimensions FROM audit_runs WHERE id=?",
            (body["run_id"],)).fetchone()["dimensions"]) == [body["dimension"]]
    finally:
        site.stop()


def test_it_records_everything_the_dimension_emits_for_the_page(tmp_path):
    """The design decision F-06 states outright. A refresh of Headings runs
    ONP, and ONP also emits for Title & description, Images, Structured data
    and Indexability — all of which is recorded.

    Filtering the output down to the section would leave a finding that was
    held back indistinguishable from one that no longer fires, and the
    resolution rule reads exactly that difference."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        body = _refresh(client, site_id, site.base_url + "/a").json()

        recorded = [dict(r) for r in conn.execute(
            "SELECT check_id, dimension FROM findings WHERE run_id=?",
            (body["run_id"],))]
        assert recorded, "the refresh recorded nothing at all"
        sections = {an.categorise(r["check_id"], r["dimension"])
                    for r in recorded}
        assert sections - {"headings"}, (
            f"only the section asked for was recorded: {sections}")
        assert sections <= set(an.DIMENSION_CATEGORIES["ONP"]), (
            f"the refresh recorded outside the dimension it ran: {sections}")
    finally:
        site.stop()


# --- what it may close ------------------------------------------------------

def test_every_other_pages_findings_and_timestamps_are_untouched(tmp_path):
    """The acceptance signal's second clause, read from stored state rather
    than from a screen: the home page is fixed and NOT refreshed, so its
    findings must still be open, with the timestamps they had."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        pages = _pages_by_fingerprint(conn)
        elsewhere = {fp for fp, paths in pages.items()
                     if paths and "/a" not in paths}
        assert elsewhere, "the fixture has no finding off the refreshed page"
        before = _states(conn, site_id)

        site.routes["/"] = (200, {}, GOOD)          # fixed, and not looked at
        assert _refresh(client, site_id,
                        site.base_url + "/a").status_code == 200

        after = _states(conn, site_id)
        for fp in sorted(elsewhere):
            assert after[fp] == before[fp], (
                f"{fp} is on another page and the refresh moved it: "
                f"{before[fp]} -> {after[fp]}")
    finally:
        site.stop()


def test_it_closes_only_findings_whose_page_it_revisited(tmp_path):
    """The clause that makes the run worth trusting. The page it read is
    genuinely fixed, so its findings clear; everything cleared names that
    page."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        pages = _pages_by_fingerprint(conn)

        site.routes["/a"] = (200, {}, GOOD)         # the operator's fix
        body = _refresh(client, site_id, site.base_url + "/a").json()
        assert body["cleared"] >= 1, (
            f"a fixed page cleared nothing, so this proves nothing: {body}")

        cleared = [r["fingerprint"] for r in conn.execute(
            "SELECT fingerprint FROM finding_states"
            " WHERE site_id=? AND state='fixed' AND changed_by_run=?",
            (site_id, body["run_id"]))]
        for fp in cleared:
            assert "/a" in pages.get(fp, set()), (
                f"{fp} was cleared by a run that never read its page")
    finally:
        site.stop()


def test_it_cannot_clear_a_site_scoped_finding_it_never_measured(tmp_path):
    """One page is not a reading of the site.

    `_apply_states` treats a site-scoped finding as tested by the dimension
    merely having run — sound for an audit, which crawls the site the check
    describes, and false for a run that fetched one URL. The same run clears
    a page-scoped finding in the same call, which is what shows the rule is
    doing the work rather than the run having cleared nothing at all."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        run_id = conn.execute(
            "SELECT id FROM audit_runs WHERE site_id=?", (site_id,)).fetchone()["id"]
        with conn:
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
                " source, summary, affected_urls, evidence, recommendation,"
                " fingerprint, created_at)"
                " VALUES ('sf', ?, 'ONP', 'site-wide-thing', 'medium',"
                " 'deterministic', 's', '[]', '{}', 'r', 'site-scoped-fp', ?)",
                (run_id, "2026-08-18T00:00:00Z"))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state,"
                " changed_by_run, updated_at) VALUES (?, 'site-scoped-fp',"
                " 'open', ?, ?)", (site_id, run_id, "2026-08-18T00:00:00Z"))

        site.routes["/a"] = (200, {}, GOOD)
        body = _refresh(client, site_id, site.base_url + "/a").json()

        assert body["cleared"] >= 1, "the run cleared nothing, so this is vacuous"
        state = conn.execute(
            "SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
            (site_id, "site-scoped-fp")).fetchone()["state"]
        assert state == "open", (
            "a one-page refresh cleared a finding measured over the site")
    finally:
        site.stop()


# --- what it may score ------------------------------------------------------

def test_it_writes_no_comparable_composite_and_the_trend_does_not_move(tmp_path):
    """The acceptance signal's third clause, measured rather than asserted:
    the trend is read either side and the points are compared."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        before = runs.site_trend(conn, site_id)
        before_rows = conn.execute(
            "SELECT COUNT(*) n FROM metric_snapshots WHERE site_id=?",
            (site_id,)).fetchone()["n"]
        assert before, "the seeded audit contributed no trend point to compare"

        body = _refresh(client, site_id, site.base_url + "/a").json()

        assert body["scored"] is False
        assert runs.site_trend(conn, site_id) == before, (
            "a refresh moved the site's trend")
        assert conn.execute(
            "SELECT COUNT(*) n FROM metric_snapshots WHERE site_id=?",
            (site_id,)).fetchone()["n"] == before_rows, (
            "a refresh wrote a measurement into the site's history")
    finally:
        site.stop()


def test_the_kind_filters_already_written_cover_a_refresh(tmp_path):
    """Point 1 of the item, checked rather than assumed. `watch_changes`,
    `current_state` and the report currency index all filter to
    `kind='audit'`, so they exclude a third kind on the day it is added —
    but "should" is not a measurement."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        audit_id = conn.execute(
            "SELECT id FROM audit_runs WHERE site_id=?", (site_id,)).fetchone()["id"]
        watch_before = runs.watch_changes(conn, site_id)
        state_before = runs.current_state(conn, site_id)

        site.routes["/a"] = (200, {}, GOOD)     # so the refresh moves something
        body = _refresh(client, site_id, site.base_url + "/a").json()
        assert body["run_id"] != audit_id and body["cleared"] >= 1, body

        assert runs.watch_changes(conn, site_id) == watch_before, (
            "the run-to-run watch compared a one-page refresh against an audit")
        state = runs.current_state(conn, site_id)
        assert state["last_audit"] == state_before["last_audit"], (
            f"the fix loop is reporting a refresh as the last audit: {state}")
        # `moved` is "what the last audit changed", derived from current
        # state — so a finding the refresh closed leaves that group rather
        # than joining it. What must not happen is the reverse: the refresh's
        # own clearances counted as the audit's work.
        assert state["moved"]["fixed"] == state_before["moved"]["fixed"], (
            "a refresh's clearances were reported as the last audit's")
        assert {r["changed_by_run"] for r in conn.execute(
            "SELECT changed_by_run FROM finding_states"
            " WHERE site_id=? AND state='fixed'", (site_id,))} == {body["run_id"]}, (
            "the run that cleared them is not the run recorded against them")
    finally:
        site.stop()


def test_the_home_card_reports_the_audits_score_not_a_refreshs(tmp_path):
    """**A guard**, and one of two here.

    `/api/overview` picks the newest scored run with no `kind` filter at all,
    so the composite of a one-page pass — which `mark_complete` writes onto
    the run row for every kind — became the number on the client card. The
    trend was already protected and this was not, which is exactly the
    difference between a guard that was written and a guard that was assumed.

    It failed for a `verify` run too, and has since `verify` shipped. The
    filter closes both, because the reader's question — "what did the last
    audit of this site score" — has one right answer for every narrow kind.
    """
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        before = client.get("/api/overview").json()
        card = next(s for s in before["sites"] if s["site_id"] == site_id)

        site.routes["/a"] = (200, {}, GOOD)
        _refresh(client, site_id, site.base_url + "/a")

        after = next(s for s in client.get("/api/overview").json()["sites"]
                     if s["site_id"] == site_id)
        assert after["score"] == card["score"], (
            "a one-page refresh became the site's score on Home")
        assert after["last_run_id"] == card["last_run_id"], (
            "a refresh became the run Home links to as the site's last")
        assert after["last_run_at"] == card["last_run_at"]
    finally:
        site.stop()


def test_a_refresh_is_not_read_as_the_site_losing_its_pages(tmp_path):
    """**A guard**, the third.

    `crawl_diff` compares the last two crawls to catch a deleted section or a
    template that ate the body copy. It read any kind of run, so a one-page
    refresh laid against a full audit reported every other page as *removed*
    — the sitemap-total bug's exact shape, arriving as an alert about a site
    that had not changed at all. `watch_changes` beside it had the filter;
    this one did not.
    """
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        # The seeded audit stores no evidence, and `crawl_diff` needs two
        # blobs to compare — so without this the comparison never happens and
        # the test passes by having nothing to say. It was written that way
        # first and was found by removing the filter it exists to cover.
        audit_id = conn.execute(
            "SELECT id FROM audit_runs WHERE site_id=?", (site_id,)).fetchone()["id"]
        runs.store_evidence(conn, audit_id, {"pages": [
            {"url": site.base_url + "/", "status": 200, "word_count": 40},
            {"url": site.base_url + "/a", "status": 200, "word_count": 40}]})
        before = runs.crawl_diff(conn, site_id)

        assert _refresh(client, site_id,
                        site.base_url + "/a").status_code == 200

        assert runs.crawl_diff(conn, site_id) == before, (
            "a one-page refresh was read as a change to the site's page set")
    finally:
        site.stop()


def test_a_refresh_does_not_postpone_the_scheduled_audit(tmp_path):
    """**A guard**, the second.

    `scheduler.due_sites` reads the newest run of any kind as "the last
    crawl", so a refresh reset the clock on unattended auditing: the site
    stopped being due, silently, because somebody re-read one page. Same
    exposure as the card above, and the same fix — the clock counts audits.
    """
    from clauditseo import scheduler

    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        old = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
        with conn:
            conn.execute("UPDATE sites SET schedule='weekly' WHERE id=?", (site_id,))
            conn.execute("UPDATE audit_runs SET started_at=? WHERE site_id=?",
                         (old, site_id))
        now = datetime.utcnow()
        assert site_id in {s["id"] for s in scheduler.due_sites(conn, now)}, (
            "the site was not due before the refresh, so this proves nothing")

        _refresh(client, site_id, site.base_url + "/a")

        assert site_id in {s["id"] for s in scheduler.due_sites(conn, now)}, (
            "a refresh postponed the site's next unattended audit")
    finally:
        site.stop()


# --- the tier it runs at ----------------------------------------------------

@pytest.mark.parametrize("tier", ["T2", "T3"])
def test_it_inherits_the_tier_of_the_audit_it_refreshes(tmp_path, tier):
    """Tier is a term in the comparability key because a T2 crawl and a T3
    crawl measure different populations (WF-56). A refresh that picked its own
    tier would lay one population over the other through a new door."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        with conn:
            conn.execute("UPDATE audit_runs SET tier=? WHERE site_id=?",
                         (tier, site_id))

        body = _refresh(client, site_id, site.base_url + "/a").json()

        assert body["tier"] == tier
        assert conn.execute("SELECT tier FROM audit_runs WHERE id=?",
                            (body["run_id"],)).fetchone()["tier"] == tier, (
            "the tier the refresh ran at was not recorded on the run")
    finally:
        site.stop()


def test_a_site_with_no_audit_has_nothing_to_refresh(tmp_path):
    """The tier comes from the audit being refreshed, so there has to be one.
    Refused with the reason rather than defaulted to T2 — a default here is
    the WF-56 defect, chosen quietly."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo

    site = _fixture().start()
    try:
        db = tmp_path / "bare.db"
        conn = connect(db)
        migrate(conn)
        op = repo.ensure_default_operator(conn)
        site_id = repo.create_site(conn, repo.create_client(conn, op, "C"),
                                   site.base_url + "/")
        client = TestClient(create_app(db_path=db))

        resp = _refresh(client, site_id, site.base_url + "/a")
        assert resp.status_code == 422, resp.text
        assert "no audit" in resp.json()["detail"]
        assert conn.execute(
            "SELECT COUNT(*) n FROM audit_runs").fetchone()["n"] == 0, (
            "a refused refresh left a run behind")
    finally:
        site.stop()


# --- what it refuses --------------------------------------------------------

def test_a_section_no_sweep_refreshes_cannot_be_refreshed(tmp_path):
    """`ANALYSIS_ONLY`: no sweep populates International, so no run refreshes
    it. The screen offers nothing there; the endpoint refuses it, so the rule
    holds for a caller that did not read the screen.

    The exemplar was `urls` until 29 August 2026, when TEC gained
    `internal-link-tracking-params` and a sweep started covering it. The
    premise assertion below is what said so — it is written to fail loudly
    rather than let the case be tested against a section that is no longer an
    instance of it.
    """
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        assert an.refresh_for("intl") is None, "the premise moved"

        resp = _refresh(client, site_id, site.base_url + "/a", section="intl")
        assert resp.status_code == 422, resp.text
        assert "no automatic check refreshes" in resp.json()["detail"]
    finally:
        site.stop()


def test_a_refresh_cannot_be_pointed_at_another_site(tmp_path):
    """The URL is a page of the site under audit. Anything else is a crawl of
    somewhere else, started through a control that says it re-reads a page
    the operator is looking at."""
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        resp = _refresh(client, site_id, "https://example.com/a")
        assert resp.status_code == 422, resp.text
        assert "not a page of this site" in resp.json()["detail"]
    finally:
        site.stop()


def test_an_unknown_section_is_refused_rather_than_guessed(tmp_path):
    site = _fixture().start()
    try:
        client, conn, site_id = _client_and_site(tmp_path, site)
        resp = _refresh(client, site_id, site.base_url + "/a", section="nope")
        assert resp.status_code == 422, resp.text
        assert "unknown section" in resp.json()["detail"]
    finally:
        site.stop()
