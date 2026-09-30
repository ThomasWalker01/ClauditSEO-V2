/**
 * The client report's hold, drawn one way wherever the report is acted on (item
 * 178, UI audit 08-3).
 *
 * The landing held "Build the client report" while three other ways to the same
 * page stayed live: the nav, the strip's Client report step reading "done" in
 * green, and Generate on arrival. The hold neither stopped the journey nor said
 * how to lift it. Now each surface reads the same answer - the server's
 * `client_report_hold`, the function the generator and the plan route refuse on
 * - and draws it with `ReportHeld`, in the registry's word, with the way out
 * beside it: triage, where the unassessed findings are.
 *
 * Not in the nav, since 2026-09-18: see the note where it used to be, in
 * `App.tsx`. The surfaces are the ones that act on the report - the landing's
 * button, the strip's Deliver chapter, and Generate - and not the chrome that
 * merely points at it.
 */
import { useFetch } from "./api";
import { entry } from "./glossary";
import { goHandler } from "./nav";

export type ReportHold = {
  run_id: string; held: boolean; count: number;
  critical: number; high: number; reason: string | null;
};

/** The registered word (item 166). */
export const REPORT_HELD_WORD: string = entry("report-held").word;

export function useReportHold(runId: string | null | undefined) {
  return useFetch<ReportHold>(runId ? `/api/runs/${runId}/client-report-hold` : null);
}

/** The mark's words, in one place: the strip's Deliver chapter builds the
 *  same sentence from `REPORT_HELD_WORD` and had its own copy of the tail.
 *
 *  "N to assess" was one word - assess - over a different population from the
 *  primary action's "N not yet assessed" beside it: 7 against 32 on twenty22,
 *  the first being the Critical and High subset and the second the whole audit.
 *  Naming the severities is what the sentence under the headline already does
 *  ("Client report held: 7 Critical or High not yet assessed"). */
export const heldWords = (count: number): string =>
  `${REPORT_HELD_WORD} · ${count} Critical or High to assess`;

/** Where the hold's count opens (items 202, 207): the record narrowed to
 *  exactly what the hold counts. Since item 239 step 7 that is the site's
 *  running record - its open Critical and High, whichever audit last
 *  measured them (`open_severe`) - so the link carries no audit narrowing;
 *  `raised=` belongs to the history view. One writing, because three places
 *  say "held" - the landing's lane, the strip's Deliver step and Reports. */
export function heldRecordHref(siteId: string): string {
  return `#/sites/${siteId}?tab=all&state=open&sev=critical,high`;
}

/** "held for assessment · 3 Critical or High to assess", and the way to lift
 *  it. */
export function ReportHeld({ count, siteId, id }: {
  count: number; siteId: string; id?: string;
}) {
  // The record, on what is open (item 196). This pointed at triage, which is
  // the third place that did - the hold is "not yet assessed", only
  // `set_state` changes that, and triage wrote no state. A link that cannot
  // lift the hold it is attached to is worse than no link: it reads as the
  // way out and spends instead.
  const record = heldRecordHref(siteId);
  return (
    <span className="report-held" id={id} role="note">
      {heldWords(count)}
      {" "}<a className="report-held-go" href={record}
              onClick={goHandler(record)}>Open the record</a>
    </span>
  );
}
