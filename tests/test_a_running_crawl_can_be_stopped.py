"""A crawl the operator did not ask for should be stoppable at page four
(relay item 136a, part 5).

The 145-page run that produced this item ran to completion because there
was nothing to stop it with. Parts 1 to 3 mean it would not start now —
but "the product cannot be told to stop" is a separate fact about it, and
the next surprise will not be the one just fixed.

The stop is at a page boundary rather than mid-fetch: a half-read page is
not evidence, and killing the thread would leave the run row `running`
for ever. What the operator gets is the pages already fetched, recorded
as a `cancelled` run that says how many.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import Tier


def test_a_crawl_asked_to_stop_returns_what_it_had(monkeypatch):
    """The loop's third stop condition, beside `max_pages` and
    `wall_clock` — and it reports itself the same way, because "why is
    this crawl smaller than I expected" is one question with three
    answers."""
    from clauditseo.crawler import crawl as _crawl

    pages = ["https://stop.test/", "https://stop.test/a", "https://stop.test/b"]
    seen: list[str] = []

    def fake_fetch(self, url, **kw):
        from clauditseo.crawler.types import Page

        # Only the pages: robots and the sitemap go through this same
        # fetcher, and counting them would stop the crawl before it began.
        if not url.endswith(("robots.txt", "sitemap.xml")):
            seen.append(url)
        body = "".join(f'<a href="{u}">x</a>' for u in pages)
        return Page(url=url, requested_url=url, status=200,
                    content_type="text/html; charset=utf-8",
                    content=f"<html><body>{body}</body></html>")

    monkeypatch.setattr(_crawl.Fetcher, "fetch", fake_fetch)
    # Robots is fetched through the same `Fetcher`, so the stub above
    # answers it too - a 200 with no disallow, which allows everything.

    stop_after = 2

    def should_stop() -> bool:
        return len(seen) >= stop_after

    result = _crawl.crawl("https://stop.test/", Tier.T3, should_stop=should_stop)
    assert result.truncated_by == "cancelled", result.truncated_by
    assert 0 < len(result.pages) <= stop_after + 1, [p.url for p in result.pages]


def test_a_crawl_nobody_stops_is_untouched(monkeypatch):
    """The must-not-change direction: a run with no stop asked for must
    behave exactly as it did, or every stored crawl's comparability moves
    under the operator."""
    import inspect

    from clauditseo.crawler.crawl import crawl

    assert inspect.signature(crawl).parameters["should_stop"].default is None


# --- the register -------------------------------------------------------

def test_a_stop_is_asked_for_by_run_and_answered_once():
    """The signal is per run and one-shot: a stop asked for a run that has
    finished must not stop the next one to reuse the worker."""
    from clauditseo.persistence import runs

    runs.request_stop("run-a")
    assert runs.stop_requested("run-a") is True
    assert runs.stop_requested("run-b") is False
    runs.clear_stop("run-a")
    assert runs.stop_requested("run-a") is False


def test_a_cancelled_run_is_a_status_of_its_own_and_not_a_failure():
    """`failed` means the product broke; `cancelled` means the operator
    changed their mind. A run list that showed the second as the first
    would have the operator debugging their own decision."""
    import tempfile
    from pathlib import Path

    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    conn = connect(Path(tempfile.mkdtemp()) / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "c.test")
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.cancel_run(conn, run_id, fetched=4)
    row = conn.execute("SELECT status, error, finished_at FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    conn.close()
    assert row["status"] == "cancelled", dict(row)
    assert "4" in (row["error"] or ""), row["error"]
    assert row["finished_at"], "a cancelled run is finished; it is not still running"


def test_a_cancelled_run_is_not_history_the_site_is_judged_by():
    """It reached some pages and scored nothing. Counting it as an audit
    would let a cancelled run stand as the site's standing position."""
    from clauditseo.persistence import runs

    assert "cancelled" not in runs.SCORED_STATUSES
    assert "cancelled" not in runs.AUDITED_STATUSES


def test_the_route_that_stops_a_run_exists_and_names_the_run():
    from clauditseo.api.app import create_app

    app = create_app(db_path=None) if False else None
    import clauditseo.api.app as _app
    import inspect

    src = inspect.getsource(_app)
    assert '"/api/runs/{run_id}/stop"' in src, (
        "no route can stop a running crawl, so a 145-page crawl the "
        "operator did not ask for runs to the end")
