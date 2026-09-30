import { SecondaryButton } from "./buttons";
import { Working } from "./working";
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import { BriefPriceFrame, Card, ErrorNote, PriceScopeNote, SpendMark }
  from "./components";
import { ReportView } from "./markdown";
import { Pill, Tone } from "./pill";
import { SpendButton, SpendTarget } from "./spend";

/** A figure the analyst derived rather than quoting. Older cached envelopes
 *  stored a bare string, so both shapes are accepted. */
export type Figure = string | { value: string; context?: string };

/** What `GET /api/runs/{run}/expert/{tool}` returns to a screen that only
 *  reads a stored brief — the subset of `Envelope` that route serves.
 *
 *  Stated as its own type rather than reusing `Envelope`: the analyses lane
 *  never holds an `Envelope` (it has no `status`, no `tier`, no cost), and
 *  the previous shape there was the inline `{ report?: string }` written at
 *  two call sites, which is how the three figure fields the server has been
 *  serving since UX-79 came to be dropped on both — UX-03. One name, so the
 *  next field the route gains is added once. */
export type StoredBrief = {
  report?: string;
  figures_to_verify?: Figure[];
  figures_flagged?: number | null;
  /** What the parser made of the answer (brief v12 step AL). The part
   *  page has no Read button since brief v13 step AO, so this reader is
   *  where the dropped rows and their reasons are read. */
  contract?: Contract | null;
};

type RaisedFinding = {
  severity: string; code: string; summary: string; affected_urls?: string[];
};

export type Envelope = {
  /** `not_applicable` is a decision, not a failure: the server read the
   *  crawl, found nothing for this brief to audit, and refused the dispatch
   *  rather than billing for a report saying so. Q-32/CQ-223. It is rendered
   *  as a note and marked `skipped`, never as an error. */
  status: "ok" | "unavailable" | "empty" | "needs_input" | "not_applicable";
  reason?: string;
  required?: string[];
  cached?: boolean;
  tokens?: number;
  tokens_in?: number;
  tokens_out?: number;
  cost?: number | null;
  model?: string;
  tier?: string;
  tool?: string;
  report?: string;
  findings?: RaisedFinding[];
  figures_to_verify?: Figure[];
  /** How many derived figures the cap dropped from the list above.
   *  `null`/absent means never recorded (a brief stored before the count
   *  existed), which renders the same as zero — see migration 0027. */
  figures_withheld?: number | null;
  figures_flagged?: number | null;
  truncated?: boolean;
  /** What the contract made of a conforming brief's answer (brief v12
   *  step AL): the rows the parser dropped, each with its reason, and the
   *  rows the brief could not assess, each naming what it needs. */
  contract?: Contract | null;
};

export type ContractDrop = { row?: { check?: string; page?: string; replacement?: string } | null; reason: string };
export type ContractNeed = { check?: string; page?: string; needs?: string };
export type Contract = {
  status?: string; part?: string | null; strategy?: string | null;
  rows?: unknown[]; dropped?: ContractDrop[]; not_assessable?: ContractNeed[];
  assumptions?: string[]; uncovered?: unknown[]; reparsed?: boolean;
};

/** The contract's own accounting on a read report (brief v12 step AL):
 *  every row the parser dropped with the reason it gave, and every row the
 *  brief could not assess with what it needs. Rendered before the prose
 *  since these are the rows the replacement table does not show, and the
 *  part page points here for them. */
export function ContractAccount({ contract }: { contract?: Contract | null }) {
  if (!contract) return null;
  const dropped = contract.dropped ?? [];
  const needs = contract.not_assessable ?? [];
  if (!dropped.length && !needs.length) return null;
  const pathOf = (u?: string) => { if (!u) return ""; try { return new URL(u).pathname || "/"; } catch { return u; } };
  return (
    <div className="contract-account">
      {dropped.length > 0 && (
        <details className="contract-dropped" open>
          <summary>{dropped.length} row{dropped.length === 1 ? "" : "s"} dropped by the parser</summary>
          <table className="md-table contract-dropped-table">
            <thead><tr><th>Check</th><th>Page</th><th>Replacement</th><th>Reason</th></tr></thead>
            <tbody>
              {dropped.map((d, n) => (
                <tr key={n}>
                  <td><code>{d.row?.check ?? "—"}</code></td>
                  <td><code>{pathOf(d.row?.page) || "—"}</code></td>
                  <td className="muted">{d.row?.replacement ?? ""}</td>
                  <td>{d.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      {needs.length > 0 && (
        <details className="contract-needs" open>
          <summary>{needs.length} row{needs.length === 1 ? "" : "s"} not assessable</summary>
          <table className="md-table contract-needs-table">
            <thead><tr><th>Check</th><th>Page</th><th>Needs</th></tr></thead>
            <tbody>
              {needs.map((d, n) => (
                <tr key={n}>
                  <td><code>{d.check ?? "—"}</code></td>
                  <td><code>{pathOf(d.page) || "—"}</code></td>
                  <td>{d.needs ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

export type ExpertInput = {
  key: string; label: string; hint?: string;
  multiline?: boolean; required?: boolean;
};
export type ExpertSpec = {
  id: string; name: string; blurb: string; inputs?: ExpertInput[];
  tier?: "fast" | "standard" | "deep";
  /** Measured from this operator's own history, not estimated. */
  typicalCost?: number | null;
  typicalTokens?: number | null;
};

const TIER_NOTE: Record<string, string> = {
  fast: "routed to the fast model: this analysis applies a fixed checklist",
  standard: "routed to the standard model",
  deep: "routed to the best model: the judgement is the product",
};

// Local helper deleted: it disagreed with schedule.tsx on sub-dollar
// precision and carried no currency. One owner in components.tsx now, and
// re-exported here because callers already import `money` from this module.
import { money } from "./components";
export { money };

/** What this brief has typically cost. Dollars once rates are configured,
 *  otherwise tokens — never a guessed price. */
function priceHint(t: ExpertSpec): string {
  if (t.typicalCost != null) return `~${money(t.typicalCost)} a run`;
  if (t.typicalTokens != null) return `~${Math.round(t.typicalTokens / 1000)}k tokens a run`;
  return "not run yet";
}

/** `runs_costed` and `runs_sampled` are the two counts `/api/playbook`
 *  already puts beside the price (`runs_costed` in `/api/playbook`) and this
 *  screen has never read - UX-74. They are the population the median was
 *  taken over and the population it is a share of; the pair, so neither can
 *  be read as the other. */
type BriefMeta = { typical_cost?: number | null; typical_tokens?: number | null;
                   runs_costed?: number; runs_sampled?: number;
                   /** Which site's briefs the price was measured over, or
                    *  `null` for install-wide — CQ-198. Carried by
                    *  `/api/playbook` since UX-77 made the same path answer
                    *  both ways; this panel is one of the two on which a
                    *  brief is bought. */
                   scoped_to_site?: string | null;
                   tier?: string; model?: string };

const words = (s?: string) => (s ? s.trim().split(/\s+/).length : 0);

type StoredResult = { tool: string; created_at: string; findings: number;
                      cost?: number | null };

export function ExpertPanel({ runId, siteId, tools: given, url, heading, blurb }:
    { runId: string;
      /** Which site's history the prices below are drawn from — UX-77.
       *
       *  Required rather than optional, deliberately. An optional prop would
       *  have been a smaller diff and would leave the defect one forgetful
       *  call site away: omitting it silently restores the install-wide median
       *  this panel used to paint, and nothing on screen would say so. Made
       *  required, the compiler asks the question of every future caller. */
      siteId: string;
      tools: ExpertSpec[]; url?: string; heading: string;
      /** What *these* briefs read. One paragraph was hard-coded for every
       *  phase and described phase 1's evidence — inlink counts, canonical
       *  targets, sitemap reconciliation — under the content and local
       *  phases too, where it is simply untrue. */
      blurb?: string }) {
  // What each brief has actually cost this operator, so the choice of what to
  // run is made with the price in view rather than discovered afterwards.
  const [meta, setMeta] = useState<Record<string, BriefMeta>>({});
  const [deepModel, setDeepModel] = useState<string>("");
  /** Whether the prices have been read for this site (item 178): until then a
   *  spend here is held with "checking the price", not offered unpriced. */
  const [metaRead, setMetaRead] = useState(false);
  // `site_id` on the fetch, and keyed on it — UX-77. "What each brief has
  // actually cost this operator" was true of the install and read on screen as
  // true of the site in front of them, beside the control that spends.
  useEffect(() => {
    let live = true;
    const q = siteId ? `?site_id=${encodeURIComponent(siteId)}` : "";
    setMetaRead(false);
    api.get<{ experts: Record<string, BriefMeta>;
              model_tiers: Record<string, string> }>(`/api/playbook${q}`)
      .then((d) => { if (!live) return;
                     setMeta(d.experts ?? {}); setDeepModel(d.model_tiers?.deep ?? "");
                     setMetaRead(true); })
      // Advisory only: a failed read never blocks the panel, it leaves the
      // prices unknown - said as "no estimate yet", not held for ever.
      .catch(() => { if (live) { setMeta({}); setMetaRead(true); } });
    return () => { live = false; };
  }, [siteId]);
  const tools = given.map((t) => ({
    ...t,
    typicalCost: meta[t.id]?.typical_cost ?? null,
    typicalTokens: meta[t.id]?.typical_tokens ?? null,
    runsCosted: meta[t.id]?.runs_costed ?? 0,
    runsSampled: meta[t.id]?.runs_sampled ?? 0,
  }));
  // The scope of the whole payload, not of one brief - CQ-198. Every row in
  // one `/api/playbook` answer is priced under the same `site_id`, so the
  // first row carries the answer's scope. `undefined` before the payload
  // arrives, which is a panel with no price to frame rather than an
  // install-wide one - a distinction `null` carries and has to keep.
  const priceScope = Object.values(meta)[0];
  // What has already run against THIS audit. Without it the panel could not
  // answer the first question anyone asks of it — have these run? — because
  // `results` below only holds what was run in this browser session, so a
  // brief run yesterday looked identical to one never run at all.
  const [stored, setStored] = useState<Record<string, StoredResult>>({});
  const [loaded, setLoaded] = useState(false);
  const reloadStored = () =>
    api.get<{ results: StoredResult[] }>(`/api/runs/${runId}/expert`)
      .then((d) => {
        setStored(Object.fromEntries((d.results ?? []).map((r) => [r.tool, r])));
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  useEffect(() => { reloadStored(); }, [runId]);

  const [results, setResults] = useState<Record<string, Envelope>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openInputs, setOpenInputs] = useState<string | null>(null);
  /** Which reports are on screen. Separate from `results`, which is the
   *  cache: hiding a report should not throw away a fetch, and showing it
   *  again should be instant rather than another round trip. */
  const [openReports, setOpenReports] = useState<Set<string>>(new Set());
  const toggleReport = (id: string, on?: boolean) =>
    setOpenReports((cur) => {
      const next = new Set(cur);
      if (on ?? !next.has(id)) next.add(id); else next.delete(id);
      return next;
    });
  // A ref as well as state: the loop in runRest reads it between briefs, and
  // state captured in that closure would never see the change.
  const [stopped, setStopped] = useState(false);
  const stoppedRef = useRef(false);
  useEffect(() => { stoppedRef.current = stopped; }, [stopped]);
  const [values, setValues] = useState<Record<string, Record<string, string>>>({});

  const setValue = (toolId: string, key: string, value: string) =>
    setValues((v) => ({ ...v, [toolId]: { ...(v[toolId] ?? {}), [key]: value } }));

  const ask = (toolId: string, model?: string) =>
    api.post<Envelope>(`/api/runs/${runId}/expert/${toolId}`, {
      ...(url ? { url } : {}), inputs: values[toolId] ?? {},
      ...(model ? { model } : {}),
    });

  /** Fetch what this brief already said about this audit. Free — it reads
   *  the stored report rather than calling a model.
   *
   *  Without it the report vanished on reload: the panel kept results only in
   *  component state, so a brief run yesterday showed a tick and a date and
   *  no report at all, and the only route back to its contents was to run it
   *  again and pay for it a second time. The endpoint existed and the Tools
   *  screen had been using it all along. */
  const show = async (toolId: string) => {
    // Already on screen: this is the hide half of the same button. It was
    // one-way, so a report could be opened and never put away, and reading
    // four briefs meant scrolling past four full reports to reach the fifth.
    if (openReports.has(toolId)) {
      toggleReport(toolId, false);
      return;
    }
    if (results[toolId]) {          // cached from earlier — no refetch
      toggleReport(toolId, true);
      return;
    }
    setBusy(toolId);
    try {
      const got = await api.get<Envelope>(`/api/runs/${runId}/expert/${toolId}`);
      setResults((r) => ({ ...r, [toolId]: got }));
      toggleReport(toolId, true);
    } catch {
      /* stored but unreadable: leave it unset and let them run it again */
    } finally {
      setBusy(null);
    }
  };

  const run = async (toolId: string) => {
    setBusy(toolId);
    setError(null);
    try {
      const resp = await ask(toolId);
      setResults((r) => ({ ...r, [toolId]: resp }));
      toggleReport(toolId, true);
      reloadStored();
      if (resp.status === "needs_input") setOpenInputs(toolId);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  /** Run the same brief on its configured tier and on the deep model, so the
   *  tier choice is settled by reading both rather than by assumption. The
   *  two calls differ only by model — same evidence, same inputs. */
  const compare = async (toolId: string) => {
    const deep = meta[toolId]?.tier === "deep";
    if (deep) {
      setError(`${toolId} already runs on the deep model — there is nothing to compare it against here.`);
      return;
    }
    setBusy(toolId);
    setError(null);
    try {
      const [configured, deepRun] = await Promise.all([
        ask(toolId), ask(toolId, deepModel),
      ]);
      setResults((r) => ({ ...r, [toolId]: configured, [`${toolId}::deep`]: deepRun }));
      toggleReport(toolId, true);
      if (configured.status === "needs_input") setOpenInputs(toolId);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  const ran = tools.filter((t) => stored[t.id]);
  const notRun = tools.filter((t) => !stored[t.id]);
  const priceOf = (t: typeof tools[number]) => t.typicalCost ?? null;
  const outstanding = notRun.reduce((sum, t) => sum + (priceOf(t) ?? 0), 0);
  const unpriced = notRun.filter((t) => priceOf(t) == null).length;

  /** Every brief in this phase that has not run yet, one after another.
   *  Sequential rather than parallel: these cost money, and a queue you can
   *  stop is worth more than finishing a few seconds sooner. */
  const runRest = async () => {
    setStopped(false);
    for (const t of notRun) {
      if (stoppedRef.current) break;
      setBusy(t.id);
      try {
        const resp = await ask(t.id);
        setResults((r) => ({ ...r, [t.id]: resp }));
      } catch (e) {
        setError((e as ApiError).message);
        break;
      }
    }
    setBusy(null);
    reloadStored();
  };

  return (
    <Card>
      <h3>{heading}</h3>
      <p className="muted">
        {blurb ?? "Specialist analyses run against this audit's stored crawl "
                  + "evidence. Each returns its own report format. Values the "
                  + "evidence cannot support come back marked, never invented."}
      </p>
      {/* CQ-198. Once for the panel, covering both prices each row paints -
          the one beside `Run` and the one beside `re-run`. Read from the
          payload rather than from `siteId` above: this panel always asks for
          a site, so its own id could never report that the answer came back
          install-wide, which is the case the operator cannot infer. */}
      {priceScope && <PriceScopeNote scopedToSite={priceScope.scoped_to_site} />}

      {/* The state of play, before the buttons. These are launchers, not
          results, and nothing said so: a brief that had never run looked
          exactly like one that had, because the only difference was the word
          "re-run" on a pill. */}
      {loaded && (
        <p className="brief-state">
          {ran.length === 0 ? (
            <>
              <strong>
                {tools.length === 1
                  ? "This analysis has not run against this audit."
                  : `None of these ${tools.length} have run against this audit.`}
              </strong>{" "}
              <span className="muted">
                Each button below starts one and spends tokens; nothing here
                has run itself.
              </span>
            </>
          ) : (
            <>
              <strong>{ran.length} of {tools.length} have run against this
              audit.</strong>{" "}
              <span className="muted">
                {ran.map((t) => t.name).join(", ")} — most recent{" "}
                {ran.map((t) => stored[t.id].created_at).sort().slice(-1)[0]
                  ?.slice(0, 10)}.
                {notRun.length > 0 && ` Not yet run: ${notRun.map((t) => t.name)
                  .join(", ")}.`}
              </span>
            </>
          )}
          {notRun.length > 0 && (
            <>
              {" "}
              {/* UX-66. Stable caption, state on `aria-busy`, words in the
                  region below the tool list — the convention
                  `views.tsx`'s `ReportView` states in full. */}
              {/* Item 178: priced on the control and confirmed, naming what runs. */}
              <SpendButton busy={busy !== null}
                           price={!metaRead ? undefined : outstanding > 0 ? outstanding : null}
                           confirm={{ title: `Run ${notRun.length === 1 ? notRun[0].name
                                        : `${notRun.length} analyses`} against this audit?`,
                                      body: <><SpendTarget runId={runId} />
                                        <p>One after another, stoppable after each:{" "}
                                          {notRun.map((t) => t.name).join(", ")}.</p>
                                        {unpriced > 0 && outstanding > 0 && (
                                          <p>{unpriced} of them {unpriced === 1 ? "has" : "have"} never
                                            run here and {unpriced === 1 ? "is" : "are"} not in the price.</p>
                                        )}</>,
                                      action: notRun.length === 1 ? `Run ${notRun[0].name}` : `Run ${notRun.length}` }}
                           onSpend={runRest}>
                {notRun.length === 1
                  ? `run ${notRun[0].name}`
                  : ran.length === 0
                    ? `run all ${notRun.length}`
                    : `run the remaining ${notRun.length}`}
              </SpendButton>
              {busy && (
                <SecondaryButton onClick={() => setStopped(true)}>
                  stop after this one
                </SecondaryButton>
              )}
              {/* Only worth saying when there IS a figure to qualify. With
                  nothing priced yet it just restated the line above it. */}
              {unpriced > 0 && outstanding > 0 && (
                <span className="muted">
                  {" "}({unpriced} of them {unpriced === 1 ? "has" : "have"}{" "}
                  never run here, so {unpriced === 1 ? "it is" : "they are"} not
                  in that figure)
                </span>
              )}
              {outstanding === 0 && (
                <span className="muted">
                  {" "}· no price yet — none of these has run here before, so
                  there is nothing measured to estimate from
                </span>
              )}
            </>
          )}
        </p>
      )}
      {error && <ErrorNote error={error} />}
      <div className="filters">
        {tools.map((t) => (
          <span key={t.id}>
            {/* Item 178: one control, one job. With nothing stored this spends,
                so it is the spend control, priced and confirmed; with a report
                stored it only shows it, so it is navigation. */}
            {!stored[t.id] ? (
              <SpendButton busy={busy === t.id} why={busy !== null && busy !== t.id ? "another analysis is running" : null}
                           price={!metaRead ? undefined : t.typicalCost ?? null}
                           confirm={{ title: `Run ${t.name} against this audit?`,
                                      body: <><SpendTarget runId={runId} />
                                        <p>{t.blurb}</p>
                                        <p className="muted">{TIER_NOTE[t.tier ?? "standard"]}.</p></>,
                                      action: `Run ${t.name}` }}
                           onSpend={() => run(t.id)}>
                {t.name}{t.tier === "fast" ? " ·fast" : t.tier === "deep" ? " ·deep" : ""}
              </SpendButton>
            ) : (
            <SecondaryButton
                    title={`${t.blurb}\n\n${TIER_NOTE[t.tier ?? "standard"]}`}
                    disabled={busy !== null}
                    /* A disclosure once the report exists, so its state is
                       announced rather than only visible. */
                    aria-expanded={openReports.has(t.id)}
                    aria-busy={busy === t.id}
                    onClick={() => show(t.id)}>
              {/* UX-66. The caption keeps the tool's own name through the
                  press; `aria-busy` carries the state and the region below
                  the list says it in words, once, for whichever of these
                  identically-shaped controls is running. */}
              {openReports.has(t.id) ? `hide ${t.name}`
                : stored[t.id] ? `show ${t.name}` : t.name}
              {t.tier === "fast" ? " ·fast" : t.tier === "deep" ? " ·deep" : ""}
              {/* Ran-or-not in a mark of its own. "re-run" alone carried the
                  whole distinction and read as part of the name. */}
              {stored[t.id] && (
                <span className="brief-ran"
                      title={`Ran ${stored[t.id].created_at.slice(0, 10)} — `
                             + `${stored[t.id].findings} finding${stored[t.id].findings === 1 ? "" : "s"}`}>
                  ✓ {stored[t.id].created_at.slice(0, 10)}
                </span>
              )}
            </SecondaryButton>
            )}
            {/* Price beside the control that spends, not inside it — F-10.
                Showing a stored report costs nothing and carries neither. */}
            {!stored[t.id] && (
              <span className="cost-tag">
                {priceHint(t)}
                {/* Beside the price and not inside `priceHint`, because that
                    string also feeds the two `title=` attributes above and a
                    limitation that appears only in a tooltip is the breach the
                    provenance invariant's extended clause names. UX-74. */}
                {t.typicalCost != null && <> <BriefPriceFrame
                    costed={t.runsCosted} sampled={t.runsSampled} /></>}
              </span>
            )}
            {/* Re-running is now its own button rather than the same one that
                opens the report, so paying for a second run is a decision
                rather than the consequence of clicking to read the first. */}
            {stored[t.id] && (
              <>
                <SpendButton busy={busy === t.id} why={busy !== null && busy !== t.id ? "another analysis is running" : null}
                             price={!metaRead ? undefined : t.typicalCost ?? null}
                             confirm={{ title: `Run ${t.name} again?`,
                                        body: <><SpendTarget runId={runId} />
                                          <p>It replaces the report stored from{" "}
                                            {stored[t.id].created_at.slice(0, 10)}.</p></>,
                                        action: `Re-run ${t.name}` }}
                             onSpend={() => run(t.id)}>
                  re-run
                </SpendButton>
                <span className="cost-tag">
                  {priceHint(t)}
                  {t.typicalCost != null && <> <BriefPriceFrame
                      costed={t.runsCosted} sampled={t.runsSampled} /></>}
                </span>
              </>
            )}
            {!!t.inputs?.length && (
              <SecondaryButton
                      title={`Supply context this analysis cannot derive from a crawl`}
                      onClick={() => setOpenInputs(openInputs === t.id ? null : t.id)}>
                {openInputs === t.id ? "hide inputs" : "inputs"}
                {t.inputs.some((i) => i.required) ? " *" : ""}
              </SecondaryButton>
            )}
            {t.tier !== "deep" && deepModel && (
              <SpendButton busy={busy === t.id} why={busy !== null && busy !== t.id ? "another analysis is running" : null}
                           price={!metaRead ? undefined : null}
                           confirm={{ title: `Run ${t.name} twice, to compare with the deep model?`,
                                      body: <><SpendTarget runId={runId} />
                                        <p>It runs this analysis on its configured tier and again
                                          on {deepModel}, over the same evidence, and shows both.
                                          It costs two runs.</p></>,
                                      action: "Run both" }}
                           onSpend={() => compare(t.id)}>
                vs deep
              </SpendButton>
            )}
          </span>
        ))}
      </div>
      {/* UX-66. One region for every control above — the tool list and the
          "run the remaining" button all key on the same `busy`, and at most
          one tool runs at a time. Mounted unconditionally and empty while
          idle: a region inserted in the same render as its text gives
          assistive technology nothing to observe a change against. */}
      <div className="muted" role="status" aria-live="polite">
        {busy && <Working key={busy}>{`${stored[busy] ? "Opening" : "Analysing"} `
          + `${tools.find((t) => t.id === busy)?.name ?? busy}…`}</Working>}
      </div>

      {tools.filter((t) => t.id === openInputs && t.inputs?.length).map((t) => (
        <div key={t.id} className="expert-inputs">
          <h4>{t.name} — context the crawl cannot derive</h4>
          <p className="muted">
            Optional unless marked required. Anything left blank is passed to
            the analysis as not supplied, and it will say so rather than guess.
          </p>
          {t.inputs!.map((input) => (
            <div key={input.key} className="advice-field">
              <label className="muted advice-label">
                {input.label}{input.required ? " (required)" : ""}
                {input.hint ? ` — ${input.hint}` : ""}
              </label>
              {input.multiline ? (
                <textarea rows={4} style={{ width: "100%" }}
                          value={values[t.id]?.[input.key] ?? ""}
                          onChange={(e) => setValue(t.id, input.key, e.target.value)} />
              ) : (
                <input style={{ width: "100%" }}
                       value={values[t.id]?.[input.key] ?? ""}
                       onChange={(e) => setValue(t.id, input.key, e.target.value)} />
              )}
            </div>
          ))}
        </div>
      ))}

      {tools.map((t) => {
        const result = results[t.id];
        const rival = results[`${t.id}::deep`];
        if (!result || !openReports.has(t.id)) return null;
        if (result.status === "not_applicable") {
          // A correct outcome must not be painted as an error. `ErrorNote`
          // carries `role="alert"`, so rendering this through it would also
          // announce a decision the product made properly as a failure.
          return (
            <p key={t.id} className="muted" style={{ whiteSpace: "pre-wrap" }}>
              {t.name}: {result.reason}
            </p>
          );
        }
        if (result.status !== "ok" || !result.report) {
          return (
            <ErrorNote key={t.id}
                       error={`${t.name}: ${result.reason ?? "no report produced"}`} />
          );
        }
        if (rival?.status === "ok" && rival.report) {
          return (
            <div key={t.id}>
              <h4>{t.name} — configured tier against the deep model</h4>
              <p className="muted">
                Same evidence, same inputs, same analysis. Only the model differs,
                so any difference below is the model's.{" "}
                {compareNote(result, rival)}
              </p>
              <div className="compare-grid">
                <Report title="Configured tier" result={result} runId={runId} />
                <Report title="Deep model" result={rival} runId={runId} />
              </div>
            </div>
          );
        }
        return <Report key={t.id} title={t.name} result={result} runId={runId} />;
      })}
    </Card>
  );
}

/** One line summarising what the extra spend bought, in the terms that
 *  actually vary: price, length and how many pages were named. Length is not
 *  quality — a shorter report reaching the same verdict is a better report —
 *  so this states the differences and draws no conclusion from them. */
function compareNote(a: Envelope, b: Envelope): string {
  const parts: string[] = [];
  if (a.cost != null && b.cost != null && a.cost > 0) {
    parts.push(`the deep model cost ${(b.cost / a.cost).toFixed(1)}× as much`);
  } else if (a.tokens && b.tokens) {
    parts.push(`the deep model used ${(b.tokens / a.tokens).toFixed(1)}× the tokens`);
  }
  const [wa, wb] = [words(a.report), words(b.report)];
  if (wa && wb) parts.push(`wrote ${wb.toLocaleString()} words against ${wa.toLocaleString()}`);
  const urls = (e: Envelope) =>
    new Set((e.findings ?? []).flatMap((f) => f.affected_urls ?? [])).size;
  if (urls(a) || urls(b)) parts.push(`named ${urls(b)} pages against ${urls(a)}`);
  return parts.length ? `Here, ${parts.join(", ")}.` : "";
}

/** The brief's own statement of what it could not verify: the derived figures
 *  it flagged, and how many of them are on screen.
 *
 *  UX-03. This lived inline in `Report` below, which `ExpertPanel` mounts at
 *  exactly one place — `views.tsx`'s `RunDetailView`, the run-page route. The two screens
 *  an operator actually reads a stored brief on open `ReportView` alone
 *  (`catalogue.tsx`'s drawer, `analyses.tsx`'s `AnalysisList`), so the count of figures the brief could not
 *  ground was absent from both. The server was already serving it: the
 *  `GET /api/runs/{run}/expert/{tool}` handler returns `figures_to_verify`,
 *  `figures_withheld` and `figures_flagged` (`runs.py`, `expert_report`), and the two
 *  read sites typed the response `{ report?: string }` and dropped all three.
 *  So this is one owner and three call sites, not a new capability — no new
 *  data, no new endpoint, no prompt change.
 *
 *  Left as a component taking the two fields rather than a whole `Envelope`,
 *  because the analyses lane holds the response shape and not an `Envelope`,
 *  and widening that type to satisfy a presentation import is how the two
 *  screens would come to disagree again. */
export function DerivedFigures({ figures, flagged }:
    { figures?: Figure[]; flagged?: number | null }) {
  // Bound once. The three readers below — the block's gate, the list itself,
  // and the sentence stating how much of it is on screen — narrowed this
  // optional independently, which is how the gate and the sentence came to
  // disagree about whether there was anything to say.
  const shown = figures ?? [];
  // Either a list to spot-check or a total to account for. The gate used to
  // be the list alone, and the sentence below sits inside this block — so the
  // one case where the whole list is gone said nothing at all. Read at the
  // running product on 23 August 2026: `js-rendering` on run `1d85ff71…`
  // serves nine flagged figures of which today's rule re-derives none, and
  // Playwright painted zero `.figures-withheld` elements on that panel.
  // Silence there is UX-79 one layer out — the operator whose spot-check list
  // lost every value gets no list and no reason.
  if (!shown.length && !((flagged ?? 0) > 0)) return null;
  return (
    <div className="figures-note">
      <strong>Derived figures</strong> — computed by the analyst rather than
      quoted verbatim from the crawl evidence. Reasonable in a report, worth
      a spot-check before quoting to a client.
      <ul>
        {shown.map((f, n) => {
          const value = typeof f === "string" ? f : f.value;
          const context = typeof f === "string" ? "" : f.context;
          return (
            <li key={n}>
              <code>{value}</code>
              {context ? <span className="muted"> — “{context}”</span> : null}
            </li>
          );
        })}
      </ul>
      {/* The cap is deliberate — this is a list a person reads, not a log —
          but silence about it made the list above read as "all of them".
          Both numbers are the server's, and neither is a copy of
          FIGURES_TO_VERIFY_CAP, because a second copy of that constant would
          drift from it.

          UX-79: this used to read "Showing the first N. M more…", with N the
          rendered list's length and M `figures_withheld`. The two are
          computed under different rules — N by today's judgement when a
          stored brief is recalled, M by the day's when it ran — so they did
          not sum to what the brief flagged, and after the re-judge N is a
          filtered subset rather than a prefix, which is what made "the first"
          false as well. `figures_flagged` is the one number they were both
          drawn from, so the sentence states a subset of a stated total and
          asserts no arithmetic the server did not do. */}
      {flagged != null && flagged > shown.length && (
        <p className="muted figures-withheld">
          Showing <strong>{shown.length} of the {flagged}</strong> derived{" "}
          {flagged === 1 ? "figure" : "figures"} this analysis flagged —
          spot-check the analysis itself before quoting figures from it.
        </p>
      )}
    </div>
  );
}

export function Report({ title, result, runId }:
    { title: string; result: Envelope; runId?: string }) {
  return (
    <section className="expert-report">
      <h4>
        {title}{" "}
        <span className="muted">
          {result.model}
          {result.tier ? ` (${result.tier} tier)` : ""}
          {result.tokens ? ` · ${result.tokens.toLocaleString()} tokens` : " · cached"}
          {result.cost != null ? ` · ${money(result.cost)}` : ""}
        </span>
      </h4>
      {result.truncated && (
        <ErrorNote error="This report was cut off by the output budget — treat the tail as incomplete." />
      )}
      {!!result.findings?.length && (
        <table className="md-table findings-index">
          <thead>
            <tr><th>Severity</th><th>Issue</th><th>Summary</th><th>Pages</th></tr>
          </thead>
          <tbody>
            {result.findings.map((f, n) => (
              <tr key={n}>
                <td><Pill tone={`sev-${f.severity}` as Tone}>{f.severity}</Pill></td>
                <td><code>{f.code}</code></td>
                <td>{f.summary}</td>
                <td>
                  {f.affected_urls?.length
                    ? f.affected_urls.map((u, k) => (
                        <a key={k} href={u} target="_blank" rel="noreferrer noopener"
                           className="url-chip">{u.replace(/^https?:\/\/[^/]+/, "") || "/"}</a>
                      ))
                    : <span className="muted">not URL-specific</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {/* Either a list to spot-check or a total to account for. The gate used
          to be the list alone, and the sentence below sits inside this block —
          so the one case where the whole list is gone said nothing at all.
          Read at the running product on 23 August 2026: `js-rendering` on run
          `1d85ff71…` serves nine flagged figures of which today's rule
          re-derives none, and Playwright painted zero `.figures-withheld`
          elements on that panel. Silence there is UX-79 one layer out — the
          operator whose spot-check list lost every value gets no list and no
          reason. Recorded rather than left to be rediscovered by whoever next
          measures this panel against the corpus. */}
      <DerivedFigures figures={result.figures_to_verify}
                      flagged={result.figures_flagged} />
      <ContractAccount contract={result.contract} />
      {/* `runId` is what makes an unresolved question in the prose runnable
          (F-05); ReportView owns the wrap. Without a run there is nothing to
          record an answer against, so the markers render inert — the state
          they were in before this existed. */}
      <ReportView source={result.report!} runId={runId} />
    </section>
  );
}

// Phase 1 — crawl and indexability.
export const SITE_EXPERTS: ExpertSpec[] = [
  { id: "crawl", name: "Crawl & sitemaps",
    blurb: "robots and AI-crawler rules, sitemap validity/coverage/regression, reachability, render parity",
    inputs: [{ key: "PLATFORM", label: "Platform / CMS", hint: "e.g. WordPress + Rank Math" },
             { key: "FRAMEWORK", label: "Front-end framework", hint: "e.g. Next.js (App Router), or 'server-rendered'" },
             { key: "CDN_OR_WAF", label: "CDN / WAF", hint: "e.g. Cloudflare — needed before ua-server-refusal can be judged" },
             { key: "RENDER_CONSTRAINTS", label: "Render constraints", multiline: true,
               hint: "e.g. 'cannot change framework', 'CDN only'" }] },
  { id: "indexability", name: "Indexability",
    blurb: "noindex vs inlinks, canonical targets, chains, conflicting signals",
    inputs: [
      { key: "PLATFORM", label: "Platform / CMS", hint: "e.g. WordPress + Rank Math" },
      { key: "CANONICAL_CONVENTION", label: "Canonical convention",
        hint: "protocol, www, trailing slash, parameter policy" },
      { key: "INTENDED_NOINDEX_PATTERNS", label: "Intentionally noindexed",
        multiline: true }] },
  { id: "urls", name: "URLs & parameters",
    blurb: "URL shape and case, the pattern table, and each parameter classified against the site's rules and Indexability's canonicals",
    inputs: [] },
  { id: "freshness", name: "Freshness & decay", tier: "deep",
    blurb: "what has gone stale and what to do about it, from three date signals "
      + "that disagree. Decay itself needs Search Console",
    inputs: [
      { key: "PERFORMANCE_DATA", label: "Traffic or ranking data", multiline: true,
        hint: "Search Console or analytics per URL. Without it decay cannot be "
          + "observed, only staleness" },
      { key: "CURRENT_WINDOW", label: "Current period" },
      { key: "COMPARISON_WINDOW", label: "Comparison period" },
      { key: "BUSINESS_GOALS", label: "Business goals", multiline: true },
      { key: "CMS", label: "CMS" },
      { key: "RESOURCE_CAPACITY", label: "Capacity to act",
        hint: "how many pages can realistically be refreshed" },
      { key: "EXCLUSIONS", label: "Pages to leave alone", multiline: true },
      { key: "TOP_N", label: "How many to rank", hint: "defaults to 20" }] },
  { id: "content-gap", name: "Content gap", tier: "deep",
    blurb: "topics the site does not cover. Without keyword data these are "
      + "inferred coverage gaps, never demonstrated demand",
    inputs: [
      { key: "KEYWORD_DATA", label: "Keyword data", multiline: true,
        hint: "volume and difficulty — without it no gap can carry a traffic estimate" },
      { key: "KEYWORD_TOOL", label: "Keyword tool used" },
      { key: "GSC_DATA", label: "Search Console export", multiline: true,
        hint: "reveals near-miss rankings worth strengthening" },
      { key: "COMPETITORS", label: "Competitors", multiline: true },
      { key: "AUDIENCE", label: "Audience" },
      { key: "MARKET", label: "Market" },
      { key: "TOPIC_OR_KEYWORD_SEED", label: "Topic seed" },
      { key: "WHAT_THE_SITE_SELLS_OR_DOES", label: "What the site sells or does",
        multiline: true },
      { key: "PRIORITY_SERVICES_OR_PRODUCTS", label: "Priority services or products",
        multiline: true },
      { key: "BUDGET_TEAM_CMS_OR_PUBLISHING_LIMITS", label: "Publishing constraints",
        multiline: true },
      { key: "N_BRIEFS", label: "How many content briefs to outline", hint: "defaults to 5" }] },
];

// Phase 8 — local. Three of these four audit things a crawl cannot see, so
// they work from what you paste and say plainly what they could not check.
export const LOCAL_EXPERTS: ExpertSpec[] = [
  { id: "local-signals", name: "Local signals", tier: "deep",
    blurb: "on-site NAP, LocalBusiness schema, opening hours and location page "
      + "substance — every finding with verbatim before and drop-in after",
    inputs: [
      { key: "BUSINESS_NAME", label: "Canonical business name",
        hint: "the name of record; every on-site variant is measured against it" },
      { key: "ADDRESS", label: "Canonical address" },
      { key: "PHONE", label: "Canonical phone" },
      { key: "BUSINESS_TYPE", label: "Business type" },
      { key: "TARGET_LOCATIONS", label: "Target locations", multiline: true },
      { key: "OPENING_HOURS", label: "Opening hours of record", multiline: true },
      { key: "PLATFORM", label: "Platform / CMS" },
      { key: "LOCALE", label: "Market / locale", hint: "defaults to Australia, en-AU" }] },
  { id: "gbp-audit", name: "Business Profile audit",
    blurb: "categories, hours, description, services, attributes, posts, photos, "
      + "Q&A. Reads only what you paste — it cannot query the live profile",
    inputs: [
      { key: "PLACE_QUERY", label: "Google listing search",
        hint: "how to find the Business Profile if the bare domain does not match it" },
      { key: "LISTED_NAME", label: "Business name as listed" },
      { key: "PRIMARY_CATEGORY", label: "Primary category" },
      { key: "SECONDARY_CATEGORIES", label: "Secondary categories" },
      { key: "STOREFRONT", label: "Location model",
        hint: "storefront, service area, hybrid or multi-location" },
      { key: "TARGET_LOCATIONS", label: "Service areas targeted", multiline: true },
      { key: "NAP_DETAILS", label: "NAP as listed on the profile", multiline: true,
        hint: "the profile's version, not the site's — the comparison is the point" },
      { key: "HOURS", label: "Hours, including special hours", multiline: true },
      { key: "DESCRIPTION", label: "Business description", multiline: true },
      { key: "SERVICES_LIST", label: "Services or products listed", multiline: true },
      { key: "ATTRIBUTES", label: "Attributes ticked", multiline: true },
      { key: "POSTS_DATA", label: "Posts", multiline: true,
        hint: "frequency, most recent date, types used" },
      { key: "PHOTOS_DATA", label: "Photos", multiline: true,
        hint: "counts by type, owner vs customer, most recent" },
      { key: "QA_DATA", label: "Q&A", multiline: true },
      { key: "REVIEWS_DATA", label: "Reviews", multiline: true,
        hint: "count, average, response rate, recency" },
      { key: "COMPETITORS", label: "Local pack competitors", multiline: true }] },
  { id: "citations-nap", name: "Citations & NAP",
    blurb: "directory consistency against a canonical record. Without listing "
      + "data it builds the framework and marks every finding [TO CONFIRM]",
    inputs: [
      { key: "PLACE_QUERY", label: "Google listing search",
        hint: "how to find the Business Profile if the bare domain does not match it" },
      { key: "CANONICAL_NAME", label: "Canonical business name",
        hint: "exact legal or trading name of record" },
      { key: "CANONICAL_ADDRESS", label: "Canonical address" },
      { key: "CANONICAL_PHONE", label: "Canonical phone" },
      { key: "PRIMARY_CATEGORY", label: "Primary category" },
      { key: "SECONDARY_CATEGORIES", label: "Secondary categories" },
      { key: "SINGLE_LOCATION", label: "Location model",
        hint: "single location, multi-location or service area" },
      { key: "SERVICE_AREAS", label: "Service areas", multiline: true },
      { key: "INDUSTRY", label: "Industry / vertical" },
      { key: "HISTORICAL_NAP_VARIANTS", label: "Former names, addresses or phones",
        multiline: true, hint: "the usual source of stale citations" },
      { key: "LISTING_DATA", label: "Listing data or export", multiline: true,
        hint: "without it the analysis builds the framework and marks findings [TO CONFIRM]" },
      { key: "AUDIT_SOURCE", label: "Tool used to gather it",
        hint: "BrightLocal, Whitespark, Semrush, manual" },
      { key: "CLAIMED_LISTINGS", label: "Directories already claimed", multiline: true },
      { key: "COMPETITORS", label: "Competitors for gap comparison", multiline: true }] },
  { id: "review-signals", name: "Review signals", tier: "deep",
    blurb: "velocity, distribution, response rate, sentiment, and whether review "
      + "markup is permitted for this entity at all",
    inputs: [
      { key: "PLACE_QUERY", label: "Google listing search",
        hint: "how to find the Business Profile if the bare domain does not match it" },
      { key: "REVIEW_EXPORT", label: "Review export", multiline: true,
        hint: "platform, date, rating, text, reviewer, owner response and date" },
      { key: "BUSINESS_NAME", label: "Business name" },
      { key: "PLATFORMS", label: "Platforms covered" },
      { key: "PERIOD", label: "Period covered" },
      { key: "BENCHMARKS", label: "Competitor or category norms", multiline: true },
      { key: "BUSINESS_CONTEXT", label: "Business context", multiline: true,
        hint: "sector, locations, seasonality, review-request process" },
      { key: "PRIMARY_GOAL", label: "Primary goal",
        hint: "defaults to overall signal health" }] },
];

// Phase 2 — technical foundation.
export const FOUNDATION_EXPERTS: ExpertSpec[] = [
  { id: "security", name: "Security & transport",
    blurb: "nine domains A-I; compromise triage first, CSP from observed origins, config with rollback",
    inputs: [
      { key: "STACK", label: "Server and CDN stack", hint: "e.g. Nginx behind Cloudflare" },
      { key: "SITE_TYPE", label: "Site type", hint: "brochure, ecommerce, SaaS, portal" },
      { key: "THIRD_PARTY_MAP", label: "Third parties", multiline: true,
        hint: "host -> what it is -> purpose; tells known scripts from unexplained" }] },
  { id: "mobile-viewport", name: "Mobile viewport", tier: "fast",
    blurb: "viewport correctness per page, zoom suppression as a WCAG failure",
    inputs: [
      { key: "PLATFORM", label: "Platform / builder",
        hint: "needed for platform-specific remediation" },
      { key: "KNOWN_CONSTRAINTS", label: "Known constraints", multiline: true }] },
  { id: "site-architecture", name: "Architecture & internal links",
    blurb: "click depth, orphans, graph shape, hub-and-spoke, anchor distribution",
    inputs: [
      { key: "TOPIC_CLUSTERS", label: "Topic clusters", multiline: true,
        hint: "intended hub pages and their spokes" },
      { key: "PRIORITY_URLS", label: "Priority URLs", multiline: true },
      { key: "SITE_TYPE", label: "Site type" },
      { key: "PLATFORM", label: "Platform / CMS" },
      { key: "TECHNICAL_CONSTRAINTS", label: "Constraints on changes", multiline: true,
        hint: "e.g. template-only edits, no nav changes" }] },
  { id: "hreflang", name: "Hreflang & i18n",
    blurb: "reciprocity, x-default, canonical alignment, one method only",
    inputs: [
      { key: "TARGET_LOCALES", label: "Target locales", hint: "e.g. en-AU, en-GB, de-DE" },
      { key: "ARCHITECTURE", label: "Domain architecture",
        hint: "ccTLD, subdomain, subfolder or parameter" },
      { key: "IMPLEMENTATION_METHOD", label: "Implementation method",
        hint: "HTML head, HTTP header or XML sitemap" },
      { key: "PLATFORM", label: "Platform / CMS" },
      { key: "REPORTED_ISSUES", label: "Reported symptoms", multiline: true }] },
  { id: "migration-redirects", name: "Migration & redirects",
    blurb: "validates a redirect map you supply; chains, loops, equity preservation",
    inputs: [
      { key: "REDIRECT_MAP", label: "Redirect map", multiline: true, required: true,
        hint: "source URL, destination URL, status code" },
      { key: "MIGRATION_TYPE", label: "Migration type",
        hint: "replatform, IA restructure, domain consolidation, HTTPS/www" },
      { key: "LEGACY_DOMAIN_OR_STRUCTURE", label: "Legacy domain or structure" },
      { key: "LEGACY_URL_INVENTORY", label: "Legacy URL inventory", multiline: true },
      { key: "PLATFORM_AND_MECHANISM", label: "Redirect mechanism",
        hint: "e.g. Nginx, .htaccess, Cloudflare Rules" },
      { key: "PERFORMANCE_DATA", label: "Performance data per legacy URL",
        multiline: true },
      { key: "CLIENT_CONSTRAINTS", label: "Client constraints", multiline: true }] },
];


