# ClauditSEO

Self-hosted SEO auditing suite. Staged audits (any subset of dimensions × one
depth tier), a full client and finding history so results are comparable
across time, evidence-first reporting, and an optional LLM analyst layer that
adds judgement without ever touching the deterministic score.

## Install

Needs **Python 3.12+** and **Node 18+**.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

macOS / Linux:

```bash
bash scripts/dev.sh
```

That one command creates the virtualenv, installs dependencies, applies
database migrations, seeds demo data, builds the dashboard, and serves
everything on **http://localhost:8020**.

### Keeping the server up (Windows)

A server started from a terminal belongs to that terminal's process tree and
dies with it — closing the shell, restarting your editor or ending an agent
session all take it down. To run it as a proper background service instead:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-service.ps1
```

That registers a per-user scheduled task which starts ClauditSEO at logon,
restarts it if it crashes, and starts it immediately. It runs under the Task
Scheduler service, so nothing in a terminal can take it with it. Output goes
to `data/server.log`. Remove it with `scripts\uninstall-service.ps1`.

## Your first audit in five minutes

1. Bootstrap as above and open http://localhost:8020.
2. Click a client (two demo clients are seeded) or add your own, then add a
   site with its domain and business type.
3. Open the site → **launch audit**. Pick dimensions and a tier:
   - **auto (Adaptive, the default)** — a free pulse scores every dimension,
     then escalates only what needs it: ≥95 stops, 80–94 gets a full crawl,
     60–79 adds that dimension's analyst, <60 goes deep with paid APIs where
     keyed. Regressions always escalate; unchanged dimensions are not
     re-spent on (hysteresis). Bands configurable via `CLAUDITSEO_BAND_*`.
   - **T1 Pulse** — homepage + robots + sitemap head; under two minutes; never
     calls paid APIs or the analyst layer.
   - **T2 Standard** — up to 100 pages, every applicable free check.
   - **T3 Deep** — up to 500 pages plus paid APIs where keys exist (hard caps:
     500 pages / 60 minutes, so nothing can run away).
4. Watch the run finish, then explore: score trend, dimension breakdown with
   visible weights, findings by state, run-to-run comparison, regression
   banner, and the report generator.

Or from the terminal:

```bash
clauditseo audit run --client "Acme Plumbing" --site acmeplumbing.example --dims ONP,TEC --tier T2
```

## Audit dimensions

| Code | Dimension | Notes |
|---|---|---|
| TEC | Technical | robots, sitemaps + coverage, status codes, redirect chains, HTTPS, security headers, indexability, viewport |
| ONP | On-Page | titles/metas + duplication, headings, alt coverage, canonicals, structured-data validity |
| PRF | Performance | CWV via PageSpeed/CrUX when keyed; local timing signals (low confidence) otherwise |
| CNT | Content | thin/duplicate content, readability, text-to-template ratio |
| OFP | Off-Page | backlink profile via pluggable providers; honest not-assessed when keyless |
| LOC | Local | NAP consistency, LocalBusiness schema, location-page quality (applies to local businesses; weight redistributes otherwise) |
| AIS | AI-Surface | AI-crawler access, llms.txt, answer-extractability structure |

Adding a dimension requires zero engine changes — implement the three-method
module interface and register it (see `tests/test_engine_g3.py::ExtModule`
for a complete example).

Scoring is deterministic: identical findings in, identical score out. Weights
are always shown next to sub-scores, and analyst findings never enter the
composite.

## API keys (all optional)

Everything degrades gracefully: a missing key lowers confidence tags and
renders `[TO CONFIRM: …]` in reports — it never breaks a run or invents a
number. Keys live in environment variables only, never in the database.

| Variable | Enables |
|---|---|
| `CLAUDITSEO_PAGESPEED_KEY` | Core Web Vitals lab data (PageSpeed Insights) |
| `CLAUDITSEO_CRUX_KEY` | Real-user CWV field data (Chrome UX Report) |
| `CLAUDITSEO_MOZ_TOKEN` | Backlink metrics (Moz Links API) |
| `CLAUDITSEO_OPENPAGERANK_KEY` | Free domain-authority signal |
| `CLAUDITSEO_DATAFORSEO_LOGIN` / `_PASSWORD` | Backlink summary (DataForSEO) |
| `CLAUDITSEO_GOOGLE_SA_FILE` | Search Console (service-account JSON; also needs `pip install google-auth`) |
| `ANTHROPIC_API_KEY` | The LLM analyst layer and its models |

Multi-source data merges confidence-weighted: the highest-confidence source
wins per metric and every value records where it came from.

## From hygiene checks to advice

The deterministic dimensions are hygiene checks: they tell you a page has no
H1, a title outside the length guideline, or a canonical pointing elsewhere.
They deliberately do not judge whether the H1 you have is any *good*.

That judgement is the **page advisor**, reached from any page in a run
(Issues by cause → expand a check → *inspect page* → *Advise on this page*).
It recommends the H1, title tag, meta description and the answer line that
sits beneath the heading, with ranked alternatives — triaging first on
whether the page is commercial, part of a hub-and-spoke structure, YMYL, or
search-facing, and only running the modules those axes call for. It fetches
the page live, may pull a sibling page to verify a cannibalisation claim
before making it, keeps unverified figures and outcome claims out of the
recommended copy, and flags brand-coined terms as unverified when no
keyword provider is configured. One page per call, budget-capped
(`CLAUDITSEO_LLM_BUDGET_PAGE`, default 60,000 tokens), cached by page
content.

## The analyst layer

Optional judgement on top of the deterministic engine: four analyst agents
(E-E-A-T, search intent, answer-extractability, and a prioritisation
narrative) plus a read-only history chat. The analysts are genuinely agentic:
each can call tools mid-analysis — fetch a page from the audited site,
re-run a single deterministic check, or query the site's stored run history —
and the loop continues until the model decides it is done. Ground rules, all
enforced in code and gated by tests:

- Analysts see an evidence bundle (findings + capped page extracts) plus
  tightly contained tools — never the open web. Tool fetches are limited to
  the audited host, honour robots.txt, and have their own per-run budget.
  All crawled or fetched content is treated as untrusted data;
  instruction-like text planted in pages is surfaced as a security-note
  finding and provably influences nothing.
- Analyst findings carry `model-judgement` source, the model id, a confidence
  band and evidence citations. Uncited findings — and findings containing any
  figure not present verbatim in the bundle — are rejected at ingest.
- Results are cached by (task, model, evidence hash): re-running against
  unchanged pages spends zero tokens, proven in the run's cost log.
- Budgets: T1 never invokes analysts. T2 caps at `CLAUDITSEO_LLM_BUDGET_T2`
  (default 50,000 tokens), T3 at `CLAUDITSEO_LLM_BUDGET_T3` (default 200,000).
  Estimated spend prints before execution; over-budget tasks are cut from the
  tail (the prioritisation narrative is last to be cut), never half-run.

No key? The whole suite works; the analyst band is simply absent. Set
`CLAUDITSEO_LLM_PROVIDER=mock` to demo the analyst UI keyless and token-free.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CLAUDITSEO_DB` | `data/clauditseo.db` | SQLite file location |
| `CLAUDITSEO_PORT` | `8020` | API + dashboard port |
| `CLAUDITSEO_TOKEN` | unset | Set to require operator token login |
| `CLAUDITSEO_LOCALE` | `en-AU` | Default locale for new sites |
| `CLAUDITSEO_LLM_MODEL` | `claude-sonnet-5` | Analyst model |

## Operators and multi-user

ClauditSEO starts in **open local mode**: no tokens, no login. Two ways to
lock it down:

- `CLAUDITSEO_TOKEN=<secret>` — single shared operator token (full access).
- **Operator accounts** — `clauditseo operator add --name "Avery" --role member`
  creates an account and prints its login token once (only a SHA-256 hash is
  stored). As soon as any operator has a token, the API requires login.
  Roles: `owner` sees every client; `member` sees only clients they created —
  other clients' data answers 404, never leaking existence.
  `clauditseo operator list` shows accounts.

For porting to a hosted platform: all SQL lives in `clauditseo/persistence/`
and `clauditseo/db/`, migrations stick to the SQLite/Postgres common subset
where practical, and ownership scoping is already enforced at the repository
layer — see ARCHITECTURE.md for the port checklist.

## Backup and restore

All data is one SQLite file (`data/clauditseo.db` plus its `-wal`/`-shm`
sidecars while the server runs). To back up: stop the server, copy the file.
To restore: stop the server, put the copy back, start again. Migrations apply
automatically on next start. Generated reports live under `reports/out/`.

## Client data care

The database holds client business information. It stays local by default:
no third-party telemetry, no credentials in the database, keys in environment
variables only. Operators storing personal information of Australian clients
should consider their obligations under the Privacy Act 1988 (Australian
Privacy Principles).

The crawler is polite by design: robots.txt always honoured (a 5xx robots
response means fetch nothing), an identifiable `ClauditSEOBot` user agent,
rate-limited requests, and hard page/time budgets per tier. It never
circumvents auth walls or CAPTCHAs.

## Reading this repository

The tests are the design record, not a coverage exercise. Over 4,200 clauses
run from a clean checkout, and the docstring above each one says what it is
holding and why - the defect that caused it, the number it was measured at,
and, where there was one, the approach that was tried and rejected. If you
want to know why something has the shape it has, the guard over it is usually
a better answer than the code.

Three that show the pattern, chosen because each records something that would
otherwise be invisible:

- `tests/test_the_legend_keys_what_is_on_the_screen.py` opens by saying which
  half of the change request that produced it was wrong, and why the clause
  nobody asked for matters more than the reported one.
- `tests/test_the_way_up_is_on_every_part.py` records a contrast defect
  introduced by its own fix, caught on rendered pixels, along with the
  measured ratios before and after.
- `tests/test_the_export_script_verifies_what_it_produces.py` states the one
  property it exists for - that a refused export leaves nothing behind - and
  records a fixture that was wrong when the guard first ran.

Two conventions are worth knowing before reading them:

- **A clause is proven red before it is trusted.** A guard that has only ever
  passed is not yet evidence, so the defect is reintroduced and the failure
  message read. Where that mattered, the docstring says so.
- **When a guard is wrong, it is amended with its reasoning, not loosened.**
  Several clauses here have been changed because the behaviour they asserted
  turned out to be the defect; they carry both the old claim and the
  instruction that replaced it, so the next reader sees a decision rather
  than a number that drifted.

Layout and layer rules are in [ARCHITECTURE.md](ARCHITECTURE.md); the
release-by-release story is in [CHANGELOG.md](CHANGELOG.md).

## Development

```bash
.venv/Scripts/pytest                    # full suite, includes all phase gates
cd dashboard && npm run build           # type-check + build the dashboard
cd dashboard && npm run dev             # Vite dev server (proxies /api to 8020)
```

The console script, not `python -m pytest`: the module form puts the working
directory on `sys.path` and the console script does not. Several guards here
check that the tree behaves like a stranger's checkout, and the interpreter
quietly adding the root to the path is the difference between testing that
and rehearsing it.

**What skips on a fresh clone, and why.** Two groups of tests report `s`
rather than running, and both are honest rather than broken:

- **The rendered tests** need a built dashboard and a browser. Run
  `npm run build` in `dashboard/` and `playwright install chromium` first;
  until then they skip, because they serve `dashboard/dist` and assert against
  what a browser actually painted.
- **A handful of guards read a register this repository does not carry** - the
  author's audit log and working notes, which are not part of the product.
  They name it in their skip reason. See `tests/private_register.py`.

Everything else runs from a clean checkout.

The phase gates (G0–G7) live in `tests/` alongside the clauses described
in [Reading this repository](#reading-this-repository).
