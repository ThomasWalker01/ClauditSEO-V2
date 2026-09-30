"""The accessibility checks that need a rendered page.

Contrast against resolved styles, focus order, reading order, and anything
whose answer depends on the cascade rather than the markup. None of it is
decidable from HTML, which is why the A11Y dimension says plainly that it
did not assess them when this module has not run.

Optional in the same way the renderer is: Playwright is imported lazily,
``available()`` is the gate, and a bare install audits everything else and
is honest about the gap. See ``clauditseo/vendor/README.md`` for where
axe.min.js came from and how to upgrade it.

A note on trust. axe reports violations against WCAG success criteria and is
very good at what it covers, but automated testing reaches roughly a third
of WCAG. A page with no axe violations is a page with no *detectable*
violations, and findings from here say so. It is a floor, not a clearance.
"""

from __future__ import annotations

from clauditseo import BOT_NAME

import json
from pathlib import Path

from clauditseo.engine.types import Finding, Severity

AXE_JS = Path(__file__).parent / "vendor" / "axe.min.js"

#: axe's own impact scale, mapped onto ours. "minor" lands on LOW rather than
#: INFO because it is still a real barrier for someone; INFO in this codebase
#: means "not a defect", and axe never reports those.
IMPACT = {
    "critical": Severity.CRITICAL,
    "serious": Severity.HIGH,
    "moderate": Severity.MEDIUM,
    "minor": Severity.LOW,
}

#: Rules whose subject matter another dimension already owns. Running them
#: would deduct twice for one defect: ONP raises img-alt-missing and
#: heading-skip, TEC raises mobile-viewport, and A11Y's own static pass
#: raises the rest.
ALREADY_OWNED = {
    "image-alt", "input-image-alt", "area-alt",          # ONP img-alt-missing
    "heading-order", "page-has-heading-one",             # ONP headings
    "meta-viewport", "meta-viewport-large",              # TEC mobile-viewport
    "html-has-lang", "html-lang-valid",                  # A11Y html-lang-missing
    "label", "form-field-multiple-labels",               # A11Y form-control-unlabelled
    "link-name", "button-name",                          # A11Y *-name-missing
    "duplicate-id", "duplicate-id-active", "duplicate-id-aria",
    "tabindex",                                          # A11Y tabindex-positive
    "frame-title",                                       # A11Y iframe-title-missing
    "landmark-one-main",                                 # A11Y landmark-main-missing
    "aria-valid-attr-value",                             # A11Y aria-reference-broken
}

#: Nodes named per finding before the evidence stops being readable.
from clauditseo.modules.pagefacts import INSTANCE_HTML  # noqa: E402

SAMPLE = 8


def available() -> bool:
    """Both halves must be present: the browser driver and the script."""
    if not AXE_JS.is_file():
        return False
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _script() -> str:
    return AXE_JS.read_text(encoding="utf-8")


#: Where a run's screenshots live. One directory per run, so retention is
#: `rmtree` of a path the run already knows, and no picture can outlive the
#: run it was taken for or be orphaned by one that was deleted.
SCREENS = Path("data/screens")


def screens_dir(run_id: str, root: Path | None = None) -> Path:
    return (root or SCREENS) / run_id


def page_hash(url: str) -> str:
    """The picture's file name.

    A hash of the URL rather than a slug: a path can contain anything a URL
    can, including separators and characters Windows refuses, and a slug
    that collides puts one page's screenshot under another page's findings.
    """
    import hashlib
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def run_page(url: str, timeout_ms: int = 30_000,
             screenshot_to: Path | None = None) -> dict:
    """Load one URL, inject axe, and return its raw result object.

    Raises rather than returning a sentinel: the caller decides whether a
    page that will not render is a failed audit or a skipped page, and that
    depends on why it was being audited.

    `screenshot_to` writes a full-page PNG there (136j Part B). A failure to
    write one does NOT fail the pass and does not raise: the violations are
    the audit and the picture is only how they are drawn, so a lost picture
    costs a blank overlay rather than a page's findings. The reason is
    recorded either way - a run with no pictures and no reason is
    indistinguishable from one where the pass never ran.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                user_agent=f"{BOT_NAME}/1.0 (+accessibility audit)")
            pg = ctx.new_page()
            pg.goto(url, timeout=timeout_ms, wait_until="load")
            pg.wait_for_timeout(1_200)     # hydration frameworks paint late
            pg.add_script_tag(content=_script())
            # runOnly keeps us to the WCAG rulesets; axe's "best-practice"
            # tags are opinions worth reading but not worth scoring a client
            # against without saying so.
            # `rect` per node, and the two page dimensions it is relative
            # to (136j Part B). Document coordinates, not viewport: the
            # overlay is drawn over a full-page screenshot, so a box has to
            # keep its position when the page is scrolled.
            #
            # A zero-area rect is KEPT as zero rather than dropped. An
            # element that is display:none or clipped to nothing is a real
            # violation with a real position - it is simply invisible, which
            # is frequently the defect itself.
            #
            # `target` is an array because axe walks into iframes: the last
            # entry is the selector within the innermost document and the
            # earlier ones are the frames to get there. Only a single-entry
            # target can be resolved from here, so a node inside an iframe
            # gets `rect: null` and the drawing states it rather than
            # guessing a box.
            result = pg.evaluate("""() => axe.run(document, {
                runOnly: { type: 'tag',
                           values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] },
                resultTypes: ['violations'],
            }).then(r => {
                const de = document.documentElement;
                const box = (t) => {
                    if (!t || t.length !== 1) return null;
                    let el = null;
                    try { el = document.querySelector(t[0]); } catch (e) { return null; }
                    if (!el) return null;
                    const b = el.getBoundingClientRect();
                    return { x: Math.round(b.left + window.scrollX),
                             y: Math.round(b.top + window.scrollY),
                             w: Math.round(b.width), h: Math.round(b.height) };
                };
                return {
                    violations: r.violations.map(v => ({
                        id: v.id, impact: v.impact, help: v.help,
                        helpUrl: v.helpUrl, tags: v.tags,
                        nodes: v.nodes.map(n => ({
                            target: n.target, html: (n.html || '').slice(0, 300),
                            failureSummary: n.failureSummary, rect: box(n.target) })),
                    })),
                    viewport: { w: window.innerWidth, h: window.innerHeight },
                    document: { w: Math.max(de.scrollWidth, de.offsetWidth),
                                h: Math.max(de.scrollHeight, de.offsetHeight) },
                    testEngine: r.testEngine,
                    url: r.url,
                    // Item 136q commit 2: the rendered anchor set, taken in
                    // the evaluate that was already running. No extra page
                    // load, and it is the only place the rendered DOM is in
                    // scope. `href` is read off the property rather than the
                    // attribute so the browser has already resolved it
                    // against the page's base - the initial-HTML side is
                    // absolute too, and comparing a resolved URL with a
                    // written one would call every relative link
                    // render-only.
                    anchors: [...document.querySelectorAll('a[href]')]
                        .map(a => ({ url: a.href,
                                     anchor: (a.textContent || '').trim().slice(0, 120) }))
                        .filter(a => a.url && !a.url.startsWith('javascript:')),
                    // Item 136o Part A: every block-level text element, with
                    // where it is and what it says. The hash is NOT computed
                    // here - the raw text is returned and `cnt.content_hash`
                    // hashes it in Python, so there is one normalisation and
                    // it is the one `duplicate-content` and `stale` use.
                    text_blocks: (() => {
                        const NAMED = new Set(['P','LI','H1','H2','H3','H4',
                            'H5','H6','TD','BLOCKQUOTE','FIGCAPTION','DD']);
                        const landmarkOf = (el) => {
                            for (let n = el; n; n = n.parentElement) {
                                const t = n.tagName;
                                if (t === 'HEADER') return 'header';
                                if (t === 'NAV') return 'nav';
                                if (t === 'MAIN') return 'main';
                                if (t === 'FOOTER') return 'footer';
                                if (t === 'ASIDE') return 'aside';
                            }
                            return 'none';
                        };
                        const directText = (el) => {
                            let t = '';
                            for (const n of el.childNodes)
                                if (n.nodeType === 3) t += n.textContent;
                            return t.trim();
                        };
                        const out = [];
                        const walk = document.querySelectorAll('body *');
                        const NAMED_SEL = [...NAMED].join(',').toLowerCase();
                        for (const el of walk) {
                            const tag = el.tagName;
                            const named = NAMED.has(tag);
                            // Once each (item 245): a named element inside
                            // another is already in its text, so counting it
                            // too put a menu item's words in twice - a nav
                            // `li` and every `p` and heading under it.
                            if (named && el.parentElement
                                && el.parentElement.closest(NAMED_SEL)) continue;
                            // `innerText` for a named element (item 245):
                            // `textContent` joins its children with no space,
                            // so "Webdesign" and "About the Design Process"
                            // read as "WebdesignAbout" - one word, miscounted
                            // and misnamed. `innerText` is the text as laid
                            // out for a reader.
                            let text = named
                                ? (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim()
                                : directText(el);
                            if (!named) {
                                const disp = getComputedStyle(el).display;
                                if (disp !== 'block') continue;
                            }
                            const words = text ? text.split(/\\s+/).length : 0;
                            if (words < 3) continue;
                            const r = el.getBoundingClientRect();
                            out.push({
                                tag: tag.toLowerCase(),
                                landmark: landmarkOf(el),
                                words,
                                text: text.slice(0, 2000),
                                rect: { x: Math.round(r.left + window.scrollX),
                                        y: Math.round(r.top + window.scrollY),
                                        w: Math.round(r.width),
                                        h: Math.round(r.height) },
                            });
                        }
                        return out.slice(0, 400);
                    })(),
                };
            })""")
            # After the evaluate, so the picture is of the page axe judged
            # rather than of one that carried on hydrating afterwards.
            if screenshot_to is not None:
                try:
                    screenshot_to.parent.mkdir(parents=True, exist_ok=True)
                    pg.screenshot(path=str(screenshot_to), full_page=True)
                    result["screenshot"] = {
                        "path": screenshot_to.as_posix(),
                        "bytes": screenshot_to.stat().st_size}
                except Exception as exc:                    # noqa: BLE001
                    result["screenshot"] = {
                        "error": f"{type(exc).__name__}: {exc}"[:200]}
            return result
        finally:
            browser.close()


def findings_from(result: dict, page_url: str, path: str) -> list[Finding]:
    """Turn one page's axe result into findings for the A11Y dimension."""
    out: list[Finding] = []
    for v in result.get("violations", []):
        rule = v.get("id") or "unknown"
        if rule in ALREADY_OWNED:
            continue
        nodes = v.get("nodes", [])
        out.append(Finding(
            dimension="A11Y",
            # Namespaced so a rule rename upstream cannot collide with one of
            # our own check ids, and so the source is legible in the history.
            check_id=f"axe-{rule}",
            severity=IMPACT.get((v.get("impact") or "").lower(), Severity.MEDIUM),
            summary=f"{v.get('help') or rule} — {len(nodes)} element(s) on {path}.",
            subject=path,
            affected_urls=[page_url],
            evidence={
                "rule": rule,
                "wcag": sorted(t for t in v.get("tags", []) if t.startswith("wcag")),
                "help_url": v.get("helpUrl"),
                "nodes": [{"target": n.get("target"),
                           "html": n.get("html"),
                           "why": n.get("failureSummary")}
                          for n in nodes[:SAMPLE]],
                "nodes_total": len(nodes),
                # The same two fields the static checks carry (136j Part A),
                # from axe's own nodes, so 136f reads one shape for every
                # check rather than branching on where the row came from.
                # `target` is a list of selectors when the element is inside
                # an iframe; joined, because that IS the path to it.
                "instances": [
                    {"selector": " ".join(n.get("target") or []),
                     "selector_norm": " ".join(n.get("target") or []),
                     "html": (n.get("html") or "")[:INSTANCE_HTML],
                     "landmark": "none",
                     # Absent rather than null where the node is inside an
                     # iframe and could not be resolved: 136f draws the
                     # absent-data state for it, which is different from a
                     # box at the origin.
                     **({"rect": n["rect"]} if n.get("rect") else {})}
                    for n in nodes],
                "count": len(nodes),
            },
            recommendation=(v.get("help") or "")
            + (f" See {v['helpUrl']}." if v.get("helpUrl") else ""),
        ))
    return out


def coverage_note(pages_tested: int, engine: dict | None) -> Finding:
    """What the pass could not see, stated as a finding so it survives into
    the report rather than living only in a log."""
    version = (engine or {}).get("version", "unknown")
    return Finding(
        dimension="A11Y",
        check_id="axe-coverage",
        severity=Severity.INFO, scope_statement=True,
        summary=f"axe-core {version} checked {pages_tested} rendered page(s) "
                "against WCAG 2.0/2.1/2.2 A and AA.",
        subject="site",
        affected_urls=[],
        evidence={"engine": engine, "pages_tested": pages_tested,
                  "rulesets": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
        recommendation="Automated testing reaches roughly a third of WCAG. No "
                       "violations here means none detectable, not none present: "
                       "whether alt text is meaningful, whether focus order makes "
                       "sense, and whether a custom widget can be operated by "
                       "keyboard all still need a person.",
    )
