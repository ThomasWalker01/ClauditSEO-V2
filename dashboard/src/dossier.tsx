/**
 * Per-page dossier: everything known about one URL, across every run and
 * every brief. Clients ask page-first — "what's wrong with our services
 * page?" — and until now the answer was scattered per-tool.
 */
import { useEffect, useState } from "react";
import { ApiError, api } from "./api";
import { Card, ErrorNote, Loading, SeverityTag } from "./components";
import { day, stamp } from "./dates";
import { ConfirmControls, TO_CONFIRM_LEGEND, candidateWord } from "./to_confirm";
import { Legend, entry } from "./glossary";
import { Pill, Tone } from "./pill";
import type { Severity } from "./api";
import { ExpertPanel, ExpertSpec } from "./expert";
import { useAnalyses } from "./analyses";
import { goHandler } from "./nav";

type Dossier = {
  url: string;
  history: { run_id: string; at: string; source: string; status: number | null;
             /** Which run (item 257): its kind, tier and scope. */
             kind?: string; tier?: string | null; scope?: string | null;
             /** The server's label ("Links only") for a re-check of some
              *  parts (screen audits round 4, Pages IP-01), or null. */
             part_only?: string | null;
             title: string | null; word_count: number | null;
             meta_description?: string | null;
             click_depth: number | null;
             content_dates: Record<string, string> }[];
  findings: { dimension: string; check_id: string; severity: string;
              summary: string; source: string; state: string | null;
              attempted_at: string | null;
              /** Item 250: the row's identity, and whether it waits for the
               *  operator. */
              fingerprint?: string; to_confirm?: boolean;
              /** When the run that last measured the row finished, and - for
               *  an analysis row - when the analysis was written (item 251). */
              measured_at?: string | null; analysed_at?: string | null;
              /** The record's reconciliation (screen audits round 3): an
               *  analysis row a later automatic reading cleared, and one it
               *  has not raised since. */
              superseded_on?: string | null; unseen_since?: string | null;
              /** Screen audits round 4 (Pages IP-02, AC-04, AC-05, IP-06). */
              source_word?: string | null; coverage_note?: boolean;
              brief_status?: string | null; state_at?: string | null }[];
  /** The Pages table's count for this page, by its rule (one per check). */
  open_checks?: number;
  page_briefs: { tool_id: string; model_id: string; created_at: string;
                 tokens: number | null; findings: number }[];
  /** The run that last measured this page: what a page-level analysis runs
   *  against (item 251). Not the site's newest run - a page the newest
   *  crawl did not fetch was last measured by an older one. */
  measured_run_id?: string | null;
  /** The crawls the history was looked for in (item 257): the newest
   *  `looked_in` of the site's `total`. */
  crawls?: { looked_in: number; total: number };
};

/** What a crawl row was, in the words the Audits tab uses: an audit's tier and
 *  scope, or a re-check of one part. */
function runLabel(h: Dossier["history"][number]): string {
  if (h.kind === "refresh") return "re-check";
  if (h.part_only) return `re-check · ${h.part_only}`;
  if (h.kind && h.kind !== "audit") return h.kind;
  const scope = h.scope ? ` · ${h.scope}` : "";
  return `${h.tier ?? "audit"}${scope}`;
}

/** "seen in 4 of the site's 5 crawls", or, where only the newest are opened,
 *  "seen in 6 of the last 6 crawls (11 in all)". */
export function crawlsSeen(seen: number, crawls: Dossier["crawls"]): string {
  const n = (k: number) => `${k} crawl${k === 1 ? "" : "s"}`;
  if (!crawls) return `seen in ${n(seen)}`;
  return crawls.total > crawls.looked_in
    ? `seen in ${seen} of the last ${n(crawls.looked_in)} (${crawls.total} in all)`
    : `seen in ${seen} of the site's ${n(crawls.total)}`;
}

export function PageDossierView({ siteId, url }:
    { siteId: string; url: string }) {
  const [data, setData] = useState<Dossier | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** Bumped by an answer to a "to confirm" row (item 250), so the row is
   *  read back in the state the answer left it. */
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    api.get<Dossier>(`/api/sites/${siteId}/dossier?url=${encodeURIComponent(url)}`)
      .then((d) => { if (live) setData(d); })
      .catch((e: ApiError) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [siteId, url, tick]);

  // The page-level analyses, from the lanes payload's own headers. They
  // lived on `#/runs/<id>/page/<url>` (item 251), which now lands here.
  const { data: pageLanes } = useAnalyses(data?.measured_run_id ?? null);
  const pageExperts: ExpertSpec[] = (pageLanes ? [...pageLanes.ready, ...pageLanes.available] : [])
    .filter((x) => x.type === "page")
    .map((x) => ({ id: x.tool, name: x.name, blurb: x.does,
                   tier: x.tier as ExpertSpec["tier"], inputs: x.inputs }));

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;

  const latest = data.history[0];
  // A PASS the analysis returned is not a fault to confirm (screen audits
  // round 4, Pages AC-05): "home page correctly carries no BreadcrumbList"
  // stood with Confirm, Accept and Withdraw.
  const passed = (f: Dossier["findings"][number]) =>
    f.state === "candidate" && /^PASS/i.test(f.brief_status ?? "");
  // Coverage notes are not findings (AC-04): said under the table.
  const notes = data.findings.filter((f) => f.coverage_note);
  const rows = data.findings.filter((f) => !f.coverage_note);
  const waiting = rows.filter((f) => f.state === "candidate" && f.to_confirm && !passed(f)).length;
  const fixedN = rows.filter((f) => f.state === "fixed").length;
  const previous = data.history[1];
  const wordShift = latest?.word_count != null && previous?.word_count
    ? latest.word_count - previous.word_count : null;

  return (
    <>
      <h2 className="dossier-url">{data.url}</h2>
      <p className="muted">
        {/* Screen audits round 4 (Pages UX-05): back to the table the page
            was opened from. */}
        <a href={`#/sites/${siteId}?tab=pages`}
           onClick={goHandler(`#/sites/${siteId}?tab=pages`)}>back to pages</a> ·{" "}
        <a href={data.url} target="_blank" rel="noreferrer noopener">open page</a>
        {/* Item 257: what was counted. It read "seen in 6 crawl(s)" on a
            site with eleven: only the newest six are opened. */}
        {latest && <> · {crawlsSeen(data.history.length, data.crawls)}, last {day(latest.at)}</>}
      </p>

      {latest && (
        <div className="cols">
          <Card>
            <h3>As last crawled</h3>
            <p>
              HTTP {latest.status} · {latest.word_count ?? "?"} words
              {wordShift != null && wordShift !== 0 && (
                <strong className={wordShift < 0 ? " regressed" : " good-text"}>
                  {" "}({wordShift > 0 ? "+" : ""}{wordShift} since previous crawl)
                </strong>
              )} · depth {latest.click_depth ?? "?"}
              {latest.source !== "crawler" && <> · via {latest.source}</>}
            </p>
            <p className="muted">{latest.title ?? "no title captured"}</p>
            {!!Object.keys(latest.content_dates ?? {}).length && (
              <p className="muted">
                {/* The page's own stated dates, as the page states them: a
                    day the page publishes is not an instant this product
                    measured, so it is not moved into the reader's zone. */}
                {Object.entries(latest.content_dates).map(([k, v]) =>
                  `${k}: ${String(v).slice(0, 10)}`).join(" · ")}
              </p>
            )}
          </Card>
          <Card>
            <h3>Crawl history</h3>
            <table className="findings">
              <thead><tr><th>When</th><th>Run</th><th>Status</th><th>Words</th><th>Depth</th>
                         <th>Title</th></tr></thead>
              <tbody>
                {data.history.map((h, i) => {
                  // Screen audits round 4 (Pages US-03): the title the crawl
                  // fetched, marked where it changed from the crawl before.
                  const older = data.history[i + 1];
                  const titleMoved = older && older.title !== h.title;
                  const descMoved = older && (older.meta_description ?? null) !== (h.meta_description ?? null);
                  return (
                    <tr key={h.run_id} className="linked-row">
                      <td><a className="row-link dossier-run-link" href={`#/runs/${h.run_id}`}>
                        {stamp(h.at)}</a></td>
                      <td className="muted dossier-run">{runLabel(h)}</td>
                      <td>{h.status ?? "—"}</td>
                      <td>{h.word_count ?? "—"}</td>
                      <td>{h.click_depth ?? "—"}</td>
                      <td className="dossier-title">
                        {h.title ?? <span className="muted">none</span>}
                        {titleMoved && <span className="muted"> · title changed</span>}
                        {descMoved && <span className="muted"> · description changed</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {/* Screen audits round 4 (Pages UX-01): the analyses before the
          findings heading, so the heading heads the table. */}
      {data.measured_run_id && (
        <ExpertPanel runId={data.measured_run_id} siteId={siteId} tools={pageExperts} url={url}
                     heading="Page-level experts" latestForPage />
      )}
      <h3>Findings naming this page</h3>
      {rows.length > 0 && (
        <p className="muted dossier-count">
          {/* The Pages table's number, by its rule (screen audits round 4,
              Pages AC-03, UX-03): one per check, whoever found it. */}
          {data.open_checks ?? 0} check{data.open_checks === 1 ? "" : "s"} open or back after a fix
          {waiting > 0 && <> · {waiting} to confirm</>}
          {fixedN > 0 && <> · {fixedN} fixed</>}
          {" · "}{rows.length} row{rows.length === 1 ? "" : "s"} in all
        </p>
      )}
      {rows.length > 0 && (
        // Screen audits round 4 (Pages IP-04): the severities and states
        // the table draws, and the three answers where a row waits on them.
        <Legend ids={[...[...new Set(rows.map((f) => `sev-${f.severity}`))],
                      ...[...new Set(rows.filter((f) => f.state && f.state !== "candidate")
                                         .map((f) => `state-${f.state}`))],
                      ...(waiting ? TO_CONFIRM_LEGEND : [])]} />
      )}
      {rows.length ? (
        <table className="findings">
          <thead><tr><th>Severity</th><th>Check</th><th>Source</th><th>Summary</th>
                     <th>State</th></tr></thead>
          <tbody>
            {rows.map((f, i) => (
              <tr key={i}>
                <td><SeverityTag severity={f.severity as Severity} /></td>
                <td><code>{f.dimension}/{f.check_id}</code></td>
                <td className="muted dossier-source">
                  {f.source_word === "brief" ? "analysis" : "automatic"}
                </td>
                <td>{f.summary}</td>
                <td>
                  {passed(f)
                    ? <span className="muted">passed by the analysis</span>
                    : f.superseded_on
                    // Overtaken: the automatic checks read this page after
                    // the analysis and cleared the check. Said as that, not
                    // as the row's own "open" beside the sweep's "fixed".
                    ? <span className="muted">
                        overtaken: the automatic checks cleared it {day(f.superseded_on)}
                      </span>
                    : f.state
                    ? <Pill tone={(f.state === "candidate" ? "state-candidate"
                                   : `state-${f.state}`) as Tone}>
                        {f.state === "candidate" ? candidateWord(f.to_confirm)
                          : entry(`state-${f.state}`).word}
                      </Pill>
                    : <span className="muted">not on the record</span>}
                  {!f.superseded_on && f.unseen_since && (
                    <span className="muted"> · not seen by the automatic checks since {day(f.unseen_since)}</span>
                  )}
                  {/* Item 250: the same three answers the part page offers. */}
                  {f.to_confirm && f.fingerprint && !passed(f) && (
                    // The legend above says what the three answers do, once
                    // (screen audits round 4, Pages UX-09: fifteen copies).
                    <ConfirmControls fingerprints={[f.fingerprint]} siteId={siteId}
                                     subject={`${f.dimension}/${f.check_id}`} explain={false}
                                     onStateChanged={() => setTick((t) => t + 1)} />
                  )}
                  {f.attempted_at && <span className="muted"> · fix attempted</span>}
                  {/* A fixed row is dated by the reading that cleared it
                      (screen audits round 4, Pages IP-06, AC-01): "fixed ·
                      measured 11 Oct" stood beside its old failing figure. */}
                  {f.state === "fixed" && f.state_at ? (
                    <span className="muted dossier-measured">
                      {" · "}cleared {day(f.state_at)}; the summary is the last reading that raised it
                    </span>
                  ) : f.state === "regressed" && f.state_at ? (
                    // Screen audits round 4 (Run views AC-03): "regressed ·
                    // measured 12 Oct" on rows that came back on 25 Sept.
                    <span className="muted dossier-measured">
                      {" · "}back since {day(f.state_at)}
                      {f.measured_at ? `; last measured ${day(f.measured_at)}` : ""}
                    </span>
                  ) : (f.analysed_at || f.measured_at) && (
                    <span className="muted dossier-measured">
                      {" · "}{f.analysed_at ? `analysed ${day(f.analysed_at)}`
                                           : `measured ${day(f.measured_at)}`}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No finding names this page. That is a statement
           about the checks run so far, not a clean bill of health.</p>}
      {notes.length > 0 && (
        <p className="muted dossier-notes">
          Not findings, so not counted: {notes.map((f) => `${f.dimension}/${f.check_id}`).join(", ")}
          {" "}— what an audit of this kind cannot observe.
        </p>
      )}

      {!!data.page_briefs.length && (
        <>
          <h3>Page analyses that read this URL</h3>
          <ul className="group-pages">
            {data.page_briefs.map((b, i) => (
              <li key={i}>
                <code>{b.tool_id}</code> · {day(b.created_at)} ·{" "}
                {b.findings} finding{b.findings === 1 ? "" : "s"} · {b.model_id}
                {" "}<a href="#/tools">open in tools</a>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
