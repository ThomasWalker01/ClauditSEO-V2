"""The skip picture reads the pages the checks read (item 268, row 5).

The picture counted 14 pages skipping a level and the record 12, both on the
29 Sept T2 crawl. The audit read it as two fields (`outline` against
`headings`). Read against the stored crawl, the two agreed on every page:
the difference was two 404s, `/on-page-seo/` and
`/post-seo/on-page-seo/image-optimization/`. The check leaves a page that
answered an error out (item 227), and the picture read it. The picture now
leaves it out and names it.
"""

from __future__ import annotations

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

HOST = "skip.fixture"
BASE = f"https://{HOST}"
AT = "2026-10-05T00:00:00+00:00"
SKIP = [[1, "Title"], [3, "Jumped"]]


def test_an_error_page_is_named_and_not_counted(tmp_path):
    conn = connect(tmp_path / "skip.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Skip Co"), HOST)
    run = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run, {"start_url": BASE + "/", "pages": [
        {"url": BASE + "/", "status": 200, "content_type": "text/html", "headings": SKIP},
        {"url": BASE + "/gone/", "status": 404, "content_type": "text/html", "headings": SKIP},
    ]})
    runs.mark_complete(conn, run, AT)
    got = runs.heading_shapes_payload(conn, run)
    assert got["errored"] == [BASE + "/gone/"], got
    assert BASE + "/gone/" not in got["at"] and BASE + "/" in got["at"], got["at"]
    assert got["not_checked"] == [], got
    conn.close()
