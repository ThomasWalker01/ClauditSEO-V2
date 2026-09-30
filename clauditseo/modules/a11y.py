"""A11Y — Accessibility dimension.

What a machine can decide from the HTML alone, and nothing more. Barriers
that are structural — a control with no label, a link with no name, a page
with no language — are decidable from markup and belong here. Whether alt
text is *useful*, whether focus order makes sense, whether a custom widget
behaves, are not, and no amount of static analysis will settle them.

The split from ONP is by question, not by tag. ONP already owns
``img-alt-missing``, ``h1-missing`` and ``heading-skip``, and TEC owns
viewport zoom suppression; all four are accessibility failures as much as
SEO ones, and duplicating them here would double-count the same defect in
two dimensions and inflate the deduction. This module covers what nothing
else does.

Colour contrast is deliberately absent. It cannot be computed from HTML —
it needs the cascade resolved against rendered geometry, which is what the
optional axe pass in ``clauditseo.axe`` is for. A page audited without the
renderer is told, in as many words, that contrast was not assessed rather
than being allowed to look clean.
"""

from __future__ import annotations

from collections import Counter

from clauditseo.crawler.types import CrawlResult
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier

from .pagefacts import PageFacts, extract_facts, html_pages

#: Link text that describes the act of clicking rather than the destination.
#: Deliberately short and unambiguous — "more" or "details" alone can be
#: perfectly clear in context, and a checker that cries wolf gets ignored.
GENERIC_LINK_TEXT = {
    "click here", "here", "read more", "learn more", "more", "more info",
    "more information", "this link", "link", "continue", "go", "download",
    "see more", "find out more",
}

#: Controls that carry no user-visible value and need no label of their own.
UNLABELLED_OK = {"hidden", "submit", "reset", "button", "image"}

#: How many pages to name in the evidence before it stops being readable.
SAMPLE = 10

#: How many pages the rendered pass will open, per tier. Rendering costs
#: seconds per page against milliseconds for parsing, so this is a sample and
#: the run says so rather than letting the count pass for coverage.
AXE_PAGE_BUDGET: dict = {Tier.T1: 1, Tier.T2: 5, Tier.T3: 20}


def _spread(facts: list[PageFacts], n: int) -> list[PageFacts]:
    """The homepage plus an even spread of the rest.

    Taking the first N would sample whatever the crawler happened to reach
    first, which is the homepage and its immediate navigation — the pages
    most likely to share one template and least likely to contain the forms
    and tables where barriers concentrate.
    """
    if len(facts) <= n:
        return list(facts)
    rest = facts[1:]
    step = max(1, len(rest) // max(1, n - 1))
    return [facts[0]] + rest[::step][:n - 1]


def _accessible_name(el: dict) -> str:
    """The name a screen reader would announce, as far as static HTML says.

    aria-labelledby wins in the real algorithm but points at another element,
    so its presence is treated as "named" without resolving it — resolution
    is the broken-reference check's job, not this one's.
    """
    if (el.get("aria_labelledby") or "").strip():
        return "(aria-labelledby)"
    return ((el.get("aria_label") or "").strip()
            or (el.get("text") or "").strip()
            or (el.get("title") or "").strip())


def _labelled(control: dict, label_for: set[str]) -> bool:
    if control["type"] in UNLABELLED_OK:
        return True
    if control.get("wrapped_in_label"):
        return True
    if (control.get("aria_label") or "").strip():
        return True
    if (control.get("aria_labelledby") or "").strip():
        return True
    if (control.get("title") or "").strip():
        return True
    return bool(control.get("id") and control["id"] in label_for)


#: The position fields the crawler records per element (136j Part A). One
#: helper rather than six spellings: 136f groups on these, and a check that
#: named them differently would be a group of its own for no reason.
WHERE_FIELDS = ("selector", "selector_norm", "landmark", "html")


def instance(element: dict, **extra) -> dict:
    """One flagged element, as every check reports it.

    An element the crawler could not place still gets an entry - with the
    position fields absent rather than empty. 136f then draws the
    absent-data state for it, which is the honest reading: "this check
    flagged something here and cannot say which element" is different from
    "this element has no selector".
    """
    out = {k: element[k] for k in WHERE_FIELDS if element.get(k)}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def flagged(elements: list[dict], **per) -> dict:
    """`instances` and `count` for a list of flagged elements.

    `count` is `len(elements)` and not `len(instances)` so the two can never
    drift: they are the same list. It exists as a field because it used to
    exist only inside a summary sentence, which meant the only way to read
    it was to parse English.
    """
    keys = per.pop("keys", None)
    rows = [instance(e, **{k: e.get(v) for k, v in (keys or {}).items()})
            for e in elements]
    return {"instances": rows, "count": len(elements)}


def _block_hash(text: str) -> str:
    """One block's words, hashed the way the site-wide index hashes a page.

    `cnt.content_hash`, not a second normalisation (the item is explicit):
    the block classes `shared` and `boilerplate` are `duplicate-content`'s
    data at block grain, and if a block hashed differently here the two would
    disagree about whether two pages carry the same paragraph.
    """
    from clauditseo.modules.cnt import content_hash

    return content_hash(text)


#: How much of a region's text is kept for the Content tab's expanded row
#: (item 245): enough to read what the region says, short of storing every
#: rendered page's body a second time.
BLOCK_EXCERPT_WORDS = 40


def _block_excerpt(text: str) -> str:
    """The region's opening, for the row a reader expands (item 245)."""
    words = (text or "").split()
    return " ".join(words[:BLOCK_EXCERPT_WORDS]) + ("…" if len(words) > BLOCK_EXCERPT_WORDS else "")


def _block_name(text: str) -> str:
    """What a region is called on the overlay: the block's first six words,
    trimmed. Built here, before the raw text is dropped, so the drawing has a
    label without carrying the whole block."""
    words = (text or "").split()
    name = " ".join(words[:6])
    return name + ("…" if len(words) > 6 else "")


class AccessibilityModule:
    code = "A11Y"
    name = "Accessibility"
    default_weight = scoring.DEFAULT_WEIGHTS["A11Y"]
    #: Twelve of fourteen checks name the page they were found on —
    #: `form-control-unlabelled`, `link-name-missing`, `duplicate-id` and the
    #: rest are properties of one document's markup, and re-reading that one
    #: URL re-measures every one of them. `contrast-not-assessed` and
    #: `axe-sampled` are the two site-scoped notes and do not change this:
    #: the question is whether *any* finding can be moved, not whether all
    #: can. See `registry.page_blind_dims`.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        facts = [extract_facts(p) for p in html_pages(crawl.pages)]
        findings: list[Finding] = []
        for f in facts:
            findings += self._page_checks(f)
        findings += self._axe_pass(facts, tier, context)
        findings += self._site_checks(facts, context)
        return findings

    # -- rendered pass -----------------------------------------------------

    def _axe_pass(self, facts: list[PageFacts], tier: Tier,
                  context: dict) -> list[Finding]:
        """Contrast, focus order and everything else the cascade decides.

        Silent when the renderer is absent — the honesty note in
        ``_site_checks`` is what speaks in that case, so a bare install is
        told what it is missing exactly once rather than per page.

        Rendering is far slower than parsing, so this reads a sample rather
        than the whole crawl, and says how many it read. A page that fails to
        render is reported as a page that failed to render; treating it as
        clean would be the worst possible default here.
        """
        if context.get("skip_axe"):
            return []
        from clauditseo import axe
        if not axe.available():
            return []

        budget = AXE_PAGE_BUDGET.get(tier, 5)
        sample = _spread(facts, budget)
        out: list[Finding] = []
        engine: dict | None = None
        tested = 0
        # A picture per rendered page (136j Part B), under the run that took
        # it. Without a run id there is nowhere to put one that retention
        # could later find, so the pass runs exactly as before and the
        # overlay draws its absent-data state - which is what every run
        # taken before this item does anyway.
        run_id = context.get("run_id")
        screens: dict[str, dict] = {}
        rendered: dict[str, list] = {}
        text_blocks: dict[str, list] = {}
        for f in sample:
            shot = (axe.screens_dir(run_id) / f"{axe.page_hash(f.url)}.png"
                    if run_id else None)
            try:
                result = axe.run_page(f.url, screenshot_to=shot)
            except Exception as exc:                       # noqa: BLE001
                out.append(Finding(
                    dimension=self.code, check_id="axe-render-failed",
                    severity=Severity.INFO,
                    summary=f"{f.path} could not be rendered, so its contrast and "
                            "focus order were not checked.",
                    subject=f.path, affected_urls=[f.url],
                    evidence={"error": str(exc)[:300]},
                    recommendation="Open the page in a browser to see whether it "
                                   "loads at all. Until it renders, treat this "
                                   "page as unassessed rather than clean.",
                ))
                continue
            engine = engine or result.get("testEngine")
            tested += 1
            # Item 136q commit 2. The rendered anchor set, handed to TEC
            # through the same context A11Y already uses for `axe_ran`.
            # `core.RUN_FIRST` puts this module ahead of its consumer, so
            # the caller's dimension order cannot decide whether
            # `links-behind-js` can answer.
            rendered[f.url] = result.get("anchors") or []
            # Item 136o Part A. Each block's raw text becomes a `hash` through
            # `cnt.content_hash` - the one normalisation the site-wide index
            # uses - and the raw text is dropped, so what is stored is the
            # rect, the words and the hash and not the page's whole body a
            # second time.
            blocks = result.get("text_blocks") or []
            for blk in blocks:
                raw = blk.pop("text", "") or ""
                blk["name"] = _block_name(raw)
                blk["excerpt"] = _block_excerpt(raw)
                blk["hash"] = _block_hash(raw)
            text_blocks[f.url] = blocks
            shot_meta = result.get("screenshot") or {}
            if shot_meta.get("path"):
                # The page's own dimensions, from the same evaluate that
                # produced the rects, so a box and the image it is drawn on
                # are measured in one coordinate system.
                doc = result.get("document") or {}
                screens[f.url] = {
                    "screenshot_path": shot_meta["path"],
                    "screenshot_w": doc.get("w"),
                    "screenshot_h": doc.get("h"),
                    "bytes": shot_meta.get("bytes"),
                    "page_hash": axe.page_hash(f.url)}
            elif shot_meta.get("error"):
                screens[f.url] = {"screenshot_error": shot_meta["error"]}
            out += axe.findings_from(result, f.url, f.path)

        if tested:
            context["axe_ran"] = True
            # Which pages were rendered, and what each one's DOM linked at.
            # The COUNTS travel with it: `links-behind-js` may only make a
            # site-wide claim when the rendered pass covered the whole crawl,
            # and it cannot work that out from the map alone.
            context["rendered_anchors"] = rendered
            context["rendered_coverage"] = {"rendered": tested,
                                            "pages": len(facts)}
            # Item 136o Part A: the page's text blocks, for the Content
            # overlay to read back and classify.
            context["text_blocks"] = text_blocks
            note = axe.coverage_note(tested, engine)
            if screens or text_blocks:
                note.evidence = {**(note.evidence or {}),
                                 **({"screens": screens} if screens else {}),
                                 **({"text_blocks": text_blocks} if text_blocks else {})}
            out.append(note)
            if len(facts) > tested:
                out.append(Finding(
                    dimension=self.code, check_id="axe-sampled",
                    severity=Severity.INFO, scope_statement=True,
                    summary=f"{tested} of {len(facts)} crawled page(s) were "
                            "rendered for the accessibility pass.",
                    subject="site", affected_urls=[],
                    evidence={"rendered": tested, "crawled": len(facts),
                              "tier": str(tier),
                              # Which pages have a picture, and where. The
                              # overlay needs a page to find its own image
                              # without a second lookup, and this row is
                              # already the one that says what was rendered.
                              "screens": screens,
                              # Item 136o Part A: each rendered page's text
                              # blocks, keyed by url like `screens`. The
                              # Content overlay classifies these at read time
                              # against what the run knows.
                              "text_blocks": text_blocks},
                    recommendation="Rendering is minutes per hundred pages where "
                                   "parsing is seconds, so this pass samples across "
                                   "the crawl. Raise the tier to widen it. "
                                   "Templates repeat, so a barrier found on one "
                                   "page is usually on every page sharing its "
                                   "template — and one missed on an unrendered "
                                   "page is not evidence of its absence.",
                ))
        return out

    # -- per page ----------------------------------------------------------

    def _page_checks(self, f: PageFacts) -> list[Finding]:
        out: list[Finding] = []

        if not (f.lang or "").strip():
            out.append(Finding(
                dimension=self.code, check_id="html-lang-missing",
                severity=Severity.HIGH,
                summary=f"{f.path} does not declare a language on <html>.",
                subject=f.path, affected_urls=[f.url], evidence={},
                recommendation="Add lang to the <html> element (lang=\"en-AU\" for "
                               "Australian English). Without it a screen reader "
                               "reads the page in whatever voice it defaulted to, "
                               "which can make correct text unintelligible.",
            ))

        label_for = set(f.label_for)
        unlabelled = [c for c in f.form_controls if not _labelled(c, label_for)]
        if unlabelled:
            out.append(Finding(
                dimension=self.code, check_id="form-control-unlabelled",
                severity=Severity.HIGH,
                summary=f"{len(unlabelled)} form control(s) on {f.path} have no "
                        "associated label.",
                subject=f.path, affected_urls=[f.url],
                evidence={"controls": [
                    {k: v for k, v in c.items() if v and k not in WHERE_FIELDS}
                    for c in unlabelled[:SAMPLE]],
                    "total_controls": len(f.form_controls),
                    **flagged(unlabelled, keys={"tag": "tag", "name": "name",
                                                "control_id": "id"})},
                recommendation="Give each control a <label for> matching its id, or "
                               "wrap it in a <label>. A placeholder is not a label: "
                               "it disappears on input and is not announced by every "
                               "screen reader.",
            ))

        nameless = [ln for ln in f.links
                    if ln.get("href") and not _accessible_name(ln)]
        if nameless:
            out.append(Finding(
                dimension=self.code, check_id="link-name-missing",
                severity=Severity.HIGH,
                summary=f"{len(nameless)} link(s) on {f.path} have no accessible name.",
                subject=f.path, affected_urls=[f.url],
                evidence={"hrefs": [ln["href"] for ln in nameless[:SAMPLE]],
                          "total_links": len(f.links),
                          **flagged(nameless, keys={"href": "href"})},
                recommendation="Give the link visible text, or an aria-label when it "
                               "is an icon. An icon-only link with no name is "
                               "announced as its URL, one character at a time.",
            ))

        generic = [ln for ln in f.links
                   if _accessible_name(ln).lower().strip(" .:→>»") in GENERIC_LINK_TEXT]
        if generic:
            out.append(Finding(
                dimension=self.code, check_id="link-text-generic",
                severity=Severity.LOW,
                summary=f"{len(generic)} link(s) on {f.path} describe the click "
                        "rather than the destination.",
                subject=f.path, affected_urls=[f.url],
                evidence={"examples": [
                    {"text": _accessible_name(ln), "href": ln.get("href")}
                    for ln in generic[:SAMPLE]],
                    **flagged(generic, keys={"href": "href", "text": "text"})},
                recommendation="Name the destination in the link itself. Screen "
                               "reader users commonly navigate by pulling up a list "
                               "of every link on the page, where fourteen entries "
                               "reading \"read more\" are indistinguishable.",
            ))

        anon_buttons = [b for b in f.buttons if not _accessible_name(b)]
        if anon_buttons:
            out.append(Finding(
                dimension=self.code, check_id="button-name-missing",
                severity=Severity.HIGH,
                summary=f"{len(anon_buttons)} button(s) on {f.path} have no "
                        "accessible name.",
                subject=f.path, affected_urls=[f.url],
                evidence={"total_buttons": len(f.buttons)},
                recommendation="Give the button text, or an aria-label describing "
                               "what it does — not what it looks like.",
            ))

        dupes = {i: n for i, n in Counter(f.ids).items() if n > 1}
        if dupes:
            out.append(Finding(
                dimension=self.code, check_id="duplicate-id",
                severity=Severity.MEDIUM,
                # Elements first, ids second. 136j's agreement rule is that
                # `count` equals what the summary says, and `count` is the
                # number of ELEMENTS because that is what gets fixed - three
                # divs sharing one id are three edits. The old wording said
                # "1 id(s)" for that case and would have made the two
                # disagree by construction.
                summary=f"{sum(dupes.values())} element(s) on {f.path} share "
                        f"{len(dupes)} duplicated id(s).",
                subject=f.path, affected_urls=[f.url],
                evidence={"ids": dict(list(dupes.items())[:SAMPLE]),
                          # Every element carrying a repeated id, not one
                          # entry per id: the fix is per element, and a
                          # count of ids would say 1 where three elements
                          # share one.
                          **flagged([d for d in f.id_where if d["id"] in dupes],
                                    keys={"element_id": "id"})},
                recommendation="Make every id unique. label/for and every aria "
                               "reference resolve to the first match, so a repeat "
                               "silently points the wrong control at the wrong text.",
            ))

        declared = set(f.ids)
        broken = [(attr, ref) for attr, ref in f.aria_refs if ref not in declared]
        if broken:
            out.append(Finding(
                dimension=self.code, check_id="aria-reference-broken",
                severity=Severity.MEDIUM,
                summary=f"{len(broken)} aria reference(s) on {f.path} point at an "
                        "id that does not exist.",
                subject=f.path, affected_urls=[f.url],
                evidence={"refs": [f"{a}={r}" for a, r in broken[:SAMPLE]]},
                recommendation="Point each aria-labelledby/describedby/controls at a "
                               "real id. A dangling reference is worse than none: it "
                               "suppresses the fallback name the element would "
                               "otherwise have had.",
            ))

        positive = [t for t in f.tabindexes if t.strip().lstrip("+").isdigit()
                    and int(t) > 0]
        if positive:
            out.append(Finding(
                dimension=self.code, check_id="tabindex-positive",
                severity=Severity.MEDIUM,
                summary=f"{len(positive)} element(s) on {f.path} use a positive "
                        "tabindex.",
                subject=f.path, affected_urls=[f.url],
                evidence={"values": sorted(set(positive))[:SAMPLE]},
                recommendation="Use tabindex=\"0\" and fix the source order instead. "
                               "A positive value pulls the element to the front of "
                               "the whole page's tab sequence, ahead of everything "
                               "with no tabindex at all.",
            ))

        untitled = [i for i in f.iframes
                    if not (i.get("title") or "").strip()
                    and not (i.get("aria_label") or "").strip()]
        if untitled:
            out.append(Finding(
                dimension=self.code, check_id="iframe-title-missing",
                severity=Severity.MEDIUM,
                summary=f"{len(untitled)} iframe(s) on {f.path} have no title.",
                subject=f.path, affected_urls=[f.url],
                evidence={"srcs": [i["src"][:120] for i in untitled[:SAMPLE]]},
                recommendation="Title each iframe with what it contains (\"Booking "
                               "form\", \"Location map\"). Untitled frames are "
                               "announced only as \"frame\".",
            ))

        # A table with rows but no header cells is either a data table missing
        # its headers or a layout table that should say so.
        headerless = [t for t in f.tables
                      if t["rows"] > 1 and t["th"] == 0 and t.get("role") != "presentation"]
        if headerless:
            out.append(Finding(
                dimension=self.code, check_id="table-headers-missing",
                severity=Severity.MEDIUM,
                summary=f"{len(headerless)} table(s) on {f.path} have data rows but "
                        "no header cells.",
                subject=f.path, affected_urls=[f.url],
                evidence={"tables": headerless[:SAMPLE]},
                recommendation="Use <th> for header cells, or role=\"presentation\" "
                               "if the table is only there for layout. Without "
                               "headers each cell is read with no indication of "
                               "which column it belongs to.",
            ))

        if not (f.landmarks & {"main", "role=main"}):
            out.append(Finding(
                dimension=self.code, check_id="landmark-main-missing",
                severity=Severity.LOW,
                summary=f"{f.path} has no <main> landmark.",
                subject=f.path, affected_urls=[f.url],
                evidence={"landmarks_present": sorted(f.landmarks),
                          # Zero, by construction - this row exists because
                          # no main was found. Stated as a field anyway so
                          # 136f reads one shape for every check, and so a
                          # later "more than one main" row can use the same
                          # one without a second spelling.
                          "instances": [{"landmark": name} for name in sorted(f.landmarks)],
                          "count": 0},
                recommendation="Wrap the primary content in <main>. It is what "
                               "\"skip to content\" and screen-reader region "
                               "navigation jump to.",
            ))

        return out

    # -- whole site --------------------------------------------------------

    def _site_checks(self, facts: list[PageFacts], context: dict) -> list[Finding]:
        """One honesty finding, not a check: say plainly which barriers this
        run could not look for. Silence here would let a page with unreadable
        text score clean on accessibility."""
        if not facts:
            return []
        if context.get("axe_ran"):
            return []
        return [Finding(
            dimension=self.code, check_id="contrast-not-assessed",
            severity=Severity.INFO, scope_statement=True,
            summary="Colour contrast, focus order and reading order were not "
                    "assessed — this run had no renderer.",
            subject="site", affected_urls=[],
            evidence={"pages_checked": len(facts),
                      "needs": "pip install clauditseo[render], "
                               "then playwright install chromium"},
            recommendation="These need the page rendered, not just its HTML. "
                           "Install the renderer to add the axe pass; until then "
                           "treat this dimension as a floor, not a clearance.",
        )]

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # Wholly page-derived: every check here reads a fetched page, so a
        # crawl that fetched none measured none of this dimension.
        return scoring.subscore(self.code, findings, self.default_weight, context,
                                coverage=scoring.page_coverage(context))


registry.register(AccessibilityModule())
