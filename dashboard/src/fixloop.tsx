/**
 * The fix loop, once, for every screen that shows findings.
 *
 * The rule the whole thing rests on: a tick is a claim, a crawl is a
 * measurement. Ticking never marks a finding fixed — only a crawl that looks
 * at the page again may change the record. That is what makes ticking free of
 * consequence and safe to do in bulk, and why a row reads "awaiting a look"
 * rather than "done".
 *
 * It lived on the Current tab while The record grew a second implementation:
 * a "mark fix attempted" button, its own wording ("attempted, still present"
 * against "still there"), and no verify beside it, so a mark made there could
 * not be acted on. Deleting the second copy fixed the conflict and lost the
 * capability. Sharing the first fixes both — the same mechanism, the same
 * words, wherever findings are listed.
 */
import { Working } from "./working";
import { SecondaryButton } from "./buttons";
import { ReactNode, useEffect, useState } from "react";
import { RunStatus, api, completedAudits } from "./api";
import { Pill } from "./pill";

/** The least a row must carry to take part. */
export type Markable = {
  fingerprint: string;
  state: string;
  summary: string;
  /** "deterministic" | "model-judgement". A brief's finding is judged by
   *  re-running the brief, so a crawl cannot verify it. */
  source?: string;
  /** Whether a crawl could look again at this finding, decided on the server
   *  by `runs.names_a_page`. Required, not optional: both payloads that reach
   *  a tick carry it, and `tsc` naming a third call site that does not is the
   *  point — an optional field silently absent is how the tick came to be
   *  offered for findings the verify route refuses. */
  names_a_page: boolean;
  attempted_at?: string | null;
  attempt_note?: string | null;
};

/** What a verification decided about a marked finding — four answers, not
 *  two. `undecided` is a narrow run refusing to judge a finding that names no
 *  page: it did not clear and it is NOT "still there", because nothing looked
 *  at it. Reporting it as still there sent the operator to inspect a template
 *  on the strength of a check the run declined to make (WF-66, report 053).
 *
 *  `unchanged` is the fourth, added for WF-100: the page WAS read, the run did
 *  not re-raise the finding, and it already stood `fixed` before this run. It
 *  used to be counted as still there, because the server derived that count by
 *  subtraction — so the operator was sent to inspect a template on the
 *  strength of a crawl that had not re-found anything.
 *
 *  A union rather than a boolean beside the pair, so `tsc` names every site
 *  that has to handle each case instead of letting one fall through to the
 *  existing else-branch.
 *
 *  **Which word a finding gets is decided on the server and is not re-derived
 *  here.** This module used to compute it from `decided` and `cleared`, which
 *  is one rule written twice in two languages — and the Python half was the
 *  one that was wrong. `WORD` below is a spelling map and nothing more. */
export type Outcome = Record<string,
  "cleared" | "still" | "undecided" | "unchanged">;

/** Server word to screen word. A rename table, not a decision. */
const WORD: Record<string, Outcome[string]> = {
  cleared: "cleared",
  still_present: "still",
  not_checked: "undecided",
  unchanged: "unchanged",
};

/** Which run is allowed to have judged a mark.
 *
 *  A verification looks at only the handful of pages it was asked about, so
 *  its timestamp cannot settle a mark it never covered. An audit looks at
 *  everything, which is why it is the only judge — the same rule the server
 *  applies when it computes `last_audit` for the Current tab, restated here
 *  because the record builds its own from the run list.
 *
 *  The two screens disagreed until this existed: a mark made at 10:42 and a
 *  verification of a *different* finding at 11:48 made the record read "still
 *  there" while Current, correctly, still read "awaiting a look".
 *
 *  `started_at`, not `finished_at`, to match the server exactly. */
export function lastJudgingRun(
    runs?: { status: RunStatus; kind: string; started_at: string | null }[],
) {
  return completedAudits(runs)[0]?.started_at;
}

export function useFixLoop(siteId: string, lastAudit?: string | null,
                           onChanged?: () => void) {
  const [marked, setMarked] = useState<Set<string>>(new Set());
  const [outcome, setOutcome] = useState<Outcome>({});
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** A mark made before the last audit has already been judged.
   *
   *  "Awaiting a look" was shown for every attempt however old, so a fix
   *  marked three weeks and five audits ago still claimed to be waiting for
   *  its first look when it had been checked repeatedly and was still there.
   *  The audit is the judge; once one has run, the answer is in. */
  const judged = (f: Markable) =>
    Boolean(f.attempted_at && lastAudit && f.attempted_at < lastAudit);

  /** Ticks come from the server, not from browser memory. `attempted_at` was
   *  always stored and always survived a reload; the checkbox did not, so a
   *  refresh left the chip in place and took the verify button away with it. */
  const seed = (findings: Markable[]) =>
    setMarked((cur) => {
      const next = new Set(cur);   // union: a tick a second old is not undone
      for (const f of findings) if (f.attempted_at) next.add(f.fingerprint);
      return next;
    });

  const mark = (f: Markable, on: boolean) => {
    setMarked((cur) => {
      const next = new Set(cur);
      if (on) next.add(f.fingerprint); else next.delete(f.fingerprint);
      return next;
    });
    // WF-84: both ways. Until this had an `else`, unticking reached nothing —
    // `seed()` above unions the server's `attempted_at` back in on every load,
    // so the tick the operator had just removed came back on the next render
    // and the deliverable went on printing `_(fix attempted)_` beside it.
    if (on) {
      api.post(`/api/sites/${siteId}/states/${f.fingerprint}/attempt`,
               { note: "" })
        .catch(() => { /* the local mark stands; the next audit judges it */ });
    } else {
      api.del(`/api/sites/${siteId}/states/${f.fingerprint}/attempt`)
        .catch(() => { /* the local untick stands; the next load re-seeds */ });
    }
  };

  /** Re-crawl only the pages behind these findings.
   *
   *  A few pages and no model tokens, so it runs in the foreground and
   *  answers immediately — a verification that finished silently would leave
   *  the question it was run to settle.
   *
   *  "A few" is the server's word now, not this comment's: the route refuses
   *  **422** above `runs.VERIFY_PAGE_CAP` pages, and that refusal reaches the
   *  operator through `setError` and the `ErrorNote` beside every call site.
   *  `MarkBar` withholds the button where it can already tell the batch is
   *  over, so the 422 is the backstop for the case a screen cannot see — an
   *  anatomy page count that is a floor. */
  const verify = async (fingerprints: string[]) => {
    if (!fingerprints.length) return;
    setVerifying(true);
    setError(null);
    try {
      const res = await api.post<{ outcomes: { fingerprint: string;
                                               cleared: boolean;
                                               decided: boolean;
                                               outcome: string }[] }>(
        `/api/sites/${siteId}/verify`, { fingerprints });
      const next: Outcome = {};
      for (const o of res.outcomes) {
        // Read, not re-derived. `cleared` and `decided` are still on the
        // payload and are still true; they are no longer enough to tell the
        // four cases apart, and the branch that tried is WF-100.
        const word = WORD[o.outcome];
        if (word) next[o.fingerprint] = word;
      }
      setOutcome((cur) => ({ ...cur, ...next }));
      // Cleared ones drop their tick; the rest keep it so another go is one
      // click away. Marks elsewhere are untouched.
      setMarked((cur) => {
        const keep = new Set(cur);
        for (const fp of fingerprints) if (next[fp] === "cleared") keep.delete(fp);
        return keep;
      });
      onChanged?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setVerifying(false);
    }
  };

  /** WF-84. The button reading `clear these marks` cleared browser memory
   *  and nothing else, so the marks were back on the next load.
   *
   *  One request per mark rather than a batch route: the marks a screen holds
   *  are already the ones behind its verify button, which the server caps, and
   *  a second bulk endpoint would be a second place to get the cap wrong. Each
   *  failure is swallowed the same way `mark` swallows its own — the local
   *  untick stands and the next `seed()` tells the truth about what landed. */
  const clear = (fingerprints: string[]) => {
    setMarked((cur) => {
      const next = new Set(cur);
      for (const fp of fingerprints) next.delete(fp);
      return next;
    });
    for (const fp of fingerprints) {
      api.del(`/api/sites/${siteId}/states/${fp}/attempt`)
        .catch(() => { /* see above: the next load re-seeds from the server */ });
    }
  };

  return { marked, outcome, verifying, error, judged, seed, mark, verify,
           clear, setOutcome };
}

/** Seeds the loop from a list whenever that list changes. */
export function useSeed(seed: (f: Markable[]) => void, findings: Markable[],
                       dep: unknown) {
  useEffect(() => { seed(findings); /* eslint-disable-next-line */ }, [dep]);
}

/** The fix-loop column's header.
 *
 *  Here rather than at each table because it was not here: both screens
 *  carried `<th className="fix-col"><span className="sr-only">Mark as
 *  fixed</span></th>`, copied byte for byte, announced to a screen reader
 *  and drawn for nobody. A sighted operator got an unlabelled checkbox and
 *  no way to learn that ticking it is free, reversible, and how you ask for
 *  a re-check — so the capability read as missing and was asked for again.
 *
 *  The column header carries the name; each tick's own `aria-label` still
 *  carries which finding it belongs to. Exported as a `<th>` and not as a
 *  string so a third table cannot reintroduce the divergence.
 */
export function FixCol() {
  return <th className="fix-col">Fixed?</th>;
}


/** Why there is no tick, said in text.
 *
 *  Each refusal used to be an em dash with the reason in a `title`. The
 *  product had already settled that argument for its own tab strip, one file
 *  over: "hover text alone fails the reader who is not using a mouse and the
 *  one who does not think to hover". A control that declines to act owes the
 *  same disclosure as one that acts, and this is the only column where the
 *  operator can ask why nothing happened.
 */
function NoTick({ why }: { why: string }) {
  return <span className="muted no-tick">{why}</span>;
}


/** The tick, or the reason there is none. Three refusals, all readable.
 *
 *  The third exists because the first two did not cover the case the server
 *  actually refuses. A site-level finding — no llms.txt, contrast not
 *  assessed, no backlink data — names no page, and
 *  `POST /api/sites/{id}/verify` answers **422** for a batch of them: "these
 *  findings name no page to re-fetch — they are site-level, and are judged by
 *  a full audit". The tick was offered anyway, so the operator's mark bought
 *  an error message. Five of the twelve findings a default audit raises are
 *  in that state.
 *
 *  `names_a_page` is the server's own answer rather than a count read here:
 *  the anatomy payload's `pages` counts entries that need not be URLs and its
 *  `urls` is truncated to ten, so a re-derivation would be a second
 *  implementation of a rule that already has an owner.
 */
export function FixTick({ f, marked, onMark }: {
  f: Markable; marked: Set<string>; onMark: (f: Markable, on: boolean) => void;
}) {
  if (f.state !== "open" && f.state !== "regressed") {
    return <NoTick why={`only an open finding can be marked — this one is ${f.state}`} />;
  }
  if (f.source && f.source !== "deterministic") {
    return <NoTick why="raised by an analysis — re-run that analysis to judge it, not a crawl" />;
  }
  if (!f.names_a_page) {
    return <NoTick why="site-wide — it names no page to re-fetch, so a full audit judges it, not a re-check" />;
  }
  return (
    <input type="checkbox" className="fix-chk"
           checked={marked.has(f.fingerprint)}
           aria-label={`mark fixed: ${f.summary.slice(0, 60)}`}
           onChange={(e) => onMark(f, e.target.checked)} />
  );
}

/** What a state means, once, for every screen that names one.
 *
 *  UX-43. The meaning of `withdrawn` existed only in two `title` attributes —
 *  `FixState` below and the Current pane's excluded line
 *  (`anatomy.tsx`) — and `candidate` in three, spelled three different ways
 *  ("It opens if a second run confirms it", "it opens if it appears again",
 *  "opens if it appears again"). Three spellings of one meaning is the
 *  evidence that nothing owned it; the provenance invariant is the reason it
 *  may not live in a `title` at all.
 *
 *  These are the three states a finding can be in that take it *out* of the
 *  count in front of the operator, which is why they are the ones that owe an
 *  explanation: a number that silently drops a row is a number nobody can
 *  reconcile. The states that stay in the count — `open`, `regressed`,
 *  `fixed` — are named by their own chip and explain themselves.
 *
 *  Exported because the guard reads it: `test_dashboard_a11y.py` parses the
 *  keys and sentences out of this file and asserts no `title` under
 *  `dashboard/src` carries one. The population comes from the owner rather
 *  than from a list in the test, which is the mistake `UNBROKEN_TOKEN_CLASSES`
 *  and `NARROW_RUN_PHRASE` are both still making.
 */
export const STATE_MEANING: Record<string, string> = {
  "withdrawn": "The audit that raised this could not see the site, so the finding was never true. Not a fix — nothing was repaired. A later audit that does see it will reopen it.",
  "candidate": "Seen once. Model output varies run to run, so a single sighting is not yet treated as a fact — it opens if it appears again.",
  "accepted-risk": "Excluded by your own decision; never reinstated automatically.",
};


/** A state's meaning, in text a keyboard reaches. */
export function StateNote({ state }: { state: string }) {
  const why = STATE_MEANING[state];
  return why ? <span className="state-why">{why}</span> : null;
}


/** Every verdict a verification can return, each with its chip.
 *
 *  A `Record` keyed on the union rather than an if-chain, so `tsc` names this
 *  site when a fourth verdict is added. The chain it replaces had no such
 *  property: a new member fell silently through to the state-based branches
 *  below and rendered as `open`, which is how "not checked" would have looked
 *  identical to "nobody has verified anything yet".
 *
 *  `undecided` is a narrow run declining to judge a finding that names no
 *  page. Its text is rendered, not a `title` — the provenance invariant is
 *  that a stated limitation appears in text a keyboard reaches, and the
 *  limitation IS the message here. `cleared` has no chip: a cleared finding's
 *  stored state is already `fixed` and the branch below draws it.
 */
const VERDICT_CHIP: Record<Outcome[string], ReactNode> = {
  cleared: null,
  still: (
    <span className="state st-still"
          title="The verification fetched this page and the finding was
                 still there — the change did not reach it">still there</span>
  ),
  undecided: <span className="state st-undecided">not checked</span>,
  unchanged: (
    <Pill tone="state-fixed"
          title="The verification fetched this page and did not find this
                 finding — it was already fixed before this audit">still fixed
    </Pill>
  ),
};

/** One vocabulary for what is true of a finding right now.
 *  (`FixState`, not `FindingState` — that name is already the row type the
 *  API returns, and two of them in one import list is a coin toss.) */
export function FixState({ f, marked, outcome, judged }: {
  f: Markable; marked: Set<string>; outcome: Outcome;
  judged: (f: Markable) => boolean;
}) {
  const said = outcome[f.fingerprint];
  if (said && said !== "cleared") {
    return VERDICT_CHIP[said];
  }
  if (f.state === "fixed") {
    return <Pill tone="state-fixed">fixed</Pill>;
  }
  if (f.state === "accepted-risk") {
    return <Pill tone="state-accepted">accepted</Pill>;
  }
  // The chip and the sentence, not the chip and a `title`. Both states below
  // take the finding out of the count above it, so the number cannot be
  // reconciled without them — which is what makes the meaning a limitation on
  // a displayed value rather than a nicety (UX-43).
  if (f.state === "withdrawn") {
    return (
      <>
        <Pill tone="state-withdrawn">withdrawn</Pill>
        <StateNote state="withdrawn" />
      </>
    );
  }
  if (f.state === "candidate") {
    return (
      <>
        <span className="muted">seen once</span>
        <StateNote state="candidate" />
      </>
    );
  }
  if (judged(f)) {
    return (
      <span className="state st-still"
            title={`Marked fixed on ${f.attempted_at?.slice(0, 10)}, but an
                    audit has run since and it is still open — the change did
                    not take`}>still there</span>
    );
  }
  if (marked.has(f.fingerprint) || f.attempted_at) {
    return (
      <span className="state st-marked"
            title="Marked as fixed. It stays open until a crawl looks at this
                   page again — only that can clear it">awaiting a look</span>
    );
  }
  // After the mark, not before it. Regressed used to win outright, so ticking
  // a regressed row changed nothing on screen and read as a dead checkbox.
  if (f.state === "regressed") {
    return <Pill tone="state-regressed">regressed</Pill>;
  }
  return <span className="muted">open</span>;
}

/** The bar above a list: what is marked in it, and how to settle it. */
export function MarkBar({ here, pages, pagesExact = true, pageCap, elsewhere,
                         outcome, verifying, onVerify, onClear, extra }: {
  /** Fingerprints marked in THIS list — the bar counts what it sits above. */
  here: string[];
  /** Distinct pages those findings sit on, which is what verifying actually
   *  re-crawls. Passed in because a fingerprint does not carry its URLs: the
   *  caller has the rows, so the caller counts. Distinct, not a sum — two
   *  findings on one page are one page fetched. */
  pages: number;
  /** Whether `pages` is the count or a floor. The anatomy payload truncates
   *  each finding's URL list at ten while sending the true total beside it,
   *  so a caller reading the list alone undercounts and one reading the
   *  total cannot dedupe across findings. Saying "at least" is the honest
   *  reading of a number that is known to be a lower bound; claiming it
   *  exactly is how the bar came to say 10 above a column reading 12. */
  /** The most pages one verification may re-crawl, from the payload rather
   *  than from a constant here: `runs.VERIFY_PAGE_CAP` is the owner and both
   *  payloads behind the two call sites carry it, because a rule spelled in
   *  Python and again in TypeScript drifts — CQ-82's shape.
   *
   *  `undefined` means "the payload did not say", which is not the same as
   *  "no ceiling": the bar then offers, and the server answers 422 in a
   *  sentence `ErrorNote` renders. That is the same path a page count that is
   *  a floor already takes, so it needs no second behaviour. */
  pageCap?: number;
  pagesExact?: boolean;
  elsewhere: number;
  outcome: Outcome;
  verifying: boolean;
  onVerify: () => void;
  onClear: () => void;
  extra?: ReactNode;
}) {
  const mine = new Set(here);
  const cleared = Object.entries(outcome)
    .filter(([fp, o]) => o === "cleared" && mine.has(fp)).length;
  const still = Object.entries(outcome)
    .filter(([fp, o]) => o === "still" && mine.has(fp)).length;
  const undecided = Object.entries(outcome)
    .filter(([fp, o]) => o === "undecided" && mine.has(fp)).length;
  // WF-100. These were inside `still` until the server could tell them
  // apart: the page was read, the finding was not re-raised, and it already
  // stood fixed. Counted separately rather than dropped, because "the run
  // looked and it is still gone" is the answer to what was asked.
  const unchanged = Object.entries(outcome)
    .filter(([fp, o]) => o === "unchanged" && mine.has(fp)).length;
  const verified = cleared + still + undecided + unchanged > 0;
  if (!here.length && !verified) return null;

  /** Both counts, each named.
   *
   *  The bar counted findings while the row beside it counted pages, and it
   *  named neither: "verify these 1 now" sat above a row reading 11 in a
   *  Pages column. Both were true — one finding was marked, and it did span
   *  eleven pages — but nothing said which unit the 1 was, and "these 1" is
   *  not grammatical, so there was no clue to read. The sentence that would
   *  have settled it lives in the button's `title` and needs a hover. */
  const n = (count: number, noun: string) =>
    `${count} ${noun}${count === 1 ? "" : "s"}`;
  const scope = `${n(here.length, "finding")} across `
    + `${pagesExact ? "" : "at least "}${n(pages, "page")}`;

  /** Whether this batch is one the verify route would refuse on size.
   *
   *  Compared against `pages` rather than `here.length` because the route
   *  counts pages: a finding is not a page, and the whole finding is that one
   *  tick on a site-wide check was a several-hundred-page blocking request.
   *
   *  A floor above the cap is certainly above it, so `pagesExact` does not
   *  soften this; a floor below it may still be over, and that case reaches
   *  the server and comes back as rendered text. Claiming a total the screen
   *  cannot know is how this bar came to say 10 above a column reading 12. */
  const over = pageCap !== undefined && pages > pageCap;

  return (
    // `done` is "everything asked about came back clear". A run that
    // declined to judge one of them is not done, so `undecided` blocks it for
    // the same reason `still` does.
    <div className={`mark-bar${verified && !still && !undecided ? " done" : ""}`}>
      {/* One statement, not two. Reporting "2 still there" beside "2 marked
          fixed" reads as two separate facts about the same two findings. */}
      {verified ? (
        <strong>
          {cleared > 0 && `${cleared} cleared`}
          {cleared > 0 && still > 0 && " · "}
          {still > 0 && `${still} still there`}
          {(cleared > 0 || still > 0) && unchanged > 0 && " · "}
          {unchanged > 0 && `${unchanged} still fixed`}
          {(cleared > 0 || still > 0 || unchanged > 0) && undecided > 0 && " · "}
          {undecided > 0 && `${undecided} not checked`}
        </strong>
      ) : (
        <strong>{n(here.length, "finding")} marked fixed here</strong>
      )}
      <span className="muted">
        {/* The undecided case is stated first and on its own terms. It used
            to fall into the `still` branch, which asserts a page was fetched
            — for a finding no page was fetched for.

            WF-69 widened what this branch covers, so the sentence no longer
            states the reason. `decided` used to mean "the finding names a
            page"; it now means "the run READ a page this finding names",
            which is `_apply_states`' own rule — so the branch holds two
            reasons: the finding named no page, or it named one the run could
            not read (a 503, a timeout, a host that stopped resolving). The
            old sentence asserted the first for both, and would have told the
            operator "one names no page" about a finding naming a page that
            had just returned 503.

            Both reasons, named, rather than one asserted. The server knows
            which applies to each finding and does not send it; adding that
            is a payload decision, and a sentence that is true of both costs
            nothing while it is unmade. */}
        {undecided > 0
          ? "this audit did not look at "
            + (undecided === 1 ? "it" : "them")
            + (undecided === 1
               ? " — it names no page, or the page it names could not be read"
               : " — they name no page, or the pages they name could not be "
                 + "read")
          : still > 0
          ? "the page was fetched and the finding was still on it — check the "
            + "template rather than the page"
          : unchanged > 0
          ? "the crawl read those pages and did not find "
            + (unchanged === 1 ? "it" : "them")
            + " — nothing moved, because nothing had come back"
          : verified ? "the crawl looked and they were gone"
          : "still open until those pages are looked at again"}
      </span>
      {/* What a verification costs, and when it will not be offered at all.
          Both in rendered text, which is the half of this finding that
          reports 013 to 038 kept naming on its own: the button's only cost
          statement was `title="…Seconds, and no model tokens."`, so a
          keyboard operator and a screen reader got a control with no price on
          it, and the price was wrong besides — it was however many pages the
          marked findings happened to name.

          Withheld rather than disabled where the batch is over the cap. A
          disabled control with a reason beside it is still a control the
          operator will try to press; and `FixTick` was cured of exactly this
          one round ago, by not offering what the server would refuse.

          `.muted` on the refusal, the same class the outcome sentence above
          uses, and no class of its own: a name reachable by neither a rule
          nor a selector is what `PAINTED_BY_NOTHING` exists to record, and
          one invented to hold a guard off is worse than none. */}
      {here.length > 0 && (over ? (
        <span className="muted">
          Too many pages to look at while you wait:{" "}
          {pagesExact ? "" : "at least "}{n(pages, "page")} against a limit of{" "}
          {pageCap}. Untick some, or run a full audit — that one runs in the
          background and reports its progress.
        </span>
      ) : (
        <>
          {/* UX-66. Stable caption, state on `aria-busy`, words in the
              unconditionally-mounted region below — the convention
              `views.tsx`'s `ReportView` states in full. */}
          <SecondaryButton className="mark-verify" disabled={verifying}
                  aria-busy={verifying} onClick={onVerify}>
            {verified ? `look again at ${scope}` : `verify ${scope} now`}
          </SecondaryButton>
          <span className="muted" role="status" aria-live="polite">
            {verifying && <Working>{`Looking at ${scope}…`}</Working>}
          </span>
          <span className="muted">
            Re-crawls only those pages and runs only their dimensions. It runs
            while you wait, and spends no model tokens.
          </span>
        </>
      ))}
      {here.length > 0 && (
        <SecondaryButton disabled={verifying} onClick={onClear}>
          clear these marks
        </SecondaryButton>
      )}
      {/* Marks outside this list are not its business to count, but ignoring
          them silently would hide work in progress. Deliberately vague about
          where: on Current that is another category, on the record another
          page of results or behind a filter. */}
      {elsewhere > 0 && (
        <span className="muted">{elsewhere} more marked elsewhere on this site</span>
      )}
      {extra}
    </div>
  );
}
