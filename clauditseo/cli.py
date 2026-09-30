"""ClauditSEO command-line interface.

    clauditseo migrate            apply pending database migrations
    clauditseo seed               seed demo data (idempotent)
    clauditseo serve              start the API + dashboard server
    clauditseo demo               migrate + seed + serve in one go
"""

from __future__ import annotations

import argparse
import sys

from clauditseo import APP_NAME, __version__
from clauditseo.config import settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo


def _cmd_migrate() -> int:
    cfg = settings()
    conn = connect(cfg.db_path)
    ran = migrate(conn)
    conn.close()
    print(f"database: {cfg.db_path}")
    print(f"migrations applied: {ran or 'none (up to date)'}")
    return 0


def _cmd_seed() -> int:
    cfg = settings()
    conn = connect(cfg.db_path)
    migrate(conn)
    result = repo.seed_demo(conn)
    conn.close()
    print("demo data seeded" if result["seeded"] else "demo data already present — skipped")
    return 0


def _redirect_output_when_headless(cfg) -> None:
    """Under pythonw.exe (no console, as a scheduled task uses) sys.stdout is
    None, and the first log write kills the process. Send output to a file
    instead, which also gives the service somewhere to record failures."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_path = cfg.db_path.parent / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(log_path, "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = sys.stderr = stream


def _cmd_serve() -> int:
    import uvicorn

    from clauditseo.api.app import create_app

    cfg = settings()
    _redirect_output_when_headless(cfg)
    print(f"{APP_NAME} {__version__} — http://localhost:{cfg.port}")

    # Before uvicorn binds, and before anything can take time: the parent is
    # only resolvable while it is alive, and the shell that started this may
    # be gone seconds from now.
    from pathlib import Path

    from clauditseo import provenance

    rec = provenance.record_start(cfg.db_path.parent,
                                  Path(__file__).resolve().parents[1])
    parent = (rec.get("parent") or {}).get("cmdline") or rec.get("parent_error")
    marker = rec.get("marker") or {}
    by = (f"{marker.get('kind')} {marker.get('subject')}".strip()
          if marker else "nothing holding the marker")
    print(f"started by: {by} | parent: {parent}")

    _start_scheduler(cfg)
    uvicorn.run(create_app(), host="127.0.0.1", port=cfg.port, log_level="info")
    return 0


def _start_scheduler(cfg) -> None:
    """Recurring audits, only in the served process — tests and one-off CLI
    commands must not spawn a launcher thread. Launches go through the app's
    own HTTP API so every validation and the run thread stay identical to a
    hand-started audit."""
    import httpx

    from clauditseo.db.connection import connect
    from clauditseo.scheduler import start_scheduler

    headers = ({"Authorization": f"Bearer {cfg.api_token}"}
               if cfg.api_token else {})

    def launch(site: dict) -> None:
        httpx.post(f"http://127.0.0.1:{cfg.port}/api/sites/{site['id']}/audits",
                   json={"tier": "T2"}, headers=headers,
                   timeout=30.0).raise_for_status()

    def launch_tool(job: dict) -> None:
        """One scheduled brief, against the site's latest completed run.

        Generous timeout: a deep brief is a single blocking model call that
        can run for minutes, and giving up on it early would leave the work
        running server-side while the scheduler recorded a failure."""
        httpx.post(f"http://127.0.0.1:{cfg.port}/api/runs/{job['run_id']}"
                   f"/expert/{job['tool_id']}",
                   json={}, headers=headers, timeout=900.0).raise_for_status()

    start_scheduler(lambda: connect(cfg.db_path), launch, launch_tool=launch_tool)


def _cmd_audit_run(args) -> int:
    import clauditseo.modules  # noqa: F401  (register dimensions)
    from clauditseo.crawler.crawl import crawl as crawl_site
    from clauditseo.engine import registry
    from clauditseo.engine.core import run_audit
    from clauditseo.engine.types import Site, Tier
    from clauditseo.persistence import runs
    from clauditseo.providers.base import ProviderHub

    cfg = settings()
    dims = [d.strip().upper() for d in args.dims.split(",") if d.strip()]
    unknown = [d for d in dims if d not in registry.all_modules()]
    if unknown:
        print(f"unknown dimension(s): {', '.join(unknown)}")
        return 2
    adaptive_mode = args.tier == "auto"
    tier = Tier.T1 if adaptive_mode else Tier(args.tier)

    conn = connect(cfg.db_path)
    migrate(conn)
    client_row = conn.execute(
        "SELECT id FROM clients WHERE lower(name)=lower(?) AND archived_at IS NULL",
        (args.client,)).fetchone()
    if not client_row:
        print(f"no client named {args.client!r} — create it in the dashboard or seed data")
        return 2
    site_row = conn.execute(
        "SELECT * FROM sites WHERE client_id=? AND lower(domain)=lower(?)"
        " AND archived_at IS NULL", (client_row["id"], args.site)).fetchone()
    if not site_row:
        print(f"client {args.client!r} has no site {args.site!r}")
        return 2

    domain = site_row["domain"].strip()
    from clauditseo.crawler.crawl import crawl_start_url
    start_url = args.url or crawl_start_url(domain)
    site = Site(domain=site_row["domain"], locale=site_row["locale"],
                business_type=site_row["business_type"],
                target_market=site_row["target_market"])
    hub = ProviderHub.from_settings(cfg)

    if tier is Tier.T3:
        paid = [p.name for p in hub.backlink_providers + hub.cwv_providers]
        print(f"T3 deep run — paid/keyed providers in play: {paid or 'none (keyless)'}")

    run_id = runs.create_run(conn, site_row["id"], dims, tier.value,
                             analyst_enabled=args.analyst or adaptive_mode,
                             # The CLI crawls the site (brief v3 step I).
                             scan_scope="full")
    mode = "adaptive" if adaptive_mode else tier.value
    print(f"run {run_id}: crawling {start_url} ({mode}, dims {','.join(dims)})")
    try:
        if adaptive_mode:
            from clauditseo.adaptive import run_adaptive
            result, _ = run_adaptive(conn, run_id, site, site_row["id"], start_url,
                                     cfg, dims, model=args.model, announce=print)
        else:
            crawl_result = crawl_site(start_url, tier, security_paths="SEC" in dims)
            result = run_audit(site, crawl_result, dims, tier,
                               context={"providers": hub})
            # Stored here, not beside `complete_run`, and for the reason the
            # served path stores it here too: the evidence is a fact about the
            # crawl, gathered before the analyst layer runs, so an analyst
            # failure must not be what decides whether the run can say what it
            # reached. The adaptive branch above stores it at both its exits;
            # this branch stored it at neither, which is why runs `93bdd2b2`,
            # `8fdeb042` and `d9c14277` hold `crawled_paths` with
            # `crawl_evidence` NULL and `_breadth_phrase` has nothing to read.
            from clauditseo.crawler.evidence import snapshot
            runs.store_evidence(conn, run_id, snapshot(crawl_result))
            from clauditseo.analysts.layer import provider_from_settings, run_analyst_layer
            outcome = run_analyst_layer(conn, run_id, site.domain, result, crawl_result,
                                        cfg, enabled=args.analyst, announce=print,
                                        provider=provider_from_settings(cfg, args.model))
            if outcome.ran:
                result.findings.extend(outcome.security_findings)
                result.findings.extend(outcome.findings)
                print(f"analyst layer: spent {outcome.spent_tokens} tokens, "
                      f"{len(outcome.findings)} insight(s) accepted")
                for spend in outcome.spends:
                    if spend.skipped:
                        print(f"  {spend.task}: skipped ({spend.skipped})")
            elif args.analyst:
                print(f"analyst layer not run: {outcome.reason_not_run}")
            runs.complete_run(conn, run_id, result)
    except Exception as exc:
        runs.fail_run(conn, run_id, str(exc))
        print(f"run failed: {exc}")
        return 1

    from clauditseo.reporting.render import NO_COMPOSITE

    if result.composite_score is None:
        print(f"\n{NO_COMPOSITE}")
    else:
        print(f"\ncomposite score: {result.composite_score}")
    for dim, sub in sorted(result.subscores.items()):
        flag = "" if sub.applicable else "  (not applicable)"
        print(f"  {dim}: {sub.score:6.2f}  weight {sub.weight:.3f}{flag}")
    tried = result.stats["pages_crawled"]
    read = result.stats.get("pages_eligible", tried)
    pages = f"{read}" if read == tried else f"{read} read of {tried} tried"
    print(f"findings: {len(result.findings)}  pages: {pages}")
    states = [s for s in runs.site_states(conn, site_row["id"]) if s["state"] == "regressed"]
    if states:
        print(f"REGRESSIONS: {len(states)} previously fixed issue(s) are back:")
        for s in states[:10]:
            print(f"  [{s['severity']}] {s['dimension']}/{s['check_id']}: {s['summary']}")
    conn.close()
    return 0


def _cmd_operator(args) -> int:
    cfg = settings()
    conn = connect(cfg.db_path)
    migrate(conn)
    try:
        if args.operator_command == "add":
            op_id, token = repo.create_operator(conn, args.name, args.email, args.role)
            print(f"operator created: {args.name} ({args.role}), id {op_id}")
            print(f"login token (shown once, store it now): {token}")
            print("Note: once any operator has a token, the API requires token login.")
        else:
            for op in repo.list_operators(conn):
                token_state = "token set" if op["has_token"] else "no token"
                print(f"{op['id'][:8]}  {op['role']:<7} {op['name']}"
                      f"  {op['email'] or '-'}  ({token_state})")
    finally:
        conn.close()
    return 0


def _cmd_report(args) -> int:
    from clauditseo.reporting.checks import ReportCheckError
    from clauditseo.reporting.generate import generate

    cfg = settings()
    conn = connect(cfg.db_path)
    migrate(conn)
    run_ids = [r.strip() for r in args.runs.split(",") if r.strip()]
    try:
        report = generate(conn, args.template, args.audience, run_ids)
    except (ValueError, ReportCheckError) as exc:
        print(f"report not generated: {exc}")
        return 1
    finally:
        conn.close()
    print(f"report written: {report['path']}")
    if report.get("pdf_path"):
        print(f"pdf written: {report['pdf_path']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clauditseo", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("migrate", "seed", "serve", "demo"):
        sub.add_parser(name)

    audit = sub.add_parser("audit", help="run and inspect audits")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    run_p = audit_sub.add_parser("run", help="run a staged audit")
    run_p.add_argument("--client", required=True, help="client name")
    run_p.add_argument("--site", required=True, help="site domain")
    run_p.add_argument("--dims", default="TEC,ONP,PRF,CNT,OFP,LOC,AIS",
                       help="comma-separated dimension codes")
    run_p.add_argument("--tier", default="auto",
                       choices=["auto", "T1", "T2", "T3"],
                       help="auto (adaptive, default) runs a pulse then escalates "
                            "only what scores below the health bands")
    run_p.add_argument("--url", default=None,
                       help="start URL override (default https://<domain>/)")
    run_p.add_argument("--analyst", action="store_true",
                       help="enable the LLM analyst layer (never on T1)")
    run_p.add_argument("--model", default=None,
                       help="analyst model override, e.g. claude-fable-5")

    op_parser = sub.add_parser("operator", help="manage operator accounts")
    op_sub = op_parser.add_subparsers(dest="operator_command", required=True)
    op_add = op_sub.add_parser("add", help="create an operator and print their token once")
    op_add.add_argument("--name", required=True)
    op_add.add_argument("--email", default=None)
    op_add.add_argument("--role", default="member", choices=["owner", "member"])
    op_sub.add_parser("list")

    report_p = sub.add_parser("report", help="generate a report from stored runs")
    report_p.add_argument("--runs", required=True,
                          help="run id (or two comma-separated ids for comparison)")
    report_p.add_argument("--template", default="run",
                          choices=["run", "run-free", "comparison", "monthly-trend"])
    report_p.add_argument("--audience", default="client",
                          choices=["client", "internal"])
    args = parser.parse_args(argv)

    if args.command == "audit" and args.audit_command == "run":
        return _cmd_audit_run(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "operator":
        return _cmd_operator(args)
    if args.command == "migrate":
        return _cmd_migrate()
    if args.command == "seed":
        return _cmd_seed()
    if args.command == "serve":
        return _cmd_serve()
    if args.command == "demo":
        rc = _cmd_migrate() or _cmd_seed()
        return rc or _cmd_serve()
    return 2


if __name__ == "__main__":
    sys.exit(main())
