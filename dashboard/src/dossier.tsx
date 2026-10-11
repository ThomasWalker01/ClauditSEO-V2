/**
 * Per-page dossier: everything known about one URL, across every run and
 * every brief. Clients ask page-first — "what's wrong with our services
 * page?" — and until now the answer was scattered per-tool.
 */
import { useEffect, useState } from "react";
import { ApiError, api } from "./api";
import { Card, ErrorNote, Loading } from "./components";
import { day } from "./dates";
import { ConfirmControls, candidateWord } from "./to_confirm";
import { ExpertPanel, ExpertSpec } from "./expert";
import { useAnalyses } from "./analyses";

type Dossier = {
  url: string;
  history: { run_id: string; at: string; source: string; status: number | null;
             /** Which run (item 257): its kind, tier and scope. */
             kind?: string; tier?: string | null; scope?: string | null;
             title: string | null; word_count: number | null;
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
              superseded_on?: string | null; unseen_since?: string | null }[];
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
  const previous = data.history[1];
  const wordShift = latest?.word_count != null && previous?.word_count
    ? latest.word_count - previous.word_count : null;

  return (
    <>
      <h2 className="dossier-url">{data.url}</h2>
      <p className="muted">
        <a href={`#/sites/${siteId}`}>back to site</a> ·{" "}
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
              <thead><tr><th>When</th><th>Run</th><th>Status</th><th>Words</th><th>Depth</th></tr></thead>
              <tbody>
                {data.history.map((h) => (
                  <tr key={h.run_id} className="linked-row">
                    <td><a className="row-link" href={`#/runs/${h.run_id}`}>
                      {day(h.at)}</a></td>
                    <td className="muted dossier-run">{runLabel(h)}</td>
                    <td>{h.status ?? "—"}</td>
                    <td>{h.word_count ?? "—"}</td>
                    <td>{h.click_depth ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      <h3>Findings naming this page</h3>
      {data.measured_run_id && (
        <ExpertPanel runId={data.measured_run_id} siteId={siteId} tools={pageExperts} url={url}
                     heading="Page-level experts" latestForPage />
      )}
      {data.findings.length ? (
        <table className="findings">
          <thead><tr><th>Severity</th><th>Check</th><th>Summary</th>
                     <th>Memory</th></tr></thead>
          <tbody>
            {data.findings.map((f, i) => (
              <tr key={i}>
                <td><span className={`sev sev-${f.severity}`}>{f.severity}</span></td>
                <td><code>{f.dimension}/{f.check_id}</code></td>
                <td>{f.summary}</td>
                <td>
                  {f.superseded_on
                    // Overtaken: the automatic checks read this page after
                    // the analysis and cleared the check. Said as that, not
                    // as the row's own "open" beside the sweep's "fixed".
                    ? <span className="muted">
                        overtaken: the automatic checks cleared it {day(f.superseded_on)}
                      </span>
                    : f.state
                    ? <span className={`state state-${f.state}`}>
                        {f.state === "candidate" ? candidateWord(f.to_confirm) : f.state}
                      </span>
                    : <span className="muted">untracked</span>}
                  {!f.superseded_on && f.unseen_since && (
                    <span className="muted"> · not seen by the automatic checks since {day(f.unseen_since)}</span>
                  )}
                  {/* Item 250: the same three answers the part page offers. */}
                  {f.to_confirm && f.fingerprint && (
                    <ConfirmControls fingerprints={[f.fingerprint]} siteId={siteId}
                                     subject={`${f.dimension}/${f.check_id}`}
                                     onStateChanged={() => setTick((t) => t + 1)} />
                  )}
                  {f.attempted_at && <span className="muted"> · fix attempted</span>}
                  {(f.analysed_at || f.measured_at) && (
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
