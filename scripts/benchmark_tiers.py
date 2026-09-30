"""Measure what the deep tier actually costs against what it actually buys.

Runs every expert brief in phases 1-4 twice over one stored audit run: once
forcing the deep model on all of them (the baseline), once using the tier each
tool is configured with. Same run, same evidence, same operator inputs, so the
model is the only thing that changes.

Two things make or break the honesty of this:

  * The analyst cache must be bypassed. A cached reply reports zero tokens and
    would flatter whichever pass happened to run second.
  * Input and output tokens must be counted separately, because output costs
    several times more per token and the two passes have very different
    input/output balances.

Cost in dollars is derived, not measured. Token counts are the measurement;
the rate table below is applied afterwards and is printed in the report so the
figures can be rechecked against a real bill.

    python scripts/benchmark_tiers.py --run-id <id> [--dry-run] [--resume]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8020"
DB = Path("data/clauditseo.db")

# Phases 1-4, in playbook order. Held here rather than derived so the benchmark
# measures a fixed, quotable set even as the playbook grows.
TOOLS = [
    ("1. Crawl and indexability", "crawl"),
    ("1. Crawl and indexability", "indexability"),
    ("1. Crawl and indexability", "urls"),
    ("1. Crawl and indexability", "js-rendering"),
    ("2. Technical foundation", "https-security"),
    ("2. Technical foundation", "site-architecture"),
    ("2. Technical foundation", "hreflang"),
    ("2. Technical foundation", "migration-redirects"),
    ("3. On-page", "onpage-hygiene"),
    ("3. On-page", "cannibalisation-map"),
    ("3. On-page", "image-optimisation"),
    ("4. Structured data", "entity-graph"),
]

# migration-redirects refuses to run without a map to validate. The same
# synthetic map is supplied to both passes, so it cannot favour either; it is
# declared in the report because it is operator input, not crawl evidence.
INPUTS = {
    "migration-redirects": {
        "REDIRECT_MAP": "/old-services, /services, 301\n"
                        "/old-about-us, /about, 301\n"
                        "/blog/old-post, /blog/post, 301",
        "MIGRATION_TYPE": "IA restructure",
    },
}

# $ per million tokens, (input, output). ASSUMED LIST PRICE, not measured and
# not billed — see the note this script writes into the report. Override with
# --prices "model:in/out,..." to re-cost against a real invoice.
DEFAULT_PRICES = {
    "claude-opus-5": (15.00, 75.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

PASSES = [("opus-baseline", "claude-opus-5"), ("configured-tiers", None)]


def parse_prices(raw: str) -> dict:
    out = {}
    for entry in (raw or "").split(","):
        if ":" in entry and "/" in entry:
            model, _, pair = entry.partition(":")
            a, b = pair.split("/", 1)
            out[model.strip()] = (float(a), float(b))
    return out


def cost_of(model: str, tokens_in: int, tokens_out: int, prices: dict):
    rate = prices.get(model)
    if not rate:
        return None
    return round(tokens_in / 1e6 * rate[0] + tokens_out / 1e6 * rate[1], 4)


def quality_proxies(report: str, envelope: dict) -> dict:
    """Objective, countable properties of the answer. Deliberately not a
    quality score: judging whether a finding is *correct* needs hand labels
    (the golden set), and inventing one here would be worse than none."""
    words = len(report.split())
    return {
        "words": words,
        "chars": len(report),
        "headings": len(re.findall(r"^#{1,4} ", report, re.M)),
        "table_rows": len(re.findall(r"^\|", report, re.M)),
        "urls_cited": len(set(re.findall(r"https?://[^\s\)\]|]+", report))),
        # The brief's own honesty markers: does the model admit what it cannot
        # see, or does it fill the gap?
        "to_confirm": len(re.findall(r"\[TO CONFIRM\]|\[NOT SUPPLIED\]", report)),
        "code_blocks": report.count("```") // 2,
        "figures_to_verify": len(envelope.get("figures_to_verify") or []),
        "truncated": bool(envelope.get("truncated")),
    }


def run_one(client: httpx.Client, run_id: str, tool: str, model: str | None) -> dict:
    body = {"no_cache": True, "inputs": INPUTS.get(tool, {})}
    if model:
        body["model"] = model
    started = time.time()
    try:
        resp = client.post(f"{BASE}/api/runs/{run_id}/expert/{tool}", json=body,
                           timeout=httpx.Timeout(1200.0, connect=10.0))
        envelope = resp.json() if resp.status_code < 500 else {
            "status": "http_error", "reason": f"HTTP {resp.status_code}"}
    except Exception as exc:                      # noqa: BLE001 - recorded, not raised
        envelope = {"status": "error",
                    "reason": f"{type(exc).__name__}: {exc}"}
    envelope["elapsed_s"] = round(time.time() - started, 1)
    return envelope


def estimate(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT AVG(quantity) FROM cost_entries WHERE operation LIKE 'EXPERT:%'"
    ).fetchone()[0] or 36000
    print(f"  historical average: {rows:,.0f} tokens per brief")
    print(f"  {len(TOOLS)} tools x {len(PASSES)} passes = {len(TOOLS)*len(PASSES)} calls")
    print(f"  rough total: {rows*len(TOOLS)*len(PASSES):,.0f} tokens "
          "(split briefs bill twice, so treat this as a floor)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", default="benchmarks")
    ap.add_argument("--prices", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="skip tool/pass combinations already in the log")
    args = ap.parse_args()

    prices = {**DEFAULT_PRICES, **parse_prices(args.prices)}
    out = Path(args.out)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    log_path = out / "results.jsonl"

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    run = conn.execute(
        "SELECT r.*, s.domain FROM audit_runs r JOIN sites s ON s.id=r.site_id"
        " WHERE r.id=?", (args.run_id,)).fetchone()
    if not run:
        print(f"no such run: {args.run_id}")
        return 1
    print(f"run {args.run_id[:8]}  {run['domain']}  "
          f"tier={run['tier']}  score={run['composite_score']}")
    estimate(conn)
    if args.dry_run:
        for label, forced in PASSES:
            print(f"\npass '{label}': model={forced or 'configured tier per tool'}")
            for phase, tool in TOOLS:
                print(f"    {phase:28} {tool}")
        return 0

    done = set()
    if args.resume and log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done.add((rec["pass"], rec["tool"]))
        print(f"resuming: {len(done)} calls already recorded")

    for label, forced in PASSES:
        for phase, tool in TOOLS:
            if (label, tool) in done:
                print(f"  [skip] {label:16} {tool}")
                continue
            print(f"  [run ] {label:16} {tool:22} ", end="", flush=True)
            env = run_one(httpx.Client(), args.run_id, tool, forced)
            report = env.get("report") or ""
            model = env.get("model", forced or "?")
            rec = {
                "pass": label, "phase": phase, "tool": tool,
                "model": model, "tier": env.get("tier"),
                "status": env.get("status"), "reason": env.get("reason"),
                "calls": env.get("calls"),
                "tokens_in": env.get("tokens_in", 0),
                "tokens_out": env.get("tokens_out", 0),
                "tokens": env.get("tokens", 0),
                "cost_usd": cost_of(model, env.get("tokens_in", 0),
                                    env.get("tokens_out", 0), prices),
                "elapsed_s": env.get("elapsed_s"),
                "quality": quality_proxies(report, env) if report else None,
            }
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if report:
                (out / "reports" / f"{label}__{tool}.md").write_text(
                    report, encoding="utf-8")
            print(f"{rec['status']:12} {rec['tokens']:>7,} tok  "
                  f"{rec['elapsed_s']:>6}s  "
                  f"${rec['cost_usd'] if rec['cost_usd'] is not None else '?'}")

    print(f"\nlogged to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
