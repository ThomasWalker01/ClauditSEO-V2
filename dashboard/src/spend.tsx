/**
 * The two controls whose press is not free to take back (item 178, UI audit
 * patterns A and B): one that spends money, and one that cannot be undone.
 *
 * **Spend.** The price is on the control, in words - a figure, or the
 * registry's "no estimate yet", never an empty slot. Until the data it acts on
 * belongs to the current selection it is held, `aria-disabled` and still
 * focusable, with the reason in visible text beside it rather than in a
 * `title`. The press asks first: what runs, where, and the price.
 *
 * **Danger.** The destructive tone, not the free action's green. The press
 * asks first, naming what goes and what depends on it.
 *
 * Both hold the same way. A native `disabled` drops the control out of the tab
 * order and leaves its reason to a tooltip, which is how "no analysis writes to
 * this part" reached mouse users only (05-2, 06-8).
 */
import { useId, type ReactNode } from "react";
import { SpendMark, money } from "./components";
import { SPEND_WORDS, useConfirm, type ConfirmAsk } from "./confirm";
import { Pill } from "./pill";
import { host, runShortLabel, useSelection } from "./selection";

/** A price as a spend control says it: a figure, or the registry's word.
 *  `undefined` is "not read yet" and says so. */
export function priceWords(usd: number | null | undefined): string {
  if (usd === undefined) return SPEND_WORDS.checking;
  if (usd === null) return SPEND_WORDS.unpriced;
  return `~${money(usd)}`;
}

type Held = {
  /** Why it cannot be pressed now, in words, or `null` when it can. Drawn
   *  beside the control. */
  why?: string | null;
  /** Something is already running from it: `aria-busy`, and held. */
  busy?: boolean;
  className?: string;
  children: ReactNode;
};

export function SpendButton({ price, why = null, busy = false, className = "", children,
                             confirm, onSpend, showPrice = true, title }: Held & {
  /** What the press does, for a table whose verbs each say so. */
  title?: string;
  /** USD, `null` for no estimate, `undefined` while the estimate is being read
   *  - which also holds the control, since a spend is not offered unpriced
   *  while its price is on the way. */
  price: number | null | undefined;
  /** What the confirmation says. `title` is the question; `body` names what
   *  runs, on which site and audit, over how many pages. */
  confirm: Omit<ConfirmAsk, "kind" | "price">;
  onSpend: () => void | Promise<void>;
  /** Off where the label already carries the price its own way. */
  showPrice?: boolean;
}) {
  const [dialog, ask] = useConfirm();
  const whyId = useId();
  const reason = why ?? (price === undefined ? SPEND_WORDS.checking : null);
  const held = busy || Boolean(reason);
  return (
    <>
      <Pill as="button" type="button" tone="action-paid"
            className={`btn btn-spend spend-btn${className ? ` ${className}` : ""}`} title={title}
            aria-disabled={held || undefined} aria-busy={busy || undefined}
            aria-describedby={why ? whyId : undefined}
            onClick={async (e) => {
              e.preventDefault();
              if (held) return;
              const ok = await ask({ ...confirm, kind: "spend",
                                     price: price == null ? null : `about ${money(price)}` });
              if (ok) await onSpend();
            }}>
        <SpendMark />{children}
        {showPrice && <span className="spend-price"> · {priceWords(price)}</span>}
      </Pill>
      {/* The label already says "checking the price"; only a reason of the
          caller's own is drawn beside it. */}
      {why && <span id={whyId} className="muted spend-why">{why}</span>}
      {dialog}
    </>
  );
}

export function DangerButton({ why = null, busy = false, className = "", children,
                              confirm, onConfirm, label, title }: Held & {
  title?: string;
  /** The accessible name, where the visible label is a mark ("✕") or a verb
   *  repeated on every row ("remove"). */
  label?: string;
  /** `title`: "Remove the Moz key?"; `body`: what goes and what depends on it;
   *  `action`: the confirming label. */
  confirm: Omit<ConfirmAsk, "kind" | "price">;
  onConfirm: () => void | Promise<void>;
}) {
  const [dialog, ask] = useConfirm();
  const whyId = useId();
  const held = busy || Boolean(why);
  return (
    <>
      <Pill as="button" type="button" tone="action-danger"
            className={`btn btn-danger danger-btn${className ? ` ${className}` : ""}`} title={title}
            aria-label={label}
            aria-disabled={held || undefined} aria-busy={busy || undefined}
            aria-describedby={why ? whyId : undefined}
            onClick={async (e) => {
              e.preventDefault();
              if (held) return;
              if (await ask({ ...confirm, kind: "danger" })) await onConfirm();
            }}>
        {children}
      </Pill>
      {why && <span id={whyId} className="muted danger-why">{why}</span>}
      {dialog}
    </>
  );
}

/** Where a spend lands, for its confirmation: the site and the audit in the
 *  bar, and how many pages it reads. From the selection, so a confirmation
 *  cannot name a site the screen has moved off. */
export function SpendTarget({ pages = null, page = null, runId: given }: {
  pages?: number | null; page?: string | null;
  /** The audit it runs against where that is not the bar's pick - the run
   *  page's own audit. */
  runId?: string;
}) {
  const { site, runs, runId: picked } = useSelection();
  const runId = given ?? picked;
  const run = runs.find((r) => r.id === runId) ?? null;
  return (
    <p className="confirm-target">
      On <strong>{site ? host(site.domain) : "the selected site"}</strong>
      {run ? <>, reading audit <strong>{runShortLabel(run)}</strong>
        {" "}of {(run.finished_at || run.started_at).slice(0, 10)}</>
        : runId ? <>, reading audit <strong>{runId.slice(0, 8)}</strong></> : null}
      {page ? <>, for <strong>{page}</strong></>
        : pages != null ? <>, over <strong>{pages} page{pages === 1 ? "" : "s"}</strong></> : null}.
    </p>
  );
}
