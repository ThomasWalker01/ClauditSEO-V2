# Deep tier vs configured tiers — cost and quality benchmark

- **Target run:** `3a33737219d7464489a19b6acac18179`  (a 100-page commercial
  roofing site; the client is not named, and item 187 keeps it that way)
- **The measurements below are all this ships.** The 24 report bodies this
  run produced, and `results.jsonl` that `benchmark_report.py` regenerates
  this file from, are a real client's audit content and are excluded from
  the public tree by `PUBLIC_EXCLUDE.txt`. The regeneration command further
  down will therefore not run here; the figures it produced are kept as
  written, because the conclusion is the part worth publishing.
- **Scope:** every expert brief in workbench phases 1–4 (12 tools), run twice
- **Pass A `opus-baseline`:** every tool forced onto the deep model
- **Pass B `configured-tiers`:** every tool on the tier it ships with
- Same audit run, same stored crawl evidence, same operator inputs in both passes. The model is the only variable.

## How to read this

**Token counts are measured.** They come from the API's own usage figures, recorded per call, input and output separately.

**Dollar figures are derived, not billed.** They apply the rate table below to those token counts. The rates are list prices entered as an assumption — nothing here reads an invoice. Re-cost against a real bill without re-running anything:

```
python scripts/benchmark_report.py --prices "claude-opus-5:15.00/75.00,..."
```

**The analyst cache was bypassed for every call.** Otherwise the second pass would replay the first, report zero tokens, and show a fictitious 100% saving.

| Model | Input $/M | Output $/M |
|---|---:|---:|
| `claude-haiku-4-5-20251001` | 1.00 | 5.00 |
| `claude-opus-5` | 15.00 | 75.00 |
| `claude-sonnet-5` | 3.00 | 15.00 |

## Per-tool comparison

| Tool | Tier | Baseline model | Baseline tokens | Baseline $ | Tiered model | Tiered tokens | Tiered $ | Cost change |
|---|---|---|---:|---:|---|---:|---:|---:|
| `crawl-health` | standard | claude-opus-5 | 16,702 | $0.52 | claude-sonnet-5 | 14,995 | $0.08 | -84.9% |
| `indexability` | standard | claude-opus-5 | 25,544 | $0.72 | claude-sonnet-5 | 24,365 | $0.13 | -82.5% |
| `url-hygiene` | standard | claude-opus-5 | 19,934 | $1.10 | claude-sonnet-5 | 11,677 | $0.10 | -91.2% |
| `js-rendering` | standard | claude-opus-5 | 44,481 | $1.54 | claude-sonnet-5 | 37,899 | $0.21 | -86.4% |
| `https-security` | standard | claude-opus-5 | 26,450 | $1.31 | claude-sonnet-5 | 18,064 | $0.15 | -88.3% |
| `site-architecture` | standard | claude-opus-5 | 94,122 | $3.20 | claude-sonnet-5 | 77,783 | $0.48 | -85.0% |
| `hreflang` | standard | claude-opus-5 | 10,229 | $0.61 | claude-sonnet-5 | 7,660 | $0.08 | -86.3% |
| `migration-redirects` | standard | claude-opus-5 | 37,519 | $1.43 | claude-sonnet-5 | 26,641 | $0.18 | -87.6% |
| `onpage-hygiene` | fast | claude-opus-5 | 29,412 | $0.64 | claude-haiku-4-5 | 21,761 | $0.03 | -95.1% |
| `cannibalisation-map` | deep | claude-opus-5 | 61,475 | $2.36 | claude-opus-5 | 62,556 | $2.43 | +3.1% |
| `image-optimisation` | standard | claude-opus-5 | 54,048 | $2.15 | claude-sonnet-5 | 46,153 | $0.35 | -84.0% |
| `entity-graph` | deep | claude-opus-5 | 42,617 | $1.81 | claude-opus-5 | 41,454 | $1.72 | -4.8% |
| **Total** | | | **462,533** | **$17.39** | | **391,008** | **$5.93** | **-65.9%** |

### Totals

| | Input tokens | Output tokens | Total | Cost |
|---|---:|---:|---:|---:|
| Opus baseline | 288,279 | 174,254 | 462,533 | $17.39 |
| Configured tiers | 265,892 | 125,116 | 391,008 | $5.93 |
| **Saved** | | | | **$11.46** (-65.9%) |

Running all 12 phase 1–4 briefs costs **$17.39** on the deep model against **$5.93** on the shipped tiers — a **66% reduction** per full pass.

## The control: tools that ran the same model twice

2 tool(s) ship on the deep tier already, so both passes used the same model. Their spread is pure run-to-run variance, and it sets the bar: any difference smaller than this between models is noise, not evidence.

| Tool | Model | Tokens A | Tokens B | Δ | Words A | Words B | Δ |
|---|---|---:|---:|---:|---:|---:|---:|
| `cannibalisation-map` | claude-opus-5 | 61,475 | 62,556 | +1.8% | 8623 | 9040 | +4.8% |
| `entity-graph` | claude-opus-5 | 42,617 | 41,454 | -2.7% | 5371 | 5199 | -3.2% |

## What the cheaper tiers gave up

These are **countable properties of the output, not a quality score.** Deciding whether a finding is *correct* needs hand-labelled ground truth, which this benchmark does not have. Both sets of reports are saved under `benchmarks/reports/` for side-by-side reading.

| Tool | Model change | Words | Headings | Table rows | URLs cited | `[TO CONFIRM]` | Unverified figures | Truncated |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `crawl-health` | claude-opus-5 → claude-sonnet-5 | 1,233 → 866 (-29.8%) | 1 → 1 | 14 → 14 | 37 → 17 | 0 → 1 | 3 → 3 | no |
| `indexability` | claude-opus-5 → claude-sonnet-5 | 2,314 → 1,788 (-22.7%) | 0 → 0 | 9 → 9 | 3 → 1 | 5 → 3 | 2 → 3 | no |
| `url-hygiene` | claude-opus-5 → claude-sonnet-5 | 4,800 → 1,979 (-58.8%) | 26 → 21 | 59 → 21 | 36 → 6 | 2 → 4 | 8 → 7 | no |
| `js-rendering` | claude-opus-5 → claude-sonnet-5 | 4,903 → 2,646 (-46.0%) | 16 → 8 | 40 → 29 | 21 → 33 | 4 → 1 | 8 → 8 | no |
| `https-security` | claude-opus-5 → claude-sonnet-5 | 5,509 → 2,886 (-47.6%) | 16 → 29 | 13 → 11 | 24 → 11 | 2 → 1 | 5 → 0 | no |
| `site-architecture` | claude-opus-5 → claude-sonnet-5 | 11,358 → 7,148 (-37.1%) | 48 → 17 | 244 → 125 | 0 → 0 | 39 → 27 | 8 → 8 | no |
| `hreflang` | claude-opus-5 → claude-sonnet-5 | 3,167 → 2,109 (-33.4%) | 7 → 7 | 39 → 14 | 4 → 2 | 5 → 2 | 8 → 3 | no |
| `migration-redirects` | claude-opus-5 → claude-sonnet-5 | 5,659 → 3,023 (-46.6%) | 8 → 9 | 56 → 36 | 16 → 3 | 26 → 13 | 8 → 7 | no |
| `onpage-hygiene` | claude-opus-5 → claude-haiku-4-5 | 1,232 → 1,213 (-1.5%) | 4 → 6 | 11 → 11 | 5 → 6 | 0 → 0 | 1 → 7 | no |
| `image-optimisation` | claude-opus-5 → claude-sonnet-5 | 7,559 → 6,090 (-19.4%) | 12 → 12 | 63 → 62 | 3 → 17 | 23 → 6 | 8 → 8 | no |

## Did they find the same things?

Issue codes raised by each pass, compared as sets. Word counts say how much a model wrote; this says whether it reached the same conclusions. A tool where both passes raise identical codes at identical severities is one where the deep tier bought length, not detection.

Only briefs that ask for backticked issue codes carrying an explicit severity can be compared this way. The rest answer in prose or in severity-columned tables, and are listed below as not extractable rather than forced through a regex that would invent findings.

| Tool | Codes (baseline) | Codes (tiered) | Both | Baseline only | Tiered only | Severity disagreements |
|---|---:|---:|---:|---|---|---|
| `crawl-health` | 1 | 1 | 1 | — | — | — |
| **Total** | | | **1** | **0** | **0** | |

**Not extractable (11 of 12):** `indexability`, `url-hygiene`, `js-rendering`, `https-security`, `site-architecture`, `hreflang`, `migration-redirects`, `onpage-hygiene`, `cannibalisation-map`, `image-optimisation`, `entity-graph`. These briefs do not answer with coded findings, so their two reports must be compared by reading them side by side in `benchmarks/reports/`. No score is invented for them here.

The two passes agreed on **1 of 1** distinct issue codes (100%). 0 were raised only by the deep model and 0 only by the configured tiers.

> Set overlap is not correctness. Both passes can miss the same real issue, and agreement between two models is not evidence that either is right. This measures consistency, which is all it can measure without hand-labelled ground truth.

## Timing

- **Opus baseline:** 35.4 minutes wall clock for 12 briefs
- **Configured tiers:** 22.6 minutes wall clock for 12 briefs

## Limits of this benchmark

- **One site, one run.** Results are for this evidence set. A site with different failure modes may shift the balance.
- **One sample per cell.** These models are not deterministic; the control section above is the only variance estimate here.
- **No correctness measurement.** Longer output is not better output, and a confident wrong answer scores well on every proxy in this file.
- **Prices are assumed list rates**, not billed amounts.
