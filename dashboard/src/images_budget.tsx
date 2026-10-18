/** The Images part page's two budget blocks (brief v16c).
 *
 *  **Bytes for pixels**, a scatter of every image the crawl could weigh:
 *  across, the box it is drawn at; up, what it cost to send. And **every
 *  image as the visitor sees it**, the page's own thumbnails with a frame
 *  where a check fired.
 *
 *  **Nothing here decides anything.** Every state a dot or a frame paints
 *  arrives on the payload from `persistence.runs.image_state`, which calls
 *  the same `onp.image_weight_state` that raises `img-heavy`, and
 *  `alt_missing` is `img-alt-missing`'s own rule. That is the item's
 *  requirement written as a dependency rather than as a comment: there is
 *  no arithmetic in this file for a later edit to the check to disagree
 *  with. The only numbers computed here are pixel positions.
 *
 *  **The budget lines come from the registry**, on the payload as
 *  `budget`, for the same reason - a ceiling drawn from a constant in a
 *  renderer is a picture of a rule the product does not apply.
 */
import { stamp } from "./client_lanes";
import { useEffect, useRef, useState } from "react";

import { ImageRecord } from "./anatomy";
import { MEASURE_WORD } from "./measure";

/** The file at the end of a URL. Lives here rather than in `part_page.tsx`
 *  because both blocks name files and `part_page` imports this module; the
 *  other direction would be a cycle. */
export const fileOf = (src: string) => {
  const clean = (src || "").split("?")[0].split("#")[0];
  return clean.slice(clean.lastIndexOf("/") + 1) || clean;
};

/** The file an image record is (item 241). Where `src` is a script lazy
 *  loader's `data:` placeholder - 271 of twenty22's 366 images - the file
 *  the loader swaps in, else the one the browser fetched. Drawn and named
 *  from this, a lazy image was a blank tile called `svg%3E` with "no
 *  extension", over a page whose pictures were all there. */
export const fileSrc = (i: { src: string; lazy_src?: string | null; resolved?: string | null }) =>
  !(i.src || "").startsWith("data:") ? i.src
    : i.lazy_src || (i.resolved && !i.resolved.startsWith("data:") ? i.resolved : "") || i.src;

/** The three numbers the site record carries, or the check's own defaults
 *  where it carries none. Resolved on the server so both blocks and the
 *  finding are drawn against one set. */
export type ImageBudget = { floor_kb: number; image_kb: number;
                            bytes_per_pixel: number };

/** One drawable image: a weight the browser saw, against a box it
 *  measured. An image missing either is not on this list — it is in
 *  `unmeasured` or `unplaced` and the block says so in words. */
export type ImageDot = {
  src: string; page: string; w: number; h: number; kb: number;
  /** The viewport width the box was measured at (item 272, row 7). */
  at?: number | null;
  bytes_per_pixel: number | null; alt_missing: boolean; decorative: boolean;
  state: "ok" | "warn" | "bad" | "mute";
  /** One dot per distinct image (item 241): the paths it is on, how many
   *  times it is placed, and where its weight came from - the browser's
   *  record of the fetch, or the server's size header. */
  paths: string[]; placements: number; weight_source: "resource" | "header" | null;
};

export type ImageBudgetPayload = {
  run_id: string; scope: string | null; budget: ImageBudget;
  dots: ImageDot[]; total: number; drawable: number;
  unmeasured: number; unplaced: number; pages: number;
  /** Placements drawn, and the pages the browser pass looked at (item 241). */
  placements: number; weighed_pages: number;
  /** Each page's own count (item 272, row 7). */
  per_page?: Record<string, { total: number; unmeasured: number; unplaced: number;
                              placed: number }>;
  recorded: boolean;
  /** Whether the audit measured images in a browser (item 205). */
  measured: boolean | "unavailable";
  /** Whether any image was seen as a page's largest paint (item 272). */
  lcp_found?: boolean;
  tier?: string | null; started_at?: string | null;
};

const KB = 1024;
/** The x axis, item 241: from a 40-pixel square to at least 800×600. */
const PX_AXIS_LO = 40;
const PX_AXIS_MIN = 800 * 600;

/** The page-mode note, reconciled as site mode's is (item 272, row 7):
 *  "11 images on /: 7 distinct drawn, 2 with no rendered box, 3 repeat
 *  placements". It read "7 distinct images on /" over a wall of 11. */
export function pageNote(t: { total: number; unmeasured: number; unplaced: number; placed: number }
                           | undefined, distinct: number, scope: string): string {
  const s = (n: number) => (n === 1 ? "" : "s");
  if (!t) return `${distinct} distinct image${s(distinct)} ${scope}.`;
  const parts = [`${distinct} distinct drawn`];
  if (t.placed > distinct) parts.push(`${t.placed - distinct} repeat placement${s(t.placed - distinct)}`);
  if (t.unplaced) parts.push(`${t.unplaced} with no rendered box`);
  if (t.unmeasured) parts.push(`${t.unmeasured} not weighed`);
  return `${t.total} image${s(t.total)} ${scope}: ${parts.join(", ")}.`;
}

/** "on /about/" or "on 26 pages" - where a distinct image is placed. */
// "at this size" (screen audits round 4, Images IP-04, AC-06): a dot is one
// file at one drawn size, so the logo read "on 40 pages" here and 45 on its
// row, which counts the file at every size.
const onPages = (d: ImageDot) =>
  d.paths.length === 1 ? `on ${d.paths[0]} at this size` : `on ${d.paths.length} pages at this size`;
/** The tick values the mockup names, drawn where they fall inside the run's
 *  own range and left off where they do not. */
const PX_TICKS: [number, string][] = [[40 * 40, "40²"], [200 * 150, "200×150"],
                                      [400 * 300, "400×300"], [800 * 600, "800×600"],
                                      [1200 * 720, "1200×720"]];
const KB_TICKS = [10, 20, 50, 100, 200, 500];

/** The plot box inside the viewBox, in the viewBox's own units. */
const L = 70, R = 1080, T = 20, B = 380;
/** "1 byte", "1.5 bytes" (item 272, row 12): the site record's ceiling is
 *  often 1, and "1 bytes a pixel" was on screen. */
const bytes = (n: number) => `${n} ${n === 1 ? "byte" : "bytes"}`;

const pathOf = (u: string) => { try { return new URL(u).pathname || "/"; } catch { return u; } };

/** Which file an image reference names, wherever it is written (item 244):
 *  a dot's `src`, a wall tile's file and a finding's `image` are the same
 *  image when they resolve, against the page they were read on, to one
 *  path - whether written relative, absolute or as the markup had it. */
export const imageKey = (src: string | null | undefined, base: string) => {
  if (!src) return "";
  try { return new URL(src, base).pathname; } catch { return src; }
};

/** The dot's own key: its file, resolved against the page it was read on. */
export const dotKey = (d: ImageDot) => imageKey(d.src, d.page);

/** "the logo", "hero.jpg": a picked image's name, as a chip says it. */
export const pickedName = (d: ImageDot) => fileOf(d.src) || d.src;

/** Block 1: one dot per image, against the budget the registry states.
 *
 *  x is square-root on pixels and y is log10 on bytes, as the mockup: an
 *  axis linear in either would put every thumbnail in one corner and one
 *  hero photograph in the other, which is a picture of the scales and not
 *  of the site.
 *
 *  The top of x is the largest box the run measured rather than a fixed
 *  1200×720 — a site whose largest image renders at 300px should not be
 *  drawn in the left third of a chart sized for somebody else's.
 */
export function BytesForPixels({ payload, page, picked = null, onPick }: {
  payload: ImageBudgetPayload | null | undefined;
  /** The page filter, when the scope bar names one: the same dots, narrowed. */
  page: string;
  /** The image a press selected, and how to select one (item 244). A press
   *  used to narrow the whole part to the dot's first page, which since item
   *  241 is one of the image's pages - the logo's first of 40 - chosen for
   *  the reader and the other 39 dropped without a word. */
  picked?: ImageDot | null;
  onPick?: (dot: ImageDot | null) => void;
}) {
  const [tip, setTip] = useState<{ dot: ImageDot; x: number; y: number } | null>(null);
  // Screen audits round 3 (Images UX-01): one tab stop for the whole chart,
  // not one per dot. twenty22 drew 108 dots, each `tabIndex=0`, in stacks of
  // 8 to 12 at one point, and a keyboard reader tabbed 108 times to reach the
  // checks table. The arrow keys move between dots, left to right (a roving
  // tab stop); Tab leaves the chart.
  const [roving, setRoving] = useState(0);
  const chart = useRef<SVGSVGElement | null>(null);
  if (!payload) return null;
  const { budget } = payload;
  // Item 241: a dot is a distinct image, on every page it is placed on.
  const here = page ? payload.dots.filter((d) => d.paths.includes(pathOf(page))) : payload.dots;
  const scope = page ? `on ${pathOf(page)}` : "on the site";
  const pickedKey = picked ? dotKey(picked) : null;
  // Pressing the selected dot again clears it, as the chip's × does.
  const toggle = (d: ImageDot) => onPick?.(pickedKey === dotKey(d) ? null : d);

  const lede = (
    <p className="muted ib-lede">
      {/* Item 205: whose numbers these are, in the provenance line's words. */}
      {payload.tier ? `From audit ${payload.tier}${payload.started_at
        ? ` ${stamp(payload.started_at)}` : ""}. ` : ""}
      One dot per image the crawl weighed at each size it is drawn, however many
      pages it is on there. Across: how large it is drawn on the
      page. Up: how many bytes it cost to send. The shaded band is the budget —
      an image above the band is paying for pixels nobody sees; below the floor
      it is not worth touching. Hover a dot for the file; press it to see that image&rsquo;s problems and pages.
    </p>
  );

  if (!here.length) {
    // Absent, and visibly not zero (the contract). Three different
    // sentences, because "this crawl found no images", "nobody weighed
    // them" and "none of them are on this page" are three different
    // situations and an operator acts on each of them differently.
    //
    // Item 205: and two more before them, because "the pass found nothing"
    // and "the pass did not run" were one sentence - the CDN one - and on
    // twenty22 it explained same-origin images the audit had never measured.
    const why = !payload.recorded
      ? "This crawl recorded no images at all."
      : payload.measured === "unavailable"
        ? "No renderer was installed when this audit ran, so no image on it was "
          + "weighed or measured on the page."
      : payload.measured === false
        ? "This audit did not measure images in a browser, so nothing here has a "
          + "weight or a rendered size."
      : page
        ? `Nothing on ${pathOf(page)} carries both a measured weight and a rendered box.`
        : `None of the ${payload.total} images this crawl recorded carry a `
          + "transferred weight. A browser reports zero bytes for an image served "
          + "from another origin without Timing-Allow-Origin, and this product "
          + "reads a zero as “not measured” rather than as a weightless "
          + "image — so a site whose images sit on a CDN is weighed by nobody.";
    return (
      <section className="ib-block ib-block-scatter">
        <h4>Bytes for pixels</h4>
        {lede}
        <p className="muted ib-absent">{why} There is nothing to plot, which is
          not the same as every image being inside its budget.</p>
      </section>
    );
  }

  // Item 241: a stable axis, from 40² to at least 800×600. Scaled to the
  // largest box alone, one distinct size put every dot on the right edge and
  // drew one tick; a small image is drawn where a small image belongs.
  const pxMax = Math.max(...here.map((d) => d.w * d.h), PX_AXIS_MIN);
  const kbMax = Math.max(...here.map((d) => d.kb),
                         // Room above the ceiling at the widest box, so the
                         // budget line itself is never drawn off the top.
                         (pxMax * budget.bytes_per_pixel) / KB, budget.floor_kb * 2);
  const lx = (px: number) => L + ((Math.sqrt(Math.max(px, PX_AXIS_LO * PX_AXIS_LO)) - PX_AXIS_LO)
                                  / (Math.sqrt(pxMax) - PX_AXIS_LO)) * (R - L);
  const ly = (kb: number) => B - (Math.log10(kb + 1) / Math.log10(kbMax + 1)) * (B - T);

  // The ceiling, sampled geometrically because x is a square root: even
  // steps in pixels would draw a straight line as a polygon of one point at
  // the left and forty at the right.
  //
  // **Clipped at the flat ceiling**, which the mockup does not draw. The
  // check has two arms — bytes per pixel, and a flat per-image kilobyte
  // ceiling — and an image over the flat one is `img-heavy` however large
  // it renders. Drawing only the diagonal would put a warn dot inside the
  // shaded band, and a band that contradicts the dots in it is worse than
  // one line more. Both numbers are the registry's.
  const ceiling = (px: number) => Math.min((px * budget.bytes_per_pixel) / KB, budget.image_kb);
  const samples: number[] = [];
  for (let px = PX_AXIS_LO * PX_AXIS_LO; px <= pxMax; px *= 1.15) samples.push(px);
  samples.push(pxMax);
  const band = samples.map((px) => `${lx(px)},${ly(Math.max(ceiling(px), budget.floor_kb))}`)
                      .join(" ");
  // Where the per-pixel arm meets the flat per-file one, within the axis.
  const flatAt = Math.min(Math.max((budget.image_kb * KB) / budget.bytes_per_pixel,
                                   PX_AXIS_LO * PX_AXIS_LO * 4), pxMax);

  // Where each dot is drawn, its place in the arrow keys' order (across, then
  // up), and the dots that share its point: a stack reads "3 of 9 at this
  // point" so the reader knows the next arrow stays where it is.
  const xy = here.map((d) => [Math.min(lx(d.w * d.h), R - 6), ly(d.kb)] as const);
  const order = here.map((_, n) => n)
    .sort((a, b) => xy[a][0] - xy[b][0] || xy[b][1] - xy[a][1]);
  const rank = new Map(order.map((n, i) => [n, i] as const));
  const spot = (n: number) => `${Math.round(xy[n][0])}:${Math.round(xy[n][1])}`;
  const stacks = new Map<string, number[]>();
  for (const n of order) stacks.set(spot(n), [...(stacks.get(spot(n)) ?? []), n]);
  const stackNote = (n: number) => {
    const s = stacks.get(spot(n)) ?? [];
    return s.length > 1 ? ` (${s.indexOf(n) + 1} of ${s.length} at this point)` : "";
  };
  const current = order[Math.min(roving, order.length - 1)] ?? 0;
  const step = (from: number, by: number) => {
    const i = Math.max(0, Math.min(order.length - 1, (rank.get(from) ?? 0) + by));
    setRoving(i);
    chart.current?.querySelectorAll<SVGCircleElement>("circle.ib-dot")[order[i]]?.focus();
  };

  const named = (d: ImageDot) =>
    `${fileOf(d.src)}, ${d.w} by ${d.h} pixels${d.at ? ` at ${d.at} wide` : ""}, ${d.kb} kilobytes`
    + (d.weight_source === "header" ? " by the server's size header" : "")
    + (d.alt_missing ? ", no alt text" : "") + `, ${onPages(d)}`;

  return (
    <section className="ib-block ib-block-scatter">
      <h4>Bytes for pixels</h4>
      {lede}
      {/* `role="group"` and not `role="img"`. The dots are buttons, and axe
          calls a labelled image containing focusable children
          `nested-interactive` — correctly: a picture is a leaf, and this one
          is not. A labelled group is what a chart whose marks are controls
          actually is, and the label below is still the sentence a reader who
          cannot see it needs. */}
      <svg ref={chart} className={`ib-scatter${pickedKey ? " ib-has-pick" : ""}`} viewBox="0 0 1100 420" role="group"
           aria-label={`${here.length} images ${scope}, plotted by rendered size against `
                       + `transferred weight, against a ceiling of `
                       + `${bytes(budget.bytes_per_pixel)} a pixel and a `
                       + `${budget.floor_kb} KB floor. Arrow keys move between the images; `
                       + "Tab leaves the chart"}>
        <polygon className="ib-band"
                 points={`${lx(samples[0])},${ly(budget.floor_kb)} ${band} `
                         + `${R},${ly(budget.floor_kb)}`} />
        <polyline className="ib-ceiling" points={band} />
        {/* Item 272 (row 12): anchored at the bend, left of the flat
            segment, and 14 above the line, so it neither runs along the flat
            part nor sits on the dots under it. */}
        <text className="ib-ceiling-name" x={lx(flatAt) - 6} textAnchor="end"
              y={ly(Math.max(ceiling(flatAt), budget.floor_kb)) - 14}>
          budget for its size
        </text>
        <line className="ib-floor" x1={L} y1={ly(budget.floor_kb)} x2={R}
              y2={ly(budget.floor_kb)} />
        <text className="ib-floor-name" x={R} y={ly(budget.floor_kb) - 5} textAnchor="end">
          {budget.floor_kb} KB floor — below this, not scored
        </text>
        {PX_TICKS.filter(([v]) => v <= pxMax).map(([v, label]) => (
          <text key={label} className="ib-tick" x={lx(v)} y={B + 18} textAnchor="middle">
            {label}
          </text>
        ))}
        {KB_TICKS.filter((kb) => kb <= kbMax).map((kb) => (
          <text key={kb} className="ib-tick" x={L - 8} y={ly(kb) + 4} textAnchor="end">
            {kb} KB
          </text>
        ))}
        <line className="ib-axis" x1={L} y1={B} x2={R} y2={B} />
        <line className="ib-axis" x1={L} y1={T} x2={L} y2={B} />
        <text className="ib-axis-name" x={(L + R) / 2} y={B + 38} textAnchor="middle">
          drawn size on the page
        </text>
        {here.map((d, n) => (
          /* A dot is a control — it selects its image — so it carries a
             role, a tab stop, a name and whether it is pressed, which is what
             `test_no_click_handlers_on_non_interactive_elements` asks of
             anything with an onClick. */
          <circle key={`${d.src}-${d.page}-${n}`}
                  className={`ib-dot ib-${d.state}${d.weight_source === "header" ? " ib-header" : ""}`
                             + (pickedKey && dotKey(d) === pickedKey ? " ib-picked" : "")}
                  aria-pressed={Boolean(pickedKey && dotKey(d) === pickedKey)}
                  cx={xy[n][0]} cy={xy[n][1]} r={d.state === "mute" ? 3 : 4.5}
                  role="button" tabIndex={n === current ? 0 : -1} aria-label={named(d) + stackNote(n)}
                  onMouseEnter={(e) => setTip({ dot: d, x: e.clientX, y: e.clientY })}
                  onMouseMove={(e) => setTip({ dot: d, x: e.clientX, y: e.clientY })}
                  onMouseLeave={() => setTip(null)}
                  onFocus={(e) => {
                    setRoving(rank.get(n) ?? 0);
                    const box = (e.target as SVGCircleElement).getBoundingClientRect();
                    setTip({ dot: d, x: box.left, y: box.top });
                  }}
                  onBlur={() => setTip(null)}
                  onClick={() => toggle(d)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(d); }
                    else if (e.key === "ArrowRight" || e.key === "ArrowUp") { e.preventDefault(); step(n, 1); }
                    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") { e.preventDefault(); step(n, -1); }
                    else if (e.key === "Home") { e.preventDefault(); step(n, -order.length); }
                    else if (e.key === "End") { e.preventDefault(); step(n, order.length); }
                  }} />
        ))}
      </svg>
      <div className="ib-legend">
        <span><i className="ib-key-ok" />within budget</span>
        <span><i className="ib-key-warn" />over budget for its size</span>
        <span><i className="ib-key-bad" />over budget and missing alt</span>
        <span><i className="ib-key-mute" />under the {budget.floor_kb} KB floor, not scored</span>
        {/* Keyed only where one is drawn: a legend names what is on it. */}
        {here.some((d) => d.weight_source === "header") && (
          <span><i className="ib-key-header" />hollow: weighed by the server's size header, not seen fetched</span>
        )}
      </div>
      {/* What is not on the chart, said rather than left to be inferred from
          a count that looks small. */}
      <p className="muted ib-note">
        {/* Item 241: placements and distinct images are two numbers, and
            the chart draws the second. */}
        {page
          ? pageNote(payload.per_page?.[pathOf(page)], here.length, scope)
          : `${payload.placements} placement${payload.placements === 1 ? "" : "s"} of `
            + `${here.length} distinct image${here.length === 1 ? "" : "s"} weighed, `
            + `of ${payload.total} images the crawl recorded.`}
        {/* Item 272 (row 8): the 48 is the pages with a stored snapshot, not
            the crawl's 45, and says so - two page counts on one screen with
            nothing to tell them apart read as one disagreeing with itself. */}
        {!page && payload.weighed_pages < payload.pages
          ? ` Weighed on ${payload.weighed_pages} of the ${payload.pages} pages with a stored snapshot.`
          : ""}
        {!page && payload.unmeasured > 0
          ? ` ${payload.unmeasured} carry no transferred weight, so they are not plotted.`
          : ""}
        {!page && payload.unplaced > 0
          ? ` ${payload.unplaced} were weighed but never measured on screen.`
          : ""}
        {!page && payload.drawable > here.length
          ? ` This chart stops at ${here.length} of ${payload.drawable} it could draw.`
          : ""}
        {" "}The ceiling is {bytes(budget.bytes_per_pixel)} a rendered pixel and{" "}
        {budget.image_kb} KB a file, from the site record.
      </p>
      {tip && (
        <div className="ib-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          <code>{tip.dot.src}</code>
          <div className="ib-tip-line">
            {tip.dot.w}&times;{tip.dot.h} drawn{tip.dot.at ? ` at ${tip.dot.at}` : ""} &middot; {tip.dot.kb} KB
            {tip.dot.bytes_per_pixel != null
              ? ` · ${tip.dot.bytes_per_pixel} B/px` : ""}
            {tip.dot.alt_missing ? <b className="ib-tip-bad"> &middot; no alt</b> : null}
          </div>
          {tip.dot.weight_source === "header" && (
            <div className="ib-tip-line">weight from the server&rsquo;s size header; the page
              did not fetch it while measured</div>
          )}
          <div className="ib-tip-line">
            {onPages(tip.dot)}
            {tip.dot.paths.length > 1
              ? `: ${tip.dot.paths.slice(0, 3).join(", ")}${tip.dot.paths.length > 3 ? ", …" : ""}`
              : ""}
          </div>
        </div>
      )}
    </section>
  );
}

/** How many pages a list shows before "show all", as elsewhere. */
const PAGES_SHOWN = 12;

/** The pages an image is on, each one press from opening it (item 244). */
function PagesOf({ dot, onPage }: { dot: ImageDot; onPage?: (url: string) => void }) {
  const [all, setAll] = useState(false);
  const origin = (() => { try { return new URL(dot.page).origin; } catch { return ""; } })();
  const shown = all ? dot.paths : dot.paths.slice(0, PAGES_SHOWN);
  return (
    <>
      <ul className="ib-pages">
        {shown.map((p) => (
          <li key={p}>
            <button type="button" className="btn-link" onClick={() => onPage?.(origin + p)}>{p}</button>
          </li>
        ))}
      </ul>
      {dot.paths.length > PAGES_SHOWN && (
        <button type="button" className="btn-link ib-pages-all" onClick={() => setAll((v) => !v)}>
          {all ? "show fewer" : `show all ${dot.paths.length}`}
        </button>
      )}
    </>
  );
}

/** The filter a pressed dot sets, stated (item 244): the file and how many
 *  pages it is on, opening to those pages; × clears it. The part's page is
 *  not touched by a dot - going to a page is one more press, on a page the
 *  reader chose. */
export function PickedImage({ dot, onClear, onPage }: {
  dot: ImageDot; onClear: () => void; onPage?: (url: string) => void;
}) {
  return (
    <div className="ib-picked-chip" role="status">
      <details>
        <summary>
          image: <code>{pickedName(dot)}</code> · {onPages(dot)}
        </summary>
        <PagesOf dot={dot} onPage={onPage} />
      </details>
      <button type="button" className="btn-link ib-picked-clear" onClick={onClear}
              aria-label={`clear the image filter (${pickedName(dot)})`}>×</button>
    </div>
  );
}

/** Block 2: the page's own images, in DOM order.
 *
 *  Not a count — the actual pictures, so "which one" is answered by
 *  looking. The states are the ones the server stamped onto each inventory
 *  record, so a frame and a finding cannot disagree.
 *
 *  **The thumbnail is the image itself, from its own URL.** The crawl
 *  stores no image bytes — `imaging.measure` records what a browser saw of
 *  each file and never the file — so "the crawl's stored image bytes" do
 *  not exist to read. The image card this block sits beneath has rendered
 *  `<img src={record.src}>` since brief v15, and doing the same here is one
 *  mechanism rather than two; where the URL does not load, the tile is the
 *  grey box with its dimensions that the item asks for, which is what an
 *  `<img>` that fails to paint leaves behind.
 */
export function ImageWall({ inventory, page, budget, picked = null, onPage }: {
  inventory: ImageRecord[] | null | undefined; page: string; budget: ImageBudget | null;
  /** The image a dot selected (item 244): at site scope the wall lists the
   *  pages it is on, each opening that page; on a page it marks the tile
   *  and brings it into view. */
  picked?: ImageDot | null;
  onPage?: (url: string) => void;
}) {
  const heading = <h4>Every image, as the visitor sees it</h4>;
  const pickedKey = picked ? dotKey(picked) : null;
  const pickedTile = useRef<HTMLLIElement | null>(null);
  // `{ block: "center" }`, the tree's one scroll convention.
  useEffect(() => { pickedTile.current?.scrollIntoView({ block: "center" }); }, [pickedKey, page]);
  if (!page && picked) {
    return (
      <section className="ib-block ib-block-wall">
        {heading}
        <p className="muted ib-lede">
          <code>{pickedName(picked)}</code> is on {picked.paths.length === 1
            ? "one page" : `${picked.paths.length} pages`}. Open one to see it among
          that page&rsquo;s images.
        </p>
        <PagesOf dot={picked} onPage={onPage} />
      </section>
    );
  }
  if (!page) {
    return (
      <section className="ib-block ib-block-wall">
        {heading}
        <p className="muted ib-absent">Pick a page to see its images.</p>
      </section>
    );
  }
  const rows = inventory ?? [];
  if (!rows.length) {
    return (
      <section className="ib-block ib-block-wall">
        {heading}
        <p className="muted ib-absent">
          This crawl recorded no images on {pathOf(page)}.
        </p>
      </section>
    );
  }
  const over = rows.filter((i) => i.state === "warn" || i.state === "bad");
  const noAlt = rows.filter((i) => i.alt_missing);
  const weighed = rows.filter((i) => i.kb != null);
  const weight = weighed.reduce((n, i) => n + (i.kb ?? 0), 0);
  return (
    <section className="ib-block ib-block-wall">
      {heading}
      <p className="muted ib-lede">
        Thumbnails in page order. A red frame is missing alt; an amber frame is
        over budget. Nothing here is a count — it is the actual images, so
        &ldquo;which one&rdquo; is answered by looking.
      </p>
      <div className="ib-figures">
        <div><b>{rows.length}</b>images on {pathOf(page)}</div>
        <div className="ib-fig-bad"><b>{noAlt.length}</b>missing alt</div>
        <div className="ib-fig-warn"><b>{over.length}</b>over budget</div>
        <div>
          <b>{(weight / KB).toFixed(1)} MB</b>
          {weighed.length === rows.length
            ? "image weight on this page"
            : `image weight, from the ${weighed.length} that were weighed`}
        </div>
      </div>
      <ul className="ib-wall">
        {rows.map((i, n) => {
          const big = i.state === "warn" || i.state === "bad";
          const frame = i.alt_missing && big ? "both" : i.alt_missing ? "alt" : big ? "big" : "";
          return (
            <li key={`${fileSrc(i)}-${n}`}
                ref={pickedKey && imageKey(fileSrc(i), page) === pickedKey ? pickedTile : undefined}
                className={`ib-tile${frame ? ` ib-tile-${frame}` : ""}`
                           + (pickedKey && imageKey(fileSrc(i), page) === pickedKey
                             ? " ib-tile-picked" : "")}>
              {/* The tile's own name, never the page's alt text: the alt is
                  what is being reported on, and reusing it would make a
                  missing one invisible to the reader who most needs it. */}
              <img className="ib-thumb" src={fileSrc(i)} loading="lazy"
                   alt={i.alt_missing ? "image without alt text" : fileOf(fileSrc(i))} />
              {i.alt_missing
                ? <span className="ib-tag ib-tag-alt">no alt</span>
                : big && i.kb != null
                  ? <span className="ib-tag ib-tag-big">{i.kb} KB</span>
                  : null}
              <span className="ib-cap">
                {i.drawn_w && i.drawn_h ? `${i.drawn_w}×${i.drawn_h}` : MEASURE_WORD["not-measured"]}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="muted ib-note">
        A frame is a check that fired, not a second opinion about one:
        {" "}<code>img-alt-missing</code> for the red and <code>img-heavy</code>
        {" "}for the amber.
        {budget
          ? ` Over budget means past ${bytes(budget.bytes_per_pixel)} a rendered `
            + `pixel or ${budget.image_kb} KB a file.`
          : ""}
        {weighed.length < rows.length
          ? ` ${rows.length - weighed.length} of these carry no transferred weight, `
            + "so nothing on them is over budget by measurement."
          : ""}
      </p>
    </section>
  );
}
