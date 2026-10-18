"""What only a browser can say about an image.

Six fields the Images brief needs are not in a page's markup: the width an
image actually renders at, its intrinsic size after decoding, whether it
sits above the fold, whether it is the page's Largest Contentful Paint
element, the aspect-ratio CSS gives it, and what it weighs on the wire.
Until this existed the engine handed the brief `[not measured]` for all
six and the brief held every check that needed one — honest, and thin.

**Optional in the same way `renderer.py` is.** Playwright is imported
lazily, `available()` is the gate, and a crawl without it stores exactly
what it stored before: the markup's own fields, and nothing invented for
the rest. A measurement this module could not take is absent from its
result rather than defaulted, because the whole point of the pass is to
replace a guess with a number.

**One visit per page, not one per breakpoint.** The page is loaded once
at the widest breakpoint with an LCP observer already armed, then the
viewport is stepped down through the rest and every image re-measured.
Five sizes cost five layouts, not five loads, and the resource timings
that carry weight are read once from the single load.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from clauditseo import BOT_NAME

log = logging.getLogger("clauditseo.imaging")

#: Long enough for a hydrating page to paint, short enough that a site
#: with a hundred pages is not an afternoon. The same figure the renderer
#: settles for, and for the same reason.
RENDER_TIMEOUT_MS = 25_000
SETTLE_MS = 1_200
#: Item 241: a lazy image is not requested until it nears the viewport, so
#: the pass scrolls the document the way a visitor would before it reads what
#: was fetched. One viewport a step, a pause for the requests each step
#: starts, a cap so an endless feed is not scrolled forever, and a bounded
#: wait for the network to settle once back at the top.
SCROLL_STEP_MS = 150
SCROLL_MAX_STEPS = 60
NETWORK_IDLE_MS = 5_000
#: How long a HEAD for an image's size may take. It is the fallback for an
#: image the page never fetched while measured, and one slow server must not
#: hold the pass.
HEAD_TIMEOUT_MS = 5_000

#: The widths the layout is measured at when the site record names none.
#: Mobile first, then the two most common laptop widths, then a desktop.
DEFAULT_BREAKPOINTS = (480, 768, 1024, 1440, 1920)

#: A cap on how much of a crawl this pass will look at. Measuring is a
#: page load per page and the audit's own clock is the operator's, so a
#: large site is measured in part and says so rather than in full and
#: late. The brief is told which pages carry measurements.
MAX_PAGES = 40

#: What the browser reads out of one page. Kept as a string here rather
#: than assembled per call: it is the whole of what this module knows how
#: to observe, and it should be readable in one piece.
_MEASURE_JS = """
() => {
  const seen = [];
  const abs = (u) => { try { return new URL(u, document.baseURI).href; } catch { return u || ""; } };
  // Item 241: a script lazy loader keeps the real file in one of these while
  // `src` is a placeholder, and swaps it in as the image nears the viewport.
  // The image is keyed by that attribute where it has one - the key the
  // crawler's markup record carries as `lazy_src` - so the two meet on the
  // file, before the swap and after it.
  const lazyOf = (el) => {
    for (const name of ["data-lazy-src", "data-src", "data-original", "data-lazy"]) {
      const v = (el.getAttribute(name) || "").trim();
      if (v && !v.startsWith("data:")) return v;
    }
    return "";
  };
  for (const el of document.querySelectorAll("img")) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const lazy = lazyOf(el);
    const current = el.currentSrc || el.getAttribute("src") || "";
    seen.push({
      src: lazy || el.getAttribute("src") || "",
      // The file the browser fetched; where it is still the placeholder, the
      // file the loader would have swapped in, so a HEAD can weigh it.
      resolved: abs(lazy && (!current || current.startsWith("data:")) ? lazy : current),
      rendered_w: Math.round(rect.width),
      rendered_h: Math.round(rect.height),
      intrinsic_w: el.naturalWidth || null,
      intrinsic_h: el.naturalHeight || null,
      // Above the fold means the top edge is inside the first viewport,
      // which is what decides whether loading it late costs a paint.
      above_fold: rect.top < window.innerHeight && rect.bottom > 0,
      // Where down the document it sits, 0 at the top and 1 at the bottom
      // (brief v16 step AU1). The template rule needs this on a page that
      // declares no landmarks at all, where "header" and "footer" can only
      // mean the top and the bottom of the document.
      top_pct: (() => {
        const doc = Math.max(document.documentElement.scrollHeight, 1);
        return Math.min(1, Math.max(0, (rect.top + window.scrollY) / doc));
      })(),
      css_aspect_ratio: style.aspectRatio && style.aspectRatio !== "auto"
        ? style.aspectRatio : null,
    });
  }
  return seen;
}
"""

_RESOURCES_JS = """
() => Object.fromEntries(
  performance.getEntriesByType("resource")
    .filter((r) => r.initiatorType === "img" || /\\.(avif|webp|jpe?g|png|gif|svg)(\\?|$)/i.test(r.name))
    .map((r) => [r.name, Math.round((r.encodedBodySize || r.transferSize || 0) / 1024)]))
"""

#: Down the document a viewport at a time, then back to the top (item 241).
#: Returns how many steps it took, which a test reads.
_SCROLL_JS = """
async ([stepMs, maxSteps]) => {
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  let steps = 0;
  while (steps < maxSteps
         && window.scrollY + window.innerHeight < document.documentElement.scrollHeight) {
    window.scrollBy(0, window.innerHeight);
    steps += 1;
    await pause(stepMs);
  }
  window.scrollTo(0, 0);
  await pause(stepMs);
  return steps;
}
"""

#: Armed before navigation, because an observer registered after the paint
#: it is meant to see reports nothing.
_LCP_INIT_JS = """
window.__lcp = null;
window.__lcp_seen = false;
try {
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      // Seen at all, whatever it turned out to be: that is what makes
      // "this image is not the paint" different from "nobody looked".
      window.__lcp_seen = true;
      if (entry.element && entry.element.tagName === "IMG") {
        window.__lcp = entry.element.currentSrc || entry.element.getAttribute("src") || null;
      }
    }
  }).observe({ type: "largest-contentful-paint", buffered: true });
} catch (e) { /* an engine without the entry type reports no LCP, not a wrong one */ }
"""


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _measure_one(page, url: str, breakpoints) -> dict:
    """One page, loaded once and measured at every breakpoint."""
    widest = max(breakpoints)
    page.set_viewport_size({"width": widest, "height": 900})
    page.add_init_script(_LCP_INIT_JS)
    page.goto(url, timeout=RENDER_TIMEOUT_MS, wait_until="load")
    page.wait_for_timeout(SETTLE_MS)
    # Item 241: weigh what a visitor would load. Before this, the one
    # resource read came before any scroll, so every `loading="lazy"` image
    # below the fold had no entry and no weight - on twenty22, 286 of 366;
    # the only images weighed were the header's. The attribute itself stays
    # in the markup record as evidence (`img-lcp-lazy` reads it).
    page.evaluate(_SCROLL_JS, [SCROLL_STEP_MS, SCROLL_MAX_STEPS])
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
    except Exception:                       # noqa: BLE001 - a busy page is still measured
        pass

    weights = page.evaluate(_RESOURCES_JS) or {}
    # `None` where the observer reported nothing at all, which is not the
    # same as "no image is the paint": a page whose largest element is a
    # CSS background reports an LCP this pass cannot attribute to an
    # `<img>`, and every image on it is then unknown rather than cleared.
    lcp = page.evaluate("() => window.__lcp")
    lcp_seen = page.evaluate("() => window.__lcp_seen === true")
    by_src: dict[str, dict] = {}
    for width in sorted(breakpoints, reverse=True):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(120)          # one layout, not a load
        for seen in page.evaluate(_MEASURE_JS) or []:
            src = seen["src"]
            if not src:
                continue
            record = by_src.setdefault(src, {
                "resolved": seen["resolved"],
                "intrinsic_w": seen["intrinsic_w"], "intrinsic_h": seen["intrinsic_h"],
                "css_aspect_ratio": seen["css_aspect_ratio"],
                "rendered": {}, "above_fold": False,
                # Where down the document it sits (brief v16 step AU1),
                # taken at the widest breakpoint because that is the first
                # measured and because a narrow viewport stacks a page and
                # moves everything down it. The template fallback reads
                # this on pages that declare no landmarks at all.
                "top_pct": seen["top_pct"],
            })
            record["rendered"][str(width)] = [seen["rendered_w"], seen["rendered_h"]]
            # Above the fold at any width it is measured at: a hero that
            # drops below the fold on a phone is still the paint on a
            # desktop, and the check is about the worst case.
            record["above_fold"] = record["above_fold"] or seen["above_fold"]

    for src, record in by_src.items():
        # Kept, not popped (brief v16 step AU7): this is the file the
        # browser actually fetched after `srcset` chose, and the re-encode
        # probe must weigh that one rather than the `src` attribute, which
        # on an image pipeline names a different rendition.
        resolved = record["resolved"] = record.get("resolved") or urljoin(url, src)
        record["weight_kb"] = weights.get(resolved)
        # Where the weight came from (item 241): the browser's own record of
        # the fetch, or - filled below - the server's size header.
        record["weight_source"] = "resource" if record["weight_kb"] else None
        record["lcp_candidate"] = (bool(lcp and (lcp == resolved or lcp == src))
                                   if lcp_seen else None)
    _weigh_by_header(page, url, by_src)
    return by_src


def _weigh_by_header(page, url: str, by_src: dict[str, dict]) -> None:
    """The fallback for an image the page never fetched while measured, same
    origin only (item 241): a HEAD for its size, marked `weight_source:
    header`. A cross-origin image without Timing-Allow-Origin stays
    unmeasured, as the block already explains - asking another origin is
    not this pass's to do."""
    from urllib.parse import urlsplit
    host = urlsplit(url).netloc
    for record in by_src.values():
        if record.get("weight_kb") or urlsplit(record["resolved"]).netloc != host:
            continue
        try:
            got = page.request.head(record["resolved"], timeout=HEAD_TIMEOUT_MS)
            size = int(got.headers.get("content-length") or 0) if got.ok else 0
        except Exception:                   # noqa: BLE001 - one image, not the page
            size = 0
        if size > 0:
            record["weight_kb"] = max(1, round(size / 1024))
            record["weight_source"] = "header"


def measure(urls, breakpoints=DEFAULT_BREAKPOINTS, cap: int = MAX_PAGES) -> dict[str, dict]:
    """Per url, per image src: what the browser saw.

    Returns `{}` where Playwright is not installed — the caller keeps its
    unmeasured fields and says so. A page that fails to load is absent
    from the result for the same reason: an empty measurement and a failed
    one must not read alike.
    """
    if not available():
        return {}
    from playwright.sync_api import sync_playwright

    out: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=f"{BOT_NAME}/1.0 (+headless image measurement for audit)")
            for url in list(urls)[:cap]:
                page = context.new_page()
                try:
                    out[url] = _measure_one(page, url, breakpoints)
                except Exception as error:            # one page's failure is its own
                    log.warning("image measurement failed for %s: %s", url, error)
                finally:
                    page.close()
        finally:
            browser.close()
    return out


# --- the pass an audit takes (item 205) --------------------------------------
#
# It lived in `api/app.py` as `_measure_rendered` and `_measure_savings`,
# called from the fixed-tier launcher only. `adaptive.run_adaptive` - the
# launcher's default tier and what a part's re-check sends - never took it, so
# every adaptive audit stored its images with no weight and no rendered box,
# and the Images part drew "a site whose images sit on a CDN is weighed by
# nobody" over same-origin images another audit had weighed five days before.
# Here, below both, as `perf.trace_for_run` already is for the trace.


def _int_or_none(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def reencode_candidates(measured: dict, record: dict) -> list[tuple[str, int | None]]:
    """(url, width) for every image whose row will state a saving.

    Read off the measurements rather than off the findings, because the
    findings do not exist yet - the checks run after this - and because the
    two agree by construction: the same three numbers decide both."""
    budget_image = _int_or_none(record.get("budget_image_kb")) or 300
    per_pixel_cap = _float_or_none(record.get("bytes_per_pixel")) or 1.0
    budget_lcp = _int_or_none(record.get("budget_lcp_kb")) or 200
    legacy = ("jpg", "jpeg", "png", "gif")
    out: list[tuple[str, int | None]] = []
    for images in measured.values():
        for src, shot in images.items():
            weight = shot.get("weight_kb")
            widths = [(v[0], v[1]) for v in (shot.get("rendered") or {}).values()]
            shown = max(widths, default=(0, 0))
            pixels = shown[0] * shown[1]
            per_pixel = (weight * 1024 / pixels) if (weight and pixels) else None
            stem = str(shot.get("resolved") or src).split("?")[0].rsplit(".", 1)
            heavy = bool(weight and (weight > budget_image
                                     or (per_pixel is not None and per_pixel > per_pixel_cap)))
            lcp_over = bool(weight and shot.get("lcp_candidate") and weight > budget_lcp)
            old_format = len(stem) == 2 and stem[1].lower() in legacy
            if heavy or lcp_over or old_format:
                out.append((str(shot.get("resolved") or src), shown[0] or None))
    return out


def measure_savings(measured: dict, record: dict) -> None:
    """Re-encode every candidate and put the result on its own row, in place.

    A failure carries its reason onto the row rather than dropping out: "we
    tried and could not" is a different sentence from "we did not try"."""
    from clauditseo import reencode

    if not reencode.available():
        return
    quality = _int_or_none(record.get("reencode_quality")) or 60
    candidates = reencode_candidates(measured, record)
    if not candidates:
        return
    try:
        results = reencode.measure(candidates, quality=quality)
    except Exception:                       # noqa: BLE001 - a pass, not a gate
        log.warning("image re-encode pass failed; rows keep their unmeasured "
                    "savings", exc_info=True)
        return
    for images in measured.values():
        for src, shot in images.items():
            got = results.get(str(shot.get("resolved") or src))
            if got:
                shot.update(got)


def measure_for_run(crawl, record: dict | None, report=None) -> tuple[dict, bool | str]:
    """What a browser saw of every image the crawl fetched, and whether it
    looked: `(measurements, state)`, the state being True where the pass ran,
    False where it failed, and "unavailable" where no renderer is installed.

    The state is stored with the run, because the screen cannot tell "the
    pass measured nothing" from "the pass did not run" from the images alone,
    and it printed the CDN explanation for both."""
    say = report or (lambda _m: None)
    if not available():
        say("No renderer installed: image sizes and weights not measured")
        return {}, "unavailable"
    say("Measuring images in a browser")
    record = record or {}
    urls = [p.url for p in crawl.pages
            if p.status == 200 and (p.content_type or "").startswith("text/html")]
    breakpoints = record.get("breakpoints") or DEFAULT_BREAKPOINTS
    try:
        measured = measure(urls, breakpoints=tuple(breakpoints))
    except Exception:                       # noqa: BLE001 - a pass, not a gate
        log.warning("image measurement pass failed; the inventory keeps its "
                    "unmeasured fields", exc_info=True)
        return {}, False
    if measured:
        say("Measuring what the heaviest images would weigh re-encoded")
        measure_savings(measured, record)
    return measured, True
