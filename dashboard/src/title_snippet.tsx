/** The snippet as a result will cut it, and every page's length on one line
 *  (brief v16i, item 136n Parts B and C).
 *
 *  **Nothing here measures.** The widths, the states and the words that fall
 *  off are the server's, from `onp.snippet` — the same function the length
 *  checks read. A component that measured for itself would agree on the day
 *  it shipped and disagree the first time either number moved, which is the
 *  whole reason the measurement is one function and lives on the payload.
 */

import { useRef, useState } from "react";

import { Counted, Populations, makeCount } from "./population";

export type SnippetState = "ok" | "warn" | "bad" | "mute";

export type SnippetField = {
  text: string | null;
  px: number;
  font: string;
  chars?: number;
  min_chars?: number;
  estimated?: boolean;
  // One measurement, two cut lines. `px` is the string's width; desktop and
  // mobile are two readings of it against two limits. The toggle picks,
  // client-side, so no press re-fetches (brief v16i).
  state: SnippetState; limit_px: number; falls_off?: string;
  mobile_state: SnippetState; mobile_limit_px: number; mobile_falls_off?: string;
  /** The viewport the length check fires at (item 152): `mobile` for titles,
   *  `desktop` for descriptions until their mobile width is measured. Absent on
   *  a payload from before it, which reads as desktop. */
  fires?: "mobile" | "desktop";
};

/** The verdict at the width the check fires at - what the strip and the facts
 *  row draw, so they say what the finding says. */
export function fired(f: SnippetField) {
  return at(f, f.fires === "mobile");
}

/** The verdict for the width in scope. */
function at(f: SnippetField, mobile: boolean) {
  return mobile
    ? { state: f.mobile_state, limit_px: f.mobile_limit_px, falls_off: f.mobile_falls_off }
    : { state: f.state, limit_px: f.limit_px, falls_off: f.falls_off };
}

export type StripBar = {
  url: string; path: string;
  title: SnippetField;
  description: SnippetField;
};

export type TitleLengths = {
  pages: number;
  bars: StripBar[];
  title_cut_px: number;
  desc_cut_px: number;
  title_cut_viewport?: "mobile" | "desktop";
  desc_cut_viewport?: "mobile" | "desktop";
};

/** One tone per state, the register item 140 fixed. `mute` is a decision not
 *  taken (no title), never a gap. */
const TONE: Record<SnippetState, string> = {
  ok: "ok", warn: "warn", bad: "bad", mute: "mute",
};

// --- Part B: the snippet card -------------------------------------------

/** The result itself, at Google's real width, so the description wraps where
 *  Google wraps it (item 136n, operator 2026-09-08); the title clips at the
 *  box edge, which is its cut. Drawn on its own so the strip's detail panel
 *  can reuse the same card rather than a second one drifting from it (item
 *  146). 652px is the measured desktop result width; mobile is the phone one. */
export function ResultCard({ title, description, host, mobile = false }: {
  title: SnippetField; description: SnippetField; host: string; mobile?: boolean;
}) {
  const dv = at(description, mobile);
  return (
    <div className="snip-card" style={{ maxWidth: `${mobile ? 412 : 652}px` }}>
      <div className="snip-site">{host}</div>
      <div className="snip-title-wrap">
        <span className="snip-title">{title.text || "(no title)"}</span>
      </div>
      <div className="snip-desc">
        {description.text || <span className="muted">(no description — Google will write its own)</span>}
        {/* Inside `.snip-desc`, which is what its CSS has always said it was
            against - `.snip-desc { position: relative }` with the comment
            "`.snip-desc` is the positioning context" (item 136n). It was a
            SIBLING until item 198, so the nearest positioned ancestor was
            none of `.snip-card`, `.strip-panel` or anything above them, and
            the containing block resolved to the initial one: a page-tall
            dashed rule at the window's right edge. The operator: "There is a
            cut here line down the side of the page?" */}
        {dv.state === "bad" && (
          <span className="snip-desc-cut" aria-hidden="true">
            <span className="snip-desc-cut-label">cut here</span>
          </span>
        )}
      </div>
    </div>
  );
}

/** The result card, at the width the toggle selects, with the two rulers and
 *  the caption BESIDE it on a wide column and beneath it on a narrow one
 *  (item 199B). The card is `ResultCard`. */
export function SnippetCard({ snippet, host, mobile, onToggle, byRule = false }: {
  snippet: { title: SnippetField; description: SnippetField };
  host: string;
  mobile: boolean;
  onToggle: (mobile: boolean) => void;
  /** Whether this width was chosen by the rule rather than by the operator
   *  (item 199A). Only the caller can tell: `mobile` is true either way.
   *  Shown only when the rule chose, because saying "where the title cuts"
   *  to someone who just pressed `mobile` explains their own press to them. */
  byRule?: boolean;
}) {
  const t = snippet.title, d = snippet.description;
  const tv = at(t, mobile), dv = at(d, mobile);
  return (
    <div className="snip">
      <div className="snip-head">
        <span className="snip-label">As a search result will cut it</span>
        <div className="snip-toggle" role="group" aria-label="preview width">
          {(["desktop", "mobile"] as const).map((w) => {
            const on = (w === "mobile") === mobile;
            return (
              <button key={w} type="button" className={`snip-tab${on ? " on" : ""}`}
                      aria-pressed={on} onClick={() => onToggle(w === "mobile")}>
                {w}
              </button>
            );
          })}
        </div>
        {/* Item 199A: the block opens on the width the title check fired at
            (item 152), so the reader meets the cut first. Nothing said so,
            and the toggle then read as a preference someone had set wrong. */}
        {byRule && (
          <span className="snip-why muted">mobile: where the title cuts</span>
        )}
      </div>

      {/* Item 199B: the card on the left, what measures it on the right. The
          two rulers were full-width while the card was 652, so they were the
          only thing spanning the block and the space beside the card was
          empty. Narrow columns stack, in the one `@container part` rule item
          136m put every part-page block's narrow layout in. */}
      <div className="snip-body">
        <ResultCard title={t} description={d} host={host} mobile={mobile} />

        <div className="snip-measures">
          <Ruler field={t} kind="title" v={tv} />
          <Ruler field={d} kind="description" v={dv} />

          <p className="snip-caption muted">
        title {t.px} px
        {tv.state === "bad"
          ? <> · <span className="snip-fall">falls off: “{tv.falls_off}”</span></>
          : t.text ? " · fits" : " · no title"}
        {" · "}description {d.px} px
        {dv.state === "bad"
          ? <> · <span className="snip-fall">falls off: “{dv.falls_off}”</span></>
          : dv.state === "warn"
            ? <> · <span className="snip-short">short, Google will write its own</span></>
            : d.text ? " · fits" : " · none"}
          {(t.estimated || d.estimated) && (
            <> · <span className="snip-est">width estimated — a character is outside the metrics table</span></>
          )}
          </p>
        </div>
      </div>
    </div>
  );
}

/** A bar filled to the measured width, capped at the cut, in the state tone.
 *  The number sits at the end so the two rulers line up down the card. */
function Ruler({ field, kind, v }: {
  field: SnippetField; kind: string;
  v: { state: SnippetState; limit_px: number };
}) {
  if (!field.text) {
    return (
      <div className="snip-ruler">
        <span className="snip-ruler-name">{kind}</span>
        <span className="muted snip-ruler-none">not set</span>
      </div>
    );
  }
  const pct = Math.min(100, Math.round((field.px / v.limit_px) * 100));
  return (
    <div className="snip-ruler">
      <span className="snip-ruler-name">{kind}</span>
      <span className="snip-ruler-track">
        <span className={`snip-ruler-fill tone-${TONE[v.state]}`}
              style={{ width: `${pct}%` }} />
      </span>
      <span className="snip-ruler-n">{field.px} / {v.limit_px} px</span>
    </div>
  );
}

// --- Part C: every page's length on one line ----------------------------

/** Two strips, Title and Description: one thin bar per page in crawl order,
 *  height the measured px, colour the state. The strip answers "where on the
 *  site do the long ones cluster", so it stays in crawl order and never
 *  sorts. */
export function LengthStrips({ lengths, total, onPick, pops = null }: {
  lengths: TitleLengths;
  /** The populations a count may be counted over (item 155). The foot is a
   *  count over the record and renders by the rule like any other: plain
   *  where the record IS the page's scope, `N of M in the record` where it
   *  differs. */
  pops?: Populations | null;
  // The record count (item 146z): the strip plots this audit's crawl set, not
  // the record, and the two are different numbers on a partial crawl. The foot
  // names both so a strip saying 45 beside a table saying 68 does not read as a
  // rounding nobody checks. Falls back to the drawn count if the record total
  // is not known.
  total: number | null;
  onPick: (path: string) => void;
}) {
  // The panel's subject: the bar under the pointer or focus, unless one is
  // pinned, in which case it holds until a second click. Hover is debounced,
  // so sweeping a hundred bars renders one card, not a hundred (item 146).
  const [active, setActive] = useState<StripBar | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const host = hostOf(lengths.bars);
  const shown = pinned
    ? lengths.bars.find((b) => b.url === pinned) ?? active
    : active;

  const preview = (bar: StripBar) => {
    if (pinned) return;           // a pinned card does not follow the pointer
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setActive(bar), 40);
  };
  const activate = (bar: StripBar) => {
    window.clearTimeout(timer.current);
    if (pinned === bar.url) { onPick(bar.url); return; }  // 2nd click → page scope
    setPinned(bar.url);
    setActive(bar);
  };

  return (
    <div className="strips">
      <Strip name="Title" cut={lengths.title_cut_px} viewport={lengths.title_cut_viewport ?? "desktop"}
             bars={lengths.bars}
             total={total} pops={pops} pick={(b) => b.title} selected={shown?.url}
             onPreview={preview} onActivate={activate} />
      {/* The panel goes immediately after the strip it explains; where two
          strips describe one object, one panel serves both and sits between
          them (item 146). Title and description are one search result. */}
      <StripPanel bar={shown} host={host} pinned={!!pinned} />
      <Strip name="Description" cut={lengths.desc_cut_px} viewport={lengths.desc_cut_viewport ?? "desktop"}
             bars={lengths.bars}
             total={total} pops={pops} pick={(b) => b.description} selected={shown?.url}
             onPreview={preview} onActivate={activate} />
      {/* Part A resolved the two sides to different units, so the label says
          so rather than leaving it inferred (item 146). Once, beneath both
          strips, because both read by it. */}
      <p className="strip-unit muted">
        over: pixel width · short: characters · missing: no value on the page
      </p>
    </div>
  );
}

/** The site host for the card, from the first bar that carries a real URL. */
function hostOf(bars: StripBar[]): string {
  for (const b of bars) {
    try { return new URL(b.url).host; } catch { /* keep looking */ }
  }
  return "";
}

/** The reserved detail panel, between the two strips: `path · value · state ·
 *  decisive detail` (item 146). The decisive detail is the result card Part B
 *  draws (`ResultCard`). Fixed height (`.strip-panel` in the stylesheet), so a
 *  one-line and a two-line description leave the strip below in the same
 *  place; the empty state is centred, not padded. */
function StripPanel({ bar, host, pinned }: {
  bar: StripBar | null; host: string; pinned: boolean;
}) {
  if (!bar) {
    return (
      <div className="strip-panel">
        <p className="strip-panel-empty">
          Hover or focus a bar to see the page. Click to pin it.
        </p>
      </div>
    );
  }
  return (
    <div className={`strip-panel${pinned ? " pinned" : ""}`}>
      <div className="strip-panel-head">
        <span>{pinned ? "pinned" : bar.path}</span>
        <span className="strip-panel-hint">
          {pinned ? "click again to open page scope" : "click to pin"}
        </span>
      </div>
      <ResultCard title={bar.title} description={bar.description} host={host} />
      <p className="strip-panel-path"><code>{bar.path}</code></p>
      <StripFacts title={bar.title} description={bar.description} />
    </div>
  );
}

/** The facts row, as text so it reads aloud and copies (item 146): the
 *  fall-off words appear here, not only as the visual cut. */
function StripFacts({ title, description }: {
  title: SnippetField; description: SnippetField;
}) {
  // At the width each check fires at (item 152), so the panel and the finding
  // agree on whether the title is cut.
  const tv = fired(title), dv = fired(description);
  return (
    <p className="strip-facts">
      <span>title <b className={tv.state === "bad" ? "bad" : "okc"}>{title.px} px</b> of {tv.limit_px}</span>
      {" · "}
      {!title.text
        ? <span className="warn">missing</span>
        : tv.state === "bad"
          ? <span className="bad">falls off: <b>“{tv.falls_off}”</b></span>
          : <span className="okc">fits</span>}
      {" · "}
      <span>
        description <b className={dv.state === "bad" ? "bad" : dv.state === "warn" ? "warn" : "okc"}>{description.px} px</b> of {dv.limit_px}
        {description.text ? <> · {description.chars} characters</> : null}
        {" · "}
        {!description.text
          ? <b className="warn">missing</b>
          : dv.state === "bad"
            ? <b className="bad">cut</b>
            : dv.state === "warn"
              ? <b className="warn">short, Google will write its own</b>
              : <b className="okc">fits</b>}
      </span>
    </p>
  );
}

function Strip({ name, cut, viewport, bars, total, pick, selected, onPreview, onActivate,
                 pops = null }: {
  name: string; cut: number; viewport: string;
  bars: StripBar[];
  total: number | null;
  pops?: Populations | null;
  pick: (b: StripBar) => SnippetField;
  selected: string | undefined;
  onPreview: (b: StripBar) => void;
  onActivate: (b: StripBar) => void;
}) {
  // The tallest bar sets the scale, but never below the cut line, so the cut
  // is always somewhere on the strip and a page over it reads as over.
  const max = Math.max(cut, ...bars.map((b) => pick(b).px), 1);
  const stateOf = (b: StripBar) => (pick(b).state === "mute" ? "mute" : fired(pick(b)).state);
  const over = bars.filter((b) => stateOf(b) === "bad").length;
  const short = bars.filter((b) => stateOf(b) === "warn").length;
  const missing = bars.filter((b) => stateOf(b) === "mute").length;
  /** Item 181 (05-6): one tab stop per strip, not one per page - two strips of
   *  100 bars put 200 stops between the actions and the checks table. The
   *  selected bar, else the first, holds the stop; arrows, Home and End move. */
  const [roving, setRoving] = useState(0);
  const selIndex = bars.findIndex((b) => b.url === selected);
  const stop = selIndex >= 0 ? selIndex : Math.min(roving, Math.max(0, bars.length - 1));
  const move = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    const at = [...e.currentTarget.querySelectorAll<HTMLButtonElement>(".strip-bar")]
      .indexOf(document.activeElement as HTMLButtonElement);
    if (at < 0) return;
    const next = e.key === "Home" ? 0 : e.key === "End" ? bars.length - 1
      : e.key in keys ? Math.max(0, Math.min(bars.length - 1, at + keys[e.key])) : -1;
    if (next < 0) return;
    e.preventDefault();
    setRoving(next);
    e.currentTarget.querySelectorAll<HTMLButtonElement>(".strip-bar")[next]?.focus();
  };
  return (
    <div className="strip">
      <div className="strip-label">
        <span className="strip-name">{name}</span>
        {/* The viewport the cut is measured at (item 152): on a mobile-first
            index it has to be said rather than assumed. */}
        <span className="muted strip-cut">cut at {cut} px · {viewport}</span>
      </div>
      <div className="strip-bars" role="list" onKeyDown={move}
           aria-label={`${name} width per page, arrow keys move between pages`}>
        {bars.map((b, i) => {
          // The verdict at the width the check fires at (item 152); the width
          // itself is one measurement and does not change with the viewport.
          const raw = pick(b);
          const f = { ...raw, state: raw.state === "mute" ? raw.state : fired(raw).state };
          // An absent value is a mute bar, not a gap (item 146): a run of
          // pages with no title must not read as a quiet stretch where
          // nothing is wrong. Hatched at a fixed height, so it is told apart
          // from a genuinely short bar by more than fill (WCAG 1.4.1).
          const mute = f.state === "mute";
          return (
            <button key={b.url} type="button" role="listitem" tabIndex={i === stop ? 0 : -1}
                    className={`strip-bar tone-${TONE[f.state]}`
                      + `${mute ? " strip-bar-mute" : ""}`
                      + `${selected === b.url ? " sel" : ""}`}
                    style={mute ? undefined
                                : { height: `${Math.max(2, Math.round((f.px / max) * 100))}%` }}
                    aria-label={mute ? `${b.path} · no value` : `${b.path} · ${f.px} px`}
                    onMouseEnter={() => onPreview(b)}
                    onFocus={() => onPreview(b)}
                    onClick={() => onActivate(b)} />
          );
        })}
      </div>
      {/* One label rule across both strips (item 146): N over · N short · N
          missing, zeros included. A strip that omitted a zero taught a reader
          who saw an absence to distrust it. */}
      {/* The foot names its own denominator (item 155, superseding part of
          146z). It shipped `45 of 68 pages - this audit's crawl`, with M as
          the record count, and now sits on a page whose header reads `45 of
          53 on the site`. Two ratios over the same numerator must not read as
          a contradiction, so this one says which population its M is: crawl
          OF RECORD, which stays legal - it is a what-we-know statement, not a
          prevalence. The right span is unchanged. */}
      <div className="strip-foot muted">
        <span>
          <Counted pops={pops} unit="pages"
                   count={makeCount(bars.length, "record",
                                    pops?.record.size ?? total ?? bars.length)}
                   title={"How much of what we know about this site this "
                          + "audit's crawl drew. Not a fault rate - the part "
                          + "header states coverage against the site."} />
          {" · this audit's crawl · first crawled … last crawled"}
        </span>
        <span className="strip-counts">
          <span className="strip-over">{over} over</span>{" · "}
          <span className="strip-short">{short} short</span>{" · "}
          <span className="strip-missing">{missing} missing</span>
        </span>
      </div>
    </div>
  );
}
