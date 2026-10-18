"""The model's raw answer is kept beside what the reader made of it (item 148,
migration 0055).

The first real International run on Acme met a reader with three defects,
and the stored `report` and `contract` were already the parse - the fenced
block was gone - so the only way to a correct contract was a second paid run.
"""

from __future__ import annotations

import dataclasses

from clauditseo.analysts.expert import run_expert
from clauditseo.config import Settings
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.evidence import snapshot
from clauditseo.engine.types import Site, Tier
from tests.test_expert_tools import StubExpert
from tests.test_figure_cap_declares_what_it_withheld import FAST, _db, brief_site  # noqa: F401

REPORT = ("## CRAWL HEALTH SUMMARY\n\nOne page was crawled.\n\n"
          "```json\n{\"findings\": []}\n```\n")


def _raw(conn, run_id):
    return conn.execute("SELECT raw FROM expert_reports WHERE run_id=? AND"
                        " tool_id='crawl'", (run_id,)).fetchone()[0]


def test_the_raw_answer_is_stored_before_any_parser_touches_it(tmp_path, brief_site):
    ev = snapshot(crawl(brief_site.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    try:
        out = run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
                         cfg, StubExpert(REPORT), use_cache=False)
        assert out["status"] == "ok", out
        assert _raw(conn, run_id) == REPORT
    finally:
        conn.close()


def test_a_cached_replay_still_stores_the_raw_answer(tmp_path, brief_site):
    """The payload is what `analyst_cache` replays, so raw rides in it: kept
    beside the payload, a replay would store NULL and a reader defect on a
    replayed brief would be a paid re-run again."""
    ev = snapshot(crawl(brief_site.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    try:
        run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
                   cfg, StubExpert(REPORT))
        conn.execute("UPDATE expert_reports SET raw=NULL WHERE run_id=?", (run_id,))
        conn.commit()
        second = run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
                            cfg, StubExpert(REPORT))
        assert second["cached"] is True, second
        assert _raw(conn, run_id) == REPORT
    finally:
        conn.close()
