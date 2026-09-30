/** Where the score has been — the Audit pane's Score trend block (brief v16f).
 *
 *  The block used to be one paragraph. A chart stood above it until UX-06,
 *  which removed it for carrying no axis, no dates and nothing the table
 *  under it did not already say; what was left was the sentence naming every
 *  break. This draws the chart back, and the reason it is not the same chart
 *  is the whole of brief v16f: the breaks and the pairs are now two different
 *  facts, and neither of them is a list of prose.
 *
 *  **Nothing here decides whether two points are comparable.** `basis_key`,
 *  `partner_run_id` and `partner_index` arrive from `runs.site_trend`, which
 *  is the one place the four terms are weighed. This file decides where a dot
 *  goes and which tone it takes. That split is the same one `crawl_depth.tsx`
 *  and `images_budget.tsx` make, and here it is load-bearing rather than
 *  tidy: the Runs table's comparison link is built from the same
 *  `partner_run_id` this chart draws a line to, so a second opinion in
 *  TypeScript would let the picture and the link disagree about which audit
 *  reads against which.
 *
 *  **Two relations, drawn differently, because they answer different
 *  questions.** A dashed vertical rule marks a *step* where the basis key
 *  moved — `comparable`, the adjacent-step verdict. A line joins a point to
 *  its *partner* — the nearest earlier point measured the same way, which may
 *  be several points back. On the operator's own history the first is eight
 *  rules and the second is one arc, and collapsing them into one drawing is
 *  what made nine runs look like nine unrelated numbers.
 *
 *  **Tone.** `--good`, `--warn-strong` and `--danger` for the three score
 *  bands, `--warn-strong` for the break rules, `--info` for the current-basis
 *  band and `--text` for the lines. Item 140's rule applied before item 140
 *  lands: no new colour, and the bands are `SCORE_BANDS`' own — the chart
 *  cannot call 62 fair while the badge beside it calls it something else.
 */
import { useState } from "react";

import { TrendPoint } from "./api";
import { SCORE_BANDS } from "./components";

const trendDay = (iso: string) => (iso || "").slice(0, 10);
const trendMinute = (iso: string) => (iso || "").slice(11, 16);

/** Labels for a whole trend, carrying a time only where a date collides.
 *
 *  UI-22, seen on live data. The break label was composed from `trendDay` at
 *  both ends, so two runs on one day read `2026-08-15 → 2026-08-15` — the
 *  sentence saying *why* a line stopped being comparable, naming two points
 *  the operator then could not tell apart in the table under it. The points
 *  were 2h06m apart and `captured_at` carries the full stamp: the
 *  information was present and the render discarded it.
 *
 *  Decided once for the series rather than per adjacent pair, and that is
 *  the point rather than an economy. A label names a point the reader goes
 *  on to find in the Runs table below, so the two have to agree; a column
 *  showing a time on the two colliding rows and a date on the rest would put
 *  the burden back on the reader it was widened for. One rule, every label.
 *
 *  A stamp with no time component keeps its date rather than gaining a blank
 *  one, so a payload carrying a date-only `captured_at` degrades to exactly
 *  today's rendering instead of to `2026-08-15 `.
 */
export function trendLabels(points: TrendPoint[]): string[] {
  const days = points.map((p) => trendDay(p.captured_at));
  const collides = days.some((d, i) => days.indexOf(d) !== i);
  return points.map((p, i) => {
    const at = trendMinute(p.captured_at);
    return collides && at ? `${days[i]} ${at}` : days[i];
  });
}

/** Which terms of the frame differ between two adjacent points, in full and
 *  in the four characters a rotated axis label has room for.
 *
 *  Not a second comparability verdict — `comparable` already says *that* two
 *  points cannot be read against each other, and it is the server's to
 *  decide. This says *which* term moved, which is the part an operator needs
 *  in order to act, and it is read off two rows rather than judged. Where the
 *  server calls a boundary and no term here differs, the caller says so
 *  plainly rather than printing an empty reason.
 *
 *  **`short` is built beside `long`, not parsed back out of it.** The
 *  operator's mockup derived its rule labels from the prose with four regular
 *  expressions — `w.match(/→ ([\d.]+)/)` and its neighbours — which is a
 *  parser for a sentence written twenty lines above it, and the first
 *  reworded sentence would have produced `engine null`. The two forms of one
 *  fact are made in one place from the same two values.
 */
export function frameChanges(prev: TrendPoint, p: TrendPoint):
    { long: string; short: string }[] {
  const out: { long: string; short: string }[] = [];
  const unknown = (v: string | null | undefined) => v || "unknown";
  if (prev.tier !== p.tier)
    out.push({ long: `tier ${unknown(prev.tier)} → ${unknown(p.tier)}`,
               short: `${unknown(prev.tier)} → ${unknown(p.tier)}` });
  if (prev.engine_version !== p.engine_version)
    out.push({ long: `engine ${unknown(prev.engine_version)} → `
                     + `${unknown(p.engine_version)}`,
               short: `engine ${unknown(p.engine_version)}` });
  const before = prev.scope?.basis ?? null;
  const after = p.scope?.basis ?? null;
  if (before !== after)
    out.push({ long: `basis ${unknown(before)} → ${unknown(after)}`,
               short: `basis ${unknown(after)}` });
  // The fourth term, added with WF-58. Named here rather than left to the
  // caller's "the frame changed" fallback: the server breaks the line the
  // moment two runs measured different dimensions, and that break is the
  // commonest one an operator can cause — one click on the anatomy screen
  // launches a single-dimension run. A break nobody can name is a break
  // nobody acts on, which is the whole reason this function exists.
  //
  // Printed as what was added and what was dropped rather than as two lists.
  // Eight codes either side is a sentence nobody reads; "A11Y, PRF dropped"
  // is the fact. A set that changed in both directions says both.
  const dimsBefore = prev.scope?.dimensions ?? null;
  const dimsAfter = p.scope?.dimensions ?? null;
  if (dimsBefore === null || dimsAfter === null) {
    // One side never recorded its population, so nothing can be said about
    // what moved — only that the comparison has no ground. Distinguished from
    // a real difference because "unknown" is not a set that gained or lost
    // anything.
    if (dimsBefore !== dimsAfter)
      out.push({ long: "dimensions unknown on one of the two audits",
                 short: "dimensions ?" });
  } else {
    const added = dimsAfter.filter((d) => !dimsBefore.includes(d));
    const dropped = dimsBefore.filter((d) => !dimsAfter.includes(d));
    if (added.length)
      out.push({ long: `dimensions added: ${added.join(", ")}`,
                 short: `+${added[0]}` });
    if (dropped.length)
      out.push({ long: `dimensions dropped: ${dropped.join(", ")}`,
                 short: `−${dropped[0]}` });
  }
  return out;
}

/** The long forms alone, for the sentences that name a whole change. */
export const frameMoved = (prev: TrendPoint, p: TrendPoint): string[] =>
  frameChanges(prev, p).map((c) => c.long);

/** How one trend point reads against another — the Runs table's last column.
 *
 *  Brief v16f moves this from "the point before" to "the nearest earlier
 *  point on the same basis", which is the server's `partner_index`. The
 *  column that used to answer *yes* or *no: the tier changed* now names a
 *  run, because the operator's question was never whether a comparison was
 *  permitted — it was which two things are being compared.
 *
 *  Where the partner is not the previous point, the answer says so and names
 *  what the run between changed. That clause is the one thing on this screen
 *  a reader could otherwise mistake for an error: two rows apart, joined,
 *  with a run between them that is not.
 */
export function trendReading(points: TrendPoint[], i: number): string {
  const labels = trendLabels(points);
  const p = points[i];
  const partner = p.partner_index;
  if (partner === null || partner === undefined) {
    if (i === 0) return "— first point";
    const why = frameMoved(points[i - 1], p);
    return `nothing — ${why.join(", ") || "the frame changed"}`;
  }
  if (partner === i - 1) return labels[partner];
  // What the first run *after* the partner changed — the one that broke the
  // adjacency. Named from that step rather than from this point's own, which
  // by construction changed nothing: this point and its partner share a key.
  const why = frameMoved(points[partner], points[partner + 1]);
  return `${labels[partner]} · nearest same basis; the audit between changed `
       + `${why.join(", ") || "the frame"}`;
}

/** The plot box inside the viewBox, in the viewBox's own units — the
 *  operator's mockup's, so the drawing is the one that was approved. */
const L = 64, R = 1070, T = 34, B = 270, VIEW_H = 340;
/** Below this many points the per-point score labels are drawn above the
 *  dots. Past it they would overlap into a grey stripe, so they move to the
 *  hover alone and the dates thin out — the item's own degradation. */
const LABEL_CAP = 20;

/** The y axis floor. 50 by default, as the mockup, and lower where a run
 *  actually scored below it: an axis that clips is a chart that lies about
 *  the one number it exists to show. */
const floorFor = (scores: number[]) =>
  Math.min(50, Math.floor(Math.min(...scores, 50) / 10) * 10);

/** Which band a score is in, from `SCORE_BANDS` — the same three the badge
 *  and `ScoreBandKey` use. `find` is the owner's own selector. */
const bandOf = (score: number) => SCORE_BANDS.find((b) => score >= b.at)!;

const dims = (p: TrendPoint) => p.scope?.dimensions ?? null;

export function ScoreTrend({ points }: { points: TrendPoint[] }) {
  const [tip, setTip] = useState<{ i: number; x: number; y: number } | null>(null);
  if (!points.length)
    return (
      <p className="muted st-absent">
        No audit has produced a score yet, so there is no trend. An audit that was
        blocked, narrow or unscored is not a point on it — which is not the
        same as a score of zero.
      </p>
    );

  const labels = trendLabels(points);
  const scores = points.map((p) => p.value);
  const lo = floorFor(scores);
  const n = points.length;
  const x = (i: number) => (n === 1 ? (L + R) / 2 : L + (i / (n - 1)) * (R - L));
  const y = (s: number) => B - ((s - lo) / (100 - lo)) * (B - T);
  const showLabels = n <= LABEL_CAP;

  // The stretch that shares the latest basis, as contiguous runs rather than
  // as one rectangle from the first matching point to the last. On the
  // operator's history the matching points are 02:22 and 02:37 with a T2 run
  // between them, and one rectangle would shade a point that is not in the
  // band — a picture contradicting the sentence under it.
  const latestKey = points[n - 1].basis_key;
  const inBand = points.map((p) => p.basis_key === latestKey);
  const bands: [number, number][] = [];
  inBand.forEach((here, i) => {
    if (!here) return;
    const last = bands[bands.length - 1];
    if (last && last[1] === i - 1) last[1] = i;
    else bands.push([i, i]);
  });

  // The break rules: one per step where the key moved, labelled with the
  // first term that moved. The full list stays in the Runs table's row —
  // eight rotated words down a chart is the paragraph UX-06 removed.
  const breaks = points
    .map((p, i) => ({ p, i }))
    .filter(({ p, i }) => i > 0 && !p.comparable)
    .map(({ i }) => {
      const changes = frameChanges(points[i - 1], points[i]);
      return { i, at: (x(i - 1) + x(i)) / 2,
               word: changes.length ? changes[0].short : "frame" };
    });

  const shared = inBand.filter(Boolean).length;
  const latest = points[n - 1];
  const frame = `${latest.tier ?? "unknown tier"}, engine `
    + `${latest.engine_version ?? "unknown"}, ${latest.scope?.basis ?? "unknown basis"}`;
  const sentence = shared > 1
    ? `${shared} points share the latest basis (${frame}). Only those move `
      + "together; everything left of the first rule is history, not trend."
    : "The latest point stands alone. Nothing before it was measured the same "
      + `way — ${frame} — so there is no trend yet, only a start. The next audit `
      + "on this basis is the first comparison.";

  const named = (p: TrendPoint, i: number) =>
    `${labels[i]}, ${p.value.toFixed(1)}, ${p.tier ?? "unknown tier"}`;

  return (
    <section className="st-root">
      <h3 className="st-head">Score trend</h3>
      <p className="muted st-note">
        A line joins a point to the nearest earlier point measured the same
        way — same tier, engine, share basis and dimension set — even where
        other audits sit between them. A dashed rule marks each step where
        something changed. The shaded stretch is the current basis: only those
        points are directly comparable with the latest.
      </p>
      {/* `role="img"` and a `<title>`, not a labelled group: nothing in this
          chart is a control. The dots answer to the pointer and the Runs
          table below is the accessible equivalent — every point is a row on
          it, with the same score, the same frame and the same partner. */}
      <svg className="st-chart" viewBox={`0 0 1100 ${VIEW_H}`} role="img">
        <title>
          {`Composite score over ${n} scored audit${n === 1 ? "" : "s"}, `
           + `${labels[0]} to ${labels[n - 1]}. ${sentence}`}
        </title>
        {bands.map(([from, to]) => (
          <rect key={`band-${from}`} className="st-band"
                x={x(from) - 18} y={T - 10}
                width={x(to) - x(from) + 36} height={B - T + 10} rx={4} />
        ))}
        {/* The two thresholds are `SCORE_BANDS`', drawn where they fall.
            A band whose floor is off the axis draws no rule rather than one
            pinned to the edge. */}
        {SCORE_BANDS.filter((b) => b.at > lo && b.at < 100).map((b) => (
          <g key={b.word}>
            <line className={`st-rule st-rule-${b.cls}`}
                  x1={L} y1={y(b.at)} x2={R} y2={y(b.at)} />
            <text className={`st-rule-name st-rule-${b.cls}`} x={R}
                  y={y(b.at) - 5} textAnchor="end">{b.at} · {b.word}</text>
          </g>
        ))}
        {/* The axis, at the four values the item names. Drawn from the
            floor upward and filtered by it, so a site that scored below 50
            gains a tick at its own floor rather than an axis that starts
            above its worst run. */}
        {[lo, 60, 80, 100].filter((t, i, all) => t >= lo && all.indexOf(t) === i)
          .map((t) => (
            <text key={t} className="st-tick" x={L - 8} y={y(t) + 4}
                  textAnchor="end">{t}</text>
          ))}
        <line className="st-axis" x1={L} y1={B} x2={R} y2={B} />
        {points.map((p, i) => {
          const j = p.partner_index;
          if (j === null || j === undefined) return null;
          // Straight to the point before, a shallow arc over anything
          // further back — so "these two, across those" is visible without
          // reading a column.
          const path = j === i - 1
            ? `M${x(j)},${y(points[j].value)} L${x(i)},${y(p.value)}`
            : `M${x(j)},${y(points[j].value)} Q${(x(j) + x(i)) / 2},`
              + `${Math.min(y(points[j].value), y(p.value)) - 26} `
              + `${x(i)},${y(p.value)}`;
          return <path key={`join-${i}`} className="st-join" d={path} />;
        })}
        {breaks.map((b) => (
          <g key={`break-${b.i}`}>
            <line className="st-break" x1={b.at} y1={T - 6} x2={b.at} y2={B} />
            <text className="st-break-name"
                  transform={`translate(${b.at + 4},${B - 6}) rotate(-90)`}>
              {b.word}
            </text>
          </g>
        ))}
        {points.map((p, i) => {
          const band = bandOf(p.value);
          return (
            <g key={`p-${i}`}>
              {/* The hollow ring: this point's population was recovered from
                  the per-dimension rows stored beside it, not recorded by the
                  run. A derived figure that cannot be told from a stored one
                  is the provenance breach this product is sold on not having,
                  and the note under the chart says what the ring means. */}
              {p.basis_recovered && (
                <circle className="st-ring" cx={x(i)} cy={y(p.value)} r={9} />
              )}
              <circle className={`st-dot st-${band.cls}`} cx={x(i)}
                      cy={y(p.value)} r={6}
                      onMouseEnter={(e) => setTip({ i, x: e.clientX, y: e.clientY })}
                      onMouseMove={(e) => setTip({ i, x: e.clientX, y: e.clientY })}
                      onMouseLeave={() => setTip(null)} />
              {showLabels && (
                <text className="st-score" x={x(i)} y={y(p.value) - 13}
                      textAnchor="middle">{p.value.toFixed(1)}</text>
              )}
              <text className="st-when" x={x(i)} y={B + 16} textAnchor="middle">
                {labels[i].slice(5, 10)}
              </text>
              <text className="st-frame" x={x(i)} y={B + 30} textAnchor="middle">
                {p.tier ?? "?"} · {p.engine_version ?? "?"}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="st-legend">
        {SCORE_BANDS.map((b) => (
          <span key={b.word}><i className={`st-key-${b.cls}`} />{b.word}, {b.means}</span>
        ))}
        <span><i className="st-key-break" />the comparison breaks here</span>
        <span><i className="st-key-band" />same basis as the latest</span>
      </div>
      <p className="st-now">{sentence}</p>
      {points.some((p) => p.basis_recovered) && (
        <p className="muted st-recovered">
          {`The dimension set for ${points.filter((p) => p.basis_recovered).length} `
           + `of ${n} point${n === 1 ? "" : "s"} — the ringed ones — was `
           + "recovered from the per-dimension scores stored beside it, not "
           + "recorded by the audit."}
        </p>
      )}
      {tip && (
        <div className="st-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          <b>{named(points[tip.i], tip.i)}</b>
          <div className="st-tip-line">
            engine {points[tip.i].engine_version ?? "unknown"} ·{" "}
            {points[tip.i].scope?.basis ?? "unknown basis"}
          </div>
          <div className="st-tip-line">
            {dims(points[tip.i])?.join(" ") ?? "dimension set not recorded"}
          </div>
          <div className="st-tip-line">
            {points[tip.i].partner_index === null
             || points[tip.i].partner_index === undefined
              ? "no earlier point on this basis"
              : `reads against ${labels[points[tip.i].partner_index!]}`
                + " — nearest point on the same basis"}
          </div>
        </div>
      )}
    </section>
  );
}
