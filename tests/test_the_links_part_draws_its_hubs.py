"""The Links part draws its hubs and its site picture (item 271, row 6).

The prompt requires a `hubs` block ("The UI draws it"), the parser kept it,
and nothing in persistence, the API or the dashboard read it: the structure
the brief is organised around was paid for on every run and never shown.
The block now rides in the payload as `brief_hubs`, and Links declares a
site picture: the hubs, then how body inlinks and click depth fall across
the live pages, counted by `modules.links`' own rule.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import latest_view, repo, runs

HOST = "hubs.fixture"
BASE = f"https://{HOST}"
AT = "2026-10-05T00:00:00+00:00"
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def _page(path, links, depth, status=200):
    return {"url": BASE + path, "status": status, "content_type": "text/html",
            "title": path, "click_depth": depth,
            "links": [{"url": BASE + t, "anchor": "a", "region": r} for t, r in links]}


def test_the_site_picture_counts_by_the_modules_rule(tmp_path):
    conn = connect(tmp_path / "hubs.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Hubs Co"), HOST)
    run = runs.create_run(conn, site_id, ["LNK"], "T2")
    runs.store_evidence(conn, run, {"start_url": BASE + "/", "pages": [
        # Nav links count for nothing; the error page links count for nothing.
        _page("/", [("/a", "nav"), ("/a", "body"), ("/b", "body")], 0),
        _page("/a", [("/b", "body"), ("/c", "footer")], 1),
        _page("/b", [("/a", "body")], 1),
        _page("/c", [], 2),
        _page("/gone", [("/c", "body"), ("/c", "body")], 1, status=404),
    ]})
    runs.mark_complete(conn, run, AT)
    latest_view.rebuild(conn, site_id, "test: a small graph")
    got = runs.links_site_payload(conn, site_id)
    assert got["pages"] == 4 and got["counted"] == 3 and got["minimum"] == 3, got
    bands = {b["band"]: b["pages"] for b in got["inlinks"]}
    # /a has 2 body inlinks (from / and /b), /b has 2, /c has 0.
    assert bands == {"0": 1, "1": 0, "2": 2, "3 to 4": 0, "5 or more": 0}, bands
    assert got["depth"] == [{"depth": "0", "pages": 1}, {"depth": "1", "pages": 2},
                            {"depth": "2", "pages": 1}], got["depth"]
    conn.close()


def test_the_hubs_block_rides_in_the_payload_and_is_drawn():
    import inspect
    src = inspect.getsource(runs.anatomy_view)
    assert '("fixes", brief_fixes), ("hubs", brief_hubs)' in src
    assert '"brief_hubs": brief_hubs.get(c.key, []),' in src
    page = SRC.read_text(encoding="utf-8")
    assert "links: { now: LinksNow, siteNow: LinksSiteNow," in page
    block = page.split("function LinksSiteNow", 1)[1].split("\n}\n", 1)[0]
    assert "<th className=\"num\">Spokes linking up</th>" in block


def test_a_page_at_the_link_cap_is_said():
    import inspect
    src = inspect.getsource(runs.links_site_payload)
    assert 'capped = sum(1 for p in pages if len(p.get("links") or []) >= LINK_DETAIL_CAP)' in src
    page = SRC.read_text(encoding="utf-8")
    assert "Body links are counted from the first {site.cap} links stored per page" in page
