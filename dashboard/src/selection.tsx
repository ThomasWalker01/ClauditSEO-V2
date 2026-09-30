/**
 * Which client, site and audit run the operator is currently looking at.
 *
 * This used to be a 156px card at the top of the Tools screen, and nothing
 * else in the app knew about it: opening Tools, then Clients, then Tools
 * again re-picked the first site in the list. Selection is context, not page
 * content, so it lives once, in the header, and every screen reads it.
 *
 * The run matters as much as the site. A brief reads *stored crawl evidence*,
 * so "which audit" is part of the question being asked, not a detail of how
 * it gets answered — which is why it sits in the bar rather than inside a
 * tool's own controls.
 */
import { stamp } from "./client_lanes";
import { LinkButton, SecondaryButton } from "./buttons";
import {
  ReactNode, createContext, useContext, useEffect, useState,
} from "react";
import { RunStatus, api, completedAudits, hasScore, isNarrowScope, scopeOf, scopeWord } from "./api";
import { LOADING_WORD } from "./glossary";
import { goto } from "./nav";
import { Pill } from "./pill";

export type Site = { id: string; domain: string; client: string };
export type Run = { id: string; status: RunStatus; composite_score: number | null;
                    started_at: string; has_evidence?: boolean;
                    /** When the run ended (`list_runs` selects every column).
                     *  The landing's "finished 7 hours ago" reads it (item
                     *  168, the landing says one thing). */
                    finished_at?: string | null;
                    /** "audit" or "verify" — only an audit may be selected as
                     *  the run a screen describes. */
                    kind: string;
                    /** What the run was, for the label (brief v3 step I), and
                     *  the server's classification (brief v6 step V2). */
                    scan_scope?: string | null; crawled_paths?: string | null;
                    effective_scope?: string | null; site_reading?: boolean;
                    /** The tier, for the label (brief v5 step P). */
                    tier?: string };

type Selection = {
  sites: Site[];
  site?: Site;
  siteId: string;
  setSiteId: (id: string) => void;
  runs: Run[];
  runId: string;
  setRunId: (id: string) => void;
  /** Whether `runs` and `runId` are the CURRENT site's (item 179). Until the
   *  site's audit list has answered they are empty - never the previous
   *  site's - and a reader says "Loading…", not "no completed audit": the
   *  audit found Tools still pointing at the last site's audit, with "Run all"
   *  live, for 14 s after a switch (09-2), and every client route calling an
   *  audited site unaudited while the list was in flight (01-4, 11-1). */
  runsReady: boolean;
  /** Why `runs` is empty, when it is empty because the read failed rather
   *  than because nothing has run. Swallowed until audit F-14: a 500 on the
   *  bar's own fetch painted "no completed audit" on a site with three, and
   *  nothing on screen offered a way back. `refreshRuns` clears it. */
  runsError: string | null;
  /** Bumped when a run is created or finishes, so the bar re-reads. */
  refreshRuns: () => void;
  /** Called by whatever creates a site, so the picker offers it without a
   *  reload. Every screen that picks a target reads this one list. */
  refreshSites: () => void;
};

const Ctx = createContext<Selection | null>(null);

/** Survives a reload. The operator works one client at a time for an hour;
 *  losing the selection on every refresh was the single most repeated
 *  annoyance in this UI. */
const KEY = "clauditseo:site";
//: The pre-rename key was carried over for one release. That is done; the
//: worst case for anyone missed is that the client picker starts empty.
const remembered = () => {
  try {
    return localStorage.getItem(KEY) || "";
  } catch { return ""; }
};
const remember = (id: string) => { try { localStorage.setItem(KEY, id); }
                                   catch { /* private mode: not worth failing over */ } };

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [sites, setSites] = useState<Site[]>([]);
  const [siteId, setSiteIdRaw] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState("");
  /** The site `runs` were read for: the target-ownership check. */
  const [runsFor, setRunsFor] = useState<string | null>(null);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // Its own tick rather than sharing the runs one: a run is created far more
  // often than a site is, and every creation would have re-fetched a list
  // that had not changed.
  const [siteTick, setSiteTick] = useState(0);

  const setSiteId = (id: string) => {
    setSiteIdRaw(id);
    remember(id);
    // On a site route the URL names the site, and the effect below reads it
    // back. Without moving the URL too, picking a different site was undone
    // a beat later by that effect and the control snapped back — switching
    // was impossible from the screens most likely to want it.
    //
    // The tail is kept, so switching from Launch audit lands on the new
    // site's Launch audit rather than dropping you somewhere else. The first
    // version matched only the bare `#/sites/<id>`, which meant switching
    // from a sub-route was silently ignored — and, worse, would have left
    // the identity line naming one site while the page acted on another.
    const [path, query] = (window.location.hash || "").split("?");
    const m = /^#\/sites\/[^/]+(\/.*)?$/.exec(path);
    if (m) {
      // A run id in the query belongs to the site being left behind.
      const keep = new URLSearchParams(query || "");
      keep.delete("run");
      // And the pane (plan §4c): the site screen lands by its own rule,
      // and a kept `?tab=` would land site B on the pane site A was on.
      keep.delete("tab");
      // And the record's filter, which names a state site A was looking at.
      keep.delete("state");
      const tail = keep.toString();
      goto(`#/sites/${id}${m[1] ?? ""}${tail ? `?${tail}` : ""}`);
    }
  };

  // Re-read on demand, not only on mount. This fetched once with an empty
  // dependency array for the app's whole life, so a site created after the
  // tab was opened was invisible to every screen that picks a target until a
  // reload: the operator added a client, went to Tools to audit it, and Home
  // showed three sites while the picker offered two.
  useEffect(() => {
    let live = true;
    api.get<Site[]>("/api/sites").then((s) => {
      if (!live) return;
      setSites(s);
      // Choosing is for the first load and for a selection that has gone
      // away. On a re-fetch the operator has usually navigated since, and
      // re-applying the remembered id here would drag them back — the same
      // rule the runs effect below states as "keep the operator's pick
      // across a refresh".
      setSiteIdRaw((cur) => {
        if (cur && s.some((x) => x.id === cur)) return cur;
        const prior = remembered();
        // Fall back rather than clear: a remembered site that has since been
        // deleted should not leave the app with no selection at all.
        return s.some((x) => x.id === prior) ? prior : (s[0]?.id ?? "");
      });
    }).catch(() => { /* views surface their own errors */ });
    return () => { live = false; };
  }, [siteTick]);

  // Only completed runs carry evidence a brief can read, so an in-progress or
  // failed run is never offered as a target.
  //
  // Nor is a verification. It re-crawls the handful of pages behind some
  // ticked findings and stores no expert reports, so selecting one showed
  // "Ready to read · 0" on a site holding eight — and since the newest run is
  // usually a verification, that was the default view. The rule is the same
  // one `lastJudgingRun` applies to the fix loop: an audit looks at
  // everything, a verification looks at what it was asked about.
  useEffect(() => {
    if (!siteId) { setRuns([]); setRunId(""); return; }
    let live = true;
    api.get<{ runs?: Run[] }>(`/api/sites/${siteId}`)
      .then((s) => {
        if (!live) return;
        setRunsError(null);
        const usable = completedAudits(s.runs);
        setRuns(usable);
        setRunsFor(siteId);
        // Keep the operator's pick across a refresh; otherwise the newest
        // run that read the site (brief v5 step P, WF-09): a nav or page
        // scan is listed but never the default, since the standing counts
        // and the sidebar read from the pick and a one-page scan wore the
        // site's name on the operator's own screen.
        setRunId((cur) => (usable.some((r) => r.id === cur) ? cur
                                                            : defaultRun(usable)?.id ?? ""));
      })
      .catch((e: Error) => {
        if (live) { setRuns([]); setRunId(""); setRunsError(e.message); setRunsFor(siteId); }
      });
    return () => { live = false; };
  }, [siteId, tick]);

  // The route can name the site it is about: `#/sites/<id>`. It no longer
  // names an audit (item 239 step 5): `run=` is the Audits tab's history
  // view's alone, read there, and ignored everywhere else.
  useEffect(() => {
    const apply = () => {
      const [path] = (window.location.hash || "").split("?");
      const site = /^#\/sites\/([^/?]+)/.exec(path)?.[1];
      if (site && site !== siteId) setSiteIdRaw(site);
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [siteId]);

  // Target ownership (item 179): nothing reads a previous site's audit list or
  // pick as this site's. `runId` is also refused when it is not one of the
  // current site's audits - a `?run=` naming another site's audit included.
  const runsReady = Boolean(siteId) && runsFor === siteId;
  const ownRuns = runsReady ? runs : [];
  const ownRunId = runsReady && ownRuns.some((r) => r.id === runId) ? runId : "";
  const value: Selection = {
    sites, siteId, setSiteId, runs: ownRuns, runId: ownRunId, setRunId, runsError,
    runsReady,
    site: sites.find((s) => s.id === siteId),
    refreshRuns: () => setTick((t) => t + 1),
    refreshSites: () => setSiteTick((t) => t + 1),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelection(): Selection {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSelection outside SelectionProvider");
  return v;
}

/** How a site's domain is written on screen, everywhere it is written.
 *
 *  Exported for `components.tsx`'s `PriceScopeNote` (CQ-198), which names the
 *  site a brief price was measured on. A second stripper there would be one
 *  more place for `https://www.acme.com.au/` and `www.acme.com.au` to be
 *  the same site under two spellings on one screen. */
export const host = (domain: string) => domain.replace(/^https?:\/\//, "").replace(/\/$/, "");
const day = (iso: string) => (iso || "").slice(0, 10);

/** The newest run that read the site; failing one, the newest run at all. */
export function defaultRun(usable: Run[]): Run | undefined {
  return usable.find((r) => !isNarrowScope(scopeOf(r))) ?? usable[0];
}

/** One label for a run wherever it is picked (brief v5 step P): when, to
 *  the minute, so two runs of one day differ; the tier; the scope; the
 *  score. `(latest)` marks the newest, which is not always the default. */
/** The chosen audit's name where the bar has no room for `runLabel` (item
 *  174): its tier and its score, or its day where it has no score. */
export function runShortLabel(r: Run): string {
  const score = hasScore(r.status) && r.composite_score != null ? String(r.composite_score) : null;
  return [r.tier || null, score ?? day(r.started_at)].filter(Boolean).join(" · ");
}

export function runLabel(r: Run, i: number): string {
  const when = stamp(r.started_at);
  const scope = scopeOf(r);
  const score = hasScore(r.status) && r.composite_score != null ? ` · ${r.composite_score}` : "";
  return `${when || day(r.started_at)}${r.tier ? ` · ${r.tier}` : ""}`
    + ` · ${scope ? scopeWord(scope) : "scope unknown"}${score}${i === 0 ? " (latest)" : ""}`;
}

/** Which site everything is about, and the way to change it.
 *
 *  It shows the current selection rather than a placeholder. The earlier
 *  version stayed empty so it would not repeat an identity line elsewhere on
 *  the page — but Tools and Home have no such line, so on those screens
 *  nothing on screen said whose site you were looking at. One control that
 *  both states the selection and changes it is fewer things than a label
 *  plus a switcher, and it cannot disagree with itself.
 *
 *  A native input + datalist rather than a hand-built combobox: the browser
 *  supplies filtering, keyboard handling and screen-reader semantics, all
 *  easy to get subtly wrong and hard to notice without testing.
 */
export function SiteSearch() {
  const { sites, siteId, setSiteId, site } = useSelection();
  const [typing, setTyping] = useState<string | null>(null);
  const id = "site-search-list";
  const label = (s: Site) => `${s.client} › ${host(s.domain)}`;
  const current = site ? label(site) : "";

  const commit = (value: string) => {
    const match = sites.find((s) => label(s) === value)
      // Typed but not picked from the list: match any distinctive part, so
      // "roofing" finds it without typing the full breadcrumb.
      ?? sites.find((s) => label(s).toLowerCase().includes(value.toLowerCase().trim()));
    if (match && match.id !== siteId) {
      setSiteId(match.id);
      setTyping(null);
      return true;
    }
    return false;
  };

  if (!sites.length) return null;
  return (
    <label className="globalsearch">
      <span className="gs-label">Working on</span>
      <input className="input gs-input" list={id}
             // While typing the field is the query; otherwise it is the
             // answer. Abandoning a search must restore the selection, not
             // leave a half-typed name looking like the current site.
             value={typing ?? current}
             aria-label="Current client and site — type to switch"
             onFocus={(e) => { setTyping(""); e.currentTarget.select(); }}
             onBlur={() => setTyping(null)}
             onChange={(e) => { setTyping(e.target.value); commit(e.target.value); }}
             onKeyDown={(e) => {
               if (e.key === "Enter" && commit(typing ?? "")) e.currentTarget.blur();
               if (e.key === "Escape") { setTyping(null); e.currentTarget.blur(); }
             }} />
      <datalist id={id}>
        {sites.map((s) => <option key={s.id} value={label(s)} />)}
      </datalist>
    </label>
  );
}

/** The selects themselves, unframed, so a screen can drop them into its own
 *  layout — Tools puts them in the right half of its header. */
export function ContextControls({ stacked = false, face = false }: {
  stacked?: boolean;
  /** Draw the chosen audit's short name, "T3 · 71.28", over the select (item
   *  174). A native select cannot show one string closed and another in its
   *  list, so the select keeps the full labels - the list, the title and the
   *  accessible name read them - and paints no text of its own; the face is
   *  the visible label, hidden from assistive technology as a duplicate. */
  face?: boolean;
} = {}) {
  const { sites, siteId, setSiteId, runs, runId, setRunId, site,
          runsError, refreshRuns, runsReady } = useSelection();
  if (!sites.length) return null;
  const chosen = runs.find((r) => r.id === runId) ?? null;
  /** Item 179: "no completed audit" only for a list that has answered empty.
   *  While it is being read the picker says so, and is busy (01-4). */
  const empty = runsReady ? "no completed audit" : `${LOADING_WORD} audits…`;
  // Stacked puts each select on its own labelled row, for the narrow column
  // on the client screen; inline is the one-line header bar.
  if (stacked) {
    return (
      <>
        {runsError && (
          <p className="error" role="alert">
            The audit list could not be read: {runsError}{" "}
            <SecondaryButton onClick={refreshRuns}>
              Try again
            </SecondaryButton>
          </p>
        )}
        <label className={`sel-row${face ? " sel-faced" : ""}`}>
          <span className="sel-lbl">Audit</span>
          <select className="input" value={runId} disabled={!runs.length}
                  aria-busy={!runsReady}
                  title={face && chosen ? runLabel(chosen, runs.indexOf(chosen)) : undefined}
                  onChange={(e) => setRunId(e.target.value)}>
            {!runs.length && <option value="">{empty}</option>}
            {runs.map((r, i) => (
              <option key={r.id} value={r.id}>{runLabel(r, i)}</option>
            ))}
          </select>
          {face && (
            <span className="sel-face" aria-hidden="true">
              {chosen ? runShortLabel(chosen) : runsReady ? "no completed audit" : `${LOADING_WORD}…`}
            </span>
          )}
        </label>
      </>
    );
  }
  return (
    <>
      {site && <span className="ctx-site">{host(site.domain)}</span>}
      <span className="ctx-sep" aria-hidden="true">›</span>
      <select className="ctx-select" value={runId} disabled={!runs.length}
              aria-label="audit run" aria-busy={!runsReady}
              onChange={(e) => setRunId(e.target.value)}>
        {!runs.length && <option value="">{empty}</option>}
        {runs.map((r, i) => (
          <option key={r.id} value={r.id}>{runLabel(r, i)}</option>
        ))}
      </select>
      {site && (
        <LinkButton className="ctx-jump" href={`#/sites/${site.id}`}
           title="Open this site's own page — history, findings and reports">
          Open&nbsp;site&nbsp;→
        </LinkButton>
      )}
    </>
  );
}
