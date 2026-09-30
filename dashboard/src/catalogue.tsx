/** The catalogue of every brief, as a drawer that slides in from the right
 *  of the Analyse pane (brief v4 Item 3e, `_plans/site-screen-brief-v4-2026-09-03.md`).
 *
 *  One row per brief in sidebar order: part · brief · scope · default model
 *  · one estimate · state · run or re-run. The lanes it replaces stood in
 *  the pane's body with a sixteen-option model select on every row and a
 *  price beside "unpriced"; the drawer states one figure or "unpriced",
 *  never both, and the model as text - the default is Admin's, and a
 *  launch-time override was a second place to set the same thing.
 *
 *  A brief scoped to one page cannot run from here: it says "needs a page
 *  · pick a page" and the link leads to the Pages pane, where a page is a
 *  door. Triage is a row like the others (Item 3c).
 *
 *  Opened by the legend strip's control and by the floating tab on the
 *  right edge; the content under it does not move, because the drawer is
 *  fixed to the viewport. Mounted only while open, so nothing hidden is
 *  in the tab order; focus lands on its close control, and Escape closes.
 */
import { Working } from "./working";
import { NOT_READ } from "./glossary";
import { LinkButton, PrimaryButton, SecondaryButton } from "./buttons";
import { useEffect, useRef, useState } from "react";
import { Counted, makeCount } from "./population";
import { costOf } from "./cost";
import { api } from "./api";
import { AnatomyScreen, Category, rankParts } from "./anatomy";
import { Analysis, Part, price, shortModel, useAnalyses } from "./analyses";
import { Card, ErrorNote, Loading, SpendMark, money } from "./components";
import { SpendButton, SpendTarget } from "./spend";
import { ContractAccount, DerivedFigures, StoredBrief } from "./expert";
import { ReportView } from "./markdown";
import { catalogueOnlyFromHash, goHandler, hashWithout, type CatalogueOnly } from "./nav";
import { unreadParts } from "./client_lanes";
import { LookDot } from "./panels";
import { narrowPickNote } from "./api";
import { useSelection } from "./selection";
import { Pill } from "./pill";

const SCOPE_WORD: Record<string, string> = {
  site: "site", page: "one page", report: "report", monitor: "monitor", triage: "scoreboard",
};

type Row = { part: string | null; a: Analysis };

/** Every brief once, in the order the payload gives them - the sidebar's:
 *  group, then part, then name (brief v10 step AD). The part is each
 *  brief's own, from its prompt's header, so no mapping lives here.
 *  Triage writes to no part and is not in the catalogue: it ranks the rest
 *  from step 3. The client plan writes `report` and is not here either -
 *  it writes the document, not a section of the site, and its door is the
 *  Generate control on Reports (brief v18 step AY). Both part values are
 *  `briefs.PARTLESS` on the engine side; the drawer is a list of sections,
 *  so a brief belonging to none of them has no row to sit in. */
export function catalogueRows(_a: AnatomyScreen, analyses: Analysis[]): Row[] {
  return [...analyses]
    .filter((x) => x.type !== "triage" && x.part !== "none" && x.part !== "report")
    .sort((x, y) => (x.order ?? 1e9) - (y.order ?? 1e9) || x.tool.localeCompare(y.tool))
    .map((x) => ({ part: x.part_label ?? null, a: x }));
}

/** The drawer's groups: one per sidebar part in order, with its rows - and
 *  a part no brief writes to keeps its header, reading "no brief yet",
 *  rather than vanishing. */
export function catalogueGroups(parts: Part[] | undefined, rows: Row[],
                                rankOf: Map<string, number> | null = null): { part: Part; rows: Row[] }[] {
  const by = new Map<string, Row[]>();
  for (const r of rows) {
    const key = r.a.part ?? "";
    by.set(key, [...(by.get(key) ?? []), r]);
  }
  // The shop sorts by rank (brief v24 step BN): parts triage ranked and
  // placed come first in rank order, then the rest in the order they had.
  // `rankOf` is null for a ranking carried from an older audit, which is
  // shown on Audit and does not reorder the shop.
  const order = (parts ?? []).map((part, i) => ({ part, i }));
  if (rankOf) {
    order.sort((x, y) => ((rankOf.get(x.part.key) ?? Infinity) - (rankOf.get(y.part.key) ?? Infinity))
                         || (x.i - y.i));
  }
  const listed = order.map(({ part }) => ({ part, rows: by.get(part.key) ?? [] }));
  const known = new Set((parts ?? []).map((p) => p.key));
  const stray = rows.filter((r) => !known.has(r.a.part ?? ""));
  return stray.length
    ? [...listed, { part: { key: "", label: "Other", group: "", briefs: [] }, rows: stray }]
    : listed;
}

/** What the catalogue holds that has not run: every brief but triage,
 *  which ranks the rest and is not a row here. */
/** How many analyses the catalogue lists as not run — the count on the control
 *  that opens it, and it has to be the count of what opens.
 *
 *  It excluded `triage` and nothing else, so it read 24 against a catalogue
 *  listing 23: the client plan writes to no part, is not in the drawer, and is
 *  reached from Reports (audit F4). Same filter as `analyses` below, which is
 *  the list itself. */
export function notRunCount(lanes: { available: Analysis[] } | null | undefined): number | null {
  return lanes
    ? lanes.available.filter((x) => x.type !== "triage"
                                    && x.part !== "none" && x.part !== "report").length
    : null;
}

export function CatalogueFab({ a, onOpen }: { a: AnatomyScreen; onOpen: () => void }) {
  const n = notRunCount(a.lanes);
  return (
    <SecondaryButton className="catalogue-fab" onClick={onOpen}
            aria-label={`All analyses${n !== null ? ` · ${n} not run` : ""} — open the catalogue`}>
      All analyses{n !== null ? ` · ${n} not run` : ""}
    </SecondaryButton>
  );
}

/** The shop's fixed drawer. The list inside is `CatalogueList`, which
 *  Analyses will also draw as its body with no part open (brief v24 step BO;
 *  channel ruling 2026-09-15), so the two can never list different things. */
export function CatalogueDrawer({ siteId, a, onClose, ask = null, onRerun }: {
  siteId: string; a: AnatomyScreen; onClose: () => void;
  ask?: { part: string | null; n: number } | null;
  onRerun?: (key: string) => void;
}) {
  return (
    <aside className="catalogue-drawer" role="complementary" aria-label="All analyses"
           onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <CatalogueList siteId={siteId} a={a} onClose={onClose} ask={ask} onRerun={onRerun} />
    </aside>
  );
}

/** Every part and the briefs that investigate it, with run-all and its
 *  confirm. `onClose` is the drawer's; an inline shop has nothing to close. */
export function CatalogueList({ siteId, a, onClose, ask = null, onRerun }: {
  siteId: string; a: AnatomyScreen; onClose?: () => void;
  /** The re-run glyph's press, on a part header with a sweep behind it: one
   *  press to the part's refresh confirmation. The sidebar's, re-homed here
   *  because the shop is the one place that lists every part (channel
   *  ruling 2026-09-15). */
  onRerun?: (key: string) => void;
  /** Run-all's ask (brief v4 Item 3f): open on the confirm panel, scoped
   *  to a part or to everything. Counted, so one part can be asked twice. */
  ask?: { part: string | null; n: number } | null;
}) {
  const runId = a.run ?? null;
  /** Item 207: the address can narrow the list to what a landing figure
   *  counted - the parts not read, or the analyses not run - so pressing the
   *  figure shows that many things and no more. Read on every hashchange,
   *  like the page scope. */
  const [only, setOnly] = useState<CatalogueOnly>(() => catalogueOnlyFromHash(siteId));
  useEffect(() => {
    const read = () => setOnly(catalogueOnlyFromHash(siteId));
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [siteId]);
  /** The picker's run may be a nav or page scan (brief v6 step V3): every
   *  control that would run a brief against it is disabled with the
   *  server's own sentence. */
  const { runs: pickedRuns } = useSelection();
  const narrowNote = narrowPickNote(pickedRuns.find((r) => r.id === runId));
  const [tick, setTick] = useState(0);
  const { data: lanes, error: loadError } = useAnalyses(runId, tick);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<{ tool: string; name: string } | null>(null);
  const [brief, setBrief] = useState<StoredBrief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);

  const read = async (x: Analysis) => {
    if (open?.tool === x.tool) { setOpen(null); setBrief(null); return; }
    setBusy(x.tool);
    setError(null);
    try {
      const got = await api.get<StoredBrief>(`/api/runs/${runId}/expert/${x.tool}`);
      setBrief(got);
      setOpen({ tool: x.tool, name: x.name });
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(null); }
  };
  const run = async (x: Analysis) => {
    setBusy(x.tool);
    setError(null);
    try {
      await api.post(`/api/runs/${runId}/expert/${x.tool}`, {});
      setTick((t) => t + 1);
      a.bumpLanes();
      a.setTick((t) => t + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(null); }
  };

  // Every brief but triage (brief v10 step AD): the header's counts, the
  // rows and the button all count the catalogue's own population.
  // The same set `catalogueRows` lists, so the header's count and the rows
  // under it cannot disagree — the drawer is a list of sidebar sections,
  // and triage and the client plan write to none (brief v18 step AY). The
  // header counted one more than it showed the first time the plan was
  // registered, which is exactly what `test_the_drawers_numbers_agree`
  // exists to catch.
  const analyses = lanes
    ? [...lanes.ready, ...lanes.available].filter(
        (x) => x.type !== "triage" && x.part !== "none" && x.part !== "report")
    : [];
  const rows = catalogueRows(a, analyses);
  const triage = lanes?.triage ?? null;
  /** Every part's rank, stale or fresh, for the header digit; the ORDER
   *  below reads a fresh ranking only (BN). */
  const rankAll = rankParts(a.data?.categories ?? [], triage).rankOf;
  const groups = catalogueGroups(lanes?.parts, rows,
                                 triage && !triage.stale
                                   ? rankParts(a.data?.categories ?? [], triage).rankOf : null);
  /** What is DRAWN under a narrowing - only that. The header's counts and
   *  Run all keep the whole catalogue: a narrowing that changed what Run all
   *  spends on would make a view into an instruction. */
  const unread = unreadParts(a.data?.categories ?? []);
  const unreadKeys = new Set(unread.map((c) => c.key));
  /** A part counted unread with no group here should no longer exist: the
   *  unread rule counts only catalogued parts (the channel, 20260924-0220-180).
   *  If one appears, a lane is missing - worth a line in the console for
   *  whoever is building, not a sentence to the operator. */
  const listedKeys = new Set(groups.map((g) => g.part.key));
  const elsewhere: { part: Part; rows: Row[]; elsewhere?: boolean }[] = [];
  if (only === "unread") {
    for (const c of unread.filter((x) => !listedKeys.has(x.key))) {
      console.warn(`catalogue: part ${c.key} is counted unread and has no lane`);
    }
  }
  const shownGroups: { part: Part; rows: Row[]; elsewhere?: boolean }[] = !only ? groups
    : [...groups
        .map((g) => ({ ...g, rows: only === "not-run" ? g.rows.filter((r) => r.a.state !== "ready") : g.rows }))
        .filter((g) => (only === "unread" ? unreadKeys.has(g.part.key) : g.rows.length > 0)),
       ...elsewhere];
  const shownRows = shownGroups.reduce((n, g) => n + g.rows.length, 0);
  const readN = analyses.filter((x) => x.state === "ready").length;
  /** The header's numbers and the button's (brief v5 step Q): what is read,
   *  what can run now, what needs a page first. The button counts what run-all
   *  would tick - the same set as "can run now".
   *
   *  There were three, and they summed to 22 under a total of 23 (audit F4):
   *  `migration-redirects` is `needs_input`, so it is in none of the three and
   *  the reader was left to find the difference. It is the fourth now. */
  const canRunNow = analyses.filter((x) => x.state === "not_run" && x.type !== "page");
  const needPage = analyses.filter((x) => x.type === "page" && x.state !== "ready").length;
  const needsInput = analyses.filter((x) => x.type !== "page"
                                            && x.state === "needs_input").length;
  const pricedFor = (x: Analysis) =>
    Boolean(x.model && lanes?.models?.find((m) => m.model === x.model)?.price);
  /** One figure per row, and "unpriced" only where the brief's model has
   *  no price on file - a row with a priced model and no history says so
   *  instead, and the two are different remedies.
   *
   *  Led by the cost's kind since brief v17 step AV5, which is the word
   *  the part pages head their second section with. **Every row here is
   *  `model`**: the catalogue lists briefs, and the five rows carrying
   *  `kind: sweep` are the *briefs that accompany* those sweeps - each is
   *  in `EXPERT_TOOLS`, has a prompt and spends. The sweep itself runs
   *  inside the audit and is not a row at all, which is why AV5's `free`
   *  case is not written here rather than written unreachable;
   *  `tests/test_free_work_is_not_offered_for_sale.py` fails the day that
   *  stops being true. */
  const estCell = (x: Analysis) => (
    <>
      <span className="crow-kind">model</span>{" · "}
      {x.state === "ready" && x.cost != null ? money(x.cost)
       : x.est_cost_default != null ? money(x.est_cost_default)
       : pricedFor(x) ? <span className="crow-noest">no estimate yet — never run here</span>
       : <span className="crow-unpriced">unpriced — set on{" "}
           <a href="#/admin?tab=models" onClick={goHandler("#/admin?tab=models")}>Admin › Models and budgets</a>
         </span>}
    </>
  );
  const batchPriced = canRunNow.filter((x) => x.est_cost_default != null);
  // Item 180 (e6): the server's one sum, which the landing reads too; the
  // client sum is the fallback for a payload from before it.
  const batchTotal = lanes?.batch?.cost
    ?? batchPriced.reduce((s, x) => s + (x.est_cost_default as number), 0);

  /** The confirm panel (brief v4 Item 3f): one for both scopes. Each brief
   *  with its default model and its estimate at that model; page-scoped
   *  briefs unticked and not tickable, with the reason; already-read briefs
   *  unticked with a re-run tick; one total in USD at the defaults, and the
   *  wall time assuming the briefs run in parallel - the longest one. */
  const [scope, setScope] = useState<string | null | undefined>(undefined);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!ask) return;
    setScope(ask.part);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ask?.n]);
  const partOf = (tool: string) => rows.find((r) => r.a.tool === tool)?.part ?? null;
  const inScope = scope === undefined ? [] : rows.filter(
    ({ a: x }) => scope === null || x.part === scope);
  useEffect(() => {
    if (scope === undefined) return;
    setTicked(new Set(inScope.filter(({ a: x }) => x.state === "not_run" && x.type !== "page")
                             .map(({ a: x }) => x.tool)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, lanes]);
  const chosen = inScope.filter(({ a: x }) => ticked.has(x.tool));
  const priced = chosen.map(({ a: x }) => x.est_cost_default).filter((c): c is number => c != null);
  const total = priced.reduce((s, c) => s + c, 0);
  const wall = Math.max(0, ...chosen.map(({ a: x }) => x.est_seconds ?? 0));
  const scopeLabel = scope === null ? "every analysis"
    : (a.data?.categories.find((c) => c.key === scope)?.label ?? "this part");
  const commit = () => {
    a.startBatch(chosen.map(({ a: x }) => x.tool));
    setScope(undefined);
  };
  /** Item 181 (04-14): the confirm panel takes focus when it opens and gives it
   *  back to whatever opened it when it closes, by Cancel or Escape. */
  const confirmHead = useRef<HTMLHeadingElement>(null);
  const confirmFrom = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (scope === undefined) return;
    confirmFrom.current = document.activeElement as HTMLElement | null;
    confirmHead.current?.focus();
  }, [scope === undefined]);
  const closeConfirm = () => {
    setScope(undefined);
    const from = confirmFrom.current;
    if (from?.isConnected) from.focus();
  };
  // Escape closes an open report too, returning focus to its read control.
  useEffect(() => {
    if (!open) return;
    const tool = open.tool;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || document.querySelector("[role=alertdialog]")) return;
      setOpen(null); setBrief(null);
      requestAnimationFrame(() =>
        document.querySelector<HTMLElement>(`[data-read="${CSS.escape(tool)}"]`)?.focus());
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open?.tool]);
  const batchN = lanes ? analyses.filter((x) => x.type !== "page" && x.state === "not_run").length : 0;

  return (
    <>
      <div className="catalogue-head">
        <h3>
          All analyses
          {lanes && (
            <small className="muted">
              {" "}· {analyses.length} · {readN} read · {canRunNow.length} can run now
              {needPage ? ` · ${needPage} need a page` : ""}
              {needsInput ? ` · ${needsInput} need${needsInput === 1 ? "s" : ""} context a crawl cannot supply` : ""}
              {" "}· models are the defaults on{" "}
              <a href="#/admin?tab=briefs" onClick={goHandler("#/admin?tab=briefs")}>Admin › Analysis defaults</a>
            </small>
          )}
        </h3>
        <span className="catalogue-acts">
          {lanes && batchN > 0 && (
            <PrimaryButton className="run-all"
                    disabled={Boolean(narrowNote)} title={narrowNote ?? undefined}
                    aria-expanded={scope === null} onClick={() => setScope(null)}>
              Run all {batchN}
              {batchPriced.length ? ` · ${money(batchTotal)}` : " · unpriced"}
              {batchPriced.length < batchN
                ? ` (${batchPriced.length} priced, ${batchN - batchPriced.length} unpriced)` : ""}
            </PrimaryButton>
          )}
          {/* The same chip the legend strip carries (brief v17 step
              AV4). **Every row of this drawer is analysis** - it is a
              catalogue of briefs, and a brief is the only thing in the
              app that spends a model - so `free only` empties it rather
              than filtering it. Said in one line instead of leaving a
              table that looks broken. */}
          <button type="button" className="chip cost-chip"
                  aria-pressed={a.cost === "free"}
                  title="Every row here is a paid analysis. With this on, the catalogue says so rather than listing work you have asked not to see."
                  onClick={() => a.setCost(a.cost === "free" ? "" : "free")}>
            free only
          </button>
          {onClose && (
            <SecondaryButton ref={closeRef} onClick={onClose}>close ×</SecondaryButton>
          )}
        </span>
      </div>
      {narrowNote && <p className="muted narrow-pick-note" role="note">{narrowNote}</p>}
      {a.batchError && <ErrorNote error={a.batchError} />}
      {scope !== undefined && lanes && (
        <div className="batch-confirm" role="group" aria-label="confirm the batch"
             onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); closeConfirm(); } }}>
          <h4 tabIndex={-1} ref={confirmHead}>
            Run {chosen.length} analys{chosen.length === 1 ? "is" : "es"} against this audit
            <span className="muted"> · {scopeLabel} · confirm</span>
          </h4>
          <table className="findings batch-table">
            <thead><tr><th /><th>Analysis</th><th>Model</th><th>Est.</th><th>Note</th></tr></thead>
            <tbody>
              {inScope.map(({ a: x }) => {
                const pageScoped = x.type === "page";
                const read = x.state === "ready";
                const runnable = !pageScoped && (x.state === "not_run" || read);
                return (
                  <tr key={x.tool} className={`batch-row${ticked.has(x.tool) ? " is-ticked" : ""}`}>
                    <td>
                      <input type="checkbox" className="batch-tick"
                             aria-label={`${x.name} in this batch`}
                             checked={ticked.has(x.tool)} disabled={!runnable}
                             onChange={(e) => setTicked((t) => {
                               const next = new Set(t);
                               if (e.target.checked) next.add(x.tool); else next.delete(x.tool);
                               return next;
                             })} />
                    </td>
                    <td>{x.name} <code className="muted">{x.tool}</code></td>
                    <td className="muted">{x.model ? shortModel(x.model) : "—"}</td>
                    <td className="muted crow-est">{estCell(x)}</td>
                    <td className="muted batch-note">
                      {pageScoped ? <span className="crow-page">one page — narrow first; not in this batch</span>
                        : read ? `already read ${x.ran_at?.slice(0, 10) ?? ""} · tick to re-run`
                        : x.state === "needs_input" ? "needs context a crawl cannot supply"
                        : x.state === "running" ? "running now" : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="batch-foot">
            <b className="batch-total">
              {chosen.length} will run · {priced.length ? money(total) : "unpriced"}
              {priced.length ? ` from ${priced.length} priced row${priced.length === 1 ? "" : "s"}` : ""}
              {priced.length < chosen.length ? ` · ${chosen.length - priced.length} unpriced` : ""}
              {" · in parallel"}{wall ? ` · ~${Math.ceil(wall / 60)} min` : ""}
            </b>
            <span className="muted">
              at the per-analysis defaults, priced {Math.round((lanes.input_share ?? 0.9) * 100)}% as input —
              change them on{" "}
              <a href="#/admin?tab=briefs" onClick={goHandler("#/admin?tab=briefs")}>Admin › Analysis defaults</a>
            </span>
            <PrimaryButton className="batch-commit"
                    disabled={!chosen.length || Boolean(narrowNote)} title={narrowNote ?? undefined}
                    onClick={commit}>
              <SpendMark />Run {chosen.length}
            </PrimaryButton>
            <SecondaryButton onClick={closeConfirm}>Cancel</SecondaryButton>
          </div>
        </div>
      )}
      {/* Item 179: the empty answer only once the audit list has answered
          empty; until then, and until the lanes arrive, the registered word. */}
      {!runId && a.headReady && <p className="muted">No completed audit yet — analyses read one.</p>}
      {!lanes && !loadError && (runId || !a.headReady) && <Loading what="the analyses" />}
      {loadError && <ErrorNote error={loadError} />}
      {error && <ErrorNote error={error} />}
      {lanes && a.cost === "free" && (
        <p className="muted catalogue-folded">
          Every row here is a paid analysis — {analyses.length} here, {canRunNow.length} that
          could run now. <code>free only</code> is on, so none of them are listed.
        </p>
      )}
      {/* The part headers stay under `free only`, and only the brief rows
          fold: the shop is how every part is reached (brief v24 step BO), a
          filter must not take that away, and the header is where the free /
          analysis split is said. */}
      {lanes && only && (
        <p className="muted catalogue-only">
          {only === "unread"
            ? `Showing only the ${shownGroups.length} part${shownGroups.length === 1 ? "" : "s"} not read on this audit.`
            : `Showing only the ${shownRows} analys${shownRows === 1 ? "is" : "es"} not run.`}{" "}
          <a href={hashWithout(["only"])} onClick={goHandler(hashWithout(["only"]))}>Show every part</a>
        </p>
      )}
      {lanes && (
        <table className="findings catalogue-table">
          <thead>
            <tr><th>Part</th><th>Analysis</th><th>Scope</th><th>Default model</th>
                <th>Est.</th><th>State</th><th /></tr>
          </thead>
          <tbody>
            {shownGroups.map(({ part: grp, rows: inPart, elsewhere: notHere }) => [
              <tr key={`part-${grp.key}`} className="crow-part">
                <th colSpan={7} scope="rowgroup">
                  {/* The shop reaches every part, a clean one included (brief
                      v24 step BO: the sidebar's job "reach a part with
                      nothing open" lands here), with the part's open count
                      carrying its population (155). */}
                  {/* Triage's digit, a dash for a part it did not name,
                      nothing before any ranking exists: the sidebar's rank
                      column, on the header of the list that is sorted by it
                      (channel ruling 2026-09-15, item 4). */}
                  {triage && grp.key && (
                    <span className={`anat-rank${rankAll.get(grp.key) == null ? " anat-rank-none" : ""}`}>
                      {rankAll.get(grp.key) ?? "–"}
                    </span>
                  )}
                  {grp.key ? (
                    <a className="crow-part-link"
                       href={`#/sites/${siteId}?tab=findings&part=${encodeURIComponent(grp.key)}`}
                       onClick={goHandler(`#/sites/${siteId}?tab=findings&part=${encodeURIComponent(grp.key)}`)}>
                      {grp.label}
                    </a>
                  ) : grp.label}
                  {(() => {
                    const cat = a.data?.categories.find((c) => c.key === grp.key);
                    if (!cat) return null;
                    // While `free only` is on, the count is what free work
                    // found and what analysis added is said beside it (brief
                    // v17 step AV4; ruling item 5). "+0 analysis" would be
                    // furniture, so a part with nothing paid says nothing.
                    const split = splitByCost(cat);
                    const state = cat.tools.some((t) => a.queued.includes(t)) || cat.analysing?.length
                      ? "live" : cat.analysed_by?.length ? "read" : "none";
                    return (
                      <>
                        <span className="muted crow-part-open">
                          {" · "}<Counted count={a.cost ? makeCount(split.free, "record") : cat.total}
                                          pops={a.data?.populations ?? null} /> open
                          {/* Item 180 (e2): a 0 carries what is waiting to be confirmed. */}
                          {!a.cost && (cat.seen_once?.value ?? 0) > 0 && (
                            <> · <Counted count={cat.seen_once!} pops={a.data?.populations ?? null} /> seen once</>
                          )}
                        </span>
                        {a.cost && split.model > 0 && (
                          <span className="muted sb-model"
                                title={`${split.model} more here, raised by an analysis`}>
                            {" "}+{split.model} analysis
                          </span>
                        )}
                        {" "}
                        {/* Read and running, where briefs are read (ruling
                            item 3). */}
                        <LookDot state={state}
                                 label={state === "live"
                                          ? `${(cat.analysing?.length ? cat.analysing : ["an analysis"]).join(", ")} is running now`
                                        : state === "read" ? `Analysed by ${cat.analysed_by!.join(", ")}`
                                        : "No analysis has run against this part"} />
                      </>
                    );
                  })()}
                  {/* NOT the unread state, and briefly drawn as it: audit F14
                      listed this beside the three rivals of `not read`, and
                      `not read` is wrong here. This group has no rows because
                      NO analysis writes to this part - there is nothing to
                      read, now or later - where `not read` means an analysis
                      exists and nothing has run it. Two states, two
                      sentences. */}
                  {inPart.length === 0 && !notHere && (
                    <span className="muted crow-nobrief"> · no analysis covers this part</span>
                  )}
                  {notHere && (
                    <span className="muted crow-nobrief"> · its analyses are not run from the catalogue</span>
                  )}
                  {onRerun && a.data?.categories.find((c) => c.key === grp.key)?.refresh && (
                    // Item 183: the free re-check, in its registered word.
                    <SecondaryButton className="anat-rerun"
                            aria-label={`Re-check ${grp.label}`} onClick={() => onRerun(grp.key)}>
                      ↻<span className="sr-only"> Re-check</span>
                    </SecondaryButton>
                  )}
                </th>
              </tr>,
              ...(a.cost === "free" ? [] : inPart).map(({ part, a: x }) => {
              const pageScoped = x.type === "page";
              const state = x.state === "ready" ? "read"
                : x.state === "running" || a.queued.includes(x.tool) ? "live" : "none";
              return (
                <RowGroup key={x.tool}
                          open={open?.tool === x.tool}
                          report={open?.tool === x.tool ? (
                            <Card>
                              <div className="modal-head">
                                <h4>{open.name}</h4>
                                <SecondaryButton
                                        onClick={() => { setOpen(null); setBrief(null); }}>close</SecondaryButton>
                              </div>
                              {brief?.report
                                ? <>
                                    <DerivedFigures figures={brief.figures_to_verify}
                                                    flagged={brief.figures_flagged} />
                                    <ContractAccount contract={brief.contract} />
                                    <ReportView source={brief.report} runId={runId ?? undefined} />
                                  </>
                                : <p className="muted">This report was not retained.</p>}
                            </Card>
                          ) : null}>
                  <tr className={`crow crow-${state}`}>
                    <td className="muted">{part ?? "—"}</td>
                    <td><span className="crow-name">{x.name}</span> <code className="muted">{x.tool}</code></td>
                    <td className={pageScoped ? "crow-page" : "muted"}>{SCOPE_WORD[x.type] ?? x.type}</td>
                    <td className="muted">
                      {x.model ? shortModel(x.model) : "—"}{" "}
                      <a className="crow-override" href="#/admin?tab=briefs"
                         onClick={goHandler("#/admin?tab=briefs")}>override</a>
                    </td>
                    <td className="muted crow-est">{estCell(x)}</td>
                    <td>
                      <LookDot state={state} />{" "}
                      {x.state === "ready"
                        ? `read ${x.ran_at?.slice(0, 10) ?? ""}`
                        : x.state === "running" || a.queued.includes(x.tool) ? "running now"
                        : x.state === "needs_input" && x.questions?.length
                          ? <span className="crow-asked" title={x.questions.join(" / ")}>
                              asked instead of answering: {x.questions[0]}
                            </span>
                        : x.state === "needs_input" ? "needs context a crawl cannot supply"
                        : pageScoped ? <span className="muted">needs a page</span> : NOT_READ}
                    </td>
                    <td className="crow-act">
                      {pageScoped && x.state !== "ready" ? (
                        <LinkButton href={`#/sites/${siteId}?tab=pages`}
                           onClick={goHandler(`#/sites/${siteId}?tab=pages`)}>pick a page</LinkButton>
                      ) : x.state === "ready" ? (<>
                        {/* Item 181 (04-14): busy, not disabled - a disabled
                            button drops focus to the body mid-press. */}
                        <SecondaryButton data-read={x.tool}
                                aria-busy={busy === x.tool}
                                onClick={() => { if (busy !== x.tool) read(x); }}>
                          {open?.tool === x.tool ? "close" : "read"}
                        </SecondaryButton>{" "}
                        {/* Item 178: priced on the control, held with its reason in
                            text, confirmed. */}
                        <SpendButton price={x.est_cost ?? x.est_cost_default ?? null}
                                     busy={busy === x.tool}
                                     why={narrowNote ? "this audit is too narrow for it" : null}
                                     confirm={{ title: `Re-run ${x.name}?`,
                                                body: <><SpendTarget />
                                            <p>{x.does}</p></>,
                                                action: `Re-run ${x.name}` }}
                                     onSpend={() => run(x)}>
                          re-run
                        </SpendButton>
                      </>) : x.state === "not_run" ? (
                        <SpendButton price={x.est_cost ?? x.est_cost_default ?? null}
                                     busy={busy === x.tool}
                                     why={narrowNote ? "this audit is too narrow for it" : null}
                                     confirm={{ title: `Run ${x.name}?`,
                                                body: <><SpendTarget />
                                            <p>{x.does}</p></>,
                                                action: `Run ${x.name}` }}
                                     onSpend={() => run(x)}>
                          run
                        </SpendButton>
                      ) : <span className="muted">{x.verb}</span>}
                      <span className="muted" role="status" aria-live="polite">
                        {busy === x.tool && <Working>working…</Working>}
                      </span>
                    </td>
                  </tr>
                </RowGroup>
              );
              }),
            ])}
          </tbody>
        </table>
      )}
    </>
  );
}

/** A row and, when its report is open, the report beneath it. */
function RowGroup({ children, open, report }: {
  children: React.ReactNode; open: boolean; report: React.ReactNode;
}) {
  return (
    <>
      {children}
      {open && report && (
        <tr className="crow-report"><td colSpan={7}>{report}</td></tr>
      )}
    </>
  );
}

/** What free work found in a part, and what analysis added (brief v17 step
 *  AV4). Counted off the same findings the count counts, so the two numbers
 *  cannot drift from the one they replace. Moved from the sidebar with its
 *  badge (brief v24 step BO). */
export function splitByCost(c: Category): { free: number; model: number } {
  const model = c.findings.filter(
    (f) => costOf(c, `${f.dimension}/${f.check_id}`) === "model").length;
  // `.value`: the three findings counts carry their population since item
  // 156, and this is arithmetic over them rather than a render of one.
  return { free: c.total.value - model, model };
}
