/**
 * A running sweep, held outside the component that started it.
 *
 * "Run all" is a loop in the browser: it POSTs one brief, waits, POSTs the
 * next. An async closure does not stop when the component that created it
 * unmounts, so leaving the Tools screen mid-sweep left the loop running and
 * spending — while every trace of it went with the component. The marks
 * vanished, the "stop after this brief" button vanished, and coming back
 * showed a screen that believed nothing was happening.
 *
 * The operator saw the marks disappear and reasonably read it as "the sweep
 * stopped". It had not. The work outliving the view is the correct half; the
 * state and the stop control not outliving it with the work is the bug, so
 * they live here instead.
 *
 * Deliberately module-level rather than a context: the sweep is one thing in
 * one tab, and a provider high enough to survive every route is a provider
 * that re-renders the whole app whenever a brief finishes.
 */

export type SweepState =
  "queued" | "running" | "done" | "failed" | "needs_input" | "skipped";

export type Sweep = {
  /** The loop is between briefs or inside one. */
  active: boolean;
  /** Stop was pressed; the brief in flight finishes and then it ends. */
  stopping: boolean;
  /** Which audit it is running against — a sweep belongs to one run, and
   *  showing its marks after switching client is the same mistake as the
   *  page filter that survived a site change. */
  runId: string | null;
  marks: Record<string, SweepState>;
  /** What did not run, reported once the loop ends. */
  error: string | null;
};

export const EMPTY_SWEEP: Sweep = { active: false, stopping: false, runId: null,
                       marks: {}, error: null };

let snapshot: Sweep = EMPTY_SWEEP;
const listeners = new Set<() => void>();

/** A new object every time, because `useSyncExternalStore` compares by
 *  identity — mutating in place would leave every subscriber unaware. */
function commit(next: Partial<Sweep>) {
  snapshot = { ...snapshot, ...next };
  listeners.forEach((l) => l());
}

export const sweepStore = {
  subscribe(l: () => void) {
    listeners.add(l);
    return () => { listeners.delete(l); };
  },
  get(): Sweep {
    return snapshot;
  },

  /** Marks for a run that is not the one being looked at are not this
   *  screen's marks. Returns the empty sweep rather than another audit's. */
  forRun(runId: string | null): Sweep {
    return snapshot.runId && snapshot.runId === runId ? snapshot : EMPTY_SWEEP;
  },

  start(runId: string, ids: string[]) {
    commit({
      active: true, stopping: false, runId, error: null,
      marks: Object.fromEntries(ids.map((id) => [id, "queued" as SweepState])),
    });
  },
  mark(id: string, state: SweepState) {
    commit({ marks: { ...snapshot.marks, [id]: state } });
  },
  requestStop() {
    commit({ stopping: true });
  },
  /** Read by the loop each iteration; it is the loop, not the view, that
   *  decides to end. */
  stopRequested(): boolean {
    return snapshot.stopping;
  },
  finish(error: string | null) {
    commit({ active: false, stopping: false, error });
  },
  /** After the operator has read the failure list. */
  clearError() {
    commit({ error: null });
  },
};
