/** The legend strip and the panes it keys (brief v4 Item 3d).
 *
 *  Moved out of `sidebar.tsx` when the sidebar was retired (brief v24 step
 *  BO): its jobs went to the landing's lanes, the shop's part headers, the
 *  four destinations, Audit's precheck block and the Record's part select
 *  (channel rulings of 2026-09-15). The strip stays, and its words no longer
 *  describe a list that is not on the screen.
 */
import { SecondaryButton } from "./buttons";
import { LookLegend } from "./panels";
import { money } from "./components";
import { AnatomyScreen } from "./anatomy";
import { notRunCount } from "./catalogue";
import { Pill } from "./pill";

export type SidebarPane = "landing" | "precheck" | "history" | "findings" | "all";
// `triage` left this union at item 197: item 196 retired the ranking
// pane, `paneFor` aliases the word to `history`, and the branch that
// drew its key went with it. `precheck` is dead by the same two
// mechanisms and is NOT removed here - it is outside item 197, and
// the clause in `test_the_legend_keys_what_is_on_the_screen.py`
// records it by name so the next dead branch cannot hide behind it.

/** A page as an operator recognises it: its path. */
const pathOf = (u: string) => { try { return new URL(u).pathname || "/"; } catch { return u; } };

/** The legend strip, above the content (brief v4 Item 3d): only the symbols in play on this pane, per the brief's
 *  table. Before anything has counted the site there is nothing to read,
 *  and the strip says so.
 *
 *  On Analyse it also carries the catalogue's control, "All briefs · N not
 *  run"; Item 3e makes the catalogue a drawer and 3f puts run-all beside
 *  it. */
export function LegendStrip({ pane, a, catalogueOpen = false, onCatalogue,
                              listShowing = false }: {
  pane: SidebarPane;
  a: AnatomyScreen;
  catalogueOpen?: boolean;
  onCatalogue?: () => void;
  /** Whether the analyses list is on the screen at all (item 197). It is
   *  the same list in two places - open in the drawer, or standing as the
   *  shop when no part is - and the keys below belong to the list, not to
   *  either of its mounts. The caller knows which; this does not. */
  listShowing?: boolean;
}) {
  const { data, precheck, lanes, page, setPage } = a;
  const counted = Boolean(precheck) || Boolean(data?.current?.last_audit);
  const triage = lanes?.triage ?? null;
  // The catalogue's own count (brief v12 step AN): triage ranks the rest
  // and is not a row there, so counting it here made this strip and the
  // drawer's control disagree by one.
  const notRun = notRunCount(lanes);
  /** The narrow, said on every pane while it is on (brief v12 step AM):
   *  the one filter every block below reads, with its clear beside it. */
  const narrowed = page ? (
    <span className="legend-narrow">
      narrowed to <code>{pathOf(page)}</code>
      <SecondaryButton className="legend-narrow-clear"
              aria-label={`clear the narrow to ${pathOf(page)}`} onClick={() => setPage("")}>×</SecondaryButton>
    </span>
  ) : null;
  /** `free only` (brief v17 step AV4), on every pane because the thing
   *  it filters - what an audit found for nothing against what a model
   *  was paid to read - is on every pane. Pressed again it clears; the
   *  Record offers `analysis` as well, and pressing `free only` there
   *  swaps rather than stacks, because one address carries one answer. */
  const costChip = counted ? (
    <button type="button" className="chip cost-chip"
            aria-pressed={a.cost === "free"}
            title="Show only the checks that cost nothing to run. Analysis keeps its heading and its count."
            onClick={() => a.setCost(a.cost === "free" ? "" : "free")}>
      free only
    </button>
  ) : null;
  let body: JSX.Element;
  if (!counted) {
    body = <span className="muted">Legend fills in as steps run.</span>;
  } else if (pane === "precheck") {
    body = (<>
      <b>Precheck</b>
      <span>pages published and what changed since the last check</span>
      <span className="key"><i className="anat-n n-info">n</i> what the precheck itself can say</span>
    </>);
  } else if (pane === "history") {
    body = (<>
      <b>Counts</b>
      <span>open findings per part, on the landing and in the shop</span>
      <span className="key"><i className="anat-n n-high">n</i> open</span>
      <span className="key"><i className="anat-n n-info">n</i> info</span>
      <span className="key"><i className="anat-n n-zero">0</i> nothing open</span>
    </>);
  } else if (pane === "findings") {
    body = (<>
      {onCatalogue && (
        <span className="legend-catalogue">
          <SecondaryButton className="anat-catalogue-open"
                  aria-expanded={catalogueOpen} onClick={onCatalogue}>
            {catalogueOpen ? "hide the catalogue" : "open the catalogue"}
          </SecondaryButton>
          <span className="muted">
            All analyses
            {notRun !== null ? ` · ${notRun} not run` : ""}
            {lanes?.outstanding_cost != null ? ` · ${money(lanes.outstanding_cost)} for all` : ""}
          </span>
        </span>
      )}
      {/* Item 197: these key the analyses list, so they are emitted with
          it. `LookDot` is drawn at catalogue.tsx:487 and :549, `anat-rank`
          at :447, `anat-rerun` at :507 - all four inside `CatalogueList`,
          and nowhere else in the app. That list is on the screen in two
          cases and no others: the drawer is open, or no part is open and
          the shop is standing. Outside it a part's state is a count and the
          word "unread" (items 174 and 186), never a dot.

          The drawer is shut by default (views.tsx:699), so inside a part
          these five entries described symbols that were not on the screen -
          the exact thing the header above says this strip stopped doing.
          The operator, reading a part page: "these status dots don't seem
          to have a purpose here any more."

          The catalogue control and `free only` stay outside the condition:
          they are the closed-state strip, and both act on what is in front
          of the reader. */}
      {listShowing && (<>
        <LookLegend words={{
          read: "read — an analysis has run against this part",
          live: "running now",
          none: "automatic checks only — a 0 counts only what the audit's own checks saw",
        }} />
        {triage && <span className="key"><i className="anat-rank">1</i> triage rank</span>}
        <span className="key"><i className="anat-rerun legend-rerun" aria-hidden="true">↻</i> re-check this part</span>
      </>)}
    </>);
  } else {
    body = (<>
      <b>Filter</b>
      <span>pick a part to narrow the record; its chip clears it</span>
      <span className="muted">counts are open findings in the current filter</span>
    </>);
  }
  return (
    <div className="legend-strip anat-legend" data-pane={pane}>
      {/* The strip's own words first, then the one control that acts on
          every pane below it. Leading with the chip put `free only`
          in front of `Counts` and made the strip read as a filter
          bar rather than as a key. */}
      {narrowed}{body}{costChip}
    </div>
  );
}
