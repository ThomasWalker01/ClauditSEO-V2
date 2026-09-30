/** Going somewhere, including going where you already are.
 *
 *  The app routes on the `hashchange` event alone — `App.tsx`'s `useHash` and
 *  `SiteDetailView`'s own listener both key on it — and **the browser does not
 *  fire `hashchange` when a hash is assigned the value it already has**. So a
 *  control that navigates to the pane the URL already names does nothing at
 *  all: no event, no re-render, no feedback.
 *
 *  That is not hypothetical. Two controls shipped dead:
 *
 *    - `read triage` on the client screen, whose handler assigned
 *      `#/sites/<id>?tab=analyses`;
 *    - `open analyses`, an anchor to the same URL — an anchor click to the
 *      current location is the same no-op, so the bug has two shapes and
 *      grepping for assignments alone would have found one of them.
 *
 *  Both were reported by the operator as "the button does nothing", which is
 *  exactly what it did.
 *
 *  Every navigation goes through here. A guard in
 *  `tests/test_navigation_goes_through_one_door.py` keeps it that way, because
 *  the failure is silent at the call site: a raw assignment looks correct, and
 *  is correct, right up until the target happens to be where you already are.
 */

/** The page a client view is scoped to, read from the address (brief v23
 *  step BK: scope is a mode, and a mode lives in the route).
 *
 *  It was React state in `useAnatomy`, so a page-scoped view could not be
 *  linked, did not survive a reload, and Back did nothing about it. The hash
 *  already carries the screen's smaller state (`?tab=`, `?cost=`), so this is
 *  that pattern rather than a new one.
 *
 *  Honoured only on the site it was chosen on: a `page=` carried onto another
 *  client's address names a URL that client does not have, so it is no scope
 *  rather than an empty screen - the same guarantee the old `{site, url}`
 *  pair gave by construction. */
export function pageScopeFromHash(siteId: string): string {
  const [path, query] = (window.location.hash || "").split("?");
  if (!siteId || path !== `#/sites/${siteId}`) return "";
  return new URLSearchParams(query || "").get("page") || "";
}

/** `hash` with the page scope set to `url`, or removed when `url` is empty.
 *  Removing it is the way back to site mode, so it is a navigation too and
 *  Back undoes it. */
export function withPageScope(hash: string, url: string): string {
  const [path, query] = hash.split("?");
  const q = new URLSearchParams(query || "");
  if (url) {
    q.set("page", url);
    // A narrow is a view of the site's population, and one page has none to
    // narrow (brief v25 step BP): choosing a page drops it, here, rather than
    // leaving two scopes to collide.
    for (const k of ["depth", "check", "template"]) q.delete(k);
  } else q.delete("page");
  const tail = q.toString();
  return tail ? `${path}?${tail}` : path;
}

/** Carry the current page scope onto a navigation that stays on the same
 *  client and says nothing about scope itself. Every pane link on the client
 *  screen (`?tab=history`, `?tab=all&state=fixed`) predates the scope being in
 *  the address; without this, opening a pane silently dropped the operator
 *  back into site mode, where before BK the chosen page followed them across
 *  every pane. A link that sets `page=` itself, or leaves the client, is left
 *  alone. */
function keepPageScope(next: string): string {
  const [curPath, curQuery] = (window.location.hash || "").split("?");
  const cur = new URLSearchParams(curQuery || "");
  if (!curPath.startsWith("#/sites/")) return next;
  const [path, query] = next.split("?");
  if (path !== curPath) return next;
  const q = new URLSearchParams(query || "");
  // The part in hand travels the same way (brief v24 step BM): it was React
  // state, so it followed the operator across panes, and moving it into the
  // address must not make every pane link drop it.
  let changed = false;
  for (const key of ["page", "part"]) {
    const v = cur.get(key);
    if (v && !q.has(key)) { q.set(key, v); changed = true; }
  }
  if (!changed) return next;
  return `${path}?${q.toString()}`;
}

/** The part in the address (brief v24 step BM): `?part=<key>`, on the site it
 *  names only, like the page scope. A lane row, the sidebar and the triage
 *  table all open a part by writing it, so Back closes it. */
export function partFromHash(siteId: string): string {
  const [path, query] = (window.location.hash || "").split("?");
  if (!siteId || path !== `#/sites/${siteId}`) return "";
  return new URLSearchParams(query || "").get("part") || "";
}

/** The Audits tab's history view (item 239 step 5): the one address that
 *  names an audit, `?view=audits&run=<id>`. A `run=` anywhere else is
 *  ignored - the site screen is the current view. */
export function historyRunFromHash(siteId: string): string {
  const [path, query] = (window.location.hash || "").split("?");
  if (!siteId || path !== `#/sites/${siteId}`) return "";
  const q = new URLSearchParams(query || "");
  return q.get("view") === "audits" ? q.get("run") || "" : "";
}

/** The history view's address for one audit of a site. */
export const historyHref = (siteId: string, runId: string) =>
  `#/sites/${siteId}?tab=all&view=audits&run=${encodeURIComponent(runId)}`;

/** The record's narrowing (item 207): `raised=` - the findings one audit
 *  raised - and `sev=` - a comma list of severities. Not `run=`: that key is
 *  the header's picked audit on every client tab, so an operator who pinned
 *  an audit and opened the Record carried it in and got a record silently
 *  narrowed to that audit (the channel, 20260924-0220-202). On the site they were written
 *  for only, like the page scope. They are how a figure that counted one
 *  audit's Critical and High opens exactly those rows rather than every
 *  audit's open findings of every severity. */
export function recordNarrowFromHash(siteId: string): { run: string; sev: string[] } {
  const [path, query] = (window.location.hash || "").split("?");
  if (!siteId || path !== `#/sites/${siteId}`) return { run: "", sev: [] };
  const q = new URLSearchParams(query || "");
  return { run: q.get("raised") || "",
           sev: (q.get("sev") || "").split(",").map((s) => s.trim()).filter(Boolean) };
}

/** The catalogue's narrowing (item 207): the parts the landing counts as not
 *  read, or the analyses it counts as not run. Anything else is no narrowing,
 *  not an empty list. */
export type CatalogueOnly = "" | "unread" | "not-run";
export function catalogueOnlyFromHash(siteId: string): CatalogueOnly {
  const [path, query] = (window.location.hash || "").split("?");
  if (!siteId || path !== `#/sites/${siteId}`) return "";
  const v = new URLSearchParams(query || "").get("only") || "";
  return v === "unread" || v === "not-run" ? v : "";
}

/** The current address without `keys`: the way out of a narrowing. A link,
 *  so Back puts the narrowing back. */
export function hashWithout(keys: string[]): string {
  const [path, query] = (window.location.hash || "").split("?");
  const q = new URLSearchParams(query || "");
  for (const k of keys) q.delete(k);
  const tail = q.toString();
  return tail ? `${path}?${tail}` : path;
}

/** `hash` with the part set to `key`, or removed when `key` is empty. */
export function withPart(hash: string, key: string): string {
  const [path, query] = hash.split("?");
  const q = new URLSearchParams(query || "");
  if (key) q.set("part", key);
  else q.delete("part");
  const tail = q.toString();
  return tail ? `${path}?${tail}` : path;
}

/** Navigate to `hash`, and make it observable even when nothing changed.
 *  `keepScope: false` is for the one caller that means to change the scope:
 *  the mode switch returning to the whole site. */
export function goto(hash: string, { keepScope = true } = {}): void {
  const raw = hash.startsWith("#") ? hash : `#${hash}`;
  const next = keepScope ? keepPageScope(raw) : raw;
  if (window.location.hash === next) {
    // Re-announce rather than re-assign. Assigning is the no-op; the listeners
    // read `window.location.hash` themselves and ignore the event's payload,
    // so an event carrying the unchanged URLs is honest — nothing moved, and
    // the screen still needs to act on being told to go here.
    window.dispatchEvent(new HashChangeEvent("hashchange", {
      oldURL: window.location.href,
      newURL: window.location.href,
    }));
    return;
  }
  window.location.hash = next;
}

/** An `onClick` for an anchor that should also work when it points at here.
 *
 *  The `href` stays on the element — it is what makes the control a link:
 *  middle-click, copy-address and the status bar all read it, and a `<button>`
 *  styled as a link would take those away. This only intercepts the plain
 *  left-click that the browser would otherwise turn into a no-op.
 */
export function goHandler(hash: string) {
  return (e: React.MouseEvent) => {
    // Leave modified clicks alone: ctrl/cmd/shift/middle are the user asking
    // for a new tab or window, and hijacking them is worse than the bug.
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey
        || e.shiftKey || e.altKey) return;
    e.preventDefault();
    goto(hash);
  };
}
