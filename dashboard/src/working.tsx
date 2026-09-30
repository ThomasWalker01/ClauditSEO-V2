/** Item 204: what an action in flight says while it runs.
 *
 *  The house pattern holds (UX-66): the button's caption never changes, its
 *  state is on `aria-busy`, and the words go in a `role="status"` region that
 *  was mounted before it had anything to say. What that pattern did not do was
 *  make the words look live. They were drawn `.muted`, the same ink and size as
 *  the provenance line beside them, and the button itself went dashed and grey
 *  - which is also exactly how a button held for a reason looks (item 178).
 *  Nothing on the screen told working from waiting-to-be-allowed.
 *
 *  So the busy words are wrapped here, inside the region that already exists:
 *  the region's element, its `role` and its mounting do not move, and every
 *  guard that reads them from source still reads the same thing. Mounting this
 *  IS the start of the wait - callers write `busy && <Working>…</Working>` -
 *  so no call site keeps a start time of its own.
 */
import { useEffect, useState, type ReactNode } from "react";

/** A press that answers inside this does not need a clock; a count that shows
 *  "1 s" and vanishes is noise, not information. */
export const ELAPSED_AFTER_SECONDS = 3;

/** Whole seconds since the calling component mounted. */
export function useElapsed(): number {
  const [since] = useState(() => Date.now());
  const [now, setNow] = useState(since);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return Math.floor((now - since) / 1000);
}

export function Working({ children }: { children: ReactNode }) {
  const secs = useElapsed();
  return (
    <span className="working">
      {children}
      {/* Hidden from assistive technology: this sits inside a polite live
          region, and a figure that changes every second would be announced
          every second. The words were announced once, when they arrived;
          the count is for the eye. */}
      <span className="working-secs" aria-hidden="true">
        {secs >= ELAPSED_AFTER_SECONDS ? ` · ${secs} s` : ""}
      </span>
    </span>
  );
}
