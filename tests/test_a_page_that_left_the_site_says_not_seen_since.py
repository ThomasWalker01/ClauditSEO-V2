"""A page that has left the site says "not seen since", not an age (item 243,
item 239 amendment 6).

Step 6 dates every item from the run that measured it, so a page that is
gone kept its last reading and aged towards "out of date", as if it were a
page nobody had re-checked. The two are told apart by each reference crawl's
fetched set and sitemap, against the previous reference crawl's:

  - `/old/`: the first crawl fetched it, the second neither fetched it nor
    lists it in its sitemap. It reads "not seen since <first crawl's date>"
    and carries no age tone, and is no part of the part's date range.
  - `/kept/`: the second crawl did not fetch it, but its sitemap still lists
    it. Not gone - just not re-read - so it keeps its age.
  - Nothing on `/old/` changes state: its finding stays open until the
    operator moves it.
  - A crawl that stopped short (`truncated_by`) marks nothing gone, and a
    rebuild derives the same record as the live writes.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import latest_view, repo, runs
from clauditseo.persistence.repo import create_id
from tests.needs_build import needs_build

HOST = "gone.fixture"
BASE = f"https://{HOST}"
FIRST, SECOND = "2026-09-18T00:00:00+00:00", "2026-09-23T00:00:00+00:00"

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


def _page(path: str, title: str) -> dict:
    return {"url": BASE + path, "status": 200, "content_type": "text/html", "title": title,
            "meta_description": f"{title} description", "h1": [title]}


def _crawl(conn, site_id: str, at: str, paths: list[str], listed: list[str],
           truncated_by: str | None = None) -> str:
    run = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run, {
        "start_url": BASE + "/", "truncated_by": truncated_by,
        "pages": [_page(p, f"{p} on {at[:10]}") for p in paths],
        "sitemaps": [{"url": BASE + "/sitemap.xml", "status": 200, "is_index": False}],
        "sitemap_entries": [BASE + p for p in listed],
        "sitemap_entry_total": len(listed)})
    runs.mark_complete(conn, run, at)
    conn.execute("UPDATE audit_runs SET started_at=?, finished_at=?, composite_score=70"
                 " WHERE id=?", (at, at, run))
    conn.commit()
    return run


def _site(conn, name: str = "Gone Co") -> str:
    op = repo.ensure_default_operator(conn)
    return repo.create_site(conn, repo.create_client(conn, op, name), HOST)


def _plant(conn, site_id: str, *, truncated: bool = False) -> None:
    first = _crawl(conn, site_id, FIRST, ["/", "/old/", "/kept/"], ["/", "/old/", "/kept/"])
    # One open finding on the page that is about to leave.
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'ONP',"
            " 'title-missing', 'medium', 'deterministic', 'No title', ?, 'fp-old', ?, '{}')",
            (create_id(), first, json.dumps([BASE + "/old/"]), FIRST))
    _crawl(conn, site_id, SECOND, ["/"], ["/", "/kept/"],
           truncated_by="max_pages" if truncated else None)
    latest_view.rebuild(conn, site_id, "test: two reference crawls")


@pytest.fixture()
def planted(tmp_path):
    conn = connect(tmp_path / "gone.db")
    migrate(conn)
    site_id = _site(conn)
    _plant(conn, site_id)
    yield conn, site_id
    conn.close()


def test_a_page_the_newest_crawl_neither_fetched_nor_lists_is_gone(planted):
    conn, site_id = planted
    assert latest_view.gone(conn, site_id, "ONP") == {"/old/": FIRST}
    # Listed but not re-read is not gone; fetched is not gone.
    parts = {c["key"]: c for c in runs.anatomy_view(conn, site_id, BASE + "/old/")["categories"]}
    assert parts["title-desc"]["gone_since"] == FIRST, parts["title-desc"]["gone_since"]
    for path in ("/kept/", "/"):
        parts = {c["key"]: c for c in runs.anatomy_view(conn, site_id, BASE + path)["categories"]}
        assert parts["title-desc"]["gone_since"] is None, (path, parts["title-desc"]["gone_since"])
    # The page keeps its last reading, and says it has left.
    facts = runs.page_facts(conn, site_id, BASE + "/old/")
    assert facts["title"] == "/old/ on 2026-09-18" and facts["gone"] == {"ONP": FIRST}, facts


def test_a_gone_page_is_no_part_of_the_parts_date_range(tmp_path):
    """Here `/old/` is the only page older than the second crawl, so the
    range says whether it was counted: it would start on 18 Sept."""
    conn = connect(tmp_path / "range.db")
    migrate(conn)
    site_id = _site(conn)
    _crawl(conn, site_id, FIRST, ["/", "/old/"], ["/", "/old/"])
    _crawl(conn, site_id, SECOND, ["/"], ["/"])
    parts = {c["key"]: c for c in runs.anatomy_view(conn, site_id)["categories"]}
    rng = parts["title-desc"]["measured_range"]
    assert rng["from"] == SECOND and rng["to"] == SECOND, rng
    conn.close()


def test_nothing_on_a_gone_page_changes_state_by_itself(planted):
    conn, site_id = planted
    state = conn.execute("SELECT state FROM finding_states WHERE site_id=? AND fingerprint='fp-old'",
                         (site_id,)).fetchone()
    assert state and state["state"] == "open", dict(state) if state else None


def test_a_crawl_that_stopped_short_marks_nothing_gone(tmp_path):
    conn = connect(tmp_path / "short.db")
    migrate(conn)
    site_id = _site(conn)
    _plant(conn, site_id, truncated=True)
    assert latest_view.gone(conn, site_id) == {}
    conn.close()


def test_a_rebuild_derives_the_same_presence_as_the_live_writes(tmp_path):
    conn = connect(tmp_path / "live.db")
    migrate(conn)
    site_id = _site(conn)
    _crawl(conn, site_id, FIRST, ["/", "/old/"], ["/", "/old/"])
    _crawl(conn, site_id, SECOND, ["/"], ["/"])
    # `mark_complete` applied each run live; the rebuild replays them.
    live = latest_view.gone(conn, site_id)
    latest_view.rebuild(conn, site_id, "test: replay")
    assert live == latest_view.gone(conn, site_id) == {"/old/": FIRST}
    conn.close()


# --- on screen --------------------------------------------------------------

@pytest.fixture(scope="module")
def served():
    from tests.test_triage_ranks_the_section_rail import _serve
    server, thread, db, base = _serve("gone")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Gone Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": HOST}, timeout=30).json()
        conn = connect(db)
        _plant(conn, site["id"])
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _prov(browser, base, site_id, path):
    from urllib.parse import quote
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=title-desc"
                f"&page={quote(BASE + path, safe='')}", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".part-prov .prov-line .age", timeout=30_000)
        return pg.evaluate("""() => {
          const age = document.querySelector('.part-prov .prov-line .age');
          return {text: age.textContent.replace(/\\s+/g, ' ').trim(), tone: age.dataset.age,
                  classes: [...age.classList],
                  note: (document.querySelector('.prov-gone')?.textContent || '')
                          .replace(/\\s+/g, ' ').trim()};
        }""")
    finally:
        pg.close()


@NEEDS_BROWSER
@needs_build
def test_the_gone_page_reads_not_seen_since_and_a_listed_one_keeps_its_age(browser, served):
    base, site_id = served
    old = _prov(browser, base, site_id, "/old/")
    assert old["text"] == "not seen since 18 Sept", old
    assert old["tone"] == "gone" and not any(c.startswith("tone-") for c in old["classes"]), old
    assert "left the site" in old["note"] and "18 Sept" in old["note"], old
    kept = _prov(browser, base, site_id, "/kept/")
    assert kept["tone"] != "gone" and kept["text"].startswith("measured"), kept
    assert kept["note"] == "", kept
