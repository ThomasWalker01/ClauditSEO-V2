/**
 * The pieces the client screen and the tools screen both use.
 *
 * They had the same skeleton already — a two-column header, a rail of grouped
 * things down the left, a report panel on the right — and diverged only in
 * their styling. Copying the client screen's new look across would have given
 * two implementations of one design, which is how this codebase previously
 * ended up with two fix loops and two vocabularies for "attempted". So the
 * shared parts live here and both screens import them.
 *
 * What is deliberately NOT shared: what each screen counts. Current shows a
 * site's standing position across every audit; Tools shows what one audit has
 * and has not been analysed with. Identical-looking panels that mean different
 * things is its own failure, which is why the pane header carries the scope.
 */
import { Working } from "./working";
import { NOT_READ } from "./glossary";
import { SecondaryButton } from "./buttons";
import { ReactNode } from "react";
import { SpendMark } from "./components";
import { goHandler } from "./nav";
import { Pill } from "./pill";
import { SpendButton, SpendTarget } from "./spend";

/** Whether anything has looked at this thing yet.
 *
 *  Four states, not three. Current has read / running / never, but a tool can
 *  also be unable to run at all — no provider key, or a required input the
 *  crawl cannot supply — and folding that into "never run" would say the
 *  operator simply has not got round to it. That is the same lie as
 *  "link-gap runs in every audit": a status that describes the world wrongly
 *  because the vocabulary was too small.
 */
export type LookState = "read" | "live" | "none" | "blocked";

export const LOOK_TITLE: Record<LookState, string> = {
  read: "Has run — open it to read",
  live: "Running now",
  none: "Nothing has looked at this yet",
  blocked: "Cannot run: it needs a provider key or an input that is not set",
};

/** The dot. Carries a screen-reader word as well as a colour, so the state is
 *  never conveyed by hue alone (WCAG 1.4.1). */
export function LookDot({ state, label }: { state: LookState; label?: string }) {
  // `NOT_READ`, not "not analysed" (audit F14): this dot's screen-reader
  // word was a fourth spelling of the state item 180 unified.
  const word = { read: "analysed", live: "analysis running",
                 none: NOT_READ, blocked: "blocked" }[state];
  return (
    <span className={`cat-dot cat-${state}`} title={label ?? LOOK_TITLE[state]}>
      <span className="sr-only">{word}</span>
    </span>
  );
}

/** The legend, wherever the dots are read. */
export function LookLegend({ blocked = false, words }: {
  /** Only shown where a thing can actually be blocked. */
  blocked?: boolean;
  /** Per-screen wording — the dots mean the same, the nouns differ. */
  words?: Partial<Record<LookState, string>>;
}) {
  const say = (k: LookState, fallback: string) => words?.[k] ?? fallback;
  const rows: [LookState, string][] = [
    ["read", say("read", "an analysis has run against this — open it to read")],
    ["live", say("live", "analysis running now")],
    ["none", say("none", "nothing has analysed it")],
  ];
  if (blocked) {
    rows.push(["blocked",
               say("blocked", "cannot run — it needs a key or an input")]);
  }
  return (
    <div className="dot-legend">
      {rows.map(([state, text]) => (
        <span key={state}>
          <i className={`cat-dot cat-${state}`} aria-hidden="true" />
          {text}
        </span>
      ))}
    </div>
  );
}

/** One of the two panes at the top of a screen. */
export function Pane({ act, title, aside, children }: {
  /** The action pane, which carries the analysis purple. */
  act?: boolean;
  title: string;
  /** What this pane is scoped to — a date, a tier, a step. */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={`cur-pane${act ? " cur-act" : ""}`}>
      <div className="cur-head">
        <h2 className="head-label">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Panes({ children }: { children: ReactNode }) {
  return <div className="cur-grid">{children}</div>;
}

/** Headline figures: big, coloured by meaning, each with its own label.
 *
 *  `tone` is what the number means, never how it looks — so a screen cannot
 *  decide that its "outstanding" should be green today. */
export type Figure = {
  value: ReactNode;
  label: ReactNode;
  tone?: "warn" | "good" | "danger" | "quiet";
  title?: string;
  /** Where the things this counts are. The number is the control (F-11):
   *  a quantity the operator cannot reach is a claim taken on trust.
   *  Absent where the list would be empty — no control onto nothing. */
  href?: string;
  /** The link's name for a reader who meets it out of its row: the
   *  number alone is not one. */
  name?: string;
};

export function Figures({ items }: { items: Figure[] }) {
  return (
    <dl className="cur-figs">
      {items.map((f, i) => (
        <div key={i}>
          {/* Term before description, as a definition list requires; the
              figure is drawn above its label by CSS order (audit F-24). */}
          <dt>{f.label}</dt>
          <dd className={`fig${f.tone ? ` fig-${f.tone}` : ""}`} title={f.title}>
            {f.href
              ? <a className="fig-link" href={f.href} onClick={goHandler(f.href)}
                   aria-label={f.name}>{f.value}</a>
              : f.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** A report's header: what it is, the way to run it again, and the way out.
 *
 *  "Run it again" sits here rather than in a list above because this is where
 *  the reason to appears — an older brief opens by saying its prose was not
 *  retained, and the control to obey that has to be within reach of the
 *  sentence asking for it. */
export function ReportHead({ title, onRerun, rerunning, rerunTitle, onClose, rerunPrice = null }: {
  title: ReactNode;
  onRerun?: () => void;
  rerunning?: boolean;
  rerunTitle?: string;
  onClose?: () => void;
  /** Item 178: the re-run's price, `null` for none known. */
  rerunPrice?: number | null;
}) {
  return (
    <div className="modal-head">
      <h4>{title}</h4>
      {onRerun && (
        /* UX-66. Stable caption, state on `aria-busy`, words in the region
           below — the convention `views.tsx`'s `ReportView` states in full. */
        <SpendButton busy={rerunning} price={rerunPrice} onSpend={onRerun}
                     confirm={{ title: "Run this analysis again?",
                                body: <><SpendTarget />
                                  <p>{rerunTitle ?? "It replaces the stored report."}</p></>,
                                action: "Run it again" }}>
          run it again
        </SpendButton>
      )}
      {onClose && (
        <SecondaryButton onClick={onClose}>close</SecondaryButton>
      )}
      {/* Mounted unconditionally, and outside the `onRerun` guard for the
          same reason: a region inserted in the same render as its text gives
          assistive technology nothing to observe a change against. */}
      <span className="muted" role="status" aria-live="polite">
        {rerunning && <Working>Running it again…</Working>}
      </span>
    </div>
  );
}
