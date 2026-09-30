/**
 * How bad the worst thing in a group is, and the order that answers it.
 *
 * Its own module because two screens need it and they already import each
 * other: `anatomy.tsx` takes values from `client_lanes.tsx`, so the strip
 * importing this back out of `anatomy` would close a runtime cycle. A type
 * import is erased; a value import is an edge, and a cycle that breaks breaks
 * at module init.
 */

/** Worst first. The record's own order, and the one the severity tones are
 *  registered against. */
export const SEV_RANK: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3, info: 4,
};

/** The count pill takes the colour of the worst thing inside it, so scanning
 *  the tree finds the severe categories before the merely large ones.
 *
 *  Unused between brief v24 step BO - which retired the sidebar whose pills
 *  carried it - and item 195, when the operator asked for the colour back:
 *  "Counts should get a severity colour as every other measured item does."
 *  The strip that replaced the sidebar had never carried it across, and this
 *  function sat here with its reason written down and nothing calling it.
 *
 *  `info` when the group is empty, which is the quiet end: a part with
 *  nothing in it is not severe, and the caller decides whether to paint at
 *  all. */
/** Structural rather than `Finding`: that type is declared in `anatomy.tsx`
 *  and not exported, and this rule reads exactly one of its fields. Widening
 *  another module's surface to name a type you use one property of is a
 *  bigger change than the thing it buys. */
export function worst(findings: { severity: string }[]): string {
  return findings.reduce(
    (acc, f) => (SEV_RANK[f.severity] < SEV_RANK[acc] ? f.severity : acc), "info");
}
