/** The Analyses pane: the catalogue, the issue browser with its rail and
 *  drawer.
 *
 *  Brief step 8 (CQ-02): the pane's body, moved verbatim out of
 *  `SiteDetailView`, with the one component only it rendered. */
import { FindingState } from "./api";
import { AnatomyScreen, AnatomyView } from "./anatomy";

export function AnalysePane({ siteId, anat, states, selected, onSelect, rerunAsk,
                             onRunAll, onRerun }: {
  siteId: string; anat: AnatomyScreen; states?: FindingState[];
  /** The part in hand is the screen's (brief v4 Item 3a). */
  selected: string; onSelect: (key: string) => void;
  rerunAsk: { key: string; n: number } | null;
  /** Run the part's briefs that are not run (brief v4 Item 3f). */
  onRunAll: (part: string) => void;
  /** The shop header's re-run glyph (brief v24 step BO). */
  onRerun?: (key: string) => void;
}) {
  return (
    <>
        <AnatomyView key={siteId} siteId={siteId} a={anat} states={states}
                     selected={selected} onSelect={onSelect} rerunAsk={rerunAsk}
                     onRunAll={onRunAll} onRerun={onRerun} />
        {/* The Internal link suggestions block stood here from brief v5
            step T until brief v17 step AW, which closes it. It was a
            result about internal links with no check behind it, no record
            row and no place in a report; the Links part page is where a
            suggestion belongs, beside the eight checks that raise the
            question and the fix cards that answer it. */}
    </>
  );
}

// ---- run detail ------------------------------------------------------------

