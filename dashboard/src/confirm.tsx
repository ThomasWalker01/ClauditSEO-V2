/**
 * One confirmation, for every control that spends or cannot be undone (item
 * 178, patterns A and B of the 2026-09-17 UI audit), and one dialog behaviour
 * for every modal (item 181, pattern G).
 *
 * The audit found spending one press from rest in a dozen places - the scan
 * cells, the part pages' analysis pill, the crawl on Tools, the batch link -
 * and nineteen deletes on Admin, per-finding withdraw and the note cross with
 * no second step, drawn in the free action's green. Each had grown its own
 * answer or none: `window.confirm` in four places, an inline row in one, a
 * modal in two. This is the one answer.
 *
 * **What a confirmation says.** A spend names what runs, where, and its price -
 * or says in words that there is no price, never an empty slot. A delete names
 * what goes and what depends on it. Both from the caller, because only the
 * caller knows; the shape and the words around them are here, and the words
 * are the registry's (item 166).
 *
 * **How a dialog behaves** (`useDialog`). Focus moves into it, Tab and
 * Shift+Tab stay inside it, Escape closes it, and closing returns focus to the
 * control that opened it. The confirm opens on Cancel, not on the action: a
 * dialog that opens on the spending button is one Enter from the spend.
 */
import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { entry } from "./glossary";
import { Pill } from "./pill";

/** Registered words (item 166): the spending and danger vocabularies. */
export const SPEND_WORDS = {
  unpriced: entry("spend-unpriced").word,
  checking: entry("spend-checking").word,
} as const;
export const DANGER_WORDS = {
  undone: entry("danger-undone").word,
} as const;

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), '
  + 'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** The shared modal behaviour (item 181): trap, Escape, and focus returned to
 *  the trigger. `initial` is where focus lands; the dialog box itself when
 *  absent. */
export function useDialog(ref: RefObject<HTMLElement | null>, onClose: () => void,
                          initial?: RefObject<HTMLElement | null>) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const box = ref.current;
    (initial?.current ?? box)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close.current(); return; }
      if (e.key !== "Tab" || !box) return;
      const items = [...box.querySelectorAll<HTMLElement>(FOCUSABLE)]
        .filter((el) => el.checkVisibility?.() ?? true);
      if (!items.length) { e.preventDefault(); box.focus(); return; }
      const first = items[0], last = items[items.length - 1];
      const at = document.activeElement;
      if (e.shiftKey && (at === first || at === box || !box.contains(at))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && (at === last || !box.contains(at))) {
        e.preventDefault(); first.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      // Back to where the operator was, if it is still there to go back to.
      if (trigger && trigger.isConnected) trigger.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

export type ConfirmAsk = {
  /** `spend` spends money; `danger` cannot be undone. */
  kind: "spend" | "danger";
  /** The question, as a heading: "Run 4 analyses on acme.com.au?" */
  title: string;
  /** What it acts on and what depends on it, in sentences. */
  body: ReactNode;
  /** A spend's price in words: "about USD 0.40", or `null` for none known,
   *  which is said as the registry's unpriced word rather than left blank. */
  price?: string | null;
  /** The confirming button's label: "Run 4", "Remove the Moz key". */
  action: string;
  /** A danger that can be put back (a withdrawn finding reopens) says how in
   *  its body instead of "cannot be undone". */
  undone?: boolean;
};

/** A pending confirmation, and the dialog that answers it. `ask` resolves true
 *  on the action and false on Cancel, Escape or the backdrop. */
export function useConfirm(): [ReactNode, (a: ConfirmAsk) => Promise<boolean>] {
  const [pending, setPending] = useState<(ConfirmAsk & { resolve: (ok: boolean) => void }) | null>(null);
  const ask = useCallback((a: ConfirmAsk) => new Promise<boolean>((resolve) => {
    setPending({ ...a, resolve });
  }), []);
  const answer = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
  };
  const node = pending ? <ConfirmDialog ask={pending} onAnswer={answer} /> : null;
  return [node, ask];
}

let seq = 0;

export function ConfirmDialog({ ask, onAnswer }: {
  ask: ConfirmAsk; onAnswer: (ok: boolean) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [id] = useState(() => `confirm-${++seq}`);
  useDialog(box, () => onAnswer(false), cancel);
  return (
    <div className="modal-backdrop" role="presentation"
         onClick={(e) => { if (e.target === e.currentTarget) onAnswer(false); }}>
      <div className={`modal confirm-dialog confirm-${ask.kind}`} role="alertdialog" aria-modal="true"
           tabIndex={-1} ref={box} aria-labelledby={`${id}-h`} aria-describedby={`${id}-b`}>
        <div className="modal-head">
          <h3 id={`${id}-h`}>{ask.title}</h3>
        </div>
        <div id={`${id}-b`} className="confirm-body">
          {ask.body}
          {ask.kind === "spend" && (
            <p className="confirm-price">
              {ask.price ? <>Price: <strong>{ask.price}</strong></> : <>Price: {SPEND_WORDS.unpriced}</>}
            </p>
          )}
          {ask.kind === "danger" && ask.undone !== false && (
            <p className="confirm-undone">This {DANGER_WORDS.undone}.</p>
          )}
        </div>
        <div className="modal-actions">
          <Pill as="button" type="button" tone="nav" ref={cancel} onClick={() => onAnswer(false)}>
            Cancel
          </Pill>
          <Pill as="button" type="button" className="confirm-go"
                tone={ask.kind === "spend" ? "action-paid" : "action-danger"}
                onClick={() => onAnswer(true)}>
            {ask.action}
          </Pill>
        </div>
      </div>
    </div>
  );
}
