/** The Headings part's two pictures (brief v16d): the outline of one page,
 *  and which skip sits on which template across the site.
 *
 *  Ported from the operator's approved mockup
 *  (`headings_visual_mockup.html`); the heading text and the template split
 *  in that file are illustrative and every rung, row and count here is read
 *  off the payload.
 *
 *  **Nothing in this file decides what is wrong**, which is the item's own
 *  rule and the reason `onp.heading_outline_state` exists: a rung's state,
 *  the gap where a level was skipped and the absent H1 all arrive decided
 *  from the server, from the one function `h1-missing`, `h1-multiple` and
 *  `heading-skip` themselves call. The card that stood here before had a
 *  second implementation of both rules inline - `previous && line.level >
 *  previous + 1`, a running `seenH1` - and a second implementation agrees on
 *  the day it is written and on no later one.
 *
 *  **A page may draw more gaps than it carries findings, and that is the
 *  outline being honest rather than the two disagreeing.** `heading-skip`
 *  breaks out of its loop after the first skip, so a page skipping twice is
 *  one finding; the ladder draws the page, so it shows both. The rung for
 *  the skip that fired opens its card; the one after it has nothing to open,
 *  which is what the item's "no action otherwise" is for. The agreement the
 *  guards hold is the page-level one, where the ladder and the record are
 *  making the same claim.
 *
 *  **The site block groups with `anatomy.tsx`'s own `templatesOf`.** The
 *  server sends the shape of each page's fault and no template at all: what
 *  a template is is decided once, in the function the check group line above
 *  this table already uses, and a second copy of "a first segment ten or
 *  more pages share" - in Python, on a payload - is how one screen comes to
 *  disagree with itself about `/blog/*`.
 *
 *  **Tone.** The stylesheet's existing semantic tokens and no new colour,
 *  which is item 140's rule: `--text` for a heading present, `--warn-strong`
 *  for a skipped level, `--danger` for the missing H1, `--edge` for the
 *  connectors. The mockup's `--ink`, `--warn`, `--bad` and `--edge` are
 *  those four meanings under other names.
 */
import { HeadingOutline, HeadingShapes, templatePathOf, templatePrefixOf,
         templatesOf } from "./anatomy";

/** The ladder's geometry, the mockup's numbers. A rung's column is its
 *  level, so indentation is the level and not a decoration of it. */
const COL0 = 28;
const COLW = 54;
const RH = 34;
/** A gap is shorter than a rung, so a skipped level reads as the space it
 *  is rather than as another heading. The mockup's 0.8. */
const GAPH = RH * 0.8;
const VIEW_W = 560;

/** How many heading rungs are drawn before the ladder says it has stopped
 *  (the item's ~40). Gaps are not counted against it: a gap is not a
 *  heading, and a page whose fortieth heading is reached through two skips
 *  would otherwise lose two real rungs to them. */
export const RUNG_CAP = 40;

const X = (level: number) => COL0 + (Math.max(1, Math.min(6, level)) - 1) * COLW;

/** How wide the rung itself is drawn, before its text. The mockup's taper:
 *  a deeper heading is a shorter mark, so the shape of the outline is
 *  legible without reading a word of it. */
const RUNGW = (level: number) => Math.max(60, 220 - (level - 1) * 30);

/** One line of SVG text, cut to what the box can hold.
 *
 *  SVG has no ellipsis: `text-overflow` needs a block box and there is not
 *  one here. The cut is by character against an average advance, which is
 *  approximate by construction - it is a cut for a label, and the heading's
 *  own text is on the rung's accessible name whole, so nothing is lost by
 *  it. */
export function fit(text: string, level: number, big: boolean): string {
  const room = VIEW_W - (X(level) + RUNGW(level) + 10);
  const chars = Math.max(8, Math.floor(room / ((big ? 13.5 : 12.5) * 0.52)));
  const clean = (text || "").replace(/\s+/g, " ").trim();
  return clean.length > chars ? `${clean.slice(0, chars - 1).trimEnd()}…` : clean;
}

/** The figcaption, generated: the path, the skip shapes present, then the
 *  H1 state - the mockup's three parts, in its order. */
export function captionOf(outline: HeadingOutline, path: string): string[] {
  const shapes = [...new Set(outline.skips.map((s) => `H${s.from}→H${s.to}`))];
  const first = outline.rungs.find((r) => r.kind === "heading");
  const h1 = outline.h1s === 0
    ? (first ? `no H1 — the outline starts at H${first.level}` : "no H1")
    : outline.h1s === 1 ? "one H1" : `${outline.h1s} H1s`;
  return [path,
          shapes.length ? `${shapes.join(", ")} skip${shapes.length > 1 ? "s" : ""}`
                        : "levels run in order",
          h1];
}

/** Which check a rung belongs to, or null where it belongs to none.
 *
 *  Read off `fires`, never re-derived: the fired skip's heading and its gaps
 *  open the `heading-skip` card, the absent H1 opens `h1-missing`, and the
 *  second and later H1s open `h1-multiple`. A gap for a later skip returns
 *  null, because the record holds no row for it. */
export function checkOfRung(outline: HeadingOutline,
                            rung: HeadingOutline["rungs"][number]): string | null {
  const skip = outline.fires["heading-skip"];
  if (rung.kind === "no-h1") return "h1-missing";
  if (rung.kind === "gap") {
    return skip && rung.for_index === skip.index ? "heading-skip" : null;
  }
  if (skip && rung.index === skip.index) return "heading-skip";
  if (rung.level === 1 && rung.state === "warn") return "h1-multiple";
  return null;
}

/** Block 1. The outline of this page, one rung per heading in DOM order,
 *  indented by level, with the gaps drawn where the missing levels would
 *  have been. */
export function OutlineLadder({ outline, path, onCheck, checks }: {
  outline: HeadingOutline | null | undefined;
  path: string;
  /** Open the record's card for a check. A rung with no check is inert,
   *  which is the item's "no action otherwise". */
  onCheck?: (checkId: string) => void;
  /** Which checks the record actually holds a card for on this page, so a
   *  rung never offers to scroll to nothing. */
  checks?: ReadonlySet<string>;
}) {
  if (!outline) return null;
  const headings = outline.rungs.filter((r) => r.kind === "heading");
  if (!headings.length) {
    // The item's degradation, and it is a sentence rather than an empty
    // ladder: a page with no headings is already `h1-missing` on the
    // record, and an empty figure would say the crawl found an outline with
    // nothing wrong with it.
    return (
      <p className="muted ho-none">
        The crawl recorded no headings on this page, so there is no outline to
        draw. That is itself the finding below — a page with no headings has
        no H1 either.
      </p>
    );
  }
  // The cap, and the one thing it may not do.
  //
  // **A cap that hides the fault is worse than a longer ladder**, and this
  // is not a hypothetical: Acme's `/line-of-credit` carries 46 headings
  // and its H2->H4 skip is the forty-first, so the first reading of this
  // block on the running product drew forty clean rungs and said "6 more
  // headings below" - a picture of a skip with no skip in it, on the page
  // the item names in its own stop report. No fixture could have shown it;
  // a fixture is written short enough to read.
  //
  // So the window is forty rungs OR as far as the first marked one,
  // whichever is longer. The common page is unchanged, and the page whose
  // fault is deep enough to be cut off keeps it.
  const lastMarked = outline.rungs.reduce(
    (n, r, i) => (r.state !== "ink" ? i : n), -1);
  const shown: HeadingOutline["rungs"] = [];
  let kept = 0;
  for (const [i, rung] of outline.rungs.entries()) {
    if (rung.kind === "heading" && kept >= RUNG_CAP && i > lastMarked) break;
    if (rung.kind === "heading") kept += 1;
    shown.push(rung);
  }
  const more = headings.length - kept;

  const caption = captionOf(outline, path);
  let y = 22;
  const placed = shown.map((rung) => {
    const at = y;
    y += rung.kind === "gap" ? GAPH : RH;
    return { rung, y: at };
  });
  const height = y + 10;
  const label = `Heading outline of ${path}: ${caption.slice(1).join(", ")}`;

  return (
    <figure className="ho-figure">
      <figcaption className="ho-cap">
        <b>{caption[0]}</b> · {caption[1]} · {caption[2]}
      </figcaption>
      {/* `role="group"` and not `role="img"`: the rungs that open a card are
          focusable, and a labelled `role="img"` may not hold focusable
          children - which is what axe reported against the Images scatter
          on its first run (brief v16c). */}
      <svg className="ho-ladder" role="group" aria-label={label}
           viewBox={`0 0 ${VIEW_W} ${height}`}>
        <title>{label}</title>
        {[1, 2, 3, 4, 5].map((l) => (
          <text key={`col${l}`} className="ho-col" x={X(l)} y={12}>H{l}</text>
        ))}
        {placed.map(({ rung, y: at }, i) => {
          const prior = placed[i - 1];
          const check = checkOfRung(outline, rung);
          const live = check !== null && (!checks || checks.has(check)) && !!onCheck;
          const text = rung.kind === "heading"
            ? fit(rung.text, rung.level, rung.level === 1) : rung.text;
          const w = rung.kind === "heading" ? RUNGW(rung.level)
                  : rung.kind === "no-h1" ? 120 : 90;
          const name = rung.kind === "heading"
            ? `H${rung.level}: ${rung.text}${rung.state === "warn" ? " — flagged" : ""}`
            : rung.text;
          return (
            <g key={`${rung.kind}-${i}`}
               className={`ho-rung ho-${rung.kind} ho-${rung.state}`
                          + (rung.in_main === false ? " ho-outside" : "")
                          + (live ? " ho-live" : "")}
               role={live ? "button" : undefined}
               tabIndex={live ? 0 : undefined}
               aria-label={live ? `${name} — open its fix` : undefined}
               onClick={live ? () => onCheck!(check!) : undefined}
               onKeyDown={live ? (e) => {
                 if (e.key === "Enter" || e.key === " ") {
                   e.preventDefault();
                   onCheck!(check!);
                 }
               } : undefined}>
              {/* The connector down the parent column, drawn on the lower of
                  the two rungs it joins so it cannot outlive either. */}
              {prior && (
                <line className="ho-link"
                      x1={X(Math.min(prior.rung.level, rung.level))} y1={prior.y + 8}
                      x2={X(Math.min(prior.rung.level, rung.level))} y2={at - 8} />
              )}
              <line className="ho-mark" x1={X(rung.level)} y1={at}
                    x2={X(rung.level) + w} y2={at} />
              {/* In words and not only as a stroke pattern: a dash is not
                  there at all for a screen reader, which is why every rung
                  carries real text and why the gaps carry theirs. */}
              <text className="ho-text" x={X(rung.level) + w + 10} y={at + 4}>{text}</text>
            </g>
          );
        })}
      </svg>
      {more > 0 && (
        <p className="muted ho-more">
          {more} more heading{more === 1 ? "" : "s"} below the {kept} drawn
          {kept > RUNG_CAP && ` — past the ${RUNG_CAP} this block stops at, `
                             + "because the level that skipped is down there"}.
        </p>
      )}
      <div className="ho-legend">
        <span><i className="ho-key-ink" />heading present</span>
        <span><i className="ho-key-warn" />level skipped — the rung that should be here</span>
        <span><i className="ho-key-bad" />missing H1</span>
      </div>
    </figure>
  );
}

/** One row of the site-scope table: one fault shape on one template. */
export type SkipRow = {
  code: string; label: string; tone: string; check: string;
  prefix: string; pages: number; examples: string[];
  /** Whether the residual bucket really is the site's top level. It is not
   *  always: `templatesOf` calls nothing a template under ten pages of a
   *  first segment, so a shape carried by four `/news/*` pages lands in the
   *  residual bucket with no template found - and calling that "/ and
   *  top-level pages" is the table stating something false about paths the
   *  reader can see in the same cell. Found by the guard, which reads the
   *  rendered row rather than the grouping. */
  rooted: boolean;
};

/** Which skip sits on which template, from the shapes the server read and
 *  the template rule the causes table above already uses.
 *
 *  Exported because the block's whole argument is in this grouping, and a
 *  guard that can only reach it through a browser can only ever check that
 *  a table rendered. */
export function skipRows(shapes: HeadingShapes): SkipRow[] {
  const rows: SkipRow[] = [];
  const byCode = new Map<string, string[]>();
  for (const [url, codes] of Object.entries(shapes.at ?? {})) {
    for (const code of codes) {
      const seen = byCode.get(code);
      if (seen) seen.push(url); else byCode.set(code, [url]);
    }
  }
  for (const [code, urls] of byCode) {
    const meta = shapes.labels?.[code]
      ?? { label: code, tone: "warn", check: "heading-skip" };
    // The same function the check group line above this table groups with.
    // It returns nothing at all under ten pages, which is its rule and not
    // an edge case: a shape on nine pages has no template, so it is one row
    // over all of them.
    const groups = templatesOf(urls.map((u) => ({
      fingerprint: u, urls: [u], state: "open", names_a_page: true })));
    const heads = groups.map((g) => g.prefix).filter((p) => p !== "");
    const buckets = groups.length ? groups.map((g) => g.prefix) : [""];
    for (const prefix of buckets) {
      // `templatePrefixOf`, which is the rule `templatesOf` itself buckets
      // by. A `startsWith` here would agree with it on every path in the
      // fixture and part company on the first one carrying a query string.
      const inside = prefix === ""
        ? urls.filter((u) => !heads.includes(templatePrefixOf(templatePathOf(u))))
        : urls.filter((u) => templatePrefixOf(templatePathOf(u)) === prefix);
      if (!inside.length) continue;
      rows.push({ code, label: meta.label, tone: meta.tone, check: meta.check,
                  prefix, pages: inside.length,
                  // Top-level means one path segment or none - not
                  // `templatePrefixOf(...) === "/"`, which only ever holds
                  // for the home page itself: `/about` prefixes to
                  // `/about/`. Written the other way first, and the guard
                  // caught it by reading the rendered row against the paths
                  // printed in the same cell.
                  rooted: prefix === "" && inside.every(
                    (u) => templatePathOf(u).split("/").filter(Boolean).length <= 1),
                  // The item's "an example path or three when the template
                  // is not a glob": a residual bucket is not a pattern, so
                  // it is named by what is in it.
                  // Deduplicated: two URLs of one page - a trailing slash,
                  // a query - are one path, and the running product printed
                  // "/apply, /apply, /broker-cheat-sheet" on Acme before
                  // this line said so.
                  examples: prefix === ""
                    ? [...new Set(inside.map(templatePathOf))].sort().slice(0, 3)
                    : [] });
    }
  }
  return rows.sort((a, b) => b.pages - a.pages
                             || a.label.localeCompare(b.label)
                             || a.prefix.localeCompare(b.prefix));
}

/** How a template reads on the row. The residual bucket is not a glob, so
 *  it is not written as one - and it is only called the top level where its
 *  pages are actually at it. `anatomy.tsx`'s cause table says "No shared
 *  template" for the same bucket, which is the other half of this sentence
 *  and the wording this borrows. */
export const templateWord = (row: { prefix: string; rooted: boolean }) =>
  row.prefix !== "" ? `${row.prefix}*`
  : row.rooted ? "/ and top-level pages" : "no shared template";

/** The share of the whole one row must reach before the closing sentence is
 *  written. The item's own gate, and the reason it is there: "fix this
 *  template" is only advice while there is a template whose fixing changes
 *  the number. */
export const DOMINANT = 0.4;

export function closingLine(rows: SkipRow[]): string | null {
  const total = rows.reduce((n, r) => n + r.pages, 0);
  const top = rows[0];
  if (!top || !total || top.pages / total < DOMINANT) return null;
  return `Fix the ${templateWord(top)} template and the count above `
         + `drops by ${top.pages} on the next audit.`;
}

/** Block 2. One row per (fault shape × template), largest first. */
export function SkipsByTemplate({ shapes }: { shapes: HeadingShapes | null | undefined }) {
  if (!shapes) return null;
  const head = (
    <>
      <h4 className="ho-head">Which skip, on which template</h4>
      <p className="muted ho-lede">
        A skip is a template defect, not one defect per page: this is the
        shape of each fault and how many pages of each template carry it. One
        row is usually one fix.
      </p>
    </>
  );
  if (!shapes.recorded) {
    // Absent, not clean. A run that stored no heading list has nothing to
    // group, and an empty table would say the site's outlines are in order.
    return (
      <section className="ho-site">
        {head}
        <p className="muted ho-absent">
          This audit recorded no heading list on any of its {shapes.crawled}{" "}
          page{shapes.crawled === 1 ? "" : "s"}, so which skip sits where is not
          known for it — which is not the same as there being none. Re-audit
          the site to record them.
        </p>
      </section>
    );
  }
  const all = skipRows(shapes);
  if (!all.length) {
    return (
      <section className="ho-site">
        {head}
        <p className="muted ho-clean">
          None of the {shapes.pages} page{shapes.pages === 1 ? "" : "s"} this
          audit read the headings of skips a level or wants an H1.
        </p>
      </section>
    );
  }
  // Rows of one page collapse into a single line: forty rows of one page is
  // a list of pages, and the table is about templates.
  const rows = all.filter((r) => r.pages > 1);
  const ones = all.filter((r) => r.pages === 1);
  const largest = Math.max(...all.map((r) => r.pages), 1);
  const shapesN = new Set(all.map((r) => r.code)).size;
  const pagesN = Object.keys(shapes.at ?? {}).length;
  const closing = closingLine(all);
  // Item 180 (ruling 20260918-0402): the pages this picture leaves out, named
  // once, rather than a silent difference between the picture and the table.
  const skipped = shapes.not_checked ?? [];
  return (
    <section className="ho-site">
      {head}
      {skipped.length > 0 && (
        <p className="muted ho-not-checked">
          {skipped.length} page{skipped.length === 1 ? "" : "s"} here
          {skipped.length === 1 ? " is" : " are"} not read by these checks: the
          canonical points at another page, which is the one judged
          {" "}({skipped.slice(0, 3).join(", ")}
          {skipped.length > 3 ? ` and ${skipped.length - 3} more` : ""}).
        </p>
      )}
      <table className="ho-grid">
        <thead>
          {/* Three columns and not the mockup's four. The mockup gives the
              bar a column and the number an unlabelled one beside it, and
              `test_no_column_header_is_visible_only_to_a_screen_reader`
              refuses a header with no visible name - rightly: a column a
              sighted reader cannot see the name of is a column nobody
              named. The bar and the count are one fact, so they are one
              cell, which is what they were describing anyway. */}
          <tr><th>skip</th><th>template</th>
              <th className="ho-barcol">pages</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.code}|${r.prefix}`}>
              <td><code className={`ho-shape ho-shape-${r.tone}`}>{r.label}</code></td>
              <td className="ho-tpl">
                <code>{templateWord(r)}</code>
                {r.examples.length > 0 && (
                  <span className="muted"> · {r.examples.join(", ")}</span>
                )}
              </td>
              <td className="ho-pages">
                {/* The bar is a graphic whose count stands beside it, so it
                    is `aria-hidden`: the number is the same fact, and
                    announcing both reads it twice. */}
                <span className={`ho-bar ho-bar-${r.tone}`} aria-hidden="true"
                      style={{ width: `${(r.pages / largest) * 100}%` }} />
                <b className="ho-n">{r.pages}</b>
              </td>
            </tr>
          ))}
          {ones.length > 0 && (
            <tr className="ho-ones">
              <td colSpan={2} className="muted">
                {ones.length} other page{ones.length === 1 ? "" : "s"}, one each
              </td>
              <td className="ho-pages"><b className="ho-n">{ones.length}</b></td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="muted ho-closing">
        {shapesN} shape{shapesN === 1 ? "" : "s"} across {pagesN}{" "}
        page{pagesN === 1 ? "" : "s"}.{closing ? ` ${closing}` : ""}
      </p>
    </section>
  );
}
