import { useCallback, useEffect, useState } from "react";

const TOKEN_KEY = "clauditseo:token";
//: The pre-rename key was read once and carried over for one release so the
//: rename did not read as "the new version broke my login". That carry-over
//: is done: anyone who has opened the app since has been migrated, and an
//: operator who has not will be asked to sign in once.

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** One authorized request, up to the point where a body is read.
 *
 *  Split out of `call` so that a caller wanting bytes rather than JSON gets
 *  the SAME token and the SAME error handling — UX-30 is what happens when a
 *  second way of fetching exists that does not. There, two elements loaded an
 *  API path by themselves; the answer is not a second fetch path but this one,
 *  read as a blob.
 */
async function request(path: string, init?: RequestInit): Promise<Response> {
  // Merged through Headers rather than object spread. Header names are
  // case-insensitive, so a caller's "content-type" did not replace the
  // "Content-Type" below — spreading kept both keys and fetch joined them
  // into "application/json, application/json", which is not a media type
  // any parser accepts. Every PUT in the app 422'd on that, silently.
  // `set` is the whole point: an override has to override.
  const headers = new Headers({ "Content-Type": "application/json" });
  for (const [name, value] of new Headers(init?.headers ?? {})) {
    headers.set(name, value);
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* keep status */
    }
    throw new ApiError(resp.status, detail);
  }
  return resp;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json() as Promise<T>;
}

/** Why a call failed, at the grain the operator needs — three answers, not
 *  two. The screen used to ask only "was this a 401", which made every other
 *  failure indistinguishable from success and painted an outage as an empty
 *  dashboard (UX-06).
 *
 *  `unreachable` deliberately covers both halves of "the server is not
 *  answering", because they arrive as different objects and neither is a fact
 *  about the operator's token:
 *
 *    - `fetch` itself rejects — nothing listening, connection dropped, DNS.
 *      The error is a `TypeError` with no `status` at all, which is why a
 *      branch written on status codes could never see it.
 *    - a 5xx from a process that is up and broken.
 *
 *  A body that is not JSON lands here too: `call` throws out of `resp.json()`
 *  with no status, and a server answering an API route with something a
 *  parser rejects is not answering it.
 *
 *  `other` is the 4xx that is neither — a 404 or a 422 that a view can and
 *  should report in its own terms. That is the case the old comment
 *  "non-auth errors surface inside views" was true of, kept rather than
 *  widened. */
export type Failure = "auth" | "unreachable" | "other";

export function classify(err: unknown): Failure {
  if (err instanceof ApiError) {
    if (err.status === 401) return "auth";
    return err.status >= 500 ? "unreachable" : "other";
  }
  return "unreachable";
}

/** The underlying error, for the line under the headline. Shown rather than
 *  swallowed: "Failed to fetch" is not a sentence to put in front of an
 *  operator on its own, but it is exactly what they need to paste to whoever
 *  runs the box. */
export function describe(err: unknown): string {
  if (err instanceof ApiError) return `${err.status} — ${err.message}`;
  if (err instanceof Error) return err.message;
  return String(err);
}

export const api = {
  get: <T>(path: string) => call<T>(path),
  post: <T>(path: string, body: unknown) =>
    call<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    call<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  del: <T>(path: string) => call<T>(path, { method: "DELETE" }),
  /** The bytes at an API path, with the token attached. For anything a
   *  browser element loads — see `objectUrl` below. */
  blob: (path: string) => request(path).then((r) => r.blob()),
};

/**
 * A URL an `<img src>` or a `<link rel="icon" href>` may carry.
 *
 * UX-30, carried at High since report 034. Every `/api/` route in this product
 * is declared `operator=op_dep`, and a browser loading a subresource by itself
 * sends no `Authorization` header: it is a plain unauthenticated GET of
 * whatever the attribute says. So the tab icon and the admin panel's logo
 * preview were both a 401, rendering as the built-in mark and as a broken
 * image, with nothing on screen to say why. It cannot be seen on a development
 * install, because `auth` grants full access when no token exists anywhere.
 *
 * The fetch happens HERE, with the token, and the browser is handed bytes it
 * already has. The caller owns the returned URL and must `URL.revokeObjectURL`
 * it when it stops using it — an object URL is a document-lifetime reference
 * to a blob, so one created per render and never released is a leak that grows
 * with the size of the image.
 */
export function objectUrl(path: string): Promise<string> {
  return api.blob(path).then((b) => URL.createObjectURL(b));
}

/**
 * `objectUrl` for a React element: fetch on mount and on every change of
 * `path`, and release the previous URL rather than leaving it behind.
 *
 * `null` while the bytes are in flight and after a failure, so a caller
 * renders no element rather than a broken one — which is the state UX-30 put
 * on screen and the reason a bare `src` is not the fix. A path of `null` means
 * there is nothing to show, and asks for nothing.
 */
export function useObjectUrl(path: string | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!path) { setUrl(null); return; }
    let live = true;
    let mine: string | null = null;
    objectUrl(path)
      .then((u) => {
        if (!live) { URL.revokeObjectURL(u); return; }
        mine = u;
        setUrl(u);
      })
      .catch(() => { if (live) setUrl(null); });
    return () => {
      live = false;
      if (mine) URL.revokeObjectURL(mine);
    };
  }, [path]);
  return url;
}

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export type Finding = {
  id: string;
  dimension: string;
  check_id: string;
  severity: Severity;
  source: "deterministic" | "model-judgement";
  model_id: string | null;
  confidence: string;
  summary: string;
  affected_urls: string[];
  evidence: Record<string, unknown>;
  recommendation: string;
  fingerprint: string;
  /** The tool that judges this check, or null if nothing does (F-02).
   *  Decided on the server, so a row cannot offer a control the server
   *  would refuse — null here and no control there are one decision. */
  specialist?: string | null;
};

export type Run = {
  id: string;
  site_id: string;
  /** What this run was sent to look at. Three today, and the contract is the
   *  set rather than the list: `"audit"` reads the site, `"verify"` re-fetches
   *  the pages behind named findings, `"refresh"` re-measures one page for one
   *  dimension (`FEATURES.md` F-06). This comment said "audit or verify" for
   *  the three rounds `refresh` had existed, on the one field three server
   *  filters turn on.
   *
   *  `string` rather than a union, deliberately, and the reason is the
   *  opposite of `RunStatus`'s. A status has a CHECK constraint and every
   *  classifier over it is exhaustive, so a sixth member should be a compile
   *  event. A kind has no constraint and the server may add one; asking
   *  `isSiteReading` gives an unfamiliar kind the careful answer instead of a
   *  build failure. */
  kind: string;
  dimensions: string[];
  tier: string;
  status: RunStatus;
  composite_score: number | null;
  engine_version?: string | null;
  /** The server's classification (brief v6 step V2): the effective scope
   *  - page | nav | site | full - and whether the run reads the site. */
  effective_scope?: string | null; site_reading?: boolean;
  /** page | nav | site | full, or null on a run from before the column. */
  scan_scope?: string | null;
  /** The paths the crawl fetched, as the JSON text the server stores - a
   *  reader parses it once. Absent on a run that stored no evidence. */
  crawled_paths?: string | null;
  /** What the crawl actually reached. Assembled by `get_run` since the
   *  blocked status landed, and read by nothing until the run screen learned
   *  to say why a blocked run has no score. */
  scope?: {
    pages_fetched: number; discovered: number | null;
    robots_blocked: number; truncated_by: string | null;
  } | null;
  /** How much of the intended audit the composite rests on, 0-1, read back
   *  from the row the engine stored beside the score — not recomputed here.
   *
   *  `basis` is which of two quantities the value is, and is not decoration:
   *  `coverage` is dimension coverage alone, for a site that declared no page
   *  total, and `coverage+breadth` is that figure scaled by the share of the
   *  declared pages the crawl reached. Five real rows for one site held both
   *  under one key at 0.2879 and 0.9362 in the same tier, which is why the
   *  frame travels with the value. `null` on rows written before migration
   *  0022 added the frame column.
   *
   *  Absent for a run that stored no figure at all — a verification, a
   *  refresh, a robots-blocked audit. That is "not measured", never "measured
   *  as none", and the screen prints nothing rather than a zero. */
  measured_share?: {
    value: number; basis: string | null;
    pages_fetched: number | null; discovered: number | null;
  } | null;
  subscores: Record<string, {
    score: number; weight: number; applicable: boolean;
    /** Share of the dimension actually measured, 0-1. Written by every run. */
    coverage: number;
    unmeasured?: string[];
  }> | null;
  started_at: string | null;
  finished_at: string | null;
  analyst_enabled: boolean;
  error?: string | null;
  progress?: { label: string; at: string }[];
  findings?: Finding[];
  deterministic_findings?: Finding[];
  analyst_findings?: Finding[];
  costs?: { provider: string; operation: string; units: string; quantity: number;
            actual_cost?: number | null }[];
};

/** The completed runs that looked at the whole site, newest first.
 *
 *  A verification is a completed run too, but it re-crawls only the pages
 *  behind some ticked findings and stores no expert reports — so it must
 *  never stand in for "the latest audit". It did in four places: the run
 *  selector defaulted to one (making "Ready to read · 0" the default view on
 *  a site holding eight reports), the workbench read one, the history
 *  headline read one, and the fix loop treated one as having judged every
 *  mark on the site. `kind` defaults to "audit" because runs recorded before
 *  the column existed were all audits.
 *
 *  Anything asking "what does this site look like" wants this list. Anything
 *  listing what has happened — the Runs table, the reports page — wants the
 *  unfiltered one, because a verification did happen. */
export function completedAudits<T extends { status: RunStatus; kind: string }>(
    runs?: T[]): T[] {
  return (runs ?? []).filter((r) => hasResults(r.status) && isSiteReading(r.kind));
}

/** Whether this run may be generalised to the site it belongs to — scored
 *  onto a trend, counted as the latest audit, compared against another run.
 *
 *  The mirror of `runs.SITE_READING_KINDS` on the server, and the same
 *  argument as `hasScore`: the rule existed here as the literal
 *  `r.kind === "audit"` inside one filter, so the three render sites that
 *  print a composite had only `hasScore` to gate on. `hasScore` asks whether
 *  a score was PRODUCED; this asks whether it describes the SITE. A
 *  verification of eight pages produces a real 86.2 that is not the site's,
 *  and both screens printed it beside a 224-page audit's 70.52.
 *
 *  An allow-list, so a fourth run kind is narrow on the day it is added
 *  rather than on the day someone notices. `kind` is `string` and not a
 *  union on purpose — the server owns the vocabulary and a new kind must not
 *  need a client release to be handled safely. */
/** A run row, or the bare kind the older callers still hold. */
type RunLike = string | null | undefined
  | { kind?: string | null; site_reading?: boolean; scan_scope?: string | null;
      crawled_paths?: string | null; effective_scope?: string | null };

export function isSiteReading(run: RunLike): boolean {
  // A row carries the server's answer (brief v6 step V2) - `site_reading`,
  // or its kind and effective scope for a row from before the field; a
  // bare kind is the older question, answered the older way.
  return typeof run === "object" && run !== null
    ? (run.site_reading !== undefined ? run.site_reading
       : run.kind === "audit" && !isNarrowScope(scopeOf(run)))
    : run === "audit";
}

/** Every status `audit_runs.status` may hold, as the CHECK constraint in
 *  migration 0001 defines it. A union rather than `string` so that adding a
 *  status is a compile event: the classifiers below are exhaustive, and a
 *  sixth member makes each one fail until it has been told what the new
 *  status means. `status: string` let five screens quietly disagree about
 *  what a run in an unfamiliar state should do. */
export type RunStatus =
  "pending" | "running" | "complete" | "failed" | "cancelled" | "blocked";

/** Reached only if a union member went unhandled, which `tsc` catches first.
 *  The throw is for a status arriving from the API at runtime without passing
 *  through the type — a server ahead of this bundle. */
export function assertNever(value: never, where: string): never {
  throw new Error(`${where}: unhandled run status ${JSON.stringify(value)}`);
}

/** Still working, so a screen should keep polling. */
export function isInFlight(status: RunStatus): boolean {
  switch (status) {
    case "pending":
    case "running":
      return true;
    case "complete":
    case "failed":
    case "cancelled":
    // Terminal: the crawl reached a definite answer and that answer was
    // "you may not look". Nothing further will arrive, so stop polling.
    case "blocked":
      return false;
    default:
      return assertNever(status, "isInFlight");
  }
}

/** Produced findings and a score a screen may read. Deliberately narrower
 *  than "finished": a failed or cancelled run is over and has nothing to
 *  show. */
/** Produced a SCORE a screen may print. Narrower than `hasResults`, and the
 *  distinction the server already draws between `SCORED_STATUSES` and
 *  `AUDITED_STATUSES` — a blocked run is an audit that happened, and its
 *  composite rests on robots.txt alone. The client had only the wider
 *  predicate, so a blocked run's composite (80.0 on the fixture, from a
 *  crawl that fetched nothing) printed as an ordinary score in six places. */
export function hasScore(status: RunStatus): boolean {
  switch (status) {
    case "complete":
      return true;
    case "blocked":
    case "pending":
    case "running":
    case "failed":
    case "cancelled":
      return false;
    default:
      return assertNever(status, "hasScore");
  }
}

export function hasResults(status: RunStatus): boolean {
  switch (status) {
    case "complete":
    // It fetched no page, but robots.txt and the sitemap were measured in
    // their own right and its findings are stored. The server agrees:
    // `current_state` treats a blocked run as the site's latest audit, and a
    // screen that disagreed would roll the fix loop back to an older crawl
    // while saying nothing had changed.
    case "blocked":
      return true;
    case "pending":
    case "running":
    case "failed":
    case "cancelled":
      return false;
    default:
      return assertNever(status, "hasResults");
  }
}

/** Safe to offer deletion. Only a run still executing is withheld — the
 *  existing rule, kept exactly, now stated once instead of per screen. */
export function isDeletable(status: RunStatus): boolean {
  switch (status) {
    case "running":
      return false;
    case "pending":
    case "complete":
    case "failed":
    case "cancelled":
    case "blocked":
      return true;
    default:
      return assertNever(status, "isDeletable");
  }
}

export type FindingState = {
  fingerprint: string;
  /** "candidate" is a model finding seen once — it opens if a second run
   *  confirms it, and is dropped if not. It was missing from this union
   *  while the record's own filter offered it.
   *  "withdrawn" is the finding that was never true — the audit that
   *  raised it could not see the site. */
  state: "candidate" | "open" | "fixed" | "regressed" | "accepted-risk"
       | "withdrawn";
  updated_at: string;
  changed_by_run: string | null;
  dimension: string;
  check_id: string;
  severity: Severity;
  summary: string;
  affected_urls: string[];
  /** Whether a crawl could look again at this finding — the verify route's
   *  own rule (`runs.names_a_page`), decided on the server. Not derivable
   *  from `affected_urls` here: the route keeps only entries starting `http`,
   *  and a finding may name a header or a sitemap entry instead. */
  names_a_page: boolean;
  /** Not a finding: an Info statement of what the audit could not measure.
   *  The server's rule (`runs.is_coverage_note`, brief v5 step S). */
  coverage_note?: boolean;
  /** The fix loop. Stored on every tick and read back, so a mark survives a
   *  reload on whichever screen made it. */
  attempted_at?: string | null;
  attempt_note?: string | null;
  /** "deterministic" | "model-judgement". Only a deterministic finding can be
   *  judged by a crawl, so only it gets a tick. */
  source?: string;
  /** The source as a word (brief v10 step AF): `sweep` or `brief`, a
   *  column and not a prefix on the check id. */
  source_word?: "sweep" | "brief";
  /** A conforming brief's proposed copy, and the status it gave the row. */
  proposed?: string | null;
  brief_status?: string | null;
  brief?: string | null;
  /** An analysis row the automatic checks have since cleared on every page
   *  it names: when (item 239 step 4). */
  superseded_on?: string | null;
  /** A duplicate row's shared string, from either source (brief v11 step
   *  AH): the record's group line counts the groups. */
  group?: string | null;
  raised?: boolean;
  /** What an image answer carries (brief v15): the image the row is
   *  about, the other checks its one replacement closes, and whether the
   *  change is one file's, a template's or a pipeline's. */
  image?: string | null;
  /** Every image the finding covers (item 246): one finding per check per
   *  page names each image failing it there. */
  images?: string[];
  also_resolves?: string[];
  /** The URL template a per-template brief row is about (items 217, 222). */
  template?: string | null;
  /** Brief v20's three row fields (items 147, 148). `suppressed` is the
   *  because-clause naming the check that owns the verdict -- one state with
   *  two producers (sweep precedence and the brief's own field), never two
   *  states on screen. */
  fix_id?: string | null;
  suppressed?: string[];
  confidence?: string | null;
  kind?: string | null;
  /** What a structured-data answer carries (brief v16): the block the row
   *  is about, as the inventory numbers it, and where the change goes in
   *  the operator's own words. */
  block?: string | null;
  where?: string | null;
  /** What a links answer carries (brief v17 step AW): the source pages a
   *  suggestion proposes, each with the anchor drawn from the target's
   *  own words and the heading it belongs after. */
  /** The AI surface brief's row payload (item 145 BH): candidates, passage,
   *  criteria, sections, deltas. */
  payload?: Record<string, unknown>;
  suggestions?: { source: string; anchor: string; after?: string;
                  overlap?: string[] }[];
  /** A Security brief row's rollout (brief v20 step BD). */
  rollout?: Rollout | null;
};

/** How one security change is deployed: per layer, with its risk, a check that
 *  it worked, the way back, and where it falls in the rollout order. */
export type Rollout = {
  domain?: string | null; impact?: string | null;
  config?: { layer?: string; stack?: string; block?: string }[] | null;
  deploy_risk?: string | null; verify?: string | null; rollback?: string | null;
  order?: number | null; staged?: string | null;
};

/** What a source tag says on hover (brief v10 step AF): the sentence the
 *  retired "Two sources, two questions" panel used to carry. */
/** What a `candidate` tag means (brief v12 step AM): the corroboration
 *  rule's output, made visible where the row is shown. */
export const CANDIDATE_NOTE =
  "An analysis raised this and the automatic checks have not: it waits as a candidate until a "
  + "second analysis run confirms it or an automatic check corroborates it. Shown so the "
  + "proposed copy is not lost while it waits.";

export const SOURCES_NOTE = "Raised both by the automatic checks and by an analysis. The checks count every instance it can match, mechanically. The analysis reports only what it judged worth acting on, and can see things a parser cannot. The numbers are not meant to agree.";

/** Why two runs cannot be read as one series, in the order `frameMoved`
 *  gives for trend points: tier, engine, scope, dimensions. Empty means
 *  comparable. Brief v2 step B: the crawl diff between two runs of
 *  different scope reported scope shrink as pages gone, and this is the
 *  predicate the "reads against previous" column already stands on. */
export function runsDiffer(a: Run, b: Run): string[] {
  const out: string[] = [];
  const say = (v: string | null | undefined) => v || "unknown";
  if (a.tier !== b.tier) out.push(`tier ${say(a.tier)} → ${say(b.tier)}`);
  if ((a.engine_version ?? null) !== (b.engine_version ?? null))
    out.push(`engine ${say(a.engine_version)} → ${say(b.engine_version)}`);
  if ((a.scan_scope ?? null) !== (b.scan_scope ?? null))
    out.push(`scope ${say(a.scan_scope)} → ${say(b.scan_scope)}`);
  const da = [...a.dimensions].sort().join(","), db = [...b.dimensions].sort().join(",");
  if (da !== db) {
    const gone = a.dimensions.filter((d) => !b.dimensions.includes(d));
    const added = b.dimensions.filter((d) => !a.dimensions.includes(d));
    out.push([gone.length ? `${gone.join(", ")} dropped` : "",
              added.length ? `${added.join(", ")} added` : ""].filter(Boolean).join(", "));
  }
  return out;
}

/** The paths a run fetched, parsed once; empty when it stored none. */
export function crawledPaths(r: Pick<Run, "crawled_paths">): string[] {
  try {
    const v = r.crawled_paths ? JSON.parse(r.crawled_paths) : [];
    return Array.isArray(v) ? v.map(String) : [];
  } catch { return []; }
}

/** A crawl that fetched at least this many pages read the site - the
 *  server's `runs.SITE_WIDE_MIN_PATHS`, spelled once here. */
export const SITE_WIDE_MIN_PATHS = 50;

/** What a run was: `page | nav | site | full`, or null when nothing is
 *  known. The stored scope wins; where a run predates the column, the
 *  crawl's own page count decides - one page is a page scan, fewer than
 *  fifty a navigation scan - and the tier never does (brief v3 step I,
 *  WF-05b): a T2 run that fetched twenty pages wore "site-wide" for a day.
 *  The server's `runs.scope_of` says the same. */
export function scopeOf(r: Pick<Run, "scan_scope" | "crawled_paths"> & { effective_scope?: string | null }): string | null {
  // The server's classification first (brief v6 step V2); the count rule
  // below stands in only for a row from before the field existed.
  if (r.effective_scope !== undefined) return r.effective_scope;
  if (r.scan_scope) return r.scan_scope;
  const n = crawledPaths(r).length;
  if (!n) return null;
  return n === 1 ? "page" : n < SITE_WIDE_MIN_PATHS ? "nav" : "site";
}

/** Why a brief may not run against this run, or null where it may (brief
 *  v6 step V3) - the server's own sentence, said on the screen before the
 *  press rather than as a 409 after it. */
export function narrowPickNote(run: Pick<Run, "kind" | "scan_scope" | "crawled_paths">
                               & { effective_scope?: string | null; site_reading?: boolean }
                               | null | undefined): string | null {
  if (!run || isSiteReading(run)) return null;
  const n = crawledPaths(run).length;
  const word = scopeWord(scopeOf(run)) ?? "narrow audit";
  return `This audit is a ${word} — an analysis run against it reads ${n} page${n === 1 ? "" : "s"}. `
    + "Pick a site-wide audit, or run one on step 2.";
}

/** Not a finding: an Info row stating what the audit could not measure
 *  (`runs.is_coverage_note`, brief v5 step S). The server's own answer where
 *  the row carries it; the id pattern stands in for a row stored before the
 *  field existed.
 *
 *  Here rather than in one screen, because three decided it separately and the
 *  part page did not decide it at all: `PRF/cwv-not-assessed` reached Speed's
 *  Fixes block as a sixth fix where the part's own count is five, was drawn in
 *  the check table with the state word `open` - registered as "a fault the
 *  latest audit still found" - and got a fix card under the heading Fixes.
 *  Item 180's ruling: a coverage note is not a finding and is never counted
 *  with them. */
export const isCoverageNote = (s: { coverage_note?: boolean; severity: string;
                                    check_id: string }): boolean =>
  s.coverage_note ?? (s.severity === "info"
    && (/-not-assessed$/.test(s.check_id) || /-coverage$/.test(s.check_id)
        // `runs.ENGINE_RUN_NOTES` (item 238).
        || s.check_id === "adaptive-escalation" || s.check_id === "adaptive-no-escalation"));

/** A scan of one page or of the navigation set: its score is over those
 *  pages alone and is shown as such wherever a site score would be. */
export const isNarrowScope = (scope: string | null | undefined) =>
  scope === "page" || scope === "nav";

/** How a scope reads on screen. */
export const scopeWord = (scope: string | null | undefined) =>
  scope === "page" ? "page scan" : scope === "nav" ? "nav scan"
  : scope === "site" || scope === "full" ? "site-wide" : null;

/** What a narrow run's score is over, as a clause to set beside the number, or
 *  null where the run read the site and the score needs no qualifier.
 *
 *  `RunScore` withholds the number in a table cell, where there is no room to
 *  qualify it. In a sentence there is room, and withholding would be the worse
 *  answer: the composite is a real measurement of what it measured. One
 *  spelling, because it is said on the client screen's headline and on the
 *  Reports card, and those two disagreeing is the defect it fixes - twenty22's
 *  run 991401ab read one page of 53 and both printed a bare 72.77. */
export const scoreExtent = (scope: string | null | undefined) =>
  scope === "page" ? "over one page"
  : scope === "nav" ? "over its navigation" : null;

/** The newest completed audit that read the site rather than a page or its
 *  navigation - the crawl a "page not in latest crawl" claim may rest on.
 *  By `scopeOf`, never by tier. */
export function latestSiteWideCrawl(runs: Run[] | undefined): Run | null {
  for (const r of runs ?? []) {
    if (r.kind !== "audit" || !hasResults(r.status) || !r.crawled_paths) continue;
    const scope = scopeOf(r);
    if (scope === "site" || scope === "full") return r;
  }
  return null;
}

/** One change the run-to-run watch reports, as the alert strip renders it. */
export type WatchChange = { what: string; before: unknown; after: unknown;
                            severity: string; note?: string };

export type SiteDetail = {
  id: string;
  client_id: string;
  domain: string;
  locale: string;
  business_type: string | null;
  states: FindingState[];
  regressions: FindingState[];
  runs: Run[];
  trend: TrendPoint[];
  /** The most pages `POST /api/sites/{id}/verify` will re-crawl in one go,
   *  from `runs.VERIFY_PAGE_CAP`. Carried so the record tab's mark bar can
   *  decline a batch the route would answer 422 for, rather than spelling the
   *  ceiling a second time in TypeScript. */
  verify_page_cap?: number;
};

/** A point on a site's score trend, with the frame it was measured in.
 *
 *  Typed to the payload rather than to what the chart happened to read.
 *  `{ value, captured_at }` was narrower than what the server has sent
 *  since migration 0012, so `comparable` was not merely ignored by the
 *  chart - it could not be referred to at all, and two migrations existed
 *  to carry a caveat no screen could see.
 *
 *  `comparable` is the server's verdict, from `runs.site_trend`, keyed on
 *  engine version, share basis, tier and the dimension set. The other four
 *  fields are here so a screen can say *which* term moved; they are not here
 *  so a client can reach its own verdict. Two opinions about one fact is how
 *  they start to disagree.
 *
 *  `scope.dimensions` is the fourth term, added with WF-58. It is typed here
 *  for the same reason the other three are: the server now breaks the line on
 *  it, and a term the type drops is a break the screen can only describe as
 *  "the frame changed".
 *
 *  `scope.dimensions_basis` says which rung that set came from - `recorded`
 *  by the run on its own frame, or `derived` at read time from the
 *  per-dimension scores stored beside it. `null` is neither, and only then is
 *  the set unknown. It is typed and rendered rather than carried silently:
 *  a rung stored and read by nobody is CQ-205's open finding one table over,
 *  and a derived figure indistinguishable from a recorded one is the
 *  provenance breach this product is sold on not having.
 *
 *  `basis_key` is those four terms as one string, and `partner_index` /
 *  `partner_run_id` name the nearest EARLIER point that shares it — brief
 *  v16f. They are on the payload for the reason the four terms are typed and
 *  not re-judged: the chart shades a stretch by key, joins a point to its
 *  partner, and the Runs table offers a comparison against that same run, and
 *  three drawings of one fact must come from one answer. A client that
 *  grouped by its own key would be the second opinion this type's first
 *  paragraph exists to refuse.
 *
 *  `partner_index` indexes THIS list; `partner_run_id` is the run behind that
 *  point, and it is `null` where the run cannot be named — a snapshot written
 *  before migration 0044 whose stamp names two runs of the site. The pairing
 *  is still drawn in that case; only the link to it is withheld. */
export type TrendPoint = {
  value: number;
  captured_at: string;
  tier: string | null;
  engine_version: string | null;
  scope: {
    basis?: string | null;
    dimensions?: string[] | null;
    dimensions_basis?: "recorded" | "derived" | null;
  } | null;
  comparable: boolean;
  basis_key: string;
  /** True where `scope.dimensions` was read back off the per-dimension rows
   *  rather than recorded by the run. The chart rings those points. */
  basis_recovered: boolean;
  run_id: string | null;
  partner_index: number | null;
  partner_run_id: string | null;
  partner_captured_at: string | null;
};

export type ClientSummary = {
  id: string;
  name: string;
  notes: string;
  site_count: number;
};

export type ClientDetail = ClientSummary & {
  sites: {
    id: string;
    domain: string;
    business_type: string | null;
    latest_score: number | null;
    run_count: number;
    open_findings: number;
    regressions: number;
  }[];
};

export type Meta = {
  dimensions: {
    code: string; name: string; default_weight: number;
    /** The Current-tab sections this dimension's sweep refreshes. One
     *  dimension covers up to four, which is why the launcher cannot offer
     *  a section-level checkbox. */
    categories?: string[];
  }[];
  /** Sections no sweep populates — filled by an analysis or not at all. */
  analysis_only?: string[];
  tiers: string[];
  /** The scan scope table, keyed as the server's `scanscope.SCOPES` is.
   *  `max_pages` is the page budget the crawler will actually enforce for
   *  that scope; `null` means it takes the tier's own, which is not a figure
   *  any screen can state. The scan grid reads this rather than typing the
   *  cap it used to (CQ-245) — the labels are not here because the two
   *  languages word them differently on purpose. */
  scopes: Record<string, { max_pages: number | null }>;
  business_types: string[];
  analyst_available: boolean;
  analyst_budgets: Record<string, number>;
  providers: Record<string, { configured: boolean; detail: string; env: string }>;
  dimension_providers: Record<string, string[]>;
  models: string[];
};


/** What the hook knows, and which subject it knows it about.
 *
 *  One object rather than three `useState` calls, because the three move
 *  together or not at all — that is the whole of WF-13 and UX-13. Separate
 *  setters are what let an error from one request outlive it and a payload
 *  from one subject be read under another. `for` is the subject `data` and
 *  `error` describe; anything the caller is no longer asking about is not
 *  answered. */
type FetchState<T> = {
  for: string | null;
  /** The path `data` was actually fetched from, which is NOT `for`.
   *
   *  UX-56. `for` is what the payload is labelled by, and for `AnatomyView`
   *  that is deliberately the site rather than the URL, so the payload
   *  survives a page change. That left no record of which page the payload on
   *  screen belongs to, and the screen's stale banner inferred one from
   *  `loading` — a flag that goes true for every refresh, including four that
   *  change no path at all. The result was a false sentence, announced, right
   *  after two actions that cost money.
   *
   *  Written on the resolve path only, and left alone by the failure path: a
   *  failed poll does not move the payload, so it does not move the payload's
   *  provenance either. `null` until the first reply lands. */
  path: string | null;
  data: T | null;
  error: string | null;
  loading: boolean;
};

/** Fetch on mount and whenever `refresh` changes, discarding a response that
 *  arrives after the component has moved on. Lived in views.tsx until a
 *  second screen needed it; a data hook belongs with the client it uses.
 *
 *  **It answers for the current request only** — WF-13 and UX-13, one hook,
 *  eleven rounds. `live` dropped a superseded *reply*; nothing dropped the
 *  superseded *state*, so the hook kept answering questions about a request
 *  it was no longer making:
 *
 *  - `setError(null)` was never called anywhere, so the first dropped request
 *    poisoned the hook for the life of the component. Every screen reads
 *    `if (error)` before it reads `data` and `App.tsx` mounts `SiteDetailView`
 *    unkeyed, so a 503 on one site put an error on screen that walking to a
 *    healthy site could not clear. Reload was the only recovery and nothing
 *    said so. Two things clear it now: a result that is not an error, and a
 *    change of path.
 *  - `data` outlived its path, so between a site change and its response the
 *    screen showed the previous site's tab counts under the new site's URL.
 *
 *  `loading` and `retry` are the disclosed recovery the finding asked for.
 *  Both are read by `ErrorNote`, which every `useFetch` caller already
 *  renders — a flag no screen reads would be CQ-23's writer-with-no-reader in
 *  a new place. */
/** The loaded gate (item 179, loading honesty): whether a payload is the answer
 *  for the request being made NOW - the current selection's - and so may be
 *  drawn as fact.
 *
 *  `data` alone cannot say it. Between a change of subject and its reply a
 *  screen holds either nothing (a new identity blanks) or the previous
 *  request's payload (a same-identity path change keeps it, marked stale), and
 *  the UI audit found both drawn as the answer: "No audit to describe yet" on
 *  an audited site for 3 to 10 s on every client route, and a page's figures
 *  inside site sentences for 19 s after "Whole site" (11-1, 02-1, 02-2). An
 *  empty-state sentence, a 0 or a figure is drawn only when `ready`; until
 *  then the element says "Loading…".
 *
 *  Pure, and named as a hook because it is read beside `useFetch`'s result. */
export function useLoaded<T>(r: { data: T | null; payloadPath: string | null },
                             path: string | null): { ready: boolean; data: T | null } {
  const ready = r.data != null && path != null && r.payloadPath === path;
  return { ready, data: ready ? r.data : null };
}

export function useFetch<T>(path: string | null, refresh = 0,
                            identity?: string) {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<FetchState<T>>(
    { for: null, path: null, data: null, error: null, loading: false });

  // What this data is LABELLED BY, which is the path only by default.
  //
  // `AnatomyView` is why this is a parameter. Its screen is labelled by the
  // site and its page filter is a control on that screen, so blanking on
  // every path change unmounts the picker between keystrokes — which is the
  // regression `2ed927a` fixed by removing the blanking altogether, and
  // `test_a_late_response_for_another_page_is_not_rendered` still holds the
  // ground it was won on. Reports 025 and 030 name the remedy for that
  // screen and it is a different one: keep the payload and MARK IT STALE
  // while the next reply is in flight. `loading` is what makes that
  // expressible; passing `siteId` here is what makes it necessary.
  //
  // A change of identity still keeps nothing, so the cross-client case is
  // unaffected: walking to another site blanks, walking to another page of
  // the same site marks.
  const key = identity ?? path;

  useEffect(() => {
    if (!path) return;
    let live = true;
    // Announced before the request, not after it, and the same rule governs
    // `data` and `error`: a different path keeps nothing, a same-path
    // refetch keeps what is on screen until the result lands.
    //
    // Clearing the error here instead was tried and is wrong. Every caller
    // returns early on `error`, so clearing it at the top of the effect
    // unmounts the failure the moment Try again is pressed — the operator
    // gets a bare "Loading…" where the sentence they are acting on used to
    // be, and the control cannot report the state it put the app into. The
    // poison WF-13 names is an error that a SUCCESS did not clear, and the
    // resolve path below clears it. Holding it for the length of one request
    // is the screen staying still while it works.
    setState((s) => s.for === key
      ? { ...s, loading: true }
      : { for: key, path: null, data: null, error: null, loading: true });
    api.get<T>(path)
      .then((d) => {
        if (live) setState({ for: key, path, data: d, error: null,
                             loading: false });
      })
      // The payload is left alone: a single failed poll should not throw away
      // good data that is still about this path. The error is what is new.
      .catch((e: ApiError) => {
        if (live) setState((s) => ({ ...s, for: key, error: e.message, loading: false }));
      });
    return () => { live = false; };
  }, [path, key, refresh, nonce]);

  // The render between a change of subject and the effect still holds the
  // old subject's state, so the guard is here as well as in the effect.
  const mine = state.for === key;
  return {
    data: mine ? state.data : null,
    error: mine ? state.error : null,
    loading: path !== null && (state.loading || !mine),
    /** Which path `data` came from, so a caller can COMPARE rather than infer.
     *
     *  `loading` cannot answer "is what I am looking at out of date" — it
     *  answers "is a request in flight", and the two differ on every refresh
     *  that does not change the subject. A caller that needs the first asks
     *  this against the path it is currently requesting. `null` means there
     *  is no payload to be out of date, which is `<Loading/>`, not staleness. */
    payloadPath: mine ? state.path : null,
    retry: useCallback(() => setNonce((n) => n + 1), []),
  };
}
