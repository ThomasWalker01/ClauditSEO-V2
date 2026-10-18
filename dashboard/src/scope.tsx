/** The one audit picker, and the one place it is labelled.
 *
 *  Brief step 1 (`_plans/site-screen-reorg-brief-2026-09-03.md`, CQ-01 and
 *  UI-01). The labelled picker was rendered in four places - the Analyses pane,
 *  the Triage pane, the analyses tab's own bar and Admin's Workbench - each
 *  a label around the same `ContextControls`. The brief's diagnosis was four
 *  implementations; the tree's answer is one implementation mounted four
 *  times, and the fix is the same either way: one mount, above the panes,
 *  and every pane reads the pick.
 *
 *  **Not a second context.** The brief sketches an `AuditScope` context with
 *  `runId` and `setRunId`. `SelectionProvider` (`selection.tsx`) already is
 *  that context for the whole app - it holds the run, reads `?run=` off the
 *  address, and keeps the pick across a refresh - so `useAuditScope` reads
 *  it rather than standing a second provider beside it for the same value
 *  to drift between. Persistence in the address is unchanged: a route may
 *  name `?run=`, and the picker does not write one.
 */
import { ReactNode } from "react";
import { ContextControls, useSelection } from "./selection";

/** The audit every run-scoped reader follows, and the setter the bar uses. */
export function useAuditScope() {
  const { runId, setRunId, runs, runsError, refreshRuns } = useSelection();
  return { runId, setRunId, runs, runsError, refreshRuns };
}

/** The bar: three columns on one row (brief v8 step X, after v4 Item 1's
 *  two). `stands`, the Standing column: the site's standing counts under a
 *  pill naming the run they are computed from. `pages`, the Pages column:
 *  the record's count, the published count, the picker's run's crawl, and
 *  the page filter under them. `.scope-pick`, the Reading audit column: the
 *  label - whose `title` is the one sentence saying what the pick scopes,
 *  no longer rendered inline - the select, and the alert row beneath it,
 *  which is empty rather than absent so the bar keeps one height from site
 *  to site. `.run-scope` is the class the rendered tests select the picker
 *  by; there is one on a screen. A caller with nothing standing (Admin's
 *  workbench) gets the picker column alone. */
export function AuditScopeBar({ note, stands, pages, children, mode, line, lanes, band }: {
  note: string; stands?: ReactNode; pages?: ReactNode; children?: ReactNode;
  /** The client view's landing state (brief v23 step BL): the state sentence
   *  and the one primary action, on a top line with the picker at its right.
   *  With `lanes`, the bar is that line, the three lanes as its three
   *  columns, and the context band beneath; `stands` and `pages` are the old
   *  columns and are not drawn. */
  line?: ReactNode;
  lanes?: ReactNode;
  band?: ReactNode;
  /** The client view's scope mode (brief v23 step BK). Stamped as
   *  `data-mode` so the mode hue reaches the bar's own furniture - its
   *  underline and the context band inside it - and nothing else. Admin's
   *  workbench has no page scope and passes none. */
  mode?: "site" | "page";
}) {
  if (line !== undefined) {
    // `.run-scope` stays the outer element and `.scope-pick` the picker's own
    // wrapper, so every rendered test that finds the picker by those still
    // does; `.scope-alert` stays beneath it, empty rather than absent.
    // A grid rather than three stacked rows. Stacked - line, lanes, band - the
    // bar measured 250 px at 1568 wide against a part pane that must start
    // within 400 px (`test_the_rail_is_a_strip`, not to be loosened), so the
    // picker and the context band share a right-hand column beside the
    // sentence and the lanes instead of each taking a full-width row.
    return (
      <div className="run-scope run-scope-lanes" data-mode={mode}>
        <div className="scope-state">{line}</div>
        {/* The lanes left the bar for the body at brief v24 step BM; the
            slot stays for a caller that still wants them in a bar. */}
        {lanes !== undefined && <div className="scope-lanes">{lanes}</div>}
        <div className="scope-side">
          <div className="scope-pick">
            <span className="sel-lbl" title={note}>Reading audit</span>
            <ContextControls stacked />
            <div className="scope-alert">{children}</div>
          </div>
          {band}
        </div>
      </div>
    );
  }
  return (
    <div className={`run-scope${stands === undefined ? " run-scope-pick-only" : ""}`}
         data-mode={mode}>
      {stands !== undefined && <div className="scope-stands">{stands}</div>}
      {pages !== undefined && <div className="scope-pages">{pages}</div>}
      <div className="scope-pick">
        <span className="sel-lbl" title={note}>Reading audit</span>
        <ContextControls stacked />
        <div className="scope-alert">{children}</div>
      </div>
    </div>
  );
}
