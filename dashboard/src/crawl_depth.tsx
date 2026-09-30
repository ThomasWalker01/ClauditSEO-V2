/** How deep the crawl had to go — the Crawl & sitemaps part's "now" block
 *  (brief v16b).
 *
 *  A histogram of pages by clicks from the home page, over the audit the
 *  pane is reading. Ported from the operator's approved mockup
 *  (`crawl_depth_mockup.html`); the distribution in that file is
 *  illustrative and every number here is read off the payload.
 *
 *  **Nothing here computes what the chart says**, the same split brief v16a
 *  drew for the Structured data picture: bars, counts, the sitemap-only
 *  tally and where the "past three clicks" rule falls all arrive whole from
 *  `runs.crawl_depth_payload`. This file decides how tall a bar is drawn and
 *  which tone it takes, and reads every number off the model — so the chart
 *  and the finding list it narrows cannot count different things.
 *
 *  **Bars are `<button>`s and CSS boxes rather than the mockup's `<rect>`s.**
 *  A bar is a control here — pressing one narrows the part's finding list —
 *  and the mockup's SVG has no element that is one. The drawing is the
 *  mockup's: fill, count above, depth label below, one baseline, no
 *  gridlines, a dashed rule before the first bar past three. What changed is
 *  the technique, so the keyboard and the accessibility tree get a real
 *  pressed control rather than a shape with a click handler on it.
 *
 *  **Tone.** Two of the stylesheet's existing semantic tokens and no new
 *  colour, which is item 140's rule applied before item 140 lands: `--good`
 *  for the depths a crawler and a person can both reach, `--warn-strong`
 *  past three. The mockup's `--crawl` has no counterpart in this palette and
 *  inventing one would be the second answer 140 exists to remove.
 */
import type { CSSProperties } from "react";
import { pathOf } from "./components";
import { goto } from "./nav";
import { setNarrowInHash } from "./narrow";
import { pathKey } from "./population";

/** One bar's height, as a fraction of the tallest, handed to the stylesheet
 *  as a custom property. Both the fill and the count above it are placed
 *  from it, so they cannot part company. */
const frac = (f: number): CSSProperties =>
  ({ "--cd-f": String(f) } as CSSProperties);

/** Pages by click depth for one stored run, as the server assembled it. */
export type CrawlDepth = {
  run_id: string;
  /** False where the run stored no depth on any page: the block says so
   *  rather than drawing an empty chart, which would read as zero. */
  recorded: boolean;
  /** `page | nav | site | full`, for the narrow-run qualifier. */
  scope: string | null;
  /** The page depth 0 belongs to, as the crawl resolved it. */
  entry: string | null;
  /** Pages the run stored, whether or not each carried a depth. */
  crawled: number;
  /** Of those, how many answered an error (item 229): the chart counts them,
   *  the "reached" figure beside it does not. */
  errored?: number;
  /** The first depth the server calls deep, so "past three" is written down
   *  once, on the server, and read here. */
  deep_from: number;
  bars: { depth: number; pages: number; sitemap_only: number }[];
  /** Every page's depth, for narrowing the finding list to one bar. */
  at: Record<string, number>;
};

/** What the address carries, verbatim. Read as a string and validated
 *  separately, because the payload it has to be valid against arrives from
 *  the network and the address does not wait for it. */
export function depthFromHash(): string {
  const q = new URLSearchParams((window.location.hash || "").split("?")[1] || "");
  return q.get("depth") ?? "";
}

/** Which bar that names, or null. A depth the payload has no bar for is no
 *  selection rather than an empty finding list, for `costFromHash`'s reason:
 *  a truncated or hand-edited link should show everything, which is what
 *  this screen shows by default. */
export function depthPicked(depth: CrawlDepth | null | undefined,
                            raw: string): number | null {
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isInteger(n)) return null;
  return depth?.recorded && depth.bars.some((b) => b.depth === n) ? n : null;
}

/** Write the selection into the address, which is where the block reads it
 *  back from. The same one-way rule `cost` follows: the setter navigates,
 *  `hashchange` re-reads, and a pasted link and a press are the same event. */
export function setDepthInHash(next: number | null): void {
  // One narrow at a time (brief v25 step BP): the depth is one of three.
  setNarrowInHash("depth", next === null ? null : String(next));
}

/** Whether a URL sits at the selected depth, or null where nothing is
 *  selected. Matched as the crawl spells it, or by path where a stored
 *  finding spells the host differently — the same tolerance `narrowStates`
 *  applies to the page filter, and for the same reason: a finding stored
 *  against `example.com/x` and a crawl that fetched `www.example.com/x` are
 *  about one page. */
export function pagesAtDepth(depth: CrawlDepth | null | undefined,
                             pick: number | null): ((url: string) => boolean) | null {
  if (!depth || pick === null) return null;
  const urls = new Set<string>();
  const paths = new Set<string>();
  for (const [url, d] of Object.entries(depth.at)) {
    if (d !== pick) continue;
    urls.add(url);
    paths.add(pathOf(url));
  }
  // Keyed the way 155 keys a page (`pathKey`: `/x` and `/x/` are one page),
  // which is what the crawl population intersects with - `pathOf` alone kept
  // the slash and an intersection could silently drop a page (brief v25 BP).
  const keys = new Set([...urls].map(pathKey));
  return (url: string) => urls.has(url) || paths.has(pathOf(url)) || keys.has(pathKey(url));
}

/** How a bar reads on the axis. Depth 0 is the home page and whatever else
 *  reached the crawl without a click path from it — a real signal, so it is
 *  on the label rather than in a tooltip. */
export function barLabel(bar: { depth: number; sitemap_only: number }): string {
  if (bar.depth === 0) {
    return bar.sitemap_only > 0 ? `home + ${bar.sitemap_only} sitemap-only` : "home";
  }
  return `${bar.depth} click${bar.depth === 1 ? "" : "s"}`;
}

/** The word a narrow run's heading carries, or null where the run read the
 *  site. `api.ts`'s `scopeWord` says the same about the score column, and
 *  these are its two narrow answers. */
const narrowWord = (scope: string | null) =>
  scope === "page" ? "page scan" : scope === "nav" ? "nav scan" : null;

export function CrawlDepthBlock({ depth, picked, onPick }: {
  depth: CrawlDepth | null | undefined;
  picked: number | null;
  onPick: (next: number | null) => void;
}) {
  if (!depth) return null;
  const narrow = narrowWord(depth.scope);
  const head = (
    <>
      <h4 className="cd-head">
        How deep the crawl had to go
        {narrow && <span className="cd-narrow"> — {narrow}: over those pages alone</span>}
      </h4>
      {/* The item's sentence, verbatim. It is the block's whole argument:
          the chart is a count, and this says why the count matters. */}
      <p className="muted cd-note">
        Pages by clicks from the home page. Anything past three is hard for a
        crawler to keep fresh and hard for a person to find; anything at zero
        clicks that is not the home page arrived only through the sitemap.
        {" "}Over the {depth.crawled} URL{depth.crawled === 1 ? "" : "s"} the crawl fetched
        {(depth.errored ?? 0) > 0
          ? `, including ${depth.errored} that returned an error`
          : ""}.
      </p>
    </>
  );
  if (!depth.recorded) {
    // Absent, not zero. A run that stored no depth has nothing to draw from,
    // and an empty chart would say every page sits at the home page — a
    // measurement this run never made.
    return (
      <section className="cd-root">
        {head}
        <p className="muted cd-absent">
          This audit recorded no click depth, so how deep the crawl went is not
          known for its {depth.crawled} page{depth.crawled === 1 ? "" : "s"} —
          which is not the same as their all being one click from home.
          Re-audit the site to record it.
        </p>
      </section>
    );
  }
  const tallest = Math.max(...depth.bars.map((b) => b.pages), 1);
  const chosen = picked === null ? undefined
    : depth.bars.find((b) => b.depth === picked);
  return (
    <section className="cd-root">
      {head}
      <div className="cd-chart" role="group"
           aria-label="Pages by clicks from the home page">
        {depth.bars.map((bar) => {
          const deep = bar.depth >= depth.deep_from;
          // The dashed rule is drawn on the first bar past three rather than
          // as a shape of its own, so it cannot drift from the bar it
          // divides — and a crawl no deeper than three has no such bar, which
          // is the degradation the item asks for and not a second branch.
          const rule = deep && bar.depth === depth.deep_from;
          const on = picked === bar.depth;
          return (
            <button key={bar.depth} type="button" aria-pressed={on}
                    className={`cd-bar${deep ? " cd-deep" : ""}`
                               + `${rule ? " cd-rule" : ""}${on ? " cd-on" : ""}`}
                    onClick={() => onPick(on ? null : bar.depth)}>
              {rule && <span className="cd-ruleword">past three clicks</span>}
              {/* The bar's height as a fraction, not as a length: the
                  stylesheet owns how tall the tallest bar is drawn and how
                  much room the count and the label take, so this file cannot
                  disagree with it about where the baseline sits. */}
              <span className="cd-n" style={frac(bar.pages / tallest)}>{bar.pages}</span>
              <span className="cd-fill" style={frac(bar.pages / tallest)} />
              <span className="cd-label">{barLabel(bar)}</span>
            </button>
          );
        })}
      </div>
      {chosen && (
        <p className="cd-picked">
          Narrowed to the {chosen.pages} page{chosen.pages === 1 ? "" : "s"} at{" "}
          {barLabel(chosen)}.{" "}
          <button type="button" className="cd-clear" onClick={() => onPick(null)}>
            show every depth
          </button>
        </p>
      )}
    </section>
  );
}
