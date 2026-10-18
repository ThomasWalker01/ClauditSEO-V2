# Is the deep tier worth paying for? — findings

Analyst commentary on the measurements in [`BENCHMARK.md`](BENCHMARK.md).
Kept in a separate file because `BENCHMARK.md` is regenerated from
`results.jsonl` and would overwrite anything written into it.

**Measured:** 24 calls — the 12 expert briefs in workbench phases 1–4, run
twice over audit run `3a337372` (a 100-page commercial site, 1.36 MB of
stored crawl evidence). Same evidence, same operator inputs, cache bypassed on
every call. The model is the only variable.

---

## 1. The headline, and why it is smaller than it looks

**$17.39 on Opus throughout → $5.93 on the shipped tiers. A 65.9% reduction
per full pass.**

That 66% understates what tiering does, because two of the twelve briefs are
*configured* to stay on Opus and did. Separating them:

| Group | Tools | Opus baseline | Configured | Change |
|---|---:|---:|---:|---:|
| Downgraded (standard + fast) | 10 | $13.23 | $1.78 | **−86.5%** |
| Left on deep by design | 2 | $4.16 | $4.15 | −0.3% |
| **All** | 12 | **$17.39** | **$5.93** | **−65.9%** |

So the real finding is: **where tiering is applied it removes ~86% of the
cost, and the remaining bill is dominated by the two briefs deliberately kept
on Opus.** Those two are 2 of 12 briefs but **70% of the tiered spend.**

Wall clock fell from **35 to 23 minutes** for a full pass. On the ten
downgraded briefs alone it roughly halved.

## 2. The control — why these numbers can be trusted

`cannibalisation-map` and `entity-graph` ship on the deep tier, so they ran
**Opus in both passes**. Their spread is pure run-to-run variance:

| Tool | Cost Δ | Token Δ | Word Δ |
|---|---:|---:|---:|
| `cannibalisation-map` | +3.1% | +1.8% | +4.8% |
| `entity-graph` | −4.8% | −2.7% | −3.2% |

**The noise floor is roughly ±5%.** The 82–95% reductions elsewhere are around
17–19× that, so they are real effects and not sampling artefacts.

This also calibrates the quality proxies, which matters more. Word count
varies ±5% between two runs of the *same* model on the *same* input.
Any word-count gap below ~5% is meaningless; the 19–59% reductions on the
downgraded briefs sit far outside it and are genuine.

## 3. What the cheaper tiers actually gave up

Nothing truncated. No call failed. All 24 returned complete reports. But the
cheaper models wrote materially less, and the loss is not evenly distributed.

**Cost tracks output length, not input size.** `url-hygiene` cost double
`crawl-health` on *fewer* total tokens, purely because it wrote four times as
much. Output is priced ~5× input, so the saving compounds: a cheaper model at
a lower rate that also writes shorter answers multiplies the two effects.
That is where the 86% comes from — not from the rate card alone.

### The real concern: cited URLs

For an SEO audit the specific affected URLs are the actionable payload. Sonnet
consistently cited fewer of them:

| Tool | URLs cited (Opus → Sonnet) |
|---|---|
| `url-hygiene` | 36 → 6 (**−83%**) |
| `migration-redirects` | 16 → 3 (−81%) |
| `crawl-health` | 37 → 17 (−54%) |
| `https-security` | 24 → 11 (−54%) |
| `js-rendering` | 21 → **33** (+57%) |
| `image-optimisation` | 3 → **17** (+467%) |

Mostly down, sometimes sharply — but not uniformly, and two went up. A report
that diagnoses the same issue while naming six affected pages instead of
thirty-six is cheaper *and* less useful, because the operator has to rediscover
the rest by hand. **This is the strongest argument found for keeping the deep
tier on inventory-style briefs.**

### A false alarm worth recording

`onpage-hygiene` on Haiku flagged 7 unverified figures against Opus's 1, which
looks like fabrication. It is not. Inspected in context, the numbers are
`120–160 characters` and `10–15 characters` — standard SERP thresholds stated
in the rationale, not invented claims about the site. **The ungrounded-figure
detector counts numbers in advisory prose as well as in claims about
evidence.** The count is not usable as a fabrication signal without reading
the hits.

### Where the cheap tier lost nothing

`onpage-hygiene` on **Haiku**: −95.1% cost, −1.5% words, more headings, more
URLs cited, 42s → 27s. **Twenty times cheaper for output of comparable shape.**
This is the clearest win in the set and suggests the fast tier is currently
under-used — applying a fixed checklist to one page is exactly the job a small
model does well.

## 4. Answering the question directly

**Is the deep tier worth paying for?** On this evidence, for these twelve
briefs:

- **No, for the eight standard-tier briefs.** They reached the same verdicts
  for ~14% of the cost. The gap is length and URL enumeration, not detection.
- **Emphatically no for `onpage-hygiene`.** Haiku matched Opus's output shape
  at 1/20th the price.
- **Unproven for the two deep-tier briefs**, which were never compared against
  a cheaper model — both passes ran Opus. `cannibalisation-map` and
  `entity-graph` are 70% of the remaining spend and **the obvious next
  experiment is to run them on Sonnet.** This benchmark cannot say whether
  keeping them on Opus is justified; it only shows they are what you are
  paying for.

### The one qualitative comparison done by reading

On `crawl-health`, both models produced an identical summary table (robots
Pass, sitemap Warn, HTTP Pass, redirects Pass) and both raised one finding,
`sitemap-coverage`, at Medium. Same verdict, $0.52 vs $0.079. The differences:

- **Opus reconciled in both directions** (crawl→sitemap *and* sitemap→crawl),
  surfacing 7 sitemap URLs the crawler never reached and flagging them as
  possible orphans. Sonnet ran one direction and recorded orphan status as
  `[TO CONFIRM]`. Opus found a category of problem Sonnet did not.
- **Sonnet was stricter about certainty.** Opus called 22 URLs "confirmed"
  absent from the sitemap when only 100 of 268 entries were visible — they
  could be among the unshown 168. Sonnet said exactly that.

These pull in opposite directions. The deep model did more analysis; the
cheaper one was better calibrated about its own evidence.

## 5. What this benchmark cannot tell you

- **No correctness measurement.** Every proxy here is countable, none is
  correctness. A confident wrong answer scores well on all of them. Settling
  this needs the hand-labelled golden set (open task).
- **Only 1 of 12 briefs produces machine-comparable findings.**
  `crawl-health` uses coded findings with explicit severities; the other
  eleven answer in prose, numbered headings, or severity-columned tables. So
  **ClauditSEO cannot currently automate quality regression testing across
  models** — every tier decision beyond `crawl-health` needs a human reading
  two reports. That is a product gap, not a benchmark artefact.
- **One site, one run, one sample per cell.** The control gives a variance
  estimate for Opus only; Sonnet and Haiku were each run once.
- **Prices are assumed list rates**, not billed amounts. Re-cost with
  `--prices` against a real invoice; no re-run needed.

## 6. Recommended next steps

1. **Run `cannibalisation-map` and `entity-graph` on Sonnet.** They are 70% of
   the tiered bill and the only briefs whose tier is untested. Roughly $4 to
   find out.
2. **Check whether the URL-enumeration loss matters** by reading the two
   `url-hygiene` reports (36 cited URLs vs 6). If it does, that brief belongs
   on the deep tier regardless of the 91% saving.
3. **Consider moving more briefs to the fast tier.** Haiku's result on
   `onpage-hygiene` suggests `fast` is under-used for checklist-style work.
4. **Standardise finding output across briefs** so quality comparison can be
   automated rather than read.
