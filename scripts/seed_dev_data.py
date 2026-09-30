"""Fill an empty database with runs covering the cases that keep going wrong.

After `reset_audit_data.py --apply`, or after the database is deleted and
rebuilt from migrations, there is nothing to look at: every screen renders its
empty state and no code path that depends on stored history can be exercised
by hand. This puts back a small set chosen for coverage rather than realism.

    python scripts/seed_dev_data.py                 # report only
    python scripts/seed_dev_data.py --apply         # write it

What it seeds, and why each one is here:

  normal   a crawl that fetched pages — the ordinary case everything else is
           compared against.
  blocked  **a crawl that fetched nothing, via a robots.txt that answers 503.**
           `RobotsPolicy` treats 5xx as deny-all, so the crawler declines every
           URL and the run stores as `blocked` rather than `complete`. Reached
           through the real crawler on purpose: a hand-built `CrawlResult` with
           `pages=[]` would assert the shape without exercising the path that
           produces it.
  partial  a crawl under a tight page budget. Note that this does NOT produce
           coverage between 0 and 1: `page_coverage` is deliberately binary —
           "did we see the site", not "did we see all of it" — so a truncated
           crawl still reports 1.0. Partial coverage comes from the provider
           split instead, and appears on every keyless run as `PRF=0.4` (lab
           timings measured, field data dark) and `OFP=0.0`.

A deliverable is written for each run that can have one. The blocked run
cannot have a *client* one: `generate()` refuses that, so the script prints
the refusal instead, which is what an operator meets and is worth seeing in
the output. Its internal document does generate — that is WF-05's fix — and
the operator reaches it from the run screen rather than from here.

  A specialist brief is attached to the normal run. **It is synthesised here,
  not written by a model** — no provider is called and nothing is spent, so it
  is a brief in shape, storage and provenance but carries none of a model's
  judgement. Its findings are fixed strings chosen to exercise the renderer
  (one carrying a figure, so the honesty gate sees a number needing a source
  tag). For a real one, `scripts/run_golden.py --spend` costs money and says
  so before spending it.

Not a test fixture. Tests build their own databases in `tmp_path`; this exists
for looking at the app with your eyes. It imports the fixture HTTP server from
`tests/`, so it runs from a dev checkout and not from an installed wheel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clauditseo.modules  # noqa: E402,F401  (registers the dimensions)
from clauditseo.config import settings                      # noqa: E402
from clauditseo.crawler.crawl import crawl                   # noqa: E402
from clauditseo.crawler.evidence import snapshot             # noqa: E402
from clauditseo.crawler.types import TierBudget              # noqa: E402
from clauditseo.db.connection import connect                 # noqa: E402
from clauditseo.db.migrate import migrate                    # noqa: E402
from clauditseo.engine.core import run_audit                 # noqa: E402
from clauditseo.engine.types import Site, Tier               # noqa: E402
from clauditseo.persistence import repo, runs                # noqa: E402
from clauditseo.reporting import generate as gen             # noqa: E402

#: Every dimension, so the seed exercises the coverage arithmetic across all
#: of them rather than the handful a narrower list would reach.
DIMS = ["TEC", "ONP", "PRF", "CNT", "OFP", "LOC", "AIS"]

FULL = TierBudget(max_pages=25, request_timeout_s=5, wall_clock_s=60, delay_s=0)
TIGHT = TierBudget(max_pages=2, request_timeout_s=5, wall_clock_s=60, delay_s=0)

#: robots.txt answers 503. Not a `Disallow: /` — either produces a blocked
#: run, but a 5xx is the case an operator cannot see from the site's own
#: configuration and is the one worth having in front of you.
BLOCKED_ROUTES = {
    "/robots.txt": (503, {"Content-Type": "text/plain"}, "upstream unavailable"),
    "/": (200, {}, "<html lang=en><head><title>Blocked</title></head>"
                   "<body><main><h1>Nothing may crawl this</h1>"
                   "<p>robots.txt is answering 503.</p></main></body></html>"),
}

#: Fixed strings, not a model's output. One carries a figure so the briefs
#: table exercises the honesty gate's source-tag rule.
SEEDED_BRIEF = [
    {"severity": "high", "code": "sitemap-coverage",
     "summary": "22 indexable pages are absent from the sitemap.",
     "affected_urls": ["http://seed-normal.test/"]},
    {"severity": "medium", "code": "thin-service-pages",
     "summary": "3 service pages are under 300 words.", "affected_urls": []},
]


def _audit(conn, site_id: str, domain: str, routes: dict, budget: TierBudget) -> tuple:
    """One audit through the real crawler against a fixture on 127.0.0.1."""
    from tests.conftest import FixtureSite

    server = FixtureSite(routes).start()
    try:
        crawled = crawl(server.base_url + "/", Tier.T2, budget=budget)
    finally:
        server.stop()
    result = run_audit(Site(domain=domain, business_type="local-service"),
                       crawled, DIMS, Tier.T2)
    run_id = runs.create_run(conn, site_id, DIMS, "T2")
    runs.store_evidence(conn, run_id, snapshot(crawled))
    runs.complete_run(conn, run_id, result)
    return run_id, result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write (default is to report only)")
    ap.add_argument("--db", help="database path (default: configured)")
    args = ap.parse_args()

    db = Path(args.db) if args.db else settings().db_path
    # Documents follow their database. Seeding the configured one writes to
    # the operator's own output directory, where the app can serve them;
    # seeding a scratch database with --db writes beside it, so a throwaway
    # run leaves nothing in the directory holding real deliverables. The
    # stored `reports` row names the file, so the two must not diverge — a
    # row pointing into a deleted temp directory is the orphan this avoids.
    out_dir = None if args.db is None else Path(args.db).resolve().parent / "reports-out"
    conn = connect(db)
    migrate(conn)

    existing = conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0]
    sites = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    print(f"{db}\n")
    print(f"  {sites} site(s) and {existing} run(s) already stored.")
    print("  seeds: normal (pages fetched) · blocked (robots.txt 503, no pages)"
          " · partial (tight budget)")
    print("  plus one synthesised brief on the normal run, and a client"
          " deliverable for each run.")
    if existing:
        print("\n  Note: this adds to what is there rather than replacing it."
              " Clear first with reset_audit_data.py --apply if that is not"
              " what you want.")
    if not args.apply:
        print("\nReport only. Re-run with --apply.")
        return 0

    from tests.test_history_g4 import GOOD_PROMO, _routes

    operator = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, operator, "Seed Co")

    made: dict[str, tuple] = {}
    for name, routes, budget in (
            ("normal", _routes(GOOD_PROMO), FULL),
            ("blocked", BLOCKED_ROUTES, FULL),
            ("partial", _routes(GOOD_PROMO), TIGHT)):
        domain = f"seed-{name}.test"
        site_id = repo.create_site(conn, client, domain,
                                   business_type="local-service")
        made[name] = _audit(conn, site_id, domain, routes, budget)

    # Synthesised, not model-written — see the module docstring. Stored through
    # the same two calls a real brief uses, so the storage and rendering paths
    # are exercised even though the judgement behind it is invented.
    brief_run = made["normal"][0]
    runs.store_expert_report(conn, brief_run, "crawl",
                             {"model": "seeded-locally",
                              "report": "## SUMMARY\nSeeded, not model-written.",
                              "findings": SEEDED_BRIEF, "tokens": 0, "cost": 0.0})
    runs.record_expert_findings(conn, brief_run, "crawl", "seeded-locally",
                                SEEDED_BRIEF)

    print("\n  seeded:")
    for name, (run_id, result) in made.items():
        row = conn.execute("SELECT status FROM audit_runs WHERE id=?",
                           (run_id,)).fetchone()
        print(f"    {name:<8} {run_id[:8]}  status={row['status']:<9}"
              f" composite={str(result.composite_score):<7}"
              f" eligible_pages={result.stats.get('pages_eligible')}"
              f" findings={len(result.findings)}")

    print("\n  deliverables:")
    for name, (run_id, _) in made.items():
        # `generate()` refuses a blocked run at the client audience whichever
        # door it is called through — the rule lives with the document rather
        # than at the API route, so this script inherits it like every other
        # caller. These are client documents, so the blocked run is refused
        # here exactly as before; only `audience="internal"` changed. Printed
        # rather than swallowed: the refusal is what an operator meets, and
        # is worth seeing in the output.
        try:
            out = gen.generate(conn, "run", "client", [run_id], out_dir=out_dir)
            print(f"    {name:<8} {Path(out['path']).name}")
        except ValueError as exc:
            print(f"    {name:<8} refused: {exc}")

    print("\nSeeded. Nothing was spent: the brief is synthesised, not a model call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
