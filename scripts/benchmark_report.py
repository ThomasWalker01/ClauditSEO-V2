"""Turn benchmark_tiers.py's log into a cost and quality analysis.

Separated from the measurement on purpose: the token counts cost real money to
obtain, so re-costing them against different rates must never mean re-running
the briefs.

    python scripts/benchmark_report.py [--out benchmarks] [--prices "model:in/out,..."]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from benchmark_tiers import DEFAULT_PRICES, cost_of, parse_prices

BASELINE, TIERED = "opus-baseline", "configured-tiers"


def money(value) -> str:
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "n/a"


def pct(new, old) -> str:
    """Change relative to the baseline, signed the way a delta reads: -80%
    means the tiered pass used 80% less, not that it saved a negative amount."""
    if not old:
        return "n/a"
    return f"{(new - old) / old * 100:+.1f}%"


def issue_codes(report: str) -> dict[str, str] | None:
    """Issue codes the report raised, with severity — or None if this brief's
    output is not code-structured.

    Comparing substance rather than length is the comparison that matters, but
    it is only extractable where the brief asks for `code` headings carrying an
    explicit severity. Several briefs answer in prose or in severity-columned
    tables instead, and a regex loose enough to catch those also catches
    ordinary headings: an earlier version of this scored a section titled
    "rendered" as a finding. Returning None where the format does not support
    extraction is the honest answer; those tools are compared by reading.
    """
    body = re.split(r"^No issues detected", report, flags=re.M)[0]
    found = {}
    for match in re.finditer(
            r"^#{1,4}\s+`([a-z][a-z0-9-]{3,})`\s*$"      # backticked code only
            r"(.*?)(?=^#{1,4}\s|\Z)", body, re.M | re.S):
        block = match.group(2)
        sev = re.search(r"\*\*Severity:\*\*\s*(\w+)", block)
        if sev:                                          # severity is required
            found[match.group(1)] = sev.group(1).lower()
    return found or None


def load(path: Path) -> dict:
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            records[(rec["pass"], rec["tool"])] = rec   # later wins on re-run
    return records


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="benchmarks")
    ap.add_argument("--prices", default="")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--site", default="")
    args = ap.parse_args()

    out = Path(args.out)
    prices = {**DEFAULT_PRICES, **parse_prices(args.prices)}
    records = load(out / "results.jsonl")
    tools = [t for (p, t) in records if p == BASELINE]

    # Recost from stored tokens so a rate change never needs a re-run.
    for rec in records.values():
        rec["cost_usd"] = cost_of(rec["model"], rec.get("tokens_in", 0),
                                  rec.get("tokens_out", 0), prices)

    L: list[str] = []
    A = L.append
    A("# Deep tier vs configured tiers — cost and quality benchmark")
    A("")
    A(f"- **Target run:** `{args.run_id or 'see results.jsonl'}`"
      f"{'  (' + args.site + ')' if args.site else ''}")
    A(f"- **Scope:** every expert brief in workbench phases 1–4 "
      f"({len(tools)} tools), run twice")
    A("- **Pass A `opus-baseline`:** every tool forced onto the deep model")
    A("- **Pass B `configured-tiers`:** every tool on the tier it ships with")
    A("- Same audit run, same stored crawl evidence, same operator inputs in "
      "both passes. The model is the only variable.")
    A("")

    A("## How to read this")
    A("")
    A("**Token counts are measured.** They come from the API's own usage "
      "figures, recorded per call, input and output separately.")
    A("")
    A("**Dollar figures are derived, not billed.** They apply the rate table "
      "below to those token counts. The rates are list prices entered as an "
      "assumption — nothing here reads an invoice. Re-cost against a real "
      "bill without re-running anything:")
    A("")
    A("```")
    A("python scripts/benchmark_report.py --prices \"claude-opus-5:15.00/75.00,...\"")
    A("```")
    A("")
    A("**The analyst cache was bypassed for every call.** Otherwise the second "
      "pass would replay the first, report zero tokens, and show a fictitious "
      "100% saving.")
    A("")
    A("| Model | Input $/M | Output $/M |")
    A("|---|---:|---:|")
    for model, (i, o) in sorted(prices.items()):
        A(f"| `{model}` | {i:.2f} | {o:.2f} |")
    A("")

    # --- per-tool table ------------------------------------------------------
    A("## Per-tool comparison")
    A("")
    A("| Tool | Tier | Baseline model | Baseline tokens | Baseline $ | "
      "Tiered model | Tiered tokens | Tiered $ | Cost change |")
    A("|---|---|---|---:|---:|---|---:|---:|---:|")

    totals = defaultdict(lambda: {"in": 0, "out": 0, "cost": 0.0})
    same_model, changed_model = [], []
    for tool in tools:
        b, t = records.get((BASELINE, tool)), records.get((TIERED, tool))
        if not b or not t:
            continue
        for key, rec in ((BASELINE, b), (TIERED, t)):
            totals[key]["in"] += rec.get("tokens_in", 0)
            totals[key]["out"] += rec.get("tokens_out", 0)
            totals[key]["cost"] += rec.get("cost_usd") or 0.0
        (same_model if b["model"] == t["model"] else changed_model).append((b, t))
        A(f"| `{tool}` | {t.get('tier') or '?'} "
          f"| {b['model'].split('-2')[0]} | {b.get('tokens',0):,} "
          f"| {money(b.get('cost_usd'))} "
          f"| {t['model'].split('-2')[0]} | {t.get('tokens',0):,} "
          f"| {money(t.get('cost_usd'))} "
          f"| {pct(t.get('cost_usd') or 0, b.get('cost_usd') or 0)} |")

    bt, tt = totals[BASELINE], totals[TIERED]
    A(f"| **Total** | | | **{bt['in']+bt['out']:,}** | **{money(bt['cost'])}** "
      f"| | **{tt['in']+tt['out']:,}** | **{money(tt['cost'])}** "
      f"| **{pct(tt['cost'], bt['cost'])}** |")
    A("")

    A("### Totals")
    A("")
    A("| | Input tokens | Output tokens | Total | Cost |")
    A("|---|---:|---:|---:|---:|")
    for label, key in (("Opus baseline", BASELINE), ("Configured tiers", TIERED)):
        d = totals[key]
        A(f"| {label} | {d['in']:,} | {d['out']:,} | {d['in']+d['out']:,} "
          f"| {money(d['cost'])} |")
    saved = bt["cost"] - tt["cost"]
    A(f"| **Saved** | | | | **{money(saved)}** ({pct(tt['cost'], bt['cost'])}) |")
    A("")
    if bt["cost"]:
        A(f"Running all {len(tools)} phase 1–4 briefs costs **{money(bt['cost'])}** "
          f"on the deep model against **{money(tt['cost'])}** on the shipped "
          f"tiers — a **{abs((bt['cost']-tt['cost'])/bt['cost']*100):.0f}% "
          f"reduction** per full pass.")
        A("")

    # --- control -------------------------------------------------------------
    A("## The control: tools that ran the same model twice")
    A("")
    if same_model:
        A(f"{len(same_model)} tool(s) ship on the deep tier already, so both "
          "passes used the same model. Their spread is pure run-to-run "
          "variance, and it sets the bar: any difference smaller than this "
          "between models is noise, not evidence.")
        A("")
        A("| Tool | Model | Tokens A | Tokens B | Δ | Words A | Words B | Δ |")
        A("|---|---|---:|---:|---:|---:|---:|---:|")
        for b, t in same_model:
            qa, qb = b.get("quality") or {}, t.get("quality") or {}
            A(f"| `{b['tool']}` | {b['model']} | {b.get('tokens',0):,} "
              f"| {t.get('tokens',0):,} | {pct(t.get('tokens',0), b.get('tokens',0))} "
              f"| {qa.get('words','?')} | {qb.get('words','?')} "
              f"| {pct(qb.get('words',0), qa.get('words',0))} |")
        A("")
    else:
        A("_No tool ran the same model in both passes, so this benchmark has "
          "no variance control. Treat small differences with suspicion._")
        A("")

    # --- quality -------------------------------------------------------------
    A("## What the cheaper tiers gave up")
    A("")
    A("These are **countable properties of the output, not a quality score.** "
      "Deciding whether a finding is *correct* needs hand-labelled ground "
      "truth, which this benchmark does not have. Both sets of reports are "
      "saved under `benchmarks/reports/` for side-by-side reading.")
    A("")
    A("| Tool | Model change | Words | Headings | Table rows | URLs cited | "
      "`[TO CONFIRM]` | Unverified figures | Truncated |")
    A("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for b, t in changed_model:
        qa, qb = b.get("quality") or {}, t.get("quality") or {}
        if not qa or not qb:
            A(f"| `{b['tool']}` | {b['model']} → {t['model']} "
              f"| _one pass produced no report_ | | | | | | |")
            continue
        trunc = ("both" if qa.get("truncated") and qb.get("truncated")
                 else "baseline" if qa.get("truncated")
                 else "tiered" if qb.get("truncated") else "no")
        A(f"| `{b['tool']}` | {b['model'].split('-2')[0]} → "
          f"{t['model'].split('-2')[0]} "
          f"| {qa.get('words',0):,} → {qb.get('words',0):,} "
          f"({pct(qb.get('words',0), qa.get('words',0))}) "
          f"| {qa.get('headings',0)} → {qb.get('headings',0)} "
          f"| {qa.get('table_rows',0)} → {qb.get('table_rows',0)} "
          f"| {qa.get('urls_cited',0)} → {qb.get('urls_cited',0)} "
          f"| {qa.get('to_confirm',0)} → {qb.get('to_confirm',0)} "
          f"| {qa.get('figures_to_verify',0)} → {qb.get('figures_to_verify',0)} "
          f"| {trunc} |")
    A("")

    # --- agreement on substance ---------------------------------------------
    A("## Did they find the same things?")
    A("")
    A("Issue codes raised by each pass, compared as sets. Word counts say how "
      "much a model wrote; this says whether it reached the same conclusions. "
      "A tool where both passes raise identical codes at identical severities "
      "is one where the deep tier bought length, not detection.")
    A("")
    A("Only briefs that ask for backticked issue codes carrying an explicit "
      "severity can be compared this way. The rest answer in prose or in "
      "severity-columned tables, and are listed below as not extractable "
      "rather than forced through a regex that would invent findings.")
    A("")
    A("| Tool | Codes (baseline) | Codes (tiered) | Both | Baseline only | "
      "Tiered only | Severity disagreements |")
    A("|---|---:|---:|---:|---|---|---|")
    agreed_total = only_a_total = only_b_total = 0
    not_extractable = []
    for tool in tools:
        pa = out / "reports" / f"{BASELINE}__{tool}.md"
        pb = out / "reports" / f"{TIERED}__{tool}.md"
        if not (pa.exists() and pb.exists()):
            continue
        ca = issue_codes(pa.read_text(encoding="utf-8"))
        cb = issue_codes(pb.read_text(encoding="utf-8"))
        if ca is None or cb is None:
            not_extractable.append(tool)
            continue
        both = set(ca) & set(cb)
        only_a, only_b = set(ca) - set(cb), set(cb) - set(ca)
        clash = [f"`{c}` {ca[c]}→{cb[c]}" for c in sorted(both) if ca[c] != cb[c]]
        agreed_total += len(both)
        only_a_total += len(only_a)
        only_b_total += len(only_b)
        A(f"| `{tool}` | {len(ca)} | {len(cb)} | {len(both)} "
          f"| {', '.join('`'+c+'`' for c in sorted(only_a)) or '—'} "
          f"| {', '.join('`'+c+'`' for c in sorted(only_b)) or '—'} "
          f"| {', '.join(clash) or '—'} |")
    total_codes = agreed_total + only_a_total + only_b_total
    A(f"| **Total** | | | **{agreed_total}** | **{only_a_total}** "
      f"| **{only_b_total}** | |")
    A("")
    if not_extractable:
        A(f"**Not extractable ({len(not_extractable)} of {len(tools)}):** "
          + ", ".join(f"`{t}`" for t in not_extractable)
          + ". These briefs do not answer with coded findings, so their two "
            "reports must be compared by reading them side by side in "
            "`benchmarks/reports/`. No score is invented for them here.")
        A("")
    if total_codes:
        A(f"The two passes agreed on **{agreed_total} of {total_codes}** "
          f"distinct issue codes ({agreed_total/total_codes*100:.0f}%). "
          f"{only_a_total} were raised only by the deep model and "
          f"{only_b_total} only by the configured tiers.")
        A("")
    A("> Set overlap is not correctness. Both passes can miss the same real "
      "issue, and agreement between two models is not evidence that either is "
      "right. This measures consistency, which is all it can measure without "
      "hand-labelled ground truth.")
    A("")

    # --- failures ------------------------------------------------------------
    failures = [r for r in records.values() if r.get("status") != "ok"]
    if failures:
        A("## Calls that did not return a report")
        A("")
        A("| Pass | Tool | Model | Status | Reason |")
        A("|---|---|---|---|---|")
        for rec in failures:
            A(f"| {rec['pass']} | `{rec['tool']}` | {rec['model']} "
              f"| {rec['status']} | {(rec.get('reason') or '')[:150]} |")
        A("")

    A("## Timing")
    A("")
    for label, key in (("Opus baseline", BASELINE), ("Configured tiers", TIERED)):
        secs = sum((records[(key, t)].get("elapsed_s") or 0)
                   for t in tools if (key, t) in records)
        A(f"- **{label}:** {secs/60:.1f} minutes wall clock for {len(tools)} briefs")
    A("")

    A("## Limits of this benchmark")
    A("")
    A("- **One site, one run.** Results are for this evidence set. A site with "
      "different failure modes may shift the balance.")
    A("- **One sample per cell.** These models are not deterministic; the "
      "control section above is the only variance estimate here.")
    A("- **No correctness measurement.** Longer output is not better output, "
      "and a confident wrong answer scores well on every proxy in this file.")
    A("- **Prices are assumed list rates**, not billed amounts.")
    A("")

    target = out / "BENCHMARK.md"
    target.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {target}")
    print(f"baseline {money(bt['cost'])} -> tiered {money(tt['cost'])} "
          f"({pct(tt['cost'], bt['cost'])})")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
