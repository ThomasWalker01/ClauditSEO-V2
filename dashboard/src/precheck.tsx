/** The precheck: what the site says about itself, before a scan is chosen.
 *
 *  Two states, and the difference between them is the whole point. Before it
 *  runs there is no page count anywhere, so the panel offers to measure one
 *  rather than showing an estimate. After it runs, every scope carries a
 *  figure that came from this site.
 *
 *  It sits at the head of the sequence on the client screen because it is the
 *  step before the audit: the audit is the expensive thing, and this is what
 *  tells you how big it would be.
 */

import { Working } from "./working";
import { stamp } from "./client_lanes";
import { LinkButton, SecondaryButton } from "./buttons";
import { goHandler } from "./nav";
import { useState } from "react";

import { api, useFetch } from "./api";
import { Pill } from "./pill";

export interface PrecheckScope {
  pages: number | null;
  basis: string;
}

export interface Precheck {
  entry_url: string;
  checked_at: string;
  took_ms: number;
  sitemap_state: string;
  sitemap_files: number;
  sitemap_urls: number | null;
  sitemap_truncated: boolean;
  nav_count: number;
  footer_count: number;
  nav_unique: number;
  not_linked: string[];
  not_in_sitemap: string[];
  warnings: string[];
  nav_urls: string[];
  page_urls: string[];
  page_urls_capped: boolean;
  findings_meaningful: boolean;
  scopes: Record<string, PrecheckScope>;
}

export function usePrecheck(siteId: string | null, tick = 0) {
  return useFetch<Precheck | null>(
    siteId ? `/api/sites/${siteId}/precheck` : null, tick);
}

/** The newest precheck beside the one before it (brief v4 Item 2). */
export interface PrecheckCompare {
  now: { checked_at: string; nav: number; full: number | null; full_capped: boolean;
         sitemap_files: number | null; sitemap_state: string };
  prior: { kind: "precheck" | "crawl" | null; at: string | null;
           before_audit: { id: string; started_at: string; tier: string } | null;
           nav: number | null; full: number | null; full_capped: boolean;
           sitemap_files: number | null; sitemap_state: string | null };
  diff: { nav: SetDiff; full: SetDiff; capped: boolean };
  suggestion: { cell: "full:quick" | "nav:quick" | null; changed: number;
                share: number | null; reason: string; min_share: number; min_pages: number };
}
export interface SetDiff { added: string[]; removed: string[]; known: boolean }

export function usePrecheckCompare(siteId: string | null, tick = 0) {
  return useFetch<PrecheckCompare | null>(
    siteId ? `/api/sites/${siteId}/precheck/compare` : null, tick);
}

/** The pages the prior check published and this one does not: gone, in a
 *  stronger sense than a scope-limited crawl missing them (WF-04). */
export function pagesGone(compare: PrecheckCompare | null | undefined): Set<string> {
  return new Set(compare?.diff.full.known ? compare.diff.full.removed : []);
}

/** The scope order the scan screen uses. `site` is absent deliberately: its
 *  cap is not a figure the precheck measured, and quoting one it did not
 *  measure is the estimate this step exists to replace. */
const SCOPES: [string, string][] = [
  ["page", "Page"],
  ["nav", "Nav"],
  ["full", "Full"],
];

/** Why a scope has no number, in the operator's words rather than the API's. */
function missing(state: string): string {
  return {
    absent: "no sitemap found",
    unreachable: "sitemap unreachable",
    malformed: "sitemap unreadable",
    blocked_by_robots: "robots.txt blocks it",
  }[state] ?? state;
}

export function PrecheckPanel({ siteId, data, onRan, compact, compare = null }: {
  siteId: string;
  /** `null` means never run — which is a state, not a loading spinner. */
  data: Precheck | null;
  onRan: () => void;
  compact?: boolean;
  /** Now beside prior, with the suggestion (brief v4 Item 2). Only the
   *  full panel reads it. */
  compare?: PrecheckCompare | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/sites/${siteId}/precheck`, {});
      onRan();
    } catch (e) {
      // The endpoint answers 502 when the target site is what failed. Say so
      // rather than "something went wrong": the operator needs to know it was
      // not their own install.
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  /** The caption does not change while it runs — UX-66. A control that
   *  renames itself to a busy word stops saying what it does at the moment
   *  the operator is most likely to look, and assistive technology announces
   *  it as a different control. The progress goes in a live region beside it,
   *  which is the pattern `AnalysisRow` already uses. */
  const button = (
    <>
      {/* Item 178: the precheck runs no model and costs nothing, so it is never
          drawn in the paid tone - which it was until one had run. */}
      <Pill as="button" tone={data ? "nav" : "action-free"}
              disabled={busy} aria-busy={busy} onClick={run}
              title="Reads robots.txt, the sitemap and this page's navigation.
No model, a few seconds.">
        {/* Named in both states. "re-check" read as nothing in particular
            beside two other controls on the since-retired What-to-do pane; the thing being run is
            the precheck, and the caption says so before and after. */}
        {data ? "re-run precheck" : "run precheck"}
      </Pill>
      {/* Mounted unconditionally: a region inserted in the same render as its
          text gives assistive technology nothing to observe a change against. */}
      <span className="muted" role="status" aria-live="polite">
        {busy && <Working>checking…</Working>}
      </span>
    </>
  );

  // Compact is the control and the three counts on one line, for the "What
  // to do" pane's control row. It used to sit in the strip's step 1 card
  // with the stamp and the sitemap warning as well, which made that card the
  // tallest of six and set the height of all of them; the operator moved it
  // here on 2026-09-02. The stamp and the warning are on the full panel,
  // above the chooser, where the counts are used.
  if (compact) {
    return (
      <div className="pre-panel pre-compact">
        <div className="pre-cta">
          {button}
          {/* Rendered text, not a title: that this one is free is the
              reason to press it first (audit F-06). */}
          <span className="pre-cost">free · no model</span>
          {data && (
            <span className="pre-inline">
              {SCOPES.map(([key, label]) => {
                const sc = data.scopes[key];
                if (!sc) return null;
                return (
                  <span className="pre-pair" key={key}>
                    <b>{sc.pages === null ? "—" : sc.pages}</b> {label}
                  </span>
                );
              })}
            </span>
          )}
        </div>
        {error && <p className="pre-error" role="alert">{error}</p>}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="pre-panel">
        <div className="pre-cta">
          {button}
          <span className="pre-cost">a few seconds · free · no model</span>
        </div>
        {!compact && (
          <p className="muted pre-note">
            Nothing has been checked yet, so no scan can say how many pages it
            would visit. This reads what the site publishes about itself and
            counts them.
          </p>
        )}
        {error && <p className="pre-error" role="alert">{error}</p>}
      </div>
    );
  }

  /** Only one of the two lists is a finding, and measuring a real site is
   *  what settled which. On a 272-page site with a 20-link menu, 254 sitemap
   *  pages are "not in the navigation" — which is what a blog or a catalogue
   *  looks like, not a defect. Reported as coverage, in the direction that
   *  carries information, it is a small number the operator can judge.
   *
   *  A page nothing links to is a real problem, but one page fetch cannot
   *  find one: that needs a crawl, and the crawl already reports it. */
  const missingFromSitemap = data.not_in_sitemap.length;
  const inNav = (data.sitemap_urls ?? 0) - data.not_linked.length;

  // Compact is the step-card in the sequence strip, which is one column of
  // six and as tall as its shortest sibling can afford. The figures go on one
  // line and the reasoning goes away: a step card says what the step found,
  // not why the finding is worded as it is. The full panel keeps the prose.
  return (
    <div className="pre-panel">
      <div className="pre-cta">
        {button}
        <span className="pre-cost">
          checked {stamp(data.checked_at)}
          {" · "}{(data.took_ms / 1000).toFixed(1)}s
        </span>
      </div>

      {compare && compare.prior.kind ? (
        <Compare siteId={siteId} data={data} c={compare} />
      ) : (
      <div className="pre-scopes">
        {SCOPES.map(([key, label]) => {
          const sc = data.scopes[key];
          if (!sc) return null;
          return (
            <div className="pre-scope" key={key}>
              <span className="pre-n">{sc.pages === null ? "—" : sc.pages}</span>
              <span className="pre-label">{label}</span>
              <span className="pre-basis">
                {sc.pages === null ? missing(data.sitemap_state) : sc.basis}
              </span>
            </div>
          );
        })}
      </div>
      )}
      {compare && !compare.prior.kind && (
        <p className="muted pre-note pre-first">
          First check, and no audit has crawled this site: nothing to compare
          with yet. The next check will show what moved.
        </p>
      )}

      {data.findings_meaningful && (
        <>
          {missingFromSitemap > 0 && (
            <p className="pre-found">
              <strong>{missingFromSitemap}</strong> page(s) in the navigation
              are missing from the sitemap:{" "}
              {/* Each one a link to its own page (brief v3 step J, UX-14):
                  a sentence that named a count and pointed at a list was
                  one more place to look. */}
              {data.not_in_sitemap.map((u, i) => (
                <span key={u}>
                  {i > 0 && ", "}
                  <a href={`#/sites/${siteId}/dossier/${encodeURIComponent(u)}`}>
                    {u.replace(/^https?:\/\/[^/]+/, "") || "/"}
                  </a>
                </span>
              ))}.
            </p>
          )}
          {/* Audit F9: this said "11 of 49 published pages are in the primary
              navigation" about forty lines under a Nav card reading "15 pages",
              in the same phrase, and the 4 that reconcile them are named in the
              sentence immediately above. `inNav` is the sitemap INTERSECTED
              with the nav; the card's 15 is the nav itself. Both numbers, and
              the join, in one sentence. */}
          <p className="muted pre-note">
            {inNav} of {data.sitemap_urls} published page(s) are in the primary
            navigation; the navigation has {data.nav_unique ?? data.nav_count}
            {(data.nav_unique ?? data.nav_count) - inNav > 0
              ? <>, so {(data.nav_unique ?? data.nav_count) - inNav} of
                  {" "}{(data.nav_unique ?? data.nav_count) - inNav === 1 ? "it is" : "them are"}
                  {" "}not published in the sitemap</>
              : null}. The rest are reached some other way — which is ordinary,
            and is not the same as being orphaned. Finding a page nothing links
            to needs a crawl.
          </p>
        </>
      )}

      {data.warnings.map((w) => <p className="pre-warn" key={w}>{w}</p>)}
      {error && <p className="pre-error" role="alert">{error}</p>}
    </div>
  );
}


/** Now / Prior / Change / What moved, one row per scope, and the scan the
 *  difference calls for (brief v4 Item 2). The suggestion is the server's
 *  rule over the counts - no model - and names the matrix cell, which the
 *  Audit pane pre-selects from the address. "Scan only the N new pages" is
 *  the page-list run no route takes yet: rendered disabled and saying so,
 *  never hidden and never faked.
 *
 *  Not shown, because the payload cannot say it: pages moved between the
 *  navigation and the footer - the precheck keeps one list for both. */
function Compare({ siteId, data, c }: { siteId: string; data: Precheck; c: PrecheckCompare }) {
  /* `stamp` is `client_lanes`' now (audit F11): this file had its own, and
     the two differed only in dropping the offset rather than converting. */
  const delta = (now: number | null, prior: number | null) => {
    if (now === null || prior === null) return <span className="pre-delta muted">—</span>;
    const d = now - prior;
    if (!d) return <span className="pre-delta muted">—</span>;
    const pct = prior ? ` · ${d > 0 ? "+" : ""}${Math.round((d / prior) * 100)}%` : "";
    return <span className={`pre-delta ${d > 0 ? "pre-up" : "pre-down"}`}>{d > 0 ? "+" : ""}{d}{pct}</span>;
  };
  const list = (label: string, paths: string[], tone: string) => paths.length ? (
    <details className="pre-moved">
      <summary><span className={tone}>{paths.length} {label}</span></summary>
      <ul>{paths.map((u) => (
        <li key={u}><a href={`#/sites/${siteId}/dossier/${encodeURIComponent(data.entry_url.replace(/\/$/, "") + u)}`}>{u}</a></li>
      ))}</ul>
    </details>
  ) : null;
  const priorLabel = c.prior.kind === "crawl"
    ? `vs last audit · ${stamp(c.prior.at)}`
    : `prior ${stamp(c.prior.at)}`
      + (c.prior.before_audit
         ? ` (before audit ${c.prior.before_audit.started_at.slice(0, 10)} ${c.prior.before_audit.tier})`
         : "");
  const sug = c.suggestion;
  const cellName = sug.cell === "full:quick" ? "Full · Quick" : sug.cell === "nav:quick" ? "Nav · Quick" : null;
  const [scope, depth] = (sug.cell ?? ":").split(":");
  const added = c.diff.full.known ? c.diff.full.added.length : 0;
  return (
    <>
      <p className="muted pre-prior">{priorLabel}{c.diff.capped ? " · the sitemap list is capped at 500, so the diff is over the first 500" : ""}</p>
      <table className="findings pre-compare">
        <thead><tr><th>Scope</th><th className="num">Now</th><th className="num">Prior</th><th>Change</th><th>What moved</th></tr></thead>
        <tbody>
          <tr>
            <td><b>Page</b> <span className="muted">a URL you name</span></td>
            <td className="num">1</td><td className="num">1</td>
            <td><span className="pre-delta muted">—</span></td><td className="muted">—</td>
          </tr>
          <tr>
            <td><b>Nav</b> <span className="muted">{data.scopes.nav?.basis}</span></td>
            <td className="num">{c.now.nav}</td>
            <td className="num">{c.prior.nav ?? "—"}</td>
            <td>{delta(c.now.nav, c.prior.nav)}</td>
            <td>{c.diff.nav.known
              ? (c.diff.nav.added.length || c.diff.nav.removed.length
                 ? <>{list("added", c.diff.nav.added, "pre-added")}{list("removed", c.diff.nav.removed, "pre-removed")}</>
                 : <span className="muted">unchanged</span>)
              : <span className="muted">no prior navigation to compare</span>}</td>
          </tr>
          <tr>
            <td><b>Full</b> <span className="muted">{data.scopes.full?.basis}</span></td>
            <td className="num">{c.now.full ?? "—"}</td>
            <td className="num">{c.prior.full ?? "—"}</td>
            <td>{delta(c.now.full, c.prior.full)}</td>
            <td>{c.diff.full.known
              ? <>{list("added", c.diff.full.added, "pre-added")}{list("removed", c.diff.full.removed, "pre-removed")}
                  {!c.diff.full.added.length && !c.diff.full.removed.length && <span className="muted">unchanged</span>}
                  {c.prior.sitemap_files !== null && c.prior.sitemap_files !== c.now.sitemap_files
                    && <span className="pre-files"> · sitemap files {c.prior.sitemap_files} → {c.now.sitemap_files}</span>}</>
              : <span className="muted">{missing(c.now.sitemap_state)}</span>}</td>
          </tr>
          <tr>
            <td><b>Robots</b> <span className="muted">robots.txt and the sitemap it declares</span></td>
            <td className="num muted">{c.now.sitemap_state}</td>
            <td className="num muted">{c.prior.sitemap_state ?? "—"}</td>
            <td><span className="pre-delta muted">{c.prior.sitemap_state && c.prior.sitemap_state !== c.now.sitemap_state ? "changed" : "—"}</span></td>
            <td className="muted">{c.prior.sitemap_state && c.prior.sitemap_state !== c.now.sitemap_state ? `${c.prior.sitemap_state} → ${c.now.sitemap_state}` : "unchanged"}</td>
          </tr>
        </tbody>
      </table>
      <div className="pre-suggest">
        <b>{cellName ? `Suggested: ${cellName} · free` : "Nothing to run"}</b> — {sug.reason}.
        <div className="pre-suggest-acts">
          {cellName && (
            <LinkButton
               href={`#/sites/${siteId}?tab=history&scope=${scope}&depth=${depth}`}
               onClick={goHandler(`#/sites/${siteId}?tab=history&scope=${scope}&depth=${depth}`)}>
              Show {cellName} in the grid
            </LinkButton>
          )}
          {added > 0 && (
            <>
              <SecondaryButton disabled
                      aria-describedby="pre-pagelist-why">
                Scan only the {added} new page{added === 1 ? "" : "s"}
              </SecondaryButton>
              <span id="pre-pagelist-why" className="muted">not available yet</span>
            </>
          )}
        </div>
        <p className="muted pre-rule">
          Rule: at least {Math.round(sug.min_share * 100)}% of the pages published before added or
          removed, and at least {sug.min_pages} pages → Full; only the navigation changed → Nav;
          else nothing to run. Removed pages mark their findings "on pages gone"; they are not
          scanned. The suggested cell is marked in the grid below.
        </p>
      </div>
    </>
  );
}
