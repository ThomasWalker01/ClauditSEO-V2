/**
 * Every site's cadence on one screen (item 177, concept H5 relocated to Admin).
 *
 * "When does each site run" is one question about every site, and answering it
 * meant opening each site's schedule modal in turn and holding the previous
 * ones in your head. This is the same data seen across sites: one row per site,
 * the whole-audit cadence and every brief cadence as columns, and what the row
 * costs a year, totalled.
 *
 * **One source of truth.** Each row is that site's `GET /api/sites/{id}/schedule`
 * and every change is that site's `PUT`, carrying the site's whole schedule -
 * the endpoint replaces wholesale, as the modal does - so the grid and
 * `ScheduleModal` read and write the same fields and the modal stays.
 *
 * **The cost is per row and totalled.** A cadence chosen without its price is a
 * cadence chosen blind (`schedule.tsx`), and across sites the total is the
 * number that decides. The arithmetic is `annualCost`, the modal's own, so the
 * two never price one schedule differently; the per-brief prices, with the runs
 * they came from, are one press away in that site's modal.
 */
import { Working } from "./working";
import { SecondaryButton } from "./buttons";
import { useEffect, useState } from "react";
import { api } from "./api";
import { money } from "./components";
import { LOADING_WORD } from "./glossary";
import { SaveRule } from "./save_rule";
import { ScheduleModal, annualCost, type Schedule } from "./schedule";
import { host, useSelection } from "./selection";

type Row = { schedule: Schedule | null; error: string | null; saving: boolean };

/** A site's brief cadences as the modal holds them: tool -> cadence. */
const toolsOf = (s: Schedule) => Object.fromEntries(s.tools.map((t) => [t.tool_id, t.cadence]));

export function CadenceGrid() {
  const { sites } = useSelection();
  const [rows, setRows] = useState<Record<string, Row>>({});
  /** Brief columns added here before any site schedules them. */
  const [added, setAdded] = useState<string[]>([]);
  const [modal, setModal] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const siteKey = sites.map((s) => s.id).join(",");
  useEffect(() => {
    let live = true;
    for (const s of sites) {
      api.get<Schedule>(`/api/sites/${s.id}/schedule`)
        .then((d) => { if (live) setRows((r) => ({ ...r, [s.id]: { schedule: d, error: null, saving: false } })); })
        .catch((e) => { if (live) setRows((r) => ({ ...r, [s.id]: { schedule: null, error: (e as Error).message, saving: false } })); });
    }
    return () => { live = false; };
  }, [siteKey, tick]);

  /** Write one site's whole schedule with one field changed, and show what the
   *  server answered - never the local guess. */
  const put = async (siteId: string, audit: string | null, tools: Record<string, string>) => {
    setRows((r) => ({ ...r, [siteId]: { ...r[siteId], saving: true, error: null } }));
    try {
      const d = await api.put<Schedule>(`/api/sites/${siteId}/schedule`, {
        audit_cadence: audit,
        tools: Object.entries(tools).map(([tool_id, cadence]) => ({ tool_id, cadence })),
      });
      setRows((r) => ({ ...r, [siteId]: { schedule: d, error: null, saving: false } }));
    } catch (e) {
      setRows((r) => ({ ...r, [siteId]: { ...r[siteId], error: (e as Error).message, saving: false } }));
    }
  };

  const loaded = sites.map((s) => rows[s.id]?.schedule).filter((x): x is Schedule => !!x);
  const first = loaded[0] ?? null;
  // Columns: every brief any site schedules, then any added here, in name order.
  const columns = [...new Set([...loaded.flatMap((s) => s.tools.map((t) => t.tool_id)), ...added])].sort();
  const addable = first ? first.available.map((a) => a.tool_id).filter((t) => !columns.includes(t)) : [];

  const costs = Object.fromEntries(sites.map((s) => {
    const sch = rows[s.id]?.schedule;
    return [s.id, sch ? annualCost(sch.available, toolsOf(sch)) : null];
  }));
  const priced = Object.values(costs).filter((c): c is NonNullable<typeof c> => !!c);
  const total = priced.reduce((n, c) => n + c.perYear, 0);
  const unpriced = priced.reduce((n, c) => n + c.unpriced, 0);
  const partly = priced.reduce((n, c) => n + c.partlyPriced, 0);
  const scheduled = priced.reduce((n, c) => n + c.scheduled, 0);
  const audited = loaded.filter((s) => s.audit_cadence).length;
  /** Item 179 (10-2): the totals are a statement about EVERY site, so they wait
   *  for every row to answer. Summed over the rows read so far, zero rows read
   *  "0 of 7 on a cadence · USD 0.00" and "nothing is spent unattended". */
  const answered = sites.filter((s) => rows[s.id]?.schedule || rows[s.id]?.error).length;
  const allRead = answered === sites.length;
  const unread = sites.length - loaded.length;

  return (
    <section className="cadence-grid" aria-labelledby="cadence-head">
      <h3 id="cadence-head">Cadences</h3>
      <SaveRule kind="on-change" also="explicit" />
      <p className="muted cadence-lead">
        What runs on each site without anyone asking. The whole audit costs time,
        not money; an analysis costs money every time it fires, so each row says
        what its analyses cost a year. The same fields as each site's own
        Schedule, which shows the price of every analysis and the runs it came from.
      </p>
      {!sites.length ? <p className="muted">No sites yet.</p> : (<>
      <div className="table-scroll">
        <table className="findings cadence-table">
          <thead>
            <tr>
              <th scope="col">Site</th>
              <th scope="col">Whole audit</th>
              {columns.map((t) => <th key={t} scope="col"><code>{t}</code></th>)}
              <th scope="col" className="num">A year</th>
              <th scope="col">Per site</th>
            </tr>
          </thead>
          <tbody>
            {sites.map((s) => {
              const row = rows[s.id];
              const sch = row?.schedule ?? null;
              const tools = sch ? toolsOf(sch) : {};
              const cost = costs[s.id];
              const name = `${s.client} › ${host(s.domain)}`;
              return (
                <tr key={s.id} className="cadence-row" data-site={s.id}
                    aria-busy={row?.saving || undefined}>
                  <th scope="row">{name}</th>
                  <td>
                    {sch ? (
                      <select className="input cadence-audit" value={sch.audit_cadence ?? ""}
                              aria-label={`whole-audit cadence for ${name}`}
                              disabled={row.saving}
                              onChange={(e) => put(s.id, e.target.value || null, tools)}>
                        <option value="">manual only</option>
                        {sch.audit_cadences.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    ) : <span className="muted">{row?.error ? "not read" : `${LOADING_WORD}…`}</span>}
                  </td>
                  {columns.map((t) => (
                    <td key={t}>
                      {sch && (
                        <select className="input cadence-tool" value={tools[t] ?? ""}
                                aria-label={`${t} cadence for ${name}`}
                                disabled={row.saving}
                                onChange={(e) => {
                                  const next = { ...tools };
                                  if (e.target.value) next[t] = e.target.value; else delete next[t];
                                  put(s.id, sch.audit_cadence, next);
                                }}>
                          <option value="">never</option>
                          {sch.tool_cadences.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      )}
                    </td>
                  ))}
                  <td className="num cadence-cost" data-usd={cost ? String(cost.perYear) : ""}>
                    {!cost ? "" : cost.scheduled === 0 ? <span className="muted">nothing spent</span>
                      : <>{money(cost.perYear)}
                          {cost.unpriced > 0 && (
                            <div className="muted cadence-aside">
                              + {cost.unpriced} never run here, not priced
                            </div>
                          )}</>}
                  </td>
                  <td>
                    <SecondaryButton className="cadence-open"
                            disabled={!sch}
                            onClick={() => setModal(s.id)}>
                      Schedule…<span className="sr-only"> for {name}</span>
                    </SecondaryButton>
                    <span className="muted" role="status" aria-live="polite">
                      {row?.saving ? <Working>Saving…</Working> : row?.error ? `Not saved: ${row.error}` : ""}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="cadence-total">
              <th scope="row">Every site</th>
              <td>{!allRead ? `${LOADING_WORD} ${answered} of ${sites.length} schedules…`
                   : `${audited} of ${sites.length} on a cadence`
                     + (unread ? ` · ${unread} not read` : "")}</td>
              {columns.map((t) => <td key={t} />)}
              <td className="num" data-usd={allRead ? String(total) : ""}>
                {allRead && <strong>{money(total)}</strong>}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="cadence-sum" aria-busy={!allRead}>
        {!allRead ? <span className="muted">{LOADING_WORD}…</span>
          : scheduled === 0 && unread
          ? <strong>No analyses scheduled on the {loaded.length} site{loaded.length === 1 ? "" : "s"} that
              could be read. {unread} could not be read, so this is not every site.</strong>
          : scheduled === 0
          ? <strong>No analyses scheduled on any site, so nothing is spent unattended.</strong>
          : <><strong>About {money(total)} a year across every site at these cadences.</strong>
              {partly > 0 && <span className="figure-frame"> {partly} of these
                price{partly === 1 ? "" : "s"} {partly === 1 ? "is a median" : "are medians"} over
                runs that were not all costed.</span>}
              {unpriced > 0 && <span className="muted"> Plus {unpriced} that
                {unpriced === 1 ? " has" : " have"} never run on their site, so there is no
                measured price to add.</span>}</>}
      </p>
      {addable.length > 0 && (
        <label className="cadence-add">
          Add an analysis column{" "}
          <select className="input" value="" onChange={(e) => {
            const t = e.target.value;
            if (t) setAdded((a) => [...a, t]);
          }}>
            <option value="">choose an analysis</option>
            {addable.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
      )}
      </>)}
      {modal && (
        <ScheduleModal siteId={modal}
                       onClose={() => { setModal(null); setTick((n) => n + 1); }} />
      )}
    </section>
  );
}
