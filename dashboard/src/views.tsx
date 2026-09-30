import { PrimaryButton, SecondaryButton } from "./buttons";
import { Working } from "./working";
import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import {
  api, ApiError, ClientDetail, ClientSummary, Finding, FindingState, Meta, Run,
  Severity, SiteDetail,
  completedAudits, hasResults, hasScore, isDeletable, isInFlight, isSiteReading,
  useFetch,
} from "./api";
import { goHandler as navHandler, goto as navigate, historyRunFromHash, withPart } from "./nav";
import { stamp } from "./client_lanes";
import { PrecheckPanel, pagesGone, usePrecheck } from "./precheck";
import { ScanMatrix } from "./scanmatrix";
import { DangerButton, SpendButton, SpendTarget } from "./spend";
import { ENTRIES, Legend } from "./glossary";
import { pathKey } from "./population";
import {
  AnalystBand, Card, CopyCmd, ErrorNote, FindingsTable, GroupedFindings, Loading,
  PriorityPlan, ProviderStatus, ScoreBadge, SeverityTag,
  NarrowRunNote, RunScore, RunStatusChip, ScoreBandKey, UrlLinks, money,
  pathOf, SpendMark } from "./components";
import { AnatomyView, SiteLanding, StandingHeader, isPart, useAnatomy } from "./anatomy";
import { PrecheckPane } from "./pane_precheck";
import { LegendStrip, SidebarPane } from "./legend_strip";
import { CatalogueDrawer, CatalogueFab } from "./catalogue";
import {
  FixCol, FixState, FixTick, MarkBar, StateNote, useSeed,
} from "./fixloop";
import { AuditPane } from "./pane_audit";
import { AnalysePane } from "./pane_analyse";
import { costsAcross } from "./cost";
import { PAGE, RecordPane } from "./pane_record";
import { PageAdvice, SchemaAuditPanel } from "./advice";
import { ReportView as RenderedMarkdown } from "./markdown";
import { Pill } from "./pill";
// Only the page-scoped panel survives here: it takes a URL, which the
// site-wide list has no notion of. The five site-scoped ExpertSpec arrays it
// used to import are gone — each restated a tool's name, blurb and tier, so
// the same tool read differently depending on which screen you stood on.
import { ExpertPanel, ExpertSpec } from "./expert";
import { useAnalyses } from "./analyses";
import { useSelection } from "./selection";

// Quick single-purpose audits launchable straight from the client screen.
/** The scope each crawler tier covers (channel ruling 20260918-0410): the words
 *  a reader chooses by, where the by-hand launcher still posts a tier. */
const SCOPE_WORD: Record<string, string> = {
  auto: "Adaptive", T1: "Page", T2: "Site", T3: "Full",
};

const QUICK_AUDITS: { label: string; dims: string[]; tier: string; title: string }[] = [
  // SEC joins "everything" at item 143 step BD, when Security & transport
  // left TEC for a dimension of its own.
  { label: "Pulse", dims: ["TEC", "ONP", "PRF", "CNT", "OFP", "LOC", "AIS", "SEC"],
    tier: "T1", title: "Everything, homepage-only, under two minutes" },
  { label: "Technical", dims: ["TEC", "PRF", "SEC"], tier: "T2",
    title: "Technical, performance and security, up to 100 pages" },
  { label: "On-Page", dims: ["ONP", "CNT"], tier: "T2",
    title: "On-page + content, up to 100 pages" },
  { label: "AI-Surface", dims: ["AIS"], tier: "T1",
    title: "AI crawler access, llms.txt, extractability" },
  { label: "Adaptive", dims: ["TEC", "ONP", "PRF", "CNT", "OFP", "LOC", "AIS", "SEC"],
    tier: "auto",
    title: "Default mode: cheap pulse first, then escalates only the dimensions "
      + "scoring below the health bands (95/80/60), analysts included automatically" },
];

// Re-exported name kept so this file's five call sites read as they did;
// the behaviour now comes from `nav.ts`, which is the only place a hash
// is assigned. See its header for why assigning is not enough.
const goto = navigate;

// ---- clients ---------------------------------------------------------------

// The client list view is retired and its delete moved to Home (item 169).

export function ClientDetailView({ clientId }: { clientId: string }) {
  const [tick, setTick] = useState(0);
  const { data, error, loading, retry } = useFetch<ClientDetail>(`/api/clients/${clientId}`, tick);
  const { data: meta } = useFetch<Meta>("/api/meta");
  const [domain, setDomain] = useState("");
  const [businessType, setBusinessType] = useState("");
  // `tick` above re-reads this client. The picker in the app chrome lists
  // every client's sites and does not hear about it — the second of the two
  // places a site can be created.
  const { refreshSites } = useSelection();

  const quickTitle = (q: (typeof QUICK_AUDITS)[number]): string => {
    if (!meta) return q.title;
    const wanted = [...new Set(q.dims.flatMap((d) => meta.dimension_providers[d] ?? []))];
    const missing = wanted.filter((name) => !meta.providers[name]?.configured);
    if (!missing.length) return q.title;
    const hints = missing.map((name) => `${name} (${meta.providers[name].env})`);
    return `${q.title}. Optional tools not configured: ${hints.join(", ")} — `
      + "runs anyway at lower confidence. Set them in Admin -> Provider keys.";
  };

  const [launching, setLaunching] = useState<string | null>(null);

  const addSite = async (e: FormEvent) => {
    e.preventDefault();
    if (!domain.trim()) return;
    await api.post(`/api/clients/${clientId}/sites`,
                   { domain: domain.trim(), business_type: businessType || null });
    setDomain("");
    setTick((t) => t + 1);
    refreshSites();
  };

  const quickAudit = async (siteId: string, q: (typeof QUICK_AUDITS)[number]) => {
    setLaunching(`${siteId}:${q.label}`);
    try {
      const resp = await api.post<{ run_id: string }>(`/api/sites/${siteId}/audits`,
                                                      { dims: q.dims, tier: q.tier });
      goto(`#/runs/${resp.run_id}`);
    } finally {
      setLaunching(null);
    }
  };

  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!data) return <Loading />;
  return (
    <>
      <h2>{data.name}</h2>
      {data.notes && <p className="muted">{data.notes}</p>}
      <form onSubmit={addSite} className="inline-form">
        <input value={domain} onChange={(e) => setDomain(e.target.value)}
               placeholder="example.com.au" aria-label="new site domain" />
        <select value={businessType} onChange={(e) => setBusinessType(e.target.value)}
                aria-label="business type">
          <option value="">business type…</option>
          {(meta?.business_types ?? []).map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <SecondaryButton submit>Add site</SecondaryButton>
      </form>
      <ScoreBandKey />
      <table className="findings">
        <thead>
          <tr><th>Site</th><th>Latest score</th><th>Audits</th><th>Open</th>
              <th>Regressions</th><th>Quick audit</th></tr>
        </thead>
        <tbody>
          {data.sites.map((s) => (
            <tr key={s.id} className="linked-row">
              <td><a className="row-link" href={`#/sites/${s.id}`}>{s.domain}</a></td>
              <td><ScoreBadge score={s.latest_score} /></td>
              <td>{s.run_count}</td>
              <td>{s.open_findings}</td>
              <td>{s.regressions > 0
                   ? <strong className="regressed">{s.regressions}</strong> : 0}</td>
              <td>
                <SecondaryButton
                        title="The full tool menu, in working order"
                        onClick={() => goto(`#/sites/${s.id}/workbench`)}>
                  workbench
                </SecondaryButton>
                {/* UX-66, and the worst shape of it: the caption swapped to
                    a bare ellipsis, so the control's accessible name became
                    "…" rather than merely a different name. The label stays;
                    `aria-busy` carries the state, and the region under the
                    table says it in words — once for every row, since
                    `launching` admits one press at a time. */}
                {/* Item 178: each starts an audit on one press, so each is
                    priced in words and confirmed, naming the site and scope. */}
                {QUICK_AUDITS.map((q) => (
                  <SpendButton key={q.label} price={null}
                               busy={launching === `${s.id}:${q.label}`}
                               why={launching !== null && launching !== `${s.id}:${q.label}`
                                 ? "another audit is launching" : null}
                               confirm={{ title: `Start a ${q.label} audit of ${s.domain}?`,
                                          body: <><p>{quickTitle(q)}.</p>
                                            <p>Depth {q.tier === "auto" ? "chosen as it goes" : q.tier};
                                              dimensions {q.dims.join(", ")}.</p></>,
                                          action: `Start ${q.label}` }}
                               onSpend={() => quickAudit(s.id, q)}>
                    {q.label}
                  </SpendButton>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* UX-66. One region for every quick-audit control in the table above,
          mounted unconditionally and empty while idle. It names the site and
          the tier because the controls are identical row to row. */}
      <div className="muted" role="status" aria-live="polite">
        {launching && <Working>{`Launching ${launching.split(":").slice(1).join(":")} `
          + `for ${data.sites.find((s) => s.id === launching.split(":")[0])
                    ?.domain ?? "this site"}…`}</Working>}
      </div>
      {!data.sites.length && <p className="muted">No sites yet — add one above.</p>}
    </>
  );
}

/** Ask a running crawl to stop (relay item 136a).
 *
 *  Two presses are one stop: the request is a set membership on the
 *  server, so pressing again after it has been asked changes nothing.
 *
 *  **The caption does not change** — UX-66, and this repository's fourth
 *  and fifth controls to be written this way deliberately. A button's
 *  label is its accessible name, so a name that swaps mid-press is
 *  announced as a *different control appearing*: the operator who pressed
 *  one button is told another now has focus. The state is said beside it,
 *  in a region mounted ahead of its content so there is something for
 *  assistive technology to observe a change against. `reports.tsx` wrote
 *  the reason down at UX-64 and `views.tsx` took it again at UX-88 and
 *  UX-96; writing "stopping…" into the label here would have been a fifth
 *  instance of a defect three rounds have removed.
 */
function StopRun({ runId, onStopped }: { runId: string; onStopped: () => void }) {
  const [asked, setAsked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="stop-run">
      {error && <span className="muted stop-error">{error}</span>}
      {/* Mounted whether or not it has anything to say, so the words
          arriving are a change to observe rather than a new element. */}
      <span className="muted stop-state" role="status" aria-live="polite">
        {asked ? <Working>stopping at the next page</Working> : ""}
      </span>
      {/* Item 183: stopping keeps what was fetched - nothing is removed - so it
          is a plain action, with its consequence in text rather than a title. */}
      <SecondaryButton className="stop-btn" disabled={asked}
              aria-describedby="stop-run-note"
              onClick={async () => {
                setAsked(true);
                setError(null);
                try {
                  await api.post(`/api/runs/${runId}/stop`, {});
                  onStopped();
                } catch (e) {
                  setAsked(false);
                  setError((e as Error).message);
                }
              }}>
        stop
      </SecondaryButton>
      <span id="stop-run-note" className="muted">Stops at the next page; what it has fetched is kept.</span>
    </span>
  );
}


// ---- site ------------------------------------------------------------------


/** What the record's state filter offers, and therefore what `?state=` may
 *  name. `outstanding` is open + regressed; `attention` adds the analysis
 *  findings that wait for the operator, and is the pane's default (item 237). */
const STATE_FILTERS = ["attention", "outstanding", "to-confirm", "all", "open", "regressed", "fixed",
                       "candidate", "accepted-risk", "withdrawn",
                       // Findings on a page the latest site-wide crawl did not
                       // fetch (brief v2 step F, from step B's join).
                       "gone"];

type Tab = "landing" | "findings" | "history" | "all" | "pages" | "notes";

/** The routable names, so `?tab=` can only ever name a tab that exists. */
const TABS: readonly Tab[] = ["landing", "findings", "history", "all", "pages", "notes"];
/** Which pane a `?tab=` actually renders, alias and unknown word included
 *  (item 184). Exported because the document title was computed from the raw
 *  word by a second list in `App.tsx`, and so said "Triage" over a screen
 *  headed "Audit" on every aliased address. One resolution, one answer. */
export function paneFor(raw: string | null | undefined): Tab {
  const want = raw ? (TAB_ALIAS[raw] ?? raw) : "";
  return TABS.includes(want as Tab) ? (want as Tab) : "findings";
}
/** Old names for panes that moved, so a stored link still lands where its
 *  content went (plan §6). `analyses` merged into `findings` at §7 step 4;
 *  `record` was never a tab, but a test navigated to it and landed on the
 *  default by fallthrough, and the record is what the word means. */
const TAB_ALIAS: Record<string, Tab> = {
  analyses: "findings", record: "all",
  // Brief v24 step BN: Precheck and Triage fold into Audit. `triage` is kept
  // after item 196 removed the ranking block: the word no longer names
  // anything on the pane, but a stored link landing on Audit is better than
  // one landing on the unknown-tab banner, and it is one line.
  precheck: "history", triage: "history",
};

/** A `?tab=` whose pane holds the thing it names as one block among several,
 *  and the block's anchor (item 184). Empty since item 196 removed the
 *  ranking block, which was its only entry: `triage` aliased to the Audit
 *  pane and scrolled to the ranking, and scrolling to a block that no longer
 *  exists is the failure the entry was added to prevent.
 *
 *  Kept rather than deleted, with its machinery: the shape is the answer to
 *  "a pane holds the named thing as one block among several", which is a
 *  recurring arrangement here, and the next one wants the anchor rather than
 *  a rediscovery of why it is needed. `precheck` is the standing example of
 *  the other case - its block is first on the pane, already in view.
 *
 *  Held by `useAliasBlock` rather than in the screen, which was one line under
 *  `test_the_shell_mounts_the_panes_and_holds_no_pane_body`'s 400-line cap
 *  before item 184 - so the state, its counter and its clearing live here. */
const ALIAS_BLOCK: Record<string, string> = {};

/** The Record's two views (brief v24 step BN): the finding log, and every
 *  audit so far. In the address as `?view=audits`, so a link can name either;
 *  the finding log is the default. Two views rather than one long pane, because
 *  the runs table under the log was a second table of rows in a pane whose rows
 *  are findings.
 *
 *  Out here with the other address readers (`paneFor`, `pageScopeFromHash`)
 *  rather than inside the screen: it reads the hash and holds no state, and the
 *  screen is against its 400-line cap. */
const viewOf = () => new URLSearchParams((window.location.hash.split("?")[1]) || "")
  .get("view") === "audits" ? "audits" : "findings";

/** The block an address asked for, counted so that pressing the same address
 *  twice brings it into view twice, and cleared by any address naming none so
 *  that a later pane change does not scroll.
 *
 *  `bringFor` answers the question a pane asks - "is it me, and which press?" -
 *  so the screen passes one call rather than reaching into the shape. */
function useAliasBlock() {
  const [bring, setBring] = useState<{ block: string; n: number } | null>(null);
  const forRaw = (raw: string | null) => setBring((b) => {
    const block = raw ? ALIAS_BLOCK[raw] ?? null : null;
    return block ? { block, n: (b?.n ?? 0) + 1 } : null;
  });
  const bringFor = (block: string) => (bring?.block === block ? bring.n : 0);
  return { forRaw, bringFor };
}

/** The last pane viewed for a site, so the screen opens where the operator
 *  left it (plan §4c, rule 2). Per site, because the site switcher keeps
 *  the address's query tail and would otherwise land site B on site A's
 *  pane; the switcher drops `tab` from the tail for the same reason. */
const paneKey = (site: string) => `clauditseo:pane:${site}`;
const rememberedPane = (site: string): Tab | null => {
  try {
    const v = localStorage.getItem(paneKey(site));
    return v && TABS.includes(v as Tab) ? (v as Tab) : null;
  } catch { return null; }
};
const rememberPane = (site: string, pane: Tab) => {
  try { localStorage.setItem(paneKey(site), pane); }
  catch { /* private mode: the rule below still lands somewhere */ }
};
/** And what was viewed on the record - its state filter - so "the last pane
 *  viewed" is the screen that was left, not the pane with its default put
 *  back (audit F-13). Written from the operator's own choice, never from a
 *  render: a render on the way into another site would file site A's
 *  filter under site B. */
const stateKey = (site: string) => `clauditseo:state:${site}`;
const rememberedState = (site: string): string | null => {
  try {
    const v = localStorage.getItem(stateKey(site));
    return v && STATE_FILTERS.includes(v) ? v : null;
  } catch { return null; }
};
/** How the record is grouped (brief step 6, UX-01): by check, or not at
 *  all. Remembered per site the way the state filter is, and named on the
 *  address as `?group=` for the same reason `?state=` is. */
const GROUPINGS = ["check", "none"];
const groupKey = (site: string) => `clauditseo:group:${site}`;
const rememberedGroup = (site: string): string | null => {
  try {
    const g = localStorage.getItem(groupKey(site));
    return g && GROUPINGS.includes(g) ? g : null;
  } catch { return null; }
};
const rememberGroup = (site: string, group: string) => {
  try { localStorage.setItem(groupKey(site), group); } catch { /* as above */ }
};
const rememberState = (site: string, state: string) => {
  try { localStorage.setItem(stateKey(site), state); } catch { /* as above */ }
};

/** What each pane is, in the operator's terms — the name the strip's step
 *  uses for it, and what it answers. The names are short by design and short
 *  names are ambiguous on first meeting, so the pane states its question
 *  outright in rendered text, for the reader who does not hover and the one
 *  who cannot. */
/** A pane's name, for anything outside this file that has to say which
 *  screen is showing (item 184: the document title). */
export const paneLabel = (tab: string): string =>
  PANES[paneFor(tab)].label;

const PANES: Record<Tab, { label: string; ask: string }> = {
  // Brief v24 step BM: the landing. The three lanes, at full height.
  landing: { label: "Where it stands",
             ask: "What is waiting on you, what has been measured, and what is settled" },
  // The merged pane (plan §3): the issue browser — the standing position
  // across every audit, cut by where a fix lands — and the catalogue of
  // briefs, under one run scope. Step 4's.
  findings: { label: "Analyses",
              ask: "What you may buy — then what is open, and which analysis "
                   + "investigates it" },
  // Brief v24 step BN: Audit absorbs Precheck and Triage - the count taken
  // before an audit is bought, the chooser, and the ranking taken after.
  history: { label: "Audit",
             ask: "Count what the site publishes, start an audit, and rank what "
                  + "it found" },
  // And the Record absorbs History: the finding log, then every audit so
  // far, the trend and what changed between crawls.
  all: { label: "Record",
         ask: "Every finding ever raised here, and every audit so far — the "
              + "trend and what changed between crawls" },
  pages: { label: "Pages",
           ask: "The crawled pages themselves, and what each one carries" },
  // "Client notes", not "Notes" (audit F12): the bare word put `Notes 0` in
  // the bar about 200px from a headline reading "4 coverage notes not
  // counted" - two populations under one noun, and the pane's own blurb says
  // which one this is. Renamed here rather than qualified in the bar alone,
  // because two names for one destination is the fault in the other
  // direction (item 183, pattern I).
  notes: { label: "Client notes",
           ask: "What you have written about this client, kept with the site" },
};

/** The reference row: Pages and Notes, above the pane (plan §2 rule 3).
 *
 *  They are not steps — nothing in the order produces them — but they are
 *  consulted from any step, so they sit between the strip and the pane rather
 *  than after it: the record has been measured at 41,034px unfiltered, and a
 *  destination placed after arbitrarily long content is not a destination.
 *
 *  Links, through the door: a reference row that changed the pane without
 *  writing the address was the tab row's own defect (§5g), and the reason the
 *  back button did nothing here. `aria-current="page"` marks the one whose
 *  pane is showing; the weight is the sighted cue, and the border agrees.
 *
 *  **`Pages` is the crawl population, not the list the Pages pane shows.** The
 *  caller passes `populations.crawl.size`, which is keyed on path with the
 *  query stripped (`pathKey`); the pane lists the run's fetched URLs, and on
 *  Acme two of them share a path - `/apply` and `/apply?product_type=loc` -
 *  so this badge reads 99 where the pane reads 100. A comment at the call site
 *  asserted the two were one set until audit F8 measured them. Both numbers
 *  are true of different questions, and `PageFinder` states both with the
 *  population named; which set the pane should LIST is an open ruling. */
function Refs({ siteId, active, counts }: {
  siteId: string; active: Tab | null; counts: Partial<Record<Tab, number>>;
}) {
  const items: Tab[] = ["pages", "notes"];
  return (
    <nav className="refs" aria-label="Reference">
      {items.map((t) => {
        const href = `#/sites/${siteId}?tab=${t}`;
        return (
          <a key={t} className="ref-link" href={href} onClick={navHandler(href)}
             aria-current={active === t ? "page" : undefined}>
            {PANES[t].label}
            {counts[t] !== undefined && <span className="ref-n">{counts[t]}</span>}
          </a>
        );
      })}
    </nav>
  );
}

/** A dimension's score, or an honest absence of one.
 *
 *  Three states, not two: inapplicable (LOC on a business with no premises),
 *  unmeasured (off-page with no provider key), and scored. The first two used
 *  to render as "n/a" and "100 · good" respectively, which had it exactly
 *  backwards — the dimension that could not be judged showed a perfect mark.
 *
 *  UX-87. All three states used to state their reason in a `title` on a
 *  non-focusable span, so a keyboard reached `n/a`, `not assessed` or
 *  `62% measured` and never the sentence behind it — and on the one table an
 *  operator plans a fee from, *which* checks went unmeasured was a mouse-only
 *  fact. `AccessibilityScore` sixty lines below makes the opposite choice on
 *  this same screen and states the rule: "Rendered text, not a title: what
 *  this number is not part of is a stated limitation on a displayed value,
 *  and the provenance invariant puts those in text a keyboard can reach."
 *  This is that component's wording adopted in the cell, not a second
 *  convention — same class name shape (`dim-aside` to `headline-aside`),
 *  same lower-case sentence, same placement under the figure it qualifies. */
function DimScore({ sub }: { sub: { applicable?: boolean; score: number;
                                    coverage?: number;
                                    unmeasured?: string[] } }) {
  if (sub.applicable === false) {
    return (
      <>
        <span className="muted">n/a</span>
        <div className="muted dim-aside">not applicable to this site</div>
      </>
    );
  }
  const coverage = sub.coverage ?? 1;
  if (coverage === 0) {
    return (
      <>
        <span className="muted">not assessed</span>
        <div className="muted dim-aside">
          {sub.unmeasured?.length
            ? `nothing was measured: ${sub.unmeasured.join(", ")}`
            : "nothing was measured for this dimension"}
        </div>
      </>
    );
  }
  return (
    <>
      <ScoreBadge score={sub.score} />
      {coverage < 1 && (
        <>
          <span className="muted dim-partial">
            {" "}· {Math.round(coverage * 100)}% measured
          </span>
          <div className="muted dim-aside">
            {sub.unmeasured?.length
              ? `scored on what was measured. Not measured: ${
                  sub.unmeasured.join(", ")}`
              : "scored on part of this dimension"}
          </div>
        </>
      )}
    </>
  );
}


/** The stored accessibility sub-score, at headline size, on a scale of its own.
 *
 *  F-09. `DEFAULT_WEIGHTS["A11Y"] = 0.0` — "reported, never scored" — so
 *  `composite()` renormalises accessibility out of the total, and the number
 *  beside this one has never contained it. Rendering it as a 0.0%-weight row
 *  of the composite's decomposition stated the opposite of what it is: a
 *  dimension holding 38% of every finding this product has ever raised said
 *  `high` in the findings list and "this can never matter" in the table, on
 *  one screen. It is not a component of an SEO score at zero percent. It is a
 *  second deliverable, with its own standard — ADA litigation, the European
 *  Accessibility Act — and its own reason to act, and it is stated here in
 *  its own right rather than summed with anything.
 *
 *  **The number is the stored one, never one recomputed here.** `get_run`
 *  parses the `subscores` column the engine wrote at run time
 *  (`persistence/runs.py`), so `sub.score` is that run's own recorded figure.
 *  A card that recomputed would be a second number for the same thing, and
 *  two numbers for the same thing is how they start to disagree.
 *
 *  Three states, not two, and the third is `composite()`'s own invariant
 *  rather than a looser restatement of it: **0.0 is a measurement meaning
 *  perfectly bad, and the absence of one means there was nothing to
 *  measure.** A run whose accessibility sweep did not execute reads "not
 *  assessed" and never a zero — inapplicable to the site, no coverage, or
 *  A11Y never selected for the run at all, which is the same sweep not
 *  executing and is why an absent sub-score is handled here rather than by
 *  rendering nothing. Nothing new is needed to know this: the stored
 *  `SubScore` already carries `coverage` and `unmeasured` to say so. */
function AccessibilityScore({ sub }: { sub?: { applicable?: boolean; score: number;
                                               coverage?: number;
                                               unmeasured?: string[] } }) {
  const coverage = sub?.coverage ?? 1;
  const assessed = sub != null && sub.applicable !== false && coverage > 0;
  return (
    <div className="headline-score headline-a11y">
      {assessed ? (
        <div className="headline-number">{sub!.score.toFixed(1)}</div>
      ) : (
        <div className="headline-number headline-unassessed">not assessed</div>
      )}
      <div className="muted">accessibility / 100</div>
      {/* Rendered text, not a title: what this number is not part of is a
          stated limitation on a displayed value, and the provenance
          invariant puts those in text a keyboard can reach. */}
      <div className="muted headline-aside">
        {assessed
          ? "scored separately — not part of the composite"
          : sub == null
            ? "this audit did not check accessibility"
            : sub.applicable === false
              ? "not applicable to this site"
              : `nothing was measured${sub.unmeasured?.length
                  ? `: ${sub.unmeasured.join(", ")}` : ""}`}
      </div>
      {assessed && coverage < 1 && (
        <div className="muted headline-aside">
          scored on {Math.round(coverage * 100)}% of the checks
          {sub!.unmeasured?.length
            ? ` — not measured: ${sub!.unmeasured.join(", ")}` : ""}
        </div>
      )}
    </div>
  );
}


/** How much of the intended audit the composite beside it rests on.
 *
 *  `audits/DISPOSITIONS.md`'s engineering cohort, oldest live row at twelve
 *  rounds: **`measured_share` has a writer and no reader.** Every audit has
 *  stored this figure beside its composite since the engine learned to
 *  compute it — framed, at `confidence: high`, and served on request by
 *  `GET /api/sites/{id}/trend?metric=measured_share` — and nothing has ever
 *  asked for it. A T1 pulse over a tenth of the weight and a full T3 both
 *  print a two-digit score, and this is the only stored number that tells
 *  them apart.
 *
 *  **The stored value, never one recomputed here**, for `AccessibilityScore`'s
 *  reason stated one component above: a screen that recomputed would be a
 *  second number for the same thing, and this one in particular can honestly
 *  differ from a fresh calculation, because a run completed under an older
 *  engine keeps the value that engine wrote.
 *
 *  **The frame is the point, not decoration.** `scoring.share_basis` says
 *  which of two quantities the value is, and they are not one series: five
 *  real rows for one site stood at 0.2879 and 0.9362 in the same tier meaning
 *  different things, which is what `metric_snapshots.scope` was added to
 *  record. Printing "28.8%" under one label would re-commit that defect at
 *  the reader. So the branch is on the stored basis, and
 *  `tests/test_measured_share_on_screen.py` derives the branch set by calling
 *  `share_basis` rather than by restating its two strings.
 *
 *  **A third state, and the live database is in it.** Rows written before
 *  migration 0022 carry `scope` NULL, so their basis is unknown — every row
 *  in the operator's own database is one. Unknown says so; it does not pick
 *  the likelier of the two.
 *
 *  Rendered text rather than a `title`, per the provenance invariant: a
 *  stated limitation on a displayed value goes where a keyboard can reach it.
 *
 *  Renders nothing at all when the run stored no figure — a verification, a
 *  refresh, a robots-blocked audit. Absence is not zero, and "0.0% of the
 *  intended audit" would say the crawl looked and found nothing. */
function MeasuredShare({ share }: { share?: Run["measured_share"] }) {
  if (!share) return null;
  const pct = `${(share.value * 100).toFixed(1)}%`;
  /* `share_basis` returns "coverage" for two situations and its own docstring
     says so: the site declared no total, *or* the crawl recorded no fetched
     count. Only the first is a fact about the client's site, and this branch
     asserted it for both — so a run that stored no crawl evidence at all told
     the operator something about somebody else's website on no evidence. That
     is UX-55, and it is not exotic: every CLI-launched audit takes that path
     (CQ-05) and live run 8fdeb042 is an API run in the same state. A stated
     frame that is false is worse than an absent one.

     The discriminator was already here, in these props, and was being
     discarded at the last layer: `pages_fetched` is null when nothing about
     the crawl was recorded, and a number when the site simply declared no
     total. Nothing new is fetched to tell them apart.

     Deliberately not fixed at the writer. Whether `share_basis` grows a third
     value or the stored frame gains a separate "was any scope recorded" key is
     report 065's OPEN QUESTION 1, and the answer decides whether `site_trend`'s
     grouping key moves — every stored series would split. Both answers leave
     `pages_fetched` on the wire, so this branch is correct under either and
     does not prejudge it. */
  const unscaled = share.pages_fetched === null
    ? "this audit recorded no crawl page count"
    : "this site declared no page total";
  const frame = share.basis === "coverage+breadth"
    ? `dimension coverage scaled by the ${share.pages_fetched} of `
      + `${share.discovered} declared pages this crawl reached`
    : share.basis === "coverage"
      ? `dimension coverage — ${unscaled}, so crawl breadth is not in the figure`
      : "the frame this figure was computed under was not recorded";
  return (
    <div className="muted headline-aside">
      {pct} of the intended audit measured — {frame}
    </div>
  );
}


export function SiteDetailView({ siteId }: { siteId: string }) {
  const [tick, setTick] = useState(0);
  const [tab, setTab] = useState<Tab>("findings");
  /** A `?tab=` the address named and no pane answers to. Never a silent
   *  fallthrough (plan §6): the default pane shows, and a line says which
   *  name was not one. */
  const [unknownTab, setUnknownTab] = useState<string | null>(null);
  const { forRaw: bringBlock, bringFor } = useAliasBlock();
  /** Whether the pane for this visit has been decided (plan §4c). False
   *  between entering a site with no `?tab=` and no remembered pane, and
   *  the position arriving to say how young the site is. Evaluated once
   *  per site entry, never continuously (§5b): the standing position is
   *  re-read every 1.5s while a run is in flight, and a landing tied to
   *  it would navigate the screen while the operator reads. */
  const [landed, setLanded] = useState(false);
  /** The record opens on what is outstanding — open and regressed — with
   *  the filter visible and changeable (plan §4a). "What we fixed", the
   *  most valuable content in a client report, is one choice away. */
  const [fState, setFState] = useState("attention");
  const [recordView, setRecordView] = useState<"findings" | "audits">(viewOf);
  const [shown, setShown] = useState(PAGE);
  /** How the record is grouped (brief step 6). With the address, like
   *  `fState`; the pane's own state lives in `pane_record.tsx`. */
  const [group, setGroup] = useState<string>("check");
  /** The part in hand (brief v4 Item 3a): what the sidebar selected, open
   *  on Analyse and the filter on the Record. The screen's, so it survives
   *  changing the pane; reset with the site. */
  const [part, setPart] = useState("");
  const [rerunAsk, setRerunAsk] = useState<{ key: string; n: number } | null>(null);
  /** One press to a part's refresh confirmation, from wherever the part is
   *  listed: select it, and ask. A counter, so the same part asks twice. */
  const rerunPart = (key: string) => {
    selectPart(key);
    setRerunAsk((r) => ({ key, n: (r?.n ?? 0) + 1 }));
  };
  /** The catalogue of every brief, behind one control (brief v2 step E);
   *  the control is the legend strip's since brief v4 Item 3d. */
  const [catalogue, setCatalogue] = useState(false);
  // Back to the shop closes a drawer left open inside a part: the shop is
  // the body there, and the drawer is not carried back over it.
  useEffect(() => { if (!part) setCatalogue(false); }, [part]);
  /** Run-all's ask (brief v4 Item 3f): which scope, counted so the same
   *  part can be asked twice. The drawer opens on its confirm panel. */
  const [batchAsk, setBatchAsk] = useState<{ part: string | null; n: number } | null>(null);
  const askBatch = (part: string | null) => {
    setBatchAsk((b) => ({ part, n: (b?.n ?? 0) + 1 }));
    setCatalogue(true);
  };
  useEffect(() => { setPart(""); setRerunAsk(null); }, [siteId]);
  const { data, error, loading, retry } = useFetch<SiteDetail>(`/api/sites/${siteId}`, tick);
  /** The standing position's own state, owned here so the position and the
   *  suggested order sit above the panes and survive changing one. Readers:
   *  `StandingHeader`, `AnatomyView`, `TriagePane`, and the Record pane below
   *  for the fix loop. See `useAnatomy` for what is shared and why. A verify
   *  re-reads this screen's own payload too, since the record's rows carry
   *  the states it moves. */
  const anat = useAnatomy(siteId, () => setTick((t) => t + 1));
  /** The one fix loop (audit F-17): a mark made on the Analyses pane is the
   *  same mark on the Record pane, in the same set, judged by the same
   *  audit, with no re-read in between. */
  const fix = anat.fix;
  const { refreshRuns } = useSelection();
  /** Whether the previous reading of this site had a run in flight, so the
   *  moment one finishes can be seen from here. The standing position reads
   *  a different payload from the one this screen polls, and it used to be
   *  re-read by the Current tab remounting; now that it stands above the
   *  tabs, nothing remounts it, so an audit that completed while the
   *  operator read History would leave the position and the strip a run
   *  behind until a reload. */
  const wasRunning = useRef(false);
  useEffect(() => {
    const running = Boolean(data?.runs.some((r) => isInFlight(r.status)));
    if (wasRunning.current && !running) {
      anat.setTick((t) => t + 1);
      // And the selection bar's run list, so the pick can offer the audit
      // that just finished without a reload.
      refreshRuns();
    }
    wasRunning.current = running;
    if (!running) return;
    const t = setTimeout(() => setTick((x) => x + 1), 1500);
    return () => clearTimeout(t);
  }, [data]);


  /** Which pane, from the address — the landing rule (plan §4c), in order.
   *
   *  1. An explicit `?tab=` wins: a known name is its pane, an old name is
   *     the pane its content moved to (§6), and an unknown name is the
   *     default pane WITH the name shown, never a silent fallthrough. The
   *     pane param is `tab` rather than a second `step` param: it already
   *     names a step's pane, and two words for one fact is how this screen
   *     came to have two navigations.
   *  2. Else the last pane viewed for THIS site.
   *  3. Else, once the position has arrived: the Audit pane for a site
   *     with no audit yet — the chooser in front of the operator, which is
   *     the one journey where the pipeline is unambiguously the right
   *     shape (§5d) — and otherwise step 4. The plan wrote this as
   *     "`next`, only if `next <= 2`"; with `next` fixed, a site that has
   *     an audit and no precheck would have landed on the chooser with
   *     real work waiting at step 4, and the precheck control is in the
   *     strip on every pane, so the test is whether an audit has run.
   *
   *  Read on mount and on every `hashchange`, since the links are pressed
   *  while this component is mounted; the site is read off the path
   *  rather than the prop because the two change in the same event. */
  const decide = useCallback(() => {
    const [path, query] = (window.location.hash || "").split("?");
    const site = /^#\/sites\/([^/?]+)/.exec(path)?.[1] ?? siteId;
    const q = new URLSearchParams(query || "");
    const raw = q.get("tab");
    // The part in hand is the address's (brief v24 step BM), so Back closes
    // it and a pasted link opens it.
    setPart(new URLSearchParams(query || "").get("part") || "");
    setRecordView(viewOf());
    // A figure in the standing position links to the record filtered to
    // the state it counts. Applied only when named, so a step link to the
    // record keeps whatever the operator last chose.
    // Only beside an explicit pane: a `?state=` left in the tail by a site
    // switch would otherwise set site B's filter to what site A was looking
    // at (audit F-12); the switcher drops it too.
    const state = q.get("state");
    const g = q.get("group");
    if (raw && g && GROUPINGS.includes(g)) {
      setGroup(g); rememberGroup(site, g);
    } else {
      const lastG = rememberedGroup(site);
      if (lastG) setGroup(lastG);
    }
    if (raw && state && STATE_FILTERS.includes(state)) {
      setFState(state); setShown(PAGE); rememberState(site, state);
    } else {
      // No state named: the record opens on what it was last left on.
      const last = rememberedState(site);
      if (last) { setFState(last); setShown(PAGE); }
    }
    // `?schedule` opens the scheduler, which is the Audit pane's since brief
    // v2 step A: an address that names it lands there, so Home's schedule
    // cell still opens the dialog in one click.
    if (!raw && q.has("schedule")) {
      setTab("history"); setUnknownTab(null); rememberPane(site, "history");
      setLanded(true);
      return;
    }
    if (raw) {
      const want = TAB_ALIAS[raw] ?? raw;
      if (TABS.includes(want as Tab)) {
        setTab(want as Tab); setUnknownTab(null); rememberPane(site, want as Tab);
      } else { setTab("findings"); setUnknownTab(raw); }
      bringBlock(raw);
      setLanded(true);
      return;
    }
    setUnknownTab(null);
    bringBlock(null);
    // No pane named: the landing, once the position says the site has been
    // audited (brief v24 step BM). The remembered pane no longer decides an
    // address that names none - Back from a part must return to the landing,
    // not to the pane the part was opened on.
    setLanded(false);
  }, [siteId]);
  useEffect(() => {
    decide();
    window.addEventListener("hashchange", decide);
    return () => window.removeEventListener("hashchange", decide);
  }, [decide]);
  /** Rule 3, once the position has answered — or failed, which lands on
   *  step 4 rather than guessing the site's age from nothing. */
  useEffect(() => {
    if (landed) return;
    if (anat.loading && !anat.error) return;
    if (!anat.data && !anat.error) return;  // not asked yet (item 179)
    if (anat.precheckLoading) return;    // the third clause reads it too
    const young = !anat.error && !anat.data?.current?.last_audit;
    // §4c as written: `next`, while `next <= 2`. With step 1 holding a pane
    // of its own the first clause is reachable - a site nothing has counted
    // lands on the precheck, one counted but never audited on the chooser.
    const pane: Tab = !young ? "landing" : "history";
    setTab(pane);
    rememberPane(siteId, pane);
    setLanded(true);
  }, [landed, anat.loading, anat.error, anat.data, anat.precheck,
      anat.precheckLoading, siteId]);

  useSeed(fix.seed, data?.states ?? [], data);
  /** Open a part by writing it into the address (brief v24 step BM). On a
   *  pane that does not show parts, the part opens on Analyses, as the
   *  sidebar's own rule was; on Analyses or the Record it toggles. */
  const selectPart = (key: string) => {
    const onParts = tab === "findings" || tab === "all";
    const [path, query] = (window.location.hash || `#/sites/${siteId}`).split("?");
    const q = new URLSearchParams(query || "");
    if (!onParts) q.set("tab", "findings");
    // Built from the current address and sent without the scope carry: the
    // carry copies `part` forward from the address being left, so clearing
    // the part through it put the part straight back.
    goto(withPart(`${path}?${q.toString()}`, key), { keepScope: false });
  };

  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!data) return <Loading />;
  // Audits only. A verification stores no score, so the history headline
  // read blank whenever one was the most recent run.
  const complete = completedAudits(data.runs);
  const latest = complete[0];
  return (
    <>
      {/* Identity comes from the shell now, so it is on the launch and
          workbench screens too rather than only this one. */}
      {/* Urgent things stay above the tabs: they are true whichever tab you
          are on, and a tab is a place you might never open. */}
      {/* Where the work stands and what to do next, above the tabs: it is
          true whichever tab you are on, and until this it was a child of one
          of them. Keyed like the tree below it, so a site change starts its
          picker and its triage state over. */}
      {/* No tab row (plan §7 step 5). The strip is the navigation and the
          reference links are the rest of it. Item 173 moved the links into
          the shell's bar with the audit picker; they are navigation and stay
          operable, which is why they move rather than collapse. */}
      <StandingHeader key={siteId} siteId={siteId} a={anat}
                      alerts={{ regressions: data.regressions,
                                watch: (data as any).watch }}
                      tab={landed ? tab : ""}
                      running={data.runs.find(
                        (r) => r.kind === "audit" && isInFlight(r.status)) ?? null}
                      context={<Refs siteId={siteId} active={landed ? tab : null}
                                     // The crawl population, path-keyed; see
                                     // `Refs` for what that is not (audit F8).
                                     counts={{ pages: anat.data?.populations?.crawl.size ?? anat.data?.pages.length,
                                               notes: ((data as any).notes ?? []).length }} />} />

      {/* Nothing below the strip until the pane is decided: a default that
          then changes is the screen navigating itself, and the strip above
          already says the position is loading. */}
      {/* The pane change, announced (audit F-21): a step name pressed by a
          keyboard changed the pane and nothing said so - focus stayed on
          the name, no live region spoke, and the pane's own name was a
          `<strong>` outside the heading outline. Always mounted, so the
          region exists before it speaks. */}
      <p className="sr-only" role="status" aria-live="polite">
        {landed && `Showing ${PANES[tab].label}`}
      </p>
      {landed ? (<>
      {/* One column: the sidebar that stood beside the five steps' panes is
          retired (brief v24 step BO). */}
      <div className="site-alone">
      <div className="site-main" data-anatomy={anat.data ? "loaded" : "loading"}>
      {/* Item 173 (ruling C): on the landing the heading is kept - F-21's
          pane announcement and the outline hang on it - but not drawn, and
          its subtitle goes, so the actions run straight into the lanes. */}
      <div className={`pane-head${tab === "landing" ? " sr-only" : ""}`}>
        <h2 id="pane-name" className="pane-name">{PANES[tab].label}</h2>
        {tab !== "landing" && <span className="muted pane-ask">{PANES[tab].ask}</span>}
      </div>
      {/* The legend, a strip above the content (brief v4 Item 3d): the
          symbols in play on this pane, and never inside the sidebar -
          `listShowing` applies that rule to the analyses list (item 197). */}
      {SIDEBAR_PANES.includes(tab as SidebarPane) && tab !== "landing" && (
        <LegendStrip pane={tab as SidebarPane} a={anat}
                     catalogueOpen={tab === "findings" && catalogue}
                     listShowing={tab === "findings" && (!part || catalogue)}
                     onCatalogue={tab === "findings" && part ? () => setCatalogue((v) => !v) : undefined} />
      )}
      {/* Mounted always, empty until it has something to say: a live region
          that arrives with its text is not announced (audit F-22), and the
          case this exists for is a stored address opened fresh. */}
      <p className="muted head-note pane-unknown" role="status">
        {unknownTab && `There is no pane called “${unknownTab}” — showing ${PANES[tab].label}.`}
      </p>

      {/* A landmark with the pane's own name, and the skip link's target. */}
      <div className="pane-body" id="pane" tabIndex={-1} role="region"
           aria-labelledby="pane-name">
      {/* Keyed, so a site change remounts rather than carrying this panel's
          own local state — the open category, the page filter — across to
          another client. The stale-render half of the reason is gone:
          `useFetch` now answers for the current path only, so no screen
          renders one site's data under another's name while the next load
          lands. The key stays for the state it was never about. */}

      {tab === "findings" && (
        <AnalysePane siteId={siteId} anat={anat} states={data.states}
                     selected={part} onSelect={selectPart} rerunAsk={rerunAsk} onRerun={rerunPart}
                     onRunAll={(key) => askBatch(key)} />
      )}

      {/* Audit (brief v24 step BN): the precheck counts and the sitemap read
          above, then the chooser. The ranking block that sat below went with
          item 196 - the ranking is the audit's own now and reaches the reader
          as the order of the parts and of the catalogue, rather than as a
          table with a purchase on it. */}
      {tab === "history" && (<>
        <PrecheckPane siteId={siteId} a={anat} />
        <PrecheckBadge a={anat} />
        <AuditPane siteId={siteId} data={data} anat={anat} setTick={setTick} show="start" />
      </>)}

      {tab === "landing" && <SiteLanding siteId={siteId} a={anat} />}


      {tab === "all" && (
        <nav className="record-view" aria-label="Record view">
          {([["findings", "Findings"], ["audits", "Audits"]] as const).map(([key, label]) => {
            const [path, query] = (window.location.hash || `#/sites/${siteId}`).split("?");
            const q = new URLSearchParams(query || "");
            q.set("tab", "all"); q.delete("run");  // `run=` is the history view's (item 239 step 5)
            if (key === "audits") q.set("view", "audits"); else q.delete("view");
            const href = `${path}?${q.toString()}`;
            return (
              <a key={key} href={href} onClick={navHandler(href)}
                 className={`mode-seg${recordView === key ? " mode-on" : ""}`}
                 aria-current={recordView === key ? "page" : undefined}>{label}</a>
            );
          })}
        </nav>
      )}
      {tab === "all" && recordView === "findings" && (
        <RecordPane siteId={siteId} data={data} fix={fix} shown={shown}
                    setShown={setShown} setTick={setTick}
                    fState={fState}
                    onState={(v) => { setFState(v); setShown(PAGE);
                                      rememberState(siteId, v); }}
                    group={group}
                    onGroup={(v) => { setGroup(v); setShown(PAGE);
                                      rememberGroup(siteId, v); }}
                    part={(() => {
                      const c = part ? anat.data?.categories.find((x) => x.key === part) : null;
                      return c ? { label: c.label,
                                   checks: new Set(c.findings.map((f) => f.check_id)) } : null;
                    })()}
                    onClearPart={() => selectPart("")}
                    parts={(anat.data?.categories ?? []).filter(isPart)
                             .map((c) => ({ key: c.key, label: c.label, open: c.total.value }))}
                    partKey={part} onPart={selectPart}
                    cost={anat.cost} onCost={anat.setCost} runId={anat.run ?? null}
                    costs={costsAcross(anat.data?.categories ?? [])}
                    gonePaths={pagesGone(anat.compare)} />
      )}
      {/* The Record holds every audit so far too (brief v24 step BN). */}
      {tab === "all" && recordView === "audits" && (
        <RecordAudits siteId={siteId} data={data} anat={anat} setTick={setTick} />
      )}

      {tab === "pages" && (<>
      <PageFinder siteId={siteId} latestRunId={latest?.id} />
      </>)}

      {tab === "notes" && (<>
      <Card>
        <h3>Notes</h3>
        <p className="muted">
          The context a crawl cannot supply — “client says leave the pricing
          page alone” decides what a finding means.
        </p>
        <form className="inline-form" onSubmit={async (e) => {
          e.preventDefault();
          const input = (e.target as HTMLFormElement)
            .elements.namedItem("note") as HTMLInputElement;
          if (!input.value.trim()) return;
          await api.post(`/api/sites/${siteId}/notes`, { note: input.value });
          input.value = "";
          setTick((t) => t + 1);
        }}>
          <input name="note" aria-label="Note" placeholder="Add a note…" style={{ flex: 1 }} />
          <SecondaryButton submit>Add</SecondaryButton>
        </form>
        <ul className="group-pages">
          {((data as any).notes ?? []).map((n: any) => (
            <li key={n.id}>
              <span className="muted">{n.created_at.slice(0, 10)}</span> {n.body}{" "}
              <DangerButton label={`delete the note from ${n.created_at.slice(0, 10)}`} confirm={{
                  title: "Delete this note?", action: "Delete the note",
                  body: <p>&ldquo;{n.body}&rdquo;, from {n.created_at.slice(0, 10)}.</p> }}
                onConfirm={async () => { await api.del(`/api/sites/${siteId}/notes/${n.id}`); setTick((t) => t + 1); }}>✕</DangerButton>
            </li>
          ))}
        </ul>
      </Card>
      </>)}

      </div>
      {/* The catalogue of every brief, a drawer from the right (brief v4
          Item 3e): the legend strip's control and the tab on the right
          edge open it, and it stands outside the pane's body, over the
          content, which does not move. Analyse only. */}
      {/* With a part open only: with none, the shop is Analyses' own body
          (brief v24 step BO), and a drawer of the same list over it would
          put every row on the screen twice. */}
      {tab === "findings" && part && !catalogue && (
        <CatalogueFab a={anat} onOpen={() => setCatalogue(true)} />
      )}
      {tab === "findings" && part && catalogue && (
        <CatalogueDrawer siteId={siteId} a={anat} onClose={() => setCatalogue(false)} onRerun={rerunPart}
                         ask={batchAsk} />
      )}
      </div>
      </div>
      </>) : <Loading />}
    </>
  );
}

/** The panes the sidebar stands beside: the five steps. */
const SIDEBAR_PANES: readonly SidebarPane[] = ["landing", "history", "findings", "all"];

/** The precheck's own figure for Crawl & sitemaps, on Audit beside the
 *  counts it is about (brief v24 step BN; it rode the sidebar's Crawl row
 *  as the `preBadge`, and 155 left it out of the populations). */
function PrecheckBadge({ a }: { a: ReturnType<typeof useAnatomy> }) {
  const pre = a.precheck;
  if (!pre) return null;
  const n = pre.not_in_sitemap.length + (pre.sitemap_state !== "ok" ? 1 : 0);
  if (!n) return null;
  return (
    <p className="muted pre-badge-line">
      <span className="anat-n n-info sb-pre">{n}</span>{" "}
      from the precheck for Crawl &amp; sitemaps: nav pages missing from the
      sitemap, or a sitemap that could not be read.
    </p>
  );
}

/** Jump to any crawled page's dossier — the page-first door. */
function PageFinder({ siteId, latestRunId }:
    { siteId: string; latestRunId?: string }) {
  const [pages, setPages] = useState<{ url: string; title?: string }[]>([]);
  const [fUrl, setFUrl] = useState("");
  useEffect(() => {
    if (!latestRunId) return;
    let live = true;
    api.get<{ pages: { url: string; title?: string }[] }>(
      `/api/runs/${latestRunId}/pages`)
      .then((d) => { if (live) setPages(d.pages ?? []); })
      .catch(() => { if (live) setPages([]); });
    return () => { live = false; };
  }, [latestRunId]);
  if (!pages.length) return null;
  const shown = pages.filter((p) =>
    !fUrl || p.url.toLowerCase().includes(fUrl.toLowerCase()));
  /** How many pages the rest of the screen counts: `pathKey`'s set, which is
   *  this list's URLs with the query stripped (audit F8). */
  const keys = pages.map((p) => pathKey(p.url));
  const distinctPaths = new Set(keys).size;
  /** The paths this list fetched under more than one spelling, and how many
   *  spellings each has. The difference between the two figures, named in the
   *  words the reader can act on rather than left as arithmetic (channel
   *  ruling 20260918-1430): two fetches of one page is a finding about the
   *  site's URL handling, so it is made visible rather than smoothed over. */
  const variants = new Map<string, number>();
  for (const k of keys) variants.set(k, (variants.get(k) ?? 0) + 1);
  const shared = [...variants].filter(([, n]) => n > 1);
  return (
    <Card>
      <h3>Page dossier</h3>
      {/* Item 166: the severity chips a page's findings wear. */}
      <Legend ids={["sev-critical", "sev-high", "sev-medium", "sev-low", "sev-info"]} />
      <p className="muted">
        Everything known about one page — crawl history, every finding that
        names it, every analysis that read it.
      </p>
      {/* A crawl is 557 pages on this instance's largest site, and an
          <option> list is the one collection a browser will not let you
          scroll past — it opens at the top and the only way to the page you
          want is to type its first letter. Bounded here for the same reason
          the heading outline is: the real-data-scale invariant asks for a
          control at the render site, and a count that says what the control
          is hiding. */}
      <div className="filters fact-filters">
        <input value={fUrl} placeholder="filter by URL…"
               aria-label="page URL filter"
               onChange={(e) => setFUrl(e.target.value)} />
        {/* Audit F8, and ruling 20260918-1430: two questions, not one answered
            twice. What this pane LISTS is the run's fetched URLs, because a URL
            is what was fetched; what every count around it is over - the bar's
            `Pages`, the h1's coverage, every prevalence denominator - is the
            crawl population, keyed on path with the query stripped (`pathKey`,
            whose docstring argues why: one page, two spellings). On Acme that
            is 100 against 99.
            The pane's own set leads, the counting population follows, and the
            reason is named rather than left as subtraction. */}
        <span className="muted page-count">
          {shown.length === pages.length
            ? `${pages.length} URL${pages.length === 1 ? "" : "s"} fetched`
            : `${shown.length} of ${pages.length} URLs fetched`}
          {distinctPaths !== pages.length
            ? <> · {distinctPaths} distinct page{distinctPaths === 1 ? "" : "s"}
                {shared.length
                  ? ` (${shared.map(([k, n]) => `${n} spellings of ${k}`).join(", ")})`
                  : ""}</>
            : null}
        </span>
      </div>
      {/* Named: the visible heading above is not programmatically attached,
          so a screen reader announced this only as "combo box". Found by
          running our own axe pass over our own dashboard. */}
      <select className="input" style={{ maxWidth: "100%" }} defaultValue=""
              aria-label="Open the dossier for a page"
              onChange={(e) => {
                if (e.target.value) {
                  goto(`#/sites/${siteId}/dossier/${encodeURIComponent(e.target.value)}`);
                }
              }}>
        <option value="" disabled>
          {shown.length ? "Choose a page…" : "No page matches that filter"}
        </option>
        {/* The variant marked in its own row, so a reader who wonders why the
            two figures differ finds the answer in the list rather than
            subtracting (ruling 20260918-1430). `option` takes no markup, so
            the mark is in its text. */}
        {shown.map((p) => (
          <option key={p.url} value={p.url}>
            {p.url}{(variants.get(pathKey(p.url)) ?? 1) > 1
                      ? `  — one of ${variants.get(pathKey(p.url))} spellings of this page`
                      : ""}
          </option>
        ))}
      </select>
    </Card>
  );
}

/** The Record's Audits view: the list, or - with `run=` in the address -
 *  one audit as it saw the site (item 239 step 5). Follows the address
 *  itself, so the screen above keeps no state for it. */
function RecordAudits(props: Parameters<typeof AuditPane>[0]) {
  const [asOf, setAsOf] = useState(() => historyRunFromHash(props.siteId));
  useEffect(() => {
    const read = () => setAsOf(historyRunFromHash(props.siteId));
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [props.siteId]);
  const run = asOf ? props.data.runs.find((r) => r.id === asOf) : undefined;
  // Item 166: the audit list's chips - severity and the delete that cannot
  // be undone - defined once above it, as on the Record's other view.
  return run ? <HistoryView siteId={props.siteId} run={run} />
             : <>
                 <Legend ids={["sev-critical", "sev-high", "sev-medium", "sev-low", "sev-info",
                               "action-danger", "danger-undone"]} />
                 <AuditPane {...props} show="history" />
               </>;
}

/** One audit as it saw the site (item 239 step 5, amendment 9): that run's
 *  own record - its score, what it read, the findings it raised - under a
 *  banner naming it, with the way back to the current view. Nothing here is
 *  the Latest View, and nothing outside this tab reads the run. */
function HistoryView({ siteId, run }: {
  siteId: string; run: { id: string; tier?: string | null; started_at: string | null };
}) {
  const back = `#/sites/${siteId}?tab=all&view=audits`;
  return (
    <>
      <p className="history-banner" role="status">
        Viewing as of audit {[run.tier, stamp(run.started_at)].filter(Boolean).join(" · ")}
        {" · "}<a href={back} onClick={navHandler(back)}>back to current</a>
      </p>
      <RunDetailView runId={run.id} />
    </>
  );
}

export function RunDetailView({ runId }: { runId: string }) {
  const [tick, setTick] = useState(0);
  const [flat, setFlat] = useState(false);
  const { data, error, loading, retry } = useFetch<Run>(`/api/runs/${runId}`, tick);
  useEffect(() => {
    if (data && isInFlight(data.status)) {
      const t = setTimeout(() => setTick((x) => x + 1), 1500);
      return () => clearTimeout(t);
    }
  }, [data]);

  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!data) return <Loading />;
  return (
    <>
      <h2>
        Audit of {(data.started_at ?? "").slice(0, 10)}
        {" · "}{ENTRIES.find((e) => e.engine === data.tier)?.word ?? data.tier}
        {" "}<span className="muted">({data.tier}{data.status !== "complete" ? ` · ${data.status}` : ""})</span>
      </h2>
      {/* What this run WAS, in the words it was chosen with — before the
          engine's own vocabulary. A reader arriving at a finished audit asks
          "how much of the site was this, and how hard did it look" and the
          tier line answers neither. Runs made before the chooser existed
          carry no scope, and say nothing rather than being given one. */}
      <ScanBanner run={data as unknown as ScanBannerRun} />
      <p className="muted">
        <a href={`#/sites/${data.site_id}`}>back to site</a> · {data.tier} ·{" "}
        {data.dimensions.join(", ")}
        {(data as unknown as { engine_version: string }).engine_version &&
          <> · engine v{(data as unknown as { engine_version: string }).engine_version}</>}
      </p>
      {!!(data as any).biggest_gains?.length && hasScore(data.status) && (
        <Card>
          <h3>Biggest gains</h3>
          <p className="muted">
            The scoreboard's own arithmetic — points each check is costing the
            composite, biggest first. A deduction is capped and rate-based, so
            this is the ceiling of what fixing everything recovers, not a
            promise.
          </p>
          <table className="findings">
            <thead><tr><th>Check</th><th>Dimension</th><th>Pages</th>
                       <th>Points on composite</th></tr></thead>
            <tbody>
              {(data as any).biggest_gains.slice(0, 8).map((g: any) => (
                <tr key={`${g.dimension}/${g.check_id}`}>
                  <td><code>{g.check_id}</code></td>
                  <td>{g.dimension}</td>
                  {/* Pages, under a column headed Pages. This showed the
                      finding count, so `duplicate-content` — which names both
                      sides of a pair — read "21 of 20 pages" on a table whose
                      whole purpose is defensible numbers. */}
                  <td className="muted">
                    {g.pages != null ? `${g.pages} of ${g.eligible}` : "—"}
                    {g.affected != null && g.affected !== g.pages && (
                      <span className="muted"
                            title="This check raises more than one finding on some
                                   pages — duplicate pairs name both sides.">
                        {" "}· {g.affected} findings
                      </span>
                    )}
                  </td>
                  <td><strong>{g.composite_points}</strong>
                      <span className="muted"> ({g.subscore_points} in-dimension)</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {isInFlight(data.status) && (
        <Card>
          <div className="modal-head">
            <h3>Progress</h3>
            {/* Relay item 136a. A crawl the operator did not ask for should
                be stoppable at page four; before this there was nothing to
                stop it with, and a one-page request that became 145 pages
                ran to the end. It stops at the next page boundary and keeps
                what it fetched — mid-fetch would discard a page for nothing
                and killing the worker would leave this row "running" for
                ever. */}
            <StopRun runId={data.id} onStopped={() => setTick((t) => t + 1)} />
          </div>
          <ul className="progress-steps">
            {(data.progress ?? []).map((step, i, all) => (
              <li key={i} className={i === all.length - 1 ? "current" : "done"}>
                {i === all.length - 1 ? "⏳" : "✓"} {step.label}
                <span className="muted"> {step.at.slice(11, 19)}</span>
              </li>
            ))}
            {!data.progress?.length && <li className="current">⏳ Starting…</li>}
          </ul>
        </Card>
      )}
      {data.status === "failed" && (
        <ErrorNote error={`This audit failed: ${data.error ?? "no reason recorded"}`} />
      )}
      {/* Not an error. The operator stopped it, and a run list that painted
          their own decision red would have them debugging it. */}
      {data.status === "cancelled" && (
        <Card className="run-cancelled">
          <h3>Stopped</h3>
          <p className="muted">
            {data.error ?? "stopped by the operator"}. What it fetched is
            stored; nothing was scored, because a crawl that was stopped is
            not a measurement of the site.
          </p>
        </Card>
      )}
      {/* The state the headline must not render as an ordinary score. The
          findings are real and the fix loop counts this as the latest audit,
          so the page carries on below — what changes is that the number at
          the top would be a composite of a crawl that fetched nothing. The
          scope the server already sends says what did happen. */}
      {data.status === "blocked" && (
        <Card>
          <h3>Crawl refused <RunStatusChip status={data.status} /></h3>
          <p>
            No page was fetched, so there is no page-derived score.
            {data.scope
              ? ` Measured instead: robots.txt, and ${data.scope.robots_blocked} `
                + `URL${data.scope.robots_blocked === 1 ? "" : "s"} it disallowed`
                + (data.scope.discovered
                   ? `, against ${data.scope.discovered} the sitemap declares.`
                   : ", and no sitemap the crawler could read.")
              : " Measured instead: robots.txt and the sitemap only."}
          </p>
          <p className="muted">
            The findings below come from robots.txt and the sitemap, and this
            still counts as the site's latest audit.
          </p>
        </Card>
      )}
      {/* A narrow run's own screen states what it read before its number.
          The headline says "composite / 100" over a figure computed from the
          pages behind a handful of findings, and nothing on the screen said
          the population was different from the site's. Frame is provenance:
          the number is not withheld — it is that run's own honest result —
          but it is not offered as the site's. */}
      {hasScore(data.status) && !isSiteReading(data.kind) && (
        <Card>
          <h3>What this audit read</h3>
          <p>
            This was a <strong>{data.kind}</strong> run: it fetched the pages
            behind specific findings rather than reading the site. The
            composite below is over those pages, so it is not comparable with
            an audit's and is not a point on this site's trend.
          </p>
        </Card>
      )}
      {hasScore(data.status) && (
        <>
          <div className="headline">
            <div className="headline-score">
              {/* UX-15. A composite that was never computed is not a
                  composite being withheld, and an em dash under a
                  "composite / 100" label says the second. `composite()`
                  returns null - not 0.0 - when no dimension contributed a
                  measurable share, which an A11Y-only audit does today:
                  A11Y's nominal weight is 0.0, so nothing carries weight and
                  there is no number. The label goes with the number, because
                  "/ 100" is a frame for a figure and there is no figure.

                  The sentence is the one `render.py`'s `NO_COMPOSITE` gives
                  the reports, chat and the CLI, said in rendered text rather
                  than a `title`. Held to that constant by
                  `tests/test_missing_composite_on_screen.py`, which reads
                  both clauses out of it rather than restating them - so a
                  rewording there fails here instead of leaving this screen
                  quoting a retired sentence. */}
              {data.composite_score == null ? (
                <>
                  {/* The same slot and the same words as the accessibility
                      headline beside it, so two unassessed numbers on one
                      screen do not look like two different states. */}
                  <div className="headline-number headline-unassessed">
                    not assessed
                  </div>
                  <p className="muted headline-aside">
                    Not assessed: composite score. Reason:
                    no dimension carried measurable weight.
                  </p>
                </>
              ) : (
                <>
                  <div className="headline-number">
                    {data.composite_score.toFixed(1)}
                  </div>
                  <div className="muted">composite / 100</div>
                  <div className="muted headline-aside">
                    weighted over the dimensions below
                  </div>
                  {/* The score's own qualifier, beside the score. It was
                      two paragraphs away in the scope card for the documents
                      and nowhere at all on this screen, and the figure is
                      what gets quoted. */}
                  <MeasuredShare share={data.measured_share} />
                </>
              )}
            </div>
            {/* F-09. Two totals, never one: accessibility is scored in its
                own right and is never summed with the SEO composite. Both
                numbers are read from what the run stored; neither is
                computed on this screen. */}
            <AccessibilityScore sub={(data.subscores ?? {}).A11Y} />
            {/* UX-07. The dimension scores are the same badge and the same
                bands as the composite above them. */}
            <ScoreBandKey />
            <table className="findings headline-dims">
              <thead><tr><th>Dimension</th><th>Score</th><th>Weight</th></tr></thead>
              <tbody>
                {/* A11Y stands out of this table because it stands out of the
                    total the table decomposes — its weight is zero, so a row
                    here could only ever read "0.0%", which is the composite's
                    honest arithmetic and a false account of the dimension.
                    It is not dropped from the screen: it is the headline
                    beside this one. */}
                {Object.entries(data.subscores ?? {})
                       .filter(([d]) => d !== "A11Y").sort().map(([d, s]) => (
                  <tr key={d}>
                    <td>{d}</td>
                    {/* A dimension that measured nothing has no score to
                        show. Off-page rendered "● 100.0 out of 100, good" on
                        a run whose only off-page finding was "not assessed:
                        referring domains, anchor text distribution" — the one
                        place in the app where an unmeasured thing looked
                        measured and clean. LOC already read n/a here; it just
                        happened to be inapplicable rather than unmeasured. */}
                    <td><DimScore sub={s} /></td>
                    <td>{(s.weight * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {/* Two predicates, two questions, applied by meaning rather than by
          where the old gate happened to sit. `hasScore` asks whether this
          screen may PRINT a composite — false for a blocked run, whose
          number rests on robots.txt alone. `hasResults` asks whether the run
          produced findings a screen may read, which a blocked run did: the
          server stores it in full and the fix loop counts it as the site's
          latest audit. Gating both on `hasScore` emptied the screen while
          the card above it promised "the findings below". */}
      {hasResults(data.status) && (
        <>
          <PriorityPlan findings={data.analyst_findings ?? []} />

          {/* The briefs by phase stood here, under the priority plan, and
              were the longest thing on the screen - and the operator found
              them in the wrong place (2026-09-03): a catalogue of what may be
              bought is not a reading of what one audit found. Parked under
              Admin as a tab of its own for the moment, where the same list
              runs against the audit picked there; this line says where it
              went, so a habit of scrolling to it does not end at a blank. */}
          <p className="muted phase-moved">
            The analyses by phase have moved to{" "}
            <a href="#/admin?tab=workbench"
               onClick={navHandler("#/admin?tab=workbench")}>
              Admin, under Workbench
            </a>
            , where they run against the audit you pick there.
          </p>

          <h3>
            Issues by cause{" "}
            <SecondaryButton onClick={() => setFlat(!flat)}>
              {flat ? "group by cause" : "show every finding"}
            </SecondaryButton>
          </h3>
          {flat
            ? <FindingsTable findings={data.deterministic_findings ?? []} />
            : <GroupedFindings findings={data.deterministic_findings ?? []}
                               onOpenPage={(url) =>
                                 goto(`#/runs/${runId}/page/${encodeURIComponent(url)}`)} />}

          <AnalystBand findings={data.analyst_findings ?? []} />

          {!!data.costs?.length && (
            <>
              <h3>Cost log</h3>
              <table className="findings">
                <thead><tr><th>Provider</th><th>Operation</th><th>Quantity</th></tr></thead>
                <tbody>
                  {data.costs.map((c, i) => (
                    <tr key={i}><td>{c.provider}</td><td><code>{c.operation}</code></td>
                        <td>{c.quantity} {c.units}
                          {c.actual_cost != null && ` · ${money(c.actual_cost)}`}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </>
  );
}

// ---- single page within a run ----------------------------------------------

export function PageDetailView({ runId, url }: { runId: string; url: string }) {
  // The page-scoped briefs, from the lanes payload's own headers (brief
  // v11 step AI) rather than a list kept here.
  const { data: pageLanes } = useAnalyses(runId);
  const pageExperts: ExpertSpec[] = (pageLanes ? [...pageLanes.ready, ...pageLanes.available] : [])
    .filter((x) => x.type === "page")
    .map((x) => ({ id: x.tool, name: x.name, blurb: x.does,
                   tier: x.tier as ExpertSpec["tier"], inputs: x.inputs }));
  const { data, error, loading, retry } = useFetch<Run>(`/api/runs/${runId}`);
  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!data) return <Loading />;
  const mine = (data.deterministic_findings ?? [])
    .filter((f) => f.affected_urls.includes(url));

  return (
    <>
      <h2>{pathOf(url)}</h2>
      <p className="muted">
        <a href={`#/runs/${runId}`}>back to the audit {runId.slice(0, 8)}</a> ·{" "}
        <a href={url} target="_blank" rel="noopener noreferrer">open page ↗</a>
      </p>
      <PageAdvice runId={runId} url={url} />
      <SchemaAuditPanel runId={runId} url={url} />
      <ExpertPanel runId={runId} siteId={data.site_id} tools={pageExperts} url={url}
                   heading="Page-level experts" />
      <h3>Findings on this page ({mine.length})</h3>
      {mine.length
        ? <FindingsTable findings={mine} />
        : <p className="muted">No deterministic findings recorded for this URL.</p>}
    </>
  );
}

// ---- compare ---------------------------------------------------------------

/** A comparison reason, as `compare_runs` returns it: facts, no formatting.
 *  The document renders these with backticks and a provenance tag because its
 *  honesty gate needs them; the screen does not, and used to strip that markup
 *  back off with three chained regexes — of which one matched nothing. Each
 *  surface now formats the same parts its own way and neither parses the
 *  other. */
type Reason = { lead: string; paths: string[]; overflow: number };
type NotRechecked = Finding & { not_rechecked_reason?: Reason };
type CompareResult = { new: Finding[]; resolved: Finding[];
                       not_rechecked: NotRechecked[]; persisting: Finding[];
                       /* Two counts of what the current run read, because
                        *  there are two and they are not the same quantity —
                        *  CQ-04. `pages_fetched` is the pages a check could
                        *  read; `pages_crawled` is the distinct paths they
                        *  sit on, which is fewer wherever the site serves one
                        *  page under two URL forms. Absent, not null, when
                        *  the run stored no evidence. */
                       /* And the same two counts for the baseline, because
                        *  `New` and `Resolved` are decided against it rather
                        *  than against the current run — WF-28. Absent
                        *  whenever run A recorded neither, since the payload
                        *  is computed live from the two runs. */
                       /* And, beside each page count, which of three ways it
                        *  was arrived at — CQ-205. `compare_runs` has spread
                        *  both of these into the frame since `99de440` and
                        *  nothing read either: a count the crawler counted
                        *  and one reconstructed from the stored page list
                        *  reached this screen indistinguishable. Optional
                        *  because a run whose evidence predates that commit
                        *  recorded neither, so the live diff has neither to
                        *  spread, and absent is not `attempted`. */
                       scope?: { pages_crawled: number | null;
                                 pages_fetched?: number | null;
                                 pages_fetched_basis?: string | null;
                                 dimensions: string[];
                                 pages_crawled_baseline?: number | null;
                                 pages_fetched_baseline?: number | null;
                                 pages_fetched_basis_baseline?: string | null;
                                 dimensions_baseline?: string[] } };

/** The screen's half of CQ-04, kept in step with `_diff_scope_lines`.
 *
 *  One count of what the run read, with the other named as the different
 *  quantity it is and only where they differ. The two surfaces state the same
 *  fact from one payload; the wording differs because this one has no
 *  markdown renderer and the document has no room for a second clause. */
/** How a page count was arrived at, in the words the document uses — CQ-205.
 *
 *  These strings are `PAGES_FETCHED_BASIS_NOTE` in
 *  `clauditseo/reporting/render.py`. TypeScript cannot import a Python dict,
 *  so the only thing holding the two in step is
 *  `tests/test_a_page_count_says_how_it_was_arrived_at.py`, which reads both
 *  files and fails if the wording diverges. An operator who reads the screen
 *  and the deliverable for the same run must be told the same thing in the
 *  same words, or the difference reads as a difference in the fact.
 *
 *  `recorded` is absent on purpose and the reason is in the Python owner: it
 *  is the ordinary rung, and a qualifier on every line is one nobody reads. */
const BASIS_NOTE: Record<string, string> = {
  derived: "count derived from the stored page list",
  attempted: "count is URLs attempted, not pages read",
};

function scopeCount(scope: { pages_crawled: number | null;
                             pages_fetched?: number | null;
                             pages_fetched_basis?: string | null }): string {
  const { pages_crawled: paths, pages_fetched: pages } = scope;
  if (pages !== null && pages !== undefined) {
    /* After both clauses rather than beside the figure, matching
     * `_run_phrase`: a parenthetical wedged between the page count and the
     * path count splits one quantity's sentence with a note about the
     * other's derivation. Silent for `recorded` and for a run that recorded
     * no rung — those are different facts and both are rendered as nothing,
     * because stating a rung on no evidence is the invention the key exists
     * to prevent. */
    const note = BASIS_NOTE[scope.pages_fetched_basis ?? ""];
    return `fetched ${pages} page(s)`
      + (paths !== null && paths !== pages ? ` across ${paths} distinct path(s)` : "")
      + (note ? ` (${note})` : "");
  }
  /* A run that recorded no readable-page count leaves the path count as the
   * only one there is. Calling it pages would assert a grain the payload
   * never established. */
  if (paths !== null) return `read ${paths} distinct path(s)`;
  return "fetched an unrecorded number of page(s)";
}

export function CompareView({ a, b }: { a: string; b: string }) {
  const { data, error, loading, retry } = useFetch<CompareResult>(`/api/compare?a=${a}&b=${b}`);
  //: WF-21, carried High from report 026 to 094. `TEMPLATES` has held
  //: `comparison` for the product's whole life and the CLI has always asked
  //: for it, but the dashboard's only creating call to `/api/reports` posts
  //: `run_ids: [runId]` — one id, and a comparison needs two. This screen is
  //: the only place in the product holding both, so it is where the door goes.
  //: Above the hook rules rather than beside the control: these must run
  //: before the two early returns below, or the hook order changes between
  //: a loaded and an erroring render.
  const [audience, setAudience] = useState("client");
  const [making, setMaking] = useState(false);
  const [made, setMade] = useState<
    { id: string; path: string; warnings: string[] } | null>(null);
  const [madeError, setMadeError] = useState<string | null>(null);

  //: No `SpendMark`: `generate()` reaches no provider — it reads stored
  //: evidence — so this control spends nothing. Marking one that does not
  //: spend is what `e979b1c` reverted `711557e` for.
  const generate = async () => {
    setMaking(true);
    setMadeError(null);
    setMade(null);
    try {
      const resp = await api.post<{ id: string; path: string;
                                    warnings?: string[] }>("/api/reports", {
        template: "comparison", audience, run_ids: [a, b],
      });
      setMade({ id: resp.id, path: resp.path, warnings: resp.warnings ?? [] });
    } catch (e) {
      // Said on the screen, not swallowed. The honesty gate refuses to
      // generate for some sites (KI-48) and answers 500 with what it
      // objected to; a press that silently did nothing would read as one
      // that worked.
      setMadeError((e as ApiError).message);
    } finally {
      setMaking(false);
    }
  };

  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!data) return <Loading />;
  /** The screen's half of the formatting. Plain prose: no backticks, no
   *  provenance clause — there is no markdown renderer here and no room for
   *  one on a single-line note. */
  const reasonText = (r: Reason) =>
    r.paths.length
      ? `${r.lead}: ${r.paths.join(", ")}${r.overflow ? ` (+${r.overflow} more)` : ""}`
      : r.lead;

  /** `reasonKey` names a per-finding qualifier to render beneath the line.
   *  One helper rather than a second bespoke card: the not-re-checked block
   *  below was written that way and `new` then had nowhere to put the same
   *  kind of sentence, which is how a bucket ended up carrying a reason the
   *  screen could not show. */
  const section = (title: string, items: Finding[], cls: string,
                   reasonKey?: "new_reason", label?: string) => (
    <Card>
      <h3 className={cls}>{title} ({items.length})</h3>
      {items.length
        ? <ul>{items.map((f) => (
            <li key={f.fingerprint}>
              [{f.severity}] {f.dimension}/{f.check_id} — {f.summary}
              {reasonKey && (f as Finding & { new_reason?: Reason })[reasonKey] &&
                <div className="muted rec">
                  {label}: {reasonText((f as Finding & { new_reason?: Reason })[reasonKey]!)}
                </div>}
            </li>
          ))}</ul>
        : <p className="muted">None.</p>}
    </Card>
  );
  return (
    <>
      <h2>Audit comparison</h2>
      <p className="muted">
        baseline <a href={`#/runs/${a}`}>{a.slice(0, 8)}</a> → current{" "}
        <a href={`#/runs/${b}`}>{b.slice(0, 8)}</a> (diffed by finding fingerprint;
        a finding the later audit never crawled is reported as not re-checked
        rather than resolved, and one the baseline never crawled is marked new
        to this record rather than new to the site)
      </p>
      <p className="muted">
        {/* WF-02: the scope the diff was computed under, from the diff
            itself, so this sentence cannot drift from the buckets above. */}
        {data.scope
          ? `Current audit ${scopeCount(data.scope)} and audited `
            + `${data.scope.dimensions.join(", ") || "no dimensions"}.`
          : "This comparison did not report the scope it was computed under."}
      </p>
      <p className="muted">
        {/* WF-28, the screen's half. The sentence above frames the current
            run, and the two cards below it that are decided by the baseline
            — New and Resolved — were left standing on a frame this screen
            never showed. Same payload, same derivation, second sentence. */}
        {data.scope && (data.scope.pages_crawled_baseline !== undefined
                        || data.scope.dimensions_baseline !== undefined)
          ? `Baseline audit ${scopeCount({
              pages_crawled: data.scope.pages_crawled_baseline ?? null,
              pages_fetched: data.scope.pages_fetched_baseline,
              /* CQ-205. The current run's sentence gets its rung by passing
               * `data.scope` whole; this one is rebuilt key by key, so a rung
               * added to the payload and not added here is silently dropped
               * on the baseline alone -- WF-28's exact shape. */
              pages_fetched_basis: data.scope.pages_fetched_basis_baseline })} and audited `
            + `${(data.scope.dimensions_baseline ?? []).join(", ") || "no dimensions"}. `
            + "New and Resolved are counted against it."
          : "This comparison did not report the baseline scope New and "
            + "Resolved were counted against."}
      </p>
      {/* WF-21. Below the two frame sentences deliberately: what the document
          says is what those sentences frame, so an operator reads the scope
          before asking for the artefact of it. Above the buckets, because a
          control placed under four scrolling lists is one the affordance
          invariant would count as absent again. */}
      <div className="inline-form">
        <select value={audience} onChange={(e) => setAudience(e.target.value)}
                aria-label="audience">
          <option value="client">Client-facing</option>
          <option value="internal">Internal technical</option>
        </select>
        {/* UX-88. The caption no longer swaps to a busy word. The label is
            this control's accessible name, so a name that changes mid-press
            is announced as a different control appearing — which is why
            `reports.tsx:270-289` moved the same word off the same kind of
            button for UX-64, and this is that convention rather than a
            second one. `aria-busy` carries the state the caption used to. */}
        <PrimaryButton onClick={generate} disabled={making} aria-busy={making}>
          Generate comparison report
        </PrimaryButton>
      </div>
      {/* UX-88. Failure on this control was announced and success was not:
          `madeError` renders through `ErrorNote`, which carries
          `role="alert"`, while the "Saved to …" line was a plain paragraph.
          So the one outcome a screen-reader operator was told about was the
          one where no document was produced — WCAG 2.2 AA 4.1.3 Status
          Messages, and the same sentence UX-64 was.

          Mounted unconditionally, and that is the load-bearing part: a live
          region inserted in the same render as its text gives assistive tech
          nothing to observe a change against, so the region has to be here
          before there is anything to say. It is empty while idle. */}
      <div className="muted compare-made" role="status" aria-live="polite">
        {making && <Working>Generating the comparison report…</Working>}
        {!making && made && (
          <>
            {/* Producing and reading are different acts on different routes —
                `App.tsx` states that rule for `#/reports/<run>` against
                `#/client-reports/<id>`, and this honours it rather than
                rendering the document inline where it was made. */}
            Saved to {made.path} — <a href={`#/client-reports/${made.id}`}>open
            the document</a>.
          </>
        )}
      </div>
      {madeError && <ErrorNote error={madeError} />}
      {/* The same sentence the single-run screen carries, for the same
          reason and in the same words: these are not errors, they are things
          about the document worth knowing before it is sent. */}
      {made?.warnings.map((w) => (
        <p key={w} className="muted"><strong>Before you send this:</strong> {w}</p>
      ))}
      <div className="cols">
        {section("New", data.new, "regressed", "new_reason", "new to this record")}
        {section("Resolved", data.resolved, "good-text")}
        {section("Persisting", data.persisting, "")}
        {/* Not green. These are absent from the later run because it never
            crawled their pages, and were counted as resolutions until round
            022 — 347 of them on one real comparison. */}
        <Card>
          <h3 className="muted">Not re-checked ({(data.not_rechecked ?? []).length})</h3>
          {(data.not_rechecked ?? []).length
            ? <ul>{(data.not_rechecked ?? []).map((f) => (
                <li key={f.fingerprint}>
                  [{f.severity}] {f.dimension}/{f.check_id} — {f.summary}
                  {f.not_rechecked_reason &&
                    <div className="muted rec">not re-checked: {reasonText(f.not_rechecked_reason)}</div>}
                </li>
              ))}</ul>
            : <p className="muted">None.</p>}
        </Card>
      </div>
    </>
  );
}

// ---- launcher --------------------------------------------------------------

function DepPills({ meta, codes }: { meta: Meta; codes: string[] }) {
  const names = [...new Set(codes.flatMap((c) => meta.dimension_providers[c] ?? []))];
  if (!names.length) return null;
  return (
    <span className="dep-pills">
      {names.map((name) => {
        const p = meta.providers[name];
        if (!p) return null;
        const tone = p.configured ? "state-fixed" : "held";
        return (
          <Pill key={name} tone={tone}
                title={p.configured ? p.detail
                       : `Not configured — runs without it at lower confidence. `
                         + `To enable: Admin -> Provider keys, or `
                         + `setx ${p.env} "<value>" then refresh.`}>
            {name}{p.configured ? " ✓" : " —"}
          </Pill>
        );
      })}
    </span>
  );
}

/** Dimensions under the headings the Current tab uses.
 *
 *  Derived, not asserted: crossing every check each dimension raises with the
 *  category registry puts each dimension wholly in one group — 11/11, 16/16,
 *  5/5 and so on, nothing straddling. So the two vocabularies genuinely are
 *  the same partition seen twice, and this screen no longer has to be
 *  translated on arrival from the client screen. */
const DIM_GROUPS: { heading: string; blurb: string; dims: string[] }[] = [
  { heading: "On the page",
    blurb: "fixed by editing a page",
    dims: ["ONP", "CNT", "A11Y"] },
  { heading: "Across the site",
    blurb: "fixed once, for everything",
    dims: ["TEC", "PRF", "SEC"] },
  { heading: "Beyond the site",
    blurb: "not fixed by editing the site at all",
    dims: ["LOC", "OFP", "AIS"] },
];

interface ScanBannerRun {
  scan_scope?: string | null;
  scan_depth?: string | null;
  scan_url?: string | null;
  /** The stored column: a JSON-encoded array of paths. */
  crawled_paths?: string | string[] | null;
}

const SCAN_SCOPE_WORDS: Record<string, string> = {
  page: "One page", nav: "The navigation", site: "A sample of the site",
  full: "Every reachable page",
};
const SCAN_DEPTH_WORDS: Record<string, string> = {
  quick: "checklist only, no model",
  standard: "with judgement at the edges",
  deep: "read deeply",
};

/** What the run was, said once, at the top.
 *
 *  Absent for every run made before the chooser existed — and absent is what
 *  it renders as, because those runs were not chosen on these axes and
 *  captioning one "a site scan" would be this screen inventing a fact the
 *  record does not hold.
 */
/** How many pages a run reached (item 180, UI audit 08-1). The run payload
 *  carries `crawled_paths` as the column stores it - a JSON-encoded string - so
 *  `.length` counted its characters: "reached 5743 pages" on a 100-page crawl.
 *  Parsed here, and an array is accepted too, since the type said one. */
export function crawledCount(paths: string | string[] | null | undefined): number | null {
  if (paths == null) return null;
  if (Array.isArray(paths)) return paths.length;
  try {
    const parsed: unknown = JSON.parse(paths);
    return Array.isArray(parsed) ? parsed.length : null;
  } catch {
    return null;
  }
}

export function ScanBanner({ run }: { run: ScanBannerRun }) {
  if (!run.scan_scope) return null;
  const scope = SCAN_SCOPE_WORDS[run.scan_scope] ?? run.scan_scope;
  const depth = run.scan_depth
    ? SCAN_DEPTH_WORDS[run.scan_depth] ?? run.scan_depth : null;
  const reached = crawledCount(run.crawled_paths);
  return (
    <p className="scan-banner">
      <strong>{scope}</strong>
      {depth && <span className="muted"> — {depth}</span>}
      {run.scan_url && <span className="scan-banner-url"> · {run.scan_url}</span>}
      {reached !== null && (
        <span className="muted"> · reached {reached} page{reached === 1 ? "" : "s"}</span>
      )}
    </p>
  );
}


export function LauncherView({ siteId }: { siteId: string }) {
  const { data: meta, error, loading, retry } = useFetch<Meta>("/api/meta");
  const [dims, setDims] = useState<Set<string>>(new Set());
  const [tier, setTier] = useState("auto");
  const [analyst, setAnalyst] = useState(false);
  /** Crawl the entry page and whatever its menu links to, and stop.
   *  Built and tested in the crawler months ago and reachable over the API,
   *  but never given a control here — so the only way to run it was curl. */
  const [navOnly, setNavOnly] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const [startUrl, setStartUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  /** WF-82. The verdict of the read-only check, or null when nothing has
   *  been asked about the URL now in the field. Cleared on every keystroke
   *  rather than left standing, because a verdict about a string the
   *  operator has since edited is worse than no verdict — it reads as an
   *  answer to the question they are about to ask. */
  const [urlVerdict, setUrlVerdict] =
    useState<{ acceptable: boolean; problem: string | null } | null>(null);
  const [checking, setChecking] = useState(false);
  /** The precheck feeds the chooser its page counts, and is re-read after one
   *  is run so every cell stops saying "run it" in the same breath. */
  const [preTick, setPreTick] = useState(0);
  const { data: precheck, loading: precheckLoading } = usePrecheck(siteId, preTick);

  useEffect(() => {
    if (meta && !dims.size) setDims(new Set(meta.dimensions.map((d) => d.code)));
  }, [meta]);

  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!meta) return <Loading />;

  /** Whole group on or off. Auditing "everything on the page" is a sentence
   *  an operator has; ticking three codes to express it is not. */
  const toggleGroup = (codes: string[], on: boolean) => {
    const next = new Set(dims);
    for (const c of codes) { if (on) next.add(c); else next.delete(c); }
    setDims(next);
  };

  const toggle = (code: string) => {
    const next = new Set(dims);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setDims(next);
  };

  /** WF-82: ask whether the URL would be accepted, without buying the run
   *  that acceptance would otherwise start. The server answers from the same
   *  `_validate_start_url` the launch consults, so this cannot become a
   *  second opinion about what a host is. */
  const checkUrl = async () => {
    const url = startUrl.trim();
    if (!url) return;
    setChecking(true);
    setUrlVerdict(null);
    try {
      setUrlVerdict(await api.get<{ acceptable: boolean; problem: string | null }>(
        `/api/sites/${siteId}/start-url-check?url=${encodeURIComponent(url)}`));
    } catch (e) {
      setLaunchError((e as ApiError).message);
    } finally {
      setChecking(false);
    }
  };

  const launch = async () => {
    setBusy(true);
    setLaunchError(null);
    try {
      const resp = await api.post<{ run_id: string }>(`/api/sites/${siteId}/audits`, {
        dims: [...dims], tier,
        // WF-102. `analyst` is tri-state on the server (`AuditIn`): `null`
        // means "let the tier decide", and an explicit `false` DECLINES the
        // layer. On `auto` this screen renders no analyst control at all —
        // the checkbox is in the `tier !== "auto"` branch — so the `analyst`
        // state below is whatever `useState(false)` left, and sending it
        // answered a question the operator was never asked. Every default
        // press therefore turned the paid layer off while the spend mark
        // beside the button said it would run. `null` is the screen saying it
        // has no answer, which is the truth of what it rendered.
        analyst: tier === "auto" ? null : analyst,
        model: analyst ? model ?? meta.models[0] : null,
        start_url: startUrl.trim() || null,
        nav_only: navOnly,
      });
      goto(`#/runs/${resp.run_id}`);
    } catch (e) {
      setLaunchError((e as ApiError).message);
      setBusy(false);
    }
  };

  const unconfigured = Object.entries(meta.providers)
    .filter(([, p]) => !p.configured);

  return (
    <>
      {/* Item 188: this was conditional on an `embedded` flag that only the
          retired Tools screen ever set, where the picker sat inside a page
          that had already headed it. One caller, one branch, and both are
          gone - the heading is now simply the screen's. */}
      <h2>What should we look at?</h2>

      {/* The chooser leads; the controls below are still here for anyone who
          wants to name dimensions and a tier by hand. Two decisions on two
          axes first, four settings second — the reverse of how this screen
          read before, and the reason it read as "do this scan" with nothing
          saying which. */}
      <Card>
        <h3>Choose a scan</h3>
        <PrecheckPanel siteId={siteId} data={precheck ?? null}
                       onRan={() => setPreTick((t) => t + 1)} />
        <ScanMatrix siteId={siteId} precheck={precheck ?? null}
                    precheckLoading={precheckLoading}
                    onLaunched={(runId) => {
                      navigate(`#/runs/${runId}`);
                    }} />
      </Card>

      <Card>
        <h3>Or set it up by hand</h3>
        <p className="muted">
          Every control the chooser sets, and the ones it does not: which
          dimensions run, an adaptive tier that picks its own breadth, and a
          different entry URL.
        </p>
        {/* Grouped by where a fix lands, which is how the Current tab is
            organised and how anyone actually works a site. The engine's
            dimension codes stay visible because runs, scores and the API all
            speak them — but they are no longer the only label, so arriving
            here from "Run an audit" is not a change of language.

            The grouping is not a guess: every check each dimension raises
            falls in exactly one of the three, with no dimension straddling
            two. A11Y, CNT and ONP are entirely on-page; PRF and TEC entirely
            site-wide; AIS, LOC and OFF entirely off-site. */}
        {DIM_GROUPS.map((g) => {
          const inGroup = meta.dimensions.filter((d) => g.dims.includes(d.code));
          if (!inGroup.length) return null;
          const allOn = inGroup.every((d) => dims.has(d.code));
          return (
            <section key={g.heading} className="dim-group">
              <div className="dim-group-head">
                <h4>{g.heading}</h4>
                <span className="muted">{g.blurb}</span>
                <SecondaryButton
                        onClick={() => toggleGroup(inGroup.map((d) => d.code), !allOn)}>
                  {allOn ? "none" : "all"}
                </SecondaryButton>
              </div>
              <div className="dim-grid">
                {inGroup.map((d) => (
                  <label key={d.code}>
                    <input type="checkbox" checked={dims.has(d.code)}
                           onChange={() => toggle(d.code)} /> {d.name}{" "}
                    <code className="dim-code">{d.code}</code>{" "}
                    <DepPills meta={meta} codes={[d.code]} />
                    {/* The sections this refreshes, named. The launcher picks
                        dimensions and every other screen groups by section,
                        and one dimension covers up to four of them — so
                        "audit Images" is not something the engine can be
                        asked for, and a picker that implied otherwise would
                        offer a control that cannot exist. */}
                    {!!d.categories?.length && (
                      <span className="dim-cats">
                        refreshes {d.categories.join(", ")}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            </section>
          );
        })}
        <p className="muted">
          Dimensions without pills run fully offline from the crawl. A grey pill
          means that data source is optional and currently off — the audit still
          runs, tagging affected checks as lower confidence or not assessed.
        </p>
        {/* The gap between the two vocabularies, said outright rather than
            left to be discovered: three sections on the client screen have no
            sweep behind them at all. Ticking everything here still leaves
            them empty, and a zero beside them is "nothing covers this", not
            "checked and clean". */}
        {!!meta.analysis_only?.length && (
          <p className="muted launch-gap">
            <strong>No automatic check covers {meta.analysis_only.join(", ")}.</strong>{" "}
            Those sections are filled by an analysis rather than by the crawl,
            so running every dimension above leaves them untouched — a zero
            against them means nothing has looked, not that they are clean.
          </p>
        )}
        {/* Item 183 (channel ruling 20260918-0410): scope is what this chooses.
            The crawler tier is what `tier_for_scope` derives from a scope, so a
            tier offered as a choice is a control that does not exist; the words
            here are the scope's, and the tier each posts is the receipt. */}
        <h3>How much of the site</h3>
        <div className="dim-grid">
          {meta.tiers.map((t) => (
            <label key={t}>
              <input type="radio" name="tier" checked={tier === t}
                     onChange={() => setTier(t)} /> {SCOPE_WORD[t] ?? t}
              {t === "auto" &&
                " — decided as it goes: a pulse first; dimensions scoring ≥95 stop, "
                + "80–94 get a full crawl, 60–79 add their analyst, <60 go deep "
                + "with paid APIs where keyed"}
              {t === "T1" && " — the home page, robots.txt and the sitemap head"}
              {t === "T2" && " — a representative sample, up to 100 pages"}
              {t === "T3" && " — every reachable page, up to 500, with paid APIs where keyed"}
            </label>
          ))}
        </div>
        {/* Sits with the tier because it overrides what the tier means:
            the budget stops mattering once the frontier is the menu. */}
        <label className="nav-only">
          <input type="checkbox" checked={navOnly && tier !== "auto"}
                 disabled={tier === "auto"}
                 onChange={(e) => setNavOnly(e.target.checked)} />{" "}
          Navigation only — the entry page and the pages its menu links to
          {tier === "auto" && (
            <span className="muted">
              {" "}· needs a fixed tier: an adaptive run decides its own depth,
              which is the opposite of naming the pages up front
            </span>
          )}
          {navOnly && tier !== "auto" && (
            <span className="muted">
              {" "}· the pages a site considers important enough to link from
              every page. On the site this was built against that is 20 pages
              rather than the 271 in its sitemap.
            </span>
          )}
        </label>

        <h3>Analyst layer
          <span className="dep-pills">
            <Pill tone={meta.analyst_available ? "state-fixed" : "held"}
                  title={meta.analyst_available ? meta.providers["LLM analyst"].detail
                         : `To enable: Admin -> Provider keys, or `
                           + `setx ${meta.providers["LLM analyst"].env} "<value>" then refresh.`}>
              LLM analyst{meta.analyst_available ? " ✓" : " —"}
            </Pill>
          </span>
        </h3>
        {tier === "auto" ? (
          <p className="muted">
            Managed by the escalation bands: analysts run automatically for any
            dimension scoring below 80, within the token ceiling
            ({meta.analyst_budgets.T3} tokens).
          </p>
        ) : (
          <label>
            <input type="checkbox" checked={analyst} disabled={!meta.analyst_available || tier === "T1"}
                   onChange={(e) => setAnalyst(e.target.checked)} />{" "}
            {meta.analyst_available
              ? `Enable LLM analyst (budget ${tier === "T3" ? meta.analyst_budgets.T3 : meta.analyst_budgets.T2} tokens; never runs on T1)`
              : `Unavailable — set ${meta.providers["LLM analyst"].env} to enable`}
          </label>
        )}
        {meta.analyst_available && (
          <p>
            <label>
              Model:{" "}
              <select value={model ?? meta.models[0]} disabled={!analyst}
                      onChange={(e) => setModel(e.target.value)} aria-label="analyst model">
                {meta.models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          </p>
        )}
        <h3>Start URL override <span className="muted">(optional, for staging/local)</span></h3>
        <input value={startUrl}
               onChange={(e) => { setStartUrl(e.target.value); setUrlVerdict(null); }}
               placeholder="https://staging.example.com/" style={{ width: "100%" }} />
        {/* WF-82. Pressing Run audit is how an operator used to find out
            whether a URL was acceptable, and a yes started a crawl and left
            a permanent run (`OPERATOR_ACTIONS.md:139`). This asks the same
            question and buys nothing. */}
        {/* UX-96. The caption no longer swaps to a busy word. A button's
            label is its accessible name, so a name that changes mid-press is
            announced as a different control appearing — which is why
            `reports.tsx:270-289` moved the same word off the same kind of
            button for UX-64, and why round 111 moved it off `CompareView`'s
            generate control thirteen hundred lines above (UX-88). This is
            that convention taken a third time rather than a fourth wording.
            `aria-busy` carries the state the caption used to, and the region
            below says it in words for the operator who can see neither. */}
        <p>
          <SecondaryButton onClick={checkUrl} disabled={checking || !startUrl.trim()}
                  aria-busy={checking}>
            Check this URL
          </SecondaryButton>{" "}
          <span className="muted">Answers without starting a run.</span>
        </p>
        {/* UX-97. Mounted unconditionally, and that is the load-bearing part:
            a live region inserted in the same render as its text gives
            assistive technology nothing to observe a change against, so the
            paragraph this used to be — `{urlVerdict && <p role="status">}` —
            appeared silently. The region has to be here before the answer is.
            `aria-live="polite"` is stated rather than left to the implicit
            mapping of `role="status"`, matching `Loading` in
            `components.tsx` and `reports.tsx`'s generate control, so the screen keeps
            one convention. Empty while idle: `.url-verdict:empty` drops the
            margin so an always-present element costs no space. */}
        <p className={"url-verdict"
                      + (urlVerdict && !urlVerdict.acceptable
                          ? " url-verdict-refused" : "")}
           role="status" aria-live="polite">
          {checking && <Working>Checking this start URL…</Working>}
          {!checking && urlVerdict && (urlVerdict.acceptable
            ? "This start URL would be accepted. Nothing has been run."
            : urlVerdict.problem)}
        </p>
        {launchError && <ErrorNote error={launchError} />}
        <p>
          {/* F-10. An audit is a crawl, but the analyst layer rides on it and
              that layer calls a model. The condition mirrors the server's own
              recorded gate — `analyst_enabled` on the stored run scope
              `analyst_enabled = body.analyst if body.analyst is not None
              else body.tier == "auto"` — narrowed by the two cases
              `analysts/layer.py` refuses outright: T1 never invokes the
              layer, and a run with no provider configured cannot. Auto is
              this picker's default, so the default click does spend.

              CQ-232: this used to quote `app.py:1137` and the pre-WF-59
              boolean-or form, `body.analyst or body.tier == "auto"`. Both
              were a full round stale — the gate is tri-state now — and the
              bare `app.py:1137` is a citation `scripts/check_anchors.py`
              cannot resolve, so nothing caught it. A maintainer reading the
              old text would have believed the launcher's `analyst: false`
              was still absorbed by the `or`, which is WF-102 exactly. */}
          {/* UX-66. Stable caption, state on `aria-busy`, words in the
              unconditionally-mounted region below — the same convention this
              file's own `ReportView` generate control takes. */}
          {/* Item 178 (03-1): when the analyst layer runs this spends, so it
              is the spend control, priced in words and confirmed; without it the
              audit costs time only and starts on the press as before. */}
          {meta.analyst_available && tier !== "T1" && (analyst || tier === "auto") ? (
            <SpendButton price={null} busy={busy}
                         why={!dims.size ? "choose at least one dimension" : null}
                         confirm={{ title: "Run this audit?",
                                    body: <><SpendTarget page={startUrl.trim() || null} />
                                      <p>Depth {tier === "auto" ? "chosen as it goes" : tier};
                                        dimensions {[...dims].join(", ")}. The analyst layer runs,
                                        so it spends model tokens.</p></>,
                                    action: "Run the audit" }}
                         onSpend={launch}>
              Run audit
            </SpendButton>
          ) : (
          <PrimaryButton onClick={launch} disabled={busy || !dims.size}
                  aria-busy={busy}>
            Run audit
          </PrimaryButton>
          )}
        </p>
        <div className="muted" role="status" aria-live="polite">
          {busy && <Working>Launching the audit…</Working>}
        </div>
      </Card>
      {unconfigured.length > 0 && (
        <Card>
          <h3>Enable more data sources</h3>
          <p className="muted">
            Each is optional — audits run without them at lower confidence. The
            quickest route is <strong>Admin → Provider keys</strong>, which takes
            effect immediately. Or set the variable and refresh this page (no
            server restart needed):
          </p>
          <ul>
            {unconfigured.map(([name, p]) => (
              <li key={name}>
                <strong>{name}</strong> — {p.detail}:{" "}
                <code>setx {p.env} "&lt;your value&gt;"</code>{" "}
                <CopyCmd cmd={`setx ${p.env} "<your value>"`} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

// ---- reports ---------------------------------------------------------------

export function ReportView({ runId }: { runId: string }) {
  const [template, setTemplate] = useState("run");
  const [audience, setAudience] = useState("client");
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  //: Not errors — the report was made. Things about it worth knowing before
  //: it is sent, said here because this is the moment they apply.
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    setError(null);
    setWarnings([]);
    try {
      const resp = await api.post<{ markdown: string; path: string;
                                    warnings?: string[] }>("/api/reports", {
        template, audience, run_ids: [runId],
      });
      setMarkdown(resp.markdown);
      setPath(resp.path);
      setWarnings(resp.warnings ?? []);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2>Generate report</h2>
      <p className="muted">Run <a href={`#/runs/${runId}`}>{runId.slice(0, 8)}</a></p>
      <div className="inline-form">
        <select value={template} onChange={(e) => setTemplate(e.target.value)}
                aria-label="template">
          <option value="run">Run report</option>
          {/* Brief v17 step AV6: the same document without the two
              sections a model wrote. Named for what it contains
              rather than for what it omits. */}
          <option value="run-free">Audit report — free checks only</option>
          <option value="monthly-trend">Monthly trend report</option>
        </select>
        <select value={audience} onChange={(e) => setAudience(e.target.value)}
                aria-label="audience">
          <option value="client">Client-facing</option>
          <option value="internal">Internal technical</option>
        </select>
        {/* UX-66. The caption no longer swaps to a busy word. A button's
            label is its accessible name, so a name that changes mid-press is
            announced as a different control appearing — which is why
            `reports.tsx:270-289` moved the same word off the same kind of
            button for UX-64, why round 111 moved it off `CompareView`'s
            generate control (UX-88), and why round 112 moved it off
            `LauncherView`'s "Check this URL" (UX-96). This is that convention
            taken a fourth time rather than a fourth wording. `aria-busy`
            carries the state the caption used to, and the region below says
            it in words for the operator who can see neither. */}
        <PrimaryButton onClick={generate} disabled={busy} aria-busy={busy}>
          Generate
        </PrimaryButton>
      </div>
      {error && <ErrorNote error={error} />}
      {/* UX-66. Mounted unconditionally, and that is the load-bearing part: a
          live region inserted in the same render as its text gives assistive
          technology nothing to observe a change against, so it has to be here
          before there is anything to say. Empty while idle. `aria-live` is
          stated rather than left to the implicit mapping of `role="status"`,
          matching `Loading` in `components.tsx`, `reports.tsx`'s generate control and
          `CompareView`'s, so the screen keeps one convention. */}
      <div className="muted" role="status" aria-live="polite">
        {busy && <Working>Generating the report…</Working>}
      </div>
      {/* Above the document, because it is about what is in it. Below the
          "Saved to" line it would read as a note about the file. */}
      {warnings.map((w) => (
        <p key={w} className="muted"><strong>Before you send this:</strong> {w}</p>
      ))}
      {path && <p className="muted">Saved to {path}</p>}
      {markdown && <RenderedMarkdown source={markdown} />}
    </>
  );
}

// ---- history chat ----------------------------------------------------------

type ChatEntry = { question: string; answer: string; cited_runs: string[] };

export function ChatView({ siteId }: { siteId: string }) {
  const [log, setLog] = useState<ChatEntry[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = async (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    try {
      const resp = await api.post<{ answer: string; cited_runs: string[] }>(
        "/api/chat", { site_id: siteId, question });
      setLog((l) => [...l, { question, ...resp }]);
      setQuestion("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2>History chat <span className="muted">(read-only)</span></h2>
      <p className="muted">
        Answers are grounded in this site's stored audits and findings, and cite
        the audits they drew from. Nothing here can change data.
      </p>
      {log.map((entry, i) => (
        <Card key={i}>
          <p><strong>You:</strong> {entry.question}</p>
          <p style={{ whiteSpace: "pre-wrap" }}>{entry.answer}</p>
          {!!entry.cited_runs.length && (
            <p className="muted">
              cited audits:{" "}
              {entry.cited_runs.map((r) => (
                <a key={r} href={`#/runs/${r}`} style={{ marginRight: 8 }}>
                  {r.slice(0, 8)}
                </a>
              ))}
            </p>
          )}
        </Card>
      ))}
      <form onSubmit={ask} className="inline-form">
        <input value={question} onChange={(e) => setQuestion(e.target.value)}
               placeholder="What regressed since the last audit?" style={{ flex: 1 }} />
        <SecondaryButton submit disabled={busy}>Ask</SecondaryButton>
      </form>
    </>
  );
}
