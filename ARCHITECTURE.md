# ClauditSEO architecture

Four layers with strict boundaries:

```
crawler/fetcher → audit modules → [LLM analyst layer] → persistence
                                                          ↓
                                            dashboard/API → reports
```

The analyst layer is bracketed because it is optional at runtime: with no
provider configured the pipeline skips it and everything downstream works.
No module reaches around a layer. The audit engine never touches the
database; it returns typed results (`engine/types.py`) that the persistence
layer stores. The dashboard reads only from the API.

## Packages

```
clauditseo/
  crawler/      polite BFS crawler: robots policy, tier budgets, redirect
                tracking, sitemap + llms.txt metadata fetches
  engine/       types (Finding, SubScore, Site, fingerprint), module
                registry, deterministic scoring, orchestration core
  modules/      one file per dimension (TEC, ONP, PRF, CNT, OFP, LOC, AIS);
                registration at import time; shared PageFacts extractor
  providers/    optional external connectors behind a hub: backlinks (Moz,
                DataForSEO, OpenPageRank), Google (PageSpeed, CrUX, Search
                Console) — confidence-weighted merge, graceful degradation
  analysts/     evidence bundles, provider interface (Anthropic + mock),
                agentic tool loop (fetch_page / run_check / query_history,
                budget-bounded, error-tolerant), cache, ingest validation
  persistence/  repository layer — the only code that executes SQL
  db/           SQLite connection + numbered SQL migrations
  api/          FastAPI app + deterministic history chat
  reporting/    templates, honesty checks, generation
dashboard/      React/Vite operator UI (hash-routed, no extra runtime deps)
```

## Invariants worth knowing

- **Determinism**: `scoring.py` is pure — identical findings give identical
  scores. Weight renormalisation uses each module's own default weight, so
  new dimensions compose without engine edits (gate G3 proves zero-diff).
- **Fingerprints**: `sha256(dimension:check_id:normalised subject)` truncated
  to 24 hex chars (96 bits) — a deliberate collision/storage trade-off at
  this scale, not an oversight. They drive the open → fixed → regressed
  state machine and run diffs. Change a check's subject normalisation and
  you break history continuity — bump `ENGINE_VERSION` and say so in the
  changelog.
- **Scoring is rate-based** (engine 0.2.0): per-check deductions scale with
  the share of pages affected and cap at a per-severity ceiling, so scores
  are comparable across crawl sizes and no single check floors a dimension.
  Scores from engine 0.1.0 snapshots are NOT comparable — the trend chart
  distinguishes tiers, and history is hard-cut at the version boundary
  rather than backfilled.
- **Agent-loop token growth is quadratic**: the full conversation is resent
  each round, up to 8 rounds across 4 tasks. The in-loop budget check stops
  the spend, but a large T3 bundle can burn its ceiling on tool overhead —
  the tier-scaled extract caps and curated findings keep bundles small
  precisely to leave room for tool rounds.
- **Analyst findings are commentary**: source `model-judgement`, excluded
  from scoring by construction (`subscore()` filters on source) and from the
  state machine. Security notes from the injection scan are deterministic
  and DO join the state machine.
- **Multi-operator**: `operators` and ownership columns have existed since
  migration 0001, so P9's accounts landed with zero schema changes: hashed
  per-operator tokens, owner/member roles, repository-level client scoping
  (members get 404 on others' resources), open local mode until the first
  token exists. A token set under the retired `AUDITDECK_` name is detected
  and refused rather than ignored, because ignoring it would serve the API
  with no authentication at all.
- **Postgres port path**: migrations stick to the SQLite/Postgres common
  subset where practical; the repository layer is the seam. Porting means a
  connection factory + reviewing `PRAGMA`/`datetime('now')`/`rowid` usages —
  all confined to `db/` and `persistence/`.

## Tier contracts

| Tier | Pages | Wall clock | Paid APIs | Analysts |
|---|---|---|---|---|
| T1 Pulse | 3 | 2 min | never | never |
| T2 Standard | 100 | 15 min | no | if enabled, budget-capped |
| T3 Deep | 500 (hard cap) | 60 min (hard cap) | where keyed, cost-estimated first | if enabled, budget-capped |

## Gates

Every phase shipped behind a gate that still runs in `tests/`:

- G0 fresh clone → one command → seeded stack up (`scripts/dev.ps1|sh`)
- G1 robots-disallowed never fetched (server-log proof); budgets enforced
- G2 planted TEC/ONP defects all found, severities match, score deterministic
- G3 per-dimension defects caught; EXT module = zero engine diff
- G4 open → fixed → regressed lifecycle; three-point trend
- G5 keyless completeness, injection defence, cache = zero tokens, ingest
  rejection
- G6 dashboard e2e smoke incl. regression banner, analyst band, chat citation
- G7 no unsourced numbers; no narrative numbers absent from evidence
