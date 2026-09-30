/** The Indexability part's site-level "now" (item 137, brief v18 step BA).
 *
 *  Like Crawl, this is the site's state rather than one page's: four headline
 *  counts (reached · indexable · noindex · canonical elsewhere), the canonical
 *  map as the one explanatory table, and the redirect tally. The canonical map
 *  and the counts come from the crawl the audit stored; a redirect's per-hop
 *  status is not stored, so `temporary` and `to_404` read "—" here and are the
 *  brief's job over a live redirect log. The URL convention the site uses is
 *  stated once, derived from the majority of its reached 200s. */

export type IndexabilityNow = {
  run_id: string;
  reached: number;
  indexable: number;
  noindex: number;
  canonical_elsewhere: number;
  canonical_map: {
    self: number;
    /** Absent on a payload from before item 180. */
    param_variant?: number;
    elsewhere_200: number;
    elsewhere_404: number;
    missing: number;
    conflicts_sitemap: number;
  };
  redirects: {
    total: number;
    chains: number;
    temporary: number | null;
    to_404: number | null;
  };
  convention: { scheme: string; host: string; trailing_slash: boolean };
};

/** The canonical-map rows, in the order the brief names them, each with the
 *  one-line meaning an operator reads it by. */
const MAP_ROWS: { key: keyof IndexabilityNow["canonical_map"]; label: string; why: string }[] = [
  { key: "self", label: "Self", why: "canonical points at the page itself" },
  { key: "param_variant", label: "Parameter variant", why: "a parameterised address whose canonical is the address without the parameters" },
  { key: "elsewhere_200", label: "Elsewhere → 200", why: "canonical points at another live page" },
  { key: "elsewhere_404", label: "Elsewhere → 404", why: "canonical points at a page that errors" },
  { key: "missing", label: "Missing", why: "no canonical on the page" },
  { key: "conflicts_sitemap", label: "Conflicts with sitemap", why: "in the sitemap, canonical sends indexation elsewhere" },
];

function count(n: number | null): string {
  return n === null ? "—" : String(n);
}

export function IndexabilityNowBlock({ now }: { now: IndexabilityNow }) {
  const c = now.convention;
  return (
    <div className="crawl-now">
      <h3>What the site has now</h3>
      <div className="cn-kv">
        <div>
          <span className="cn-l">Reached</span>
          <b>{now.reached}</b>
          <span className="cn-s">pages the crawl read the signals on</span>
        </div>
        <div>
          <span className="cn-l">Indexable</span>
          <b>{now.indexable}</b>
          <span className="cn-s">200 · self-canonical · no noindex</span>
        </div>
        <div>
          <span className="cn-l">Noindex</span>
          <b>{now.noindex}</b>
          <span className="cn-s">meta robots or X-Robots-Tag says noindex</span>
        </div>
        <div>
          <span className="cn-l">Canonical elsewhere</span>
          <b>{now.canonical_elsewhere}</b>
          <span className="cn-s">canonical points at another URL</span>
        </div>
      </div>

      <h4>Canonical map</h4>
      <table className="cn-matrix">
        <thead>
          <tr><th>Where the canonical points</th><th>Pages</th><th>Meaning</th></tr>
        </thead>
        <tbody>
          {MAP_ROWS.map((r) => (
            <tr key={r.key}>
              <td>{r.label}</td>
              <td>{now.canonical_map[r.key]}</td>
              <td className="cn-note">{r.why}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="cn-mute" style={{ marginTop: ".6rem" }}>
        Redirects: {now.redirects.total} · {now.redirects.chains} of two or more
        hops · {count(now.redirects.temporary)} temporary ·{" "}
        {count(now.redirects.to_404)} to a 404.
      </p>
      <p className="cn-caveat">
        A redirect&rsquo;s per-hop status is not in the stored crawl, so
        &ldquo;temporary&rdquo; and &ldquo;to a 404&rdquo; read &ldquo;&mdash;&rdquo;
        here — they are judged over a live redirect log. URL convention:{" "}
        {c.scheme}://{c.host}{c.trailing_slash ? "/…/  (trailing slash)" : "/…  (no trailing slash)"},
        from the majority of reached 200s.
      </p>
    </div>
  );
}
