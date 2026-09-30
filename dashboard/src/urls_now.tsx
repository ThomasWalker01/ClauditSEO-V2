/** The URLs & parameters part's site-level "now" (item 141, brief v19 step BB).
 *
 *  Like Crawl and Indexability, this is the site's URL space rather than one
 *  page's: a four-count strip (URLs · patterns · parameters seen ·
 *  unclassified), the convention derived from the reached 200s, and the two
 *  tables the brief names — the pattern table (template · count · depth) and
 *  the parameter inventory (key · seen · class · canonical present). The fifth
 *  inventory column says where a parameter row is handed on, because every
 *  parameter row carries `handoff: "indexability"` and a reader should not
 *  have to know that from the contract (mockup note 2). Everything is derived
 *  by the payload from the crawl the audit stored; nothing new is fetched. */

export type UrlsNow = {
  run_id: string;
  urls: number;
  pattern_count: number;
  parameters_seen: number;
  unclassified: number;
  patterns: { pattern: string; count: number; depth: number; note: string }[];
  /** Each reached URL's template (brief v25 step BP). */
  pattern_of?: Record<string, string>;
  parameters: {
    key: string;
    seen: number;
    class: string;
    canonical_present: number;
    variants: number;
  }[];
  convention: {
    scheme: string;
    host: string;
    trailing_slash: boolean;
    case: string;
    conform: number;
    total: number;
  };
  thresholds: {
    url_max_chars: number;
    slug_max_words: number;
    max_depth: number;
    rename_inlink_cap: number;
  };
};

/** A parameter is owned when it has a class in the record, or every variant
 *  the crawl saw carries a canonical; unclassified with no canonical is the
 *  one the sweep raises and the brief must classify. */
function where(p: UrlsNow["parameters"][number]): string {
  if (p.class && p.class !== "unclassified") return "classified";
  if (p.canonical_present >= p.variants && p.variants > 0) return "canonical set";
  return "→ Indexability";
}

export function UrlsNowBlock({ now, picked = null, onTemplate }: {
  now: UrlsNow;
  /** The template narrow in hand, and the way to set it (brief v25 step BP):
   *  a row's template is a button that narrows the fixes to its pages. */
  picked?: string | null;
  onTemplate?: (pattern: string | null) => void;
}) {
  const c = now.convention;
  const t = now.thresholds;
  return (
    <div className="crawl-now">
      <h3>What the site has now</h3>
      <div className="cn-kv">
        <div>
          <span className="cn-l">URLs reached</span>
          <b>{now.urls}</b>
          <span className="cn-s">pages the crawl read a URL for</span>
        </div>
        <div>
          <span className="cn-l">Patterns</span>
          <b>{now.pattern_count}</b>
          <span className="cn-s">path templates the URLs fall into</span>
        </div>
        <div>
          <span className="cn-l">Parameters seen</span>
          <b>{now.parameters_seen}</b>
          <span className="cn-s">distinct query keys across the links</span>
        </div>
        <div>
          <span className="cn-l">Unclassified</span>
          <b>{now.unclassified}</b>
          <span className="cn-s">no class and no canonical — makes duplicates</span>
        </div>
      </div>

      <p className="cn-mute" style={{ marginTop: ".6rem" }}>
        Convention, from the reached 200s: {c.scheme} · {c.host} ·{" "}
        {c.trailing_slash ? "trailing slash" : "no trailing slash"} · {c.case} ·{" "}
        {c.conform} of {c.total} conform. Thresholds: {t.url_max_chars} chars ·{" "}
        {t.slug_max_words} words · depth {t.max_depth} · rename cap{" "}
        {t.rename_inlink_cap}.
      </p>

      <h4>Patterns</h4>
      <table className="cn-matrix">
        <thead>
          <tr><th>Template</th><th>Count</th><th>Depth</th><th>Note</th></tr>
        </thead>
        <tbody>
          {now.patterns.map((r) => (
            <tr key={r.pattern}>
              <td>
                {onTemplate
                  ? <button type="button" className={`linklike un-template${picked === r.pattern ? " on" : ""}`}
                            aria-pressed={picked === r.pattern}
                            onClick={() => onTemplate(picked === r.pattern ? null : r.pattern)}>
                      <code>{r.pattern}</code>
                    </button>
                  : <code>{r.pattern}</code>}
              </td>
              <td>{r.count}</td>
              <td>{r.depth}</td>
              <td className="cn-note">{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>Parameter inventory</h4>
      {now.parameters.length === 0 ? (
        <p className="cn-mute">No query parameters seen in this crawl.</p>
      ) : (
        <table className="cn-matrix">
          <thead>
            <tr>
              <th>Key</th><th>Seen</th><th>Class</th>
              <th>Canonical present</th><th>Where it goes</th>
            </tr>
          </thead>
          <tbody>
            {now.parameters.map((p) => (
              <tr key={p.key}>
                <td><code>{p.key}</code></td>
                <td>{p.seen}</td>
                <td>{p.class}</td>
                <td>{p.canonical_present} of {p.variants}</td>
                <td className="cn-note">{where(p)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
