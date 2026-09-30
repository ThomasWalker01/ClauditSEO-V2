/** The client view's landing (brief v23 step BL, moved by brief v24 step BM):
 *  one state sentence and one primary action in the bar, and three lanes as
 *  the body, at full height.
 *
 *  BL put the lanes in the bar as its three columns, capped at three entries
 *  so the bar kept one height. BM reverses that half (operator, 2026-09-14):
 *  the lanes are the landing, each a ranked list showing its first screenful
 *  and then "N more", which expands IN PLACE. A lane that sends the reader
 *  to another screen to see its fourth item is a summary, and the landing is
 *  not a summary. They keep their names and their order in both modes; the
 *  mode decides what they are about.
 *
 *  A lane count takes 140's tones and never the mode hue; the primary action
 *  stays `action-primary` blue in both modes (BK).
 */
import { heldRecordHref } from "./report_hold";
import { LinkButton, SecondaryButton } from "./buttons";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { Category } from "./anatomy";
import type { Lanes } from "./analyses";
import { hasScore, scopeOf, scoreExtent, type RunStatus } from "./api";
import { money } from "./components";
import { LOADING_WORD, NOT_READ, entry } from "./glossary";
import { goHandler, goto } from "./nav";
import { worst } from "./severity";
import { ageDays, ageTone, ageWords } from "./age";
import { Pill } from "./pill";
import { Counted, coverageNotes, type Headline, type Populations } from "./population";

/** Entries a lane shows before "N more": its first screenful, measured on the
 *  1568 x 1080 fixture. Since item 169 a sum, not a row times a count: an entry
 *  a reader acts on carries a sentence, so rows are no
 *  longer one height, and the parts strip now takes a band under the lanes.
 *  `test_the_first_screenful_fits_the_landing` sums each lane's head, the
 *  strip and the rendered entries, and reports what the tightest lane could
 *  still take in bare rows: 14 at the change (22 before it, when every row was
 *  31 px and nothing sat under the lanes). 13 leaves the row "N more" sits on,
 *  the margin the old number kept. Item 174's reference rhythm - a 2rem
 *  headline, 12 px entry padding, 16 px card padding - measured 8; 7 keeps
 *  that margin. */
export const SCREENFUL = 7;

/** The names, in their fixed order. Exported so the guard reads the same list
 *  the screen draws rather than a second spelling of it. */
export const LANE_NAMES = ["Waiting on you", "What has been measured", "Settled"] as const;

type Entry = {
  key: string;
  value: ReactNode;
  label: ReactNode;
  /** A 140 tone for the figure: `danger` for a regression, `warn` for
   *  outstanding work, `good` for what is settled. Never a mode hue. */
  tone?: "danger" | "warn" | "good" | "quiet";
  href?: string;
  name?: string;
  /** One sentence: what this figure means (item 169). Only the entries a reader
   *  acts on carry one; a sentence on every row is the wall of text the ledger
   *  already was. */
  detail?: ReactNode;
  /* No `actions` (item 207). A row went somewhere by its figure when the
     destination was the record and by a button under it otherwise, so the
     board had two places to press and the reader had to find which. The
     figure is the door now, whatever it opens. */
};

type Current = {
  outstanding: number; open: number; regressed: number; candidate: number;
  accepted_risk: number; withdrawn: number; fixed: number;
  moved: { opened: number; fixed: number; regressed: number };
} | undefined;

function Lane({ name, cls, entries, head }: {
  name: string; cls: string; entries: Entry[]; head?: ReactNode;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? entries : entries.slice(0, SCREENFUL);
  const rest = entries.length - shown.length;
  return (
    <section className={`cl-lane ${cls}`} aria-label={name}>
      <div className="scope-head cl-lane-head">
        <span className="sel-lbl">{name}</span>
        {head}
      </div>
      {shown.length ? (
        // The "N more" link sits in the entries' row but outside the <dl>:
        // a definition list may hold only dt/dd groups (axe
        // `definition-list`). `display: contents` on the dl lets the row's
        // flex layout reach its entries.
        <div className="cl-lane-row">
        <dl className="cl-lane-list">
          {shown.map((e) => (
            <div key={e.key} className={`cl-entry cl-${e.key}`}>
              <dt>{e.label}</dt>
              <dd className={`fig${e.tone ? ` fig-${e.tone}` : ""}`}>
                {e.href
                  ? <a className="fig-link" href={e.href} onClick={goHandler(e.href)}
                       aria-label={e.name}>{e.value}</a>
                  : e.value}
              </dd>
              {/* Item 169: a second dd in the group, so `definition-list` holds
                  and `dd.fig` keeps every selector. */}
              {e.detail && (
                <dd className="cl-entry-detail">
                  <p>{e.detail}</p>
                </dd>
              )}
            </div>
          ))}
        </dl>
          {/* A button, not a link: it expands this lane where it stands and
              the address does not change (brief v24 step BM). */}
          {rest > 0 && (
            <SecondaryButton className="cl-lane-more"
                    aria-expanded={false} onClick={() => setAll(true)}>
              {rest} more
            </SecondaryButton>
          )}
        </div>
      ) : <p className="muted cl-lane-empty">nothing here</p>}
    </section>
  );
}

/** How long ago, in the words a reader uses. The exact stamp rides in the
 *  element's `title`, and `standingHead` still links the absolute time to the
 *  run that moved the counts, so nothing is lost to the rounding. */
export function ago(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "at an unknown time";
  const ms = now - new Date(iso).getTime();
  if (!Number.isFinite(ms)) return "at an unknown time";
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} minute${min === 1 ? "" : "s"} ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

/** A stored instant as a clock the operator can compare with another one.
 *
 *  Every screen wrote `iso.slice(0, 16).replace("T", " ")`, which is not a
 *  conversion: it prints whatever offset the string happens to carry and then
 *  discards the offset that would have said so. The store holds both - a run's
 *  `started_at` is `+00:00` and a precheck's `checked_at` is `+10:00` - so two
 *  renderings of the same moment sat one card apart, ten hours apart:
 *
 *      AUDIT              2026-09-17 11:02 · T1 · page scan
 *      re-run precheck    checked 2026-09-17 21:02 · 7.4s
 *
 *  and the precheck had in fact finished nine seconds BEFORE the audit began
 *  (audit F11; its ranking table calls this F10 and its own sections call it
 *  F11, which is the numbering used here). `ago` above parses the offset and
 *  was right all along, which
 *  is why the same screen could say "12 hours ago" over a stamp reading 11:02.
 *
 *  Local time, because the reader's other clock is their own. The zone is
 *  named where two stamps must be compared across machines; here the point is
 *  that two stamps on one screen are in one zone. */
export function stamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return "—";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** What sentence three calls each step. A template, not a triage special
 *  case (channel ruling 20260917-0045): "Triage is what is left.", "The
 *  catalogue is what is left." */
const LEFT_PHRASE: Record<string, string> = {
  "Precheck": "The precheck", "Audit": "An audit", "Triage": "Triage",
  "Analyses": "The catalogue", "Record": "The record",
  "Client report": "The client report",
};

/** The state sentence (item 168; brief v23 BJ's three numbers, BL's one
 *  sentence). Concept 05's shape - three short sentences, the last of which is
 *  the instruction - carrying every fact the single sentence did:
 *
 *    Audit T3 finished 7 hours ago and scored 71.28.
 *    It found 505 findings across 45 of the 74 pages on the site; 87 of them
 *    have been through.
 *    Triage is what is left.
 *
 *  Coverage's share moved to its figure's `title` and `data-pct`; it is shown
 *  without hovering in the Measured lane. The assessed share stays in the text
 *  ("87 of them (17%)"), because nothing else on the landing shows it - so
 *  each share is visible exactly once (channel ruling 20260917-0125). The hooks the tests and the screen address stay:
 *  `.fig-coverage` / `.fig-coverage-n`, `.fig-size`, `.fig-assessed`, and
 *  `data-run` naming the run the server computed them for. A size that could
 *  not be read keeps `.fig-size` (on the word "pages") and its title; the
 *  caveat's words live in the Waiting lane's retrieval entry. */
export function StateSentence(props: Parameters<typeof StateSentenceBody>[0] & {
  /** The landing's headline is the page's h1 (item 181, 02-9). */
  heading?: boolean;
}) {
  const { heading = false, ...rest } = props;
  const body = <StateSentenceBody {...rest} />;
  return heading ? <h1 className="bl-h1">{body}</h1> : body;
}

function StateSentenceBody({ headline, run, nextStep = null, loading = false }: {
  headline: Headline | null;
  /** Item 179: the headline for the current audit has not arrived. Says the
   *  registered word, never "No audit to describe yet", which is the answer
   *  for a site with no audit and was drawn on audited ones (11-1). */
  loading?: boolean;
  run: { started_at: string; finished_at?: string | null; tier?: string;
         composite_score: number | null; status?: string;
         /** What the run read, from the server (`scope_of`, brief v6 step V2).
          *  The sentence prints a composite and so has to say whether it is
          *  the site's: F2 of the 2026-09-18 audit. */
         effective_scope?: string | null; scan_scope?: string | null;
         crawled_paths?: string | null } | null;
  nextStep?: string | null;
}) {
  if (loading) {
    return <span className="muted bl-sentence bl-loading" role="status">{LOADING_WORD}…</span>;
  }
  if (!headline) return <span className="muted bl-sentence">No audit to describe yet.</span>;
  const size = headline.site_size;
  const cov = headline.coverage;
  const as = headline.assessed;
  const unknown = size.unknown || cov.unknown || cov.pct == null;
  // `exact`, because `stamp` is the helper above: this local shadowed it.
  const exact = run ? stamp(run.finished_at || run.started_at) : null;
  const scored = run && run.composite_score != null
    && (run.status == null || hasScore(run.status as RunStatus));
  /** What the score is over, where that is not the site (F2, audit of
   *  2026-09-18). `hasScore` above asks whether a score was PRODUCED, and
   *  `api.ts:282` says in as many words that this is the wrong question for
   *  printing one: twenty22's run 991401ab read one page of 53 and this
   *  sentence said "scored 72.77" on every Client tab, while the Record's cell
   *  for the same run said "page scan". The number stays - it is the right
   *  measurement of what it measured - and says what it measured. */
  const extent = run ? scoreExtent(scopeOf(run)) : null;
  return (
    <span className="bl-sentence" data-run={headline.run_id}>
      {/* One: which audit, when, and what it scored. */}
      <span className="bl-s1">
        Audit {run?.tier ? <><span className="bl-tier">{run.tier}</span>{" "}</> : null}finished{" "}
        <time className="bl-when" dateTime={run?.finished_at || run?.started_at || undefined}
              title={exact ?? undefined}>
          {run ? ago(run.finished_at || run.started_at) : "at an unknown time"}
        </time>
        {scored ? <> and scored <b className="bl-score">{run!.composite_score}</b>
                    {extent ? <> <span className="bl-extent">{extent}</span></> : null}</> : null}.
      </span>{" "}
      {/* Two: BJ's three facts, as prose. */}
      <span className="bl-s2">
        It found <span className="bl-found">{as.total} finding{as.total === 1 ? "" : "s"}</span> in this audit across{" "}
        {/* Coverage = crawled over site size, per run; the figure that follows
            the pick, so `data-run` is the run the server computed it for. */}
        <span className="fig-coverage" data-run={headline.run_id}
              data-pct={unknown ? "" : String(cov.pct)}
              title={(unknown ? "" : `${cov.pct}% of the site: `)
                     + "pages this audit fetched, over the size of the site. Per audit - a pulse and a full crawl of the same site are different figures."}>
          <b className="fig-coverage-n">{headline.audited}</b>
        </span>
        {unknown
          ? <>{" "}
              <span className="fig-size" data-unknown="1"
                    title={"Site size not known. The sitemap could not be read cleanly in this audit"
                           + (size.unknown_reason ? ` (${size.unknown_reason})` : "")
                           + ", so the site's size is not known and nothing on this "
                           + "screen is divided by it."}>
                page{headline.audited === 1 ? "" : "s"}
              </span></>
          : <>{" "}of the{" "}
              {/* Site size = declared ∪ discovered, never the declaration alone:
                  divide by the declaration and coverage rises when the
                  declaration fails. */}
              <span className="fig-size" data-unknown=""
                    title={`${size.declared} declared in the sitemap, ${size.discovered} `
                           + "reached by the crawl. The union, never the declaration "
                           + "alone: divide by the declaration and coverage rises when "
                           + "the declaration fails."}>
                <b>{size.size}</b>
              </span>{" "}pages on the site</>}.
        {/* What the count left out, in the words Home uses (item 180's ruling).
            Before this the sentence counted them and said nothing: 36 here
            against 32 in the lane below. */}
        {as.notes ? ` ${coverageNotes(as.notes)} not counted.` : ""}
        {/* The assessed share left the sentence at item 174 (channel ruling
            20260917-1430): with it the headline could not set in two lines at
            68ch. It is the Settled lane's "Assessed" entry, which keeps it
            visible without hovering - 0125's reason for keeping it at all. */}
      </span>
      {/* Three: the instruction, which the button under it carries out. */}
      {nextStep && LEFT_PHRASE[nextStep] && (
        <>{" "}<span className="bl-s3">{LEFT_PHRASE[nextStep]} is what is left.</span></>
      )}
    </span>
  );
}

/** Each mode states its own arithmetic (brief v23 step BK), and the paragraph
 *  that apologised for page mode is gone. It asserted a rule - "they no longer
 *  sum to the site total" - true on Birch's home page (parts 26, standing 24)
 *  and false on Twenty22's (17 and 17), so this reports the numbers in hand.
 *  `cur-filter-note` stays the class the rendered tests wait on for "a page is
 *  in scope". */
export function ModeArith({ page, parts, standing, siteOnly = 0 }: {
  page: string; parts: number; standing: number;
  /** Findings the page filter set aside because they are about the site as one
   *  subject (audit F15). This component was honest about the other arithmetic
   *  risk - "a cause touching several parts is counted in each" - and silent
   *  about this one, so twenty22's page mode read 29 against the site's 32 on
   *  the only page the audit crawled. */
  siteOnly?: number;
}) {
  return (
    <span className={`muted mode-arith${page ? " cur-filter-note" : ""}`}>
      {page
        ? (parts === standing
            ? <>On this page the parts sum to its standing.</>
            : <>On this page the parts sum to {parts}, not {standing}: a cause
                touching several parts is counted in each, as shared-cause
                marking is off on one page.</>)
        : (parts === standing
            ? <>The parts sum to the standing.</>
            : <>The parts sum to {parts}, not {standing}.</>)}
      {page && siteOnly > 0 && (
        <>{" "}{siteOnly} finding{siteOnly === 1 ? " is" : "s are"} about the
          site as a whole and {siteOnly === 1 ? "is" : "are"} not counted on any
          page.</>
      )}
    </span>
  );
}

/** The integrity line, separate from the sentence and a threshold rather than
 *  a gradient: no Critical or High may be unassessed when the client report is
 *  generated. Said only while it holds the report, because a green "clear"
 *  beside a percentage reads as a second progress bar. */
export function IntegrityLine({ headline, checking = false }: {
  headline: Headline | null;
  /** The guard has not been read yet (item 179, 08-6): the held button is
   *  described by this line, so it says what it is waiting on. */
  checking?: boolean;
}) {
  if (checking) {
    return (
      <span className="integrity-line integrity-checking muted" id="integrity-line" role="note">
        Checking whether the client report can go out…
      </span>
    );
  }
  const n = headline?.integrity?.count ?? 0;
  if (!n) return null;
  return (
    <span className="integrity-line" id="integrity-line" role="note">
      Client report held: {n} Critical or High not yet assessed.
    </span>
  );
}

/** What "been through" counts, for the Assessed entry's title (item 174):
 *  every state but `open`, as `run_assessed` counts them. */
const ASSESSED_TITLE = "Findings this audit raised that are no longer simply open - fixed, regressed, accepted, withdrawn or candidate. Unweighted: a Low looked at counts as much as a Critical, because this measures how much of the audit has been read, not progress toward fixed.";

export function ClientLanes({ siteId, page, current, categories, headline, lanes,
                              outstanding, record, standingHead, pops = null,
                              runState = null, arith = null }: {
  siteId: string;
  /** The mode's arithmetic (`ModeArith`), a footnote to the parts it sums
   *  (item 174): nothing sits between the actions and the lanes but the legend. */
  arith?: ReactNode;
  page: string;
  /** The populations a count is counted over (item 155): a part's row
   *  carries its own count through them, never a bare integer (156). */
  pops?: Populations | null;
  current: Current;
  categories: Category[];
  headline: Headline | null;
  lanes: Lanes | null;
  /** Findings in scope - the standing, narrowed when a page is. */
  outstanding: number;
  /** Pages in the record: bookkeeping, never a headline denominator (BJ). */
  record: number;
  /** The pill naming the run that last moved the standing counts. */
  standingHead?: ReactNode;
  /** Whether an audit is in flight, and when the last one finished (item 173):
   *  the middle lane says so, so the landing answers "is anything happening"
   *  without the reader leaving it. */
  runState?: { running: { started_at: string } | null;
                /** Completed audits of the site (item 180): one means a first audit. */
                audits?: number;
               last: { finished_at?: string | null; started_at: string } | null } | null;
}) {
  const recordAt = (state: string) => `#/sites/${siteId}?tab=all&state=${state}`;
  const link = (n: number, state: string, what: string) =>
    !page && n > 0 ? { href: recordAt(state), name: `${n} ${what} — open the record` } : {};
  /** Item 207: a figure's door to anywhere, under F-11's rule - it opens
   *  exactly what it counted, which is why each caller's `href` carries the
   *  narrowing that makes that true. No door onto nothing, and none in page
   *  mode, where these destinations cannot be narrowed to the page. */
  const door = (n: number, href: string, name: string) => (!page && n > 0 ? { href, name } : {});
  const regressed = categories.reduce((n, c) => n + c.regressed.value, 0);
  const severe = headline?.integrity;

  // WAITING ON YOU. Ranked: regressions first, because a regression is the one
  // thing that genuinely demands attention; then a retrieval issue, labelled
  // as itself - a question for us, not a fault of the site; then the Critical
  // and High nobody has looked at; then the rest.
  const waiting: Entry[] = [];
  if (regressed > 0) {
    // No action: the figure is already the `state=regressed` record link. The
    // sentence stops at what the click delivers - the record does not name the
    // audit that saw each one return (channel ruling 20260917-0140).
    waiting.push({ key: "regressed", value: regressed, tone: "danger",
                   label: page ? "Regressed on this page" : "Regressed",
                   detail: "Fixed once and back since.",
                   ...link(regressed, "regressed", "regressed") });
  }
  const size = headline?.site_size;
  if (!page && size?.unknown && /retriev|source failed/i.test(size.unknown_reason ?? "")) {
    // Where the state sentence's caveat went (item 168).
    waiting.push({ key: "retrieval", value: "?", tone: "quiet",
                   label: `Suspected retrieval issue: ${size.unknown_reason}`,
                   detail: "The sitemap could not be read, so nothing here is divided by "
                           + "the site's size. A question for us, not a fault in the site." });
  }
  if (!page && severe && severe.count > 0) {
    // The action opens the record on what is open (item 196). It used to
    // offer Triage, and the comment above it read "the way to lift the hold"
    // - which it was not: "unassessed" is `state == 'open'`, only `set_state`
    // changes that, and triage wrote no state at all. A reader who followed
    // the primary action spent, received a ranking, and the held count was
    // unchanged. That circle is the item's finding.
    //
    // Not narrowed to Critical and High, though the hold is: the record's
    // severity filter is component state rather than the address, and the
    // hold spans two severities, so a link carrying it needs a registered
    // word for "critical or high" (item 166). The record opens on the open
    // findings with its severity chips a click away, and `set_state` is
    // there, which is the half that lifts the hold.
    //
    // Item 207: and now to exactly those - `state=open`, `sev=` pressing both
    // chips. Item 239 step 7: the count is the site's open Critical and High
    // in the running record (`open_severe`), which is what a client report is
    // a copy of, so the door carries no audit narrowing.
    waiting.push({ key: "severe", value: severe.count, tone: "warn",
                   label: "Critical or High open",
                   detail: "The client report is held until these have been looked at.",
                   ...door(severe.count, heldRecordHref(siteId),
                           `${severe.count} Critical or High still open on the site — open them in the record`) });
  }
  const withOpen = categories.filter((c) => c.total.value > 0).length;
  if (outstanding > 0) {
    // One action: the figure is already the record link, and a second target
    // onto the same place is the `target-size` collision noted above.
    const open = page ? outstanding : (current?.open ?? outstanding);
    const back = !page && current && current.regressed > 0
      ? ` and ${current.regressed} regressed` : "";
    // "Outstanding in the record", not "Outstanding" (audit F5): this is
    // `standing_by_state` over every audit, and it sat bare beside a primary
    // action counting this run's findings. On Birch the two read 167 and 164,
    // adjacent, with nothing saying they count different things.
    waiting.push({ key: "outstanding", value: outstanding, tone: "warn",
                   label: page ? "Outstanding on this page" : "Outstanding in the record",
                   detail: `${open} open${back}${page ? "" : " across every audit"}, `
                           + `across ${withOpen} part${withOpen === 1 ? "" : "s"}`
                           + `${page ? " on this page" : ""}. The worst are ranked first, `
                           + "so the first you open is the one that matters.",
                   // One action, and it is the record link below (item 196).
                   // This lane used to sell triage - "Triage ranks them so the
                   // first you open is the one that matters" - which was a
                   // sentence advertising a purchase inside a count of work.
                   // The ranking is the audit's now, so the claim is true
                   // without anything being bought, and the second target
                   // onto the same place goes with the sale.
                   ...link(outstanding, "outstanding", "outstanding") });
  }
  if (!page && current && current.candidate > 0) {
    waiting.push({ key: "candidate", value: current.candidate, tone: "quiet",
                   label: "Seen once", ...link(current.candidate, "candidate", "seen once") });
  }
  // The parts are not in this lane (item 169). A part is a breakdown of the
  // standing, not a task, so every part sits in the strip under the lanes
  // (`PartsStrip`), which is also how a part is reached from the landing now
  // the sidebar is gone (brief v24 step BO's table).

  // WHAT HAS BEEN MEASURED. A part reading 0 because nothing looked is not a
  // part reading 0 because nothing is wrong, so what no brief has read and
  // what this run could not measure are entries, not footnotes.
  // Item 180 (ruling 20260918-0406): read means read against THIS audit, and a
  // part with analyses at all can be unread - Local's briefs enumerate no
  // checks, and it read "nothing to say" while four analyses were never run.
  const unread = unreadParts(categories);
  const unmeasured = categories.filter((c) => Object.keys(c.not_assessed ?? {}).length > 0);
  const measured: Entry[] = [];
  if (!page && headline) {
    const cov = headline.coverage;
    measured.push({ key: "coverage", value: headline.audited,
                    label: cov.unknown || cov.pct == null
                      ? "Pages audited, site size unknown"
                      : `of ${cov.size} pages audited (${cov.pct}%)` });
  }
  measured.push({ key: "unmeasured", value: unmeasured.length, tone: unmeasured.length ? "warn" : undefined,
                  label: page ? "Parts not measured on this page"
                              : "Parts this audit did not fully measure" });
  measured.push({ key: "unread", value: unread.length, tone: unread.length ? "warn" : undefined,
                  label: `Parts ${NOT_READ} on this audit`,
                  ...(unread.length ? {
                    detail: "A part reading 0 means the automatic checks saw nothing there, "
                            + "not that an analysis cleared it.",
                    // Item 207: the catalogue narrowed to these parts, so the
                    // press shows as many parts as the figure says.
                    ...door(unread.length, `#/sites/${siteId}?tab=analyses&only=unread`,
                            `${unread.length} part${unread.length === 1 ? "" : "s"} not read on this audit`
                            + " — open them in the catalogue"),
                  } : {}) });
  if (!page && lanes) {
    // Item 180 (ruling 20260918-0405): the number the catalogue lists, and the
    // price of pressing its Run all - one server sum - with the remainders
    // named where the operator can act on them.
    const b = lanes.batch;
    const notRun = b ? b.listed : lanes.available.filter((a) => a.type !== "triage").length;
    const plan = b?.partless.find((x) => x.tool === "plan");
    const rest = [
      plan ? `client plan${plan.est_cost_default != null ? ` ${money(plan.est_cost_default)}` : ""}, from Reports` : "",
      b && b.need_page ? `${b.need_page} need${b.need_page === 1 ? "s" : ""} a page` : "",
      // The remainder that made this a false promise (audit F4): `count` used
      // to include an analysis whose state is `needs_input`, so the aside said
      // "run 22" - with a price, on Birch - beside a button that ran 21.
      b && b.needs_input
        ? `${b.needs_input} need${b.needs_input === 1 ? "s" : ""} context a crawl cannot supply`
        : "",
    ].filter(Boolean);
    // Item 207: the catalogue's own count (item 180), and until now a figure
    // that led nowhere beside a row whose button led to the same list.
    measured.push({ key: "depth", value: notRun,
                    ...door(notRun, `#/sites/${siteId}?tab=analyses&only=not-run`,
                            `${notRun} analys${notRun === 1 ? "is" : "es"} not run — open them in the catalogue`),
                    label: <>Analyses not run{b && b.count
                      ? <span className="cl-entry-aside">
                          {" · "}{b.cost != null ? `${money(b.cost)} to run ${b.count}` : `run ${b.count}, no estimate yet`}
                          {rest.length ? ` · + ${rest.join(" · ")}` : ""}
                        </span> : null}</> });
  }

  // Is anything happening right now (item 173; concept 05's middle lane). The
  // idle case only (channel ruling 20260917-1125): while an audit runs, the
  // strip's busy pill already says "running now" on every tab and the Find
  // chapter carries the same word, so the lane defers rather than saying it a
  // second time (item 140). No re-check button: 05 drew "Re-check on-page ·
  // free", and no site-level free re-check exists to put behind one; the
  // sentence links to the Audit pane, where re-running lives.
  if (!page && runState && !runState.running) {
    const auditAt = `#/sites/${siteId}?tab=history`;
    if (runState.last) {
      // Item 207: the one row with no count, so its sentence is the door -
      // a block-level target (axe `target-size` caught inline ones here).
      measured.push({ key: "running", value: "—", tone: "quiet",
                      label: "Nothing is running",
                      detail: (
                        <a className="cl-entry-go" href={auditAt} onClick={goHandler(auditAt)}>
                          The last audit finished{" "}
                          {ago(runState.last.finished_at || runState.last.started_at)}.
                        </a>
                      ) });
    }
  }

  // SETTLED. Fixed, assessed, and what changed since the last visit. The
  // record is the site's, so on one page this lane says that rather than
  // drawing the site's figures under a page it did not count them over.
  const settled: Entry[] = [];
  if (page) {
    settled.push({ key: "site-only", value: "—", tone: "quiet",
                   label: "Settled states are the site's record, not a page's" });
  } else if (current) {
    settled.push({ key: "fixed", value: current.fixed, tone: "good", label: "Fixed to date",
                   ...link(current.fixed, "fixed", "fixed to date") });
    // What this audit's findings have been through (item 174; it was the state
    // sentence's clause). Everything assessed has been dealt with, which is
    // what this lane holds. Unweighted, and said so: a Low looked at counts as
    // much as a Critical, so this is how much of the audit has been read, never
    // progress toward fixed (`runs.py`).
    const as = headline?.assessed;
    if (as && as.total > 0) {
      settled.push({ key: "assessed", value: as.assessed, label: "Assessed",
                     detail: (
                       <span className="fig-assessed" data-pct={as.pct != null ? String(as.pct) : ""}
                             title={ASSESSED_TITLE}>
                         {/* `<1%`, not `0%`, where something HAS been assessed
                             (audit F16): Acme read `Assessed 2` with `0% of
                             this audit's 882 findings` directly under it -
                             `round(2/882*100)`. A 0 beneath a 2 claims the
                             quiet the registry gives `count-zero`, which is
                             "a count of zero", for a count that is not. */}
                         {as.pct != null
                            ? `${as.pct === 0 && as.assessed > 0 ? "<1" : as.pct}% `
                              + `of this audit's ${as.total} findings`
                            : `${as.assessed} of this audit's ${as.total} findings`}
                         {" "}have been through. Unweighted: a Low looked at counts as much as
                         a Critical.
                       </span>
                     ) });
    }
    const moved = current.moved;
    if (moved.opened || moved.fixed || moved.regressed) {
      settled.push({ key: "moved", value: `+${moved.opened} −${moved.fixed}`,
                     // Item 180 (02-14): with one audit there is no last one.
                     label: (runState?.audits ?? 2) > 1 ? "Since the last audit" : "First audit",
                     ...(moved.regressed ? { detail: `${moved.regressed} regressed.` } : {}) });
    }
    if (current.accepted_risk > 0) {
      settled.push({ key: "accepted", value: current.accepted_risk, tone: "quiet",
                     label: "Accepted risk", ...link(current.accepted_risk, "accepted-risk", "accepted risk") });
    }
    if (current.withdrawn > 0) {
      settled.push({ key: "withdrawn", value: current.withdrawn, tone: "quiet",
                     label: "Withdrawn", ...link(current.withdrawn, "withdrawn", "withdrawn") });
    }
  }

  return (
    <>
      {/* Above the lanes, on the operator's ruling (item 195A): "I want it to
          sit between these two rows for this screen only. above the waiting
          on you section."

          It ended the page before - 873px of a 1067px landing, the bottom
          fifth - and it is the only control that reaches a part, so a reader
          who wanted one scrolled past everything the parts are a breakdown
          of.

          This is the one thing item 174's reference does not allow beside the
          legend, and the ruling is what moved it rather than a reading of the
          reference. `test_the_landing_matches_the_reference` carries the
          amendment and the words it was made in. */}
      <PartsStrip siteId={siteId} page={page} categories={categories} pops={pops}
                  unread={new Set(unread.map((c) => c.key))} arith={arith} />
      <Lane name={LANE_NAMES[0]} cls="lane-waiting" entries={waiting} head={standingHead} />
      <Lane name={LANE_NAMES[1]} cls="lane-measured" entries={measured}
            head={
              // The record, kept and demoted (BJ): bookkeeping, not a
              // denominator, so it rides in the lane's head where the entry
              // cap cannot hide it and nothing is divided by it.
              <span className="muted fig-record"
                    title="Every page stored for this site across every audit - bookkeeping, not a denominator. It holds pages the site no longer serves.">
                {record} in the record
              </span>} />
      <Lane name={LANE_NAMES[2]} cls="lane-settled" entries={settled} />
    </>
  );
}

/** The site underneath (item 169; concepts 05 and 10): every part, in the
 *  anatomy's order, zeros included, each one link. A browsable breakdown of
 *  the standing rather than entries in a queue - which is where the parts sat,
 *  two organising models with neither subordinate, one level down.
 *
 *  Every part or the head's "every part" is false, and a reader who cannot
 *  find a part here looks for it in the lanes. A part no analysis has read is
 *  marked: its 0 is not a clearance (channel ruling 20260917-0140). The figure
 *  in the head is what the links add up to, so it is true by construction;
 *  whether that equals the standing is `ModeArith`'s sentence to say. */
function PartsStrip({ siteId, page, categories, pops, unread, arith = null }: {
  siteId: string; page: string; categories: Category[];
  pops: Populations | null; unread: Set<string>; arith?: ReactNode;
}) {
  const sum = categories.reduce((n, c) => n + c.total.value, 0);
  return (
    <nav className="cl-parts" aria-label={page ? "The page underneath" : "The site underneath"}>
      <div className="cl-parts-head sel-lbl" data-sum={String(sum)}>
        {page ? "The page underneath" : "The site underneath"} · every part, sums to {sum}
        {arith && <>{" "}{arith}</>}
      </div>
      <ul className="cl-parts-list">
        {categories.map((c) => (
          <li key={c.key}>
            <PartLink siteId={siteId} c={c} pops={pops} unread={unread} />
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** Which parts no analysis has read *against this audit* (item 180, ruling
 *  20260918-0406), as one rule rather than one per screen.
 *
 *  It decides a mark, and the mark is load-bearing: a part reading 0 because
 *  nothing looked is not a part reading 0 because nothing is wrong (ruling
 *  20260917-0140). Two screens now draw this pill - the landing's strip and
 *  the part view's switcher - and a rule copied is a rule that drifts, which
 *  here would spell a clearance the record does not hold. A part with no
 *  analyses at all cannot be unread: Local's briefs enumerate no checks. */
export function unreadParts(categories: Category[]): Category[] {
  // Narrowed by the channel (20260924-0220-180): a part counts only if the
  // catalogue lists an analysis for it, because the count's door is the
  // catalogue and a member it cannot act on is the seam item 207 closed.
  // `catalogued` absent (an older payload) is taken as listed.
  return categories.filter((c) => c.tools.length > 0 && c.catalogued !== false
    && (!c.brief_run || (c.brief_run.audits_since ?? null) !== 0));
}

/** One part as a link, drawn the same way wherever it is drawn: the landing's
 *  strip (item 169, item 172's chip) and the part view's switcher (item 185).
 *
 *  Shared rather than copied for the reason `unreadParts` records - the
 *  unread mark is a rule, and this markup is where it is spelled. `open` is
 *  the switcher's only addition: the part the reader is standing in, marked
 *  with `aria-current` because "which one am I in" is the question a switcher
 *  exists to answer, and left as a link so the address stays copyable.
 *
 *  **What `note` saves, and what it may not.** It drops the trailing
 *  staleness phrase ("not read", "read 3 audits ago") and nothing else.
 *  Measured with it, 18 pills took four rows at 1180px and twelve at 390px, so
 *  a control asked to stay in view was scrolling its own rows to carry a
 *  sentence; without it, two rows at 1180px.
 *
 *  **It used to drop the count as well, and that was wrong** (item 186, from an
 *  operator report against item 185's first build). I had read ruling
 *  20260917-0140 as "a figure from a part nothing read may not stand
 *  unqualified"; it says that a ZERO from such a part is not a clearance. A
 *  part's count is the automatic checks' own findings - 67 is 67 whether an
 *  analysis has read the part or not - and on a site whose analyses have not
 *  run, every part is unread, so the switcher rendered eighteen pills with no
 *  figure at all. It also rendered them with no COLOUR: `.parts-n` is the only
 *  coloured token on the pill, so withholding the figure withheld the tone
 *  with it, and the breakdown of the standing read as a tab bar. Item 174's
 *  words are "unread is the word beside the count, not a dashed edge and a
 *  muted figure" - the word annotates a count that is present, and dropping
 *  both halves is not the compact version of that.
 *
 *  The zero case keeps its qualification where a compact pill can carry it:
 *  the dim tone, the `title`, and the `aria-label`, which says the count and
 *  then the staleness in words for a reader who gets no tone at all. */
function PartLink({ siteId, c, pops, unread, open = false, note = true }: {
  siteId: string; c: Category; pops: Populations | null;
  unread: Set<string>; open?: boolean;
  /** Whether an unread part spends a line saying how stale (the strip) or
   *  simply shows no figure (the switcher). */
  note?: boolean;
}) {
  const href = `#/sites/${siteId}?tab=findings&part=${encodeURIComponent(c.key)}`;
  const isUnread = unread.has(c.key);
  return (
    <a className={`parts-link cl-part-${c.key}${isUnread ? " parts-unread" : ""}`
                   + (c.total.value === 0 ? " parts-zero" : "")
                   + (open ? " parts-open" : "")}
       href={href} onClick={goHandler(href)}
       aria-current={open ? "page" : undefined}
       data-n={String(c.total.value)} data-unread={isUnread ? "1" : ""}
       title={isUnread ? "No analysis has read this part; 0 here is not a clearance." : undefined}
       aria-label={`${c.label}: ${c.total.value} open`
                  /* Item 166, the half item 195B left open: the tone on
                      the count says which severity, and nothing else did -
                      the text is a number, the landing draws no legend, and
                      colour was the only channel. Under the SAME condition
                      as the tone, so the word and the colour cannot drift. */
                  + (c.total.value > 0 && c.findings.length
                     ? `, worst ${worst(c.findings)}` : "")
                   + (isUnread ? `, ${NOT_READ}` : "")
                   + (open ? " — the part you are reading" : " — open the part")}>
      <span className="parts-name">{c.label}</span>
      {" "}
      {/* The count wears the worst severity inside it (item 195B, the
          operator's decision). `worst()` is the sidebar's own rule, unused
          since brief v24 step BO retired the sidebar and the strip that
          replaced it never carried the colour across; its docstring is the
          reason this is a restoration rather than a new scheme - "so scanning
          the tree finds the severe categories before the merely large ones".

          The tone classes are the registered ones, measured per tone, so the
          strip borrows the vocabulary every other measured item wears instead
          of inventing a fourth for one band (item 166).

          A part with nothing open takes no tone: `.parts-zero` already paints
          it dim, and a severity badge on a zero would colour an absence. */}
      {/* No `muted` here. Item 186 added it for the unread case; it was
          overridden by `.parts-unread .parts-n` from the day it shipped, so
          it never had an effect, and with a tone on the same element it would
          take the tone's ink off its own background. Item 174's rule is
          unchanged - unread is the WORD beside the count - and the figure now
          carries severity rather than carrying nothing. */}
      <span className={"parts-n"
                       + (c.total.value > 0 && c.findings.length
                          ? ` tone tone-sev-${worst(c.findings)}` : "")}>
        <Counted count={c.total} pops={pops} />
      </span>
      {/* Item 239 step 6: out of date by the part's reference crawl - a word
          beside the count, not a colour alone. */}
      {c.sweep_run && ageTone(ageDays(c.sweep_run.at), c.age_thresholds ?? undefined) === "stale" && (
        <span className="parts-stale" title={`measured ${ageWords(ageDays(c.sweep_run.at) ?? 0)} ago`}>
          {" "}stale</span>
      )}
      {note && isUnread && <span className="muted parts-unread-mark">
        {" "}{c.brief_run && (c.brief_run.audits_since ?? 0) > 0
          ? `read ${c.brief_run.audits_since} audit${c.brief_run.audits_since === 1 ? "" : "s"} ago`
          : NOT_READ}
      </span>}
    </a>
  );
}

/** The way back to the other parts, from inside one (item 185).
 *
 *  The landing's strip is the browse model's spine and it stood in exactly one
 *  place: a pill opened a part, the strip did not come with it, and the way to
 *  the next part was Back, a scroll to the foot of the landing, and a click.
 *  Measured on twenty22 before this - 18 `part=` links on the landing, 0 on an
 *  open part, the strip itself 80% of the way down a document it ends.
 *
 *  Kept in view rather than merely first, because first is the top of a part
 *  page that measured 4,010 px: from where the reader actually is, "scroll to
 *  the top" is the full-page scroll this item exists to remove. It can be
 *  sticky without a fight - the 268 px above a part's heading (scope bar, pane
 *  head, legend) is all static, and the only other sticky thing on the screen
 *  is the re-audit drawer, in its own column.
 *
 *  It carries no head line and no arithmetic. Those belong to the landing,
 *  where this list is the breakdown of the standing; here it is a control, and
 *  a control that restates the standing spends the band it has to stay small
 *  in. Both scope modes get it: the strip's own `page` split was only ever its
 *  label, and the page in hand travels with the link (`keepPageScope`). */
/** The way UP, from inside a part to the screen the parts are a breakdown of
 *  (item 194).
 *
 *  Measured on the operator's own site before this: 59 links on an open part,
 *  30 of them to this site, and not one the bare address the landing lives at.
 *  Item 185 fixed the sibling problem - the way back to the OTHER parts - and
 *  the level above was never in its scope, which is how a fix that solved
 *  movement within a level left movement between levels unreachable.
 *
 *  It clears `part` and `tab` and navigates with `keepScope: false`. The scope
 *  carry copies `part` forward from the address being left, so a link built
 *  the ordinary way arrives back where it started - which is exactly why
 *  "Open the catalogue" does nothing from inside a part, measured the same
 *  day. `selectPart` records the same trap in the same words.
 *
 *  `page` and `run` travel: the landing reads both, and a reader who narrowed
 *  to a page or pinned an audit has not asked to leave either behind. */
/** The landing's name, and it is a SECOND SPELLING of one `views.tsx` already
 *  holds in `PANES.landing.label`.
 *
 *  That is what item 166 exists to stop, and it is spelled here anyway:
 *  `views.tsx` imports values from this file, so importing the label back out
 *  of it would close a runtime cycle - the same edge `worst()` was moved to
 *  `severity.ts` to avoid. Moving the whole pane register somewhere neutral
 *  is the fix and is more than this item.
 *
 *  So the duplication is declared rather than hidden, and
 *  `test_the_way_up_is_on_every_part.py` holds the two strings to each other:
 *  if the pane is renamed and this is not, that clause fails and names both
 *  files. A duplication a guard watches is a different thing from one nobody
 *  knows about. */
const LANDING_NAME = "Where it stands";

function UpToLanding({ siteId }: { siteId: string }) {
  const [, query] = (window.location.hash || "").split("?");
  const cur = new URLSearchParams(query || "");
  const q = new URLSearchParams();
  for (const key of ["page", "run"]) {
    const v = cur.get(key);
    if (v) q.set(key, v);
  }
  const tail = q.toString();
  const href = `#/sites/${siteId}${tail ? `?${tail}` : ""}`;
  return (
    <a className="parts-up" href={href}
       onClick={(e) => {
         if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
         e.preventDefault();
         goto(href, { keepScope: false });
       }}
       aria-label={`${LANDING_NAME} — the screen these parts break down`}>
      <span aria-hidden="true">&uarr;</span>{" "}{LANDING_NAME}
    </a>
  );
}

export function PartSwitcher({ siteId, categories, current, pops = null }: {
  siteId: string; categories: Category[];
  /** The open part's key. Marked, not omitted: a switcher that hides where
   *  you are makes the reader count. */
  current: string;
  pops?: Populations | null;
}) {
  const unread = new Set(unreadParts(categories).map((c) => c.key));
  const list = useRef<HTMLUListElement>(null);
  // The rows this strip may spend are fewer than the rows 18 parts take at a
  // narrow width, so the open part can start below the fold of the strip's own
  // scroller - a switcher that opens with the reader's position out of sight.
  // `scrollTop` rather than `scrollIntoView`, deliberately: the element's own
  // method scrolls every ancestor including the document, and the tree has one
  // convention for moving the DOCUMENT (`{ block: "center" }`, no behaviour).
  // Moving a scroller's own offset is a different act and must not look like
  // that one.
  useEffect(() => {
    const el = list.current;
    const pill = el?.querySelector<HTMLElement>(".parts-open");
    if (!el || !pill) return;
    const mid = pill.offsetTop - (el.clientHeight - pill.offsetHeight) / 2;
    el.scrollTop = Math.max(0, mid);
  }, [current]);
  // And the part itself is brought to the reader, because a hash change is not
  // a scroll: pressing Images from inside Headings at scrollY 764 changed the
  // heading and left the viewport at 1145, which is the middle of a part the
  // reader had not read a word of. Only when the heading is out of sight -
  // someone who arrives at the top of a part is already looking at it, and
  // centring a heading that is on screen would scroll the chrome above it away
  // for nothing. `{ block: "center" }` with no behaviour is the tree's one
  // convention for moving the document
  // (`test_every_scroll_into_view_uses_the_convention_already_in_the_tree`).
  useEffect(() => {
    const h = document.querySelector<HTMLElement>(".part-h2");
    if (!h) return;
    const r = h.getBoundingClientRect();
    if (r.top >= 0 && r.bottom <= window.innerHeight) return;
    h.scrollIntoView({ block: "center" });
  }, [current]);
  return (
    <nav className="part-switch"
         aria-label="Every part — switch to another, or go up to the site">
      {/* First, and outside the list: a level up is not a sibling of the
          parts, and a reader scanning pills should not have to notice that
          one of them leaves the level (item 194). */}
      <UpToLanding siteId={siteId} />
      <ul className="cl-parts-list part-switch-list" ref={list}>
        {categories.map((c) => (
          <li key={c.key}>
            <PartLink siteId={siteId} c={c} pops={pops} unread={unread}
                      open={c.key === current} note={false} />
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The verb each next step is pressed as (item 168). "next: Triage" named a
 *  step and read as a status; this says what the click does. */
const ACTION_VERB: Record<string, string> = {
  "Precheck": "Run the precheck", "Audit": "Start an audit",
  "Analyses": "Open the catalogue", "Record": "Open the record",
  "Client report": "Build the client report",
};

/** The one primary action: the step the ribbon marks next, as a command with
 *  the count it will act on (item 168, channel ruling 20260917-0045). Blue in
 *  both modes (BK); absent where no step is next, rather than a primary that
 *  does nothing. Still an anchor: it was always a real link, and the complaint
 *  was the wording and the missing count, not the element. */
export function PrimaryAction({ step, count = null, ofTotal = null }: {
  step: { name: string; href: string } | null;
  count?: number | null;
  /** What `count` is out of, for the triage step: this audit's findings.
   *
   *  Without it the button read "· 880 not yet assessed" beside a lane reading
   *  "Outstanding 1740", one implicit subject over two populations - the run's
   *  findings and the record's - both bare (audit F5). On twenty22 they
   *  coincide at 32 by accident, which is how the pair survived review. */
  ofTotal?: number | null;
}) {
  if (!step) return null;
  const verb = ACTION_VERB[step.name] ?? `Open ${step.name.toLowerCase()}`;
  const triage = step.name === "Triage";
  return (
    <LinkButton primary className="bl-primary" href={step.href}>
      {verb}{count != null
        ? <span className="bl-count"> · {count}
            {/* The population, either way. `of this audit's 882` where some
                have been assessed, and the bare clause where none have - the
                case that needed it most, since "164 of this audit's 164" is
                arithmetic nobody asked for and "164 not yet assessed" beside
                "Outstanding in the record 167" was the defect. */}
            {triage && ofTotal != null && ofTotal !== count
              ? ` of this audit's ${ofTotal} not yet assessed`
              : triage ? " not yet assessed in this audit" : ""}</span>
        : null}
    </LinkButton>
  );
}
