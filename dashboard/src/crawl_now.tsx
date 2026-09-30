/** The Crawl part's site-level "now" (item 137, brief v18 step AZ).
 *
 *  Unlike the on-page parts, this block is the SITE's state, not one page's:
 *  a four-count strip, the venn those counts decompose into, and the UA matrix
 *  as the one explanatory table. The counts and the venn come from the crawl
 *  the audit already stored; the matrix is new crawler behaviour whose rows
 *  only a live run produces, so a stored run that captured none says so rather
 *  than drawing an empty table (`crawl_now_payload` passes `ua_matrix` through
 *  as null). The UA-string caveat is stated once, beneath the matrix — a 403
 *  to a UA string is evidence of server-side filtering, not proof of what the
 *  named crawler actually sees. */
/** One agent's row in the UA matrix: its robots verdict and what the server
 *  returned to that UA string on the home page and the probe pages. */
export type UaRow = {
  agent: string;
  /** search · dataset · training · index · answer-time (item 145 BG). Null
   *  for an agent the list does not name. Optional for a pre-0.28 server. */
  class?: string | null;
  /** False for a robots token (Google-Extended, Applebot-Extended): read in
   *  robots.txt, never sent as a user-agent, so its cells are "not sent". */
  sent?: boolean;
  robots: "allow" | "disallow";
  /** Per-probed-URL HTTP status, in the order the crawl probed them; a null
   *  is a URL not fetched (blocked at the rule, or not applicable). */
  fetched: { url: string; status: number | null }[];
  note?: string | null;
};

export type CrawlNow = {
  run_id: string;
  published: number;
  /** The header's site size for the same run (item 229): declared plus every
   *  URL the crawl fetched or found linked. Null where the size is unknown. */
  known?: number | null;
  in_sitemap: number;
  reached: number;
  render_only: number;
  sitemap_files: number;
  venn: {
    reached_not_in_sitemap: number;
    in_sitemap_and_reached: number;
    published_not_reached: number;
  };
  /** Null on a run with no matrix pass — the block states the absence. */
  ua_matrix: UaRow[] | null;
  /** The parity probe (item 151). Null on a run that did not probe, which
   *  reads as not assessed, never as parity holding. Optional so a server
   *  from before 0.27.0 still type-checks. */
  mobile_parity?: MobileParity | null;
};

/** One compared pair on one page: the verdict and what differed. */
type ParityPair = {
  verdict: "same" | "named" | "size" | "not_assessed";
  differs: { field: string; base: unknown; other: unknown }[];
  compared_with?: string;
};

export type MobileParity = {
  statement: string;
  mode: string;
  sample_rule: string;
  probed: number;
  fetches: number;
  truncated_by: string | null;
  device: string;
  bot: string;
  javascript_executed: boolean;
  covers: string;
  agents: string[];
  pages: {
    url: string;
    path: string;
    agents: Record<string, { status: number | null; bytes: number | null }>;
    device: ParityPair;
    bot: ParityPair;
  }[];
  raised: Record<string, { severity: string; summary: string }>;
};

/** A pair verdict as a badge: `same` passes, a named-field difference fails,
 *  a size difference is held (a note until a reader diffs it), and a pair
 *  that fetched nothing is not judged. The declared `str-badge` classes. */
function parityKind(p: ParityPair): "pass" | "fail" | "held" {
  if (p.verdict === "same") return "pass";
  return p.verdict === "named" ? "fail" : "held";
}

function parityWords(p: ParityPair): string {
  if (p.verdict === "same") return "same";
  if (p.verdict === "not_assessed") return "not assessed";
  return p.differs.map((d) => d.field.replace(/_/g, " ")).join(", ");
}

/** "What each device and Googlebot is served" — the probe's sentence, then a
 *  row per probed page. States the absence and the JavaScript limit in words,
 *  because both are the difference between "tested clean" and "not tested". */
function ParitySection({ parity }: { parity: MobileParity | null | undefined }) {
  if (!parity) {
    return (
      <p className="cn-caveat cn-na">
        Not assessed: this run did not fetch pages as a phone and as
        Googlebot-smartphone. A re-run on engine 0.27.0 or later probes it.
      </p>
    );
  }
  const raised = Object.entries(parity.raised);
  return (
    <>
      <p className="cn-parity-statement">
        <b>{parity.statement}</b>
        <span className="cn-mute">
          {" "}· {parity.sample_rule} · {parity.fetches} fetches
          {parity.truncated_by ? ` · stopped by ${parity.truncated_by}` : ""}
        </span>
      </p>
      {parity.pages.length > 0 && (
        <table className="cn-matrix">
          <thead>
            <tr>
              <th>Page</th>
              <th>Bytes: desktop · iPhone · Googlebot</th>
              <th>iPhone vs desktop</th>
              <th>Googlebot vs browser</th>
            </tr>
          </thead>
          <tbody>
            {parity.pages.map((r) => (
              <tr key={r.url}>
                <td>{r.path}</td>
                <td className="cn-note">
                  {parity.agents
                    .map((a) => r.agents[a]?.bytes?.toLocaleString() ?? "—")
                    .join(" · ")}
                </td>
                <td>
                  <span className={`str-badge str-${parityKind(r.device)}`}>
                    {parityWords(r.device)}
                  </span>
                </td>
                <td>
                  <span className={`str-badge str-${parityKind(r.bot)}`}>
                    {parityWords(r.bot)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {raised.length > 0 && (
        <ul className="cn-parity-raised">
          {raised.map(([check, f]) => (
            <li key={check}>
              TEC/{check} · {f.severity}
            </li>
          ))}
        </ul>
      )}
      <p className="cn-caveat">
        No JavaScript was executed: these are served-HTML fetches, so a title
        or copy rewritten client-side is not seen here. Googlebot is compared
        with the iPhone, the same device class, so a difference is the bot and
        not the phone.
      </p>
    </>
  );
}

/** The pass/fail/held badge kind for a fetched-status cell: 2xx passes, a
 *  null was never fetched (held — not judged), anything else is the server
 *  saying no. Reuses the `str-badge` classes the title/description card
 *  already declares, so no new colour enters the palette. */
function statusKind(status: number | null): "pass" | "fail" | "held" {
  if (status === null) return "held";
  return status >= 200 && status < 300 ? "pass" : "fail";
}

export function CrawlNowBlock({ now }: { now: CrawlNow }) {
  const v = now.venn;
  return (
    <div className="crawl-now">
      <h3>What the site has now</h3>
      <div className="cn-kv">
        <div>
          <span className="cn-l">Published</span>
          <b>{now.published}</b>
          <span className="cn-s">
            reached or in a sitemap · {now.sitemap_files} sitemap file
            {now.sitemap_files === 1 ? "" : "s"}
            {/* Item 229: the header says "N known" of the same site. */}
            {now.known != null && now.known > now.published && (
              <> · the {now.known} known also counts {now.known - now.published} URL
                {now.known - now.published === 1 ? "" : "s"} found linked or
                fetched that {now.known - now.published === 1 ? "was" : "were"} neither
                reached nor in a sitemap</>
            )}
          </span>
        </div>
        <div>
          <span className="cn-l">In sitemap</span>
          <b>{now.in_sitemap}</b>
          <span className="cn-s">URLs the sitemaps declare, on this host</span>
        </div>
        <div>
          <span className="cn-l">Reached by crawl</span>
          <b>{now.reached}</b>
          <span className="cn-s">
            {v.published_not_reached} declared but not reached
          </span>
        </div>
        <div>
          <span className="cn-l">Render-only</span>
          <b>{now.render_only}</b>
          <span className="cn-s">content present only after JavaScript</span>
        </div>
      </div>

      {/* The three regions the four counts decompose into. A page is in exactly
          one, by normalised path, so the three sum to `published`. */}
      <div className="cn-venn">
        <div>
          <b>{v.reached_not_in_sitemap}</b>
          <span>reached, <span className="cn-warn">not in a sitemap</span></span>
          <span className="cn-mute">crawled pages the sitemaps omit</span>
        </div>
        <div>
          <b>{v.in_sitemap_and_reached}</b>
          <span>in a sitemap and reached</span>
          <span className="cn-mute">declared and fetched</span>
        </div>
        <div>
          <b>{v.published_not_reached}</b>
          <span>declared, <span className="cn-warn">not reached</span></span>
          <span className="cn-mute">in a sitemap, no crawl path</span>
        </div>
      </div>

      <h4>Who may fetch — robots.txt as read, and what each agent got</h4>
      {now.ua_matrix && now.ua_matrix.length > 0 ? (
        <>
          <table className="cn-matrix">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Class</th>
                <th>robots.txt</th>
                {now.ua_matrix[0].fetched.map((f) => (
                  <th key={f.url}>Fetched {pathLabel(f.url)}</th>
                ))}
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {now.ua_matrix.map((r) => (
                <tr key={r.agent}>
                  <td>{r.agent}</td>
                  <td>{r.class || "—"}</td>
                  <td>
                    <span className={`str-badge str-${r.robots === "allow" ? "pass" : "fail"}`}>
                      {r.robots === "allow" ? "allow" : "disallow /"}
                    </span>
                  </td>
                  {r.fetched.map((f) => (
                    <td key={f.url}>
                      <span className={`str-badge str-${r.sent === false ? "held" : statusKind(f.status)}`}>
                        {r.sent === false ? "not sent" : f.status === null ? "not fetched" : f.status}
                      </span>
                    </td>
                  ))}
                  <td className="cn-note">{r.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="cn-caveat">
            This measures the UA string&rsquo;s treatment, not the real
            crawler&rsquo;s visit: a 403 to a UA test is evidence of server-side
            filtering, not proof of what the named crawler sees. Logs would show
            that; none are ingested.
          </p>
        </>
      ) : (
        <p className="cn-caveat cn-na">
          No crawler access test in this audit. The per-crawler test is a live pass
          (brief v18 step AZ, task 4); a re-run captures it.
        </p>
      )}

      <h4>What each device and Googlebot is served</h4>
      <ParitySection parity={now.mobile_parity} />
    </div>
  );
}

/** The path of a probed URL, for a column header — the home page as "/". */
function pathLabel(url: string): string {
  try {
    const p = new URL(url, "https://x.invalid").pathname;
    return p || "/";
  } catch {
    return url;
  }
}
