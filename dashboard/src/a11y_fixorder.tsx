/** The Accessibility part's two "now" blocks (brief v16e, item 136f).
 *
 *  **Block 1, site scope** — a waterfall of fixes, tallest first, with a
 *  dashed remainder falling across it. Each bar is one piece of work and its
 *  height is the *instances* it removes, never the rows: one row saying
 *  "12 links on / have no accessible name" is twelve instances and one fix,
 *  and before 136j Part A that number lived inside an English sentence where
 *  nothing could add it up.
 *
 *  **Block 2, page scope** — the page as the rendered pass saw it, with a
 *  box over each violation. Only for pages that pass visited: 5 of 227 on
 *  Acme at T2, so the absent state is the common one and says which run
 *  and tier decided it rather than showing an empty canvas.
 *
 *  Nothing here computes a classification. `runs.fix_order_payload` decides
 *  what is chrome, what is a template and what is page-by-page, because the
 *  denominators it needs (pages assessed BY THAT CHECK — 227 for the static
 *  ones, 5 for `axe-*` on the same run) are the server's to know.
 */
import { useEffect, useRef, useState } from "react";
import { Pill } from "./pill";

/** One bar. `assessed` is the population its `pages` is a share of, and the
 *  two differ by check, which is why it travels per step. */
export type FixStep = {
  check: string; selector: string; kind: "chrome" | "template" | "page";
  instances: number; pages: number; assessed: number; share: number;
  landmarks: string[]; severity: string; example: string; rects: number;
  selectors?: number; label: string;
};

export type FixOrder = {
  total: number; steps: FixStep[]; clears_75_at: number | null;
  crawled: number; rendered: number; sum: number;
};

/** A violation's box on the page image. */
export type Barrier = {
  n: number; check: string; selector: string; impact: string;
  help: string; rect?: { x: number; y: number; w: number; h: number };
  chrome?: boolean;
};

/** Which token a step's bar takes. The three kinds are three different
 *  pieces of work, not three severities, and the tones say so: the site's
 *  furniture is one edit everywhere (bad, because it is everywhere), a
 *  template is one edit over a group (warn), and page-by-page is the long
 *  tail (mute). */
const KIND_TONE: Record<string, string> = {
  chrome: "bad", template: "warn", page: "mute",
};

const KIND_WORD: Record<string, string> = {
  chrome: "site chrome — one edit, every page",
  template: "one template — one edit, that group of pages",
  page: "page by page",
};

/** How tall the tallest bar is drawn, in px. Fixed, so the block does not
 *  grow with the count: a site with four thousand instances and one with
 *  forty draw the same shape. */
const PLOT = 180;

export function stepTone(step: FixStep): string {
  return KIND_TONE[step.kind] ?? "mute";
}

/** What a bar's hover says. The denominator is in it because a share means
 *  nothing without one, and an `axe-*` step's is not the crawl. */
export function stepTitle(step: FixStep): string {
  const bits = [
    step.check || "several checks",
    `${step.instances} instance${step.instances === 1 ? "" : "s"}`,
    `on ${step.pages} of ${step.assessed} page${step.assessed === 1 ? "" : "s"} this check assessed`,
    KIND_WORD[step.kind] ?? step.kind,
  ];
  if (step.example) bits.push(`e.g. ${pathOnly(step.example)}`);
  return bits.join(" · ");
}

function pathOnly(url: string): string {
  try { return new URL(url).pathname || "/"; } catch { return url; }
}

/** Block 1. */
export function FixOrderWaterfall({ order, onStep }: {
  order: FixOrder | null | undefined;
  onStep?: (step: FixStep) => void;
}) {
  if (!order) {
    return (
      <p className="muted fixorder-none">
        No accessibility instances are open on this site, or this audit predates
        the pass that records them. A re-check fills it.
      </p>
    );
  }
  if (!order.steps.length) {
    return <p className="muted fixorder-none">Nothing open to order.</p>;
  }
  const tallest = Math.max(...order.steps.map((s) => s.instances), 1);
  let left = order.total;
  const remainder = order.steps.map((s) => (left -= s.instances));
  const after = order.clears_75_at;
  return (
    <div className="fixorder">
      <div className="fixorder-head">
        <span className="fixorder-open">
          <b>{order.total}</b> instance{order.total === 1 ? "" : "s"} open now
        </span>
        {after != null && (
          <Pill tone="state-fixed" className="fixorder-after">
            after step {after}: {remainder[after - 1]} left
          </Pill>
        )}
      </div>
      {/* The sum is the block's own honesty check. `fix_order_payload`
          carries both numbers so the screen can say when they disagree
          rather than drawing bars that quietly do not add up. */}
      {order.sum !== order.total && (
        <p className="muted fixorder-drift" role="note">
          These steps account for {order.sum} of {order.total} open instances.
          The difference is instances no step could be built for.
        </p>
      )}
      <ol className="fixorder-plot" style={{ height: `${PLOT + 46}px` }}>
        {order.steps.map((s, i) => (
          <li key={`${s.check}-${s.kind}-${i}`} className="fixorder-step">
            <button type="button"
                    className={`fixorder-bar tone-${stepTone(s)}`}
                    style={{ height: `${Math.max(3, (s.instances / tallest) * PLOT)}px` }}
                    title={stepTitle(s)}
                    aria-label={`${s.label}, ${s.instances} instances, ${KIND_WORD[s.kind]}`}
                    onClick={() => onStep?.(s)}>
              <span className="fixorder-n">{s.instances}</span>
            </button>
            {/* The remainder after this step, as a dashed rule across the
                bar it follows. */}
            <i className="fixorder-rest"
               style={{ bottom: `${(remainder[i] / tallest) * PLOT}px` }}
               aria-hidden="true" />
            <span className="fixorder-label">{s.label}</span>
          </li>
        ))}
      </ol>
      <p className="muted fixorder-axis">
        Height is instances removed, not rows. Static checks read all{" "}
        {order.crawled} crawled page{order.crawled === 1 ? "" : "s"};{" "}
        <code>axe-*</code> reads the {order.rendered} the rendered pass
        visited, so a share is always of the pages that check assessed.
      </p>
    </div>
  );
}

/** A box on a screenshot: its number, where it is in the document, its tone
 *  and the name a screen reader gives it. */
export type ShotBox = { n: number; rect: { x: number; y: number; w: number; h: number };
                        tone: string; label: string };

/** The page's screenshot with a numbered box per region (item 245 lifted it
 *  out of `BarrierOverlay`, so Accessibility and Content draw one overlay,
 *  not two). Scaled by shown width / document width; a box pressed selects
 *  its number, and pressed again clears it. The selected box is scrolled
 *  into view when the selection comes from elsewhere - a row. */
export function ShotBoxes({ src, docW, alt, boxes, selected, onSelect }: {
  src: string; docW: number; alt: string; boxes: ShotBox[];
  selected: number | null; onSelect: (n: number | null) => void;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = box.current;
    if (!el || !docW) return;
    const fit = () => setScale(el.clientWidth / docW);
    fit();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [docW, src]);
  useEffect(() => {
    if (selected == null) return;
    box.current?.querySelector(`[data-box="${selected}"]`)
      ?.scrollIntoView({ block: "center" });
  }, [selected]);
  // Smaller boxes last so they sit on top of the ones that contain them.
  const drawn = [...boxes].sort((a, b) => (b.rect.w * b.rect.h) - (a.rect.w * a.rect.h));
  return (
    <div className="overlay-shot" ref={box}>
      <img src={src} alt={alt} />
      {drawn.map((b) => {
        const zero = b.rect.w === 0 || b.rect.h === 0;
        return (
          <button key={b.n} type="button" data-box={b.n}
                  className={`overlay-box tone-${b.tone}`
                             + (zero ? " overlay-zero" : "")
                             + (selected === b.n ? " is-sel" : "")}
                  style={{
                    left: `${b.rect.x * scale}px`,
                    top: `${b.rect.y * scale}px`,
                    width: `${Math.max(zero ? 12 : 1, b.rect.w * scale)}px`,
                    height: `${Math.max(zero ? 12 : 1, b.rect.h * scale)}px`,
                  }}
                  aria-label={b.label} aria-pressed={selected === b.n}
                  onClick={() => onSelect(selected === b.n ? null : b.n)}>
            <span className="overlay-badge">{b.n}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Block 2 — the page image with a box per violation.
 *
 *  Scaled by `shown width / document width`, which is why the payload
 *  carries the document dimensions the rects were measured against: a box
 *  placed by a ratio the image does not share lands somewhere else.
 */
export function BarrierOverlay({ src, docW, docH, barriers, tier, rendered,
                                crawled, selected, onSelect }: {
  src: string | null; docW: number; docH: number; barriers: Barrier[];
  tier?: string | null; rendered: number; crawled: number;
  selected: number | null; onSelect: (n: number | null) => void;
}) {
  if (!src) {
    return (
      <p className="muted overlay-none">
        The rendered pass did not visit this page in this audit
        ({rendered} of {crawled} page{crawled === 1 ? "" : "s"} rendered
        {tier ? ` at ${tier}` : ""}). Raise the tier or re-check this part to
        draw it.
      </p>
    );
  }
  const drawn = barriers.filter((b) => b.rect);
  const unplaced = barriers.filter((b) => !b.rect);
  return (
    <div className="overlay">
      <ShotBoxes src={src} docW={docW} selected={selected} onSelect={onSelect}
                 alt={`${docW} by ${docH} screenshot of the page, with `
                      + `${drawn.length} barrier${drawn.length === 1 ? "" : "s"} marked`}
                 boxes={drawn.map((b) => ({
                   n: b.n, rect: b.rect!, tone: toneOf(b.impact),
                   label: `violation ${b.n}, ${plainCheck(b.check)}, ${b.impact}` }))} />
      <ol className="overlay-rows">
        {barriers.map((b) => (
          <li key={b.n}
              className={`overlay-row${selected === b.n ? " is-sel" : ""}`}>
            <button type="button" className="overlay-rowbtn"
                    aria-current={selected === b.n ? "true" : undefined}
                    onClick={() => onSelect(selected === b.n ? null : b.n)}>
              <i className={`overlay-badge tone-${toneOf(b.impact)}`}>{b.n}</i>
              <code className="overlay-check">{b.check}</code>
              {b.chrome && (
                <span className="muted overlay-chrome">
                  · site chrome, on every page
                </span>
              )}
              <code className="overlay-sel">{trunc(b.selector, 48)}</code>
              <span className="overlay-help">{b.help}</span>
              {!b.rect && (
                <span className="muted overlay-noplace">position not recorded</span>
              )}
              {b.rect && b.rect.w === 0 && (
                <span className="muted overlay-noplace">not visible on the page</span>
              )}
            </button>
          </li>
        ))}
        {unplaced.length === 0 && barriers.length === 0 && (
          <li className="muted">No accessibility barriers on this page.</li>
        )}
      </ol>
    </div>
  );
}

/** Two tones, not five. Serious and critical are the ones a person cannot
 *  work around; moderate and minor are the ones they can. */
export function toneOf(impact: string): string {
  return impact === "critical" || impact === "serious" ? "bad" : "warn";
}

function plainCheck(id: string): string {
  return id.replace(/^axe-/, "").replace(/-/g, " ");
}

function trunc(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
