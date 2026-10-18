/** What a check costs to answer, and the filter built on it (brief v17
 *  steps AV1 and AV4).
 *
 *  Its own module because four things ask the question - the part page,
 *  the sidebar's badge, the Record's chips and the legend strip - and the
 *  obvious home beside the `Category` type is the one module that already
 *  imports the part page. A value crossing that edge would be a real
 *  import cycle; the only thing this module takes from `anatomy` is a
 *  type, which the build erases.
 */
import type { Category } from "./anatomy";

/** What a check costs to answer (brief v17 step AV1), from the payload.
 *
 *  `free` where the server says nothing: a check the app has never heard
 *  of is not a reason to tell an operator they will be charged for it,
 *  and the screen guessing "model" would put a price on work that is
 *  free. That is the error that costs someone money rather than a click.
 */
export function checkCost(costs: Record<string, string> | undefined,
                          check: string): string {
  const c = costs ?? {};
  const bare = check.split("/").pop() ?? check;
  // Item 219 (IP-01): content's model rows are STORED under `EXP:<brief>`
  // (`runs.contract_storage_dimension`), and the registry prices them as `CNT/<id>`.
  // The lookup tried the stored id and `ONP/`, missed both, and fell to
  // "free" - so every paid Content card sat under "Free checks · 163" and
  // "free only" showed them. A stored `EXP:` row is its check's dimension's.
  const priced = check.startsWith("EXP:") ? c[`CNT/${bare}`] : undefined;
  return c[check] ?? priced ?? c[`ONP/${bare}`] ?? "free";
}

/** The same question of one part. */
export const costOf = (part: Category, check: string): string =>
  checkCost(part.check_cost, check);

/** And of the whole payload, for the two readers that are not inside a
 *  part: the Record, whose rows are the site's rather than a section's,
 *  and anything counting across the sidebar. Later parts win ties, and
 *  there are none to win - a check belongs to one part. */
export const costsAcross = (cats: Category[]): Record<string, string> =>
  Object.assign({}, ...cats.map((c) => c.check_cost ?? {}));

/** The two answers `?cost=` may carry (brief v17 step AV4). Anything else
 *  in the address is no filter at all rather than an empty screen. */
export const COSTS = ["free", "model"];

/** What the address says the filter is. A value the app does not know is
 *  no filter rather than an empty screen: a truncated or hand-edited link
 *  should show everything, which is what this screen shows by default. */
export function costFromHash(): string {
  const q = new URLSearchParams((window.location.hash || "").split("?")[1] || "");
  const v = q.get("cost") || "";
  return COSTS.includes(v) ? v : "";
}
