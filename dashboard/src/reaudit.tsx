/** The re-audit drawer: what a re-run of one part would sweep, over which
 *  pages, how deep, and what that costs - stated before the click, around
 *  the one control that commits.
 *
 *  Brief step 5 (`_plans/site-screen-reorg-brief-2026-09-03.md`, WF-02).
 *  Re-testing a finding meant leaving the finding: the coarse control stood
 *  inside the section, under the shared-cause note, and the page-scoped one
 *  appeared only once a page was narrowed to. This drawer is the right-hand
 *  column of the Analyses pane whenever a part with a sweep behind it is
 *  open, and a finding's own "re-audit" opens it pre-scoped.
 *
 *  **It wraps the commit path; it does not duplicate it.** The control that
 *  starts the run is `SectionRefresh` (the whole-site sweep) or
 *  `PageRefresh` (one page), mounted by the caller as `children` exactly as
 *  they were mounted inside the section. Nothing here posts.
 *
 *  **It does not pretend to narrow.** The engine's unit is `(url, dims)`;
 *  the routes expose one page (`/refresh`) and the site (`/audits`), and
 *  nothing takes a list of pages. So the pages select offers the set-shaped
 *  scopes - the pages a finding is on, the nav pages, the current filter -
 *  disabled, and says in text that the sweep runs whole. The brief wrote
 *  this as "until F-06"; F-06 is built for one page, and that option is
 *  live here, so the sentence names what is and is not available rather
 *  than dating it.
 *
 *  **The estimate is the scan matrix's.** `pagesFor`, `SECS_PER_PAGE` and
 *  `human` are imported from `scanmatrix.tsx`, so a time here and a time
 *  in the chooser cannot disagree about the same site. */
import { Working } from "./working";
import { SecondaryButton } from "./buttons";
import { ReactNode, useEffect, useState } from "react";
import { Meta, useFetch } from "./api";
import { pathOf } from "./components";
import { Precheck } from "./precheck";
import { DEPTHS, DepthKey, SECS_PER_PAGE, human, pagesFor } from "./scanmatrix";
import { Pill } from "./pill";

export type Refresh = { dimension: string; also: string[]; per_page: boolean };

/** The finding the drawer was opened from, if it was opened from one. */
export type DrawerFinding = {
  check: string; pages: number; fingerprint: string;
  /** Whether a crawl can look at it - `runs.names_a_page`, decided on
   *  the server. A site-level finding is judged by a full audit. */
  namesPage: boolean;
} | null;

/** Which manual tier a chosen depth asks the launch route for. The route's
 *  own vocabulary (`AuditIn.tier`: auto | T1 | T2 | T3); a manual tier runs
 *  no analyst, which is what the section refresh asks for anyway. */
export const DEPTH_TIER: Record<DepthKey, string> = {
  quick: "T1", standard: "T2", deep: "T3",
};

export function ReauditDrawer({ label, refresh, page, precheck, finding,
                                depth, onDepth, onClearPage, children,
                                onVerify, verifying = false, verdict, verifyError,
                                pageCap, onPrimary }: {
  label: string;
  refresh: Refresh;
  /** The page the pane is narrowed to, or "". */
  page: string;
  precheck: Precheck | null;
  finding: DrawerFinding;
  /** The chosen depth, or null for the engine's own choice - shown as the
   *  Quick pill pressed (brief v5 step U): "engine decides" was a fourth
   *  pill, and the engine's own choice starts at Quick and escalates, which
   *  the Quick pill's title says. Pressing Quick keeps the engine's choice. */
  depth: DepthKey | null;
  onDepth: (d: DepthKey | null) => void;
  /** The primary control (brief v5 step U): asks the sweep's confirmation
   *  to open, the way the sidebar's re-run does. The label carries the
   *  whole choice and re-labels as the pills change. */
  onPrimary: () => void;
  /** Check ids raised both by the sweep and by a brief in this part, for
   *  the "two sources, two questions" note - inside the details here since
   *  step U, not open in the part's body. */
  /** "Whole site" chosen while a page is narrowed to: the filter is the
   *  scope, so clearing it is what widens the run. */
  onClearPage: () => void;
  children: ReactNode;
  /** Brief v2 step D. The one page-scoped run this product has takes the
   *  findings whose pages it re-crawls (`POST /api/sites/{id}/verify`,
   *  `fingerprints`), never a list of URLs, and caps the pages at
   *  `pageCap`. So "the pages this finding is on" is that run, called
   *  through the fix loop's own `verify` - the same client function the
   *  Record's banner calls - and it is offered only from a finding. */
  onVerify?: (fingerprint: string) => void;
  verifying?: boolean;
  verdict?: string | null;
  verifyError?: string | null;
  pageCap?: number;
}) {
  /** The chosen scope: the finding's pages, or the sweep (site or one page,
   *  decided by the page filter). Reset when the drawer moves to another
   *  finding, so a scope chosen for one is never committed for another. */
  const [scope, setScope] = useState<"finding" | "sweep">("sweep");
  useEffect(() => { setScope(finding ? "finding" : "sweep"); }, [finding?.fingerprint]);
  const findingScope = scope === "finding" && Boolean(finding?.namesPage);
  const { data: meta } = useFetch<Meta>("/api/meta");
  const onePage = Boolean(page) && refresh.per_page;
  const pages = pagesFor(onePage ? "page" : "site", precheck, meta?.scopes);
  const secs = (d: DepthKey) => (pages ? pages.n * SECS_PER_PAGE[d] : null);
  const plural = (n: number) => `${n} page${n === 1 ? "" : "s"}`;

  const [allChips, setAllChips] = useState(false);
  /** The pill in hand: the engine's choice reads as Quick. */
  const shown: DepthKey = depth ?? "quick";
  const depthLabel = DEPTHS.find((d) => d.key === shown)!.label;
  const chipLabel = (d: DepthKey) =>
    `${DEPTHS.find((x) => x.key === d)!.label} · free`;
  /** The whole choice in one label, re-said as the pills change. Free on
   *  every depth: the sweep asks for no analyst, so the depth decides how
   *  far it crawls, not what it spends. */
  const primaryLabel = findingScope && finding
    ? `Verify ${plural(finding.pages)} now · free`
    : onePage
      ? `Re-read ${pathOf(page)} · ${label} · ${depthLabel}`
        + (secs(shown) !== null ? ` · ${human(SECS_PER_PAGE[shown])}` : "") + " · free"
      : `Re-check ${label}`
        + (pages ? ` · ${plural(pages.n)}` : "") + ` · ${depthLabel}`
        // `human` carries its own `~` (`scanmatrix.tsx`), so the label
        // does not add a second one (brief v12 step AN).
        + (secs(shown) !== null ? ` · ${human(secs(shown)!)}` : "") + " · free";
  const chips = [refresh.dimension, ...refresh.also];
  const shownChips = allChips ? chips : chips.slice(0, 3);

  return (
    <aside className="reaudit" aria-label={`Re-check ${label}`}>
      {/* The primary control first (brief v5 step U): the whole choice in
          its label, full width, inside the first viewport. Verify where the
          drawer was opened from a finding that names pages; otherwise the
          sweep's confirmation (F-10's two steps: this press spends nothing,
          the committing button stands in the confirmation below). */}
      {findingScope && finding ? (
        <div className="sec-refresh reaudit-verify">
          <SecondaryButton className="reaudit-primary" disabled={verifying}
                  aria-busy={verifying}
                  onClick={() => onVerify?.(finding.fingerprint)}>
            {primaryLabel}
          </SecondaryButton>{" "}
          <span className="muted" role="status" aria-live="polite">
            {verifying ? <Working>Re-crawling…</Working> : verdict ? `Verified: ${verdict}.` : ""}
          </span>
          {verifyError && <p className="error" role="alert">{verifyError}</p>}
        </div>
      ) : (
        <SecondaryButton
                className={`sec-refresh-open reaudit-primary${
                  onePage ? " sec-refresh-page sec-refresh-page-open" : ""}`}
                onClick={onPrimary}
                title={onePage
                  ? `Re-measure ${pathOf(page)} for ${refresh.dimension}, the smallest audit that covers ${label}`
                  : `Re-run the ${refresh.dimension} automatic checks - the smallest dimension that covers ${label}`}>
          {primaryLabel}
        </SecondaryButton>
      )}
      {!findingScope && children}
      <h3>Re-check {label}</h3>
      {finding && (
        <p className="muted reaudit-from">
          From <code>{finding.check}</code>, on {plural(finding.pages)}.
        </p>
      )}

      <div className="reaudit-field reaudit-depth">
        <span className="sel-lbl">Depth</span>
        <div className="reaudit-chips" role="group" aria-label="Depth">
          {DEPTHS.map((d) => (
            <Pill as="button" key={d.key} type="button"
                    tone={shown === d.key ? "current" : "action-free"}
                    aria-pressed={shown === d.key}
                    onClick={() => onDepth(d.key === "quick" ? null : d.key)}
                    title={d.key === "quick"
                      ? `${DEPTH_TIER[d.key]}. The engine's own default: an audit left to it starts here and escalates where the evidence asks.`
                      : `${DEPTH_TIER[d.key]}, fixed - it does not escalate.`}>
              {chipLabel(d.key)}
            </Pill>
          ))}
        </div>
      </div>

      <label className="reaudit-field">
        <span className="sel-lbl">Pages</span>
        <select className="input reaudit-pages"
                value={findingScope ? "finding" : onePage ? "one" : "site"}
                onChange={(e) => {
                  if (e.target.value === "finding") { setScope("finding"); return; }
                  setScope("sweep");
                  if (e.target.value === "site") onClearPage();
                }}>
          <option value="finding" disabled={!finding?.namesPage}>
            {finding
              ? finding.namesPage
                ? `The ${plural(finding.pages)} this finding is on — via verify`
                : "The pages this finding is on — it names none; a full audit judges it"
              : "The pages a finding is on — open the drawer from a finding"}
          </option>
          <option value="nav" disabled>Nav pages</option>
          <option value="filter" disabled>Pages in the current filter</option>
          <option value="one" disabled={!onePage}>
            {page && refresh.per_page ? `One page — ${pathOf(page)}`
              : refresh.per_page ? "One page — narrow to it above first"
              : "One page — not for this part"}
          </option>
          <option value="site">
            {/* Item 180 (e5): the pages the request fetches, not an abstraction. */}
            Every page a site scan visits{pages && !onePage ? ` (${pages.n})` : ""}
          </option>
        </select>
      </label>

      <div className="reaudit-field reaudit-sweep">
        <span className="sel-lbl">Automatic checks</span>
        <div className="reaudit-chips">
          {shownChips.map((c, i) => (
            <Pill key={c} tone={i === 0 ? "current" : "count-info"}>
              {i === 0 ? `${c} · ${label}` : `+ ${c}`}
            </Pill>
          ))}
          {chips.length > 3 && !allChips && (
            <button type="button" className="chip reaudit-more"
                    onClick={() => setAllChips(true)}>
              + {chips.length - 3} more
            </button>
          )}
        </div>
      </div>

      {/* The prose, closed by default (brief v5 step U): what the dimension
          also refreshes, why a page set cannot be asked for, the time, and
          the two-sources note that stood open in the part's body. Read
          once, not every visit. */}
      <details className="reaudit-why">
        <summary className="muted">What this runs and why the numbers differ</summary>
        <p className="muted reaudit-also">
          {refresh.also.length
            ? `Runs with ${refresh.dimension} and refreshes ${refresh.also.length} other `
              + `section${refresh.also.length === 1 ? "" : "s"} with it: ${refresh.also.join(", ")} `
              + "(same dimension). Stated before the click."
            : `${refresh.dimension} covers ${label} and no other part.`}
        </p>
        <p className="muted reaudit-scope-note">
          {findingScope
            ? `Re-crawls the ${plural(finding!.pages)} this finding names and re-runs `
              + "their dimensions there — the same run the Record's verify starts, "
              + `from the finding rather than from a list of pages${pageCap ? `, up to ${pageCap} pages at once` : ""}. `
              + "No score is written."
            : onePage
            ? `Runs ${refresh.dimension} against ${pathOf(page)} alone, for this page, `
              + "and leaves every other page untouched. Every other section that "
              + `${refresh.dimension} covers moves with it, for this page.`
            : `Runs every ${refresh.dimension} automatic check. A set of pages is re-crawled `
              + "only from a finding that names them (verify); nav pages, a template "
              + "or the current filter cannot be asked for, since no route takes a "
              + "list of pages. "
              + (refresh.per_page
                 ? "One page can: narrow to it above."
                 : `${label} is not measured page by page: ${refresh.dimension} reads `
                   + "the domain rather than any page of it, so no page narrows this "
                   + "part, and re-reading one page could not change a finding here.")}
        </p>
        <p className="muted reaudit-cost">
          {pages === null
            ? "Run the precheck to estimate the time."
            : depth
              ? `Estimated ${human(secs(depth)!)} over ${plural(pages.n)} at ${depthLabel}, fixed.`
              : `Estimated ${human(secs("quick")!)} at Quick over ${plural(pages.n)}, `
                + `up to ${human(secs("deep")!)} if the engine escalates to Deep.`}
          {" "}Free — no model is invoked at any depth: the automatic checks ask for no analyst.
          {pages?.from === "budget" && (
            <> The page count is a budget this product sets, not something
               measured here.</>
          )}
        </p>
        {/* "Two sources, two questions" was a panel here; it is the
            tooltip on the source tag now (brief v10 step AF). */}
      </details>
    </aside>
  );
}
