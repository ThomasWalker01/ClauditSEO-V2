"""Item 239 step 2: each crawl-relative section reads its reference crawl
from the Latest View, not the audit the picker holds.

On twenty22 the picker held the ONP-only T2 of 23 Sept, which weighed no
images: the Images part's scatter read it and drew nothing - the "blank
Images chart". A section now reads the newest reading of the whole site that
measured it, with the instrument it needs: Images the newest that weighed
images (T3), the crawl, URLs and indexability blocks TEC's (T3), and the
provenance line the same run. The picked audit changes none of them.

The fixture is `test_the_latest_view`'s: T1, T3 (images weighed), a
one-page refresh, and an ONP-only T2.
"""

from __future__ import annotations

import httpx
import pytest

from tests.test_the_latest_view import _history
from tests.test_triage_ranks_the_section_rail import _serve


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    server, thread, db, base = _serve("refcrawl")
    try:
        from clauditseo.db.connection import connect
        from clauditseo.persistence import latest_view
        # Built beside, then moved in: `_history` makes its own site, so the
        # served database gets the same four runs by a rebuild of a copy.
        conn, site, ids = _history(tmp_path_factory.mktemp("h"), "h")
        live = connect(db)
        conn.backup(live)
        live.close()
        conn.close()
        yield base, site, {v: k for k, v in ids.items()}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    _ = latest_view


def _parts(base, site, run=None):
    params = {"run_id": run} if run else {}
    view = httpx.get(f"{base}/api/sites/{site}/anatomy", params=params, timeout=60).json()
    return {c["key"]: c for c in view["categories"]}


def test_the_images_part_reads_the_run_that_weighed_images(served):
    base, site, run = served
    for picked in (None, run["T2"]):
        images = _parts(base, site, picked)["images"]["images"]
        assert images and images["measured"] is True, (picked, images)
        assert images["tier"] == "T3", images


def test_the_provenance_line_names_the_reference_crawl_whatever_is_picked(served):
    base, site, run = served
    for picked in (None, run["T2"], run["T1"]):
        parts = _parts(base, site, picked)
        assert parts["urls"]["sweep_run"]["run_id"] == run["T3"], picked
        assert parts["title-desc"]["sweep_run"]["run_id"] == run["T2"], picked


def test_the_crawl_blocks_read_tecs_reference(served):
    base, site, run = served
    crawl = _parts(base, site, run["T2"])["crawl"]
    assert crawl["crawl_now"]["run_id"] == run["T3"], crawl.get("crawl_now")
