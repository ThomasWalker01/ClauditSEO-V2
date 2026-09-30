/**
 * What runs on this site without anyone asking.
 *
 * Two different things, deliberately in one place. The site cadence runs the
 * whole deterministic sweep and costs nothing but time. A brief cadence runs
 * one expert brief and costs money every time it fires — so each row carries
 * what that brief has actually cost before, because a cadence chosen without
 * a price is a guess.
 */
import { Working } from "./working";
import { SecondaryButton } from "./buttons";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { BriefPriceFrame, PriceScopeNote, money } from "./components";
import { Pill } from "./pill";
import { useDialog } from "./confirm";
import { SaveRule } from "./save_rule";

export type ToolRow = { tool_id: string; cadence: string; last_run_at: string | null;
                 due_now: boolean };
/** `cost_samples` and `samples` are the population behind `typical_cost`:
 *  the endpoint has carried both since round 079
 *  (`cost_samples` in `/api/playbook`) and this modal has never read
 *  either - UX-74. It matters most here, because this is
 *  the one screen that multiplies the price by a cadence into a year.
 *
 *  `scoped_to_site` is the population the price was measured over - CQ-198.
 *  This endpoint is always site-scoped and so never sends `null`, which is
 *  exactly why the key is read rather than assumed: the modal states what the
 *  answer says it counted, so a future endpoint that widened would be visible
 *  here instead of silently repriced under this site's name.
 *
 *  CQ-216: these were two blocks, and the CQ-198 one was inserted *between*
 *  the UX-74 block and the `type Available` it documents - so only the
 *  younger block attached and the older one documented nothing. One block,
 *  because both describe the same type. */
export type Available = { tool_id: string; cost_samples?: number; samples?: number;
                   typical_cost: number | null;
                   typical_tokens: number | null;
                   scoped_to_site?: string | null };
export type Schedule = {
  audit_cadence: string | null;
  audit_cadences: string[];
  tool_cadences: string[];
  tools: ToolRow[];
  available: Available[];
};

export const PER_YEAR: Record<string, number> = {
  weekly: 52, fortnightly: 26, monthly: 12, quarterly: 4,
};

/** What a set of brief cadences costs a year, and what that figure is made of.
 *  One computation for the per-site modal and the Admin grid (item 177), so the
 *  two never price the same schedule differently. `unpriced` counts scheduled
 *  briefs with no measured price; `partlyPriced` those whose price is a median
 *  over runs that were not all costed (UX-74). */
export function annualCost(available: Available[], tools: Record<string, string>) {
  let perYear = 0, unpriced = 0, partlyPriced = 0;
  for (const a of available) {
    const cadence = tools[a.tool_id];
    if (!cadence) continue;
    if (a.typical_cost == null) { unpriced += 1; continue; }
    perYear += a.typical_cost * (PER_YEAR[cadence] ?? 0);
    if ((a.samples ?? 0) > (a.cost_samples ?? 0)) partlyPriced += 1;
  }
  return { perYear, unpriced, partlyPriced, scheduled: Object.keys(tools).length };
}



export function ScheduleModal({ siteId, onClose }:
    { siteId: string; onClose: () => void }) {
  const [data, setData] = useState<Schedule | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [audit, setAudit] = useState<string>("");
  const [tools, setTools] = useState<Record<string, string>>({});
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    api.get<Schedule>(`/api/sites/${siteId}/schedule`)
      .then((d) => {
        if (!live) return;
        setData(d);
        setAudit(d.audit_cadence ?? "");
        setTools(Object.fromEntries(d.tools.map((t) => [t.tool_id, t.cadence])));
      })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [siteId]);

  // Escape closes, focus starts inside, Tab stays inside, and closing returns
  // focus to the control that opened it - the one dialog behaviour (item 181,
  // UI audit 03-5, 10-3). Before this, Tab left for the page behind the
  // backdrop - on the Audit pane, onto a paid scan cell - and Escape left
  // focus on the body.
  useDialog(dialog, onClose);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/api/sites/${siteId}/schedule`, {
        audit_cadence: audit || null,
        tools: Object.entries(tools).map(([tool_id, cadence]) => ({ tool_id, cadence })),
      });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  /** `partlyPriced`: scheduled rows whose price *is* known and is a median
   *  over a sample that was only partly costed - UX-74. Distinct from
   *  `unpriced`, which counts rows with no price at all: that clause says what
   *  the forecast left out, this one says what the figures it used are made
   *  of. Counted rather than summarised into the money, because a sum of
   *  medians has no direction an unpriced sample pushes it in. */
  const { perYear: costPerYear, unpriced, partlyPriced, scheduled: scheduledCount } =
    annualCost(data?.available ?? [], tools);

  return (
    /* role=presentation: a backdrop is not a control. Dismissal by Escape
       and by the close button below are the real paths; clicking outside is
       a mouse convenience on top of them. */
    <div className="modal-backdrop" role="presentation" onClick={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <div className="modal" role="dialog" aria-modal="true"
           aria-label="Schedule what runs on this site" tabIndex={-1} ref={dialog}>
        <div className="modal-head">
          <h3>Schedule</h3>
          <SecondaryButton onClick={onClose}>close</SecondaryButton>
        </div>

        <SaveRule kind="explicit" also="on-change" />
        {error && <p className="error" role="alert">{error}</p>}
        {!data ? <p className="muted">Loading…</p> : (
          <>
            <section className="sched-block">
              <h4>The whole audit</h4>
              <p className="muted sched-note">
                Crawls the site and runs every deterministic dimension. Costs
                time, not money. The scheduler will not start the first audit
                for a site — that one sizes the site and is yours to run.
              </p>
              <div className="sched-cadence">
                {["", ...data.audit_cadences].map((c) => (
                  <label key={c || "manual"} className="radio">
                    <input type="radio" name="audit" value={c}
                           checked={audit === c}
                           onChange={() => setAudit(c)} />
                    {c || "manual only"}
                  </label>
                ))}
              </div>
            </section>

            <section className="sched-block">
              <h4>Individual analyses</h4>
              <p className="muted sched-note">
                Each one reads the site's most recent completed audit. These
                cost money every time they fire, so the price shown is what
                that analysis has actually cost here before — not an estimate.
              </p>
              {/* CQ-198, and this is the screen where "here" was doing the
                  most work: the paragraph above says the price is what the
                  brief has cost, the table below multiplies it by a cadence
                  into a year, and neither said whose history it came from. */}
              {data.available[0] && <PriceScopeNote
                  scopedToSite={data.available[0].scoped_to_site} />}
              <div className="table-scroll">
                <table className="findings sched-table">
                  <thead>
                    <tr><th>Analysis</th><th className="num">Typical cost</th>
                        <th>Cadence</th><th>Last run</th></tr>
                  </thead>
                  <tbody>
                    {data.available.map((a) => {
                      const row = data.tools.find((t) => t.tool_id === a.tool_id);
                      const on = tools[a.tool_id];
                      return (
                        <tr key={a.tool_id} className={on ? "sched-on" : ""}>
                          <td><code>{a.tool_id}</code></td>
                          <td className="num">
                            {a.typical_cost != null ? <>
                                 {money(a.typical_cost)}{" "}
                                 {/* UX-74, and rendered text rather than the
                                     `title=` the cell below uses - the
                                     provenance invariant's extended clause. */}
                                 <BriefPriceFrame costed={a.cost_samples ?? 0}
                                                  sampled={a.samples ?? 0} />
                               </>
                             : a.typical_tokens
                               ? <span className="muted">
                                   ~{Math.round(a.typical_tokens / 1000)}k tokens
                                 </span>
                               : <span className="muted" title="never run here, so
                                   there is nothing to price it from">not yet run</span>}
                          </td>
                          <td>
                            <select className="input sched-select" value={on ?? ""}
                                    aria-label={`cadence for ${a.tool_id}`}
                                    onChange={(e) => setTools((t) => {
                                      const next = { ...t };
                                      if (e.target.value) next[a.tool_id] = e.target.value;
                                      else delete next[a.tool_id];
                                      return next;
                                    })}>
                              <option value="">never</option>
                              {data.tool_cadences.map((c) => (
                                <option key={c} value={c}>{c}</option>
                              ))}
                            </select>
                          </td>
                          <td className="muted">
                            {row?.last_run_at ? row.last_run_at.slice(0, 10)
                             : <span className="muted">—</span>}
                            {row?.due_now && <span className="due-tag">due now</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* The number an operator actually needs before agreeing to this. */}
            {/* "No briefs scheduled" and "scheduled but not yet priceable"
                are different statements, and reading the first while two are
                selected is worse than saying nothing. */}
            <div className="sched-total">
              {scheduledCount === 0 ? (
                <strong>No analyses scheduled — nothing will be spent unattended.</strong>
              ) : costPerYear > 0 ? (
                <>
                  <strong>About {money(costPerYear)} a year at these cadences.</strong>
                  {partlyPriced > 0 && (
                    <span className="figure-frame">
                      {" "}{partlyPriced} of these price{partlyPriced === 1 ? "" : "s"}
                      {" "}{partlyPriced === 1 ? "is a median" : "are medians"} over
                      {" "}runs that were not all costed.
                    </span>
                  )}
                  {unpriced > 0 && (
                    <span className="muted">
                      {" "}Plus {unpriced} that {unpriced === 1 ? "has" : "have"} never
                      run here, so there is no measured price to add.
                    </span>
                  )}
                </>
              ) : (
                <strong>
                  {scheduledCount} analys{scheduledCount === 1 ? "is" : "es"} scheduled,
                  none of which {scheduledCount === 1 ? "has" : "have"} run here yet —
                  so there is nothing measured to price them from. The cost will show
                  once they have run once.
                </strong>
              )}
            </div>

            <div className="modal-actions">
              <SecondaryButton onClick={onClose}>cancel</SecondaryButton>
              {/* UX-66. Stable caption, state on `aria-busy`, words in the
                  unconditionally-mounted region beside it — the convention
                  `views.tsx`'s `ReportView` states in full. */}
              <SecondaryButton onClick={save}
                      disabled={saving} aria-busy={saving}>
                save schedule
              </SecondaryButton>
              <span className="muted" role="status" aria-live="polite">
                {saving && <Working>Saving the schedule…</Working>}
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
