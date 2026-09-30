/** The AI surface part (item 145, brief v22 steps BG and BH).
 *
 *  Reachability first, one row per AI agent grouped by class, in the operator's
 *  words: Told (what robots.txt says to it), Got (what the edge answered this
 *  audit's visit as that agent), Shown (whether the page it was given differed).
 *  Asked and Refused are the field pair, drawn only where a field source is
 *  named on the site record. Built from the run's own evidence, so it draws
 *  before any analysis has run; the brief's block adds the anchor, the entities,
 *  the register and what the client must supply. Screen words map to payload
 *  fields as Told = directive, Got = edge, Shown = served, Asked = requests,
 *  Refused = refused, and the column headers carry both. */
import { SecondaryButton } from "./buttons";
import { useState } from "react";
import { Card } from "./components";
import { Legend, ENTRIES } from "./glossary";
import { MEASURE_WORD } from "./measure";
import { Pill } from "./pill";

export type AiRow = {
  agent: string; class: string; robots_token: boolean;
  told: string; got: string; shown: string; state: string;
  declared: boolean; meaning: string;
};

export type AiNow = {
  rows: AiRow[];
  classes: Record<string, string>;
  matrix_ran: boolean;
  field_source: string | null;
  render: { median_share: number | null; pages: number; below: number; threshold: number };
  llms_txt_status: number | null;
  unmeasured: string;
};

export type AiBrief = {
  now?: {
    anchor?: Record<string, unknown>;
    entities?: { name: string; kind?: string; owned_by?: string | null; resolvable?: boolean }[];
    llms_txt?: Record<string, unknown>;
  };
  read_through?: { check: string; page: string | null; payload: unknown; scope: string }[];
  absent_reads?: { check: string; part: string; needs: string; held?: string }[];
  conflicts?: { id: string; sides?: { side: string; optimises: string; testable: string }[];
                resolved_by?: string | null; applied_by?: string | null }[];
  declined?: { item: string; reason: string; handled_at?: string }[];
  client_to_supply?: number;
  run_id?: string;
  /** Block 3, kept only when authored with the build input true (step BI). */
  llms_txt_file?: { text: string; urls: number; sections: number;
                    refused: { url: string; reason: string }[]; shape: string[] } | null;
} | null;

const CLASS_ORDER = ["dataset", "training", "index", "answer-time"];

/** The registry ids the reachability legend opens on (item 166). */
export const AI_LEGEND = ["reach-stated", "reach-edge-policy", "reach-unstated-block",
  "reach-reachable", "reach-unstated", "reach-not-assessed",
  "agent-dataset", "agent-training", "agent-index", "agent-answer-time"];

function stateKey(state: string): string {
  return state.replace(/\s+/g, "-");
}

/** The state's word as the registry draws it (item 166, 2026-09-30): the
 *  server's value is what the code compares and stores - "edge policy" -
 *  and the chip says the plain word for it, "blocked on purpose". A state
 *  the registry does not know is shown as it came. */
function stateWord(state: string): string {
  const id = `reach-${stateKey(state)}`;
  return ENTRIES.find((e) => e.id === id)?.word ?? state;
}

function StateChip({ state }: { state: string }) {
  return <span className="ai-state" data-state={stateKey(state)}>{stateWord(state)}</span>;
}

/** The site tab: every AI agent, grouped by what a block on it costs. */
export function AiReachability({ now, brief }: { now: AiNow; brief: AiBrief }) {
  const field = !!now.field_source;
  const byClass = CLASS_ORDER.map((c) => [c, now.rows.filter((r) => r.class === c)] as const);
  const unstatedBlocks = now.rows.filter((r) => r.state === "unstated block");
  const cols = field ? 5 : 4;
  return (
    <Card className="now-card ai-reach">
      <h3>Can AI crawlers reach this site?</h3>
      <Legend ids={AI_LEGEND} />
      <p className="ai-lead">
        {/* Item 180 (07-4): the counts first. "No agent is turned away" was
            drawn over 13 of 19 agents nobody had visited. */}
        {(() => {
          const notVisited = now.rows.filter((r) => stateKey(r.state) === "not-assessed").length;
          const visited = now.rows.length - notVisited;
          return `${visited} of ${now.rows.length} AI crawler${now.rows.length === 1 ? "" : "s"} measured`
            + (notVisited ? ` · ${notVisited} ${MEASURE_WORD["not-measured"]} in this audit` : "") + ". ";
        })()}
        {unstatedBlocks.length > 0
          ? `${unstatedBlocks.length} AI crawler${unstatedBlocks.length === 1 ? " is" : "s are"} turned away at the firewall with nothing said and nothing declared: ${unstatedBlocks.map((r) => r.agent).join(", ")}.`
          : now.rows.some((r) => stateKey(r.state) === "not-assessed")
          ? "Of the AI crawlers measured, none is turned away without a stated or declared reason."
          : "No AI crawler is turned away without a stated or declared reason."}
        {!now.matrix_ran && " This audit did not visit as the AI crawlers, so Got and Shown are not assessed."}
      </p>
      <div className="ai-table-wrap">
        <table className="ai-table">
          <thead>
            <tr>
              <th scope="col">AI crawler</th>
              <th scope="col">Told · Got · Shown <small className="muted">rule · firewall · served</small></th>
              {field && <th scope="col">Asked · Refused <small className="muted">requests · refused · real visits</small></th>}
              <th scope="col">Where it stands</th>
              <th scope="col">What it means</th>
            </tr>
          </thead>
          <tbody>
            {byClass.map(([cls, rows]) => rows.length === 0 ? null : [
              <tr key={`class-${cls}`} className="ai-class-row">
                <th scope="rowgroup" colSpan={cols}>
                  {cls} <small className="muted">{now.classes[cls]}</small>
                </th>
              </tr>,
              ...rows.map((r) => (
                <tr key={r.agent} data-agent={r.agent}>
                  <th scope="row">
                    {r.agent}
                    {r.robots_token && <small className="muted"> robots token, never a crawler name</small>}
                  </th>
                  <td className="ai-cells">
                    <span>{r.told}</span> · <span>{r.got}</span> · <span>{r.shown}</span>
                  </td>
                  {field && <td className="ai-cells muted">not pulled yet</td>}
                  <td><StateChip state={r.state} /></td>
                  <td className="ai-meaning">{r.meaning}</td>
                </tr>
              )),
            ])}
          </tbody>
        </table>
      </div>
      <p className="ai-note muted">
        Told, Got and Shown are what this audit found when it visited as each AI crawler, from one
        place, once: how the firewall answered that crawler name, not what the vendor's own
        crawler gets from its own addresses.
        {field
          ? ` Asked and Refused come from ${now.field_source}; nothing has been pulled from it yet.`
          : " Asked and Refused need a real-visitor data source on the site record (Admin › Sites), so they are not shown."}
      </p>
      <p className="ai-line">
        <strong>What a non-rendering reader gets:</strong>{" "}
        {now.render.median_share === null
          ? "not assessed: the rendered pass did not visit a page with enough text on this audit."
          : `a median ${Math.round(now.render.median_share * 100)}% of the rendered text is in the initial HTML, `
            + `over ${now.render.pages} rendered page${now.render.pages === 1 ? "" : "s"}; `
            + `${now.render.below} of ${now.render.pages} below ${Math.round(now.render.threshold * 100)}%.`}
      </p>
      <p className="ai-line">
        <strong>/llms.txt:</strong>{" "}
        {now.llms_txt_status === 200 ? "served" : now.llms_txt_status === null
          ? "not requested on this audit" : `absent (HTTP ${now.llms_txt_status}), which is an option, not a defect`}
      </p>
      {brief?.now?.entities && brief.now.entities.length > 0 && (
        <p className="ai-line">
          <strong>Entities:</strong>{" "}
          {`${brief.now.entities.length} recorded · ${brief.now.entities.filter((e) => e.owned_by).length} owned · `
           + `${brief.now.entities.filter((e) => e.resolvable).length} resolvable`}
        </p>
      )}
      {(brief?.client_to_supply ?? 0) > 0 && (
        <p className="ai-line">
          <strong>What the client must supply:</strong>{" "}
          {brief!.client_to_supply} value{brief!.client_to_supply === 1 ? "" : "s"} marked [client to supply] in the analysis.
        </p>
      )}
      <p className="ai-unmeasured"><strong>Not measured.</strong> {now.unmeasured}</p>
    </Card>
  );
}

/** The foot of the site tab: the brief's Conflict Register, what it declined,
 *  and the reads it could not make, each saying which absence it is. */
export function AiRegister({ brief }: { brief: AiBrief }) {
  if (!brief) return null;
  return (
    <Card className="ai-register">
      <h3>Register</h3>
      <h4>Conflicts</h4>
      <ul>
        {(brief.conflicts ?? []).map((c) => (
          <li key={c.id}>
            <strong>{c.id}</strong>:{" "}
            {(c.sides ?? []).map((s) => `${s.side} (optimises ${s.optimises}; testable ${s.testable})`).join(" versus ")}
            {c.resolved_by ? `. Resolved by ${c.resolved_by}, applied by ${c.applied_by ?? "nobody yet"}.` : ". Open: the operator chooses."}
          </li>
        ))}
      </ul>
      <h4>Declined</h4>
      <ul>
        {(brief.declined ?? []).map((d, i) => (
          <li key={i}><strong>{d.item}</strong>: {d.reason}{d.handled_at ? ` (${d.handled_at})` : ""}</li>
        ))}
      </ul>
      {(brief.absent_reads ?? []).length > 0 && (
        <>
          <h4>Reads not available</h4>
          <ul>
            {(brief.absent_reads ?? []).map((a) => (
              <li key={a.check} className="ai-absent">
                <code>{a.check}</code>: {a.needs}{a.held ? ` (held: ${a.held})` : ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

/** Block 3 as the llms.txt card: the file to copy, what it left out and
 *  why, and what it cannot claim. A convention offered as an option. */
export function AiLlmsFile({ brief }: { brief: AiBrief }) {
  const [done, setDone] = useState(false);
  const f = brief?.llms_txt_file;
  if (!f) return null;
  return (
    <Card className="ai-llms">
      <h3>/llms.txt</h3>
      <p className="ai-note">
        A community convention, not a standard: offered as an option. Nothing here claims that any
        named system reads it, and publishing it grants or denies nothing. {f.urls} URL
        {f.urls === 1 ? "" : "s"} in {f.sections} section{f.sections === 1 ? "" : "s"}, every one
        a page this audit crawled.
      </p>
      <p>
        <SecondaryButton onClick={async () => {
          await navigator.clipboard.writeText(f.text).catch(() => {});
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        }}>{done ? "copied ✓" : "copy llms.txt"}</SecondaryButton>
      </p>
      <pre className="img-markup out-new ai-llms-text" tabIndex={0}>{f.text}</pre>
      {f.refused.length > 0 && (
        <>
          <h4>Left out of the file</h4>
          <ul>{f.refused.map((r) => <li key={r.url}><code>{r.url}</code> {r.reason}</li>)}</ul>
        </>
      )}
      {f.shape.length > 0 && (
        <>
          <h4>Where it breaks the convention's shape</h4>
          <ul>{f.shape.map((x, i) => <li key={i}>{x}</li>)}</ul>
        </>
      )}
      <p className="muted ai-note">Serve it at /llms.txt with Content-Type text/plain; charset=utf-8.</p>
    </Card>
  );
}

function pathKey(url: string | null): string {
  if (!url) return "";
  try { return (new URL(url, "https://x.invalid").pathname.replace(/\/+$/, "") || "/"); }
  catch { return url; }
}

/** The page tab's read-through rows (brief v22, third addition): page-scoped
 *  reads for this page; an entity-scoped read only where this page is in its
 *  `disconnected[]`; the one site-scoped read echoed once at the foot. */
export function readsForPage(brief: AiBrief, page: string) {
  const here = pathKey(page);
  const rows = brief?.read_through ?? [];
  const pageRows = rows.filter((r) => r.scope === "page" && pathKey(r.page) === here);
  const entityRows = rows.filter((r) => {
    if (r.scope !== "entity") return false;
    const dis = ((r.payload as { disconnected?: (string | { page?: string })[] } | null)?.disconnected) ?? [];
    return dis.some((d) => pathKey(typeof d === "string" ? d : d?.page ?? "") === here);
  });
  const site = rows.filter((r) => r.scope === "site");
  return { pageRows, entityRows, site };
}

/** Page mode: the site's question asked of one URL, one row per class. */
export function AiReachabilityPage({ now, page, brief }: { now: AiNow; page: string; brief?: AiBrief }) {
  const reads = readsForPage(brief ?? null, page);
  return (
    <Card className="now-card ai-reach">
      <h3>Can AI agents reach this page?</h3>
      <Legend ids={AI_LEGEND} />
      <div className="ai-table-wrap">
        <table className="ai-table">
          <thead>
            <tr><th scope="col">Class · agents</th><th scope="col">Where they stand on this page</th></tr>
          </thead>
          <tbody>
            {CLASS_ORDER.map((cls) => {
              const rows = now.rows.filter((r) => r.class === cls);
              const states = new Map<string, string[]>();
              for (const r of rows) states.set(r.state, [...(states.get(r.state) ?? []), r.agent]);
              return (
                <tr key={cls}>
                  <th scope="row">{cls} <small className="muted">{rows.map((r) => r.agent).join(" · ")}</small></th>
                  <td>
                    {[...states.entries()].map(([state, agents]) => (
                      <span key={state} className="ai-page-state"><StateChip state={state} /> {agents.join(", ")}</span>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="ai-note muted">
        The firewall answers per request, and this audit asked as each AI crawler for the home page and two
        others; where {page} was not one of them, the site&rsquo;s answer is shown.
      </p>
      {(reads.pageRows.length + reads.entityRows.length + reads.site.length) > 0 && (
        <div className="ai-reads">
          <h4>Read through from other parts</h4>
          <ul>
            {[...reads.pageRows, ...reads.entityRows].map((r, i) => (
              <li key={i} data-read={r.check} data-scope={r.scope}>
                <code>{r.check}</code> {JSON.stringify(r.payload).slice(0, 160)}
              </li>
            ))}
          </ul>
          {reads.site.map((r, i) => (
            <p key={i} className="muted ai-note" data-read={r.check} data-scope="site">
              Site-wide: <code>{r.check}</code> {JSON.stringify(r.payload).slice(0, 160)}
            </p>
          ))}
        </div>
      )}
      <p className="ai-unmeasured"><strong>Not measured.</strong> {now.unmeasured}</p>
    </Card>
  );
}

type Candidate = { entity: string; source: string; place: string; sentence: string };

/** A fix card's body for the brief's rows: each enrichment candidate as its
 *  placed sentence, a lifted passage with its four criteria, the ID page's
 *  sections, and the JSON-LD delta beside the replacement. */
export function AiSurfaceFixBody({ fix }: { fix: { current: string; note: string; replacement: string | null;
                                                    payload?: Record<string, unknown> }; facts: unknown }) {
  const p = fix.payload ?? {};
  const candidates = (p.candidates as Candidate[] | undefined) ?? [];
  const criteria = p.criteria as Record<string, boolean> | undefined;
  const sections = (p.required_sections as { section: string; source: string; held?: string }[] | undefined) ?? [];
  const delta = p.jsonld_delta ?? p.type_delta;
  return (
    <>
      <p className="fix-why">{fix.current || fix.note}</p>
      {candidates.length > 0 && (
        <ul className="ai-candidates">
          {candidates.map((c, i) => (
            <li key={i}>
              <span className="ai-sentence">{c.sentence}</span>
              <small className="muted"> {c.entity} · {c.place} · source: {c.source}</small>
            </li>
          ))}
        </ul>
      )}
      {typeof p.passage === "string" && (
        <div className="img-panel">
          <h5 className="muted">Passage{typeof p.place === "string" ? ` · ${p.place}` : ""}</h5>
          <pre className="img-markup out-new" tabIndex={0}>{p.passage}</pre>
          {criteria && (
            <p className="muted fix-meta">
              {Object.entries(criteria).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v ? "yes" : "no"}`).join(" · ")}
            </p>
          )}
        </div>
      )}
      {sections.length > 0 && (
        <ul className="ai-candidates">
          {sections.map((s, i) => (
            <li key={i}><strong>{s.section}</strong> <small className="muted">from {s.source}</small>{s.held ? ` · ${s.held}` : ""}</li>
          ))}
        </ul>
      )}
      {delta !== undefined && (
        <div className="img-panel">
          <h5 className="muted">JSON-LD change</h5>
          <pre className="img-markup out-new" tabIndex={0}>{JSON.stringify(delta, null, 2)}</pre>
        </div>
      )}
      {fix.replacement && candidates.length === 0 && typeof p.passage !== "string" && (
        <div className="img-panel">
          <h5 className="muted">Change</h5>
          <pre className="img-markup out-new" tabIndex={0}>{fix.replacement}</pre>
        </div>
      )}
    </>
  );
}
