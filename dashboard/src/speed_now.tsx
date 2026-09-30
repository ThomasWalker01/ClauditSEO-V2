/** The Speed part's site picture: the per-template vitals strip and the five
 *  pictures beneath it (item 141, brief v19 step BC, visuals 1-6).
 *
 *  **Nothing here measures and nothing here judges.** Every figure is off the
 *  performance trace the browser pass stored under the fixed device profile,
 *  and every band is Google's, served from the engine's own registry
 *  (`prf.GAUGE_BANDS`, derived from `CWV_BANDS`). That is not tidiness: the BC
 *  checkpoint found a gauge drawn on fixed 40/66% stops with its value
 *  coloured by the real thresholds, so the band under the marker contradicted
 *  the marker. One source for the numbers, one source for the bands.
 *
 *  **The strip is the template; the pictures are one page of it.** A gauge is
 *  a template-wide reading and shows the median of its traced pages. Every
 *  picture below the strip is ONE page traced end to end, named on screen —
 *  because the LCP sub-part bar has to SUM to the LCP it explains, and an
 *  average of four pages' sub-parts sums to an average that is no page's LCP.
 *  The server picks that page (the one nearest the median LCP) so the two
 *  halves cannot disagree about which page they are describing.
 *
 *  Item 155 applies throughout: every count carries its population. A
 *  template's page count and a gauge's "over" are counts over the CRAWL — the
 *  pages this run fetched and traced — and they render through `Counted` like
 *  every other count on the screen. This is the largest new count surface the
 *  product has gained in one pass, which is the 139a risk item 154 names by
 *  hand, and it is why the population rule landed first.
 */

import { SecondaryButton } from "./buttons";
import { useState } from "react";

import { Card } from "./components";
import { entry } from "./glossary";
import { Pill } from "./pill";
import { useObjectUrl } from "./api";
import { Count, Counted, Populations } from "./population";
import { SpendButton, SpendTarget } from "./spend";

/** One vital's band spec, as the engine serves it. `proxy` names the stand-in
 *  where the figure is not the vital itself — INP is not lab-measurable, so it
 *  is shown as TBT and labelled, never synthesised. */
export type Band = {
  label: string; name: string; good: number; poor: number; unit: string;
  proxy: string | null;
};

export type Gauge = {
  key: string; label: string; value: number | null; unit: string;
  band: "good" | "needs improvement" | "poor" | null;
  basis: string; proxy: string | null; over: Count;
};

export type SubParts = {
  ttfb: number; load_delay: number; load_time: number; render_delay: number;
};

export type Frame = { name: string; t_ms: number; label: string };

export type SpeedResource = {
  url: string | null; type: string | null; bytes: number | null;
  transfer: number | null; cost: "render" | "main-thread" | "fine";
  /** The BLOCKING cost, and null where there is none. The table is headed by
   *  blocking time, so a resource that blocks nothing has no figure in that
   *  column — a 1.4-second image drawn as the longest bar under that heading
   *  was the first thing the live Birch trace put on screen. */
  ms: number | null;
  /** How long it took, which is a different question and sits beside the
   *  blocking cost rather than standing in for it. */
  duration_ms: number | null;
  async: boolean | null; defer: boolean | null; is_lcp: boolean;
};

export type SpeedTemplate = {
  pattern: string; depth: number | null; pages: Count; vitals: Gauge[];
  /** The one page every picture below the strip is drawn from. */
  page: string;
  lcp: {
    ms: number | string; element: string | null; url: string | null;
    is_image: boolean | null; observed: boolean;
    sub_parts: SubParts | string; dominant: string | null;
    sub_total: number | null;
  };
  frames: Frame[] | string;
  resources: SpeedResource[]; resources_total: number;
  third_parties: { host: string; bytes: number; main_thread_ms: number; pages: number }[];
  head_rendered: string | null;
  /** The head the server sent, distinct from the rendered one since
   *  brief 160 step 2: `head_html` was the rendered head under a name
   *  that said otherwise. */
  head_fetched: string | null;
};

export type SpeedNow = {
  recorded: boolean; device_profile: string; traced: Count;
  /** Which pages the trace pass took, in its own words (`perf.sample`): one
   *  per template on T2/T3, every page of the pulse on T1. Stated beside the
   *  device profile, because a figure whose sample the reader cannot see is a
   *  figure they cannot check. */
  sample: string;
  bands: Record<string, Band>;
  field_data: {
    connected: boolean; source: string | null;
    good: number | null; needs_improvement: number | null; poor: number | null;
    note: string;
  };
  templates: SpeedTemplate[];
  run_id: string | null;
  /** Each readable page's template (brief v25 step BP). */
  pattern_of?: Record<string, string>;
};

/** Item 140's level tones, by band. `null` is not a fourth level — it is a
 *  vital the trace could not read, and it draws mute rather than green. */
const TONE: Record<string, string> = {
  "good": "ok", "needs improvement": "warn", "poor": "bad",
};

/** The word each tone is drawn with, from the registry (item 166; audit F13).
 *
 *  The pills drew the engine's own vocabulary - GOOD, NEEDS IMPROVEMENT, POOR,
 *  and "not read" for a vital the trace could not measure - on a screen whose
 *  `what these mean` legend is fed `BAND_LEGEND` and therefore defines four
 *  different words: within range, near the limit, past the limit, not
 *  measured. A legend defining five words beside pills drawing three others is
 *  the single source not being single.
 *
 *  And "good" and "poor" were already taken, for a different population: the
 *  registry's `score-good` is "a site score of 80 or above". So GOOD on a CLS
 *  gauge and "72.8 ... fair" on the Reports table used one vocabulary for a
 *  measurement band and a site score.
 *
 *  Google's word stays reachable in the pill's `title`, which is where the
 *  registry already puts industry cross-references (`matches` on lcp, cls,
 *  inp) - the rendered word is the product's, the hover is the correspondence
 *  for a reader coming from PageSpeed. */
const BAND_WORD: Record<string, string> = {
  ok: entry("band-ok").word, warn: entry("band-warn").word,
  bad: entry("band-bad").word, mute: entry("band-mute").word,
};

/** The three cost types the waterfall separates, in the brief's own colours:
 *  blocks-render red, blocks-main-thread-later amber, fine blue. Three costs,
 *  three colours, so the reader does not have to read a column to tell them
 *  apart. */
const COST: Record<SpeedResource["cost"], { tone: string; word: string }> = {
  "render": { tone: "bad", word: "blocks render" },
  "main-thread": { tone: "warn", word: "main thread later" },
  "fine": { tone: "info", word: "fine" },
};

const SUB_LABEL: Record<keyof SubParts, string> = {
  ttfb: "TTFB", load_delay: "load delay", load_time: "load time",
  render_delay: "render",
};

/** Why each sub-part is what it is, in the words the fix card reads it in.
 *  Named here rather than in the fix card because the bar is the diagnostic
 *  and the card's estimate is read OFF it — one sentence per part, or the two
 *  drift. */
const SUB_WHY: Record<keyof SubParts, string> = {
  ttfb: "server — time to the first byte of the document",
  load_delay: "discovery delay — how long before the browser knew to fetch it",
  load_time: "download — the resource itself on the wire",
  render_delay: "render delay — work between the bytes arriving and the paint",
};

function ms(n: number, unit: string): string {
  if (unit === "") return n.toFixed(n < 1 ? 3 : 2);
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)} s` : `${Math.round(n)} ms`;
}

function kb(bytes: number | null): string {
  // Zero is a dash, not `1 KB`. The floor at one exists so a 300-byte script
  // does not read as nothing, and applied to a host that shipped no bytes at
  // all it invented a kilobyte - `frog.wix.com` and `panorama.wixapps.net`
  // both read `1 KB` on the live Birch ledger with nothing transferred.
  if (bytes == null || bytes === 0) return "—";
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function path(url: string | null): string {
  if (!url) return "—";
  try {
    const u = new URL(url);
    const last = u.pathname.split("/").filter(Boolean).pop();
    return last ? `${last}${u.search}` : u.host;
  } catch { return url; }
}

/** Visual 1 — a gauge per vital on Google's bands, the measured value as a
 *  marker.
 *
 *  The track runs to 1.5x the poor threshold, so the poor band is visible
 *  rather than a hairline at the right edge, and the three band widths are
 *  computed from the thresholds themselves. A value past the end of the track
 *  clamps to it and says so — the alternative is a scale that rescales itself
 *  per site, and then two gauges side by side are two different rulers. */
function VitalGauge({ gauge, band, pops }: {
  gauge: Gauge; band: Band; pops: Populations | null;
}) {
  const max = band.poor * 1.5;
  const pct = (n: number) => `${Math.min(100, (n / max) * 100)}%`;
  const tone = gauge.band ? TONE[gauge.band] : "mute";
  const over = gauge.value != null && gauge.value > max;
  return (
    <div className={`sp-gauge sp-gauge-${tone}`} data-vital={gauge.key}
         data-band={gauge.band ?? ""}>
      <div className="sp-g-head">
        <span className="sp-g-label" title={band.name}>
          {gauge.label}{gauge.proxy ? ` (${gauge.proxy} proxy)` : ""}
        </span>
        <span className={`sp-g-band tone-${tone}`}
              title={gauge.band ? `${gauge.band} in Google's bands` : undefined}>
          {BAND_WORD[tone] ?? BAND_WORD.mute}
        </span>
      </div>
      <div className="sp-g-value">
        {gauge.value == null
          ? <span className="muted">not read</span>
          : <><b>{ms(gauge.value, gauge.unit)}</b>
              {/* Lab or field, on every figure. The brief's accept says every
                  vital is labelled lab until a field source is connected, and
                  this is where a reader is told which they are looking at. */}
              <span className="muted sp-g-basis">
                {/* The registry's word for the basis (item 166): "lab test",
                    "real visitors (field)". Google's own word stays findable. */}
                {" · "}{entry(gauge.basis === "field" ? "basis-field" : "basis-lab").word}
                {gauge.proxy ? ` · ${gauge.proxy}` : ""}
                {" · median of "}
                <Counted count={gauge.over} pops={pops} unit="pages" />
              </span></>}
      </div>
      <div className="sp-g-track" role="img"
           aria-label={`${band.name}: ${gauge.value == null ? "not read"
             : ms(gauge.value, gauge.unit)}, good at or under `
             + `${ms(band.good, band.unit)}, poor over ${ms(band.poor, band.unit)}`}>
        <span className="sp-band sp-band-ok" style={{ width: pct(band.good) }} />
        <span className="sp-band sp-band-warn"
              style={{ width: `${((band.poor - band.good) / max) * 100}%` }} />
        <span className="sp-band sp-band-bad"
              style={{ width: `${((max - band.poor) / max) * 100}%` }} />
        {gauge.value != null && (
          <span className={`sp-marker sp-marker-${tone}${over ? " sp-marker-over" : ""}`}
                style={{ left: pct(gauge.value) }} />
        )}
      </div>
      <div className="sp-g-scale muted">
        <span>good ≤ {ms(band.good, band.unit)}</span>
        <span>poor &gt; {ms(band.poor, band.unit)}</span>
      </div>
    </div>
  );
}

/** Visual 2 — the field distribution, greyed until a field source is
 *  connected.
 *
 *  Greyed with what to connect, never zeros: `good 0 · NI 0 · poor 0` is a
 *  claim about the site rather than about our data, and it is the claim a
 *  client would read first. This is also the one thing on the page the client
 *  themselves can act on to make it truthful about real users. */
function FieldBar({ field }: { field: SpeedNow["field_data"] }) {
  if (!field.connected) {
    return (
      <div className="sp-field sp-field-off">
        <div className="sp-f-head">
          <b>Real visitors (field)</b>
          <span className="muted">{field.source ? field.source : "not connected"}</span>
        </div>
        <div className="sp-f-bar sp-f-empty" aria-hidden="true" />
        <p className="muted sp-f-note">{field.note}</p>
      </div>
    );
  }
  const total = (field.good ?? 0) + (field.needs_improvement ?? 0) + (field.poor ?? 0);
  const share = (n: number | null) => (total ? `${((n ?? 0) / total) * 100}%` : "0%");
  return (
    <div className="sp-field">
      <div className="sp-f-head">
        <b>Real visitors (field)</b>
        <span className="muted">{field.source}</span>
      </div>
      <div className="sp-f-bar">
        <span className="sp-band-ok" style={{ width: share(field.good) }} />
        <span className="sp-band-warn" style={{ width: share(field.needs_improvement) }} />
        <span className="sp-band-bad" style={{ width: share(field.poor) }} />
      </div>
    </div>
  );
}

/** Visual 3 — the LCP sub-part stacked bar, the dominant part highlighted.
 *
 *  The one picture that says *why*, and the one the fix card's estimate is read
 *  off. The sum is stated beside the LCP it explains, because the brief's
 *  accept is that the sub-parts SUM to the LCP — a bar that does not is a bar
 *  drawn from a different page than the figure above it, which is exactly the
 *  mistake naming the page prevents. */
function LcpSubParts({ t }: { t: SpeedTemplate }) {
  const sub = t.lcp.sub_parts;
  if (typeof sub === "string" || !sub) {
    return (
      <p className="muted sp-sub-none">
        {t.lcp.observed
          ? "The LCP element is not a resource this pass timed, so its "
            + "sub-parts cannot be attributed — the paint is recorded, the "
            + "breakdown is not."
          : "No LCP was observed on this page, so there are no sub-parts to "
            + "break down."}
      </p>
    );
  }
  const keys: (keyof SubParts)[] = ["ttfb", "load_delay", "load_time", "render_delay"];
  const total = t.lcp.sub_total ?? keys.reduce((n, k) => n + sub[k], 0);
  // A caption needs room for its own words. Below this share the segment is a
  // sliver and the label was clipped to one letter - `T` and `r` on the live
  // Birch trace, where TTFB was 35 ms of a 2,552 ms paint. The figure is
  // never lost: the summary line beneath names the dominant part and the
  // total, and every segment carries its sentence as a title.
  const ROOM = 0.12;
  const lcpMs = typeof t.lcp.ms === "number" ? t.lcp.ms : null;
  // The sum against the LCP it explains, to the tenth of a millisecond the
  // trace stores. Stated rather than assumed: the brief's accept is that these
  // sum, so the screen is where that is checkable by eye.
  const off = lcpMs == null ? null : Math.round((total - lcpMs) * 10) / 10;
  return (
    <div className="sp-sub" data-total={String(total)}>
      <div className="sp-sub-bar">
        {keys.map((k) => (
          <span key={k}
                className={`sp-s sp-s-${k.replace("_", "-")}`
                           + (t.lcp.dominant === k ? " sp-s-dominant" : "")}
                style={{ width: total ? `${(sub[k] / total) * 100}%` : "0%" }}
                title={`${SUB_LABEL[k]} ${Math.round(sub[k])} ms — ${SUB_WHY[k]}`}>
            {total && sub[k] / total >= ROOM
              ? <span className="sp-s-cap">{SUB_LABEL[k]} {Math.round(sub[k])}</span>
              : null}
          </span>
        ))}
      </div>
      <p className="muted sp-sub-why">
        {t.lcp.dominant
          ? <><b>{SUB_LABEL[t.lcp.dominant as keyof SubParts]}</b> dominates —{" "}
              {SUB_WHY[t.lcp.dominant as keyof SubParts]}.{" "}</>
          : null}
        Sub-parts total {Math.round(total)} ms
        {lcpMs != null && <> against an LCP of {Math.round(lcpMs)} ms
          {off ? ` (${off > 0 ? "+" : ""}${off} ms)` : " — they sum"}</>}.
      </p>
    </div>
  );
}

/** One filmstrip frame. Fetched with the operator's token and handed to the
 *  browser as bytes, never as a bare `src` — every `/api/` route is behind
 *  `operator=op_dep` and a browser loading a subresource by itself sends no
 *  `Authorization` header (UX-30, and `api.useObjectUrl` exists for this). */
function FilmFrame({ runId, frame }: { runId: string | null; frame: Frame }) {
  const url = useObjectUrl(runId ? `/api/runs/${runId}/frames/${frame.name}` : null);
  return (
    <figure className={`sp-frame sp-frame-${frame.label.toLowerCase()}`}>
      {url
        ? <img src={url} alt={`the page at ${(frame.t_ms / 1000).toFixed(1)} seconds`} />
        : <span className="sp-frame-wait" aria-hidden="true" />}
      <figcaption className="muted">
        {(frame.t_ms / 1000).toFixed(1)} s
        {frame.label !== "loading" ? ` · ${frame.label}` : ""}
      </figcaption>
    </figure>
  );
}

/** Visual 4 — the filmstrip: what painted when.
 *
 *  The frames are paint frames from a CDP screencast across the load, de-duped
 *  on the bytes. Taken after `load` they were three identical copies of the
 *  finished page — the operator caught that at the BC checkpoint ("the
 *  filmstrip does not seem to change much?"), and the capture moved to
 *  `wait_until: commit` plus a screencast because of it. */
function Filmstrip({ t, runId }: { t: SpeedTemplate; runId: string | null }) {
  if (typeof t.frames === "string" || !t.frames.length) {
    return (
      <p className="muted sp-strip-none">
        This audit recorded no filmstrip for {path(t.page)} — the frames are
        written by the performance pass, and an audit taken without it has none.
      </p>
    );
  }
  return (
    <div className="sp-strip">
      {t.frames.map((f) => (
        <FilmFrame key={f.name} runId={runId} frame={f} />
      ))}
    </div>
  );
}

/** Visual 5 — resources by blocking time, three cost types in three colours.
 *
 *  Ordered render-blocking first and then by cost, which is the order a reader
 *  fixes in. The bar is scaled to the heaviest row on this page, so the
 *  picture answers "which of these is the problem" rather than "how does this
 *  page compare to another one" — that second question is the gauges'. */
function Waterfall({ t, pops, onPart }: {
  t: SpeedTemplate; pops: Populations | null;
  onPart?: (key: string) => void;
}) {
  if (!t.resources.length) {
    return <p className="muted">No resources were timed on {path(t.page)}.</p>;
  }
  // Scaled against the PAINT the blocking delays, not against the heaviest
  // blocking row. Scaled against itself, a page with one blocking resource
  // drew that row at full width whatever it cost - 1 ms of a 2,552 ms paint
  // filled the bar on the live Birch trace, which reads as the finding when
  // it is the opposite. Against the LCP, 1 ms is a hairline and a 622 ms
  // blocking script is a quarter of the bar, which is what it is.
  const paint = typeof t.lcp.ms === "number" ? t.lcp.ms : null;
  const max = Math.max(paint ?? 0, ...t.resources.map((r) => r.ms ?? 0), 1);
  return (
    <div className="table-scroll">
      <table className="findings sp-wf">
        <thead>
          <tr><th>Resource</th><th className="num">Size</th><th>Cost</th>
              <th className="num">Blocking</th><th className="num">Took</th></tr>

        </thead>
        <tbody>
          {t.resources.map((r) => (
            <tr key={r.url ?? Math.random()} className={`sp-wf-${r.cost}`}>
              <td>
                <code>{path(r.url)}</code>
                {r.is_lcp && <span className="sp-tag sp-tag-lcp"> LCP</span>}
                {/* `defer` and `async` are attributes of a SCRIPT. The trace
                    carries them on every row, and drawn on an image they read
                    as a property that element cannot have - the live Birch
                    trace showed five `.jpg · defer · async` rows. */}
                {r.type === "script" && r.defer && <span className="muted"> · defer</span>}
                {r.type === "script" && r.async && <span className="muted"> · async</span>}
              </td>
              <td className="num">{kb(r.transfer ?? r.bytes)}</td>
              <td>
                <span className={`sp-cost tone-${COST[r.cost].tone}`}>
                  {COST[r.cost].word}
                </span>
              </td>
              <td className="num sp-wf-ms">
                {r.ms == null
                  ? <span className="muted">&mdash;</span>
                  : <>
                      <span className={`sp-wf-bar sp-wf-bar-${COST[r.cost].tone}`}
                            style={{ width: `${(r.ms / max) * 100}%` }}
                            aria-hidden="true" />
                      {Math.round(r.ms)} ms
                    </>}
              </td>
              <td className="num muted">
                {r.duration_ms == null ? "\u2014" : `${Math.round(r.duration_ms)} ms`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {typeof t.lcp.ms === "number" && (
        <p className="muted sp-wf-scale">
          Bars are against this page&rsquo;s {Math.round(t.lcp.ms)} ms paint, so
          a blocking cost is read as the share of the paint it delays.
        </p>
      )}
      {t.resources_total > t.resources.length && (
        <p className="muted sp-wf-more">
          {t.resources_total - t.resources.length} more resources timed on this
          page, below the ones above by blocking cost. A row with no blocking
          figure blocks nothing &mdash; it is listed for what it weighs and
          how long it took, not as a cost.
        </p>
      )}
      {/* The Speed page never recounts image weight (brief v19 step BC). So
          this is a link and not a second figure: what an image weighs and what
          is recoverable are measured on the Images part, and restating them
          here is how two screens come to disagree about one number. */}
      <p className="muted sp-images-line">
        <b>Images</b> — weight and what is recoverable are measured on the
        Images part{typeof t.lcp.ms === "number" && t.lcp.is_image
          ? ", and this template's LCP is an image" : ""}.
        {onPart && (
          <button type="button" className="sp-to-images"
                  onClick={() => onPart("images")}>
            {" → Images"}
          </button>
        )}
      </p>
      {/* `pops` reaches the rows above through `Counted`; the table itself
          states no count of its own. */}
      {pops === undefined ? null : null}
    </div>
  );
}

/** Visual 6 — the third-party ledger as bars by main-thread milliseconds.
 *
 *  Main thread rather than bytes, because that is what a third party costs a
 *  visitor: a 40 KB script holding the thread for 300 ms is worse than a
 *  400 KB image that costs nothing. The ms come from Long Animation Frames'
 *  per-script attribution, which is the only source that can charge
 *  main-thread time to a host — the Long Tasks API attributes at frame level
 *  and answers "unknown", which is why an earlier version of this charged
 *  nobody and drew an empty ledger. */
function ThirdParties({ t, pops }: { t: SpeedTemplate; pops: Populations | null }) {
  if (!t.third_parties.length) {
    return (
      <p className="muted sp-tp-none">
        No third-party host shipped anything on this template&rsquo;s traced
        pages.
      </p>
    );
  }
  const max = Math.max(...t.third_parties.map((r) => r.main_thread_ms), 1);
  return (
    <div className="table-scroll">
      <table className="findings sp-tp">
        <thead>
          <tr><th>Host</th><th className="num">Bytes</th>
              <th className="num">Main thread</th><th className="num">Pages</th></tr>
        </thead>
        <tbody>
          {t.third_parties.map((r) => (
            <tr key={r.host}>
              <td><code>{r.host}</code></td>
              <td className="num">{kb(r.bytes)}</td>
              <td className="num sp-tp-ms">
                <span className="sp-tp-bar"
                      style={{ width: `${(r.main_thread_ms / max) * 100}%` }}
                      aria-hidden="true" />
                {r.main_thread_ms ? `${Math.round(r.main_thread_ms)} ms` : "—"}
              </td>
              {/* A count over the crawl: the template's traced pages this host
                  appeared on (item 155). */}
              <td className="num">
                <Counted pops={pops} unit="pages"
                         count={{ value: r.pages, population: "crawl",
                                  basis: "crawled", of: t.pages.value }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The whole block: the template picker, the strip, and the five pictures for
 *  the template in hand.
 *
 *  One template at a time below the strip, and the strip itself carries every
 *  template's gauges — so "which template is worst" and "why is this one
 *  slow" are two readings of one block rather than two screens. The part opens
 *  on the largest template, which the server sorts first: the one most of the
 *  site is built from is the one worth reading. */
export function SpeedNowBlock({ part, pops = null, onPart, picked, onTemplate }: {
  part: { speed_now?: SpeedNow | null };
  pops?: Populations | null;
  /** The template narrow in hand and its setter (brief v25 step BP). With a
   *  setter the picker is the narrow: pressing a template narrows the fixes
   *  below the picture to its pages, and the pictures follow it. */
  picked?: string | null;
  onTemplate?: (pattern: string | null) => void;
  /** Open another part of the site. The Speed page links to Images rather
   *  than restating what an image weighs (brief v19 step BC: "the Speed page
   *  never recounts image weight"), and a link between parts needs the
   *  selection, which lives on the client screen. */
  onPart?: (key: string) => void;
}) {
  const now = part.speed_now ?? null;
  const [localPick, setLocalPick] = useState<string | null>(null);
  const pick = onTemplate ? (picked ?? null) : localPick;
  const setPick = (pattern: string) => onTemplate
    ? onTemplate(pattern === pick ? null : pattern)
    : setLocalPick(pattern);
  if (!now) return null;
  if (!now.recorded) {
    return (
      <Card className="now-card sp-card">
        <h4>What the templates have now</h4>
        <p className="muted sp-untraced">
          This audit recorded no performance trace, so there is nothing to read
          back. The trace is a separate throttled browser pass — it runs where
          it is asked for, not on every audit — and an audit taken without it has
          no vitals, no filmstrip and no resource timing. Re-check this part to
          take one.
        </p>
        <p className="muted sp-profile">{now.device_profile}</p>
      </Card>
    );
  }
  const t = now.templates.find((x) => x.pattern === pick) ?? now.templates[0];
  // A gauge's `over` count is "how many of THIS TEMPLATE's traced pages gave
  // a figure", so the scope it renders against is the template and not the
  // site (item 155's rule, applied where the reader is looking - the same
  // narrowing the depth bar does to the cause table). Without it a median
  // taken over every page of the template read `median of 11 of 11 pages
  // crawled`, which is the redundancy the rule exists to remove.
  const inTemplate: Populations | null = pops
    ? { ...pops, scope: { pages: t.pages.value, basis: "in this template" } }
    : null;
  return (
    <Card className="now-card sp-card">
      <h4>What the templates have now</h4>
      {/* The device profile on every run, per the brief - and it states the
          throttling METHOD, because we APPLY the throttle where
          Lighthouse/PageSpeed simulate it. Ours reads lower by design, and a
          client comparing the two is owed that sentence rather than left to
          read it as a disagreement. */}
      <p className="muted sp-profile">
        {now.device_profile} · traced{" "}
        <Counted count={now.traced} pops={pops} unit="pages" />
      </p>

      {(now.templates.length > 1 || onTemplate) && (
        <div className="sp-picker" role="group" aria-label="template">
          {now.templates.map((x) => (
            <button key={x.pattern} type="button"
                    className={`sp-pick${x.pattern === t.pattern ? " on" : ""}`}
                    // Item 181 (06-13): the pressed state is the template drawn,
                    // which is the default one before any pick.
                    aria-pressed={x.pattern === t.pattern}
                    onClick={() => setPick(x.pattern)}>
              <code>{x.pattern}</code>
              <span className="muted">
                {" "}<Counted count={x.pages} pops={pops} unit="pages" />
              </span>
            </button>
          ))}
        </div>
      )}

      <h5 className="sp-h">
        <code>{t.pattern}</code>
        <span className="muted">
          {" · "}<Counted count={t.pages} pops={pops} unit="pages" />
          {t.depth != null ? ` · depth ${t.depth}` : ""}
        </span>
      </h5>

      <div className="sp-gauges">
        {t.vitals.map((g) => (
          <VitalGauge key={g.key} gauge={g} band={now.bands[g.key]} pops={inTemplate} />
        ))}
      </div>
      <FieldBar field={now.field_data} />

      {/* Everything below here is ONE page of the template, and it says so.
          The sub-part bar must sum to the LCP it explains; an average cannot. */}
      <p className="muted sp-rep">
        The pictures below are one page traced end to end —{" "}
        <code>{path(t.page)}</code>, the page of this template nearest its
        median LCP. Not an average: the sub-parts have to sum to the paint they
        explain.
      </p>

      <h5 className="sp-h">
        Why the LCP is what it is — sub-parts
        {t.lcp.element ? <span className="muted"> · <code>{t.lcp.element}</code></span> : null}
      </h5>
      <LcpSubParts t={t} />

      <h5 className="sp-h">What painted when</h5>
      <Filmstrip t={t} runId={now.run_id} />

      <h5 className="sp-h">Resources by blocking time</h5>
      <Waterfall t={t} pops={pops} onPart={onPart} />

      <h5 className="sp-h">Third parties</h5>
      <ThirdParties t={t} pops={inTemplate} />
    </Card>
  );
}

/** The Speed part's depth pills (brief v19 step BC).
 *
 *  **"Everywhere else the pills stay gone" is enforced by a slot only Speed
 *  fills, not by a change to the actions row's default** (operator ruling
 *  2026-09-11). `.cat-run` is shared by every across-the-site part, and BC's
 *  visuals and BJ's header were written against it — so this is a component
 *  that one part mounts, and every other part's row is byte-for-byte what it
 *  was. Nothing here is conditional on `part.key`; the condition is that
 *  nobody else imports it.
 *
 *  Three pills, in the brief's own words:
 *
 *    Re-check PRF · free      the sweep's trace and the thirteen free checks
 *    Run brief · Standard     `speed.md` on the templates
 *    Run brief · Deep         the same plus a per-page third-party waterfall,
 *                             when the trace has one
 *
 *  Deep is a bigger CONTEXT and not a bigger model, which is why its estimate
 *  is the same model's price over more evidence rather than a different tier's.
 */
export function SpeedActions({ now, cost, busy, onRecheck, onBrief, note }: {
  now: SpeedNow | null | undefined;
  /** The brief's estimate, from the analyses lane. Null where nothing has
   *  priced it — and then the pill says `unpriced` rather than a figure. */
  cost: number | null;
  /** The tool running right now, if one is. */
  busy: string | null;
  onRecheck: () => void;
  onBrief: (depth: "standard" | "deep") => void;
  /** Why the brief cannot run, where it cannot — a narrow scan, say. */
  note: string | null;
}) {
  const money = (n: number | null) =>
    n == null ? "unpriced" : `~USD ${n.toFixed(2)}`;
  // Deep's price is the standard estimate marked as a FLOOR, not a multiple
  // of it. A first pass wrote `cost * 1.6`, which is an invented number: the
  // two depths are one tool with one measurement, the waterfall's share of
  // the tokens has never been measured, and a figure like `~USD 0.13` would
  // be read as a promise. `~USD 0.08+` says what is known - at least the
  // standard run, because Deep sends everything Standard sends and more.
  return (
    <div className="sp-acts" role="group" aria-label="Speed depth">
      <SecondaryButton className="sp-act-prf"
            busy={busy === "sweep"}
            why={busy !== null && busy !== "sweep" ? "the analysis is running" : null}
            onClick={onRecheck}
            title="Re-runs the speed checks: the throttled trace pass and the thirteen free checks that read it. Costs no tokens.">
        Re-check PRF · free
      </SecondaryButton>
      {(["standard", "deep"] as const).map((depth) => (
        // Item 178: held with the reason in text, confirmed with the price. The
        // label keeps its own price wording - Deep's figure is a floor.
        <SpendButton key={depth} className={`sp-act-${depth}`} showPrice={false}
                     price={cost} busy={busy === "speed"}
                     why={note ?? (busy !== null && busy !== "speed" ? "the free checks are running" : null)}
                     confirm={{ title: `Run the Speed analysis at ${depth === "deep" ? "Deep" : "Standard"}?`,
                                body: <><SpendTarget />
                                  <p>{depth === "deep"
                                    ? "The Speed analysis on the templates, plus a per-page third-party "
                                      + "waterfall where the trace has one. Its price is at least the "
                                      + "Standard figure; how much more has not been measured."
                                    : "The Speed analysis on the templates."}</p></>,
                                action: `Run at ${depth === "deep" ? "Deep" : "Standard"}` }}
                     onSpend={() => onBrief(depth)}>
          {`Run analysis · ${depth === "deep" ? "Deep" : "Standard"} · `}
          {money(cost)}{depth === "deep" && cost != null ? "+" : ""}
        </SpendButton>
      ))}
      {/* WHICH WAY DEEP'S FIGURE IS WRONG, in rendered text (UX-80). It was
          in the pill's title, and `test_that_a_money_total_understates_never
          _lives_only_in_a_title` caught it - correctly: the direction a money
          total is wrong in is the one thing an operator cannot derive, and a
          tooltip is not a place they read. The `+` on the figure says there
          is more; this says how much more is unknown. */}
      {cost != null && (
        <span className="muted sp-act-floor">
          Deep is at least the Standard figure &mdash; how much the extra
          evidence adds has not been measured.
        </span>
      )}
      {/* The sample, stated beside the device profile and for the same reason
          (operator ruling 2026-09-11): the brief's "per page" predates the
          CPU 4x / Slow-4G session, so which pages were traced is a fact the
          reader needs to check any figure above. */}
      {now?.sample && (
        <span className="muted sp-act-sample">traced: {now.sample}</span>
      )}
      {note && <span className="muted sp-act-note">{note}</span>}
    </div>
  );
}
