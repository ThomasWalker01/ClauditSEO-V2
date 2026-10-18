"""KI-56 — a page-scoped brief run against more than one page inside one audit
run used to keep only the last page. Fixed; these are the guards.

**The defect, as it was reproduced rather than read.** Two `onpage-hygiene`
calls in one run, `/blocked-drains` then `/hot-water`, against a migrated
database at `486896b`:

    after page 1: findings [('h1-missing', ['http://127.0.0.1/blocked-drains'])]
    after page 2: findings [('description-missing', ['http://127.0.0.1/hot-water'])]

Page one's finding was gone and so was its report row. Two causes, one per
half: `expert_reports` was keyed `PRIMARY KEY (run_id, tool_id)` with
`page_url` *outside* the key and `store_expert_report` writes
`INSERT OR REPLACE`; `record_expert_findings` deleted by `(run_id, dimension)`.

What it had already cost: the two paid runs of 2026-08-24 were billed for
three `onpage-hygiene` calls each and stored one report each, and the
resulting 0.33-against-0.67 was read as a tier difference until
`analyst_cache` was replayed and both models turned out to have caught it.

**Why the two halves are fixed by two different mechanisms.** `QUESTIONS.md`
**Q-19** answers *page-scope the persistence*, and that is the whole of the
`expert_reports` half: migration 0029 puts `page_url` in the primary key, with
existing rows migrating to `''` rather than NULL. It reaches neither half of
`findings`, which carries no page column and whose fingerprint is deliberately
site-grained — `make_fingerprint(f"EXP:{tool_id}", f["code"], "site")`, whose
own docstring argues for it: *"Whether `opening-hours-missing` afflicts this
site is the stable fact worth remembering; which node exhibited it today is
not."* So there was nothing to scope that delete by, and giving it something
was a second decision with two defensible answers. That decision is
`QUESTIONS.md` **Q-23**, answered *merge across pages by code* on 2026-08-25:
pool `affected_urls` and join summaries, which is what `_merge_by_code`
already did when one call carried both pages.

**And the halves could not be split**, which is why this file spent a day
fixing neither. `clauditseo/golden.py`'s `_caveats` detects the loss from the
database rather than asserting it — *more calls billed than reports stored IS
the deletion* — so repairing only `expert_reports` would have made calls equal
reports, stopped the caveat printing, and left the findings being deleted with
nothing saying so. A true warning would have gone silent on a half-fix.

**These four were two strict xfails and two live counter-assertions**, and the
counter-assertions are the reason the fix could not pass by simply no longer
replacing anything: they are why `page_url` migrates to `''` and not to NULL,
since SQLite treats NULLs in a primary key as distinct and a NULL inside the
key would trade a silent delete for a silent duplicate.
"""

from __future__ import annotations

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

TOOL = "onpage-hygiene"


@pytest.fixture
def one_run(tmp_path):
    """One site, one run, and a brief that can be pointed at a page.

    Built through `repo`/`runs` rather than by INSERT, so the schema under
    test is the migrated one rather than a fixture that agrees with the code
    by construction.
    """
    conn = connect(tmp_path / "pages.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"),
                            "http://127.0.0.1/")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    yield conn, site, run_id
    conn.close()


def _read(conn, run_id, page: str, code: str, summary: str):
    """One page-scoped brief call, both halves, exactly as `run_expert` makes
    them: the findings and then the report, both handed the page that was
    read.

    Calling the product's real signature is the point, and the signature is
    half of the fix. While this file was xfailing, `record_expert_findings`
    took no page at all — an earlier draft passed `page_url=` anyway and the
    tests went red on `TypeError: unexpected keyword argument` instead of on
    the deletion, marking a signature as the defect rather than the data loss.
    Q-23's answer is what gave the function a page to be told, so the argument
    is here now for the opposite reason: `run_expert` passes
    `getattr(extra.get("page"), "url", None)` to both calls, and a helper that
    passed it to only one would be testing a shape the product never makes.
    """
    url = f"http://127.0.0.1{page}"
    runs.record_expert_findings(
        conn, run_id, TOOL, "m-1",
        [{"severity": "high", "code": code, "summary": summary,
          "affected_urls": [url]}], page_url=url)
    runs.store_expert_report(
        conn, run_id, TOOL,
        {"model": "m-1", "report": summary, "tokens": 100}, page_url=url)


def test_a_second_page_does_not_delete_the_first_pages_findings(one_run):
    """The half that corrupted the golden measurement, and the half Q-19's
    answer did not reach — Q-23's *merge across pages by code* is what does.

    Two codes from two pages, so this cannot pass on a run that stored
    nothing: the merge is by code, and these two differ, so both survive as
    their own rows.
    """
    conn, _site, run_id = one_run
    _read(conn, run_id, "/blocked-drains", "h1-missing", "No H1 on the page.")
    _read(conn, run_id, "/hot-water", "description-missing", "No description.")

    stored = runs.expert_findings(conn, run_id)
    # The population, not only the absence: two pages were read, so two codes
    # must be reachable. Asserting "nothing was lost" against an empty list
    # would pass on a run that stored nothing at all.
    assert len(stored) >= 2, f"one page's findings were lost: {stored}"
    assert {f["check_id"] for f in stored} >= {"h1-missing",
                                               "description-missing"}


def test_a_second_page_does_not_overwrite_the_first_pages_report(one_run):
    """The half the operator reads. `INSERT OR REPLACE` against a key that
    did not carry the page meant the prose for `/blocked-drains` was gone;
    migration 0029 puts the page in the key."""
    conn, _site, run_id = one_run
    _read(conn, run_id, "/blocked-drains", "h1-missing", "No H1 on the page.")
    _read(conn, run_id, "/hot-water", "description-missing", "No description.")

    rows = conn.execute(
        "SELECT page_url, report FROM expert_reports WHERE run_id=?"
        " AND tool_id=?", (run_id, TOOL)).fetchall()
    assert len(rows) == 2, f"a paid page left no report: {[dict(r) for r in rows]}"
    assert {r["page_url"] for r in rows} == {
        "http://127.0.0.1/blocked-drains", "http://127.0.0.1/hot-water"}


def test_the_same_page_read_twice_still_replaces_rather_than_doubling(one_run):
    """Live counter-assertion, and the reason `page_url` must migrate to `''`
    rather than to NULL.

    SQLite treats NULLs in a primary key as distinct, so a NULL `page_url`
    inside the key would make `INSERT OR REPLACE` never replace again — a
    silent duplicate traded for a silent delete, the same class of defect
    facing the other way. Without this the fix above passes on code that
    simply stopped replacing anything.

    The findings assertion is the same guard for the other half: the page is
    the discriminator `record_expert_findings` merges by, so reading one page
    twice must replace that page's contribution rather than pool it with
    itself.
    """
    conn, _site, run_id = one_run
    _read(conn, run_id, "/hot-water", "h1-missing", "No H1.")
    _read(conn, run_id, "/hot-water", "h1-missing", "No H1.")

    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM expert_reports WHERE run_id=? AND tool_id=?",
        (run_id, TOOL)).fetchone()
    assert rows["n"] == 1
    assert len(runs.expert_findings(conn, run_id)) == 1


def test_a_site_scoped_brief_read_twice_still_replaces_itself(one_run):
    """The same counter-assertion for the site-scoped case, which is the one
    that migrates to `''` and is by far the commoner row."""
    conn, _site, run_id = one_run
    for _ in range(2):
        runs.record_expert_findings(
            conn, run_id, "crawl", "m-1",
            [{"severity": "high", "code": "sitemap-coverage",
              "summary": "22 absent", "affected_urls": []}])
        runs.store_expert_report(
            conn, run_id, "crawl",
            {"model": "m-1", "report": "r", "tokens": 100})

    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM expert_reports WHERE run_id=?"
        " AND tool_id='crawl'", (run_id,)).fetchone()
    assert rows["n"] == 1
    assert len(runs.expert_findings(conn, run_id)) == 1


def test_two_pages_raising_one_code_pool_into_a_single_row(one_run):
    """Q-23's answer, which is not "keep both" but *merge across pages by
    code* — and the distinction is the whole reason the answer was needed.

    The `EXP:` fingerprint is `(site, tool, code)` by deliberate design, so
    two rows carrying one code inside one run would fingerprint identically
    and `recompute_expert_states` would track one of them while the other sat
    invisible to the memory. Merging is what keeps one row per code true while
    both pages survive: the URLs pool, and the summaries join through
    `_merge_by_code`, exactly as they already did when a single call carried
    both pages.
    """
    conn, _site, run_id = one_run
    _read(conn, run_id, "/blocked-drains", "h1-missing", "No H1 here.")
    _read(conn, run_id, "/hot-water", "h1-missing", "No H1 on this one either.")

    stored = [f for f in runs.expert_findings(conn, run_id)
              if f["check_id"] == "h1-missing"]

    assert len(stored) == 1, f"one code, one row: {stored}"
    assert set(stored[0]["affected_urls"]) == {
        "http://127.0.0.1/blocked-drains", "http://127.0.0.1/hot-water"}
    # Both sentences, not the newest one wearing both URLs. A pooled URL list
    # over a single page's prose would say the second page exhibits something
    # the row never describes.
    assert "No H1 here." in stored[0]["summary"]
    assert "No H1 on this one either." in stored[0]["summary"]


def test_re_reading_one_page_withdraws_only_that_pages_contribution(one_run):
    """The discriminator, asserted where it can actually fail.

    A merged row is an accumulation across calls, so "replace rather than
    merge on a re-read" needs to know which parts came from the page being
    re-read. `record_expert_findings` keeps them per page in the row's own
    evidence; deriving them from `affected_urls` instead is what Q-23 costed
    as making that list load-bearing. Here `/blocked-drains` is read again and
    no longer raises `h1-missing`: its contribution must go, and
    `/hot-water`'s must not.
    """
    conn, _site, run_id = one_run
    _read(conn, run_id, "/blocked-drains", "h1-missing", "No H1 here.")
    _read(conn, run_id, "/hot-water", "h1-missing", "No H1 on this one either.")
    _read(conn, run_id, "/blocked-drains", "title-missing", "No title.")

    stored = {f["check_id"]: f for f in runs.expert_findings(conn, run_id)}

    assert set(stored) == {"h1-missing", "title-missing"}, stored
    # The re-read page's h1 claim is withdrawn; the other page's stands alone.
    assert stored["h1-missing"]["affected_urls"] == [
        "http://127.0.0.1/hot-water"]
    assert "No H1 here." not in stored["h1-missing"]["summary"]
    assert stored["title-missing"]["affected_urls"] == [
        "http://127.0.0.1/blocked-drains"]
