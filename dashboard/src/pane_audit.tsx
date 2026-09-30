/** The Audit pane: start an audit, and read every audit so far.
 *
 *  Brief step 8 (CQ-02): the pane's body, moved verbatim out of
 *  `SiteDetailView` with the helpers only it reads - the compare pairing,
 *  the canonical dimension order and the trend join. */
import { stamp } from "./client_lanes";
import { SecondaryButton } from "./buttons";
import { Dispatch, SetStateAction, useState } from "react";
import { ScheduleModal } from "./schedule";
import { api, Meta, SiteDetail, completedAudits, isDeletable, runsDiffer, scopeOf,
         useFetch } from "./api";
import { AnatomyScreen } from "./anatomy";
import { goHandler as navHandler, goto as navigate, historyHref } from "./nav";
import { ScanMatrix } from "./scanmatrix";
import { Card, NarrowRunNote, RunScore, RunStatusChip, ScoreBandKey } from "./components";
import { ScoreTrend, trendReading } from "./score_trend";
import { Pill } from "./pill";
import { DangerButton } from "./spend";

export function AuditPane({ siteId, data, anat, setTick, show = "all" }: {
  siteId: string;
  data: SiteDetail;
  anat: AnatomyScreen;
  setTick: Dispatch<SetStateAction<number>>;
  /** Brief v24 step BN splits this pane between two destinations: the
   *  chooser is Audit's (`start`), and every audit so far - the trend, the
   *  runs, the crawl diff - is the Record's (`history`). */
  show?: "all" | "start" | "history";
}) {
  const { data: meta } = useFetch<Meta>("/api/meta");
  /** The scheduler, beside the chooser it schedules (brief v2 step A): it
   *  stood in the retired What-to-do pane, and `?schedule` on the address still opens it. */
  const [schedOpen, setSchedOpen] = useState(
    () => new URLSearchParams((window.location.hash.split("?")[1]) || "")
      .has("schedule"));
  /** Each run, mapped to the run its score reads against — the trend's own
   *  `partner_run_id`, and brief v16f's "one rule, both surfaces".
   *
   *  WF-65 moved this from ADJACENT ROWS to consecutive READINGS: the
   *  product's own loop — audit, verify, audit — puts a verification
   *  directly beneath the newest audit, and the newest audit lost its
   *  comparison link exactly when the loop had just produced something worth
   *  comparing. Adjacency was not the relation. Consecutiveness among
   *  readings was nearer, and is still not it: two consecutive readings at
   *  different tiers measure different populations, and the comparison the
   *  link opened is the one `runsDiffer` refuses to draw a crawl diff for,
   *  forty lines below.
   *
   *  So the relation is the trend's: the nearest earlier point measured the
   *  same way. It is the server's answer, computed once in `site_trend`, and
   *  it is the answer the chart above draws a line for — a screen that
   *  offered a comparison the chart does not join would be two opinions about
   *  one pairing.
   *
   *  A run with no point — narrow, blocked, unscored — has no partner and
   *  is offered no link, which is the same exclusion one step earlier.
   *
   *  `readings` is gone with it. `completedAudits` still owns the relation
   *  and the crawl-diff gate below still asks it; what it no longer does is
   *  decide who may be compared with whom. */
  /** The two newest readings of the site, for the crawl-diff gate below.
   *  `completedAudits` still owns that relation - which runs may stand
   *  for the site, in order - and it is the right one for a question
   *  about the last two crawls. What it is no longer asked is which two
   *  runs may be COMPARED; that is the trend's partner, above. */
  const readings = completedAudits(data?.runs);
  const priorReading = new Map<string, string>(
    (data?.trend ?? [])
      .filter((p) => p.run_id && p.partner_run_id)
      .map((p) => [p.run_id as string, p.partner_run_id as string]));
  /** Brief step 7. The canonical dimension order is the server's own
   *  table; a code the table does not know sorts after it, by name, so the
   *  order is total whatever a run recorded. */
  const dimIndex = new Map((meta?.dimensions ?? []).map((d, i) => [d.code, i]));
  const sortDims = (ds: string[]) => [...ds].sort((x, y) =>
    ((dimIndex.get(x) ?? 999) - (dimIndex.get(y) ?? 999)) || x.localeCompare(y));
  /** Trend point index by run id, for the runs table's reading column.
   *
   *  It was a key of (stamp, tier, score), because `metric_snapshots` had no
   *  run column and `captured_at` is a second wide — two runs of one site
   *  finishing in the same second shared it, so tier and score were added to
   *  narrow the join and a key that still named two points was dropped rather
   *  than guessed. Migration 0044 stores the id on the row and `site_trend`
   *  reads it back, so the join is now the identity it always meant to be and
   *  the three-part key is gone rather than reimplemented here. A point whose
   *  run cannot be named — a pre-0044 row at an ambiguous stamp — carries
   *  `run_id: null` and joins nothing, which is what the old key's ambiguity
   *  rule did and for the same reason. */
  const trendAt = new Map<string, number>();
  (data?.trend ?? []).forEach((p, i) => {
    if (p.run_id) trendAt.set(p.run_id, i);
  });
  return (
    <>
      {/* Step 2's pane holds the chooser (plan §3): not a second way to
          start an audit — the same `ScanMatrix` the launcher mounts, reading
          the precheck step 1 runs. The panel itself lives once, on step 1's
          pane; the grid derives every cell's page count from the same
          payload, and the line under it says so. */}
      {show !== "history" && (
      <Card>
        <h3>Start an audit</h3>
        <ScanMatrix siteId={siteId} precheck={anat.precheck}
                    precheckLoading={anat.precheckLoading}
                    onLaunched={(runId) => navigate(`#/runs/${runId}`)} />
        <p className="audit-controls">
          {/* CQ-197: `schedule-open` names the one control that opens this
              dialog, so the rendered sweep can press it without pressing
              every other pill. */}
          <SecondaryButton className="schedule-open"
                  onClick={() => setSchedOpen(true)}>
            Schedule…
          </SecondaryButton>
          <span className="muted">Runs one of these on a cadence.</span>
        </p>
        {schedOpen && <ScheduleModal siteId={siteId} onClose={() => setSchedOpen(false)} />}
        <p className="muted scan-from-precheck">
          {/* "Measured", not "Page counts": the grid's own caption above
              names which figures the precheck produced and which are page
              budgets, and this sentence used to claim all of them for the
              precheck one line below it (UX-100). Its job is the link. */}
          Measured counts come from the precheck above — re-check it there
          if the site has changed. The by-hand setup —
          dimensions, tier, entry URL — is on
          the <a href={`#/sites/${siteId}/launch`}>launcher</a>.
        </p>
      </Card>
      )}
      {show !== "start" && (<>
      {/* The trend, drawn (brief v16f). UX-06 removed a dot chart that
          carried no axis, no dates and nothing its table did not say; this
          one carries all three and one thing no table can — which points are
          joined to which, across the runs between them. The Runs table below
          is still where a point's row lives, and its last column names the
          same partner this chart draws the line to. */}
      <ScoreTrend points={data.trend} />
      {/* No dimension breakdown here. It restated the run page's own table
          for one selected run, on a pane whose job is change over time; the
          run page owns it, and the Runs table below links to every one. */}
      <h3>Audits</h3>
      {/* `runs-table` carries no style. It exists so the rendered sweep can
          name this table without naming every `.findings` table on the
          screen — the Compare column's pairing and the narrow-run wording
          are both asserted on its text, and `.findings` matches the
          findings tables too. */}
      {/* UX-07. Outside the table because `NarrowRunNote` is this table's
          one permitted `<caption>` — a second would be dropped. */}
      <ScoreBandKey />
      <table className="findings runs-table">
        <NarrowRunNote runs={data.runs.map((r) => ({ kind: r.kind, scope: scopeOf(r) }))} />
        <thead>
          <tr><th>Started</th><th>Tier</th><th>Dimensions</th><th>Status</th>
              <th>Score</th><th>Reads against</th><th>Compare</th>
              <th>More</th></tr>
        </thead>
        <tbody>
          {data.runs.map((r, i) => (
            <tr key={r.id} className="linked-row">
              {/* Item 239 step 5: the way into a run's own record, which is
                  the history view - under a banner, in this tab. */}
              <td><a className="row-link" href={historyHref(siteId, r.id)}>
                {stamp(r.started_at)}
                <span className="muted history-cue"> · view as this audit saw it</span>
              </a></td>
              <td>{r.tier}</td>
              {/* One order for every row (brief step 7, UI-03): the server's
                  dimension table, `/api/meta`'s `dimensions`, which is the
                  order scoring itself lists them in. A run stores the
                  dimensions it was asked for in the order it was asked. */}
              <td>{sortDims(r.dimensions).join(", ")}</td>
              <td><RunStatusChip status={r.status} /></td>
              {/* A score only where one was produced. A blocked run carries a
                  composite computed from robots.txt and the sitemap alone —
                  80.0 on the fixture, from a crawl that fetched nothing — and
                  printing it beside a complete run's makes the two look
                  comparable. One owner, since UX-42. */}
              <td><RunScore kind={r.kind} status={r.status}
                            score={r.composite_score} scope={scopeOf(r)} /></td>
              {/* The trend's per-point reading, on the run that made the
                  point — which earlier run this score reads against, named.
                  A run with no point (narrow, blocked, unscored) reads a
                  dash: it is not on the chart above, and it has nothing to be
                  read against. */}
              <td className="muted">
                {trendAt.has(r.id) ? trendReading(data.trend, trendAt.get(r.id)!) : "—"}
              </td>
              <td>
                {/* Offered only between two readings of the site. This is
                    the pairing WF-60 was measured on: the 224-page audit
                    against the eight-page verification, offered here as "vs
                    previous", returning `resolved: 15` for findings that run
                    never looked at. The comparison itself now refuses to
                    resolve a site-level finding against a narrow run; not
                    offering the pairing is the same answer one step earlier,
                    where the operator can see why.

                    Not the previous ROW (WF-65) and no longer the previous
                    READING either — the nearest earlier run on the same
                    basis, which is brief v16f and is the pairing the chart
                    above joins. */}
                {priorReading.has(r.id) && (
                  <a href={`#/compare/${priorReading.get(r.id)}/${r.id}`}>vs previous</a>
                )}
              </td>
              <td>
                {/* The one destructive verb on the row, behind a disclosure
                    (brief step 7, UI-04): at equal weight beside "vs
                    previous" on every row it was the easiest thing on the
                    table to press. */}
                {isDeletable(r.status) && (
                  <details className="row-more">
                  <summary aria-label={`more actions for the audit of ${r.started_at ? stamp(r.started_at) : r.id.slice(0, 8)}`}>
                    more
                  </summary>
                  <DangerButton label={`delete the audit of ${r.started_at ? stamp(r.started_at) : r.id.slice(0, 8)}`}
                                confirm={{ title: `Delete the ${r.tier} audit of ${r.started_at?.slice(0, 10) ?? r.id.slice(0, 8)}?`,
                                           // Prose, so the missing case is prose too. A dash
                                           // inside a sentence naming the run reads as a score
                                           // too small to print - UX-15's defect at lower stakes.
                                           body: <p>Score {r.composite_score ?? "not assessed"}. This removes its
                                             findings and its trend point permanently.</p>,
                                           action: "Delete the audit" }}
                                onConfirm={async () => {
                                  await api.del(`/api/runs/${r.id}`);
                                  setTick((t) => t + 1);
                                }}>
                    delete
                  </DangerButton>
                  </details>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* The diff between the two newest crawls, only when the two can be
          read as one series (brief v2 step B, WF-05 and WF-04's root): a
          T1 navigation scan after a T2 site scan reported the pages the
          smaller scan never visited as "19 pages gone", and the record's
          `/apply` contradiction was that shrink read as loss. The predicate
          is the one the runs table's reading column stands on - tier,
          engine, scope, dimensions - and when it fails, the box says which
          moved rather than painting a diff that is not one. */}
      {readings.length >= 2 && runsDiffer(readings[1], readings[0]).length > 0 && (
        <p className="muted crawl-diff-gate">
          Between the two newest crawls: no comparable pair yet — the newest
          two differ in {runsDiffer(readings[1], readings[0]).join("; ")}.
        </p>
      )}
      {(data as any).crawl_diff && readings.length >= 2
        && runsDiffer(readings[1], readings[0]).length === 0 && (() => {
        const d = (data as any).crawl_diff;
        const any_ = d.added.length + d.removed.length
                   + d.status_changed.length + d.rewritten.length;
        if (!any_) return null;
        return (
          <Card>
            <h3>Between the last two crawls</h3>
            {!!d.removed.length && (
              <p><strong className="regressed">{d.removed.length} page(s) gone:</strong>{" "}
                 {d.removed.slice(0, 5).map((u: string) =>
                   <code key={u}>{u.replace(/^https?:\/\/[^/]+/, "")} </code>)}
                 {d.removed.length > 5 ? "…" : ""}</p>
            )}
            {!!d.added.length && (
              <p><strong className="good-text">{d.added.length} new:</strong>{" "}
                 {d.added.slice(0, 5).map((u: string) =>
                   <code key={u}>{u.replace(/^https?:\/\/[^/]+/, "")} </code>)}
                 {d.added.length > 5 ? "…" : ""}</p>
            )}
            {!!d.status_changed.length && (
              <p><strong>Status changed:</strong>{" "}
                 {d.status_changed.slice(0, 6).map((c: any) => (
                   <span key={c.url}><code>{c.url.replace(/^https?:\/\/[^/]+/, "")}</code>
                     {" "}{c.before}→{c.after} · </span>))}</p>
            )}
            {!!d.rewritten.length && (
              <p><strong>Substantially rewritten</strong>{" "}
                 <span className="muted">(word count moved ≥30%):</span>{" "}
                 {d.rewritten.slice(0, 6).map((c: any) => (
                   <span key={c.url}><code>{c.url.replace(/^https?:\/\/[^/]+/, "")}</code>
                     {" "}{c.before}→{c.after}w · </span>))}</p>
            )}
          </Card>
        );
      })()}
      {!!(data as any).expert_delta?.filter((d: any) => d.since).length && (
        <>
          <h3>Since the previous run of each analysis</h3>
          <table className="findings">
            <thead><tr><th>Analysis</th><th>New</th><th>Resolved</th><th>Persisting</th></tr></thead>
            <tbody>
              {(data as any).expert_delta.filter((d: any) => d.since).map((d: any) => (
                <tr key={d.tool}>
                  <td><code>{d.tool}</code></td>
                  <td>{d.new.length ? d.new.map((c: string) =>
                        <code key={c}>{c} </code>) : <span className="muted">—</span>}</td>
                  <td className="good-text">{d.resolved.length ? d.resolved.join(", ") : "—"}</td>
                  <td className="muted">{d.persisting.length ? d.persisting.join(", ") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      </>)}
    </>
  );
}
