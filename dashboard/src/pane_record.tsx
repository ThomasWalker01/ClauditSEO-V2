/** The Record pane: every finding this site has ever had, grouped by check.
 *
 *  Brief step 8 (CQ-02): `SiteDetailView` was ~1,000 lines holding every
 *  pane's body; this is the Record's, moved verbatim, with the state that is
 *  the pane's own. What the address decides - the state filter, the
 *  grouping, how many rows are shown - stays with the screen in `views.tsx`
 *  and arrives as props, so a stored link still lands on the filter it
 *  names and a site change still resets what it reset. */
import { Working } from "./working";
import { SecondaryButton } from "./buttons";
import { sourceWord } from "./glossary";
import { Legend } from "./glossary";
import { Dispatch, ReactNode, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, FindingState, Severity, SiteDetail, crawledPaths,
         isCoverageNote, latestSiteWideCrawl, SOURCES_NOTE } from "./api";
import { ErrorNote, Loading, SeverityTag, UrlLinks } from "./components";
import { checkCost } from "./cost";
import { WriteBrief, plainName } from "./part_page";
import { narrowStates } from "./anatomy";
import { goHandler, hashWithout, pageScopeFromHash, recordNarrowFromHash } from "./nav";
import { stamp } from "./client_lanes";
import { FixCol, FixState, FixTick, MarkBar, StateNote, useFixLoop } from "./fixloop";
import { Pill } from "./pill";
import { coverageNotes } from "./population";
import { DangerButton } from "./spend";

/** Rows revealed at a time in the full findings table. */
export const PAGE = 50;

type FixLoop = ReturnType<typeof useFixLoop>;

export function RecordPane({ siteId, data, fix, fState, onState, group, onGroup,
                             shown, setShown, setTick, part = null, onClearPart,
                             parts = [], partKey = "", onPart,
                             gonePaths, cost = "", onCost, costs = {},
                             runId = null }: {
  siteId: string;
  data: SiteDetail;
  fix: FixLoop;
  /** The state filter, the grouping and the page size are the address's
   *  (`?state=`, `?group=`) and are set through the screen, which also
   *  remembers them per site. */
  fState: string;
  onState: (state: string) => void;
  group: string;
  onGroup: (group: string) => void;
  shown: number;
  setShown: Dispatch<SetStateAction<number>>;
  setTick: Dispatch<SetStateAction<number>>;
  /** The sidebar's part filter (brief v4 Item 3a): the record narrowed to
   *  the checks the part's findings raise. By check id, so a finding of
   *  that check in any state is kept; the anatomy names the part's checks
   *  from what is open in it now, which is what the sidebar counts. */
  part?: { label: string; checks: Set<string> } | null;
  onClearPart?: () => void;
  /** Every part, for the Record's own part select (brief v24 step BO;
   *  channel ruling 2026-09-15): the sidebar set this filter, and with the
   *  sidebar retired the Record carries the control. `partKey` is the
   *  address's `?part=`, which stays the source of truth. */
  parts?: { key: string; label: string; open: number }[];
  partKey?: string;
  onPart?: (key: string) => void;
  /** What each check costs to answer, and which of the two the operator
   *  has asked for (brief v17 step AV4). The address's, like `?state=`,
   *  so a link into the record carries the argument it was making. The
   *  map is the anatomy's - one answer per check for the whole app. */
  cost?: string;
  onCost?: (cost: string) => void;
  costs?: Record<string, string>;
  /** The audit a generated brief would be written from (brief v17 step
   *  AX). Absent on a site with no completed run, and the control is
   *  then not offered rather than offered and refused. */
  runId?: string | null;
  /** Pages the prior precheck published and the newest does not (brief v4
   *  Item 2): gone, whatever the latest crawl fetched - a sitemap removal
   *  outranks the crawl-scope heuristic. Paths, as `crawled_paths` are. */
  gonePaths?: Set<string>;
}) {
  /** The page scope, from the address (item 164), read on every hashchange
   *  the way BK's `useAnatomy` reads it. The record is narrowed ONCE, here,
   *  and every read below takes `states`: the chips, the groups, "N findings
   *  on N pages", "on pages not in latest crawl" and the "X of Y" count. In
   *  page mode the pane had shown the whole site's rows under a chip saying
   *  `narrowed to /` - 62 title and description findings for one page. */
  const [page, setPage] = useState(() => pageScopeFromHash(siteId));
  const [narrow, setNarrow] = useState(() => recordNarrowFromHash(siteId));
  useEffect(() => {
    const read = () => { setPage(pageScopeFromHash(siteId)); setNarrow(recordNarrowFromHash(siteId)); };
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [siteId]);
  /** Item 207: one audit's findings, when the address names the audit. The
   *  landing's hold counts ONE run's open Critical and High; the record is
   *  every audit's, so without this the figure opened 102 rows for a count
   *  of 7. Fetched as fingerprints alone - `/api/runs/{id}` is 1.7 MB. */
  const [runFps, setRunFps] = useState<{ run: string; fps: Set<string> } | null>(null);
  const [runErr, setRunErr] = useState<string | null>(null);
  useEffect(() => {
    setRunErr(null);
    if (!narrow.run) { setRunFps(null); return; }
    let live = true;
    api.get<{ fingerprints: string[] }>(`/api/runs/${narrow.run}/fingerprints`)
      .then((got) => { if (live) setRunFps({ run: narrow.run, fps: new Set(got.fingerprints) }); })
      .catch((e) => { if (live) setRunErr((e as Error).message); });
    return () => { live = false; };
  }, [narrow.run]);
  const runLoading = Boolean(narrow.run) && !runErr && runFps?.run !== narrow.run;
  /** Narrowed to the audit only once its fingerprints are in hand, and to
   *  nothing while they load: every audit's rows under a chip naming one
   *  audit would be the wrong answer drawn as the right one. On a failure
   *  the narrowing is dropped and said to be. */
  const states = useMemo(() => {
    const base = narrowStates(data?.states ?? [], page);
    if (!narrow.run || runErr) return base;
    if (runFps?.run !== narrow.run) return [];
    return base.filter((s) => runFps.fps.has(s.fingerprint));
  }, [data?.states, page, narrow.run, runFps, runErr]);
  /** Several severities at once since item 207, so a link can say "Critical
   *  or High" by pressing both chips rather than by a word no registry holds
   *  (item 166). Empty is "Any severity". A chip press is still one. */
  const [fSevs, setFSevs] = useState<string[]>(() => recordNarrowFromHash(siteId).sev);
  /** Applied when the address's `sev=` CHANGES, not on every hashchange:
   *  leaving the audit narrowing keeps `sev=` in the address, and re-applying
   *  it then would undo a chip the reader had pressed since. */
  const sevKey = narrow.sev.join(",");
  const appliedSev = useRef(sevKey);
  useEffect(() => {
    if (sevKey === appliedSev.current) return;
    appliedSev.current = sevKey;
    if (sevKey) { setFSevs(sevKey.split(",")); setShown(PAGE); }
  }, [sevKey, setShown]);
  const raisedBy = narrow.run ? data.runs.find((r) => r.id === narrow.run) : undefined;
  const runWhen = narrow.run
    ? [raisedBy?.tier, stamp(raisedBy?.started_at)].filter(Boolean).join(" · ")
      || narrow.run.slice(0, 8)
    : "";
  const [fText, setFText] = useState("");
  /** Brief v2 step B. A finding on a page the latest site-wide crawl did
   *  not fetch carries a marker. The crawl is `latestSiteWideCrawl`, never
   *  a navigation-scoped scan: a page merely outside a small scan's scope
   *  is not gone, and calling it so was the `/apply` contradiction (WF-04).
   *  Paths, because that is what the run stores; a finding naming no page
   *  is never marked. */
  const latestCrawl = latestSiteWideCrawl(data.runs);
  const fetched = new Set(latestCrawl ? crawledPaths(latestCrawl) : []);
  const pathOfUrl = (u: string) => {
    try { const x = new URL(u); return x.pathname + x.search; } catch { return u; }
  };
  const goneFrom = (s: FindingState): string[] =>
    s.affected_urls.filter((u) => /^https?:/.test(u)
      && ((latestCrawl && !fetched.has(pathOfUrl(u)))
          || (gonePaths?.has(pathOfUrl(u).replace(/\/$/, "") || "/") ?? false)));
  /** Grouped by check by default (brief step 6, UX-01): the record was
   *  1,060 flat instance rows with two buttons each on the operator's own
   *  site, and the same check on 41 pages read as 41 problems. `expanded`
   *  is the groups opened to their instances; `groupAsk` is a group-level
   *  verb awaiting its confirmation - one at a time, because a press that
   *  moves forty findings deserves a second press. */
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [groupAsk, setGroupAsk] = useState<{ key: string; to: string; label: string;
                                             fps: string[] } | null>(null);
  const [groupBusy, setGroupBusy] = useState<string | null>(null);
  /** The record's own verbs, in flight and failed (WF-95).
   *
   *  Keyed on fingerprint rather than a single boolean, because the verbs sit
   *  on every row of a table: one flag would grey out fifty buttons to say
   *  one of them was working. `verbErr` is a single value on purpose — the
   *  note renders once above the table, and two simultaneous failures on one
   *  table are a case nobody has, whereas two rows disabled at once is a case
   *  a fast clicker has immediately.
   */
  const [verbBusy, setVerbBusy] = useState<Record<string, boolean>>({});
  const [verbErr, setVerbErr] = useState<string | null>(null);
  /** A group holding a marked finding opens on its own: a mark is the
   *  operator's work in progress, and the fix loop is one loop across the
   *  panes - a tick made on Analyses is on the Record without a re-read,
   *  and a collapsed group would have hidden it. The operator can still
   *  collapse it afterwards. */
  useEffect(() => {
    if (!states.length || !fix.marked.size) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const st of states) {
        if (fix.marked.has(st.fingerprint)) next.add(`${st.dimension}/${st.check_id}`);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [fix.marked, states]);
  const needle = fText.trim().toLowerCase();
  /** The record's rows cut by check (brief step 6): one group per
   *  `dimension/check_id` in the filtered rows, in the order the rows
   *  come, with the worst severity, the pages the group's findings name,
   *  and its rows. Computed from the filtered rows, so the filters cut
   *  groups and the count under them agrees with the table. */
  type Group = { key: string; dimension: string; check_id: string;
                 severity: FindingState["severity"]; rows: FindingState[];
                 pages: number; states: Record<string, number> };
  const groupsOf = (rows: FindingState[]): Group[] => {
    const order: Severity[] = ["critical", "high", "medium", "low", "info"];
    const by = new Map<string, Group>();
    for (const r of rows) {
      const key = `${r.dimension}/${r.check_id}`;
      let g = by.get(key);
      if (!g) {
        g = { key, dimension: r.dimension, check_id: r.check_id,
              severity: r.severity, rows: [], pages: 0, states: {} };
        by.set(key, g);
      }
      g.rows.push(r);
      if (order.indexOf(r.severity) < order.indexOf(g.severity)) g.severity = r.severity;
      g.states[r.state] = (g.states[r.state] ?? 0) + 1;
    }
    for (const g of by.values()) {
      g.pages = new Set(g.rows.flatMap((r) => r.affected_urls)).size;
    }
    return [...by.values()];
  };
  /** A coverage note says what the audit could not measure - CWV without
   *  a key, backlinks without a provider, the sitemap on a T1 scan, axe's
   *  sample - and is not a finding about the site (brief v2 step F,
   *  UX-09). It stood among findings with accept/withdraw ×N beside it. It
   *  is listed in its own strip, with no verb. */
  /* The predicate moved to `api.ts` (2026-09-18): this pane had it and the
     part page needed it and had nothing, so a note was a finding there.
     The third-party-scripts clause retired with those ids (0054). */
  // `noteRows`, not `coverageNotes`: the words for the count are
  // `population.tsx`'s one spelling of them, and a list of rows named after
  // that function read as if it were it.
  const noteRows = states.filter(isCoverageNote);
  /** Every state row that is not a coverage note, within the part.
   *
   *  Item 201 reverses what this comment used to say - "counted before the
   *  severity and text filters, so a chip says what the set holds, not what
   *  the other filters left of it". The operator, on twenty22: "analysis
   *  shows 15 as a number but nothing is present when filtered". Every one of
   *  the 15 was `candidate`, and "Open + regressed" was pressed, so the chip
   *  promised rows its press could not show. A chip's number is now the
   *  number of rows the table shows when it is pressed, the other rows'
   *  filters as they stand: each row of chips counts within the OTHER rows'
   *  selection (below, `forState`, `forSev`, `forCost`), never its own. */
  /** Within the part filter (brief v5 step S): the part is a scope, as
   *  the sidebar's badge is, so the chips say what the part holds and the
   *  "Open + regressed" chip is the badge's own number. */
  const findings = states.filter((s) => !isCoverageNote(s)
                                              && (!part || part.checks.has(s.check_id)));
  /** Brief v17 step AV4. `free` and `analysis` are one filter with two
   *  faces rather than two toggles: a row is one or the other, so a
   *  record showing both is the record with no filter on at all - which
   *  is what pressing the pressed one gives back. */
  const costOfRow = (s: FindingState) => checkCost(costs, `${s.dimension}/${s.check_id}`);
  const COST_CHIPS: [string, string][] = [["free", "free"], ["model", "analysis"]];
  const inCost = (s: FindingState) => !cost || costOfRow(s) === cost;
  /** Item 237: an analysis finding on a check no sweep can raise, waiting
   *  for the operator - not for a second audit, which is not confirmation. */
  const awaiting = (s: FindingState) => s.state === "candidate" && costOfRow(s) === "model";
  /** The record opens on this (item 237): what is outstanding AND what waits
   *  for the operator, so a brief-only finding is seen without a press. Its
   *  own chip rather than widening "Open + regressed", which the landing's
   *  counts open exactly (item 207) and which keeps "open" meaning one thing. */
  const STATE_CHIPS: [string, string, (s: FindingState) => boolean][] = [
    ["attention", "Open + regressed + to confirm",
     (s) => s.state === "open" || s.state === "regressed" || awaiting(s)],
    ["outstanding", "Open + regressed", (s) => s.state === "open" || s.state === "regressed"],
    ["to-confirm", "To confirm", awaiting],
    ["fixed", "Fixed", (s) => s.state === "fixed"],
    ["accepted-risk", "Accepted", (s) => s.state === "accepted-risk"],
    ["withdrawn", "Withdrawn", (s) => s.state === "withdrawn"],
    ["candidate", "Seen once", (s) => s.state === "candidate"],
    ["gone", "On pages gone", (s) => goneFrom(s).length > 0],
    ["all", "Every state", () => true],
  ];
  /** The notes under the same state filter as the rows, so a figure that
   *  counts them - the standing position's "outstanding" counts every
   *  state row the server holds - is met by rows plus notes on this pane. */
  const inState = (s: FindingState) => {
    // One rule per chip, the chip's own (item 237 added two); an address
    // value with no chip - `open`, `regressed` - is the state itself.
    const chip = STATE_CHIPS.find(([v]) => v === fState);
    return chip ? chip[2](s) : s.state === fState;
  };
  const coverageShown = noteRows.filter(inState);
  /** The group's headline is the check, never its first instance's
   *  sentence (brief v2 step F, UX-08): "Heading level jumps H1→H4 on
   *  /blog/attention-brokers…" was the headline of a 227-page group. The
   *  product has no catalogue of check descriptions on the wire - the
   *  brief's "catalogue string" does not exist - so the headline is the
   *  check's id said as words, and the count line under it says the rest. */
  // Item 183: the same words the part pages use for a check, one source.
  const headlineOf = (checkId: string) => plainName(checkId);
  const inSev = (s: FindingState) => !fSevs.length || fSevs.includes(s.severity);
  const inText = (s: FindingState) => !needle
    || `${s.dimension}/${s.check_id} ${s.summary}`.toLowerCase().includes(needle);
  const stateRows = findings.filter((s) => inCost(s) && inState(s) && inSev(s) && inText(s));
  // Item 201: what each row of chips counts over - everything the table
  // applies except that row's own filter.
  const forState = findings.filter((s) => inCost(s) && inSev(s) && inText(s));
  const forSev = findings.filter((s) => inCost(s) && inState(s) && inText(s));
  const forCost = findings.filter((s) => inState(s) && inSev(s) && inText(s));
  return (
    <>
      <h3>The whole record</h3>
      <p className="muted">
        Every finding this site has ever had, in whatever state it reached,
        one row per check with its findings beneath.{" "}
        <details className="record-what">
          <summary>what is here</summary>
          <strong>Analyses</strong> shows only what is still open, cut by the
          part of the page it belongs to; this is the history behind it,
          filterable and searchable — or flat, one row per finding. The tick
          and the verify are the same ones as there — mark here, verify here,
          and the mark shows up on both. What is only here is the ability to
          accept a risk. Candidates are model findings seen once: they open
          when a second audit confirms them, and are dropped if it does not -
          except where no automatic check can raise the finding at all. Those
          are "to confirm": they wait for you to confirm, accept or withdraw
          them on the part page, because a second run is not confirmation.
          Coverage notes — what an audit could not measure — are listed
          under the table, and are not findings.
        </details>
      </p>
      {/* Filtered and paged. Unfiltered this table was 41,034px tall — 94%
          of the whole page — and a tab that merely hid it would have left a
          table nobody could reach the bottom of. */}
      {/* Filters as chips with their counts (brief v3 step L, UX-13): every
          set is one press, and the press says how many it reaches. "Seen
          once" is not among them - which audit first saw a finding is a
          field the record does not carry, and the brief asks for it to be
          reported rather than guessed. The chips are the address's
          `?state=` values, so a stored link and a press mean the same. */}
      <Legend ids={["outstanding", "state-open", "state-regressed", "state-fixed", "state-accepted",
                    "state-withdrawn", "state-candidate", "to-confirm", "on-pages-gone"]} />
      <div className="filters state-filters" role="group" aria-label="state filter">
        {STATE_CHIPS.map(([value, label, test]) => {
          const n = forState.filter(test).length;
          return (
            <button key={value} type="button" className="chip" data-state={value}
                    aria-pressed={fState === value} onClick={() => onState(value)}>
              {label} <Pill tone="count-info">{n}</Pill>
            </button>
          );
        })}
      </div>
      <div className="filters severity-filters" role="group" aria-label="severity filter">
        {["all", "critical", "high", "medium", "low", "info"].map((v) => {
          const n = v === "all" ? forSev.length : forSev.filter((s) => s.severity === v).length;
          // Hidden only where the severity has no row ANYWHERE (item 201): a
          // chip whose count the other filters took to 0 is information, and
          // a pressed one that vanished could not be unpressed.
          if (v !== "all" && !findings.some((s) => s.severity === v)) return null;
          return (
            <button key={v} type="button" className="chip" data-severity={v}
                    aria-pressed={v === "all" ? !fSevs.length : fSevs.includes(v)}
                    onClick={() => { setFSevs(v === "all" ? [] : [v]); setShown(PAGE); }}>
              {v === "all" ? "Any severity" : v} <Pill tone="count-info">{n}</Pill>
            </button>
          );
        })}
      </div>
      {/* What a finding cost to find (brief v17 step AV4): the same
          filter the legend strip's `free only` chip sets, offered here
          with both faces because the Record is where an operator answers
          "what did the model actually give us for the money". */}
      {onCost && (
        <div className="filters cost-filters" role="group" aria-label="cost filter">
          {COST_CHIPS.map(([value, label]) => {
            const n = forCost.filter((s) => costOfRow(s) === value).length;
            return (
              <button key={value} type="button" className="chip" data-cost={value}
                      aria-pressed={cost === value}
                      onClick={() => { onCost(cost === value ? "" : value); setShown(PAGE); }}>
                {label} <Pill tone="count-info">{n}</Pill>
              </button>
            );
          })}
        </div>
      )}
      <div className="filters record-shape">
        {/* Item 207: the audit the address narrowed to, named and removable
            where the part is. A link, because the narrowing is the address's
            and Back should put it back. */}
        {narrow.run && !runErr && (
          <a className="chip run-chip" href={hashWithout(["raised"])}
             onClick={goHandler(hashWithout(["raised"]))}
             aria-label={`narrowed to the findings raised by audit ${runWhen} — press to show every audit`}>
            raised by audit {runWhen} ×
          </a>
        )}
        {runLoading && <Loading what="the findings that audit raised" />}
        {runErr && (
          <ErrorNote error={`Could not read which findings that audit raised, so every audit is shown: ${runErr}`} />
        )}
        {part && (
          <button type="button" className="chip part-chip" aria-pressed="true"
                  aria-label={`filtered to ${part.label} — press to clear`}
                  onClick={onClearPart}>
            {part.label} ×
          </button>
        )}
        {/* A select, not a chip row: the one filter here with more values
            than a row of chips can hold. The chips rule stands for the
            others. */}
        {onPart && parts.length > 0 && (
          <select value={partKey} aria-label="Part" className="part-select"
                  onChange={(e) => onPart(e.target.value)}>
            <option value="">All parts</option>
            {parts.map((p) => (
              <option key={p.key} value={p.key}>{p.label} · {p.open} open</option>
            ))}
          </select>
        )}
        <input value={fText} placeholder="filter by check or text…"
               aria-label="text filter"
               onChange={(e) => { setFText(e.target.value); setShown(PAGE); }} />
        <select value={group} aria-label="group by"
                onChange={(e) => onGroup(e.target.value)}>
          <option value="check">group by check</option>
          <option value="none">every finding</option>
        </select>
        <span className="muted">
          {(group === "check"
            ? `${groupsOf(stateRows).length} check${groupsOf(stateRows).length === 1 ? "" : "s"}`
              + ` · ${stateRows.length} finding${stateRows.length === 1 ? "" : "s"}`
            : stateRows.length + coverageShown.length === states.length
              ? `${stateRows.length} findings`
              : `${stateRows.length} of ${states.length - noteRows.length}`)
            /* The Record's claim is not the landing's: these notes ARE in the
               list below, so the noun is shared and the predicate is not. */
            + (coverageShown.length ? ` · ${coverageNotes(coverageShown.length)}` : "")}
        </span>
      </div>
      {/* Scoped to what the filters are showing, because that is the list
          the bar sits above — the same rule as the per-category bar on
          Current. */}
      {(() => {
        const visible = group === "check"
          ? groupsOf(stateRows).slice(0, shown).flatMap((g) => g.rows)
          : stateRows.slice(0, shown);
        const mine = visible.filter((s) => fix.marked.has(s.fingerprint));
        const here = mine.map((s) => s.fingerprint);
        // Same count as the per-category bar on Current, from this screen's
        // own field name — the two must not report different totals for the
        // same marks.
        const pages = new Set(mine.flatMap((s) => s.affected_urls)).size;
        return (
          <MarkBar here={here} pages={pages}
                   extra={<span className="muted">
                     The same page-scoped run the re-audit drawer offers from a
                     finding: it re-crawls the pages behind the marked findings
                     and nothing else.
                   </span>}
                   pageCap={data.verify_page_cap}
                   elsewhere={fix.marked.size - here.length}
                   outcome={fix.outcome} verifying={fix.verifying}
                   onVerify={() => fix.verify(here)}
                   onClear={() => fix.clear(here)} />
        );
      })()}
      {fix.error && <ErrorNote error={fix.error} />}
      {/* WF-95. Above the table rather than in the row, because the row the
          press failed on may not be on screen once the table re-reads, and a
          message that can scroll out of existence is the failure being
          swallowed again by a slower mechanism.

          UX-82's placement half, answered as Q-8 on 2026-08-24: the note
          stays here and `bringIntoView` brings the operator to it. `PAGE` is
          50, so a verb pressed on row 40 painted its only report above a fold
          the operator had scrolled past — the `role="alert"` this component
          gained at `18d7122` told a screen reader and told the sighted
          operator nothing. The alternative the finding's wording suggests,
          moving the note into the row, was put to the operator and not
          chosen: it reverses the paragraph above. */}
      {verbErr && <ErrorNote error={verbErr} bringIntoView />}
      {/* Scrolls inside its own box at narrow widths (WCAG 1.4.10): at 320px
          the six columns overflowed the pane by 14px and the document by
          two, which the reflow sweep could not see until it measured this
          pane (second audit of 2026-09-02, F-26). */}
      <div className="table-scroll">
      <table className="findings">
        {/* Two columns, two different questions. The tick is the fix loop,
            shared with Current: I have fixed this, look again. Risk is
            records management — this is known, stop raising it — and it is
            only offered here because this is the only screen that shows an
            accepted finding at all.
            Marking a fix belongs on Current, beside the verify that judges
            it: two places to mark meant two vocabularies for one mechanism
            ("attempted, still present" here against "still there" there),
            and a mark made here could not be acted on because the verify
            button is over there.

            The marking was removed from here once, to kill a second
            vocabulary for one mechanism ("attempted, still present" here
            against "still there" there) and a mark that could not be acted
            on because the verify button was on the other screen. Sharing the
            component fixes both without losing the capability. */}
        <thead><tr><FixCol />
            <th>State</th><th>Severity</th><th>Check</th><th>Summary</th>
            <th>Risk</th></tr></thead>
        <tbody>
          {(() => {
            /* One renderer for an instance row, used by both shapes. */
            const instance = (s: FindingState) => (
            <tr key={s.fingerprint}
                className={fix.marked.has(s.fingerprint) ? "marked" : ""}>
              <td className="fix-col">
                <FixTick f={s} marked={fix.marked} onMark={fix.mark} />
              </td>
              {/* The stored state, then what the loop makes of it. They are
                  not the same sentence: a row can be open in the record and
                  awaiting a look in the loop. */}
              <td>
                <Pill tone={s.state === "accepted-risk" ? "state-accepted" : `state-${s.state}`}>{s.state}</Pill>
                {/* The state's own meaning, where the state is listed. The
                    filter above offers `withdrawn` and `candidate` as things
                    to narrow to, and until this line the word arrived here
                    with no account of itself on any input device — not even
                    a `title` to hover (UX-43). Only the three states that
                    take a finding *out* of the counts render one; the rest
                    are named by their chip and explain themselves. */}
                <StateNote state={s.state} />
                {(fix.marked.has(s.fingerprint) || s.attempted_at
                  || fix.outcome[s.fingerprint]) && (
                  <div className="rec-loop">
                    <FixState f={s} marked={fix.marked} outcome={fix.outcome}
                              judged={fix.judged} />
                  </div>
                )}
              </td>
              {/* The chip, not the bare word. This one cell rendered
                  severity as plain text while every other table on every
                  other screen used the shared tag — so "critical" here was
                  black body copy beside a red pill there, on the same
                  finding. */}
              <td><SeverityTag severity={s.severity} /></td>
              <td>
                <code>{s.dimension}/{s.check_id}</code>
                {/* The source as a tag on the instance (brief v10 step
                    AF), never as a prefix on the check id. */}
                <Pill tone={`source-${s.source_word ?? (s.source === "model-judgement" ? "brief" : "sweep")}`}
                      title={SOURCES_NOTE}>
                                    {sourceWord(s.source_word ?? (s.source === "model-judgement" ? "brief" : "sweep"))}
                </Pill>
              </td>
              <td>
                {s.summary} <UrlLinks urls={s.affected_urls} />
                {s.proposed && (
                  <div className="muted rec proposed">
                    proposed: {s.proposed}
                  </div>
                )}
                {goneFrom(s).length > 0 && (
                  <div className="page-gone">
                    page not in latest crawl
                    {latestCrawl?.started_at
                      ? ` (${latestCrawl.started_at.slice(0, 10)}, ${latestCrawl.tier})` : ""}
                    {goneFrom(s).length > 1 ? ` — ${goneFrom(s).length} of its pages` : ""}
                  </div>
                )}
              </td>
              <td>
                {/* Every verb this cell offers, decided in one table.

                    It was two hand-written branches — `accept risk` and
                    `withdraw` on open-or-regressed, `reopen` on the two
                    operator states — and what a branch per case cannot say is
                    which cases it left out. `fixed` was left out (WF-61): a
                    run marks a finding fixed when it is absent from a later
                    run, and absence is not a repair. On the operator's own
                    install 2 of the 18 `fixed` rows are `cwv-not-assessed`
                    and `sitemap-coverage-not-assessed` — scope limitations
                    that went away because the second run did not measure them
                    either — and nothing in the product could take one back.

                    That figure read 13 until CQ-189, and the correction is
                    worth more than the number. 13 is real and comes from a
                    different query: joining every historical `findings` row
                    to a `fixed` state gives 36 rows, of which those two
                    checks are 9 and 4. The sentence paired a numerator over
                    `findings` with a denominator over `finding_states`. Both
                    counts here are over `finding_states` rows, one per
                    fingerprint, which is the population the screen paints —
                    `SELECT COUNT(*) FROM finding_states WHERE state='fixed'`
                    for the 18.

                    CQ-195: the 2 was stated here as "the same restricted to
                    those two check ids", and that query cannot be run.
                    `finding_states` is `site_id, fingerprint, state,
                    changed_by_run, updated_at, attempted_at, attempt_note` —
                    there is no `check_id`, and the restriction as written
                    raises `no such column: check_id`. Written out in full,
                    the 2 is that same row set narrowed by a correlated
                    subquery, not a join:

                        SELECT COUNT(*) FROM finding_states s
                         WHERE s.state='fixed' AND EXISTS (
                           SELECT 1 FROM findings f
                            WHERE f.fingerprint = s.fingerprint
                              AND f.check_id IN ('cwv-not-assessed',
                                                 'sitemap-coverage-not-assessed'))

                    Correlated because `findings` holds one row per run: a
                    plain join multiplies each fingerprint by how many runs
                    raised it, which is exactly the 9-and-4 inflation above.
                    Both forms are executed against a two-run fixture by
                    `tests/test_site_level_tick.py`'s
                    `test_the_derivation_stated_beside_the_fixed_count_can_be_run`,
                    which asserts they disagree — so this method cannot go
                    stale again without the suite saying so.

                    The argument does not depend on the size and never did:
                    one clearance the product cannot take back is the case,
                    and there are two.

                    The verbs are not interchangeable and the table is where
                    that shows. `accept risk` asserts the finding is present
                    and you will live with it, so it is offered only where it
                    is present. `withdraw` asserts it was never true, which
                    can be said of a finding in any state — including one a
                    run called fixed on an absence it never rechecked.
                    `reopen` puts it back in the count. `candidate` gets none
                    of them, deliberately: a finding seen once is not yet
                    treated as a fact, so there is nothing to accept, retract
                    or restore until a second run confirms it.

                    `withdrawn` returns to `open` and not to `fixed` because
                    nothing was ever repaired — migration 0023's own
                    transition rule for a later run that sees the finding
                    again, applied to the operator who withdrew it by mistake.

                    Every verb carries a `why`, and the line this replaced
                    said the opposite (UX-81). It read "no `title` on the two
                    verbs added here, deliberately", on the ground that what a
                    state means is owned once by `STATE_MEANING` in
                    `fixloop.tsx`. That ownership is real and is untouched —
                    but `StateNote` renders only for the three states in that
                    table, and `withdraw` is offered on `open` and `regressed`,
                    which are not among them. So the one control that retracts
                    a finding from a client's record was offered with no
                    account of itself anywhere, beside `accept risk` with one,
                    on all 45 open and 5 regressed rows of a real site.

                    The two are not the same sentence and must not become it.
                    `STATE_MEANING` says what it means for a finding to BE in
                    a state; a `why` here says what PRESSING THIS does to the
                    record — which is why `accept risk`'s has always been a
                    verb description rather than a paraphrase of its state's.
                    `test_dashboard_a11y.py` holds the line between them: it
                    parses `STATE_MEANING`'s sentences out of their owner and
                    fails any `title` under `dashboard/src` sharing four
                    consecutive words with one. */}
                {[
                  { to: "accepted-risk", label: "accept risk",
                    from: ["open", "regressed"],
                    why: "Known and accepted: stops this re-alarming every "
                         + "run. The operator's call, never changed "
                         + "automatically." },
                  { to: "withdrawn", label: "withdraw",
                    from: ["open", "regressed", "fixed", "accepted-risk"],
                    why: "Retracts the finding: it was never true, so this is "
                         + "not a repair and nothing gets credit for one. A "
                         + "run that sees it again puts it back." },
                  { to: "open", label: "reopen",
                    from: ["fixed", "accepted-risk", "withdrawn"],
                    why: "Puts the finding back among the ones counted "
                         + "against this site, and back in front of the next "
                         + "run." },
                ].filter((v) => v.from.includes(s.state)).map((v) => {
                  const act = async () => {
                            setVerbBusy((b) =>
                              ({ ...b, [s.fingerprint]: true }));
                            setVerbErr(null);
                            try {
                              await api.post(
                                `/api/sites/${siteId}/states/${s.fingerprint}`,
                                { state: v.to });
                              setTick((t) => t + 1);
                            } catch (e) {
                              // WF-95's other half. The route now 404s a write
                              // it did not make; before this catch the
                              // rejection was swallowed, the tick bumped
                              // anyway, and the table re-read and looked
                              // unchanged — which is what a refused write and
                              // a successful one both looked like.
                              setVerbErr(
                                `${v.label} on ${s.dimension}/${s.check_id}`
                                + ` failed: ${(e as ApiError).message}`);
                            } finally {
                              setVerbBusy((b) =>
                                ({ ...b, [s.fingerprint]: false }));
                            }
                  };
                  // Item 178 (04-3): withdrawing and accepting risk take a finding
                  // out of the client's count, so each asks first, in the danger
                  // tone, with its consequence in text - as the group verbs do.
                  // Reopen puts one back, and stays a plain press.
                  return v.to === "open" ? (
                    <SecondaryButton key={v.to} title={v.why}
                          disabled={!!verbBusy[s.fingerprint]} onClick={act}>
                      {v.label}
                    </SecondaryButton>
                  ) : (
                    <DangerButton key={v.to} busy={!!verbBusy[s.fingerprint]} title={v.why}
                                  label={`${v.label}: ${s.dimension}/${s.check_id}`}
                                  confirm={{ title: `${v.label[0].toUpperCase()}${v.label.slice(1)} this finding?`,
                                             body: <><p><code>{s.dimension}/{s.check_id}</code>
                                               {s.affected_urls[0] ? <> on {s.affected_urls[0]}</> : null}</p>
                                               <p>{v.why}</p>
                                               <p className="muted">Reopen puts it back.</p></>,
                                             action: `${v.label[0].toUpperCase()}${v.label.slice(1)}`,
                                             undone: false }}
                                  onConfirm={act}>
                      {v.label}
                    </DangerButton>
                  );
                })}
                {/* The generator's second door (brief v17 step AX). The
                    part page has the other; the two ways an operator
                    arrives at "this page needs writing" are reading the
                    part and reading the record, and only one of them was
                    reachable. Offered on a Content row with a page,
                    because a brief is written for a page - a finding that
                    names none has nothing to write about. */}
                {runId && s.dimension === "CNT" && (s.affected_urls[0] || "") && (
                  <WriteBrief runId={runId} page={s.affected_urls[0]} />
                )}
              </td>
            </tr>
            );
            if (group !== "check") return stateRows.slice(0, shown).map(instance);

            /* Grouped (brief step 6): a row per check, its instances
               beneath on expand, and the verbs at the group level with a
               second press before anything moves. */
            const VERBS = [
              { to: "accepted-risk", label: "accept risk", from: ["open", "regressed"] },
              { to: "withdrawn", label: "withdraw",
                from: ["open", "regressed", "fixed", "accepted-risk"] },
            ];
            const commit = async (ask: NonNullable<typeof groupAsk>) => {
              setGroupBusy(ask.key);
              setVerbErr(null);
              try {
                for (const fp of ask.fps) {
                  await api.post(`/api/sites/${siteId}/states/${fp}`, { state: ask.to });
                }
                setGroupAsk(null);
                setTick((t) => t + 1);
              } catch (e) {
                setVerbErr(`${ask.label} on ${ask.key} failed part way: `
                           + `${(e as ApiError).message}. The rows it reached are `
                           + "moved; the rest are not - reload to see which.");
              } finally {
                setGroupBusy(null);
              }
            };
            return groupsOf(stateRows).slice(0, shown).flatMap((g) => {
              const open = expanded.has(g.key);
              const states = Object.entries(g.states)
                .map(([k, n]) => `${n} ${k}`).join(" · ");
              const rows: ReactNode[] = [
                <tr key={g.key} className="group-row">
                  <td className="fix-col">
                    <SecondaryButton className="group-toggle"
                            aria-expanded={open}
                            aria-label={`${open ? "collapse" : "expand"} ${g.key}`}
                            onClick={() => setExpanded((prev) => {
                              const next = new Set(prev);
                              if (!next.delete(g.key)) next.add(g.key);
                              return next;
                            })}>
                      {open ? "−" : "+"}
                    </SecondaryButton>
                  </td>
                  <td><span className="muted group-states">{states}</span></td>
                  <td><SeverityTag severity={g.severity} /></td>
                  <td><code>{g.key}</code></td>
                  <td>
                    <span className="group-headline">{headlineOf(g.check_id)}</span>
                    <div className="muted group-n">
                      {g.rows.length} finding{g.rows.length === 1 ? "" : "s"}
                      {g.pages ? ` on ${g.pages} page${g.pages === 1 ? "" : "s"}` : ""}
                      {/* A duplicate check's groups (brief v11 step AH):
                          one row per page, so the groups are counted here. */}
                      {(() => {
                        const groups = new Set(g.rows.map((r) => r.group).filter(Boolean));
                        return groups.size
                          ? <> · {groups.size} group{groups.size === 1 ? "" : "s"}</>
                          : null;
                      })()}
                      {/* Both sources on one line (brief v10 step AF). */}
                      {(() => {
                        const n = { sweep: 0, brief: 0 };
                        for (const r of g.rows) n[r.source_word ?? (r.source === "model-judgement" ? "brief" : "sweep")] += 1;
                        return n.sweep && n.brief
                          ? <> · <span className="group-sources" title={SOURCES_NOTE}>{sourceWord("sweep")} {n.sweep} · {sourceWord("brief")} {n.brief}</span></>
                          : null;
                      })()}
                      {(() => {
                        const gone = g.rows.filter((r) => goneFrom(r).length).length;
                        return gone ? <> · <span className="page-gone">{gone} on pages not in latest crawl</span></> : null;
                      })()}
                    </div>
                  </td>
                  <td>
                    {/* The verbs that move every finding under the check, behind
                        the row's overflow (brief v2 step F, UI-04): at equal
                        weight on every row they were the easiest thing on the
                        table to press. */}
                    {(() => {
                      const offered = VERBS.map((verb) => ({
                        verb,
                        fps: g.rows.filter((r) => verb.from.includes(r.state))
                                   .map((r) => r.fingerprint),
                      })).filter((o) => o.fps.length);
                      if (!offered.length) return null;
                      return (
                        <details className="row-more">
                          <summary aria-label={`actions for ${g.key}`}>⋯</summary>
                          {offered.map(({ verb, fps }) => (
                            <SecondaryButton key={verb.to}
                                    disabled={groupBusy !== null}
                                    onClick={() => setGroupAsk({ key: g.key, to: verb.to,
                                                                 label: verb.label, fps })}>
                              {verb.label} ×{fps.length}
                            </SecondaryButton>
                          ))}
                        </details>
                      );
                    })()}
                  </td>
                </tr>,
              ];
              if (groupAsk?.key === g.key) {
                rows.push(
                  <tr key={`${g.key}:ask`} className="group-confirm">
                    <td colSpan={6}>
                      <strong>{groupAsk.label} on {groupAsk.fps.length} finding
                      {groupAsk.fps.length === 1 ? "" : "s"} under {g.key}?</strong>{" "}
                      One request per finding, in order; an audit that sees a
                      withdrawn finding again puts it back.{" "}
                      {/* UX-66's shape: a stable caption, the state on
                          `aria-busy`, the busy words in the region beside. */}
                      <SecondaryButton
                              disabled={groupBusy !== null}
                              aria-busy={groupBusy === g.key}
                              onClick={() => commit(groupAsk)}>
                        yes, {groupAsk.label}
                      </SecondaryButton>{" "}
                      <span className="muted" role="status" aria-live="polite">
                        {groupBusy === g.key
                          && <Working>{`Moving ${groupAsk.fps.length} finding${groupAsk.fps.length === 1 ? "" : "s"}…`}</Working>}
                      </span>{" "}
                      <SecondaryButton
                              disabled={groupBusy !== null}
                              onClick={() => setGroupAsk(null)}>
                        cancel
                      </SecondaryButton>
                    </td>
                  </tr>);
              }
              if (open) rows.push(...g.rows.map(instance));
              return rows;
            });
          })()}
        </tbody>
      </table>
      </div>
      {coverageShown.length > 0 && (
        <details className="coverage-notes">
          <summary>
            Coverage notes — not findings ({coverageShown.length}): what this
            audit could not measure
          </summary>
          <ul>
            {coverageShown.map((s) => (
              <li key={s.fingerprint}>
                <Pill tone={s.state === "accepted-risk" ? "state-accepted" : `state-${s.state}`}>{s.state}</Pill>{" "}
                <code>{s.dimension}/{s.check_id}</code> {s.summary}
              </li>
            ))}
          </ul>
        </details>
      )}
      {(() => {
        const total = group === "check" ? groupsOf(stateRows).length : stateRows.length;
        const unit = group === "check" ? "checks" : "findings";
        return total > shown && (
          <p className="muted">
            <SecondaryButton onClick={() => setShown((n) => n + PAGE)}>
              show {Math.min(PAGE, total - shown)} more
            </SecondaryButton>{" "}
            {total - shown} {unit} still hidden of {total}.
          </p>
        );
      })()}
    </>
  );
}
