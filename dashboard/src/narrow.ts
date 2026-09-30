/** A narrow is in the address, like scope (brief v25 step BP).
 *
 *    ?depth=N        pages at crawl depth N       Crawl
 *    ?check=<id>     rows raised by one check      Indexability
 *    ?template=<p>   pages under one URL pattern   URLs, Speed
 *
 *  Set by pressing a control in a part's site picture, cleared by pressing it
 *  again, kept across a reload and undone by Back, because the setter
 *  navigates and `hashchange` re-reads - a pasted link and a press are the
 *  same event. One narrow at a time: setting one drops the others. A narrow
 *  inside page mode is meaningless, and `withPageScope` drops it when a page
 *  is chosen.
 */
import { goto } from "./nav";
import { pathKey } from "./population";

export type NarrowKind = "depth" | "check" | "template";
export type Narrow = { kind: NarrowKind; value: string } | null;
export const NARROW_KINDS: readonly NarrowKind[] = ["depth", "check", "template"];

export function narrowFromHash(): Narrow {
  const q = new URLSearchParams((window.location.hash || "").split("?")[1] || "");
  for (const kind of NARROW_KINDS) {
    const value = q.get(kind);
    if (value) return { kind, value };
  }
  return null;
}

export function setNarrowInHash(kind: NarrowKind, value: string | null): void {
  const [path, query] = (window.location.hash || "").split("?");
  const q = new URLSearchParams(query || "");
  for (const k of NARROW_KINDS) q.delete(k);
  if (value !== null && value !== "") q.set(kind, value);
  const tail = q.toString();
  goto(tail ? `${path}?${tail}` : path, { keepScope: false });
}

/** A page predicate keyed the way 155 keys a page: `pathKey`, so `/x` and
 *  `/x/` are one page, and a stored URL on another host spelling still
 *  matches. The one normalisation every narrow goes through. */
export function pagePredicate(urls: Iterable<string>): (url: string) => boolean {
  const keys = new Set<string>();
  for (const u of urls) keys.add(pathKey(u));
  return (url: string) => keys.has(pathKey(url));
}
