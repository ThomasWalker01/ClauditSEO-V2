"""Score the expert briefs against the golden fixture, on a model you name.

    python scripts/run_golden.py --estimate
    python scripts/run_golden.py --model claude-sonnet-5 --spend
    python scripts/run_golden.py --model claude-opus-5 --spend --compare <run_id>
    python scripts/run_golden.py --compare <baseline_run_id> <candidate_run_id>

The last form spends nothing: it compares two runs already in the scratch
database. Every flag named above is checked against this file's own parser by
`tests/test_a_script_advertises_only_flags_it_has.py`. `--compare` was
advertised here, and in the closing line of every successful run, for as long
as it did not exist; it was found by an operator typing the third line during
a paid run and getting `unrecognized arguments`.

This is the instrument for "does the deep tier earn its price". It serves the
fixture from 127.0.0.1, crawls it, runs the labelled briefs on the model you
name, and scores what came back against labels that are true by construction.

It refuses to spend without `--spend`. A model comparison is several briefs
against several models and the bill is the point of the exercise, so the
default is to print what it would cost and stop.

What a score here does and does not tell you. It measures whether a brief
finds problems that are definitely present and stays quiet about ones
definitely absent, on a small tidy site. That is a floor. It will catch a
model change that breaks the basics and it will not tell you which model
writes a better brief for a real client.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clauditseo.analysts.expert import EXPERT_TOOLS, run_expert, tier_of  # noqa: E402
from clauditseo.config import settings  # noqa: E402
from clauditseo.crawler.crawl import crawl  # noqa: E402
from clauditseo.crawler.evidence import snapshot  # noqa: E402
from clauditseo.crawler.types import TierBudget  # noqa: E402
from clauditseo.db.connection import connect  # noqa: E402
from clauditseo.db.migrate import migrate  # noqa: E402
from clauditseo.engine.types import Tier  # noqa: E402
from clauditseo.golden import (REGISTER_SECTION, compare,  # noqa: E402
                               record, score)
from clauditseo.persistence import repo, runs  # noqa: E402
from clauditseo.providers import fx, model_prices  # noqa: E402
from tests.conftest import FixtureSite  # noqa: E402
from tests.fixtures.golden_site import LABELS, routes  # noqa: E402

BUDGET = TierBudget(max_pages=10, request_timeout_s=5, wall_clock_s=60,
                    delay_s=0)


def is_the_live_db(db: Path, live: Path) -> bool:
    """Is `db` the operator's own database — the file `live` names?

    An identity question, not a naming one. The refusal below compared
    `db.name` against the string "clauditseo.db" for as long as
    `clauditseo/config.py` has read the path from `CLAUDITSEO_DB`, so an
    operator whose database is called anything else had no guard at all
    (CQ-220): `--db <their live db> --estimate` connected to it and migrated
    it. The name is a property of one default install; the path is the fact.

    `samefile` where both files exist, because it answers through the
    filesystem and so catches what path arithmetic cannot — a junction, a
    symlink, a hardlink, two spellings Windows considers one file. Where the
    live database does not exist yet (a fresh install has none), there is
    nothing to stat, and resolved paths compared case-insensitively on
    Windows are the best available answer.
    """
    try:
        if db.exists() and live.exists():
            return os.path.samefile(db, live)
    except OSError:                                           # noqa: BLE001
        pass
    return (os.path.normcase(str(db.resolve()))
            == os.path.normcase(str(live.resolve())))


def labelled_tools() -> list[str]:
    """Only the briefs the labels speak to. Running the other twenty would
    spend money to measure nothing."""
    named = {i["tool"] for i in LABELS["expected"] + LABELS["known_absent"]}
    return sorted(t for t in named if t in EXPERT_TOOLS)


def pages_for(tool: str) -> list[str | None]:
    """Which pages this brief has to be run against.

    A site-scoped brief runs once, as [None]. A page-scoped brief runs once
    per page its labels name — running it against the site is what produced
    no report at all.
    """
    if EXPERT_TOOLS.get(tool, {}).get("scope") != "page":
        return [None]
    return sorted({i["page"] for i in LABELS["expected"] + LABELS["known_absent"]
                   if i["tool"] == tool and i.get("page")})


def estimate(conn, model: str) -> dict:
    """What a pass would cost, from what these briefs have actually cost
    before. Absent where nothing has run yet — a guess here would be a
    forecast dressed as a measurement."""
    tools = labelled_tools()
    seen = runs.expert_estimates(conn)
    known = [(t, seen[t]) for t in tools if t in seen]
    total = sum(e.get("tokens") or 0 for _t, e in known)
    price = fx.price_for(conn, model)
    return {
        "model": model, "tools": tools,
        "measured": [t for t, _ in known],
        "unmeasured": [t for t in tools if t not in seen],
        "tokens": total or None,
        # Priced as if it were all input, which over-states rather than
        # under-states — the direction to be wrong in for a spend warning.
        "usd": round(total / 1e6 * price[0], 4) if (total and price) else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None,
                    help="model id to run the briefs on; default is each "
                         "brief's configured tier")
    ap.add_argument("--spend", action="store_true",
                    help="actually call the API")
    ap.add_argument("--estimate", action="store_true")
    # A scratch database by default, NOT the operator's own.
    #
    # This creates a client, a site and an audit run every time it is called,
    # and it defaulted to the production database — so six "Golden fixture"
    # clients with 127.0.0.1 domains appeared on the operator's home screen
    # beside their real ones, along with 6 runs, 62 findings and 11 briefs.
    # A measuring instrument that leaves marks on the thing it measures is
    # not one, and the home screen is the one place a fixture client is
    # indistinguishable from a real one at a glance.
    ap.add_argument("--db", default="data/golden-scratch.db",
                    help="where to record the run; defaults to a scratch "
                         "file so the operator's own database is untouched")
    # One run id with --spend: the baseline this run is measured against.
    # Two without: compare what is already stored and call nothing.
    ap.add_argument("--compare", nargs="+", metavar="RUN_ID",
                    help="with --spend, the baseline run id this run is "
                         "compared against; without it, two stored run ids "
                         "to compare with no API calls")
    args = ap.parse_args()
    if args.compare and len(args.compare) > 2:
        ap.error("--compare takes one run id (with --spend) or two")

    cfg = settings()
    db = Path(args.db)
    if is_the_live_db(db, cfg.db_path):
        # Named, because "the live database" is the operator's own path and
        # they cannot check the match without seeing what it matched.
        print(f"Refusing to write the golden run into the live database "
              f"({cfg.db_path}). Pass --db with a scratch path, or take the "
              f"default:", file=sys.stderr)
        print("    python scripts/run_golden.py --estimate", file=sys.stderr)
        return 2
    conn = connect(db)
    migrate(conn)
    # A scratch database is created empty, and an empty `model_prices` is why
    # every golden run until now recorded a correct token count against no
    # money at all — the instrument for "does the deep tier earn its price"
    # structurally unable to state a price. Prices are read out of the
    # operator's own database, read-only: the refusal above is about writing
    # a fixture run *into* it, and `copy_prices` opens it through a `mode=ro`
    # URI precisely so that reading stays a read. Costs are computed when each
    # brief logs, so this has to happen before anything runs.
    seeded = model_prices.copy_prices(conn, cfg.db_path,
                                      entered_by="golden-harness")
    if seeded["ok"]:
        print(f"prices: {seeded['copied']} copied from {seeded['source']}"
              + (f", {len(seeded['kept'])} already here" if seeded["kept"]
                 else ""))
    else:
        print(f"prices: none — {seeded['error']}. This run will report tokens"
              " and no money.", file=sys.stderr)

    if args.compare:
        # A mistyped run id would otherwise score as a run that caught
        # nothing and compare cleanly against it - the same class of defect
        # as a silent zero in a money column.
        for rid in args.compare:
            if not conn.execute("SELECT 1 FROM audit_runs WHERE id=?",
                                (rid,)).fetchone():
                print(f"No run {rid} in {db}.", file=sys.stderr)
                return 2
    if args.compare and not args.spend:
        if len(args.compare) != 2:
            print("--compare with one run id needs --spend, which produces "
                  "the run to compare it with. Pass two run ids to compare "
                  "two runs already stored.", file=sys.stderr)
            return 2
        print(json.dumps(
            compare(conn, args.compare[0], args.compare[1], LABELS), indent=2))
        return 0

    if args.estimate or not args.spend:
        est = estimate(conn, args.model or cfg.model_for_tier("standard"))
        print(json.dumps(est, indent=2))
        if not args.spend:
            print("\nNothing was called. Re-run with --spend to score for real.")
            return 0

    if not cfg.anthropic_api_key:
        print("No API key configured.", file=sys.stderr)
        return 2

    site = FixtureSite(routes()).start()
    try:
        base = site.base_url + "/"
        crawled = crawl(base, Tier.T2, budget=BUDGET)
        op = repo.ensure_default_operator(conn)
        site_id = repo.create_site(
            conn, repo.create_client(conn, op, "Golden fixture"), base)
        run_id = runs.create_run(conn, site_id, ["TEC"], "T2",
                                 analyst_enabled=True)
        runs.store_evidence(conn, run_id, snapshot(crawled))
        evidence = runs.get_evidence(conn, run_id)

        from clauditseo.analysts.layer import provider_from_settings
        from clauditseo.crawler.fetch import Fetcher
        fetcher = Fetcher(timeout_s=20)
        for tool in labelled_tools():
            model = args.model or cfg.model_for_tier(tier_of(tool))
            # A page-scoped brief judges one page and needs to be told which.
            # Called without one it produced nothing, and the scorer reported
            # "tool did not run" while three of five labels sat unscored
            # behind an overall catch rate of 1.0 — a flattering number
            # measuring two labels out of five.
            for page in pages_for(tool):
                where = f" {page}" if page else ""
                print(f"  {tool:20}{where:18} on {model} …", flush=True)
                extra = {}
                if page:
                    # The brief reads the page from `extra["page"]`, not from
                    # a page_url kwarg. Passing the wrong one put the URL
                    # into **extra where nothing read it, and the brief
                    # correctly reported every check "not assessable" for
                    # want of a page — behaving impeccably while the harness
                    # scored it zero.
                    extra["page"] = fetcher.fetch(base.rstrip("/") + page)
                try:
                    run_expert(conn, run_id, tool, evidence,
                               {"domain": base}, cfg,
                               provider_from_settings(cfg, model),
                               operator_inputs=LABELS.get("inputs"), **extra)
                except Exception as exc:                  # noqa: BLE001
                    print(f"    failed: {type(exc).__name__}: {exc}")
    finally:
        site.stop()

    out = score(conn, run_id, LABELS)
    out["model"] = args.model or "per-tier default"
    # What it cost, beside what it caught. Never a bare zero: `run_spend`
    # returns `usd: None` with `usd_absent_because` filled in rather than a
    # figure that reads as free.
    out["spend"] = runs.run_spend(conn, run_id)
    if args.compare:
        out["compared_with"] = compare(conn, args.compare[0], run_id,
                                       LABELS)
    print(json.dumps(out, indent=2))
    # The score, into a tracked register — relay item 087. For nine days this
    # printed and wrote nowhere, so the two paid runs of 2026-08-24 left 20
    # findings, 4 expert reports and 6 cost rows on disk and no score at all;
    # the document the operator paid for existed only in a terminal. The
    # record is written here rather than left to `>` because a redirection is
    # something the next person has to know to type, and nobody did.
    #
    # Not fatal if it fails. The run has already been paid for and its raw
    # rows are stored — refusing to print the score because the register
    # would not take the row is the wrong way round.
    try:
        where = record(conn, out, on=date.today().isoformat())
        print(f"\nrecorded: {where['path']}:{where['line']}"
              f" under '## {where['section']}'")
    except (OSError, ValueError) as exc:                      # noqa: BLE001
        print(f"\nNOT recorded: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("The run is stored; the register row is not. Add it by hand"
              f" under '## {REGISTER_SECTION}' in TIMINGS.md.", file=sys.stderr)
    # Named in the form the next run can act on, per DISCIPLINE rule 14.
    # This line said "pass it to --compare" for as long as the parser
    # had no such flag.
    print(f"\nrun_id {run_id}. To measure the next model against it:")
    print(f"    python scripts/run_golden.py --model MODEL --spend"
          f" --compare {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
