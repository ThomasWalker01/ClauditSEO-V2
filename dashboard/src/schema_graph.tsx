/** The Structured data picture — Layout 1, stacked drill (brief v16a step AT-b).
 *
 *  Ported from the designer's `L1_stacked_drill.html`, whose `renderGraph`
 *  and `drill` functions are `RENDER_RULES.md` in code. Ported rather than
 *  re-derived, for the reason the item gives: the rules are the
 *  specification and that file is the rules, so a second derivation would
 *  be a second answer to the same question. Section numbers below cite
 *  `RENDER_RULES.md`.
 *
 *  **Nothing here computes what the picture says.** The model arrives whole
 *  from `clauditseo/schema_graph.py` — nodes, ghosts, edges, collections,
 *  captions, stats, states and both verdicts. This file decides where boxes
 *  go and what colour a ring is, and reads every number off the model. That
 *  split is the point of building the model server-side: the picture has to
 *  be reproducible from what a crawl stored, months later, without the page
 *  being fetched again.
 *
 *  **Tone (RESPONSE, "Things in the brief I think are wrong", third point).**
 *  Nothing is filled except finding badges, which carry a level, and count
 *  pills, which carry a count. A node's state is its ring, a block's state
 *  is its box, and `@type` is text. Every reference mockup broke this by
 *  filling node cards from a per-`@type` palette; the first instinct on
 *  reading this file will be to reach for one, and `tests/` refuses it.
 */
import { SecondaryButton } from "./buttons";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Pill } from "./pill";
import {
  Category, SchemaGraphCollection, SchemaGraphFinding, SchemaGraphModel,
  SchemaGraphNode, SchemaGraphProp,
} from "./anatomy";

/** The tier rows, in the order section 3 fixes them, with the words the
 *  screen uses. A tier with nothing in it is not drawn; a tier with nothing
 *  *declared* is drawn as one line saying so, because the absence is the
 *  finding. */
const TIER_WORDS: Record<string, string> = {
  site: "site & page", entity: "the business", other: "other top-level",
};

/** Within the site tier, section 3's order. Anything unlisted sorts last in
 *  source order, which is what `99` does. */
const TIER_ORDER = ["WebSite", "WebPage", "BreadcrumbList", "ImageObject"];

/** Chips per card (§9) and badges per thing (§7). Four and six at the
 *  design width; the compact rules in §14 halve the chips. */
const MAX_CHIPS = 6;
const MAX_CHIPS_COMPACT = 4;
const MAX_BADGES = 4;
const MAX_CHIP_BADGES = 2;

/** §10: an edge label is truncated here. Longer labels overlap the boxes
 *  they sit between, which is worse than an ellipsis. */
const EDGE_LABEL_CAP = 34;

/** §14. 1568 is the design width; 1024 collapses the drill to two columns
 *  and hides resolved-edge labels. */
const NARROW = 1024;

/** The sticky height (220 at the design width, 160 at 1024) lives in
 *  `schema_graph.css` and not here. It was set from here as an inline
 *  custom property first, which made the stylesheet's `max-width: 1024px`
 *  and this file's `< NARROW` two owners of one breakpoint: at exactly
 *  1024 the media query applied and the inline value overrode it, so the
 *  capture measured 220 where the rules say 160. One owner, and the
 *  comparison below is `<=` so what `compact` means and what the media
 *  query means are the same set of widths. */

function tierRank(n: SchemaGraphNode): number {
  const i = TIER_ORDER.indexOf(n.types[0]);
  return i < 0 ? 99 : i;
}

function trunc(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/** §7's badges: the finding numbers, in severity colour, at most `max`
 *  then `+n`. The same numbers appear on the checklist, in the drill and on
 *  the fix cards; §7 calls that the only agreement mechanism, so they are
 *  read off the model's own ordering and never renumbered here. */
function Badges({ ns, findings, max = MAX_BADGES }: {
  ns: number[]; findings: Map<number, SchemaGraphFinding>; max?: number;
}) {
  if (!ns.length) return null;
  const shown = ns.slice(0, max);
  return (
    <span className="sg-badges">
      {shown.map((n) => {
        const f = findings.get(n);
        return (
          <i key={n} className={`sg-bd sg-bd-${f?.sev_class ?? "info"}`}
             title={f?.name ?? ""}>{n}</i>
        );
      })}
      {ns.length > max && <i className="sg-bd sg-bd-more">+{ns.length - max}</i>}
    </span>
  );
}

/** The word under a card: the worst finding's level, or `clean`. Read from
 *  the model's own list rather than recomputed — the engine sorted it. */
function stateWord(ns: number[], findings: Map<number, SchemaGraphFinding>): string {
  if (!ns.length) return "clean";
  const sev = findings.get(ns[0])?.sev;
  if (sev === "Held") return "held";
  if (sev === "Info") return "note";
  return (sev ?? "info").toLowerCase();
}

/** §8's node card. Fixed size, so level 0 never grows with item counts:
 *  the only things that can add a card are top-level nodes, ghosts and
 *  inline copies, and a list of twenty-nine cities is one chip. */
function NodeCard({ node, model, findings, collections, selected, compact, onSelect }: {
  node: SchemaGraphNode; model: SchemaGraphModel;
  findings: Map<number, SchemaGraphFinding>;
  collections: Map<string, SchemaGraphCollection>;
  selected: string | null; compact: boolean;
  onSelect: (key: string) => void;
}) {
  const tags: { cls: string; text: string }[] = [];
  if (node.kind === "ghost-dangling") {
    tags.push({ cls: "red", text: "referenced · not defined" });
  } else if (node.kind === "ghost-expected") {
    tags.push({ cls: "grey", text: "expected · absent" });
  } else if (node.kind === "inline-copy") {
    tags.push({ cls: "red", text: "inline copy" });
  } else if (node.island) {
    tags.push({ cls: "amber", text: "island" });
  }
  // §13: the whole-site tags come off the sweep's own `template` flag,
  // carried on the node by the engine. Absent where no inventory ran, and
  // the note above the canvas says so rather than a tag guessing.
  for (const flag of node.flags) {
    if (flag.startsWith("template · ") || flag.startsWith("per page · ")) {
      tags.push({ cls: flag.startsWith("template") ? "violet" : "grey", text: flag });
    }
  }

  const title = node.kind === "ghost-expected"
    ? node.type + (node.count ? ` ×${node.count}` : "")
    : node.kind === "ghost-dangling" ? (node.sid ?? node.type) : node.type;

  let sub: JSX.Element;
  if (node.kind === "ghost-dangling") {
    const props = node.refs_in.map((r) => r.prop).join(", ");
    sub = <>{compact ? `← ${props}` : `${node.type} · referenced by ${props}`}</>;
  } else if (node.kind === "ghost-expected") {
    const first = node.flags[0] ?? "";
    sub = <>{compact ? first.split(" · ")[0]
                     : first + (node.note ? ` · ${node.note}` : "")}</>;
  } else if (node.kind === "inline-copy") {
    sub = <>{node.flags[0] ?? ""}</>;
  } else {
    sub = (
      <>
        {node.sid
          ? <code className="sg-sid">{node.sid}</code>
          : <code className="sg-sid sg-bad">no @id</code>}
        {node.name ? ` · ${trunc(node.name, compact ? 24 : 48)}` : ""}
      </>
    );
  }

  const chips = node.collections
    .map((k) => collections.get(k))
    .filter((c): c is SchemaGraphCollection => !!c);
  const maxChips = compact ? MAX_CHIPS_COMPACT : MAX_CHIPS;
  const shownChips = node.kind === "node" || node.kind === "inline-copy"
    ? chips.slice(0, maxChips) : [];

  return (
    <div className={`sg-node sg-k-${node.kind} sg-r-${node.role} sg-st-${node.state}`
                    + (node.island ? " sg-island" : "")
                    + (selected === node.key ? " sg-sel" : "")}
         data-key={node.key} role="button" tabIndex={0}
         onClick={(e) => { e.stopPropagation(); onSelect(node.key); }}
         onKeyDown={(e) => {
           if (e.key === "Enter" || e.key === " ") {
             e.preventDefault(); e.stopPropagation(); onSelect(node.key);
           }
         }}>
      <div className="sg-nhead">
        <span className="sg-nt">{title}</span>
        {tags.map((t) => (
          <span key={t.text} className={`sg-tag sg-tag-${t.cls}`}>{t.text}</span>
        ))}
        <Badges ns={node.findings} findings={findings} />
      </div>
      <div className="sg-nsub">{sub}</div>
      {/* The stats line is the engine's count, not this file's: a card that
          counted its own properties and a drill that counted them again is
          how two numbers about one node end up disagreeing. */}
      {!compact && node.kind === "node" && (
        <div className="sg-nstat">
          {node.stats.properties} properties
          {node.stats.lists > 0 && ` · ${node.stats.lists} list${node.stats.lists > 1 ? "s" : ""}`}
          {node.stats.refs_out > 0 && ` · ${node.stats.refs_out} ref${node.stats.refs_out > 1 ? "s" : ""} out`}
          {node.stats.dangling > 0 && (
            <> {"· "}<b className="sg-bad">{node.stats.dangling} dangling</b></>
          )}
          {" · "}
          <span className={`sg-sw sg-sw-${node.state}`}>
            {stateWord(node.findings, findings)}
          </span>
        </div>
      )}
      {shownChips.length > 0 && (
        <div className="sg-chips">
          {shownChips.map((c) => (
            <div key={c.key}
                 className={`sg-chip sg-st-${c.state}`
                            + (selected === c.key ? " sg-sel" : "")}
                 data-key={c.key} role="button" tabIndex={0}
                 onClick={(e) => { e.stopPropagation(); onSelect(c.key); }}
                 onKeyDown={(e) => {
                   if (e.key === "Enter" || e.key === " ") {
                     e.preventDefault(); e.stopPropagation(); onSelect(c.key);
                   }
                 }}>
              <span className="sg-cp">{c.prop}</span>
              <span className="sg-cc">{c.count}</span>
              {!compact && <span className="sg-cv">{c.caption}</span>}
              <Badges ns={c.findings} findings={findings} max={MAX_CHIP_BADGES} />
            </div>
          ))}
          {chips.length > maxChips && (
            <div className="sg-chip sg-more" data-key={node.key} role="button"
                 tabIndex={0}
                 onClick={(e) => { e.stopPropagation(); onSelect(node.key); }}
                 onKeyDown={(e) => {
                   if (e.key === "Enter" || e.key === " ") {
                     e.preventDefault(); e.stopPropagation(); onSelect(node.key);
                   }
                 }}>
              +{chips.length - maxChips} more
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type EdgeGeom = {
  key: string; d: string; kind: string; label: string;
  mx: number; my: number; dim: boolean;
};

type Box = { x: number; y: number; w: number; h: number; cx: number; cy: number };

/** A collection's chip belongs to its node: an edge touching either should
 *  keep both lit. §10's fade reads ownership rather than identity. */
function ownerKey(model: SchemaGraphModel, key: string): string {
  if (model.nodes.some((n) => n.key === key)) return key;
  if (model.ghosts.some((n) => n.key === key)) return key;
  const i = key.lastIndexOf("#");
  return i > 0 ? key.slice(0, i) : key;
}

/** §10's endpoint: the point on `a`'s border along the line to `b`'s
 *  centre. */
function perim(a: Box, b: Box): { x: number; y: number } {
  const dx = b.cx - a.cx, dy = b.cy - a.cy;
  if (dx === 0 && dy === 0) return { x: a.cx, y: a.cy };
  const s = Math.min(a.w / 2 / Math.abs(dx || 1e-6), a.h / 2 / Math.abs(dy || 1e-6));
  return { x: a.cx + dx * s, y: a.cy + dy * s };
}

/** §10, the whole rule: edges are an SVG overlay measured from the rendered
 *  boxes *after* layout, so they survive wrapping and resize. Computing them
 *  from the model's ordering instead would put an arrow through a card the
 *  moment a row wrapped. */
function useEdges(model: SchemaGraphModel, selected: string | null,
                  ref: React.RefObject<HTMLDivElement>) {
  const [edges, setEdges] = useState<EdgeGeom[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const R = el.getBoundingClientRect();
    const boxOf = (key: string): Box | null => {
      const e = el.querySelector(`[data-key="${CSS.escape(key)}"]`);
      if (!e) return null;
      const r = e.getBoundingClientRect();
      const x = r.left - R.left + el.scrollLeft, y = r.top - R.top + el.scrollTop;
      return { x, y, w: r.width, h: r.height, cx: x + r.width / 2, cy: y + r.height / 2 };
    };
    const all = Array.from(el.querySelectorAll(".sg-node"))
      .map((n) => boxOf((n as HTMLElement).dataset.key ?? ""))
      .filter((b): b is Box => !!b);
    const selOwner = selected ? ownerKey(model, selected) : null;
    const out: EdgeGeom[] = [];
    model.edges.forEach((e, i) => {
      const a = boxOf(e.from), b = boxOf(e.to);
      if (!a || !b) return;
      const overlapY = a.y < b.y + b.h && b.y < a.y + a.h;
      const between = overlapY && all.some((r) =>
        r !== a && r !== b
        && r.y < Math.max(a.y + a.h, b.y + b.h) && r.y + r.h > Math.min(a.y, b.y)
        && r.cx > Math.min(a.cx, b.cx) && r.cx < Math.max(a.cx, b.cx));
      const gapX = Math.max(a.x, b.x) - Math.min(a.x + a.w, b.x + b.w);
      // §10: same row and adjacent, or another node between them, arcs over
      // the row. A straight line there would pass through a third card.
      const sameRow = overlapY && (between || gapX < 30);
      let pa: { x: number; y: number }, pb: { x: number; y: number };
      let c1: string, c2: string, mx: number, my: number;
      if (sameRow) {
        const lift = (between ? 34 : 20) + Math.min(24, Math.abs(a.cx - b.cx) / 20);
        pa = { x: a.cx + (b.cx > a.cx ? a.w * 0.25 : -a.w * 0.25), y: a.y };
        pb = { x: b.cx + (b.cx > a.cx ? -b.w * 0.25 : b.w * 0.25), y: b.y };
        c1 = `${pa.x} ${pa.y - lift}`;
        c2 = `${pb.x} ${pb.y - lift}`;
        mx = (pa.x + pb.x) / 2;
        my = Math.min(pa.y, pb.y) - lift * 0.75;
      } else {
        pa = perim(a, b); pb = perim(b, a);
        const dx = pb.x - pa.x, dy = pb.y - pa.y;
        const vertical = Math.abs(dy) > Math.abs(dx);
        c1 = vertical ? `${pa.x} ${pa.y + dy * 0.45}` : `${pa.x + dx * 0.45} ${pa.y}`;
        c2 = vertical ? `${pb.x} ${pb.y - dy * 0.45}` : `${pb.x - dx * 0.45} ${pb.y}`;
        // An "expected" edge's label sits toward the target: the source is
        // the entity, and the thing being said is about the absent end.
        const t = e.kind === "expected" ? 0.68 : 0.5;
        mx = pa.x + (pb.x - pa.x) * t;
        my = pa.y + (pb.y - pa.y) * t;
      }
      const dim = !!selected && !(
        e.from === selected || e.to === selected
        || ownerKey(model, e.from) === selOwner
        || ownerKey(model, e.to) === selOwner);
      out.push({
        key: `${e.from}->${e.to}->${i}`,
        d: `M${pa.x} ${pa.y} C ${c1}, ${c2}, ${pb.x} ${pb.y}`,
        kind: e.kind, label: trunc(e.label, EDGE_LABEL_CAP), mx, my, dim,
      });
    });
    setEdges(out);
    setSize({ w: el.scrollWidth, h: el.scrollHeight });
  }, [model, selected, ref]);

  useLayoutEffect(() => { measure(); }, [measure]);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure, ref]);

  return { edges, size, measure };
}

/** §8's canvas: the tier × block grid, the hatched "not on the page" zone,
 *  and the edge overlay over both. */
function Level0({ model, findings, collections, selected, onSelect, compact }: {
  model: SchemaGraphModel; findings: Map<number, SchemaGraphFinding>;
  collections: Map<string, SchemaGraphCollection>;
  selected: string | null; onSelect: (key: string | null) => void;
  compact: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { edges, size } = useEdges(model, selected, ref);

  const multi = model.blocks.length > 1;
  const cols = multi ? model.blocks.length : 1;
  const hasOff = model.ghosts.length > 0;
  const tiersUsed = model.tiers.filter((t) =>
    [...model.nodes, ...model.ghosts].some((n) => n.role === t));

  return (
    // `role="presentation"`, which is the exception
    // `test_no_click_handlers_on_non_interactive_elements` names and this is
    // the shape it names: the canvas is not a control, it is a second way to
    // return to the page level, and both of the first ways are real - Escape
    // is bound above, and the `page` breadcrumb is a button. Giving the
    // canvas a tab stop would put a focusable nothing in front of every node
    // card on it.
    <div className={`sg-graph${compact ? " sg-compact" : ""}`} ref={ref}
         role="presentation" onClick={() => onSelect(null)}>
      <div className="sg-grid"
           style={{
             gridTemplateColumns:
               `repeat(${cols}, minmax(0, auto))${hasOff ? " minmax(200px, auto)" : ""}`,
             gridTemplateRows: `repeat(${tiersUsed.length}, auto)`,
           }}>
        {/* The block boxes span every tier row in their column (§8). A
            `@graph` inside one script is one box with several nodes; three
            scripts are three boxes, and that distinction is Acme's whole
            finding. */}
        {model.blocks.map((b, i) => (
          <div key={b.key} className={`sg-blockbox sg-st-${b.state}`} data-key={b.key}
               role="button" tabIndex={0}
               style={{ gridColumn: `${multi ? i + 1 : 1}`,
                        gridRow: `1 / ${tiersUsed.length + 1}` }}
               onClick={(e) => { e.stopPropagation(); onSelect(b.key); }}
               onKeyDown={(e) => {
                 if (e.key === "Enter" || e.key === " ") {
                   e.preventDefault(); e.stopPropagation(); onSelect(b.key);
                 }
               }}>
            <div className="sg-blabel">
              <span className="sg-mono">
                &lt;script&gt; {b.i}{multi ? "" : " · @graph"}
              </span>
              {!compact && <span className="sg-src">{b.source}</span>}
              {!compact && (
                <span className="sg-cnt">
                  {b.nodes.length} node{b.nodes.length > 1 ? "s" : ""}
                </span>
              )}
              <Badges ns={b.findings} findings={findings} />
            </div>
          </div>
        ))}
        {hasOff && (
          <div className="sg-offbox"
               style={{ gridColumn: `${cols + 1}`,
                        gridRow: `1 / ${tiersUsed.length + 1}` }}>
            <div className="sg-blabel"><span>not on the page</span></div>
          </div>
        )}
        {tiersUsed.map((t, ti) => {
          const cells = [];
          for (let c = 0; c < cols + (hasOff ? 1 : 0); c++) {
            const inBlocks = c < cols;
            const list = inBlocks
              ? model.nodes
                  .filter((n) => n.role === t && (multi ? n.block === c + 1 : true))
                  .slice()
                  .sort((x, y) => tierRank(x) - tierRank(y))
              : model.ghosts.filter((g) => g.role === t);
            const tierName = TIER_WORDS[t] ?? t;
            // A tier with no declared node is still drawn, collapsed to one
            // line (§3): the absence is the finding, and an omitted row
            // would read as a tier nobody asked about.
            const emptyTier = c === 0 && !model.nodes.some((n) => n.role === t);
            cells.push(
              <div key={`${t}-${c}`}
                   className={`sg-cell sg-tier-${t}${ti === 0 ? " sg-row1" : ""}`
                              + (emptyTier ? " sg-emptytier" : "")
                              + (list.length ? "" : " sg-nolist")}
                   style={{ gridColumn: `${c + 1}`, gridRow: `${ti + 1}` }}>
                {!compact && inBlocks && list.length > 0 && (
                  <div className="sg-tlabel">{tierName}</div>
                )}
                {emptyTier && (
                  <div className="sg-tnote">
                    no {tierName} node{t === "site" ? "s" : ""} declared
                  </div>
                )}
                {list.map((n) => (
                  <NodeCard key={n.key} node={n} model={model} findings={findings}
                            collections={collections} selected={selected}
                            compact={compact} onSelect={onSelect} />
                ))}
              </div>,
            );
          }
          return cells;
        })}
      </div>
      <svg className="sg-edges" width={size.w} height={size.h} aria-hidden="true">
        <defs>
          {["ok", "dangling", "expected"].map((k) => (
            <marker key={k} id={`sg-ar-${k}`} viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" className={`sg-ah-${k}`} />
            </marker>
          ))}
        </defs>
        {edges.map((e) => (
          <g key={e.key} className={`sg-edge sg-e-${e.kind}${e.dim ? " sg-dim" : ""}`}>
            <path d={e.d} markerEnd={`url(#sg-ar-${e.kind})`} />
            {!compact && e.label && (
              <>
                <rect className="sg-lbg" x={e.mx - e.label.length * 3.1 - 3}
                      y={e.my - 8} width={e.label.length * 6.2 + 6} height={15} rx={3} />
                <text x={e.mx} y={e.my + 3.5} textAnchor="middle">{e.label}</text>
              </>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

/** §7a's marks, drawn beside the value. The mark is the engine's verdict on
 *  the row; this only picks the glyph. */
function PropRows({ props, onSelect }: {
  props: SchemaGraphProp[]; onSelect: (key: string) => void;
}) {
  return (
    <div className="sg-props">
      {props.map((p, i) => (
        <div key={`${p.k}-${i}`} className={`sg-prow sg-m-${p.mark ?? "none"}`}>
          <span className="sg-k"><code>{p.k}</code></span>
          <span className="sg-v">
            {p.link
              ? <a onClick={(e) => { e.preventDefault(); onSelect(p.link as string); }}
                   href={`#${p.link}`}>{p.v}</a>
              : p.v}
          </span>
          {p.note && <span className="sg-n">{p.note}</span>}
        </div>
      ))}
    </div>
  );
}

type Drill =
  | { kind: "page" }
  | { kind: "node"; node: SchemaGraphNode }
  | { kind: "collection"; col: SchemaGraphCollection; node: SchemaGraphNode | null }
  | { kind: "block"; i: number };

/** §11. `page` is the default state and the one a reader lands on: on the
 *  page, not on the page, and the checklist. Selecting anything replaces
 *  the three columns with that thing's. */
function DrillPanel({ model, drill, findings, collections, onSelect, onFix }: {
  model: SchemaGraphModel; drill: Drill;
  findings: Map<number, SchemaGraphFinding>;
  collections: Map<string, SchemaGraphCollection>;
  onSelect: (key: string | null) => void;
  onFix: (n: number) => void;
}) {
  const byKey = useMemo(() => {
    const m = new Map<string, SchemaGraphNode>();
    for (const n of [...model.nodes, ...model.ghosts]) m.set(n.key, n);
    return m;
  }, [model]);

  const findingRow = (n: number) => {
    const f = findings.get(n);
    if (!f) return null;
    return (
      <button key={n} type="button" className="sg-crow"
              onClick={() => {
                // The item's own amendment to the designer's version: a
                // checklist row selects the node *and* scrolls to its fix
                // card. The designer's only scrolls, which leaves the
                // picture showing whatever was selected before.
                if (f.anchor_keys.length) onSelect(f.anchor_keys[0]);
                onFix(f.n);
              }}>
        <i className={`sg-bd sg-bd-${f.sev_class}`}>{f.n}</i>
        <span className="sg-cname">{f.name}</span>
        <span className={`sg-sev sg-sev-${f.sev_class}`}>{f.sev}</span>
        <span className={`sg-prov sg-prov-${f.src}`}>{f.src}</span>
      </button>
    );
  };

  const crumbs: { label: string; key: string | null }[] = [{ label: "page", key: null }];
  if (drill.kind === "node") crumbs.push({ label: drill.node.type, key: drill.node.key });
  if (drill.kind === "block") crumbs.push({ label: `block ${drill.i}`, key: `block:${drill.i}` });
  if (drill.kind === "collection") {
    if (drill.node) crumbs.push({ label: drill.node.type, key: drill.node.key });
    crumbs.push({ label: drill.col.prop, key: drill.col.key });
  }

  let title = "What is on this page";
  let sub: string = `${model.blocks.length} block${model.blocks.length > 1 ? "s" : ""}`
    + ` · ${model.nodes.length} node${model.nodes.length > 1 ? "s" : ""}`;
  if (drill.kind === "node") {
    title = drill.node.type;
    sub = [drill.node.sid ?? "no @id",
           drill.node.block ? `block ${drill.node.block}` : null,
           drill.node.island ? "island" : null].filter(Boolean).join(" · ");
  } else if (drill.kind === "collection") {
    title = `${drill.col.prop} · ${drill.col.count}`;
    sub = `${drill.col.count} × ${drill.col.item_type}`
      + (drill.col.container ? ` · ${drill.col.container}` : "")
      + ` · ${drill.col.problems ? `${drill.col.problems} with a problem` : "clean"}`;
  } else if (drill.kind === "block") {
    const b = model.blocks.find((x) => x.i === drill.i);
    title = `<script> ${drill.i}`;
    sub = b ? `${b.source} · ${b.nodes.length} top-level node${b.nodes.length > 1 ? "s" : ""}` : "";
  }

  const pinned: number[] =
    drill.kind === "node" ? drill.node.findings
    : drill.kind === "collection" ? drill.col.findings
    : drill.kind === "block" ? (model.blocks.find((x) => x.i === drill.i)?.findings ?? [])
    : model.findings.map((f) => f.n);

  return (
    <div className="sg-drill">
      <div className="sg-dhead">
        <nav className="sg-crumbs">
          {crumbs.map((c, i) => (
            <span key={`${c.label}-${i}`}>
              {i > 0 && <span className="sg-sep"> › </span>}
              <button type="button" className="sg-crumb"
                      onClick={() => onSelect(c.key)}>{c.label}</button>
            </span>
          ))}
        </nav>
        <h5 className="sg-dtitle">{title}</h5>
        <p className="sg-dsub">{sub}</p>
      </div>
      <div className="sg-dcols">
        {drill.kind === "page" && (
          <>
            <div className="sg-dcol">
              <h6>on the page</h6>
              {model.blocks.map((b) => (
                <div key={b.key} className="sg-dblock">
                  <button type="button" className="sg-dblabel"
                          onClick={() => onSelect(b.key)}>
                    <code>&lt;script&gt; {b.i}</code> <span className="muted">{b.source}</span>
                  </button>
                  {model.nodes.filter((n) => n.block === b.i).map((n) => (
                    <button key={n.key} type="button"
                            className={`sg-drow sg-st-${n.state}`}
                            onClick={() => onSelect(n.key)}>
                      <span className="sg-nt">{n.type}</span>
                      <code className="sg-sid">{n.sid ?? "no @id"}</code>
                      {n.island && <span className="sg-tag sg-tag-amber">island</span>}
                      <Badges ns={n.findings} findings={findings} />
                    </button>
                  ))}
                </div>
              ))}
            </div>
            <div className="sg-dcol">
              <h6>not on the page</h6>
              {model.ghosts.length === 0 && (
                <p className="muted">Nothing is referenced that the page does not define,
                  and nothing the page type expects is absent.</p>
              )}
              {model.ghosts.map((g) => (
                <button key={g.key} type="button"
                        className={`sg-drow sg-ghost sg-k-${g.kind}`}
                        onClick={() => onSelect(g.key)}>
                  <span className="sg-nt">
                    {g.kind === "ghost-dangling" ? (g.sid ?? g.type)
                      : g.type + (g.count ? ` ×${g.count}` : "")}
                  </span>
                  <span className="sg-nsub">{g.flags[0] ?? ""}</span>
                </button>
              ))}
            </div>
            <div className="sg-dcol sg-checklist">
              <h6>checklist</h6>
              {model.findings.length === 0 && (
                <p className="muted">Nothing open on this page's markup.</p>
              )}
              {model.findings.map((f) => findingRow(f.n))}
            </div>
          </>
        )}
        {drill.kind === "node" && (
          <>
            <div className="sg-dcol">
              <h6>properties, as stored</h6>
              <PropRows props={drill.node.props} onSelect={onSelect} />
              <RawToggle raw={drill.node.raw} />
            </div>
            <div className="sg-dcol">
              <h6>lists</h6>
              {drill.node.collections.length === 0 && (
                <p className="muted">No list on this node.</p>
              )}
              <div className="sg-chips">
                {drill.node.collections.map((k) => {
                  const c = collections.get(k);
                  if (!c) return null;
                  return (
                    <div key={c.key} className={`sg-chip sg-st-${c.state}`}
                         role="button" tabIndex={0}
                         onClick={() => onSelect(c.key)}
                         onKeyDown={(e) => {
                           if (e.key === "Enter" || e.key === " ") {
                             e.preventDefault(); onSelect(c.key);
                           }
                         }}>
                      <span className="sg-cp">{c.prop}</span>
                      <span className="sg-cc">{c.count}</span>
                      <span className="sg-cv">{c.caption}</span>
                    </div>
                  );
                })}
              </div>
              <Refs node={drill.node} byKey={byKey} onSelect={onSelect} />
            </div>
            <div className="sg-dcol sg-checklist">
              <h6>fixes pinned here</h6>
              {pinned.length === 0 && <p className="muted">Nothing pinned to this node.</p>}
              {pinned.map((n) => findingRow(n))}
            </div>
          </>
        )}
        {drill.kind === "collection" && (
          <>
            <div className="sg-dcol sg-items">
              <h6>items</h6>
              {/* §7b: one row per item with its own marks. This is what the
                  designer's third layout tried to do in place, and the
                  reason that layout was not built. */}
              {drill.col.items.map((it) => (
                <div key={it.i} className={`sg-irow${it.marks.length ? " sg-imark" : ""}`}>
                  <span className="sg-ilabel">{it.label}</span>
                  {it.detail && <span className="sg-idetail">{it.detail}</span>}
                  {it.marks.map((m, j) => (
                    <span key={j} className={`sg-mark sg-m-${m.mark ?? "miss"}`}>{m.note}</span>
                  ))}
                </div>
              ))}
            </div>
            <div className="sg-dcol">
              <h6>the list itself</h6>
              <p className="muted">{sub}</p>
              {drill.node && (
                <p><SecondaryButton
                           onClick={() => onSelect(drill.node!.key)}>
                  up to {drill.node.type}
                </SecondaryButton></p>
              )}
            </div>
            <div className="sg-dcol sg-checklist">
              <h6>fixes pinned here</h6>
              {pinned.length === 0 && <p className="muted">Nothing pinned to this list.</p>}
              {pinned.map((n) => findingRow(n))}
            </div>
          </>
        )}
        {drill.kind === "block" && (
          <>
            <div className="sg-dcol">
              <h6>nodes in this block</h6>
              {model.nodes.filter((n) => n.block === drill.i).map((n) => (
                <button key={n.key} type="button" className={`sg-drow sg-st-${n.state}`}
                        onClick={() => onSelect(n.key)}>
                  <span className="sg-nt">{n.type}</span>
                  <code className="sg-sid">{n.sid ?? "no @id"}</code>
                </button>
              ))}
            </div>
            <div className="sg-dcol">
              <h6>raw JSON</h6>
              <RawToggle raw={model.nodes.filter((n) => n.block === drill.i)
                .map((n) => n.raw)} />
            </div>
            <div className="sg-dcol sg-checklist">
              <h6>fixes pinned here</h6>
              {pinned.length === 0 && <p className="muted">Nothing pinned to this block.</p>}
              {pinned.map((n) => findingRow(n))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** The block cards AT drew are still reachable, as the item asks: the raw
 *  JSON lives inside the drill's properties column rather than as a second
 *  set of cards beside the picture. */
function RawToggle({ raw }: { raw: unknown }) {
  const [open, setOpen] = useState(false);
  if (raw === null || raw === undefined) return null;
  return (
    <div className="sg-raw">
      <SecondaryButton onClick={() => setOpen(!open)}>
        {open ? "hide raw JSON" : "raw JSON"}
      </SecondaryButton>
      {open && <pre className="sg-rawjson">{JSON.stringify(raw, null, 2)}</pre>}
    </div>
  );
}

function Refs({ node, byKey, onSelect }: {
  node: SchemaGraphNode; byKey: Map<string, SchemaGraphNode>;
  onSelect: (key: string) => void;
}) {
  if (!node.refs_in.length && !node.refs_out.length) return null;
  return (
    <>
      <h6>references</h6>
      <div className="sg-props">
        {node.refs_in.map((r, i) => (
          <div key={`in-${i}`} className="sg-prow sg-m-ok">
            <span className="sg-k"><code>{"← "}{r.prop}</code></span>
            <span className="sg-v">
              <a href={`#${r.from}`}
                 onClick={(e) => { e.preventDefault(); onSelect(r.from); }}>
                {byKey.get(r.from)?.sid ?? byKey.get(r.from)?.type ?? r.from}
              </a>
            </span>
            <span className="sg-n">points here</span>
          </div>
        ))}
        {node.refs_out.map((r, i) => (
          <div key={`out-${i}`} className={`sg-prow sg-m-${r.resolved ? "ok" : "bad"}`}>
            <span className="sg-k"><code>{r.prop}{" →"}</code></span>
            <span className="sg-v">
              {r.target
                ? <a href={`#${r.target}`}
                     onClick={(e) => { e.preventDefault(); onSelect(r.target as string); }}>
                    {byKey.get(r.target)?.sid ?? byKey.get(r.target)?.type ?? r.target}
                  </a>
                : r.to}
            </span>
            <span className="sg-n">
              {r.resolved ? "✓ resolves" : "✕ not defined on this page"}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

/** The whole "what the page has now" block for Structured data.
 *
 *  `onFix` scrolls to a fix card; `anchorFor` is how the fixes block tells
 *  this component which node to light up as it scrolls (the item's addition
 *  from layout 2).
 */
export function SchemaGraphView({ part, glow, onFix }: {
  part: Category; glow: string | null; onFix: (n: number) => void;
}) {
  const model = part.graph ?? null;
  const [selected, setSelected] = useState<string | null>(null);
  const [narrow, setNarrow] = useState(
    typeof window !== "undefined" && window.innerWidth <= NARROW);

  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth <= NARROW);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // §11: Esc returns to the page level, which is the same thing clicking
  // empty canvas does.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSelected(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // The selection lives in the hash so the Record can link to a node.
  useEffect(() => {
    const q = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const node = q.get("node");
    if (node) setSelected(node);
    // Read once on mount: after that the hash follows the selection rather
    // than driving it, or a click and a hash write would fight each other.
  }, []);

  const setSel = useCallback((key: string | null) => {
    setSelected(key);
    const q = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    if (key) q.set("node", key); else q.delete("node");
    const s = q.toString();
    window.history.replaceState(null, "", s ? `#${s}` : window.location.pathname);
  }, []);

  const findings = useMemo(() => {
    const m = new Map<number, SchemaGraphFinding>();
    for (const f of model?.findings ?? []) m.set(f.n, f);
    return m;
  }, [model]);

  const collections = useMemo(() => {
    const m = new Map<string, SchemaGraphCollection>();
    for (const c of model?.collections ?? []) m.set(c.key, c);
    return m;
  }, [model]);

  const drill: Drill = useMemo(() => {
    if (!model || !selected) return { kind: "page" };
    const col = collections.get(selected);
    if (col) {
      return { kind: "collection", col,
               node: model.nodes.find((n) => n.key === col.node) ?? null };
    }
    const node = [...model.nodes, ...model.ghosts].find((n) => n.key === selected);
    if (node) return { kind: "node", node };
    const block = model.blocks.find((b) => b.key === selected);
    if (block) return { kind: "block", i: block.i };
    return { kind: "page" };
  }, [model, selected, collections]);

  if (!model) return null;

  const eligibility = model.eligibility ?? [];
  // Item 242: the verdict reads this page's markup alone, and the sweep's
  // id checks compare it with the other pages'. Where one of them is raised
  // on this page, "CONSOLIDATED" beside "@id #organization is declared by 2
  // entities" is two answers, and the screen says so rather than settling it.
  const disputed = (model.findings ?? []).some((f) => f.checks.some(
    (c) => /(^|\/)schema-(duplicate-id|orphan-instance)$/.test(c)));

  return (
    <div className="sg-root">
      {/* The two verdicts above the picture (§8's legend line sits under
          it): neither is a finding about a page, and putting them among the
          cards would make them read as one. */}
      <p className="sg-verdict">
        <b>Entity: {model.verdict.entity}</b>
        {" "}<span className="muted">(this page&rsquo;s markup)</span>
        {model.verdict.why ? ` — ${model.verdict.why}` : ""}
        {disputed && (
          <span className="sg-disputed"> · automatic checks disagree on this page</span>
        )}
      </p>
      {eligibility.length > 0 && (
        <ul className="sg-eligibility">
          {eligibility.map((e, i) => (
            <li key={i}>
              <code>{e.target ?? e.rich_result}</code>
              <span className={`sg-elig sg-elig-${e.verdict.replace(/\s+/g, "-")}`}>
                {e.verdict}
              </span>
              {e.reason ? ` — ${e.reason}` : ""}
            </li>
          ))}
        </ul>
      )}
      <div className={`sg-canvas${glow ? " sg-hasglow" : ""}`}
           data-glow={glow ?? ""}>
        <Level0 model={model} findings={findings} collections={collections}
                selected={glow ?? selected} onSelect={setSel} compact={narrow} />
      </div>
      <p className="sg-legend">
        <span className="sg-lg sg-lg-ok">resolved reference</span>
        <span className="sg-lg sg-lg-dangling">referenced, not defined</span>
        <span className="sg-lg sg-lg-expected">expected, absent</span>
        <span className="sg-lg sg-lg-island">island</span>
      </p>
      <DrillPanel model={model} drill={drill} findings={findings}
                  collections={collections} onSelect={setSel} onFix={onFix} />
    </div>
  );
}
