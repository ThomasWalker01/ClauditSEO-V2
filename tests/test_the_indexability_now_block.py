"""Indexability & canonicals' site-level "now" (item 137, brief v18 step BA).

The canonical map and the headline counts are read off one stored run's crawl
evidence; `indexability_now_payload` is the reader. Held here:

  - each reached page lands in exactly one canonical bucket (self · elsewhere→
    200 · elsewhere→404 · missing), so the four sum to `reached`;
  - `conflicts_sitemap` is a cross-cut — a sitemap-listed page whose canonical
    points elsewhere — not a fifth partition member;
  - a canonical target the crawl reached with a 4xx is `elsewhere_404`; a
    target it never saw is counted optimistically as `elsewhere_200`, because
    inventing a 404 for an unseen page is the fabrication the brief forbids;
  - `indexable` is a reached 200 that owns its own indexation and is not
    noindex; `noindex` reads meta robots or X-Robots-Tag;
  - a redirect's per-hop shape (`temporary`, `to_404`) is null — not decidable
    from a stored crawl — while the chain count is exact.
"""

from __future__ import annotations

import json

import pytest

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


@pytest.fixture
def seeded(tmp_path):
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    yield conn, site_id
    conn.close()


def _page(path, status=200, canonical="self", meta_robots=None, redirect_chain=None):
    url = f"https://x.test{path}"
    canon = url if canonical == "self" else canonical
    return {"url": url, "status": status, "content_type": "text/html",
            "canonical": None if canonical is None else canon,
            "meta_robots": meta_robots, "x_robots_tag": None,
            "redirect_chain": redirect_chain or []}


def _run(conn, site_id, pages, sitemap_entries=None):
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run_id,))
    ev = {"start_url": "https://x.test/", "pages": pages,
          "sitemap_entries": sitemap_entries or []}
    conn.execute("UPDATE audit_runs SET crawl_evidence=? WHERE id=?",
                 (json.dumps(ev), run_id))
    return run_id


def test_the_canonical_buckets_partition_the_reached_pages(seeded):
    conn, site_id = seeded
    run_id = _run(conn, site_id, [
        _page("/"),                                     # self
        _page("/a"),                                    # self
        _page("/b", canonical="https://x.test/a"),      # elsewhere -> /a (200)
        _page("/dead", status=404),                     # a 404 target for /c
        _page("/c", canonical="https://x.test/dead"),   # elsewhere -> 404
        _page("/d", canonical=None),                    # missing
    ])
    p = runs.indexability_now_payload(conn, run_id)
    assert p["reached"] == 5, p        # the 404 is attempted, not reached
    m = p["canonical_map"]
    assert m["self"] == 2, m
    assert m["elsewhere_200"] == 1, m
    assert m["elsewhere_404"] == 1, m
    assert m["missing"] == 1, m
    # The four buckets partition the reached pages.
    assert m["self"] + m["elsewhere_200"] + m["elsewhere_404"] + m["missing"] == p["reached"]
    assert p["canonical_elsewhere"] == 2, p


def test_an_unseen_canonical_target_is_counted_optimistically(seeded):
    conn, site_id = seeded
    # /x's canonical points at a page the crawl never fetched: not a proven
    # 404, so it is elsewhere_200, not elsewhere_404.
    run_id = _run(conn, site_id, [_page("/x", canonical="https://x.test/never-seen")])
    m = runs.indexability_now_payload(conn, run_id)["canonical_map"]
    assert m["elsewhere_200"] == 1 and m["elsewhere_404"] == 0, m


def test_noindex_and_indexable(seeded):
    conn, site_id = seeded
    run_id = _run(conn, site_id, [
        _page("/keep"),                                          # indexable
        _page("/hide", meta_robots="noindex, follow"),           # noindex
        _page("/canon", canonical="https://x.test/keep"),        # not indexable (elsewhere)
    ])
    p = runs.indexability_now_payload(conn, run_id)
    assert p["noindex"] == 1, p
    # Only the self/missing 200 that is not noindex is indexable.
    assert p["indexable"] == 1, p


def test_conflicts_sitemap_is_a_cross_cut(seeded):
    conn, site_id = seeded
    # /p is in the sitemap but canonicalises elsewhere — a conflict, and also
    # an elsewhere_200; the two counts are not exclusive.
    run_id = _run(conn, site_id,
                  [_page("/p", canonical="https://x.test/q"), _page("/q")],
                  sitemap_entries=["https://x.test/p"])
    m = runs.indexability_now_payload(conn, run_id)["canonical_map"]
    assert m["conflicts_sitemap"] == 1, m
    assert m["elsewhere_200"] == 1, m


def test_redirect_chains_are_counted_but_per_hop_shape_is_not(seeded):
    conn, site_id = seeded
    run_id = _run(conn, site_id, [
        _page("/one", redirect_chain=["https://x.test/old"]),                     # 1 hop
        _page("/two", redirect_chain=["https://x.test/a", "https://x.test/b"]),   # 2 hops
    ])
    r = runs.indexability_now_payload(conn, run_id)["redirects"]
    assert r["total"] == 2, r
    assert r["chains"] == 1, r          # only the two-hop one
    assert r["temporary"] is None and r["to_404"] is None, r


def test_the_convention_is_the_majority_of_reached_200s(seeded):
    conn, site_id = seeded
    run_id = _run(conn, site_id, [_page("/a/"), _page("/b/"), _page("/c")])
    c = runs.indexability_now_payload(conn, run_id)["convention"]
    assert c["scheme"] == "https" and c["host"] == "x.test"
    assert c["trailing_slash"] is True   # two of three end in a slash


def test_no_run_reads_nothing(seeded):
    conn, _ = seeded
    assert runs.indexability_now_payload(conn, None) is None
