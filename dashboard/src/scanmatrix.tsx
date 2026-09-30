/** The scan chooser: how much of the site, and how hard to look.
 *
 *  Two decisions on two axes, drawn as a grid, because they are two decisions
 *  and the product used to present them as four settings. Every cell states
 *  what it costs in pages and time before it is pressed; no cell says "T2".
 *
 *  The grid is not the point on its own — a twelve-button menu is a bigger
 *  menu, not more guidance. What makes it a recommendation is that triage
 *  marks the cell it would pick, and the marked cell is the only one wearing
 *  the accent.
 */

import { Working } from "./working";
import React, { useEffect, useState } from "react";

import { api, useFetch, Meta } from "./api";
import { Precheck } from "./precheck";
import { SpendMark } from "./components";
import { SPEND_WORDS, useConfirm } from "./confirm";
import { LOADING_WORD } from "./glossary";
import { host, useSelection } from "./selection";
import { entry, short } from "./glossary";

type ScopeKey = "page" | "nav" | "site" | "full";
export type DepthKey = "quick" | "standard" | "deep";

// Item 183 (channel ruling 20260918-0410): the words are the registry's, which
// holds `scanscope`'s own strings. Two copies of one definition is how Quick
// came to mean breadth on one screen and judgement on another.
const SCOPES: { key: ScopeKey; label: string; what: string }[] =
  (["page", "nav", "site", "full"] as ScopeKey[]).map((key) => ({
    key, label: entry(`scope-${key}`).word, what: short(entry(`scope-${key}`)),
  }));

// Exported with `SECS_PER_PAGE`, `pagesFor` and `human` for the re-audit
// drawer (`reaudit.tsx`, brief step 5), so its estimate is this one.
export const DEPTHS: { key: DepthKey; label: string; what: string; model: string }[] =
  (["quick", "standard", "deep"] as DepthKey[]).map((key, i) => ({
    key, label: entry(`depth-${key}`).word, what: short(entry(`depth-${key}`)),
    model: ["no model", "standard tier", "deep tier"][i],
  }));

/** Seconds per page, by depth. Coarse on purpose: the figure exists to
 *  separate "minutes" from "an hour", and a false precision here would be
 *  read as a promise. Replaced by measured per-site figures once enough runs
 *  are stored — which is why the caption says estimate. */
export const SECS_PER_PAGE: Record<DepthKey, number> = {
  quick: 1.8, standard: 4.5, deep: 11,
};

/** Where a row's page figure came from, carried with the figure.
 *
 *  These are two different claims and the screen used to make only one of
 *  them. A measured count is this site's own, from the precheck; a budget is
 *  the product's constant, true before the site was ever looked at. UX-100
 *  was one of four rows carrying a budget under a caption saying all four
 *  were measured — the provenance invariant's plainest breach, on the screen
 *  where the figure decides what gets bought. */
type Basis = "precheck" | "budget";
type PageCount = { n: number; from: Basis } | null;

/** What a cell will actually visit, given the precheck's counts and the
 *  server's scope table.
 *
 *  `null` where nothing has measured it — the cell then says so rather than
 *  guessing, which is the whole reason the precheck runs first. The scope
 *  table is a second thing that has to have arrived: the cap is no longer
 *  typed here (CQ-245), so until `/api/meta` answers, a bounded scope's
 *  figure is unknown in exactly the way an unrun precheck's is.
 *
 *  Every scope is bounded the same way rather than `site` alone. `full`
 *  carries `FULL_MAX_PAGES` in the same table and the client ignored it, so
 *  a site with more URLs than that ceiling read as a Full scan that would
 *  visit all of them. Same constant, same table, same lie one row down. */
export function pagesFor(scope: ScopeKey, pre: Precheck | null,
                  scopes: Meta["scopes"] | undefined): PageCount {
  if (!pre || !scopes) return null;
  const measured =
    scope === "page" ? 1
      : scope === "nav" ? (pre.nav_unique || null)
        // Site and Full read the same measurement and differ only in the
        // budget applied to it - and that measurement is the site's size, the
        // union of what the sitemap declares and what the page fetch found,
        // not the declaration alone (audit F10).
        //
        // It was `pre.sitemap_urls`: 49 on twenty22, on a screen whose own
        // header says the site has 53, and whose panel two cards up names the
        // 4 pages found and not declared. The registry says Full "is the only
        // scan whose coverage can reach 100%", which at 49 of 53 it cannot.
        // `population.tsx` gives the reason in its own words: "divide by the
        // declaration and coverage rises when the declaration fails."
        : pre.sitemap_urls === null ? null
          : pre.sitemap_urls + (pre.not_in_sitemap?.length ?? 0);
  if (measured === null) return null;
  const budget = scopes[scope]?.max_pages ?? null;
  if (budget === null || measured <= budget) {
    return { n: measured, from: "precheck" };
  }
  return { n: budget, from: "budget" };
}

/** The sentence under the grid, built from the rows above it.
 *
 *  Derived rather than written, because a fixed sentence is what UX-100 was:
 *  a caption cannot state where four figures came from unless it is looking
 *  at them. Which rows are budget-bound depends on the site — a 40-page site
 *  is under both caps, and then every figure on the screen really is the
 *  precheck's. */
function foot(rows: { label: string; pages: PageCount }[],
              ready: boolean): string {
  if (!ready) {
    return "Run the precheck above and every cell will say how many pages it "
      + "would visit.";
  }
  const times = " Times are estimates and get more honest as runs are stored.";
  // Two scopes with one figure, said rather than left to look like an error
  // (audit F10): on a site under every cap, Site and Full really do visit the
  // same pages, and two identical rows with different names read as a bug.
  const same = (() => {
    const site = rows.find((r) => r.label === "Site")?.pages;
    const full = rows.find((r) => r.label === "Full")?.pages;
    return site && full && site.n === full.n
      ? " Site and Full read the same figure here because nothing on this site "
        + "is over either cap; they differ on sites that are."
      : "";
  })();
  const capped = rows.filter((r) => r.pages?.from === "budget");
  if (!capped.length) {
    return "Page counts are this site's own, from the precheck." + same + times;
  }
  const named = capped.map((r) => `${r.label} (${r.pages!.n})`);
  const list = named.length === 1 ? named[0]
    : named.slice(0, -1).join(", ") + " and " + named[named.length - 1];
  return `Page counts are this site's own, from the precheck — except `
    + `${list}, ${capped.length === 1 ? "which is a" : "which are"} page `
    + `budget${capped.length === 1 ? "" : "s"} this product sets, not `
    + `something measured here.` + same + times;
}

export function human(seconds: number): string {
  if (seconds < 90) return `~${Math.round(seconds)}s`;
  if (seconds < 3600) return `~${Math.round(seconds / 60)}m`;
  const h = seconds / 3600;
  return `~${h < 2 ? h.toFixed(1) : Math.round(h)}h`;
}

/** `human()` in words, for a name that is spoken rather than read.
 *
 *  Same thresholds and same rounding, so the two never disagree about which
 *  scan is longer; only the rendering differs. `~4m` is right on a button
 *  three characters wide and wrong in an accessible name, where a screen
 *  reader announces it as "tilde four m".
 */
function spoken(seconds: number): string {
  const unit = (n: number, word: string) =>
    `about ${n} ${word}${n === 1 ? "" : "s"}`;
  if (seconds < 90) return unit(Math.round(seconds), "second");
  if (seconds < 3600) return unit(Math.round(seconds / 60), "minute");
  const h = seconds / 3600;
  return h < 2 ? `about ${h.toFixed(1)} hours` : unit(Math.round(h), "hour");
}

/** What a screen reader hears instead of the cell's two visible spans.
 *
 *  UX-99. The grid encodes the two decisions in *layout*: the scope in a
 *  sibling `.scan-rowhead`, the depth in a sibling `.scan-colhead`, neither
 *  tied to the button by `headers`, `aria-labelledby` or a table role. So the
 *  twelve accessible names were twelve durations, and an operator who cannot
 *  see the grid could tell how long each scan would take and nothing about
 *  which scan it was — on the screen where the product asks for money. The
 *  rendered-axe gate cannot catch this: `button-name` asks whether a button
 *  has *a* name, and every one of these had one.
 *
 *  **It restates the cost, and that is not decoration.** An `aria-label`
 *  replaces the button's whole subtree, and part of that subtree is
 *  `SpendMark`'s `sr-only` "spends model tokens: " (`components.tsx`). A
 *  label naming only the scope and the depth would have closed UX-99 by
 *  deleting the spend mark from the one audience that cannot see the `$`
 *  beside it — F-10 clause 1's invariant, broken on the same control by the
 *  change meant to improve it.
 */
function cellLabel(scopeLabel: string, depthLabel: string,
                   secs: number | null, free: boolean): string {
  //  Null is the unmeasured case, not a zero: the visible span says "run it"
  //  because no precheck has counted the pages yet, and the name says the
  //  same thing in the same words rather than implying a duration of none.
  const when = secs === null
    ? "duration unknown until the precheck runs"
    : spoken(secs);
  return `${scopeLabel} scan, ${depthLabel} depth — ${when}, `
    + (free ? "free" : "spends model tokens");
}

export function ScanMatrix({ siteId, precheck, onLaunched, running = null,
                            precheckLoading = false }: {
  /** Item 178 (03-2): the precheck is still being read, so no cell can say
   *  what it would visit yet and none is offered. */
  precheckLoading?: boolean;
  siteId: string;
  precheck: Precheck | null;
  onLaunched: (runId: string) => void;
  /** The audit in flight against this site, if one is. Every cell is
   *  withheld while it is, with the reason in rendered text: twelve enabled
   *  crawl launches under a strip saying "running" was a second audit one
   *  click away (audit F-03). The route refuses too, with a 409, so the
   *  screen's withholding is a courtesy on top of a guarantee. */
  running?: { id: string; started_at: string | null } | null;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** The URL a Page scan reads. Seeded from the precheck's entry page so the
   *  row works without typing, and editable because the row's own words
   *  promise it: "one URL you name" with nowhere to name it is a control
   *  that lies about what it does. */
  const [pageUrl, setPageUrl] = useState("");
  const url = pageUrl || precheck?.entry_url || "";
  /** "" means every nav page, which is what Nav means by default. A single
   *  URL narrows it to one — the same decision as Page, reached from the row
   *  the operator was already looking at. */
  const [navUrl, setNavUrl] = useState("");
  /** The scan scope table, for the page budgets the grid used to type.
   *  Fetched here rather than taken as a prop: the grid has two mounts — the
   *  launcher and the site's History tab — and only the launcher already
   *  holds `/api/meta`, so a prop would make the other screen fetch a payload
   *  it has no other use for. */
  const { data: meta } = useFetch<Meta>("/api/meta");

  const { sites } = useSelection();
  const [dialog, ask] = useConfirm();
  const launch = async (scope: ScopeKey, depth: DepthKey) => {
    // Item 178 (03-1): a cell that reaches a model asks first - which scan, on
    // which site, over how many pages and roughly how long - rather than
    // starting on the press. Quick runs no model and starts as before.
    if (depth !== "quick") {
      const sc = SCOPES.find((x) => x.key === scope)!;
      const d = DEPTHS.find((x) => x.key === depth)!;
      const row = rows.find((r) => r.key === scope);
      const site = sites.find((s) => s.id === siteId);
      const ok = await ask({
        kind: "spend", price: null, action: `Start ${sc.label} · ${d.label}`,
        title: `Start a ${sc.label} · ${d.label} scan${site ? ` of ${host(site.domain)}` : ""}?`,
        body: <>
          <p>{sc.what} {d.what} It runs on the {d.model}, so it spends model tokens.</p>
          <p>{row?.pages
            ? `About ${row.pages.n} page${row.pages.n === 1 ? "" : "s"}, roughly `
              + `${human(row.pages.n * SECS_PER_PAGE[depth])}.`
            : "How many pages it visits is not known until the precheck has run."}</p>
        </>,
      });
      if (!ok) return;
    }
    setBusy(`${scope}:${depth}`);
    setError(null);
    try {
      const r = await api.post<{ run_id: string }>(
        `/api/sites/${siteId}/audits`,
        // Only Page carries a URL. The other scopes derive their frontier from
        // the site, and sending one would silently re-root a whole crawl.
        scope === "page" ? { scope, depth, start_url: url }
          // A Nav scan narrowed to one page IS a page scan — the same one
          // request, so it is sent as one rather than as a second kind of
          // single-page run the engine would have to learn about.
          : scope === "nav" && navUrl
            ? { scope: "page", depth, start_url: navUrl }
            : { scope, depth });
      onLaunched(r.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  /** The precheck's suggestion, named on the address as `?scope=&depth=`
   *  by its "Run <cell> → step 2" link (brief v4 Item 2). A rule over the
   *  precheck's counts, not triage's pick: triage does not receive scope or
   *  page data and cannot rank a scan. Read on mount and on every
   *  hashchange: since brief v24 step BN the precheck and this grid are on
   *  one pane, so the link changes the address without remounting the grid,
   *  and read once it marked nothing. The cell is marked, never pressed - the
   *  press is the operator's. */
  const readRecommended = () => {
    const q = new URLSearchParams((window.location.hash.split("?")[1]) || "");
    const sc = q.get("scope"), d = q.get("depth");
    return sc && d && SCOPES.some((s) => s.key === sc) && DEPTHS.some((x) => x.key === d)
      ? `${sc}:${d}` : null;
  };
  const [recommended, setRecommended] = useState<string | null>(readRecommended);
  useEffect(() => {
    const read = () => setRecommended(readRecommended());
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Every row's figure, computed once so the grid and the sentence beneath
   *  it cannot disagree about what is on screen. */
  const rows = SCOPES.map((sc) => ({
    ...sc,
    // A narrowed Nav row is one page, and the row's own count has to agree
    // with what pressing it will do. Still the precheck's figure: the page
    // is one the precheck listed.
    pages: (sc.key === "nav" && navUrl
      ? { n: 1, from: "precheck" }
      : pagesFor(sc.key, precheck, meta?.scopes)) as PageCount,
  }));

  return (
    <div className="scan-matrix">
      {running && (
        <p className="scan-running" role="status">
          An audit is running against this site now — wait for it to finish
          rather than paying for it twice.{" "}
          <a href={`#/runs/${running.id}`}>Open the audit →</a>
        </p>
      )}
      <div className="scan-grid" role="group" aria-label="Choose a scan">
        <div className="scan-corner" aria-hidden="true">
          <span className="muted">scope ↓ &nbsp; depth →</span>
        </div>
        {DEPTHS.map((d) => (
          <div className="scan-colhead" key={d.key}>
            <strong>{d.label}</strong>
            <span className="muted">{d.what}</span>
            <span className="scan-model">{d.model}</span>
          </div>
        ))}

        {rows.map((sc) => {
          const pages = sc.pages;
          return (
            <RowOf key={sc.key} scope={sc} pages={pages} busy={busy}
                   recommended={recommended} onPick={launch}
                   counting={precheckLoading || !meta}
                   disabled={Boolean(running) || precheckLoading || !meta
                             || (sc.key === "page" && !url.trim())}
                   extra={
                     sc.key === "page" ? (
                       <label className="scan-url">
                         <span className="muted">which page</span>
                         <input type="url" value={url} spellCheck={false}
                                list="scan-page-urls" placeholder="https://…"
                                onChange={(e) => setPageUrl(e.target.value)} />
                         <datalist id="scan-page-urls">
                           {(precheck?.page_urls ?? []).map((u) => (
                             <option value={u} key={u} />
                           ))}
                         </datalist>
                         {precheck?.page_urls_capped && (
                           <span className="muted">
                             first {precheck.page_urls.length} of{" "}
                             {precheck.sitemap_urls} — type any other
                           </span>
                         )}
                       </label>
                     ) : sc.key === "nav" ? (
                       <label className="scan-url">
                         <span className="muted">which of them</span>
                         <select value={navUrl}
                                 onChange={(e) => setNavUrl(e.target.value)}>
                           <option value="">
                             All {precheck?.nav_unique ?? ""} nav pages
                           </option>
                           {(precheck?.nav_urls ?? []).map((u) => (
                             <option value={u} key={u}>{u}</option>
                           ))}
                         </select>
                       </label>
                     ) : null
                   } />
          );
        })}
      </div>

      {error && <p className="scan-error" role="alert">{error}</p>}

      <p className="muted scan-foot">
        {precheckLoading || !meta
          ? `${LOADING_WORD} the precheck - every cell waits for its page count.`
          : foot(rows, Boolean(precheck && meta))}
      </p>
      {dialog}
    </div>
  );
}

function RowOf({ scope, pages, busy, recommended, onPick, extra, disabled, counting = false }: {
  /** The page counts are still being read (item 178). */
  counting?: boolean;
  scope: { key: ScopeKey; label: string; what: string };
  pages: PageCount;
  busy: string | null;
  recommended: string | null;
  onPick: (s: ScopeKey, d: DepthKey) => void;
  /** A control the row needs to mean what it says — Page's URL field. */
  extra?: React.ReactNode;
  /** The row cannot run yet, because `extra` has not been answered. */
  disabled?: boolean;
}) {
  return (
    <>
      <div className="scan-rowhead">
        <strong>{scope.label}</strong>
        <span className="muted">{scope.what}</span>
        <span className="scan-pages">
          {pages === null
            ? "— pages"
            : `${pages.n} page${pages.n === 1 ? "" : "s"}`}
        </span>
        {extra}
      </div>
      {DEPTHS.map((d) => {
        const key = `${scope.key}:${d.key}`;
        const running = busy === key;
        const secs = pages === null ? null : pages.n * SECS_PER_PAGE[d.key];
        return (
          <div className="scan-cellwrap" key={d.key}>
            <button className={`scan-cell${recommended === key ? " is-rec" : ""}`}
                    aria-label={cellLabel(scope.label, d.label, secs,
                                          d.key === "quick")}
                    disabled={Boolean(busy) || Boolean(disabled)}
                    onClick={() => onPick(scope.key, d.key)}>
              {/* Never "run it" (03-2): that read as an instruction on a control
                  that starts an audit. The cell says what is known of its time. */}
              <span className="scan-time">
                {/* While counting the cell is held and the foot says Loading; the
                    caption stays one shape rather than swapping to a busy word. */}
                {secs !== null ? human(secs) : counting ? "—" : "time unknown"}
              </span>
              {/* The shared mark on every cell that reaches a model (F-10
                  clause 1): the launcher's control for the same POST is
                  marked, and one purchase marked on one surface and not
                  another is the defect the mark exists to end (audit F-02). */}
              <span className={`scan-cost ${d.key === "quick" ? "is-free" : ""}`}>
                {d.key === "quick" ? "free" : <><SpendMark />{SPEND_WORDS.unpriced}</>}
              </span>
            </button>
            {/* The busy word goes beside the control, never in place of its
                caption — UX-66. A cell that renamed itself would stop saying
                which scan it starts at the moment that matters most. */}
            <span className="muted scan-busy" role="status" aria-live="polite">
              {running && <Working>starting…</Working>}
            </span>
          </div>
        );
      })}
    </>
  );
}
