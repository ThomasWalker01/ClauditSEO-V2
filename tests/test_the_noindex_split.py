"""noindex-page split into noindex-linked + noindex-in-sitemap (item 137,
brief v18 step BA, channel 20260910-1430).

`noindex-page` fired one HIGH blocker on any noindex page and claimed
"internally linked" without checking. The split fires by what is true:

  - a noindex page linked from >= 3 pages -> noindex-linked, HIGH, blocker;
  - a noindex page merely in the sitemap -> noindex-in-sitemap, LOW;
  - a noindex page that is neither -> nothing (the false HIGH removed).

Held here: the emitter fires the right check for each shape; the blocker verdict
moved to noindex-linked and redirect-chain left it (the two BA reconciliations
push the triage ranking in opposite directions, so both are checked); and
migration 0049 re-homes stored noindex-page rows the same way, carrying
finding_states and retiring the stray.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.checks import blocker_checks, is_blocker
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Tier, fingerprint
from clauditseo.modules.tec import TechnicalModule
from clauditseo.persistence import repo, runs

_NOINDEX_HTML = ('<html><head><meta name="robots" content="noindex, follow">'
                 "</head><body>hidden</body></html>")
_OK_HTML = "<html><head><title>A linker page here</title></head><body>x</body></html>"


def _page(path, content=_OK_HTML, outlinks=()):
    url = f"https://x.test{path}"
    return Page(url=url, requested_url=url, status=200, content=content,
                content_type="text/html", outlinks=list(outlinks))


# ---- the emitter -----------------------------------------------------------

def _noindex_findings(crawl):
    out = TechnicalModule().run(crawl.pages, Tier.T2, {"crawl": crawl})
    return {f.check_id: f for f in out
            if f.check_id in ("noindex-linked", "noindex-in-sitemap")}


def test_a_linked_noindex_page_is_noindex_linked_high():
    target = "https://x.test/hidden"
    crawl = CrawlResult(
        start_url="https://x.test/", tier=Tier.T2,
        pages=[_page("/hidden", content=_NOINDEX_HTML),
               _page("/a", outlinks=[target]),
               _page("/b", outlinks=[target]),
               _page("/c", outlinks=[target])])
    hits = _noindex_findings(crawl)
    assert "noindex-linked" in hits, hits
    assert hits["noindex-linked"].severity.value == "high"
    assert "noindex-in-sitemap" not in hits   # not in any sitemap


def test_a_sitemap_only_noindex_page_is_noindex_in_sitemap_low():
    crawl = CrawlResult(
        start_url="https://x.test/", tier=Tier.T2,
        pages=[_page("/hidden", content=_NOINDEX_HTML)],   # no inlinks
        sitemap_entries=["https://x.test/hidden"])
    hits = _noindex_findings(crawl)
    assert "noindex-in-sitemap" in hits, hits
    assert hits["noindex-in-sitemap"].severity.value == "low"
    assert "noindex-linked" not in hits


def test_a_stray_noindex_page_fires_neither():
    # noindex, one inlink, not in the sitemap — the false HIGH the split removes.
    target = "https://x.test/hidden"
    crawl = CrawlResult(
        start_url="https://x.test/", tier=Tier.T2,
        pages=[_page("/hidden", content=_NOINDEX_HTML),
               _page("/a", outlinks=[target])])
    assert _noindex_findings(crawl) == {}


# ---- the blocker verdict, both directions ----------------------------------

def test_the_blocker_moved_to_noindex_linked_and_redirect_chain_left_it():
    assert is_blocker("TEC/noindex-linked")
    assert "TEC/noindex-linked" in blocker_checks()
    # noindex-in-sitemap is a LOW observation, never a blocker.
    assert not is_blocker("TEC/noindex-in-sitemap")
    # The retired id no longer blocks.
    assert "TEC/noindex-page" not in blocker_checks()
    assert not is_blocker("TEC/noindex-page")
    # Decision A's half: redirect-chain is no longer a blocker. The two moves
    # push a triage ranking in opposite directions, so a site with both a
    # linked noindex and a redirect chain must rank the first as a blocker and
    # the second not.
    assert not is_blocker("TEC/redirect-chain")


# ---- migration 0049 --------------------------------------------------------

_MIG = (Path(__file__).resolve().parent.parent / "clauditseo" / "db"
        / "migrations" / "0049_noindex_page_split.py")


def _apply_0049(conn):
    spec = importlib.util.spec_from_file_location("mig_0049", _MIG)
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


def _seed(conn, site_id, path, inlink_sources, in_sitemap):
    """A stored noindex-page finding on `path`, with a run whose evidence gives
    it `inlink_sources` distinct linkers and optional sitemap membership."""
    url = f"https://x.test{path}"
    pages = [{"url": url, "status": 200, "content_type": "text/html", "outlinks": []}]
    for i in range(inlink_sources):
        pages.append({"url": f"https://x.test/link{i}", "status": 200,
                      "content_type": "text/html", "outlinks": [url]})
    ev = {"start_url": "https://x.test/", "pages": pages,
          "sitemap_entries": [url] if in_sitemap else []}
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete', crawl_evidence=? WHERE id=?",
                 (json.dumps(ev), run_id))
    fp = fingerprint("TEC", "noindex-page", path)
    from clauditseo.persistence.repo import create_id, now_iso
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
        " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'TEC',"
        " 'noindex-page', 'high', 'deterministic', ?, ?, ?, ?)",
        (create_id(), run_id, "noindex", json.dumps([url]), fp, now_iso()))
    conn.execute(
        "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
        " updated_at) VALUES (?, ?, 'accepted-risk', ?, ?)", (site_id, fp, run_id, now_iso()))
    return fp


def test_0049_rehomes_a_linked_row_and_carries_its_state(seeded):
    conn, site_id = seeded
    old = _seed(conn, site_id, "/hidden", inlink_sources=3, in_sitemap=False)
    _apply_0049(conn)
    row = conn.execute("SELECT check_id, severity, fingerprint FROM findings"
                       " WHERE fingerprint=?",
                       (fingerprint("TEC", "noindex-linked", "/hidden"),)).fetchone()
    assert row is not None and row["check_id"] == "noindex-linked"
    assert row["severity"] == "high"
    assert conn.execute("SELECT COUNT(*) c FROM finding_states WHERE fingerprint=?",
                        (old,)).fetchone()["c"] == 0
    st = conn.execute("SELECT state FROM finding_states WHERE fingerprint=?",
                      (fingerprint("TEC", "noindex-linked", "/hidden"),)).fetchone()
    assert st["state"] == "accepted-risk"


def test_0049_drops_to_low_for_a_sitemap_only_row(seeded):
    conn, site_id = seeded
    _seed(conn, site_id, "/hidden", inlink_sources=0, in_sitemap=True)
    _apply_0049(conn)
    row = conn.execute("SELECT check_id, severity FROM findings"
                       " WHERE check_id='noindex-in-sitemap'").fetchone()
    assert row is not None and row["severity"] == "low"


def test_0049_retires_a_stray_row_and_its_state(seeded):
    conn, site_id = seeded
    old = _seed(conn, site_id, "/hidden", inlink_sources=1, in_sitemap=False)
    _apply_0049(conn)
    assert conn.execute("SELECT COUNT(*) c FROM findings").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM finding_states WHERE fingerprint=?",
                        (old,)).fetchone()["c"] == 0
