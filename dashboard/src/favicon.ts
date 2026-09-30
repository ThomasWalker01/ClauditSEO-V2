import { api, objectUrl } from "./api";

/** What `/api/brand` says about the tab icon. The rest of `BrandData` lives
 *  in `admin.tsx`; only this field matters here. */
type IconAnswer = { icon_href?: string | null };

/** The built-in mark from `index.html`, captured before anything replaces it,
 *  so falling back is restoring a known value rather than guessing one. */
let builtIn: string | null = null;

/** The object URL currently on the tab, so replacing it releases the last one.
 *  A blob URL lives as long as the document unless it is revoked, and this
 *  function runs again on every logo save and removal. */
let held: string | null = null;

function link(): HTMLLinkElement | null {
  return document.querySelector<HTMLLinkElement>('link[rel="icon"]');
}

/**
 * Point the tab at the operator's registered logo, or leave the default.
 *
 * FEATURES.md F-08. The decision is the server's — `/api/brand` returns
 * `icon_href`, which is a URL when a stored logo is present on disk AND
 * carries a mime a browser renders as an icon, and `null` for every way that
 * can fail. This function obeys it and holds no policy of its own, which is
 * why "a logo whose file has gone" and "a mime a browser will not take"
 * cannot be forgotten here: there is nothing to forget, only an href or not.
 *
 * Never throws. Before the operator has a token `/api/brand` is a 401, and a
 * tab icon is not worth an unhandled rejection on the way to the login gate.
 *
 * The server's answer is a path into the API, and the browser will not load
 * one: a `<link rel="icon">` is fetched as a subresource, with no
 * `Authorization` header, and every route here is guarded (UX-30). So the
 * bytes are fetched through the API client, which holds the token, and the tab
 * is given an object URL over them. The DECISION is still entirely the
 * server's — an href or nothing — and this still holds no policy; what changed
 * is who does the fetching.
 */
export async function applyBrandFavicon(): Promise<void> {
  const el = link();
  if (!el) return;
  if (builtIn === null) builtIn = el.getAttribute("href");

  let answer: IconAnswer;
  try {
    answer = await api.get<IconAnswer>("/api/brand");
  } catch {
    return;                       // not signed in yet, or the API is down
  }

  let href = builtIn;
  if (answer.icon_href) {
    try {
      href = await objectUrl(answer.icon_href);
    } catch {
      // The logo went between the two calls, or the API stopped answering.
      // The built-in mark is the right fallback for every way this fails,
      // which is the same rule `icon_href: null` already states.
      href = builtIn;
    }
  }

  // Only touch the DOM when the answer actually changes. Re-assigning the
  // same href makes some browsers refetch and flicker the tab.
  if (href && el.getAttribute("href") !== href) el.setAttribute("href", href);

  // Then release the one the tab has stopped pointing at. A freshly created
  // object URL is a unique string, so the unchanged-href branch above is only
  // ever reached by the built-in mark — there is no case where this revokes
  // the URL just installed.
  if (held && held !== href) URL.revokeObjectURL(held);
  held = href && href.startsWith("blob:") ? href : null;
}
