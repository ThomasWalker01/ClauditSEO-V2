/**
 * Every brief ever produced for a site, and what it cost.
 *
 * The deliverables were reachable one run at a time: open a run, click each
 * brief, go back. Nothing answered "what have we produced for this client"
 * or "what did we spend on it" — the two questions asked before a renewal
 * conversation, and the two the data could always have answered. One site
 * here held 30 reports across 7 runs and 894,806 tokens, none of it visible
 * on any screen.
 *
 * Flat and newest-first rather than nested under runs, because the useful
 * comparison is one brief against its own history — did crawl health say
 * this last month too — and grouping by run hides exactly that. Filtering by
 * brief turns the same table into that history.
 */
import { Working } from "./working";
import { LinkButton, PrimaryButton, SecondaryButton } from "./buttons";
import { useEffect, useState } from "react";
// `effective_scope` is read straight off the row rather than through
// `scopeOf`: the server stamps it (brief v6 step V2) and this payload carries
// neither `scan_scope` nor `crawled_paths`, which is the fallback `scopeOf`
// exists for. It carried nothing at all until 2026-09-18.
import { RunStatus, api, scoreExtent, useFetch } from "./api";
import { Card, ErrorNote, Loading, NarrowRunNote, RunScore, ScoreBandKey,
         SpendMark, Stat, Stats, money } from "./components";
import { useSelection } from "./selection";
import { goHandler } from "./nav";
import { ReportHeld, useReportHold } from "./report_hold";
import { SpendButton, SpendTarget } from "./spend";
import { Pill, type Tone } from "./pill";

type Report = {
  run_id: string; tool: string; model: string | null;
  page_url: string | null; tokens: number | null; cost: number | null;
  truncated: boolean; created_at: string;
  run_started_at: string; run_tier: string; run_score: number | null;
  /** The status that decides whether `run_score` may be printed at all. A
   *  blocked run's composite is built from robots.txt and the sitemap with no
   *  page fetched; printed beside a complete run's it reads as the same kind
   *  of measurement. */
  run_status: RunStatus;
  /** And what the run was sent to look at. Two questions, not one: the
   *  status says a score was produced, the kind says whether it describes
   *  the site. An eight-page verification is `complete`, so `hasScore` alone
   *  printed its 86.2 in the same column as a 224-page audit's 70.52. */
  run_kind: string;
  /** And what it read. `run_kind` says a verification is not an audit;
   *  `run_scope` says a one-page audit is not the site, and the "Ran against"
   *  column prints the run's composite. */
  run_scope?: string | null;
  /** Completed audits that have run since the one this analysis read. 0 is
   *  current; anything else means the site has moved underneath it. */
  audits_since: number | null;
  is_latest: boolean;
  findings: number; worst_severity: string | null;
};

type RunRow = {
  id: string; started_at: string; tier: string;
  score: number | null; status: RunStatus; reports: number;
  /** Every kind is listed — a verification is real history and hiding it
   *  would make the crawl it performed unauditable — so the row has to carry
   *  which it is rather than the server dropping it from the list. */
  kind: string;
  /** What the run was sent to look at, from the server (`scope_of`). The kind
   *  says a verification is not an audit; this says a one-page audit is not
   *  the site, and without it every `RunScore` on this screen had nothing to
   *  gate on: a page scan of 1 of 53 pages printed as "72.8 out of 100,
   *  fair". */
  effective_scope?: string | null;
  site_reading?: boolean;
};

type Payload = {
  reports: Report[];
  runs: RunRow[];
  total_cost: number | null;
  unpriced: number;
  /** Whether any model price is recorded at all. Distinguishes "nobody has
   *  set a rate" from "these ran before one existed" — the screen used to
   *  report the first when the truth was the second. */
  rate_is_set: boolean;
  /** Analyses written against an audit that is no longer the newest. */
  stale_analyses: number;
  newest_run_id: string | null;
  total_tokens: number;
  runs_with_reports: number;
};

const day = (iso: string) => (iso || "").slice(0, 10);
const tokens = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M`
  : n >= 1_000 ? `${Math.round(n / 1_000)}k` : String(n);

type Deliverable = {
  id: string; template: string; audience: string; created_at: string;
  on_disk: boolean; bytes: number | null;
  //: The audits this document was rendered from. Already on the wire —
  //: `client_reports()` has returned it since the register was written — and
  //: it is the whole of what a rewrite needs, which is why WF-07 closes on
  //: this screen alone and not at the boundary.
  run_ids: string[];
  //: Completed audits since the one this document describes. 0 is current;
  //: null means its run is no longer in the site's history.
  audits_since: number | null;
  //: "current" | "superseded" | "unknown". Unknown is its own state: see
  //: client_reports() for why it must not be read as current.
  renderer: string;
  renderer_version: string | null;
  //: The register's two halves of one fact: what this document replaced, and
  //: what replaced it. `superseded_by` is derived server-side over the site's
  //: rows rather than stored, because the column is written on the new row so
  //: a regeneration stays an insert — see `0028_report_supersedes.sql`.
  //: `QUESTIONS.md` Q-9, answered `supersede` on 23 August 2026.
  supersedes: string | null;
  superseded_by: string | null;
};

/** Client deliverables already generated for this site.
 *
 *  Both existed on disk and were recorded in the database, and nothing
 *  listed them: the client rail read "Client report ✓ 2 generated" while
 *  neither file was reachable from the app that wrote it. A deliverable you
 *  cannot open is indistinguishable from one that was never produced — and
 *  it is the artefact the whole run exists to create.
 */
/** Generate a deliverable against the audit in scope (brief v2 step G,
 *  UX-11). The rail's step 6 said "generate" and landed on a screen whose
 *  first control was a filter; this is that control, first. It posts what
 *  `ReportView` posts, for the audit the picker holds - and the comparison
 *  template for that audit against the reading before it. Generating is
 *  free (`clauditseo/reporting/generate.py` runs no model), so no spend
 *  mark; UX-66's shape for the busy state. */
function GenerateCard({ siteId, runs, onMade }: {
  siteId: string; runs: RunRow[]; onMade: () => void;
}) {
  const { runId } = useSelection();
  const [template, setTemplate] = useState("run");
  const [audience, setAudience] = useState("client");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<string | null>(null);
  //: Which of the two calls is in flight, and what the plan said if it
  //: refused. Separate from `error`, which is the one that stopped the
  //: document: a plan that could not be written is a caveat on a document
  //: that exists, not a failure to make one.
  const [stage, setStage] = useState("");
  const [planNote, setPlanNote] = useState<string | null>(null);
  // The audit in scope, or the newest reading when the picker holds none
  // of these; the comparison pairs it with the reading before it.
  const readings = runs.filter((x) => x.kind === "audit" && x.score != null);
  const at = Math.max(0, readings.findIndex((x) => x.id === runId));
  const current = readings[at];
  const previous = readings[at + 1];
  const target = current?.id ?? runId;
  const ids = template === "comparison" && previous ? [previous.id, target] : [target];
  // The run report carries the client plan, so generating one runs the
  // plan brief first, at the model Admin has set for it (brief v18 step
  // AY). Two calls rather than one server-side step, deliberately: the
  // spend is the operator's to see and to stop, and a route that quietly
  // ran a model when asked for a document would be the one control on
  // this screen whose cost was not on its face.
  //
  // `run-free` never runs it - that document is the free half by
  // definition - and neither do the comparison and trend templates, which
  // have no plan section to fill.
  const needsPlan = template === "run";
  /** Item 178 (08-2, 08-3): the hold, from the one answer every surface reads.
   *  A client document is not offered while it is held, or before the hold
   *  has been read - the landing's held button and a live Generate here could
   *  both be on screen for the same audit. */
  const { data: hold } = useReportHold(target || null);
  const holdFor = hold && hold.run_id === target ? hold : null;
  const clientHeld = audience === "client" && Boolean(target)
    && (holdFor === null || holdFor.held);
  const generate = async () => {
    setBusy(true); setError(null); setMade(null);
    try {
      if (needsPlan) {
        setStage("writing the plan…");
        // A plan that cannot be written must not stop the document: the
        // per-part sections are measured and are worth sending on their
        // own, and `_plan_section` renders the refusal in the document
        // itself. The reason is kept and shown beside the result.
        try {
          await api.post(`/api/runs/${target}/expert/plan`, { for_audience: audience });
        } catch (e) {
          // Item 178: a held client report is refused before the plan spends
          // (422), and the document would be refused for the same reason, so
          // stop here and say why rather than render and fail.
          if ((e as { status?: number }).status === 422 && audience === "client") throw e;
          setPlanNote((e as Error).message);
        }
      }
      setStage("rendering the document…");
      const resp = await api.post<{ id?: string; path?: string }>("/api/reports", {
        template, audience, run_ids: ids,
      });
      setMade(resp.id ?? resp.path ?? "made");
      onMade();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setStage("");
    }
  };
  return (
    <Card>
      <h3>Generate</h3>
      <p className="muted">
        {current
          ? <>From the audit of {day(current.started_at)} · {current.tier}
              {/* The extent beside the score, for the reason `RunScore` gates
                  on it: `· 72.77` alone read as this site's score where the
                  audit was one page of 53. Named, not withheld - the number is
                  the right one for what it measured. */}
              {current.score != null
                ? ` · ${current.score}${scoreExtent(current.effective_scope)
                    ? ` ${scoreExtent(current.effective_scope)}` : ""}`
                : ""} — the one selected on
              the <a href={`#/sites/${siteId}`} onClick={goHandler(`#/sites/${siteId}`)}>client
              screen</a>.{" "}
              {needsPlan
                ? <><SpendMark />The run report writes the client plan first,
                    at the model set for it on Admin.</>
                : "Free: no model runs."}</>
          : "Pick an audit in the header; a document is generated against one."}
      </p>
      <div className="inline-form report-gen">
        <select value={template} onChange={(e) => setTemplate(e.target.value)}
                aria-label="template">
          <option value="run">Run report</option>
          {/* Offered only where a pair exists: a comparison of one audit
              is not a document this can make, and a control that would
              fail is not offered (UX-39). */}
          {previous && (
            <option value="comparison">Comparison with {day(previous.started_at)}</option>
          )}
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
        {needsPlan && !clientHeld ? (
          // Item 178: the run report writes the plan with a model first, so
          // Generate is a spend here - priced in words and confirmed.
          <SpendButton price={null} busy={busy} why={!target ? "pick an audit first" : null}
                       confirm={{ title: "Generate the run report?",
                                  body: <><SpendTarget runId={target} />
                                    <p>It writes the client plan with a model first, at the model
                                      set for it on Admin, then renders the document for free.</p></>,
                                  action: "Write the plan and generate" }}
                       onSpend={generate}>
            Generate
          </SpendButton>
        ) : (
          <PrimaryButton onClick={clientHeld ? undefined : generate}
                disabled={busy || !target} aria-busy={busy}
                aria-disabled={clientHeld || undefined}
                aria-describedby={clientHeld ? "generate-held" : undefined}>
            Generate
          </PrimaryButton>
        )}
        {clientHeld && (holdFor
          ? <ReportHeld id="generate-held" count={holdFor.count} siteId={siteId} />
          : <span id="generate-held" className="muted">Checking whether the client report can go out…</span>)}
      </div>
      <div className="muted" role="status" aria-live="polite">
        {busy ? <Working>{stage || "Generating the document…"}</Working>
          : made ? "Generated; it is in the table below." : ""}
      </div>
      {planNote && !busy && (
        <p className="muted">
          The client plan could not be written, so the document carries the
          per-part sections only — {planNote}
        </p>
      )}
      {error && <ErrorNote error={error} />}
    </Card>
  );
}

function Deliverables({ siteId, tick = 0 }: { siteId: string; tick?: number }) {
  const [rows, setRows] = useState<Deliverable[] | null>(null);
  //: The row being rewritten, and what went wrong on the last attempt. Keyed
  //: by id rather than held as one flag, because the table is a list of
  //: independent documents and a single `busy` would grey out nine rows to
  //: report one.
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState<Record<string, string>>({});

  const load = () =>
    api.get<{ reports: Deliverable[] }>(`/api/sites/${siteId}/client-reports`)
      .then((d: { reports: Deliverable[] }) => setRows(d.reports))
      .catch(() => setRows([]));

  useEffect(() => { load(); }, [siteId, tick]);
  const [showAll, setShowAll] = useState(false);

  /** Rewrite one document with the renderer the product ships today.
   *
   *  The screen has said "regenerate before sending" since the deliverables
   *  register existed and offered `read` as the row's only verb — the
   *  affordance invariant's own first instance, and the state nine
   *  client-facing comparison documents arrived in when WF-75's adopt pass
   *  gave every orphan on disk a row.
   *
   *  A rewrite is a new document, not an edit: `POST /api/reports` stores a
   *  fresh row and a fresh file, and the old one stays listed and readable.
   *  The row it replaces is still the artefact a client was sent, and
   *  deleting it would remove the record of what they actually received.
   *
   *  **The new document records which one it replaced** — `supersedes`, the
   *  operator's answer to `QUESTIONS.md` Q-9 on 23 August 2026, against
   *  rewriting the row in place or gaining a delete route. Until then the
   *  press left the row it was pressed on completely unchanged, so the row
   *  kept its `superseded` or `unknown` renderer and kept offering this
   *  control for ever: audit WF-91 measured 14 rows offering it on the
   *  operator's own database, 11 on one site, 9 of them indistinguishable on
   *  every column this table renders. Nine presses made nine more, and
   *  nothing said which replaced which. The register still only grows; what
   *  it gained is the ability to say so.
   *
   *  No `SpendMark`: generation reaches no provider, so the control spends
   *  nothing. Marking one that does not spend is what `e979b1c` reverted.
   */
  const regenerate = async (r: Deliverable) => {
    setBusy(r.id);
    setFailed((f) => { const { [r.id]: _gone, ...rest } = f; return rest; });
    try {
      await api.post<{ id: string }>("/api/reports", {
        template: r.template, audience: r.audience, run_ids: r.run_ids,
        supersedes: r.id,
      });
      await load();
    } catch (e) {
      // Said on the row, not swallowed. The honesty gate refuses to generate
      // for some sites (KI-48) and answers 500 with what it objected to; a
      // rewrite that silently did nothing would read as one that worked.
      setFailed((f) => ({ ...f, [r.id]: (e as Error).message }));
    } finally {
      setBusy(null);
    }
  };

  if (!rows?.length) return null;
  /** Identical renders, one row (brief v2 step G, UX-11): nine rows from
   *  one day were the same comparison rendered nine times. Two rows are
   *  taken as one document when template, audience, audits, size and
   *  renderer all agree and neither replaces or is replaced by another -
   *  the register's replacement chain is never folded. The newest stands
   *  for the group and says how many it stands for; "show all" unfolds.
   *  There is no route that trashes a document, so nothing is offered
   *  that would. */
  const keyOf = (d: Deliverable) =>
    `${d.template}|${d.audience}|${[...d.run_ids].sort().join(",")}|${d.bytes ?? ""}|${d.renderer_version ?? ""}`;
  const groups = new Map<string, Deliverable[]>();
  for (const d of rows) {
    if (d.supersedes || d.superseded_by) { groups.set(d.id, [d]); continue; }
    const k = keyOf(d);
    groups.set(k, [...(groups.get(k) ?? []), d]);
  }
  const shown: { row: Deliverable; identical: number }[] = [];
  for (const members of groups.values()) {
    if (showAll || members.length === 1) {
      for (const d of members) shown.push({ row: d, identical: 0 });
    } else {
      const newest = [...members].sort((x, y) => y.created_at.localeCompare(x.created_at))[0];
      shown.push({ row: newest, identical: members.length });
    }
  }
  shown.sort((x, y) => y.row.created_at.localeCompare(x.row.created_at));
  const folded = rows.length - shown.length;
  /** The newest document of each template x audience (brief v3 step N,
   *  UI-11): the one row where `regenerate` stands inline. On every other
   *  row it sits behind the overflow - twenty-five regenerate buttons at
   *  equal weight were the easiest thing on the screen to press, and the
   *  older documents are what a client was sent, not what to send next. */
  const newestOf = new Map<string, string>();
  for (const d of [...rows].sort((x, y) => y.created_at.localeCompare(x.created_at))) {
    const k = `${d.template}|${d.audience}`;
    if (!newestOf.has(k)) newestOf.set(k, d.id);
  }
  return (
    <Card>
      <h3>Client deliverables</h3>
      <p className="muted">
        Written documents produced for this client. These are the files that
        were handed over — open one to read exactly what the client saw.
      </p>
      <table className="findings">
        <thead><tr><th>Generated</th><th>Template</th><th>For</th>
                   <th>Still current?</th><th>Size</th><th /></tr></thead>
        <tbody>
          {shown.map(({ row: r, identical }) => (
            <tr key={r.id}>
              <td>{r.created_at.slice(0, 10)}</td>
              <td>
                {r.template}
                {identical > 1 && (
                  <div className="muted dup-note">
                    {identical} identical renders — same template, audience,
                    audits, size and renderer; this is the newest
                  </div>
                )}
              </td>
              <td>{r.audience}</td>
              {/* Two ways a stored document goes out of date, and they are
                  not the same. The site can move under it — the analyses
                  table has said so for a while, and the document that
                  actually reaches the client said nothing. Or the renderer
                  can have been corrected since, which is invisible from the
                  file: six of these still read "Title duplicate on 2 pages"
                  above thirteen URLs. */}
              <td>
                {r.audits_since === null ? (
                  <span className="muted">audit no longer in history</span>
                ) : r.audits_since > 0 ? (
                  <Pill tone="state-regressed">
                    {r.audits_since} audit{r.audits_since === 1 ? "" : "s"} since
                  </Pill>
                ) : (
                  <Pill tone="state-fixed">newest audit</Pill>
                )}
                {r.renderer === "superseded" && (
                  <div className="muted">
                    written by an older report renderer ({r.renderer_version})
                  </div>
                )}
                {r.renderer === "unknown" && (
                  <div className="muted">
                    predates renderer tracking
                    {r.superseded_by ? "" : " — regenerate before sending"}
                  </div>
                )}
                {/* Q-9's answer, said on the row. Both directions are stated
                    because the register's whole job is to say which document
                    replaced which, and a reader arriving at either end of a
                    replacement should not have to scan the table for the
                    other. The instruction above drops its second clause when
                    a replacement exists — the renderer that wrote this file
                    is still unknown, which stays said, but asking for it to
                    be regenerated again is the defect WF-91 measured. */}
                {r.superseded_by && (
                  <div className="muted">
                    replaced by{" "}
                    <a href={`#/client-reports/${r.superseded_by}`}>
                      a newer document
                    </a>
                  </div>
                )}
                {r.supersedes && (
                  <div className="muted">
                    replaces{" "}
                    <a href={`#/client-reports/${r.supersedes}`}>
                      the document it was regenerated from
                    </a>
                  </div>
                )}
              </td>
              <td className="muted">
                {r.bytes ? `${Math.round(r.bytes / 1024)} kB` : "—"}
              </td>
              <td>
                {/* Recorded and present are different states. A row whose
                    file has been moved says so rather than 404 on click. */}
                {r.on_disk
                  ? <LinkButton href={`#/client-reports/${r.id}`}>
                      read
                    </LinkButton>
                  : <span className="muted">file missing</span>}
                {/* Beside the sentence that asks for it, and only there. A
                    document already at the current renderer would rewrite to
                    the same text under a new id, and a control offered where
                    it cannot usefully work is its own finding on this
                    project (UX-39). `file missing` is deliberately not a
                    trigger: a new document leaves that row as broken as it
                    was, which is a different remedy.

                    A row that has already been replaced is the same rule in
                    its third spelling, and the one WF-91 was raised for: the
                    action it names has been taken, so offering it again just
                    appends another indistinguishable document. The replaced
                    row stays listed and readable — it is what a client was
                    actually sent — and says what took its place. */}
                {r.renderer !== "current" && !r.superseded_by && (
                  newestOf.get(`${r.template}|${r.audience}`) === r.id ? (
                    <SecondaryButton
                            disabled={busy === r.id}
                            onClick={() => regenerate(r)}>
                      regenerate
                    </SecondaryButton>
                  ) : (
                    <details className="row-more">
                      <summary aria-label={`actions for the ${r.template} document of ${r.created_at.slice(0, 10)}`}>⋯</summary>
                      <SecondaryButton
                              disabled={busy === r.id}
                              onClick={() => regenerate(r)}>
                        regenerate
                      </SecondaryButton>
                    </details>
                  )
                )}
                {/* Both states of one act, in one announced region — UX-64.
                    The house pattern is `components.tsx`'s `Loading`, and this is its
                    second consumer: `role="status" aria-live="polite"`, mounted
                    with the state as `Loading` is, so the two mount the same
                    way and the convention stays one convention.

                    The busy word moved off the button label to get here. A
                    control whose name changes mid-action is announced as a
                    different control, and the label is the accessible name —
                    so the state has to be said beside it rather than in it.
                    The visible in-flight signal is unchanged in kind: the
                    control still disables, but by a measured colour rather
                    than by `opacity` (UI-16, `styles.css`). */}
                {(busy === r.id || failed[r.id]) && (
                  <div className="muted" role="status" aria-live="polite">
                    {busy === r.id
                      ? <Working>regenerating…</Working>
                      : `could not rewrite: ${failed[r.id]}`}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {(folded > 0 || showAll) && (
        <p className="muted">
          <SecondaryButton aria-pressed={showAll}
                  onClick={() => setShowAll((v) => !v)}>
            {showAll ? "fold identical renders" : `show all ${rows.length}`}
          </SecondaryButton>{" "}
          {showAll ? "Every render listed." : `${folded} identical render${folded === 1 ? "" : "s"} folded into the rows above.`}
        </p>
      )}
    </Card>
  );
}

import { Legend } from "./glossary";

export function ReportsView({ siteId }: { siteId: string }) {
  const { site } = useSelection();
  const [tool, setTool] = useState("all");
  const { data, error, loading, retry } = useFetch<Payload>(`/api/sites/${siteId}/reports`);
  const [made, setMade] = useState(0);
  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!data) return <Loading />;

  const tools = [...new Set(data.reports.map((r) => r.tool))].sort();
  const rows = tool === "all" ? data.reports
                              : data.reports.filter((r) => r.tool === tool);

  return (
    <>
      <h2 className="view-title">
        Reports{site && <span className="muted"> · {site.client}</span>}
      </h2>
      {/* Item 166: the chips a report row and its hold draw. */}
      <Legend ids={["action-primary", "sev-critical", "sev-high", "sev-medium",
                    "state-regressed", "report-held"]} />
      {/* What these are, in the reader's terms. "Brief" is the word this
          codebase uses for the operator-written prompt that casts a model as
          a named specialist — it names the instruction, not the output, so on
          a page headed Reports it reads as the wrong noun. And a table of
          names, token counts and models looks exactly like the launcher pills
          elsewhere, so it has to say outright that nothing here runs. */}
      <p className="muted view-lede">
        Written analyses a model has already produced against a stored audit.
        Each one is a specialist — crawl health, entity graph, triage — given
        that audit's crawl evidence and asked to write up what it found.
        {/* Item 178 (08-5): true of every control here. It said nothing on the
            page spends, 90 px above a Generate that writes the plan with a model. */}
        <strong> Documents render free.</strong>{" "}
        The run report writes a client plan with a model first, and says so on
        its Generate; the audit report of free checks only spends nothing. The
        analyses listed were paid for already. Open one to read it, or start a new one
        from the part it investigates on the client screen.
      </p>

      {/* Brief v2 step G: generate first, then what was handed over, then
          the analyses that fed it - folded, since step 4 lists them beside
          the part each investigates. */}
      <GenerateCard siteId={siteId} runs={data.runs} onMade={() => setMade((n) => n + 1)} />
      <Deliverables siteId={siteId} tick={made} />
      <Card>
        <Stats>
          <Stat value={data.reports.length} label="analyses written" />
          <Stat value={data.runs_with_reports} label="audits analysed"
                tone="quiet"
                title={`${data.runs.length} completed audits in total`} />
          <Stat value={tokens(data.total_tokens)} label="tokens spent"
                tone="quiet" />
          {/* Cost or its absence, never a zero standing in for "unknown" —
              and, when it is absent, the right reason. "No dollar rate set"
              was false: rates are set for sixteen models, while Home totalled
              the entries that DO carry a cost and showed $0.70. Two screens
              read as contradicting each other about money when both were
              right about their own rows. These analyses ran before any price
              was recorded, and nothing computes a cost backwards. */}
          <Stat
            value={data.total_cost != null ? money(data.total_cost) : "—"}
            label={data.total_cost != null ? "measured cost"
                   : data.rate_is_set ? "ran before pricing"
                   : "no dollar rate set"}
            tone="quiet"
            title={data.unpriced > 0
              ? `${data.unpriced} of them carry no cost, so they contribute `
                + "tokens but no dollars"
              : undefined} />
        </Stats>
        {data.total_cost == null && data.total_tokens > 0 && (
          <p className="muted home-setup">
            {data.rate_is_set
              ? "Spend is in tokens because these analyses ran before any "
                + "model price was recorded. Nothing computes a cost "
                + "backwards, so they stay in tokens; anything run from now "
                + "on carries dollars."
              : "Spend is in tokens because no dollar rate is configured. The "
                + "token figure is measured, not estimated — set rates in "
                + "Admin to see it in currency."}
          </p>
        )}
        {data.stale_analyses > 0 && (
          // The one thing here that can reach a client. An analysis
          // describes the crawl it was handed, and the site keeps moving.
          <p className="muted home-setup">
            <strong>{data.stale_analyses} of {data.reports.length}</strong>{" "}
            were written against an audit that is no longer the newest. They
            may name findings a later audit has already closed — check the
            date on a row before quoting it.
          </p>
        )}
      </Card>

      {!data.reports.length ? (
        <Card>
          <p className="muted">
            No analyses have been written for this site yet. They are started
            from an audit's own page or from the workbench, and stored against
            the audit they read.
          </p>
        </Card>
      ) : (
        <details className="analyses-all">
          <summary>
            All {data.reports.length} written analyses in one table
            {data.stale_analyses ? ` · ${data.stale_analyses} against older audits` : ""}
            {" "}— each is also listed on the page of the part it investigates
          </summary>
          <div className="filters">
            <select className="input" value={tool} aria-label="filter by analysis"
                    onChange={(e) => setTool(e.target.value)}>
              <option value="all">Every analysis ({data.reports.length})</option>
              {tools.map((t) => (
                <option key={t} value={t}>
                  {t} ({data.reports.filter((r) => r.tool === t).length})
                </option>
              ))}
            </select>
            {tool !== "all" && (
              <span className="muted">
                The same analysis across {rows.length} audit
                {rows.length === 1 ? "" : "s"}, newest first — read down to see
                what changed.
              </span>
            )}
          </div>

          {/* UX-07. Outside the table: `NarrowRunNote` below is this
              table's one permitted `<caption>`. The Ran-against column
              carries a `RunScore`, which is the same badge and bands. */}
          <ScoreBandKey />
          <div className="table-scroll">
            <table className="findings">
              {/* Mapped, not passed: this table's rows carry the run's kind
                  under `run_kind`, because a row here is an analysis and the
                  run is what it ran against. The component asks for `kind`
                  so the three call sites cannot each decide when the note
                  appears. */}
              <NarrowRunNote runs={rows.map((r) => ({ kind: r.run_kind,
                                                      scope: r.run_scope ?? null }))} />
              <thead>
                <tr>
                  <th>Analysis</th><th>Ran against</th>
                  <th className="num">Findings</th>
                  <th>Worst</th><th className="num">Tokens</th>
                  <th className="num">Cost</th><th>Model</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.run_id}:${r.tool}`}>
                    <td>
                      <code>{r.tool}</code>
                      {r.page_url && (
                        <div className="muted rep-page">{r.page_url}</div>
                      )}
                      {r.truncated && (
                        <Pill tone="state-regressed" title="The model
                          hit its output cap; the report is incomplete">
                          truncated
                        </Pill>
                      )}
                    </td>
                    <td>
                      {day(r.run_started_at)}{" "}
                      <span className="muted">{r.run_tier}</span>
                      {" "}<RunScore kind={r.run_kind} status={r.run_status}
                                     score={r.run_score}
                                     scope={r.run_scope ?? null} />
                      {/* Counted, not flagged: "superseded" is not something
                          an operator can act on, but "three audits since" is
                          — one is a re-read, five is a rewrite. */}
                      {!r.is_latest && r.audits_since ? (
                        <Pill tone="state-regressed" className="stale-mark"
                              title={"The site has been audited again since "
                                     + "this was written; it may name "
                                     + "findings a later audit has closed."}>
                          {r.audits_since} audit{r.audits_since > 1 ? "s" : ""} since
                        </Pill>
                      ) : null}
                    </td>
                    <td className="num">{r.findings}</td>
                    <td>
                      {r.worst_severity
                        ? <Pill tone={`sev-${r.worst_severity}` as Tone}>
                            {r.worst_severity}
                          </Pill>
                        : <span className="muted">—</span>}
                    </td>
                    <td className="num muted">
                      {r.tokens ? tokens(r.tokens) : "—"}
                    </td>
                    <td className="num muted">
                      {r.cost != null ? money(r.cost)
                        : <span title="Ran before a dollar rate was configured">—</span>}
                    </td>
                    <td className="muted">{r.model ?? "—"}</td>
                    <td>
                      <LinkButton href={`#/runs/${r.run_id}`}>
                        open&nbsp;→
                      </LinkButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {/* Audits that produced nothing are part of the record too: leaving
          them out would make this read as a shorter history than the site
          has, and "we audited and ran no briefs" is itself an answer. */}
      {data.runs.some((r) => r.reports === 0) && (
        <Card>
          <h3>Audits with no analysis</h3>
          <p className="muted">
            Crawled and scored, but nothing was asked of a model against them.
          </p>
          <ScoreBandKey />
          <div className="table-scroll">
            <table className="findings">
              <NarrowRunNote runs={data.runs.filter((r) => r.reports === 0)
                                     .map((r) => ({ kind: r.kind, scope: r.effective_scope ?? null }))} />
              <thead>
                <tr><th>Audit</th><th>Tier</th><th>Score</th><th></th></tr>
              </thead>
              <tbody>
                {data.runs.filter((r) => r.reports === 0).map((r) => (
                  <tr key={r.id}>
                    <td>{day(r.started_at)}</td>
                    <td className="muted">{r.tier}</td>
                    {/* The same answer as `views.tsx`, not a second one —
                        and since UX-42 that is enforced by there being one
                        component rather than by two copies agreeing. The
                        gates and their order are argued at `RunScore`.
                        `scope` is passed since 2026-09-18: without it the
                        narrow-scan gate inside `RunScore` could not fire, so
                        this cell printed a page scan's composite as a score
                        while `pane_audit.tsx`, passing it, read "page scan"
                        for the same run. One component, two call sites, one
                        missing argument. */}
                    <td><RunScore kind={r.kind} status={r.status}
                                  score={r.score} scope={r.effective_scope ?? null} /></td>
                    <td>
                      <LinkButton href={`#/runs/${r.id}`}>open&nbsp;→</LinkButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
