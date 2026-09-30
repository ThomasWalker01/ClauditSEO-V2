/**
 * Per-page dossier: everything known about one URL, across every run and
 * every brief. Clients ask page-first — "what's wrong with our services
 * page?" — and until now the answer was scattered per-tool.
 */
import { useEffect, useState } from "react";
import { ApiError, api } from "./api";
import { Card, ErrorNote, Loading } from "./components";

type Dossier = {
  url: string;
  history: { run_id: string; at: string; source: string; status: number | null;
             title: string | null; word_count: number | null;
             click_depth: number | null;
             content_dates: Record<string, string> }[];
  findings: { dimension: string; check_id: string; severity: string;
              summary: string; source: string; state: string | null;
              attempted_at: string | null }[];
  page_briefs: { tool_id: string; model_id: string; created_at: string;
                 tokens: number | null; findings: number }[];
};

export function PageDossierView({ siteId, url }:
    { siteId: string; url: string }) {
  const [data, setData] = useState<Dossier | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.get<Dossier>(`/api/sites/${siteId}/dossier?url=${encodeURIComponent(url)}`)
      .then((d) => { if (live) setData(d); })
      .catch((e: ApiError) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [siteId, url]);

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
        {latest && <> · seen in {data.history.length} crawl(s), last {latest.at.slice(0, 10)}</>}
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
                {Object.entries(latest.content_dates).map(([k, v]) =>
                  `${k}: ${String(v).slice(0, 10)}`).join(" · ")}
              </p>
            )}
          </Card>
          <Card>
            <h3>Crawl history</h3>
            <table className="findings">
              <thead><tr><th>When</th><th>Status</th><th>Words</th><th>Depth</th></tr></thead>
              <tbody>
                {data.history.map((h) => (
                  <tr key={h.run_id} className="linked-row">
                    <td><a className="row-link" href={`#/runs/${h.run_id}`}>
                      {h.at.slice(0, 10)}</a></td>
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
                  {f.state
                    ? <span className={`state state-${f.state}`}>{f.state}</span>
                    : <span className="muted">untracked</span>}
                  {f.attempted_at && <span className="muted"> · fix attempted</span>}
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
                <code>{b.tool_id}</code> · {b.created_at.slice(0, 10)} ·{" "}
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
