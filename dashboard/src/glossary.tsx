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
import { useEffect, useRef, useState } from "react";
import registry from "../../clauditseo/glossary.json";

export type Entry = {
  id: string; kind: "tone" | "term"; vocabulary: string; word: string;
  full: string; engine?: string; class?: string; matches?: string[];
  /** One word drawn in a second place (item 263): this id keeps its group,
   *  tone class and engine name, and takes its word and definition from the
   *  entry named. */
  same_as?: string;
};

type Stored = Omit<Entry, "word" | "full"> & { word?: string; full?: string };
const RAW = (registry as { entries: Stored[] }).entries;
const RAW_BY_ID = new Map(RAW.map((e) => [e.id, e]));

/** Every id, each with its word and definition - a `same_as` entry's taken
 *  from the entry it names, as `glossary.entries()` does on the engine side. */
export const ENTRIES: Entry[] = RAW.map((e) => {
  if (!e.same_as) return e as Entry;
  const t = RAW_BY_ID.get(e.same_as)!;
  return { ...(t.engine ? { engine: t.engine } : {}), ...e, word: t.word!, full: t.full! };
});
const BY_ID = new Map(ENTRIES.map((e) => [e.id, e]));
/** One entry per word: what the glossary route lists (item 263). */
export const DEFINITIONS: Entry[] = ENTRIES.filter((e) => !e.same_as);

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

/** Whether a registry entry is drawn in `scope`, outside the legend itself:
 *  a tone by its class, a term by its word (items 268 row 8, 270 row 16). */
function drawnIn(scope: Element, legend: Element, id: string): boolean {
  const e = entry(id);
  if (e.kind === "tone" && e.class) {
    return [...scope.querySelectorAll(`.${e.class}`)].some((el) => !legend.contains(el));
  }
  // The legend's own text is one run inside the block's, so cut it out.
  const text = (scope.textContent ?? "").replace(legend.textContent ?? "", "");
  return text.toLowerCase().includes(e.word.toLowerCase());
}

/** The disclosure. Placed at the top of the block, before its first chip.
 *
 *  `ifDrawn` names entries the block draws only on some subjects - the
 *  severities and states of the rows it holds (items 268 row 8, 270 row
 *  16). Each is defined only where the block draws it: Structured data
 *  listed Critical, "seen once" and "not measured" with none on screen. Read
 *  off the block as it renders, since the rows come from several renderers
 *  and some arrive after the legend does. */
export function Legend({ ids, label = "what these mean", ifDrawn = [] }: {
  ids: string[]; label?: string; ifDrawn?: string[];
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  const [drawn, setDrawn] = useState<string[]>([]);
  const want = ifDrawn.join(" ");
  useEffect(() => {
    const legend = ref.current;
    const scope = legend?.parentElement;
    if (!legend || !scope || !want) { setDrawn([]); return; }
    const read = () => {
      const now = want.split(" ").filter((id) => drawnIn(scope, legend, id));
      setDrawn((was) => (was.join(" ") === now.join(" ") ? was : now));
    };
    read();
    const watch = new MutationObserver(read);
    watch.observe(scope, { childList: true, subtree: true, characterData: true,
                           attributes: true, attributeFilter: ["class"] });
    return () => watch.disconnect();
  }, [want]);
  // One row per definition (item 263): two ids that are one word - a
  // measurement band and a check state that both say "not measured" - drew
  // the same sentence twice once they shared it. The first id names the row.
  const seen = new Set<string>();
  const shown = [...ids.filter((id) => !ifDrawn.includes(id) || drawn.includes(id)),
                 ...drawn.filter((id) => !ids.includes(id))];
  const rows = shown.filter((id) => {
    const def = entry(id).same_as ?? id;
    if (seen.has(def)) return false;
    seen.add(def);
    return true;
  });
  return (
    <details className="legend" data-legend={shown.join(" ")} ref={ref}>
      <summary>{label}</summary>
      <dl className="legend-list">
        {rows.map((id) => {
          const e = entry(id);
          return (
            <div key={id} className="legend-row" data-term={id}>
              <dt>{e.word}</dt>
              <dd>
                <span className="legend-short">{short(e)}</span>{" "}
                <a className="legend-full" href={glossaryHref(e.same_as ?? id)}
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
export function GlossaryView({ term: asked }: { term?: string }) {
  // A link that names a `same_as` id lands on the word's one definition.
  const term = asked ? (BY_ID.get(asked)?.same_as ?? asked) : asked;
  const groups = new Map<string, Entry[]>();
  for (const e of DEFINITIONS) {
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
      {/* Screen audits round 4 (Glossary UX-02): 122 entries in 25 groups
          had no index; each group is a step away. Buttons, not hash links,
          because the address is the router's. */}
      <nav className="glossary-index" aria-label="Glossary groups">
        {[...groups].map(([vocab]) => (
          <button key={vocab} type="button" className="glossary-index-go"
                  onClick={() => document.getElementById(`group-${vocab.replace(/\W+/g, "-")}`)
                    ?.scrollIntoView({ block: "center" })}>
            {vocab[0].toUpperCase() + vocab.slice(1)}
          </button>
        ))}
      </nav>
      {[...groups].map(([vocab, es]) => (
        <section key={vocab} className="glossary-group" id={`group-${vocab.replace(/\W+/g, "-")}`}>
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
