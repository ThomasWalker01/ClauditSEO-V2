/**
 * Three states for "nothing here", in words, from one source (item 180,
 * pattern D of the 2026-09-17 UI audit).
 *
 * Accessibility said "Nothing to fix on this scope" on an audit that rendered
 * no page; Links and Speed said it under "8 checks not assessed - LNK did not
 * run"; Backlinks said "Nothing open here" with no key to measure anything;
 * Security's layers read "partial" at 0 of 9 assessed; Structured data passed
 * 13 checks on a page with no JSON-LD. Every one collapsed three different
 * answers into the one a reader wants:
 *
 *   clean                a check ran on this scope and found nothing;
 *   not measured         no check ran on this scope, and the sentence says why;
 *   cannot have findings the check does not fire on this scope by construction.
 *
 * The words are the registry's (`measure-*`), and `measureOf` is the one rule
 * that picks between them, so no screen draws a fourth word for the idea.
 */
import { entry } from "./glossary";

export type Measure = "clean" | "not-measured" | "cannot";

export const MEASURE_WORD: Record<Measure, string> = {
  clean: entry("measure-clean").word,
  "not-measured": entry("measure-not-measured").word,
  cannot: entry("measure-cannot").word,
};

/** Which of the three a scope with nothing open is.
 *
 *  `checks` are the part's automatic checks on this scope, `unmeasured` those
 *  this run did not measure with the reason, and `gate` the part's own verdict
 *  when it does not apply to the site at all. */
export function measureOf({ checks, unmeasured, gate = null, noCheckWhy }: {
  checks: string[];
  unmeasured: Map<string, string>;
  gate?: { state: string; reason: string } | null;
  /** Why no automatic check covers the part, where none does. */
  noCheckWhy?: string;
}): { state: Measure; why: string } {
  if (gate?.state === "na") return { state: "cannot", why: gate.reason };
  if (!checks.length) {
    return { state: "not-measured",
             why: noCheckWhy ?? "no automatic check covers this part, and no analysis has read it" };
  }
  const measured = checks.filter((c) => !unmeasured.has(c));
  if (!measured.length) {
    const reason = unmeasured.get(checks[0]) ?? "";
    return { state: "not-measured",
             why: reason.replace(/^(not collected yet|not assessed|held): /, "") || "this audit did not run its checks" };
  }
  return { state: "clean",
           why: `${measured.length} check${measured.length === 1 ? "" : "s"} ran and found nothing`
             + (measured.length < checks.length
               ? `; ${checks.length - measured.length} more not measured` : "") };
}

/** The line a scope with nothing open draws. */
export function MeasureLine({ state, why, className = "" }: {
  state: Measure; why: string; className?: string;
}) {
  return (
    <p className={`muted measure-line${className ? ` ${className}` : ""}`} data-measure={state}>
      <b className="measure-word">{MEASURE_WORD[state][0].toUpperCase()}{MEASURE_WORD[state].slice(1)}</b>
      {" "}— {why}.
    </p>
  );
}
