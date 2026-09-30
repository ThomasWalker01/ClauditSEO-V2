/** One meaning, one definition, one place (item 166, 140's other half).
 *
 *  `clauditseo/glossary.json` is the registry, and this file only renders it.
 *  The engine reads the same file for a client report's appendix, so the
 *  sentence under a chip, the glossary route and the appendix are one text.
 *
 *  Why a disclosure and not a hover or a slide-in: a hover is invisible until
 *  found, unreachable from a keyboard or a touch screen, and fails WCAG 1.4.13
 *  on a chip this small; a slide-in is a second surface for a sentence, and
 *  the reader loses what they were reading. `<details>` at the top of the
 *  block, before the first chip, is inline, keyboard-reachable, closed by
 *  default and costs no height until opened. Under the block is where it gets
 *  lost (operator ruling, 2026-09-14).
 *
 *  No block carries its own copy of a definition: a block names registry ids
 *  and `Legend` draws the words.
 */
import registry from "../../clauditseo/glossary.json";

export type Entry = {
  id: string; kind: "tone" | "term"; vocabulary: string; word: string;
  full: string; engine?: string; class?: string; matches?: string[];
};

export const ENTRIES: Entry[] = (registry as { entries: Entry[] }).entries;
const BY_ID = new Map(ENTRIES.map((e) => [e.id, e]));

/** The same expression as `glossary.FIRST_SENTENCE`; a test holds them
 *  together. `robots.txt` carries a stop with no space after it, so it does
 *  not end a sentence. */
export const FIRST_SENTENCE = /^(.+?[.!?])(?=\s+[A-Z]|\s*$)/s;

export function short(e: Entry): string {
  const text = e.full.trim();
  const m = FIRST_SENTENCE.exec(text);
  return m ? m[1] : text;
}

export function entry(id: string): Entry {
  const e = BY_ID.get(id);
  // A block naming an id the registry does not hold is a build fault, not a
  // missing sentence to paper over: say so where it is drawn.
  if (!e) throw new Error(`glossary has no entry "${id}"`);
  return e;
}

/** The loading word, from the registry (items 166 and 179): every screen
 *  that is still reading says this and nothing else. Here rather than in
 *  `components`, which the selection imports - this module imports nothing. */
export const LOADING_WORD: string = entry("state-loading").word;

/** The one word for an analysis nothing has read (item 180 e7, audit F14).
 *
 *  Item 180 unified "unread", "not run" and "no analysis yet" and left the
 *  constant private to `client_lanes.tsx`, so three other screens carried on
 *  spelling their own: the part head and the catalogue dot said "not
 *  analysed", a catalogue row said "no analysis yet", and another said "not
 *  run". Measured on one pane in one render, all four at once. */
export const NOT_READ: string = entry("not-read").word;

export const glossaryHref = (id?: string) => `#/glossary${id ? `?term=${encodeURIComponent(id)}` : ""}`;

/** The disclosure. Placed at the top of the block, before its first chip. */
export function Legend({ ids, label = "what these mean" }: { ids: string[]; label?: string }) {
  return (
    <details className="legend" data-legend={ids.join(" ")}>
      <summary>{label}</summary>
      <dl className="legend-list">
        {ids.map((id) => {
          const e = entry(id);
          return (
            <div key={id} className="legend-row" data-term={id}>
              <dt>{e.word}</dt>
              <dd>
                <span className="legend-short">{short(e)}</span>{" "}
                <a className="legend-full" href={glossaryHref(id)}
                   aria-label={`full definition of ${e.word}`}>full definition</a>
              </dd>
            </div>
          );
        })}
      </dl>
    </details>
  );
}

/** The glossary route: the whole registry, each entry once, in full. Reference
 *  rather than a step in the loop, so it is not one of the four destinations;
 *  it is also where every term can be reviewed in one place. */
export function GlossaryView({ term }: { term?: string }) {
  const groups = new Map<string, Entry[]>();
  for (const e of ENTRIES) {
    if (!groups.has(e.vocabulary)) groups.set(e.vocabulary, []);
    groups.get(e.vocabulary)!.push(e);
  }
  return (
    <section className="glossary">
      <h2>Glossary</h2>
      <p className="muted">
        Every colour, mark and term the screens and client reports use, with
        what it means. The sentence shown beside a mark on a screen is the first
        sentence here.
      </p>
      {[...groups].map(([vocab, es]) => (
        <section key={vocab} className="glossary-group">
          <h3>{vocab[0].toUpperCase() + vocab.slice(1)}</h3>
          <dl>
            {es.map((e) => (
              <div key={e.id} id={`term-${e.id}`} data-term={e.id}
                   className={`glossary-entry${term === e.id ? " glossary-here" : ""}`}
                   ref={term === e.id ? (el) => el?.scrollIntoView({ block: "center" }) : undefined}>
                <dt>
                  {e.class ? <span className={`tone ${e.class}`}>{e.word}</span> : e.word}
                  {e.engine && <small className="muted glossary-engine">{e.engine}</small>}
                </dt>
                <dd>{e.full}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </section>
  );
}

/** The screen word for a finding's source (item 166 wording ruling,
 *  2026-09-15): `sweep` reads "automatic checks" and `brief` reads
 *  "analysis". The engine names stay in the payload and the tone names. */
export function sourceWord(source: string): string {
  return source === "sweep" ? entry("sweep").word : source === "brief" ? entry("brief").word : source;
}
