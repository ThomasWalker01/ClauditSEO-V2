"""The per-page performance trace (brief v19 step BC — Speed).

A browser pass, separate from `imaging.measure`, because the trace has to be
taken under a fixed device profile — **mid-tier mobile on 4G** — and applying
that throttling to imaging's pass would move the numbers the Images part reads.
So this launches its own page load, throttled through a CDP session, arms the
paint/LCP/CLS/long-task observers before navigation, and reads the trace back
after load settles.

Optional in the same way `imaging` and `axe` are: Playwright is imported
lazily, and `trace()` returns `{}` where it is not installed, so the caller
keeps its unmeasured fields and says so. A page that fails to load is absent
from the result rather than present-and-empty, so "the trace could not be
taken" and "the trace found nothing" never read alike.

**Where the browser genuinely cannot supply a field, it is stored as
`UNAVAILABLE`, not omitted** (item 154): the trace shape carries an
ENGINE_VERSION bump and a `test_stored_shape` entry, so a field left out now is
a migration later, and a consumer that meets `UNAVAILABLE` degrades — the way
the waterfall degrades to a totals bar — instead of meeting a missing key.

The trace is what all thirteen free Speed checks and the brief's five analysis
checks read; nothing here judges anything. The capture is the whole job.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from clauditseo import BOT_NAME

log = logging.getLogger("clauditseo.perf")

#: The sentinel a field carries when the browser pass cannot supply it — a
#: value, not an absence, so a stored trace always has every key and the
#: consumer degrades on the value rather than on a `KeyError` (item 154).
UNAVAILABLE = "unavailable"

#: The trace's own top-level keys, and a resource row's keys — declared here so
#: `test_stored_shape` can pin the nested shape (the page-record guard walks
#: only the record's own keys, not this dict inside it). A field added to a
#: trace or a resource row must be added here in the same commit, the way a new
#: page-record key is added to `test_stored_shape.EXPECTED`.
#: `head_html` became `head_rendered` at brief 160 step 2, and the rename IS
#: the fix. It was `document.head.outerHTML` read after load -- the live DOM
#: head -- while its own comment called it "head as fetched" and told the
#: caller "the raw served head is on the crawl record", which is not true:
#: nothing stores raw HTML on the evidence. Any check reading `head_html` as
#: the fetched head was reading the rendered one and could not have known.
#:
#: `head_fetched` is the real thing, from the document request's response body
#: over the CDP session this pass already holds. The two together are what make
#: `viewport-injected` (in rendered, not in fetched) and `viewport-divergent`
#: (in both, different) answerable at all -- a diff, not a second render pass.
#:
#: `mobile_render` is the three measurements item 147 called its step 8. They
#: are taken in THIS pass, on the same rendered page, under the same emulation:
#: `perf.py` was already a mobile render harness three days before that step
#: was written.
TRACE_KEYS = frozenset({
    "device_profile", "ttfb_ms", "fcp_ms", "lcp", "cls", "tbt_ms",
    "long_tasks", "resources", "fonts", "head_rendered", "head_fetched",
    "mobile_render", "frames"})
RESOURCE_KEYS = frozenset({
    "url", "type", "bytes", "transfer", "start_ms", "duration_ms", "blocking",
    "async", "defer", "media", "discovered_by", "cache_control", "compression",
    "coverage", "whitespace_ratio"})

#: The device profile every trace is taken under, stated on every run (brief
#: v19 step BC). Mid-tier mobile, 4G. The throttle numbers are the ones
#: Lighthouse's "Slow 4G"/mobile preset uses, so a reader comparing our trace
#: to a Lighthouse run is comparing like conditions.
#:
#: **We APPLY the throttle (CDP `emulateNetworkConditions` +
#: `setCPUThrottlingRate`); Lighthouse/PageSpeed default to SIMULATED
#: throttling** — it traces unthrottled and models Slow-4G afterwards. The two
#: agree closely on layout metrics but diverge on LCP/TTI, where simulation
#: routinely reads higher. Measured against PageSpeed on www.beacon.com.au
#: (2026-09-11, no CrUX field data): CLS 0.013 vs 0.013 (identical), FCP 1.6 s
#: vs 2.7 s, **LCP 2.6 s (ours) vs 6.0 s (PSI)**. Applied is the operator's
#: deliberate choice (2026-09-11): it is what a real Slow-4G phone experiences,
#: which is the brief's "device profile fixed at mid-tier mobile / 4G". So our
#: LCP reads LOWER than a client's own PageSpeed run by design — the gap is
#: throttling method, not a defect, and this is where that is written down.
DEVICE_PROFILE = "mid-tier mobile, 4G (CPU 4x, 1.6 Mbps down / 750 Kbps up, 150 ms RTT); applied throttling, not Lighthouse-simulated"
_CPU_THROTTLE = 4
#: Bytes/sec and ms — Chrome DevTools' "Slow 4G" preset.
_NET_DOWN = int(1.6 * 1024 * 1024 / 8)
_NET_UP = int(750 * 1024 / 8)
_NET_LATENCY_MS = 150
#: A mid-tier phone viewport and UA, so layout, LCP element and CLS are the
#: mobile ones — which is what Google's field data is weighted to.
_MOBILE_VIEWPORT = {"width": 412, "height": 823}
_MOBILE_UA = (f"Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 "
              f"(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 "
              f"{BOT_NAME}/1.0 (+headless performance trace for audit)")

_RENDER_TIMEOUT_MS = 30_000
_SETTLE_MS = 2_500
#: The head, "as fetched", capped — the brief asks for the first 4 KB.
_HEAD_CAP = 4096

#: Armed before navigation: an observer registered after the paint it watches
#: reports nothing. Buffered where the entry type allows it, so an entry that
#: fired before this script ran is still seen. Everything is stashed on
#: `window.__perf` and read back once after settle.
_OBSERVERS_INIT_JS = """
window.__perf = {lcp: null, cls: 0, cls_shifts: [], long_tasks: [], loaf: [], seen: {}};
function obs(type, cb, buffered) {
  try { new PerformanceObserver((l) => l.getEntries().forEach(cb))
          .observe({type: type, buffered: buffered !== false});
        window.__perf.seen[type] = true; }
  catch (e) { window.__perf.seen[type] = false; }
}
obs("largest-contentful-paint", (e) => {
  window.__perf.lcp = {
    start: e.startTime, render: e.renderTime || 0, load: e.loadTime || 0,
    size: e.size,
    url: e.url || null,
    tag: e.element ? e.element.tagName : null,
    id: e.element && e.element.id ? "#" + e.element.id : null,
    cls: e.element && e.element.className && typeof e.element.className === "string"
         ? "." + e.element.className.trim().split(/\\s+/).join(".") : null,
  };
});
obs("layout-shift", (e) => {
  if (e.hadRecentInput) return;
  window.__perf.cls += e.value;
  window.__perf.cls_shifts.push({
    value: e.value,
    sources: (e.sources || []).map((s) => s.node && s.node.nodeName
      ? s.node.nodeName.toLowerCase()
        + (s.node.id ? "#" + s.node.id : "")
        + (s.node.className && typeof s.node.className === "string"
           ? "." + s.node.className.trim().split(/\\s+/).join(".") : "")
      : "(anonymous)").slice(0, 4),
  });
});
obs("longtask", (e) => {
  window.__perf.long_tasks.push({
    start: e.startTime, duration: e.duration,
    attribution: (e.attribution || []).map((a) => a.containerSrc || a.name || "self"),
  });
});
// Long Animation Frames (Chrome 123+): unlike longtask, whose attribution is
// frame-level ("unknown"/"self"), a LoAF entry carries per-SCRIPT sourceURL and
// duration, which is what lets main-thread ms be charged to a third-party host.
obs("long-animation-frame", (e) => {
  window.__perf.loaf.push({
    start: e.startTime, duration: e.duration,
    scripts: (e.scripts || []).map((s) => ({
      url: s.sourceURL || null,
      ms: s.duration || s.totalDuration || 0})),
  });
});
"""

#: Read back once, after settle. Navigation and paint timing, the LCP the
#: observer caught, CLS, long tasks, the resource list, the fonts and the head.
#: Everything the observer could not catch is left to the Python side to mark
#: UNAVAILABLE; this returns raw numbers, not judgements.
_READ_TRACE_JS = r"""
() => {
  const nav = performance.getEntriesByType("navigation")[0] || null;
  const paint = performance.getEntriesByType("paint");
  const fcp = (paint.find((p) => p.name === "first-contentful-paint") || {}).startTime;
  const resources = performance.getEntriesByType("resource").map((r) => ({
    url: r.name,
    type: r.initiatorType,
    bytes: r.decodedBodySize || 0,
    transfer: r.transferSize || 0,
    encoded: r.encodedBodySize || 0,
    start: r.startTime,
    duration: r.duration,
    response_end: r.responseEnd,
    protocol: r.nextHopProtocol || null,
    // Chrome 107+; absent elsewhere, left for the Python side to mark.
    render_blocking: (typeof r.renderBlockingStatus !== "undefined")
      ? r.renderBlockingStatus : null,
  }));
  // Fonts: the loaded set plus the @font-face rules' font-display, and which
  // families a <link rel=preload as=font> named.
  const preloaded = new Set(
    [...document.querySelectorAll('link[rel="preload"][as="font"]')]
      .map((l) => l.href));
  const displays = {};
  for (const sheet of document.styleSheets) {
    let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
    for (const rule of rules || []) {
      if (rule.constructor && rule.constructor.name === "CSSFontFaceRule") {
        const fam = (rule.style.getPropertyValue("font-family") || "").replace(/['"]/g, "").trim();
        const disp = rule.style.getPropertyValue("font-display") || null;
        if (fam) displays[fam.toLowerCase()] = disp;
      }
    }
  }
  const fonts = [...(document.fonts || [])].map((f) => ({
    family: f.family, status: f.status,
    display: displays[(f.family || "").replace(/['"]/g, "").toLowerCase()] || null,
  }));
  // The RENDERED head, named for what it is (brief 160 step 2). This is
  // `document.head` after load, so a tag injected by script IS in here and a
  // tag the server sent may have been moved. The fetched head is read
  // separately, over CDP, on the Python side.
  const head_rendered = document.head ? document.head.outerHTML.slice(0, 4096) : null;
  // The three mobile-render measurements (item 147's step 8), taken here
  // because this pass is already a 412 x 823 Pixel 5 emulation with
  // JavaScript executing. No second load.
  const de = document.documentElement;
  const vw = window.innerWidth;
  const docw = Math.max(de.scrollWidth,
                        document.body ? document.body.scrollWidth : 0);
  // WHICH elements make the page scroll sideways, not just that it does.
  // `scrollWidth` alone cannot name a thing to fix.
  //
  // **Only elements that could CAUSE the scroll are listed**, and that rule
  // was learned on the live run that first exercised this (twenty22
  // `ed718610`, 2026-09-13). The first version listed anything whose box
  // crossed the viewport edge, and every page named
  // `mm__mobile-nav bricks-lazy-hidden` -- a hidden off-canvas menu 6 px past
  // 412 -- while `overflow_px` was 0 and the document did not scroll at all.
  // No false finding fired, because the finding is gated on `overflow_px`.
  // But the summary says "starting with" the first element listed, so on a
  // page that DID overflow it would have sent a reader to fix a menu that was
  // never the cause.
  //
  // So: nothing is listed where nothing overflows; hidden elements are
  // skipped (a box `getBoundingClientRect` still reports, for an element no
  // one can see); an element clipped by an ancestor that hides overflow is
  // skipped, because the clip is what stops it scrolling; and the list is
  // ordered by how far each reaches, so the element that sets the scroll
  // width is the one named first.
  const overflowing = [];
  const clipped = (el) => {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const o = getComputedStyle(a).overflowX;
      if (o === "hidden" || o === "clip") return true;
    }
    return false;
  };
  if (docw > vw) {
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (!(r.right > vw + 1 || r.left < -1)) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none"
          || parseFloat(cs.opacity) === 0) continue;
      if (clipped(el)) continue;
      overflowing.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        cls: (typeof el.className === "string" ? el.className : "").slice(0, 80) || null,
        right: Math.round(r.right), left: Math.round(r.left),
        width: Math.round(r.width)});
      if (overflowing.length >= 40) break;
    }
    overflowing.sort((a, b) => b.right - a.right);
    overflowing.length = Math.min(overflowing.length, 20);
  }
  // Interactive elements under 24 x 24 CSS px, the WCAG 2.2 SC 2.5.8 minimum.
  // Zero-box elements are skipped: a display:none link is not a tap target.
  const small = [];
  for (const el of document.querySelectorAll(
      "a[href], button, input, select, textarea, [role=button], [onclick]")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.width < 24 || r.height < 24) {
      small.push({tag: el.tagName.toLowerCase(),
                  text: (el.textContent || "").trim().slice(0, 40) || null,
                  w: Math.round(r.width), h: Math.round(r.height)});
      if (small.length >= 20) break;
    }
  }
  // Viewport-unit and fixed-position elements. `100vh` is taller than the
  // visible area while the URL bar shows, so the UNIT is what the fix turns
  // on and it is carried rather than counted.
  const units = [];
  for (const el of document.querySelectorAll("body *")) {
    const hit = [];
    for (const prop of ["height", "minHeight", "width"]) {
      const raw = (el.style && el.style[prop]) ? el.style[prop] : "";
      if (/\d(vh|vw|dvh|svh|lvh)\b/.test(raw)) hit.push(prop + ":" + raw);
    }
    if (getComputedStyle(el).position === "fixed") hit.push("position:fixed");
    if (hit.length) {
      units.push({tag: el.tagName.toLowerCase(),
                  cls: (typeof el.className === "string" ? el.className : "").slice(0, 80) || null,
                  used: hit.slice(0, 4)});
      if (units.length >= 20) break;
    }
  }
  const mobile_render = {
    viewport_width: vw,
    viewport_height: window.innerHeight,
    document_width: docw,
    overflow_px: Math.max(0, docw - vw),
    overflowing: overflowing,
    small_tap_targets: small,
    tap_target_min_px: 24,
    viewport_unit_elements: units};
  // <script>/<link> flags from the head, keyed by resolved URL, so the Python
  // side can attach async/defer/media/blocking to each resource row.
  const tags = {};
  for (const el of document.querySelectorAll("script[src], link[rel=stylesheet]")) {
    const u = el.src || el.href;
    if (!u) continue;
    tags[u] = {
      tag: el.tagName.toLowerCase(),
      async: el.async === true,
      defer: el.defer === true,
      media: el.media || null,
      in_head: !!(el.closest && el.closest("head")),
    };
  }
  return {
    nav: nav ? {
      ttfb: nav.responseStart, request_start: nav.requestStart,
      dom_content_loaded: nav.domContentLoadedEventEnd, load: nav.loadEventEnd,
    } : null,
    fcp: (typeof fcp === "number") ? fcp : null,
    perf: window.__perf,
    resources: resources,
    fonts: fonts,
    head_rendered: head_rendered,
    mobile_render: mobile_render,
    tags: tags,
  };
}
"""


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def whitespace_ratio(text: str) -> float:
    """The share of a source that is whitespace — the signal `unminified`
    reads (brief v19 step BC; the check is "JS/CSS whitespace ratio above
    threshold"). A minified file collapses its whitespace and scores near zero;
    a pretty-printed one carries indentation and blank lines and scores high.
    Computed here rather than in the browser so the body is weighed once and
    only the ratio is stored, never the source."""
    if not text:
        return 0.0
    ws = sum(1 for c in text if c.isspace())
    return round(ws / len(text), 4)


def _resource_type(url: str, initiator: str) -> str:
    """A resource's kind, from its initiator and extension — one vocabulary
    for the waterfall's colours and the third-party ledger."""
    ext = urlsplit(url).path.rsplit(".", 1)[-1].lower() if "." in urlsplit(url).path else ""
    if initiator in ("script", "link") and ext == "css":
        return "css"
    if ext == "css":
        return "css"
    if initiator == "script" or ext == "js":
        return "script"
    if ext in ("woff", "woff2", "ttf", "otf", "eot"):
        return "font"
    if ext in ("avif", "webp", "jpg", "jpeg", "png", "gif", "svg") or initiator == "img":
        return "image"
    if initiator in ("fetch", "xmlhttprequest"):
        return "xhr"
    return initiator or "other"


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _trace_one(page, cdp, url: str, first_party_host: str, coverage: bool,
               frames_dir=None, frame_stem=None) -> dict:
    """One page, loaded once under the throttle, traced end to end.

    Returns the trace dict — every key present, `UNAVAILABLE` where the browser
    could not supply it. Raises on a load failure so the caller can drop the
    page rather than store a half-trace.
    """
    # Coverage over CDP, not `page.coverage`: the coverage API is async-Playwright
    # only — in sync Playwright `page.coverage` does not exist, so the old calls
    # threw `AttributeError` and were swallowed, leaving coverage permanently
    # unavailable (BC checkpoint diagnosis). `CSS.startRuleUsageTracking` and
    # `Profiler.startPreciseCoverage` on the session already attached give the
    # same numbers and join to the resource list by URL.
    if coverage and cdp is not None:
        coverage = _start_coverage(cdp)
    else:
        coverage = False

    page.add_init_script(_OBSERVERS_INIT_JS)
    # Commit, not load: the filmstrip has to see the page *painting*, so the
    # frames are sampled across the settle window that follows the first byte,
    # not after `load` when the page is already static (which drew three
    # identical frames of the finished page — found at the BC checkpoint). The
    # settle wait is spent taking the frames; where none are wanted it is a
    # plain wait.
    filmstrip = None
    if frames_dir is not None and frame_stem and cdp is not None:
        filmstrip = _start_screencast(cdp)
    page.goto(url, timeout=_RENDER_TIMEOUT_MS, wait_until="commit")
    page.wait_for_timeout(_SETTLE_MS)
    try:
        page.wait_for_load_state("load", timeout=_RENDER_TIMEOUT_MS)
    except Exception:
        pass
    frames = (_stop_screencast(cdp, filmstrip, frames_dir, frame_stem)
              if filmstrip is not None else UNAVAILABLE)

    raw = page.evaluate(_READ_TRACE_JS) or {}

    cov_by_url = _stop_coverage(cdp) if coverage else {}
    # Read after load, while the body is still in the protocol's buffer
    # (brief 160 step 2). None where it cannot be had, and the trace marks it
    # UNAVAILABLE rather than substituting the rendered head.
    fetched_head = _fetched_head(cdp)
    used_by_url = {u: c["used"] for u, c in cov_by_url.items()}
    total_by_url = {u: c["total"] for u, c in cov_by_url.items()}

    # Response headers per URL, over CDP — cache-control and content-encoding
    # are not on a PerformanceResourceTiming, and this is the one place to get
    # them without a re-fetch.
    headers_by_url = _response_headers(cdp)

    tags = raw.get("tags") or {}
    resources = []
    for r in raw.get("resources") or []:
        u = r["url"]
        rtype = _resource_type(u, r.get("type") or "")
        tag = tags.get(u, {})
        hdr = headers_by_url.get(u, {})
        cache = hdr.get("cache-control")
        encoding = hdr.get("content-encoding")
        rb = r.get("render_blocking")
        # blocking: the browser's own render-blocking status where it gave one
        # (Chrome 107+); otherwise inferred for a head stylesheet/sync script.
        if rb is not None:
            blocking = (rb == "blocking")
        elif tag.get("in_head") and rtype in ("css", "script"):
            blocking = not (tag.get("async") or tag.get("defer")
                            or (rtype == "css" and tag.get("media") not in (None, "", "all")))
        else:
            blocking = UNAVAILABLE if not tag else False
        cov = UNAVAILABLE
        if u in total_by_url and total_by_url[u]:
            cov = {"used": used_by_url.get(u, 0), "total": total_by_url[u]}
        resources.append({
            "url": u, "type": rtype,
            "bytes": r.get("bytes") or 0,
            "transfer": r.get("transfer") or 0,
            "start_ms": round(r.get("start") or 0, 1),
            "duration_ms": round(r.get("duration") or 0, 1),
            "blocking": blocking,
            "async": tag.get("async", UNAVAILABLE if not tag else False),
            "defer": tag.get("defer", UNAVAILABLE if not tag else False),
            "media": tag.get("media"),
            "discovered_by": r.get("type") or UNAVAILABLE,
            "cache_control": cache if cache is not None else (UNAVAILABLE if not hdr else None),
            "compression": encoding if encoding else (UNAVAILABLE if not hdr else "none"),
            "coverage": cov,
            # whitespace_ratio is filled by the caller for js/css from the body
            # (a second cheap fetch); UNAVAILABLE until then.
            "whitespace_ratio": UNAVAILABLE,
        })

    p = raw.get("perf") or {}
    nav = raw.get("nav") or {}
    ttfb = round(nav["ttfb"], 1) if nav.get("ttfb") is not None else UNAVAILABLE
    fcp = round(raw["fcp"], 1) if raw.get("fcp") is not None else UNAVAILABLE
    lcp = _lcp_shape(p.get("lcp"), resources, ttfb, fcp,
                     (p.get("seen") or {}).get("largest-contentful-paint"))
    tbt = _tbt(p.get("long_tasks") or [], raw.get("fcp"))

    return {
        "device_profile": DEVICE_PROFILE,
        "ttfb_ms": ttfb,
        "fcp_ms": fcp,
        "lcp": lcp,
        "cls": {"value": round(p.get("cls") or 0, 4),
                "shifts": (p.get("cls_shifts") or [])[:20]},
        "tbt_ms": tbt,
        "long_tasks": _long_tasks_shape(p),
        "resources": resources,
        "fonts": _fonts_shape(raw.get("fonts") or [],
                              raw.get("head_rendered") or ""),
        # Two heads, named for what each is (brief 160 step 2). `head_fetched`
        # is UNAVAILABLE rather than falling back to the rendered one: a
        # fallback would make `viewport-injected` and `viewport-divergent`
        # compare a thing with itself and report every page clean.
        "head_rendered": (raw.get("head_rendered") or UNAVAILABLE)[:_HEAD_CAP]
        if raw.get("head_rendered") else UNAVAILABLE,
        "head_fetched": (fetched_head[:_HEAD_CAP] if fetched_head
                         else UNAVAILABLE),
        # The three measurements item 147 called its step 8, taken in this
        # pass under the emulation stated in `device_profile`.
        "mobile_render": raw.get("mobile_render") or UNAVAILABLE,
        # Sampled across the load and labelled by the nearest paint milestone
        # (FCP, LCP) from the trace just read; UNAVAILABLE where none ran.
        "frames": _label_frames(frames, fcp, lcp.get("ms")),
    }


def _label_frames(frames, fcp, lcp_ms) -> object:
    """Tag each sampled frame with the nearest paint milestone, so the
    filmstrip reads `FCP`/`LCP`/`loading` rather than a bare index. Crude by
    design (the part page does the exact alignment); the point is that the
    frames show the page painting over time, not three copies of the finished
    page."""
    if not isinstance(frames, list):
        return frames
    milestones = []
    if isinstance(fcp, (int, float)):
        milestones.append(("FCP", fcp))
    if isinstance(lcp_ms, (int, float)):
        milestones.append(("LCP", lcp_ms))
    for fr in frames:
        t = fr.get("t_ms", 0)
        near = min(milestones, key=lambda m: abs(m[1] - t)) if milestones else None
        fr["label"] = (near[0] if near and abs(near[1] - t) <= 250 else "loading")
    return frames


def _long_tasks_shape(p) -> list:
    """Main-thread long tasks, each with its per-script attribution. Preferred
    from Long Animation Frames (per-script `sourceURL` and duration — the only
    source that can charge main-thread ms to a third-party host); falls back to
    `longtask` entries, whose attribution is frame-level, so their `scripts`
    list is empty rather than the misleading "unknown" the raw API returns."""
    loaf = p.get("loaf") or []
    if loaf:
        return [{"start_ms": round(f.get("start") or 0, 1),
                 "duration_ms": round(f.get("duration") or 0, 1),
                 "scripts": [{"url": s.get("url"), "ms": round(s.get("ms") or 0, 1)}
                             for s in (f.get("scripts") or []) if s.get("url")]}
                for f in loaf if (f.get("duration") or 0) > 50][:50]
    return [{"start_ms": round(t.get("start") or 0, 1),
             "duration_ms": round(t.get("duration") or 0, 1), "scripts": []}
            for t in (p.get("long_tasks") or [])[:50]]


def _lcp_shape(lcp, resources, ttfb, fcp, seen) -> dict:
    """The LCP with its element and the four sub-parts the `lcp-cause` card
    reads. `None` element with `seen` true means the paint was not an image or
    a tagged element this pass could name — recorded so "not an image" is
    distinct from "no LCP observed"."""
    if not lcp:
        return {"ms": UNAVAILABLE, "element": None, "url": None,
                "is_image": None, "observed": bool(seen),
                "sub_parts": UNAVAILABLE}
    element = lcp.get("id") or lcp.get("cls") or (
        lcp.get("tag").lower() if lcp.get("tag") else None)
    ms = round(lcp.get("start") or 0, 1)
    # Sub-parts (brief): TTFB, resource load delay, resource load time, render
    # delay. Computable only when the LCP is a resource we timed; otherwise the
    # render-delay half is all we can attribute and the rest is UNAVAILABLE.
    sub = UNAVAILABLE
    res = next((r for r in resources if lcp.get("url") and r["url"] == lcp["url"]), None)
    if res and isinstance(ttfb, (int, float)):
        load_delay = max(0, round(res["start_ms"] - ttfb, 1))
        load_time = round(res["duration_ms"], 1)
        render_delay = max(0, round(ms - res["start_ms"] - res["duration_ms"], 1))
        sub = {"ttfb": ttfb, "load_delay": load_delay,
               "load_time": load_time, "render_delay": render_delay}
    elif res is None and lcp.get("url") is None and isinstance(ttfb, (int, float)) \
            and isinstance(fcp, (int, float)):
        # A text LCP: no resource, so it is TTFB + render delay only.
        sub = {"ttfb": ttfb, "load_delay": 0, "load_time": 0,
               "render_delay": max(0, round(ms - ttfb, 1))}
    return {"ms": ms, "element": element, "url": lcp.get("url"),
            "is_image": bool(lcp.get("url")), "observed": True, "sub_parts": sub}


def _tbt(long_tasks, fcp) -> float | str:
    """Total Blocking Time — the INP lab proxy the brief labels as such: the
    sum over long tasks (after FCP) of the milliseconds each ran past 50."""
    if fcp is None:
        return UNAVAILABLE
    total = 0.0
    for t in long_tasks:
        if (t.get("start") or 0) < fcp:
            continue
        total += max(0.0, (t.get("duration") or 0) - 50)
    return round(total, 1)


def _fonts_shape(fonts, head_rendered) -> list:
    """Each font with its font-display, whether it was preloaded, and whether a
    swap was observed (status 'loaded' after the paint means the swap
    happened). Preload is read from the head where the CSSOM did not carry it."""
    preloaded_hint = ("rel=preload" in (head_rendered or "")
                      and "as=font" in (head_rendered or ""))
    out = []
    for f in fonts:
        display = f.get("display")
        out.append({
            "family": f.get("family"),
            "display": display if display else UNAVAILABLE,
            "preloaded": preloaded_hint if preloaded_hint else UNAVAILABLE,
            # A font that finished loading is a swap-or-block; the observer does
            # not separate them without a paint diff, so this stays a hint.
            "swap_observed": (f.get("status") == "loaded") if display == "swap" else UNAVAILABLE,
        })
    return out


def _fetched_head(cdp) -> str | None:
    """The head the server actually sent, from the document request's response
    body over CDP (brief 160 step 2).

    Returns None where it cannot be had, and the caller marks it UNAVAILABLE
    rather than substituting the rendered head. That substitution is the defect
    this exists to fix: `head_html` was the rendered head under a name that
    said otherwise, so a check comparing "fetched" against "rendered" was
    comparing a thing with itself and could only ever find them identical.

    `Network.getResponseBody` is called after load, which is when the body is
    still in the protocol's buffer and the page has finished with it. A body
    Chrome has evicted, a base64 body, a request that never resolved: all
    return None, and none of them is an error worth failing a trace over.
    """
    rid = getattr(cdp, "_perf_doc_request", None) if cdp is not None else None
    if not rid:
        return None
    try:
        got = cdp.send("Network.getResponseBody", {"requestId": rid})
    except Exception:
        return None
    if not isinstance(got, dict) or got.get("base64Encoded"):
        return None
    body = got.get("body")
    if not isinstance(body, str) or not body:
        return None
    # The head only, and capped like the rendered one. A 2 MB document's body
    # is not what this is for, and the checks that read it are all about the
    # head's contents and the order of things in it.
    low = body.lower()
    start = low.find("<head")
    end = low.find("</head>")
    if start < 0:
        return body[:_HEAD_CAP]
    return body[start:(end + 7) if end > start else len(body)][:_HEAD_CAP]


def _response_headers(cdp) -> dict:
    """Cache-control and content-encoding per URL, collected over the CDP
    Network domain during the load. Empty when no CDP session was attached, so
    the resource rows mark those two fields UNAVAILABLE rather than guess."""
    if cdp is None:
        return {}
    return getattr(cdp, "_perf_headers", {}) or {}


#: The most pages one trace pass will take, whatever the sample rule offers.
#: A site with three hundred distinct templates would otherwise ask for three
#: hundred throttled loads, which is the "different audit" the sample exists to
#: prevent. Largest templates first, so the cap drops the rarest.
SAMPLE_CAP = 30


def sample(pages, tier) -> tuple[list[str], str]:
    """Which pages this run traces, and the sentence that states the sample.

    **Not per page, and that is an operator ruling rather than an omission**
    (2026-09-11). The brief's "a performance trace per page" predates the CPU
    4x / Slow-4G CDP session this pass now applies: a T3 at five hundred
    throttled traces is a different audit from the one the operator asked for.
    BB's pattern table and 151's probe already sample this way.

      T1   every readable page. The pulse's budget is three (`TIER_BUDGETS`),
           so "all three pages" IS the whole crawl - there is nothing to
           sample, and a representative of three would be a worse answer for
           no saving.
      T2   one page per URL pattern, capped. A template is the unit every
      T3   Speed analysis row is written against, so the representative is
           what the strip's gauges and the brief both read.

    Returns the URLs and a statement of the rule, which the part states beside
    the device profile — the same reason that one is stated: a figure read
    under conditions the reader cannot see is a figure they cannot check.
    """
    from clauditseo.engine.types import Tier
    from clauditseo import urlshape

    readable = [p for p in pages
                if getattr(p, "status", None) == 200
                and (getattr(p, "content_type", "") or "").startswith("text/html")]
    if not readable:
        return [], "nothing readable to trace"
    if tier is Tier.T1:
        return ([p.url for p in readable],
                f"every page of the pulse ({len(readable)})")

    groups: dict[str, list] = {}
    for page in readable:
        pattern = urlshape.derive_pattern(urlsplit(page.url).path or "/") or "/"
        groups.setdefault(pattern, []).append(page)
    # Largest template first: where the cap bites, it drops the rarest shape
    # rather than whichever the crawl happened to reach last.
    order = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    picked = [pages_[0].url for _pattern, pages_ in order[:SAMPLE_CAP]]
    rule = (f"one page per template ({len(picked)} of {len(readable)} readable, "
            f"{len(groups)} template{'s' if len(groups) != 1 else ''})")
    if len(order) > SAMPLE_CAP:
        rule += f" - capped at {SAMPLE_CAP}, largest templates first"
    return picked, rule


def trace(urls, run_id: str | None = None, cap: int = 30,
          frames_dir=None) -> dict:
    """Per url: the performance trace, taken under the fixed device profile.

    Returns `{}` where Playwright is not installed. A page that fails to load
    is absent from the result. The optional `frames_dir` receives the filmstrip
    frames; when omitted, `frames` on each trace is UNAVAILABLE.
    """
    if not available():
        return {}
    from playwright.sync_api import sync_playwright

    out: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=_MOBILE_UA, viewport=_MOBILE_VIEWPORT,
                is_mobile=True, has_touch=True, device_scale_factor=2)
            first = _host(next(iter(urls), "") or "")
            from clauditseo import axe
            for url in list(urls)[:cap]:
                page = context.new_page()
                cdp = _attach_cdp(context, page)
                try:
                    stem = axe.page_hash(url) if frames_dir is not None else None
                    tr = _trace_one(page, cdp, url, first, coverage=True,
                                    frames_dir=frames_dir, frame_stem=stem)
                    _fill_whitespace(context, tr)
                    out[url] = tr
                except Exception as error:            # one page's failure is its own
                    log.warning("performance trace failed for %s: %s", url, error)
                finally:
                    page.close()
        finally:
            browser.close()
    return out


def _attach_cdp(context, page):
    """A CDP session with the device throttle applied and a header collector
    armed. Returns None where CDP is unavailable (non-Chromium), and the trace
    then marks the CDP-only fields UNAVAILABLE."""
    try:
        cdp = context.new_cdp_session(page)
    except Exception:
        return None
    try:
        cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions", {
            "offline": False, "downloadThroughput": _NET_DOWN,
            "uploadThroughput": _NET_UP, "latency": _NET_LATENCY_MS})
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": _CPU_THROTTLE})
        headers: dict = {}
        cdp._perf_headers = headers

        def _on_response(evt):
            try:
                r = evt.get("response") or {}
                h = {k.lower(): v for k, v in (r.get("headers") or {}).items()}
                headers[r.get("url")] = {
                    "cache-control": h.get("cache-control"),
                    "content-encoding": h.get("content-encoding"),
                }
                # The document request's id, kept so its response BODY can be
                # read after load (brief 160 step 2). This is the only way to
                # the head the server actually sent: `document.head` after load
                # is the rendered one, and the crawl stores no raw HTML at all.
                #
                # The FIRST document response is the one wanted. A redirect
                # chain produces several, and an iframe produces more; the
                # first is the navigation this trace is of.
                if evt.get("type") == "Document" and not hasattr(
                        cdp, "_perf_doc_request"):
                    cdp._perf_doc_request = evt.get("requestId")
            except Exception:
                pass
        cdp.on("Network.responseReceived", _on_response)
        # Coverage needs the styleSheetId/scriptId -> URL maps, collected from
        # the moment the domains are enabled so nothing parsed before the load
        # is missed. Stored on the session for `_stop_coverage`.
        sheets: dict = {}
        scripts: dict = {}
        cdp._perf_sheets = sheets
        cdp._perf_scripts = scripts
        cdp.on("CSS.styleSheetAdded", lambda e: sheets.__setitem__(
            e["header"]["styleSheetId"],
            {"url": e["header"].get("sourceURL"), "length": e["header"].get("length")}))
        cdp.on("Debugger.scriptParsed",
               lambda e: scripts.__setitem__(e["scriptId"], e.get("url")))
        for domain in ("DOM", "CSS", "Debugger", "Profiler"):
            try:
                cdp.send(f"{domain}.enable")
            except Exception:
                pass
    except Exception:
        return cdp
    return cdp


def _start_coverage(cdp) -> bool:
    """Begin CSS and JS coverage tracking on the session. Returns False where
    the browser will not start it, so the trace marks coverage UNAVAILABLE
    rather than reporting a zero nobody measured."""
    try:
        cdp.send("CSS.startRuleUsageTracking")
        cdp.send("Profiler.startPreciseCoverage", {"callCount": False, "detailed": True})
        return True
    except Exception:
        return False


def _stop_coverage(cdp) -> dict:
    """Stop tracking and return `{url: {used, total}}` in bytes. CSS used is the
    sum of the used rule ranges against the stylesheet's length; JS used is the
    covered character ranges against the script's extent. Empty where the
    browser returned nothing, which the resource rows then read as UNAVAILABLE."""
    out: dict = {}
    sheets = getattr(cdp, "_perf_sheets", {}) or {}
    scripts = getattr(cdp, "_perf_scripts", {}) or {}
    try:
        css = cdp.send("CSS.stopRuleUsageTracking").get("ruleUsage", [])
    except Exception:
        css = []
    # Seed every stylesheet the page loaded at used=0 first, so a sheet with no
    # used rules at all (100% unused — the case `unused-css-js` most wants to
    # catch) reports rather than vanishing. `ruleUsage` carries only the rules
    # that were evaluated, so a fully-unused sheet is absent from it and would
    # otherwise never reach the result (found re-running the BC checkpoint).
    for sheet in sheets.values():
        url = sheet.get("url")
        if url and sheet.get("length"):
            out.setdefault(url, {"used": 0, "total": sheet["length"]})
    for u in css:
        sheet = sheets.get(u.get("styleSheetId"), {})
        url = sheet.get("url")
        if not url:
            continue
        row = out.setdefault(url, {"used": 0, "total": sheet.get("length") or 0})
        if u.get("used"):
            row["used"] += (u.get("endOffset", 0) - u.get("startOffset", 0))
    try:
        js = cdp.send("Profiler.takePreciseCoverage").get("result", [])
    except Exception:
        js = []
    for entry in js:
        url = entry.get("url") or scripts.get(entry.get("scriptId"))
        if not url:
            continue
        used = total = 0
        for fn in entry.get("functions", []):
            for r in fn.get("ranges", []):
                total = max(total, r.get("endOffset", 0))
                if r.get("count", 0) > 0:
                    used += (r.get("endOffset", 0) - r.get("startOffset", 0))
        if total:
            out[url] = {"used": min(used, total), "total": total}
    return out


def _fill_whitespace(context, trace_dict) -> None:
    """The whitespace ratio for each JS/CSS resource, from a cheap second fetch
    of its body inside the browser context (same cookies, same origin rules).
    Left UNAVAILABLE where the body could not be read."""
    api = getattr(context, "request", None)
    for r in trace_dict.get("resources", []):
        if r["type"] not in ("script", "css"):
            continue
        if api is None:
            continue
        try:
            resp = api.get(r["url"], timeout=10_000)
            if resp.ok:
                r["whitespace_ratio"] = whitespace_ratio(resp.text())
        except Exception:
            pass


#: The filmstrip cap — a screencast can push a frame on every repaint, which
#: is more than a strip needs; keep the ones that show a change, up to this.
_FRAME_CAP = 12


def _start_screencast(cdp) -> dict | None:
    """Arm a CDP screencast: the browser pushes a JPEG frame on every repaint,
    each with its own timestamp, so the filmstrip is the page actually painting
    rather than screenshots polled on a throttled main thread (which under 4x
    CPU could not sample the paint window densely — found at the BC checkpoint).
    Returns a collector the frames land in, or None where CDP will not start
    one (non-Chromium)."""
    import time
    state = {"frames": [], "t0": time.monotonic()}
    try:
        def _on_frame(evt):
            try:
                state["frames"].append({
                    "data": evt.get("data"),
                    "t_ms": round((time.monotonic() - state["t0"]) * 1000, 1)})
                cdp.send("Page.screencastFrameAck", {"sessionId": evt.get("sessionId")})
            except Exception:
                pass
        cdp.on("Page.screencastFrame", _on_frame)
        cdp.send("Page.startScreencast",
                 {"format": "jpeg", "quality": 60, "everyNthFrame": 1,
                  "maxWidth": 412, "maxHeight": 823})
    except Exception:
        return None
    return state


def _stop_screencast(cdp, state, frames_dir, stem) -> object:
    """Stop the screencast and write the frames that show a change, labelled by
    order and timestamp (milestone labelling is `_label_frames`'s). De-duped on
    the raw bytes, so a page that painted once yields one frame, not twelve
    copies of the finished page."""
    import base64
    import os
    try:
        cdp.send("Page.stopScreencast")
    except Exception:
        pass
    raw = state.get("frames") or []
    if not raw:
        return UNAVAILABLE
    try:
        os.makedirs(frames_dir, exist_ok=True)
    except Exception:
        return UNAVAILABLE
    frames, seen, order = [], set(), 0
    for fr in raw:
        data = fr.get("data")
        if not data or data in seen:
            continue
        seen.add(data)
        name = f"{stem}-frame{order}.jpg"
        try:
            with open(os.path.join(frames_dir, name), "wb") as f:
                f.write(base64.b64decode(data))
        except Exception:
            continue
        frames.append({"name": name, "order": order, "t_ms": fr["t_ms"]})
        order += 1
        if order >= _FRAME_CAP:
            break
    return frames or UNAVAILABLE


def trace_for_run(crawl, run_id: str) -> tuple[dict, str]:
    """The performance trace under the fixed device profile (brief v19 step
    BC), over the pages `perf.sample` selects. A separate throttled browser
    pass; failure is not fatal — a page that could not be traced is absent and
    its record reads `{"traced": False}`. Filmstrip frames are written under
    the run's screens dir.

    **The gate inverted at the depth-pill stage (item 141 step BC, operator
    2026-09-11).** It was opt-IN (`CLAUDITSEO_TRACE_PERF` had to be set), which
    left every ordinary audit with no traces at all — and the thirteen trace
    checks fire only on traced pages, so the four overlapping header/HTML
    checks could not be retired without every audit going dark on caching,
    response time and third-party weight. The trace is on by default now and
    `CLAUDITSEO_TRACE_PERF=0` turns it OFF, which is what the test suite sets:
    a throttled pass is far dearer than the imaging one (4x CPU, Slow-4G, a
    2.5s settle per page), and a suite that launched one per fixture audit
    would pay minutes for coverage its own Speed tests get explicitly.

    Returns the traces and the sample's own statement, which the Speed part
    states beside the device profile.

    Moved here from `api/app.py` on 2026-09-14 so `adaptive.run_adaptive`
    takes the same pass: every free Re-check posts `tier: "auto"`, and until
    then no adaptive run carried a trace, so every trace-derived check read
    "not assessed" after one.
    """
    import os

    from clauditseo import axe

    if os.environ.get("CLAUDITSEO_TRACE_PERF", "1") in ("0", "", "false", "no"):
        return {}, "not taken - the trace pass is switched off on this install"
    if not available():
        return {}, "not taken - no browser is installed for the trace pass"
    urls, rule = sample(crawl.pages, crawl.tier)
    if not urls:
        return {}, rule
    try:
        frames_dir = axe.screens_dir(run_id) / "perf"
        return trace(urls, run_id=run_id, frames_dir=frames_dir), rule
    except Exception:                       # noqa: BLE001 — a pass, not a gate
        logging.getLogger("clauditseo.perf").warning(
            "performance trace pass failed; Speed reads the traces as not "
            "taken", exc_info=True)
        return {}, "not taken - the trace pass failed; see the server log"
