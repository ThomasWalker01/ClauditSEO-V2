/** Which URL owns a page — the Indexability & canonicals part's "now"
 *  block (brief v16g).
 *
 *  One card per chain: the page, an arrow per `rel=canonical`, and the node
 *  the trail ends on. At page scope it is the selected page's own chain; at
 *  site scope it is the site's chains that are not the healthy case, worst
 *  first. Ported from the operator's approved mockup
 *  (`canonical_chains_mockup.html`); the paths in that file are illustrative
 *  and every one drawn here is read off the payload.
 *
 *  **Nothing here decides what a chain is or which kind it takes**, the same
 *  split brief v16a drew for the Structured data picture and v16b for the
 *  depth histogram: the walk, the four kinds, the terminal reason and the
 *  sentence under the drawing all arrive whole from
 *  `onp.canonical_chain_state`, which is the function the canonical checks
 *  themselves read their decision from. This file places dots and arrows.
 *  That is the item's rule — a chain's colour and the finding beside it must
 *  never disagree — and one function is the only way to hold it.
 *
 *  **Nodes are `<g role="button">`s and not bare `<circle>`s.** Pressing one
 *  opens that page in scope, so it is a control; the mockup's SVG has no
 *  element that is one. `role="group"` on the `<svg>` rather than
 *  `role="img"` for the reason the outline ladder gives: a labelled
 *  `role="img"` may not hold focusable children, which is what axe reported
 *  against the Images scatter on its first run.
 *
 *  **Tone.** Four of the stylesheet's existing semantic tokens and no new
 *  colour, which is item 140's rule: `--good` for a page that owns itself,
 *  `--warn-strong` for one pointing somewhere real, `--danger` for a chain
 *  that ends where nothing can be indexed, `--text-muted` for the parameter
 *  and trailing-slash variants no check raises. The mockup's `--ok/--warn/
 *  --bad/--mute` have counterparts here already and inventing a fifth
 *  would be the second answer 140 exists to remove.
 */
import { pathOf } from "./components";

/** One node of a walk, as the server recorded it. */
export type ChainNode = {
  url: string;
  path: string;
  /** The path, and the query where there is one. Acme's only chain is
   *  `/apply?product_type=loc` → `/apply`, and a picture whose two nodes
   *  both read `/apply` would be a picture of nothing. */
  label: string;
  in_crawl: boolean;
  /** A canonical pointing at another host: one hop, and no attempt to walk
   *  into a site this run never read. */
  external: boolean;
  status: number | null;
  noindex: boolean;
  robots_blocked: boolean;
  in_sitemap: boolean;
};

/** One page's canonical chain, walked. */
export type Chain = {
  url: string;
  path: string;
  label: string;
  /** `ok | warn | bad | mute` — the four kinds, decided on the server. */
  kind: "ok" | "warn" | "bad" | "mute";
  hops: number;
  relation: string;
  /** Why the chain ends where it does — `noindex`, `404`, `not crawled`,
   *  `loop`, `no canonical` — or null where it ends somewhere fine. */
  terminal: string | null;
  external_host: string | null;
  /** The check the record holds against this page, or null. `mute` is the
   *  one kind that deliberately has none. */
  check: string | null;
  nodes: ChainNode[];
  /** The sentence under the drawing, generated from the kind on the server
   *  so the words and the colour cannot part company. */
  note: string;
};

/** The site's chains that are not the healthy case, as the server
 *  assembled them. */
export type CanonicalChains = {
  run_id: string;
  /** False where no page of the run stored a canonical field at all:
   *  absent, not clean, and the block says so rather than declaring the
   *  site healthy on a measurement nobody made. */
  recorded: boolean;
  /** `page | nav | site | full`, for the narrow-run qualifier. */
  scope: string | null;
  /** Pages the run stored, whether or not each carried a canonical. */
  crawled: number;
  /** Pages walked, and how many of them own themselves. Carried whole
   *  rather than counted from `chains`, which is capped. */
  total: number;
  healthy: number;
  chains: Chain[];
  cap: number;
  more: number;
  /** The canonical checks, so "N more" narrows the record to the same rows
   *  a card's check id does. From the server: a second copy here would
   *  drift the first time a check is added. */
  checks: string[];
};

/** The drawing's box. The mockup's numbers, so a card ported from it keeps
 *  its proportions: 520 wide, the row of nodes at 34, and a taller box for
 *  the single node because its loop is drawn above the line. */
const VIEW_W = 520;
const ROW_Y = 34;
const PAD = 20;

/** The radius of the invisible circle that catches a press on a node, in
 *  viewBox units.
 *
 *  **Not the same as the dot's, and the difference is WCAG 2.2's 2.5.8.**
 *  A 6-unit dot is a 12-unit target, and the drawing is scaled to the card
 *  rather than drawn at its viewBox size — two cards across a 1400px shell
 *  puts a 520-unit box into about 320 CSS px, so every unit is worth about
 *  0.62 of a pixel — measured, not estimated: 18 units came back as a
 *  22.2px target on the first reading of this block and 22.2 is a fail.
 *  22 units is a 44-unit target and 27px at that scale, and the closest two
 *  nodes can ever come is 96 units (six nodes across the box), so a target
 *  this size cannot overlap its neighbour.
 *  `test_a_node_is_a_target_big_enough_to_press` measures the rendered
 *  figure rather than trusting this arithmetic, which is how the first
 *  number was caught. */
const HIT_R = 22;

/** Where node `i` of `n` sits. */
const xOf = (i: number, n: number) =>
  PAD + i * ((VIEW_W - 2 * PAD) / Math.max(n - 1, 1));

/** How a node's own text is anchored: the first reads from the left edge,
 *  the last to the right edge, everything between is centred. Without this
 *  a long first path runs off the box, which is what the mockup does and
 *  the reason it does it. */
const anchorOf = (i: number, n: number) =>
  i === 0 ? "start" : i === n - 1 ? "end" : "middle";

/** What a chain's sub-line says: its state, and the check the record holds
 *  for it. `healthy` where there is nothing to say — the item's own word. */
export function subOf(chain: Chain): string {
  if (chain.kind === "ok") return "healthy";
  const state = chain.check ? "open" : chain.kind === "mute" ? "no check" : "unraised";
  return chain.check ? `${state} · ${chain.check}` : state;
}

/** The accessible name of one card's drawing, in the form the item states:
 *  "canonical chain for /path, 2 hops, ends on noindex". A dashed stroke
 *  and a coloured dot are not there at all for a screen reader, so the
 *  shape is spelled out. */
export function titleOf(chain: Chain): string {
  const hops = `${chain.hops} hop${chain.hops === 1 ? "" : "s"}`;
  const end = chain.terminal ? `ends on ${chain.terminal}`
            : chain.external_host ? `ends on ${chain.external_host}`
            : chain.hops === 0 ? "canonicalises to itself"
            : "ends on an indexable page";
  return `canonical chain for ${chain.label}, ${hops}, ${end}`;
}

/** One card: the path, the state, the drawing, and the generated note. */
export function ChainCard({ chain, onPage, onCheck, checks }: {
  chain: Chain;
  /** Open a node's page in scope. The item's "clicking a node opens that
   *  page in scope"; a node the crawl never read has nothing to open. */
  onPage?: (url: string) => void;
  /** Narrow the record to a check. The item's "clicking the check id in
   *  the sub-line narrows the record". */
  onCheck?: (checkId: string) => void;
  /** Which checks the record actually holds a row for, so a sub-line never
   *  offers to narrow to nothing. */
  checks?: ReadonlySet<string>;
}) {
  const n = chain.nodes.length;
  const height = n === 1 ? 90 : 70;
  const title = titleOf(chain);
  const live = chain.check !== null && (!checks || checks.has(chain.check))
               && !!onCheck;
  return (
    <div className={`cc-card cc-${chain.kind}`}>
      <h5 className="cc-title">
        {chain.label}
        <span className="cc-sub">
          {live ? (
            <button type="button" className="cc-check"
                    onClick={() => onCheck!(chain.check!)}>
              {subOf(chain)}
            </button>
          ) : subOf(chain)}
        </span>
      </h5>
      <svg className="cc-svg" role="group" aria-label={title}
           viewBox={`0 0 ${VIEW_W} ${height}`}>
        <title>{title}</title>
        {/* One marker per card, and its id carries the card's own path:
            two cards of different kinds on one screen sharing a marker id
            would both take the first one's colour, which is what a single
            `#m-warn` did on the first reading. */}
        <defs>
          <marker id={`cc-arrow-${chain.kind}`} viewBox="0 0 10 10" refX="9"
                  refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path className="cc-head" d="M0,0 L10,5 L0,10 z" />
          </marker>
        </defs>
        {chain.nodes.map((node, i) => {
          const x = xOf(i, n);
          const last = i === n - 1;
          // The terminal node takes the bad token where the chain ends
          // somewhere nothing can be indexed, whatever the rest of the
          // chain is drawn in — that is the node the fix is about.
          const tone = last && chain.terminal && chain.terminal !== "no canonical"
            ? "cc-node-bad" : "";
          const open = !!onPage && node.in_crawl && !node.external;
          const name = `${node.label}${last && chain.terminal
            ? ` — ${chain.terminal}` : ""}${open ? " — open this page" : ""}`;
          return (
            <g key={`${node.url}-${i}`} className={`cc-node ${tone}`}
               role={open ? "button" : undefined}
               tabIndex={open ? 0 : undefined}
               aria-label={open ? name : undefined}
               onClick={open ? () => onPage!(node.url) : undefined}
               onKeyDown={open ? (e) => {
                 if (e.key === "Enter" || e.key === " ") {
                   e.preventDefault();
                   onPage!(node.url);
                 }
               } : undefined}>
              {open && <circle className="cc-hit" cx={x} cy={ROW_Y} r={HIT_R} />}
              <circle className="cc-dot" cx={x} cy={ROW_Y} r={6} />
              {/* Real text under every node, never a tooltip: the path is
                  the one thing a reader needs off this picture. */}
              <text className="cc-path" x={x} y={ROW_Y + 22}
                    textAnchor={anchorOf(i, n)}>
                {node.external && chain.external_host
                  ? chain.external_host : node.label}
                {last && chain.terminal ? `  · ${chain.terminal}` : ""}
              </text>
              {i < n - 1 && (
                <line className="cc-arrow" x1={x + 8} y1={ROW_Y}
                      x2={xOf(i + 1, n) - 10} y2={ROW_Y}
                      markerEnd={`url(#cc-arrow-${chain.kind})`} />
              )}
            </g>
          );
        })}
        {n === 1 && !chain.terminal && (
          <>
            <path className="cc-loop" d={`M${PAD + 6},${ROW_Y - 4} a18,18 0 1,1 0,8`}
                  markerEnd={`url(#cc-arrow-${chain.kind})`} />
            <text className="cc-itself" x={66} y={ROW_Y - 14}>itself</text>
          </>
        )}
      </svg>
      <p className="cc-note">{chain.note}</p>
    </div>
  );
}

/** The legend, one entry per kind, in the mockup's words. Rendered text and
 *  not a title attribute, per the provenance invariant. */
const LEGEND: [Chain["kind"], string][] = [
  ["ok", "self-canonical — as it should be"],
  ["warn", "points elsewhere — check it is intended"],
  ["bad", "ends on a page that cannot be indexed"],
  ["mute", "parameter or slash variant"],
];

/** The word a narrow run's heading carries, or null. `crawl_depth`'s
 *  `narrowWord` says the same about the depth block, and these are its two
 *  narrow answers. */
const narrowWord = (scope: string | null) =>
  scope === "page" ? "page scan" : scope === "nav" ? "nav scan" : null;

export function CanonicalChainsBlock({ chains, chain, page, onPage, onCheck,
                                       checks }: {
  /** The site's non-healthy chains. Null where there is no stored crawl to
   *  read at all — which is a different answer from a crawl that recorded
   *  no canonical, and that one arrives with `recorded: false`. */
  chains: CanonicalChains | null | undefined;
  /** The selected page's own chain, from its facts. Drawn instead of the
   *  grid whenever a page is in scope. */
  chain?: Chain | null;
  page: string | null;
  onPage?: (url: string) => void;
  onCheck?: (checkId: string) => void;
  checks?: ReadonlySet<string>;
}) {
  if (!chains) return null;
  const narrow = narrowWord(chains.scope);
  const head = (
    <>
      <h4 className="cc-head">
        Canonical chains
        {narrow && <span className="cc-narrow"> — {narrow}: over those pages alone</span>}
      </h4>
      {/* The item's sentence, verbatim. It is the block's whole argument:
          the drawing is a walk, and this says why the walk matters. */}
      <p className="muted cc-blurb">
        An arrow is a <code>rel=canonical</code>; a loop back to itself is the
        healthy case. Anything longer than one hop, or ending somewhere that is
        not indexable, is drawn in full so the fix is read off the picture.
      </p>
    </>
  );
  if (!chains.recorded) {
    // Absent, not clean. A run that stored no canonical has nothing to walk,
    // and "every page canonicalises to itself" would be a claim about a
    // measurement this run never made.
    return (
      <section className="cc-root">
        {head}
        <p className="muted cc-absent">
          This audit recorded no canonical tag on any of its {chains.crawled}{" "}
          page{chains.crawled === 1 ? "" : "s"}, so which URL owns each of them
          is not known — which is not the same as their all owning themselves.
          Re-audit the site to record it.
        </p>
      </section>
    );
  }
  if (page) {
    // Page scope: that page's chain, whatever kind it is — including the
    // healthy one, which the site-scope list drops. A reader who has asked
    // about one page is owed an answer about it.
    return (
      <section className="cc-root cc-page">
        {head}
        {chain ? (
          <div className="cc-grid">
            <ChainCard chain={chain} onPage={onPage} onCheck={onCheck}
                       checks={checks} />
          </div>
        ) : (
          <p className="muted cc-none">
            This audit stored no canonical for {pathOf(page)}, so there is no
            chain to walk from it.
          </p>
        )}
        <Legend />
      </section>
    );
  }
  if (!chains.chains.length) {
    // The item's second degradation, and it is a sentence rather than an
    // empty grid: 226 identical self-loops is not a picture.
    return (
      <section className="cc-root">
        {head}
        <p className="cc-clean">
          Every page canonicalises to itself — all {chains.total} of them.
        </p>
      </section>
    );
  }
  return (
    <section className="cc-root">
      {head}
      <div className="cc-grid">
        {chains.chains.map((c) => (
          <ChainCard key={c.url} chain={c} onPage={onPage} onCheck={onCheck}
                     checks={checks} />
        ))}
      </div>
      {chains.more > 0 && (
        <p className="cc-more">
          {chains.more} more chain{chains.more === 1 ? "" : "s"} below these.{" "}
          {onCheck && (
            <button type="button" className="cc-morelink"
                    onClick={() => onCheck(chains.checks[0])}>
              open the record on the canonical checks
            </button>
          )}
        </p>
      )}
      {/* The count the cap is measured against, so a capped grid never reads
          as the whole answer. */}
      <p className="muted cc-tally">
        {chains.healthy} of {chains.total} crawled pages canonicalise to
        themselves.
      </p>
      <Legend />
    </section>
  );
}

function Legend() {
  return (
    <div className="cc-legend">
      {LEGEND.map(([kind, words]) => (
        <span key={kind} className={`cc-key cc-${kind}`}>
          <i aria-hidden="true" />{words}
        </span>
      ))}
    </div>
  );
}
