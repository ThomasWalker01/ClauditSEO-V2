/** The operator's three answers to a finding that waits for them (items 237
 *  and 250): Confirm, Accept, Withdraw.
 *
 *  One component for every screen that shows a "to confirm" row - the part
 *  page's cards, the Record, the page dossier - so the words and what each
 *  writes cannot drift. A second paid run of the same model is not
 *  confirmation, so the product asks once, here, rather than charging for a
 *  re-run.
 *
 *  `withdrawOnly` (item 249): a row the automatic checks no longer see is
 *  offered the one answer that retires it without a paid re-run. */
import { useState } from "react";
import { api } from "./api";
import { SecondaryButton } from "./buttons";
import { entry } from "./glossary";

/** The state's word, where a candidate is drawn (item 250): "to confirm"
 *  where it waits for the operator, "seen once" where the automatic checks
 *  may still confirm it. Never the engine's `candidate`. The registry's
 *  words (item 166). */
export const candidateWord = (toConfirm: boolean | null | undefined) =>
  entry(toConfirm ? "to-confirm" : "seen-once").word;

/** What a legend adds where a screen draws "to confirm" rows: the state and
 *  its three answers. */
export const TO_CONFIRM_LEGEND = ["to-confirm", "confirm", "accept", "withdraw"];

/** The three answers in one sentence, where they are offered. */
export const CONFIRM_SAYS = "Confirm opens it as a fault; Accept keeps it as a risk you live with; "
  + "Withdraw takes it back.";

export function ConfirmControls({ fingerprints, siteId, onStateChanged, withdrawOnly = false,
                                 subject = null, explain = true }: {
  fingerprints: string[]; siteId: string; onStateChanged?: () => void;
  withdrawOnly?: boolean;
  /** What the answer is about, as "<check> on <page>" (item 267, row 9): each
   *  button's name says it, so a screen reader moving through four cards'
   *  buttons does not hear "Confirm, Accept, Withdraw" four times over. */
  subject?: string | null;
  /** Whether this control says what the three answers do. A page drawing
   *  many cards says it once above them instead (item 266, row 5). */
  explain?: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = async (state: string) => {
    setBusy(state); setErr(null);
    try {
      for (const fp of fingerprints) {
        await api.post(`/api/sites/${siteId}/states/${fp}`, { state });
      }
      onStateChanged?.();
    } catch (e) {
      setErr(`could not set it: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };
  const held = (state: string) => (busy && busy !== state ? "another answer is being saved" : null);
  // "Confirm: Article without an author, /seo/" (item 270, row 15).
  const named = (verb: string) => (subject ? `${verb}: ${subject}` : undefined);
  return (
    <div className="fix-confirm">
      {!withdrawOnly && <>
        <SecondaryButton className="fix-confirm-open" title={entry("confirm").full} busy={busy === "open"} why={held("open")}
                         label={named(entry("confirm").word)}
                         onClick={() => set("open")}>{entry("confirm").word}</SecondaryButton>
        <SecondaryButton className="fix-confirm-accept" title={entry("accept").full} busy={busy === "accepted-risk"}
                         why={held("accepted-risk")} label={named(entry("accept").word)}
                         onClick={() => set("accepted-risk")}>{entry("accept").word}</SecondaryButton>
      </>}
      <SecondaryButton className="fix-confirm-withdraw" title={entry("withdraw").full} busy={busy === "withdrawn"}
                       why={held("withdrawn")} label={named(entry("withdraw").word)}
                       onClick={() => set("withdrawn")}>{entry("withdraw").word}</SecondaryButton>
      <span className="muted" role="status">{err ?? ""}</span>
      {/* Item 267 (row 9): what each answer does, once, beside the three. */}
      {!withdrawOnly && explain && (
        <p className="muted fix-meta">{CONFIRM_SAYS}</p>
      )}
    </div>
  );
}
