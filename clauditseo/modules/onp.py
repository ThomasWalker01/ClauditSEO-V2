"""ONP — On-Page dimension.

Title and meta quality and duplication, heading hierarchy, image alt
coverage, canonical correctness per page, structured-data validity.
Duplicate-title groups double as the string-level cannibalisation signal;
the meaning-level call is the ONP-J analyst's job (P5).
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from clauditseo.crawler.crawl import normalise_url
from clauditseo.crawler.types import CrawlResult
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier
from clauditseo.textmetrics import DESC_FONT, TITLE_FONT
from clauditseo import schema_graph

from .pagefacts import (PageFacts, _links_home, extract_facts, html_pages,
                        identify_logo, mark_template_blocks, mark_template_images,
                        position_key, schema_inventory, schema_logo)

TITLE_MIN, TITLE_MAX = 10, 65
#: Brief v12 step AL: the window a replacement title is written to - the
#: Title & description prompt's own default. Narrower than the sweep's
#: flagging bounds above, which only catch the extremes: a 19-character
#: title is not a sweep finding, but it is not a replacement either.
TITLE_TARGET_MIN, TITLE_TARGET_MAX = 30, 60
#: The title ceiling under the `neighbourhood` strategy on location and
#: service pages - the prompt's soft ceiling.
TITLE_NEIGHBOURHOOD_MAX = 240
#: Brief v10 step AG: the description's window, the one the Title &
#: description brief writes replacements to. WARN outside it - a low
#: severity, since a long description is truncated rather than lost.
DESC_MIN, DESC_MAX = 120, 160

#: What the length checks measure since brief v16i: PIXELS, not characters
#: (operator ruling, 2026-09-07, option a).
#:
#: A character count was never the thing that mattered. `Illinois` and
#: `WWWWWWWW` are both eight characters and one is nearly twice as wide, so a
#: title passing at 60 characters could be cut and one failing at 66 could
#: fit. What a search result cuts is a WIDTH, so a width is what is measured.
#:
#: The four numbers are the item's, against a rendered preview. Measurement is
#: `textmetrics.text_px`, and the part page's snippet card reads the same
#: function - the picture and the finding cannot disagree about where a title
#: is cut.
TITLE_PX_DESKTOP, TITLE_PX_MOBILE, DESC_PX = 600, 410, 920

#: The character bounds these replaced, kept for one release so the migration
#: is comparable (the item asks for this). Nothing reads them to decide a
#: finding; they are here to be diffed against, and the release that removes
#: them removes this comment with it.
#: Only the MAXIMA were replaced. `TITLE_MIN` and `DESC_MIN` are retained,
#: not superseded, and carry no `_legacy` suffix: the short side still
#: measures characters, because adequacy is not a width fact.
TITLE_MAX_LEGACY, DESC_MAX_LEGACY = TITLE_MAX, DESC_MAX

#: The registered default severity of every check this module emits (brief
#: v11 step AH). One source: the emitters below read it, the contract
#: writes it onto a brief's row where the brief's value is lower or
#: missing, and the prompt is told it in SWEEP RESULTS.
DEFAULT_SEVERITY: dict[str, Severity | dict[str, Severity]] = {
    "title-missing": Severity.HIGH, "title-length": Severity.LOW,
    "title-duplicate": Severity.MEDIUM,
    # Medium by the operator's registry of 2026-09-04 (brief v11 step AI);
    # it was Low when the check joined the sweep at v10 step AG.
    "meta-desc-missing": Severity.MEDIUM, "meta-desc-length": Severity.MEDIUM,
    "meta-desc-duplicate": Severity.LOW,
    "h1-missing": Severity.MEDIUM, "h1-multiple": Severity.LOW,
    # Raised from Low to Medium - the operator's call (brief v11 step AI).
    "heading-skip": Severity.MEDIUM, "img-alt-missing": Severity.MEDIUM,
    "canonical-missing": Severity.LOW, "canonical-mismatch": Severity.MEDIUM,
    # Q-54. INFO weighs 0.0 in `scoring.SEVERITY_WEIGHTS`, so the
    # parameter grade is unscored by construction and not by a second
    # list that would have to be kept in step with this one.
    "canonical-mismatch-trailing-slash": Severity.LOW,
    "canonical-mismatch-parameter": Severity.INFO,
    "canonical-off-host": Severity.MEDIUM,
    # Item 136q commit 5.
    "title-entity-incomplete": Severity.MEDIUM,
    "canonical-missing-variant": Severity.MEDIUM, "jsonld-invalid": Severity.MEDIUM,
    "schema-deprecated-rich-result": Severity.HIGH,
    # Brief-only checks (brief v11 step AI): no emitter in the sweep; the
    # Title & description and Headings briefs raise them, and the registry
    # is where their default severity lives. A dict is a default per
    # status where the brief's FAIL and WARN mean different things.
    "title-entity-alignment": Severity.MEDIUM,
    "h1-triple-restated": {"FAIL": Severity.HIGH, "WARN": Severity.LOW},
    "h1-title-verbatim": Severity.MEDIUM, "h2-support": Severity.MEDIUM,
    "h2-location-service": Severity.MEDIUM, "h2-overstuffed": Severity.MEDIUM,
    "h2-question-unanswered": Severity.MEDIUM, "h3-sub-service": Severity.MEDIUM,
    "h3-geo-map": Severity.MEDIUM,
    "h1-brand-repeated": Severity.LOW, "h1-hook": Severity.LOW,
    # The Images brief's own set (brief v15 step AQ), at the severities its
    # prompt states. Eight of these the sweep computes from the stored
    "img-lcp-lazy": Severity.HIGH, "img-weight-budget": Severity.HIGH,
    "img-dimensions-missing": Severity.MEDIUM, "img-oversized": Severity.MEDIUM,
    "img-no-srcset": Severity.MEDIUM, "img-sizes-wrong": Severity.MEDIUM,
    "img-legacy-format": Severity.MEDIUM, "img-text-in-image": Severity.MEDIUM,
    "img-duplicate-links": Severity.MEDIUM,
    "img-link-alt-not-destination": Severity.MEDIUM,
    "img-alt-decorative-nonempty": Severity.LOW, "img-filename-generic": Severity.LOW,
    "img-sitemap-missing": Severity.LOW,
    # The one header image that is not decorative (brief v16 step AU6).
    # One row per site, carrying every sub-finding one replacement closes.
    "img-logo": Severity.MEDIUM,
    # One image too heavy for what it shows (brief v16 step AU7). The page
    # budget is a budget for a page, so a heavy image below the fold of an
    # otherwise light page sits inside it and says nothing.
    "img-heavy": Severity.MEDIUM,
    # The Structured data brief's own set (brief v16 step AS), at the
    # severities its prompt states. `schema-deprecated-rich-result`
    # existed already and keeps its name and its part.
    #
    # The last two are registered MEDIUM and the prompt's note is why
    # they read as held rather than open: `schema-triple-mismatch` is
    # held until the site record carries a GBP category and a location,
    # and `schema-review-unsupported` until review provenance is
    # confirmed - except where the markup is already on the page, which
    # is a FAIL at the registered severity. A severity is what a row
    # weighs when it is raised; whether it may be raised at all is the
    # parser's question, not this table's.
    "schema-invalid-json": Severity.HIGH,
    "schema-hidden-markup": Severity.HIGH,
    "schema-id-inconsistent": Severity.HIGH,
    "schema-missing-for-type": Severity.MEDIUM,
    "schema-required-missing": Severity.MEDIUM,
    "schema-subtype-shallow": Severity.MEDIUM,
    "schema-orphan-instance": Severity.MEDIUM,
    # Item 215: the orphan check held, because no @id is evidently the canon.
    "schema-orphan-not-assessed": Severity.INFO,
    "schema-redundant-block": Severity.MEDIUM,
    "schema-nap-mismatch": Severity.MEDIUM,
    "schema-author-missing": Severity.MEDIUM,
    "schema-datemodified-missing": Severity.MEDIUM,
    "schema-id-page": Severity.MEDIUM,
    "schema-entity-model": Severity.MEDIUM,
    "schema-graph-wiring": Severity.MEDIUM,
    "schema-catalog-mismatch": Severity.MEDIUM,
    "schema-sameas-misplaced": Severity.MEDIUM,
    # An island is a top-level node no resolved `@id` reference connects
    # to a *different* top-level node, in either direction (brief v16a,
    # RENDER_RULES section 6). INFO because it is a reading of the shape
    # rather than a judgement about it: a `SpeakableSpecification` sitting
    # on its own is a fact, and whether it should be wired to something is
    # the brief's question. Silence would be worse than an INFO row - a
    # page whose blocks do not point at each other looks, in the record,
    # exactly like one whose blocks do.
    "schema-island": Severity.INFO,
    "schema-sameas-missing": Severity.LOW,
    "schema-breadcrumb-missing": Severity.LOW,
    "schema-entity-thin": Severity.LOW,
    "schema-triple-mismatch": Severity.MEDIUM,
    "schema-review-unsupported": Severity.MEDIUM,
    # `img-review-schema` stood here until brief v16 step AS. It was
    # Review/AggregateRating markup for reviews whose provenance is not
    # confirmed, which is exactly `schema-review-unsupported` on the
    # Structured data part - one check in two parts is two answers to one
    # question, and the Images part keeps the case that is genuinely its
    # own: text baked into pixels, `img-text-in-image`.
}

#: A check that can only ever be held, and the input it is held for. The
#: parser drops a row for one with a reason (brief v15 step AQ); the
#: registry keeps it so the part page can list it and say what it needs.
#:
#: The value is carried here rather than left to whichever brief happens to
#: mention the check, because the page must be able to say why the check is
#: held on a site whose brief has never run - which is the state every site
#: is in before the first run, and the state Birch was in when the part page
#: reported `img-review-schema` among the checks that pass.
#: **Empty since brief v16 step AS, and the mechanism stays.** Its one
#: member was `img-review-schema`, retired when the Structured data brief
#: took the question over. What the mechanism does - stand a card for a
#: check that can never be raised, and keep it out of the line that says
#: which checks pass - was written because Birch's part page reported
#: `6 checks pass on this page: ... img-review-schema ...` about a check
#: no engine can run. That defect is a property of held-only checks rather
#: than of that one, and the next one registered here gets the card
#: without anybody having to rediscover why it needs one.
HELD_ONLY_NEEDS: dict[str, str] = {}

HELD_ONLY_CHECKS = tuple(HELD_ONLY_NEEDS)

#: Item 240. Checks only the browser image pass can raise: each needs a
#: weight, a rendered size or a paint the HTML does not carry. A run that
#: took no image pass on a page - every refresh and verify - has not looked
#: for them there, so it may not clear them (`runs.measured`).
IMAGE_DERIVED_CHECKS: frozenset[str] = frozenset({
    "img-heavy", "img-oversized", "img-weight-budget", "img-lcp-lazy"})

#: Item 240. Checks that are a property of the whole crawl though a finding
#: names one page: a duplicate needs the other page, a missing canonical on a
#: variant needs the variant. Only a site-reading run of the dimension can
#: say one is gone; a one-page refresh "fixed" them and the next audit raised
#: a false regression.
CROSS_PAGE_CHECKS: frozenset[str] = frozenset({
    "title-duplicate", "meta-desc-duplicate", "canonical-missing-variant"})

#: The checks above the sweep never emits: a brief's alone.
#:
#: The Images half of this list is what the stored inventory cannot answer
#: (brief v15 step AQ). The crawl reads HTML and fetches no assets, so it
#: has no file weight, no rendered width at a breakpoint, no CSS and no
#: OCR - and a check that needs one of those cannot be computed from the
#: inventory however the sweep is written. `img-oversized`,
#: `img-weight-budget` and `img-sizes-wrong` need measurements no crawl
#: here takes; `img-text-in-image` needs OCR or judgement;
#: `img-link-alt-not-destination` and `img-sitemap-missing` need a reading
#: of the destination and of the image sitemap that the crawl does not
#: keep. They are registered so the brief's rows land under them.
BRIEF_ONLY_CHECKS = ("title-entity-alignment", "h1-triple-restated", "h1-title-verbatim",
                     "h1-brand-repeated", "h1-hook", "h2-support", "h2-location-service",
                     "h2-overstuffed", "h2-question-unanswered", "h3-sub-service", "h3-geo-map",
                     "img-oversized", "img-weight-budget", "img-sizes-wrong",
                     "img-text-in-image", "img-link-alt-not-destination",
                     "img-sitemap-missing",
                     # The Structured data checks no crawl can answer (brief
                     # v16 step AS). Each needs a judgement rather than a
                     # reading: whether a subtype is deeper *and accurate*;
                     # whether a profile is one the entity controls; whether
                     # a property has a visible counterpart on the page;
                     # whether the entity's shape matches the business;
                     # whether a service catalogue matches the site; and
                     # whether a rating traces to a review anyone can see.
                     "schema-subtype-shallow", "schema-sameas-missing",
                     "schema-hidden-markup", "schema-author-missing",
                     "schema-id-page", "schema-triple-mismatch",
                     "schema-entity-model", "schema-entity-thin",
                     "schema-catalog-mismatch", "schema-review-unsupported")

# Published to the dashboard so the page-facts panel judges a value by the
# same threshold that scores it. The panel used to carry its own copy — 30-60
# for a title against this module's 10-65 — so a 62-character title was
# marked "likely truncated" on screen while passing the check that counts.
#
# `check` names the check that enforces the range, or is None where the
# guideline is advice only: nothing here measures description length, and a
# panel that grades against a rule the audit does not apply is inventing a
# finding the score will never agree with.
GUIDELINES: dict[str, dict] = {
    # `max_px` is what the check enforces since brief v16i; `min`/`max` are
    # the character bounds it replaced, kept for one release so the migration
    # is comparable. Both travel on every row - the item asks for that, and it
    # is what makes the delta readable rather than asserted.
    "title": {"min": TITLE_MIN, "max": TITLE_MAX, "check": "title-length",
              "max_px": TITLE_PX_DESKTOP, "mobile_px": TITLE_PX_MOBILE,
              "font": TITLE_FONT, "fires": "mobile"},
    # `fires` is the viewport whose width the check fires at (item 152,
    # operator's decision A, 2026-09-13): mobile-first indexing means the
    # mobile result is what a searcher sees, so a title cut at 410 px on a
    # phone is the fault, and the desktop width travels in the evidence as
    # the parity note. The description stays on desktop until its mobile
    # width is measured the way `DESC_PX` was - `mobile_px` None means
    # there is no mobile cut to fire at, not that it equals desktop.
    "meta_description": {"min": DESC_MIN, "max": DESC_MAX,
                         "check": "meta-desc-length", "max_px": DESC_PX,
                         "mobile_px": None, "font": DESC_FONT, "fires": "desktop"},
}


def cut_of(guide: dict) -> tuple[int, str, int | None, str | None]:
    """The width a length check fires at and its viewport, then the other
    viewport's width (or None) and name - read by `_length_row`, `snippet` and
    the strips' payload, so the finding, the card and the strip cannot cut at
    two different widths (item 152)."""
    if guide.get("fires") == "mobile" and guide.get("mobile_px"):
        return guide["mobile_px"], "mobile", guide["max_px"], "desktop"
    return guide["max_px"], "desktop", guide.get("mobile_px"), (
        "mobile" if guide.get("mobile_px") else None)



#: A filename that names nothing: a camera's, a counter's, a hash, or a
#: draft marker. Matched on the stem alone, so `hero-final-v3.jpg` is
#: caught by the marker and `birch-events-hero.jpg` is not.
_GENERIC_NAME = re.compile(
    r"^(img|image|imag|dsc|dscn|pxl|photo|picture|screenshot|screen[-_ ]?shot|untitled|"
    r"final|draft|copy|new|temp|tmp|asset|file|banner|pic)[-_ ]?\d*$"
    r"|^[0-9]{3,}$|^[a-f0-9]{16,}$|[-_](final|draft|copy|v\d+|new)\d*$", re.I)

#: Formats a photograph should not still be delivered in when AVIF and
#: WebP are available everywhere the product supports.
_LEGACY_FORMATS = {"jpg", "jpeg", "png", "gif", "bmp", "tiff"}

#: An icon by its own declared size: too small to carry meaning, so an alt
#: that describes it is noise between a screen reader and the page.
_ICON_PX = 48


def _src_stem(src: str) -> str:
    name = (src or "").split("?")[0].split("#")[0].rstrip("/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0]


def _src_format(src: str) -> str:
    name = (src or "").split("?")[0].split("#")[0]
    return name.rsplit(".", 1)[-1].lower() if "." in name.rsplit("/", 1)[-1] else ""


#: The smallest file the bytes-per-pixel rule will speak about (brief
#: v16 step AU7, narrowed after reading Birch). Below this a badly encoded
#: image is a badly encoded thumbnail, and re-encoding it saves bytes
#: nobody can measure on a connection.
#:
#: A stated parameter since 2026-09-06, by the operator's decision: it is
#: on the site record as `budget_image_floor_kb` and in `images.md`'s
#: description of the check, because a rule the product applies and tells
#: nobody about is a rule an operator cannot argue with. This is the
#: default the record overrides.
PER_PIXEL_FLOOR_KB = 20


#: The flat per-image ceiling, and the bytes-per-pixel ceiling, where the
#: site record names neither. Written once here because two readers now
#: apply them - `img-heavy` below, and the Images part page's budget
#: blocks, which draw the same decision as a picture (brief v16c). A
#: default spelled twice is how a chart comes to disagree with the finding
#: it is drawn beside.
BUDGET_IMAGE_KB = 300
BYTES_PER_PIXEL_CAP = 1.0


def image_weight_state(weight_kb: float | int | None, pixels: int,
                       budget_image_kb: float | int = BUDGET_IMAGE_KB,
                       per_pixel_cap: float = BYTES_PER_PIXEL_CAP,
                       floor_kb: float | int = PER_PIXEL_FLOOR_KB,
                       ) -> tuple[str, float | None]:
    """Whether one image is too heavy for what it shows, and by how much.

    The whole of `img-heavy`'s decision, lifted out of the check at brief
    v16c so the scatter on the Images part page can call it rather than
    re-derive it. The item's rule is that the dot and the finding must
    never disagree, and the only way to hold that is one function: a
    second implementation of "over budget" agrees on the day it is written
    and on no later one.

    Returns `(state, bytes_per_pixel)`, where state is one of:

    `"unmeasured"` - no weight. **Zero counts as no weight**, which is not
    a rounding decision: `imaging._RESOURCES_JS` reads `encodedBodySize ||
    transferSize || 0`, and a cross-origin image served without
    `Timing-Allow-Origin` reports both as 0, so a stored `weight_kb` of 0
    is the browser saying it could not see the bytes. The check has always
    read it that way - `if weight and ...` - and this is that line, not a
    new rule.

    `"over"` - over the flat ceiling, or over the per-pixel ceiling with a
    weight at or above the floor. Either arm is enough, and this is where
    `img-heavy` fires.

    `"unscored"` - under the floor and not over either ceiling: a badly
    encoded thumbnail, which is nothing an operator could act on. The
    order matters and is deliberate. Over wins, so an operator who sets a
    flat ceiling *below* the floor still sees the dot for the finding the
    check raises; reading the floor first would draw that image as
    unscored while the check named it, which is exactly the disagreement
    the shared function exists to prevent.

    `"ok"` - measured, at or above the floor, inside both ceilings.

    `pixels` is the rendered box the image is drawn at, `w * h`, and is 0
    where no browser measured one. The per-pixel arm then cannot apply and
    the flat ceiling decides alone, which is what the check did inline.
    """
    if not weight_kb:
        return "unmeasured", None
    per_pixel = round(weight_kb * 1024 / pixels, 2) if pixels else None
    over = (weight_kb > budget_image_kb
            or (per_pixel is not None and per_pixel > per_pixel_cap
                and weight_kb >= floor_kb))
    if over:
        return "over", per_pixel
    return ("unscored" if weight_kb < floor_kb else "ok"), per_pixel


#: How many rungs the page-scope outline ladder draws before it says it has
#: stopped (brief v16d). Forty is the item's number and it is above what the
#: crawl keeps on the overwhelming majority of pages: Acme's 227-page run
#: of 2026-09-06 stores a median of 14 headings a page and 60 on its widest,
#: and `OUTLINE_KEPT` on the client is 60. A ladder past forty rungs is a
#: page you scroll rather than a shape you read.
OUTLINE_RUNGS = 40


def heading_outline_state(headings) -> dict:
    """One page's heading outline, and which rungs of it the checks fire on.

    The whole of `h1-missing`, `h1-multiple` and `heading-skip`'s decision,
    lifted out of the check at brief v16d so the ladder on the Headings part
    page can call it rather than re-derive it. The item's rule is that the
    outline and the findings must never disagree, and the only way to hold
    that is one function: the part page had a second implementation of both
    rules inline in `HeadingsNow` - `previous && line.level > previous + 1`
    and a running `seenH1` - and a second implementation agrees on the day it
    is written and on no later one.

    `headings` is the stored per-page list, `(level, text)` as the parser
    recorded it. Rows may carry more than two members: `page_facts` serves
    the richer `outline` - level, text, whether the heading sits in the main
    region, the words after it - and the third member rides through onto the
    rung so the ladder can dim what sits outside `<main>` as the list it
    replaces did. Nothing here re-extracts: the sweep walked the document
    once and this reads what it wrote.

    Returns:

    `rungs` - what to draw, in page order and including the ones that are not
    headings at all. Each is `kind`, `level`, `text`, `state` and `index`:

      * `kind="heading"` - a heading the parser saw. `index` is its position
        in `headings`, which is what `heading-skip` stores as
        `outline_index`, so a rung and a finding name the same thing.
      * `kind="gap"` - a level nothing on the page occupies, at the position
        the missing level would have taken. **One per skipped level**, so
        H2→H5 draws two; `for_index` is the heading that skipped, so a gap
        and the finding about it can be joined.
      * `kind="no-h1"` - drawn once, before everything, where the page has
        no H1 at all.

    `state` is `ink` where nothing is wrong, `warn` for a gap and for the
    second and later H1s, `bad` for the absent H1 - the four tokens the item
    names, decided here rather than in the renderer.

    `fires` is what the checks raise on this page, and it is the half that
    must not drift: `h1-missing` and `h1-multiple` as booleans, and
    `heading-skip` as the **first** skip alone or None. First alone is not a
    simplification - the check has always broken out of its loop after one,
    so a page skipping twice is one finding - and reporting every skip here
    would make the ladder disagree with the record on the second one. Every
    skip is still in `skips`, because the ladder draws the page and not the
    finding list, and `test_the_outline_and_the_checks_agree` compares the
    two at the page level, which is the level at which they are the same
    claim.
    """
    rows = [r for r in (headings or []) if r is not None and len(r) >= 2]
    levels = [int(r[0]) for r in rows]
    h1s = [i for i, lvl in enumerate(levels) if lvl == 1]
    h1_texts = [str(rows[i][1] or "") for i in h1s]
    skips = [{"from": prev, "to": cur, "index": i + 1}
             for i, (prev, cur) in enumerate(zip(levels, levels[1:]))
             if cur > prev + 1]

    rungs: list[dict] = []
    if rows and not h1s:
        rungs.append({"kind": "no-h1", "level": 1, "text": "no H1 on this page",
                      "state": "bad", "index": None})
    seen_h1 = 0
    previous = None
    for i, row in enumerate(rows):
        level = levels[i]
        if previous is not None and level > previous + 1:
            for missing in range(previous + 1, level):
                rungs.append({"kind": "gap", "level": missing,
                              "text": f"H{missing} skipped", "state": "warn",
                              "index": None, "for_index": i})
        if level == 1:
            seen_h1 += 1
        rungs.append({
            "kind": "heading", "level": level, "text": str(row[1] or ""),
            # A rung is warn where a check names it: the heading that skipped,
            # and the second and later H1s. The first H1 of a page with three
            # is not the fault and is not marked as one.
            "state": ("warn" if (previous is not None and level > previous + 1)
                                or (level == 1 and seen_h1 > 1) else "ink"),
            "index": i,
            "in_main": row[2] if len(row) > 2 else None,
        })
        previous = level

    return {
        "rungs": rungs, "levels": levels, "h1s": len(h1s),
        "h1_texts": h1_texts, "skips": skips,
        # **A page with no headings at all is an `h1-missing` page**, which
        # is what `if not h1s:` has always said and is not softened here:
        # the ladder's own answer to that page is a sentence rather than an
        # empty ladder, and it is a sentence about a finding that exists.
        "fires": {"h1-missing": not h1s,
                  "h1-multiple": len(h1s) > 1,
                  "heading-skip": skips[0] if skips else None},
    }


def skip_shape(skip: dict | None) -> str | None:
    """How one skip reads on the site-scope table: `H2 → H4`.

    Here rather than in the renderer for `heading_outline_state`'s reason -
    the row's label and the finding's summary are the same claim about the
    same pair of levels, and the payload that groups 226 pages by shape has
    to spell it the way the check does.
    """
    if not skip:
        return None
    return f"H{skip['from']} → H{skip['to']}"


#: How far a canonical walk follows the trail before it gives up (brief
#: v16g). Five is the item's number and it is far past anything a site does
#: on purpose: Acme's 227-page run of 2026-09-06 has no chain longer than
#: one hop, and a chain a crawler will not follow past two is already the
#: finding. The cap exists for the pathological case, and a walk that hits
#: it is `bad` for the same reason a loop is - it never reached a page that
#: owns itself.
CANONICAL_HOPS = 5


def canonical_relation(path: str, canonical: str | None,
                       url: str = "") -> str:
    """What one page's `rel=canonical` says about the page itself.

    **The single decision both the canonical checks and the chain picture
    read**, lifted out of `_page_checks` at brief v16g for
    `heading_outline_state`'s reason: the item's rule is that a chain's
    colour and the finding beside it must never disagree, and one function
    is the only way to hold that. The block below the checks used to have
    no implementation at all; giving it a second one would have agreed on
    the day it was written and on no later one.

    Returns one of six words, and the four that are not `elsewhere` or
    `missing` raise nothing - which is exactly what fired before this
    function existed:

      * `missing`  - no canonical tag. Raises `canonical-missing`.
      * `blank`    - a tag with nothing in it. Raised nothing then and
        raises nothing now; `f.canonical.strip()` guarded the old branch.
      * `self`     - the page canonicalises to itself.
      * `variant-slash` / `variant-parameter` - the target differs from
        the page only by a trailing slash, or only by the query string.
        The old check compared `urlsplit(...).path` with `rstrip("/")` on
        both sides, so neither difference ever reached it.

        One word until Q-54, which grades them differently: a slash
        variant is nearly always an accident and a parameter variant is
        usually deliberate. The branches always knew which was which and
        the return value threw it away, so the caller could not have told
        them apart however carefully it read.
      * `off-host` - same path, different host. **Also raised nothing**,
        for the same reason: the old comparison never looked at the host.
        This is a real gap in the check and it is named here rather than
        closed, because closing it would change what fires and brief v16g
        stops before that. See
        `test_an_off_host_canonical_is_the_one_kind_no_check_answers`.
      * `elsewhere`- the target is a different path. Raises
        `canonical-mismatch`.

    `url` is the page's own URL where the caller has it. Without it the
    host and the query cannot be compared and the answer degrades to what
    the path alone can say, which is what the check itself did.
    """
    if canonical is None:
        return "missing"
    if not canonical.strip():
        return "blank"
    split = urlsplit(canonical)
    canon_path = split.path or "/"
    here = path or "/"
    if canon_path.rstrip("/") != here.rstrip("/"):
        return "elsewhere"
    # Everything past this point compares equal on the path, which is where
    # the check has always stopped. None of it fires.
    page = urlsplit(url) if url else None
    if (page is not None and split.netloc and page.netloc
            and not same_site_host(split.netloc, page.netloc)):
        return "off-host"
    if canon_path != here:
        return "variant-slash"               # a trailing slash and nothing else
    if page is not None and split.query != page.query:
        return "variant-parameter"           # a parameter and nothing else
    return "self"


#: Which check a relation raises, or None. Read by `_page_checks` so the
#: emitter and the picture cannot part company over which word fires.
CANONICAL_CHECK = {"missing": "canonical-missing",
                   "elsewhere": "canonical-mismatch",
                   # Q-55. The same-path case, which raised nothing at all
                   # until this item - a page handing its content to
                   # another domain, and the record silent about it.
                   "off-host": "canonical-off-host",
                   # Q-54. Graded apart because the two accidents are not
                   # the same accident: a slash variant is nearly always
                   # one, a parameter variant is usually a decision.
                   "variant-slash": "canonical-mismatch-trailing-slash",
                   "variant-parameter": "canonical-mismatch-parameter"}

#: The relations that are a variant of the page's own URL, whatever kind.
#: A prefix test would read as a spelling trick; this says what it means.
VARIANT_RELATIONS = ("variant-slash", "variant-parameter")

#: The terminal-axis canonical checks (item 137, brief v18 step BA). Facts about
#: where the walk ends, not what the markup says — so they are born under TEC
#: while the relation checks above stay ONP (channel 20260910-0830). Their
#: dimension is read here rather than assumed, so an emitter knows whether the
#: verdict is its to emit.
TERMINAL_CANONICAL_CHECKS = ("canonical-to-404", "canonical-loop",
                             "canonical-sitemap-conflict")


def canonical_verdict(kind: str, terminal: str | None, relation: str,
                      start_in_sitemap: bool, target_in_sitemap: bool,
                      external_host: str | None = None) -> str | None:
    """The one canonical check a page raises on the relation/terminal/sitemap
    axis, or None (item 137, brief v18 step BA, channel 20260910-0850).

    Precedence, most specific first:

        bad + 4xx/5xx terminal       -> canonical-to-404          (TEC)
        bad + loop/capped            -> canonical-loop            (TEC)
        bad + >=2 hops, end fine, or
          a non-status terminal      -> canonical-mismatch        (ONP)
        in sitemap, target is not    -> canonical-sitemap-conflict (TEC),
                                        including where the relation is mute
        otherwise                    -> the relation check        (ONP), or None

    `off-host` is NOT on this axis: it is Q-55's orthogonal co-emitted check
    and is handled by its own emitter, so a verdict never returns it and never
    suppresses it. `self`/`blank` return None (no finding), and `mute` returns
    None on the relation axis (Q-54 stands) unless the sitemap clause upgrades
    it — a sitemap listing /page/ while the canonical says /page is exactly
    "sitemap declares one form, canonical another", and Q-54 decided only that
    the variant *relation* raises nothing, not that a sitemap contradiction does.
    """
    # Off-host is Q-55's own co-emitted check and is off this axis entirely,
    # whether the relation reads `off-host` or `elsewhere` with the target on
    # another host (`/partner -> mirror.example/elsewhere`). The verdict is the
    # plain relation there (elsewhere -> canonical-mismatch), and off-host rides
    # beside it; a foreign host is not a sitemap-form conflict, so it does not
    # take the sitemap branch either.
    if relation == "off-host":
        return None
    if kind == "bad":
        if terminal and terminal.isdigit() and int(terminal) >= 400:
            return "canonical-to-404"
        if terminal == "loop":
            return "canonical-loop"
        return "canonical-mismatch"
    # The sitemap contradiction: the sitemap asserts the form the canonical
    # rejects. Both ends read from `in_sitemap` per node; where BOTH are in the
    # sitemap the sitemap lists both forms, which is a sitemap defect BA names
    # no id for and is left out of scope deliberately (channel 20260910-0850).
    # An off-host target is trivially absent from this site's sitemap, so it is
    # excluded here — its concern is `canonical-off-host`, not a form conflict.
    if (relation in ("elsewhere",) + VARIANT_RELATIONS
            and start_in_sitemap and not target_in_sitemap and not external_host):
        return "canonical-sitemap-conflict"
    return CANONICAL_CHECK.get(relation)


def canonical_nodes_from_crawl(crawl) -> dict:
    """The canonical index `canonical_chain_state` walks, built from a live
    crawl rather than stored evidence (item 137, brief v18 step BA).

    `runs.canonical_nodes` builds the same shape post-storage for the dashboard;
    the terminal checks fire at run time, so this reads the same fields off the
    live `Page` objects. One builder per run — the modules share it through
    `context` so neither walks the crawl twice."""
    from clauditseo.persistence.runs import canonical_nodes
    from .pagefacts import extract_facts

    # Every page, not just the html 200s: a canonical target that 4xx'd is a
    # node the walk must see AS a 4xx to call it canonical-to-404 rather than
    # "not crawled". Only html 200s carry a canonical to read.
    pages = []
    for page in crawl.pages:
        html = page.status == 200 and page.content_type.startswith("text/html")
        facts = extract_facts(page) if html else None
        pages.append({"url": page.url, "status": page.status,
                      "canonical": facts.canonical if facts else None,
                      "meta_robots": facts.meta_robots if facts else None,
                      "x_robots_tag": page.x_robots_tag})
    return canonical_nodes({"pages": pages,
                            "robots_blocked": list(crawl.robots_blocked),
                            "sitemap_entries": list(crawl.sitemap_entries)})


def canonical_nodes_from_facts(f) -> dict:
    """A one-page canonical index, for a direct `_page_checks` unit call that
    passes no run-wide nodes (item 137, brief v18 step BA)."""
    from clauditseo.persistence.runs import canonical_nodes
    return canonical_nodes({"pages": [{
        "url": f.url, "status": None, "canonical": f.canonical,
        "meta_robots": getattr(f, "meta_robots", None), "x_robots_tag": None}],
        "robots_blocked": [], "sitemap_entries": []})


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _bare_host(host: str) -> str:
    """A host with `www.` and any port removed.

    The apex and its `www` are one site. Answering that first is what Q-55
    asks for, and without it the off-host check would fire on every site
    that canonicalises `example.com/x` to `www.example.com/x` - which is
    the single most common correct canonical there is.
    """
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def same_site_host(a: str, b: str) -> bool:
    """Whether two hosts are the same site as far as a canonical goes.

    **One predicate, read by the check and by the chain drawing**, for the
    reason `canonical_relation` exists: the card's colour and the finding
    beside it must never disagree, and the way they come to disagree is two
    implementations of "is this the same host".

    `site_hosts` on the record would widen this, and there is no such field
    (Q-55's report): `sites` stores `domain` and nothing else host-shaped,
    so the registered set is the entry host and its www/apex counterpart
    and no more. A site serving two real domains is not answered here.
    """
    if not a or not b:
        return True                 # nothing to compare: not a difference
    return _bare_host(a) == _bare_host(b)


def canonical_off_host(url: str, canonical: str | None) -> str | None:
    """The host a canonical hands the page to, or None where it does not.

    Independent of `canonical_relation`'s single word on purpose. The two
    facts are orthogonal - a canonical can point at another host on the
    same path or on a different one - and the operator ruled on
    2026-09-07 that a different-path off-host raises BOTH this and
    `canonical-mismatch`. One word could not have said both.
    """
    if not canonical or not canonical.strip():
        return None
    target = urlsplit(urljoin(url, canonical.strip()))
    here = urlsplit(url)
    if not target.netloc or not here.netloc:
        return None                 # relative, or a page with no host to compare
    if same_site_host(target.netloc, here.netloc):
        return None
    return target.netloc.lower()


def _canonical_key(url: str) -> str:
    """How the walk decides it has been here before. The crawl's own
    spelling minus a trailing slash, because `/x` and `/x/` canonicalising
    to each other is a loop and not a two-page chain."""
    split = urlsplit(url)
    return f"{split.netloc.lower()}{(split.path or '/').rstrip('/') or '/'}?{split.query}"


def _chain_label(url: str) -> str:
    """How one node reads under the drawing: the path, and the query where
    there is one.

    Not the path alone. Acme's only chain is
    `/apply?product_type=loc` -> `/apply`, and a picture whose two nodes
    both said `/apply` would be a picture of nothing - the query is the
    whole difference the chain is about.
    """
    split = urlsplit(url)
    path = split.path or "/"
    return f"{path}?{split.query}" if split.query else path


def _terminal_reason(node: dict) -> str | None:
    """Why this node cannot be indexed, in the word the chain labels it
    with, or None where it can.

    The order is the order a reader needs: a page nobody fetched is not a
    page with a status, and a page robots.txt forbade is not a 404.
    """
    if not node.get("in_crawl"):
        return "not crawled"
    if node.get("robots_blocked"):
        return "robots-blocked"
    status = node.get("status")
    if isinstance(status, int) and status >= 400:
        return str(status)
    if node.get("noindex"):
        return "noindex"
    return None


def canonical_chain_note(kind: str, hops: int, terminal: str | None,
                         external_host: str | None = None,
                         relation: str | None = None) -> str:
    """The sentence under one chain, generated from the kind.

    Here and not in the renderer for `skip_shape`'s reason: the sentence
    and the colour are the same claim about the same walk, and a client
    writing its own would be the second implementation this whole block
    exists to avoid.
    """
    if kind == "ok":
        return "Canonical is the page itself. Nothing to do."
    if kind == "mute":
        # Both grades since Q-54. The sentence names which one, because the
        # two now carry different findings and a reader told only "variant"
        # would not know which row to look for - and it no longer says "no
        # check fires", which was true until this item and would have gone
        # on reading as true.
        if relation == "variant-parameter":
            return ("Parameter variant pointing at the clean URL. Listed, and "
                    "not deducted from the score - dropping a query string is "
                    "usually deliberate.")
        if relation == "variant-slash":
            return ("Trailing-slash variant pointing at the same path. Almost "
                    "always an accident, so it is scored.")
        return ("Parameter or trailing-slash variant pointing at the clean URL.")
    if terminal == "no canonical":
        return ("The page declares no canonical URL, so nothing states which URL "
                "owns this content.")
    if external_host:
        return (f"Canonical points at {external_host}, which this crawl did not "
                "read. Confirm the other host is meant to own the content.")
    if terminal == "loop":
        return ("The chain comes back to a URL it has already been through, so it "
                "never reaches a page that owns itself.")
    if terminal:
        end = {"not crawled": "a URL this crawl never read",
               "robots-blocked": "a URL robots.txt forbids",
               "noindex": "a noindexed page"}.get(terminal, f"a {terminal}")
        hop = ("Two hops" if hops == 2 else f"{hops} hops" if hops > 2
               else "The chain")
        return (f"{hop} and the end of the chain is {end}, so the page has "
                "effectively asked to be dropped.")
    if hops >= 2:
        return (f"{hops} hops before a page owns itself. The end is indexable, but "
                "a crawler that follows two redirections of credit may follow "
                "neither.")
    return ("Points at a different URL that is itself indexable. If the move was "
            "intended, fine; if not, the page is telling Google to index the "
            "other one.")


def canonical_chain_state(url: str, nodes: dict,
                          hops: int = CANONICAL_HOPS) -> dict:
    """One page's canonical chain, walked, and the kind it draws as.

    `nodes` is the run's canonical index as `runs.canonical_nodes` builds
    it, keyed by the URL as the crawl spells it and again by path: each
    value carries what the sweep already knows about that URL - whether it
    was crawled, its status, whether it is noindexed, whether robots
    forbade it, whether the sitemap lists it - and its own `canonical`, so
    the walk is a lookup and never a second fetch.

    The walk: page -> its canonical -> that URL's canonical, stopping when
    a node canonicalises to itself, when the target is not a node this run
    holds, when a URL comes round a second time, or at `hops`.

    The four kinds, and each is one token on the screen (item 140's rule):

      * `ok`   - one node, self-canonical.
      * `warn` - one hop to a URL that is itself indexable, self-canonical
        and crawled; a page with no canonical at all; a canonical to
        another host.
      * `bad`  - the chain ends somewhere that cannot be indexed, or it
        loops, **or it is two hops or more even where the end is fine**.
        A hop is a hop: a crawler that follows two of them is a crawler
        that may follow neither.
      * `mute` - the target differs from the page only by a parameter or a
        trailing slash. The one kind that deliberately has no finding
        beside it, because the check has never raised one for it.

    `check` is what the record holds against this page, or None, and it
    comes from `CANONICAL_CHECK` rather than from a rule of its own - which
    is what makes `test_a_chain_and_its_finding_agree` a comparison rather
    than a tautology: the fixture declares the findings, the engine derives
    the kind, and the two are compared at the page level.
    """
    start = nodes.get(url) or nodes.get(urlsplit(url).path or "/") or {}
    first = dict(start, url=start.get("url") or url,
                 path=start.get("path") or (urlsplit(url).path or "/"),
                 in_crawl=bool(start))
    walked: list[dict] = [first]
    seen = {_canonical_key(first["url"])}
    relation = canonical_relation(first["path"], start.get("canonical"),
                                  first["url"])
    terminal: str | None = None
    external_host: str | None = None
    at = start
    capped = True
    while len(walked) - 1 < hops:
        here = walked[-1]
        rel = canonical_relation(here["path"], at.get("canonical") if at else None,
                                 here["url"])
        if rel in ("self", "missing", "blank"):
            capped = False
            break
        target = urljoin(here["url"], (at.get("canonical") or "").strip())
        if rel == "off-host" or not same_site_host(_host(target),
                                                  _host(first["url"])):
            # The item's third degradation. One hop, the host on the node,
            # and no attempt to walk into a site this run never crawled -
            # "not crawled" would be true and would say the wrong thing.
            external_host = _host(target)
            walked.append({"url": target, "path": urlsplit(target).path or "/",
                           "in_crawl": False, "external": True,
                           "status": None, "noindex": False,
                           "robots_blocked": False, "in_sitemap": False})
            capped = False
            break
        key = _canonical_key(target)
        found = nodes.get(target) or nodes.get(urlsplit(target).path or "/")
        walked.append(dict(found or {},
                           url=(found or {}).get("url") or target,
                           path=(found or {}).get("path")
                                or (urlsplit(target).path or "/"),
                           in_crawl=bool(found)))
        if key in seen:
            terminal, capped = "loop", False
            break
        seen.add(key)
        at = found or {}
        if not found:
            capped = False
            break

    if terminal is None and len(walked) > 1 and external_host is None:
        terminal = _terminal_reason(walked[-1])
        if terminal is None and capped:
            # A walk that ran out of hops never reached a page that owns
            # itself, which is the same thing a loop fails to do.
            terminal = "loop"

    hop_count = len(walked) - 1
    if relation == "self":
        kind = "ok"
    elif relation in VARIANT_RELATIONS:
        kind = "mute"
    elif relation in ("missing", "blank"):
        kind, terminal = "warn", "no canonical"
    elif terminal is not None or hop_count >= 2:
        kind = "bad"
    else:
        kind = "warn"
    # The single check this page raises on the relation/terminal/sitemap axis
    # (item 137, brief v18 step BA). The terminal and sitemap checks are more
    # specific than the relation one and take its place; `check` is what both
    # the emitters and `test_a_chain_and_its_finding_agree` read, so the walk
    # is the one place the verdict is decided. Falls back to the relation check
    # for off-host (Q-55's own co-emitted check) so the chain still names it.
    start_sm = bool(walked[0].get("in_sitemap")) if walked else False
    target_sm = bool(walked[-1].get("in_sitemap")) if len(walked) > 1 else start_sm
    verdict = canonical_verdict(kind, terminal, relation, start_sm, target_sm,
                                external_host)
    return {
        "url": first["url"], "path": first["path"],
        "kind": kind, "hops": hop_count, "relation": relation,
        "terminal": terminal, "external_host": external_host,
        "check": verdict or CANONICAL_CHECK.get(relation),
        "label": _chain_label(first["url"]),
        "nodes": [{"url": n["url"], "path": n["path"],
                   "label": _chain_label(n["url"]),
                   "in_crawl": bool(n.get("in_crawl")),
                   "external": bool(n.get("external")),
                   "status": n.get("status"),
                   "noindex": bool(n.get("noindex")),
                   "robots_blocked": bool(n.get("robots_blocked")),
                   "in_sitemap": bool(n.get("in_sitemap"))}
                  for n in walked],
        "note": canonical_chain_note(kind, hop_count, terminal, external_host,
                                     relation),
    }

def _saving(shot: dict) -> dict:
    """What the file would weigh re-encoded, where that was measured.

    Never a ratio and never a rule of thumb (brief v16 step AU7): either a
    file was fetched, decoded, resized and encoded, or the row carries no
    saving. Where the probe ran and failed, it says so - "we tried and
    could not" is a different thing from "we did not try", and the card
    distinguishes them.
    """
    if shot.get("measured_kb") is not None:
        return {"measured_kb": shot["measured_kb"], "encoder": shot.get("encoder")}
    if shot.get("reencode_error"):
        return {"reencode_error": shot["reencode_error"]}
    return {}


def _float_or(value, fallback: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


#: What each page type is expected to carry, from the prompt's own map -
#: the one rule the Structured data brief owns (brief v16 step AS). Keys
#: are the site record's page types; the value is the node types any one of
#: which satisfies the page.
SCHEMA_FOR_TYPE = {
    # The entity node, and only the entity node. The prompt's map asks the
    # home page for three things - the entity, a WebSite and a WebPage -
    # and accepting any of the three let a site publishing a bare WebSite
    # pass the check that every other check turns on. Observed on Birch,
    # whose home page carries one WebSite block and no Organization at
    # all: the sweep raised nothing, and the one thing wrong with the
    # site's markup is exactly that. The other two are the brief's to
    # raise, because "this page has no WebPage node" is a judgement about
    # what the page is.
    "home": ("Organization", "LocalBusiness"),
    "location": ("LocalBusiness",),
    "service": ("Service",),
    "blog": ("Article", "BlogPosting", "NewsArticle"),
    "article": ("Article", "BlogPosting", "NewsArticle"),
    "product": ("Product",),
    "event": ("Event",),
}

#: Rich results Google has withdrawn or narrowed to a point where the
#: markup buys nothing. Named rather than derived: this is a fact about
#: Google's product decisions, and it changes when they change it.
DEPRECATED_RESULTS = ("FAQPage", "HowTo")

#: The node types that describe the business itself, as opposed to a page,
#: an article or a product. `schema-orphan-instance` is about these.
ENTITY_TYPES = ("Organization", "LocalBusiness", "Corporation", "NGO",
                "LocalBusiness", "Store", "Restaurant", "ProfessionalService",
                "TravelAgency", "EventVenue", "HomeAndConstructionBusiness")

#: What Google marks Required for the rich results this product assesses.
#: A registry table rather than a rule, because "required" is Google's
#: word and the list is theirs to change.
REQUIRED_PROPERTIES = {
    "Article": ("headline",),
    "BlogPosting": ("headline",),
    "NewsArticle": ("headline",),
    "Product": ("name",),
    "Event": ("name", "startDate", "location"),
    "Recipe": ("name", "image"),
    "BreadcrumbList": ("itemListElement",),
}



def _islands(facts, site) -> list:
    """The page's island nodes, per RENDER_RULES section 6.

    Built through `schema_graph.build_model` rather than re-derived here, so
    the finding and the picture the part page draws cannot disagree about
    which nodes are islands - two implementations of one rule is how a card
    and a row end up saying different things about the same node.

    The raw blocks rather than the flattened inventory, because the
    inventory keeps two levels and collapses a list of objects to its first
    member: a reference three deep inside an `itemListElement` is not in it,
    and a node wired only through one would be reported as an island it is
    not.

    The source label is not read here - an island is a fact about
    references and nothing about it depends on which plugin wrote the block
    - so it is left as the placeholder rather than looked up, and the
    picture gets the real one from the stored inventory.

    A block that does not parse yields nothing: that is
    `schema-invalid-json`'s finding, and stating it twice would double the
    count.
    """
    blocks = []
    for raw in (getattr(facts, "jsonld_blocks", None) or []):
        try:
            blocks.append({"source": "inline", "json": json.loads(raw)})
        except (TypeError, ValueError):
            continue
    if not blocks:
        return []
    model = schema_graph.build_model(
        blocks, None,
        {"host": _host_of(facts.url), "page": facts.path,
         "page_type": _page_type_for(site, facts.url)},
        [])
    return [n for n in model.nodes if n.kind == "node" and n.island]


def _host_of(url: str) -> str:
    """A URL's host without `www.`, or "" where it has none."""
    try:
        return urlsplit(str(url)).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


#: Page types that are scoped to a place, so the record's location belongs
#: in the title. Every other type reports `names_place` as `n/a` rather than
#: as a failure - a service page that names no suburb is not incomplete, it
#: is not about a suburb.
LOCATION_SCOPED_TYPES = ("location", "service-area", "branch", "store")


#: How each criterion reads in a sentence a client would use.
_CRITERION_WORDS = {"names_entity": "what the page is about",
                    "names_brand": "the brand",
                    "names_place": "the location"}


def _title_replacement(site, facts, criteria: dict) -> str:
    """The title as it should read, from facts already on the record.

    Built from what is missing and nothing else: no rewording of what is
    already there, because the check is about what the title omits and a
    replacement that also restyled it would be answering a question nobody
    asked.
    """
    title = (facts.title or "").strip()
    parts = [title]
    if criteria.get("names_entity") is False:
        owned = _owned_entity(site, facts.url)
        if owned:
            parts.insert(0, owned)
    if criteria.get("names_place") is False:
        place = (getattr(site, "locations", None) or "")
        if isinstance(place, str) and place.strip():
            parts.append(place.strip())
    if criteria.get("names_brand") is False:
        brand = (getattr(site, "brand", None) or "").strip()
        if brand:
            parts.append(brand)
    out = " | ".join(dict.fromkeys([p for p in parts if p]))
    return out[:TITLE_MAX]


def snippet(title: str | None, meta_description: str | None) -> dict:
    """One page's title and description, as a search result will cut them.

    **The picture and the finding read this same function** (brief v16i). The
    checks call `_length_row`; the snippet card and the length strips call
    `snippet`; both measure through `textmetrics` against the same
    `GUIDELINES`. A card drawn from a second measurement would agree on the
    day it shipped and disagree the first time either number moved.

    **One measurement, two cut lines.** A string's pixel WIDTH does not change
    between desktop and mobile - only the width the result gives it does (600
    vs 410 for the title). So `px` is measured once and the desktop and mobile
    verdicts are two readings of it: the card's toggle switches which cut line
    applies without re-fetching, which is why the payload carries both rather
    than the server re-measuring per press.

    `state` is `ok` / `warn` (short, in characters) / `bad` (over, in pixels)
    / `mute` (absent). The over state carries the words that fall off at each
    width; the drawing labels the cut with them, not with the number.
    """
    from clauditseo.textmetrics import cut_at, measure

    def one(text, guide, font):
        if not text:
            return {"text": None, "state": "mute", "px": 0,
                    "limit_px": guide["max_px"],
                    "mobile_limit_px": guide["mobile_px"] or guide["max_px"],
                    "mobile_state": "mute", "fires": cut_of(guide)[1],
                    "font": f"{font[0]} {font[1]}px"}
        m = measure(text, font)
        out = {"text": text, "px": m["px"], "limit_px": guide["max_px"],
               "mobile_limit_px": guide["mobile_px"] or guide["max_px"],
               "font": m["font"], "estimated": m["estimated"],
               "chars": len(text), "min_chars": guide["min"]}

        def verdict(limit):
            if m["px"] > limit:
                return "bad", cut_at(text, limit, font)["falls_off"]
            if len(text) < guide["min"]:
                return "warn", ""
            return "ok", ""

        out["state"], out["falls_off"] = verdict(guide["max_px"])
        mob_state, mob_fall = verdict(guide["mobile_px"] or guide["max_px"])
        out["mobile_state"], out["mobile_falls_off"] = mob_state, mob_fall
        # Which of the two readings is the one the check fires at (item 152),
        # so the strip and the card's default view draw the finding's cut.
        out["fires"] = cut_of(guide)[1]
        return out

    return {
        "title": one(title, GUIDELINES["title"], TITLE_FONT),
        "description": one(meta_description, GUIDELINES["meta_description"],
                           DESC_FONT),
    }


def _length_row(text: str, font, limit_px: int, other_px: int | None,
                short_chars: int, legacy_min: int = 0,
                legacy_max: int = 0, viewport: str = "desktop",
                other_viewport: str | None = None) -> dict | None:
    """One length verdict, or None where the string is fine.

    **Two units, on purpose** (operator ruling through the questions channel,
    2026-09-08). Truncation is a WIDTH fact - whether a string is cut depends
    on pixels, which is the whole of what Part A fixes. Adequacy is not: in
    pixels a title of five short words scores worse than one of three wide
    ones, which is not a defect anyone would act on. `About | Beacon Events` is
    a good title and must not fire.

    So over-length is measured in pixels at the cut `cut_of` names, and minimum
    length stays in characters at the registry minimum it always used. The
    row says which unit produced the verdict, so nobody infers it from the
    number.

    **The truncation point is the finding's useful content, not the number**
    (brief v16i). A row saying "612 px" tells an operator nothing they can
    act on; the words that fall off are what they rewrite around, so both
    widths and both fall-off strings travel in the evidence.

    Over fires at `limit_px`, the width of `viewport` - mobile for titles
    since item 152 (decision A), desktop for descriptions until their mobile
    width is measured. The other viewport is carried beside it rather than
    firing its own row: one string, one fault, and a second row for the same
    title at another window would be the double-reporting this repo keeps
    guarding against.
    """
    from clauditseo.textmetrics import cut_at, measure

    m = measure(text, font)
    px = m["px"]
    # Both units on every row for one release (the item asks for it). The
    # character count is no longer what decides anything; it is here so the
    # operator can see WHY a row moved when the unit changed, which a bare
    # pixel figure cannot show.
    evidence: dict = {"px": px, "limit_px": limit_px,
                      "font": m["font"], "measured": "pixels",
                      "legacy_chars": len(text or ""),
                      "legacy_bounds": [legacy_min, legacy_max]}
    if m["estimated"]:
        # The table did not know every glyph, so the number is an estimate
        # and the row says so rather than implying a precision it lacks.
        evidence["note"] = (f"{m['unmeasured_glyphs']} character"
                            f"{'' if m['unmeasured_glyphs'] == 1 else 's'} "
                            "outside the width table, charged at the average "
                            "width - this measurement is an estimate")

    if px > limit_px:
        fired = cut_at(text, limit_px, font)
        evidence["falls_off"] = fired["falls_off"]
        evidence["over_px"] = px - limit_px
        # The width that fired is a viewport, and the line says which (item
        # 152): "cut at 600 px" left the reader to assume the surface.
        evidence["viewport"] = viewport
        if other_px and other_viewport:
            evidence[f"{other_viewport}_px_limit"] = other_px
            # Only where the other window cuts it too: a title cut on a phone
            # and whole on desktop carries no desktop fall-off to invent.
            if px > other_px:
                evidence[f"falls_off_{other_viewport}"] = cut_at(text, other_px, font)["falls_off"]
        says = (f"is {px} px and is cut at {limit_px} px on {viewport} - "
                f'"{fired["falls_off"]}" falls off')
        return {"says": says, "evidence": evidence}

    chars = len(text or "")
    if chars < short_chars:
        evidence["short_chars"] = short_chars
        evidence["measured"] = "characters"
        return {"says": f"is {chars} characters, under the {short_chars} "
                        "the guideline asks for", "evidence": evidence}
    return None


def _title_criteria(site, facts, page_type: str) -> dict:
    """The three observable properties 136q asks for, each `True`, `False`
    or `"n/a"`.

    `"n/a"` is not a soft failure. Where the record supplies nothing to test
    against - no entity for this page, no brand, no location scope - the
    question cannot be asked, and answering `False` would report the
    operator's empty record as the site's fault. Both live sites carry a
    brand and nothing else, so on today's data this check asks one of the
    three questions and says so.
    """
    title = (facts.title or "").strip()
    out: dict[str, object] = {}

    # names_entity - the entity this page owns, by canonical name or a
    # recorded variant.
    owned = _owned_entity(site, facts.url)
    if not owned:
        out["names_entity"] = "n/a"
    else:
        names = [owned] + list(
            (getattr(site, "entity_variants", None) or {}).get(owned, []) or [])
        out["names_entity"] = any(_names(title, n) for n in names)

    brand = (getattr(site, "brand", None) or "").strip()
    out["names_brand"] = _names(title, brand) if brand else "n/a"

    place = (getattr(site, "locations", None) or "")
    place = place if isinstance(place, str) else ""
    if page_type not in LOCATION_SCOPED_TYPES or not place.strip():
        out["names_place"] = "n/a"
    else:
        out["names_place"] = _names(title, place.strip())
    return out


def _owned_entity(site, url: str) -> str:
    """The record's entity whose own URL is this page, or "".

    Ownership is the record's statement, not a guess from the title: the
    page a `sub_services` entry points at is the page that owns it.
    """
    from clauditseo.modules.links import _entity_rows

    have, _ = _entity_rows(site)
    for ent in have:
        if _same_page(ent["hub"], url):
            return ent["entity"]
    return ""


def _same_page(a: str, b: str) -> bool:
    try:
        pa, pb = urlsplit(a).path or "/", urlsplit(b).path or "/"
    except ValueError:
        return a == b
    return pa.rstrip("/").lower() == pb.rstrip("/").lower()


def _names(title: str, name: str) -> bool:
    from clauditseo.modules.links import _mentions

    return bool(name) and _mentions(title, name)


def canonical_entity_id(entity_ids: set[str], inventories: dict) -> str | None:
    """The entity @id the orphan check measures against when the site record
    names none (item 215), or None when the markup does not settle it.

    It was `sorted(entity_ids)[0]`. Alphabetical order is not evidence, and on
    twenty22 it chose `#local_business` over `#organization`, which is the id
    the Structured data brief's own principle names - so the sweep called 45
    Organization blocks orphans and the brief proposed the opposite fix on the
    same cards. In order: one id is the only choice; an id ending
    `/#organization` is the convention the brief follows; else the id more
    blocks reference than any other; else nothing, and the check is held."""
    if len(entity_ids) == 1:
        return next(iter(entity_ids))
    org = sorted(i for i in entity_ids if i.lower().rstrip("/").endswith("#organization"))
    if org:
        return org[0]
    refs = {i: 0 for i in entity_ids}
    for blocks in inventories.values():
        for b in blocks:
            for v in (b.get("properties") or {}).values():
                if isinstance(v, str) and v in refs and v != b.get("id"):
                    refs[v] += 1
    if not refs:
        return None
    best = max(refs.values())
    top = [i for i, n in refs.items() if n == best]
    return top[0] if best > 0 and len(top) == 1 else None


def _page_type_for(site, url: str) -> str:
    """What the site record calls this page, or "" where it says nothing.

    The record keys page types by path. A type nobody set is not guessed
    at - `schema-missing-for-type` is about a page whose kind is known, and
    inventing the kind would invent the finding with it - with one
    exception: the site root is the home page, which is not an inference
    about content but a fact about the URL, and the home page is the one
    every entity check turns on.
    """
    types = getattr(site, "page_types", None) or {}
    if not isinstance(types, dict):
        return ""
    try:
        path = urlsplit(url).path or "/"
    except ValueError:
        return ""
    return str(types.get(path) or types.get(url) or ("home" if path == "/" else ""))


def _or_list(parts: list[str]) -> str:
    """`a`, `a or b`, `a, b or c` - for a list of alternatives, where
    `_and_list` would say the page needs all three."""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " or " + parts[-1]


def _and_list(parts: list[str]) -> str:
    """`a`, `a and b`, `a, b and c` - so a summary listing what is wrong
    with one image reads as a sentence rather than as a list with commas
    where an operator expects a conjunction."""
    if len(parts) == 1:
        return parts[0]
    # Semicolons where a clause already carries an "and", because "carries
    # no width and height and the header shows" reads as one run-on and an
    # operator has to parse it twice to see where the list divides.
    sep = "; " if any(" and " in p for p in parts) else ", "
    return sep.join(parts[:-1]) + (";" if sep == "; " else "") + " and " + parts[-1]


def _int_or(value, fallback: int) -> int:
    """A budget from the site record, or the product's own number."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return fallback


def _px(value) -> int | None:
    try:
        return int(str(value).strip().rstrip("px"))
    except (TypeError, ValueError):
        return None


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


class OnPageModule:
    code = "ONP"
    name = "On-Page"
    default_weight = scoring.DEFAULT_WEIGHTS["ONP"]
    #: Every check without exception is a property of one document —
    #: title, meta description, H1, image alt, canonical, JSON-LD validity,
    #: heading order. This is the dimension the page refresh was built for.
    #: See `registry.page_blind_dims`.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        facts = [extract_facts(p) for p in html_pages(crawl.pages)]
        findings: list[Finding] = []
        # Hoisted above the loop for item 136q commit 5: `title-entity-
        # incomplete` reads the site record, and the record was fetched
        # below the loop that needs it.
        site_record = context.get("site")
        # The run's canonical index, built once and shared through context so
        # TEC's terminal-canonical pass walks the same nodes without a second
        # build (item 137, brief v18 step BA).
        nodes = context.get("canonical_nodes")
        if nodes is None:
            nodes = canonical_nodes_from_crawl(crawl)
            context["canonical_nodes"] = nodes
        for f in facts:
            findings += self._page_checks(f, site_record, nodes)
        # The delivery checks the inventory can answer (brief v15 step AQ),
        # one row per image - and, where a browser measured the pages, the
        # two more that need a rendered width and a weight.
        site = context.get("site")
        budgets = (_int_or(getattr(site, "budget_lcp_kb", None), 200),
                   _int_or(getattr(site, "budget_page_kb", None), 1000),
                   # Per image, not per page (brief v16 step AU7): a heavy
                   # image below the fold of an otherwise light page sits
                   # inside the page budget and says nothing there.
                   _int_or(getattr(site, "budget_image_kb", None), BUDGET_IMAGE_KB),
                   _float_or(getattr(site, "bytes_per_pixel", None), BYTES_PER_PIXEL_CAP))
        findings += self._image_checks(facts, context.get("image_measurements"), budgets,
                                       getattr(site, "brand", None))
        # The Structured data checks the inventory answers (brief v16 step
        # AS). Site-level, because half of them are questions about the run
        # rather than about a page.
        findings += self._structured_data_checks(facts, site)
        duplication = self._duplication_checks(facts)
        # One URL, one canonical finding. Where the crawl proved a variant is
        # an uncanonicalised copy of a page it also fetched, the generic LOW
        # "declares no canonical URL" says strictly less about that URL than
        # the finding that names the page it duplicates, so it gives way.
        named = {u for f in duplication
                 if f.check_id == "canonical-missing-variant"
                 for u in f.affected_urls}
        findings = [f for f in findings
                    if not (f.check_id == "canonical-missing"
                            and set(f.affected_urls) & named)]
        return findings + duplication

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # This dimension measures page content, so a crawl that fetched no
        # page measured none of it. Without this it inherited coverage 1.0
        # and reported 100 at full weight from nothing.
        return scoring.subscore(self.code, findings, self.default_weight, context,
                                coverage=scoring.page_coverage(context))

    def _title_entity(self, f: PageFacts, site) -> list[Finding]:
        """Whether the title names what the page owns (item 136q commit 5).

        Three observable properties, each reported in `criteria` as `True`,
        `False` or `"n/a"`. **`"n/a"` is not a soft failure**: where the
        record supplies nothing to test against, the question cannot be
        asked, and answering `False` would report the operator's empty record
        as the site's fault. On both live sites today only `brand` is set, so
        this check asks one of its three questions and the row says which.

        Free and structural. The item calls it "analysis where a title
        template is supplied"; the contract already settles what that means -
        a check the sweep emits is `free` whether or not a brief also reads
        it, and the brief adds reading to a finding that exists rather than
        creating one. `{{TITLE_TEMPLATE}}` is unset on both sites, so the
        template path is specified and unexercised; the structural path is
        what runs.
        """
        if site is None or not (f.title or "").strip():
            return []
        criteria = _title_criteria(site, f, _page_type_for(site, f.url))
        # Nothing to say where every question was n/a or answered yes.
        if not [k for k, v in criteria.items() if v is False]:
            return []
        missing = [k for k, v in criteria.items() if v is False]
        return [Finding(
            dimension=self.code, check_id="title-entity-incomplete",
            severity=DEFAULT_SEVERITY["title-entity-incomplete"],
            summary=f"{f.path} does not name "
                    + _or_list([_CRITERION_WORDS[k] for k in missing])
                    + " in its title.",
            subject=f.path, affected_urls=[f.url],
            evidence={"criteria": criteria, "title": f.title,
                      "replacement": _title_replacement(site, f, criteria)},
            recommendation="Name what the page owns in the title, within "
                           f"{TITLE_MAX} characters.")]

    def _page_checks(self, f: PageFacts, site=None, nodes: dict | None = None) -> list[Finding]:
        out: list[Finding] = []

        if not f.title:
            out.append(Finding(
                dimension=self.code, check_id="title-missing", severity=DEFAULT_SEVERITY["title-missing"],
                summary=f"{f.path} has no <title>.", subject=f.path, affected_urls=[f.url],
                evidence={},
                recommendation="Write a unique, descriptive title of roughly 50-60 characters.",
            ))
        else:
            fire_px, viewport, other_px, other_vp = cut_of(GUIDELINES["title"])
            row = _length_row(f.title, TITLE_FONT, fire_px, other_px,
                              short_chars=TITLE_MIN,
                              legacy_min=TITLE_MIN, legacy_max=TITLE_MAX,
                              viewport=viewport, other_viewport=other_vp)
            if row:
                out.append(Finding(
                    dimension=self.code, check_id="title-length",
                    severity=DEFAULT_SEVERITY["title-length"],
                    summary=f"Title on {f.path} " + row["says"],
                    subject=f.path, affected_urls=[f.url],
                    evidence={"title": f.title, **row["evidence"]},
                    recommendation="Rewrite the title to fit the display "
                                   "window without truncation.",
                ))

        if f.meta_description:
            fire_px, viewport, other_px, other_vp = cut_of(GUIDELINES["meta_description"])
            row = _length_row(f.meta_description, DESC_FONT, fire_px, other_px,
                              short_chars=DESC_MIN,
                              legacy_min=DESC_MIN, legacy_max=DESC_MAX,
                              viewport=viewport, other_viewport=other_vp)
            if row:
                out.append(Finding(
                    dimension=self.code, check_id="meta-desc-length",
                    severity=DEFAULT_SEVERITY["meta-desc-length"],
                    summary=f"Description on {f.path} " + row["says"],
                    subject=f.path, affected_urls=[f.url],
                    evidence={"description": f.meta_description,
                              **row["evidence"]},
                    recommendation="Rewrite the description to fit the "
                                   "display window without truncation.",
                ))

        if not f.meta_description:
            out.append(Finding(
                dimension=self.code, check_id="meta-desc-missing", severity=DEFAULT_SEVERITY["meta-desc-missing"],
                summary=f"{f.path} has no meta description.", subject=f.path,
                affected_urls=[f.url], evidence={},
                recommendation="Add a meta description of roughly 120-160 characters that "
                               "earns the click.",
            ))
        # The character-window branch that stood here until brief v16i is
        # gone, not left beside the pixel one: the block above is the whole
        # of `meta-desc-length` now. Leaving both would have raised two rows
        # for one description, which is what it did on the run that found
        # this - the new block was ADDED and the old `elif` was still there.

        # One decision for all three heading checks and for the ladder the
        # part page draws from the same list (brief v16d). What follows
        # reads `fires`; nothing here re-derives "skipped" or "second h1",
        # which is what let the screen and the record disagree before.
        outline = heading_outline_state(f.headings)
        h1s = outline["h1_texts"]
        if outline["fires"]["h1-missing"]:
            out.append(Finding(
                dimension=self.code, check_id="h1-missing", severity=DEFAULT_SEVERITY["h1-missing"],
                summary=f"{f.path} has no H1.", subject=f.path, affected_urls=[f.url],
                evidence={"headings": f.headings[:10]},
                recommendation="Give the page exactly one H1 that states its topic.",
            ))
        elif outline["fires"]["h1-multiple"]:
            out.append(Finding(
                dimension=self.code, check_id="h1-multiple", severity=DEFAULT_SEVERITY["h1-multiple"],
                summary=f"{f.path} has {len(h1s)} H1 headings.", subject=f.path,
                affected_urls=[f.url], evidence={"h1s": h1s},
                recommendation="Keep one H1; demote the rest to H2.",
            ))

        # `outline_index` is the position of the offending heading in this
        # page's outline, 0-based, into `f.headings` — the same list
        # `evidence.snapshot` stores as `headings` and the client screen
        # renders. FEATURES.md F-07: "H2→H4 on /" says a level was skipped
        # and not which heading, so the screen had nothing to open at and the
        # operator had to count down the outline by hand.
        #
        # The first skip alone, which is what the loop this replaced did with
        # its `break`. `heading_outline_state` decides which one that is, and
        # the ladder reads the same answer.
        skip = outline["fires"]["heading-skip"]
        if skip:
            out.append(Finding(
                dimension=self.code, check_id="heading-skip", severity=DEFAULT_SEVERITY["heading-skip"],
                summary=f"Heading level jumps H{skip['from']}→H{skip['to']} on {f.path}.",
                subject=f.path, affected_urls=[f.url],
                evidence={"sequence": outline["levels"], "outline_index": skip["index"]},
                recommendation="Keep heading levels sequential so the outline stays "
                               "meaningful.",
            ))

        missing_alt = [src for src, alt in f.images if alt is None or not alt.strip()]
        if missing_alt:
            out.append(Finding(
                dimension=self.code, check_id="img-alt-missing", severity=DEFAULT_SEVERITY["img-alt-missing"],
                summary=f"{len(missing_alt)} of {len(f.images)} image(s) on {f.path} "
                        "lack alt text.",
                subject=f.path, affected_urls=[f.url],
                evidence={"missing": missing_alt[:10], "total_images": len(f.images)},
                recommendation="Describe each meaningful image in its alt attribute; use "
                               'alt="" only for decorative images.',
            ))

        # One decision for both canonical checks and for the chain the
        # Indexability part page draws from the same answer (brief v16g/v18 step
        # BA). The walk is the single source now: `chain["check"]` is the one
        # verdict on the relation/terminal/sitemap axis (`canonical_verdict`),
        # so the picture and the record cannot disagree, and where the verdict
        # is a terminal check (canonical-to-404/loop/sitemap-conflict, TEC) none
        # of the ONP relation branches below fire — TEC emits it instead, and
        # the more specific finding is the one the page keeps. `off-host` is
        # off this axis (Q-55's own co-emitted check, below) and is untouched.
        # A direct unit call (no run) passes no nodes; build a one-page index
        # from this page so the walk still resolves its own canonical. A target
        # the single page does not hold reads "not crawled", which is `bad` with
        # no status and so `canonical-mismatch` — the same verdict the run gives
        # an elsewhere-canonical whose target it did reach as a live page.
        page_nodes = nodes if nodes is not None else canonical_nodes_from_facts(f)
        chain = canonical_chain_state(f.url, page_nodes)
        verdict = chain["check"]
        if verdict == "canonical-missing":
            out.append(Finding(
                dimension=self.code, check_id="canonical-missing", severity=Severity.LOW,
                summary=f"{f.path} declares no canonical URL.", subject=f.path,
                affected_urls=[f.url], evidence={},
                recommendation="Add a self-referencing canonical link unless the page is "
                               "a deliberate duplicate.",
            ))
        elif verdict == "canonical-mismatch":
            canon_path = urlsplit(f.canonical).path or "/"
            out.append(Finding(
                dimension=self.code, check_id="canonical-mismatch", severity=Severity.MEDIUM,
                summary=f"{f.path} canonicalises to {canon_path} — its content will "
                        "be credited to that URL.",
                subject=f.path, affected_urls=[f.url],
                evidence={"canonical": f.canonical},
                recommendation="Confirm the canonical target is intended; if not, make "
                               "it self-referencing.",
            ))
        elif verdict == "canonical-mismatch-trailing-slash":
            # LOW and scored. The two URLs are the same page and one of
            # them is the accident: nobody links `/x/` deliberately when
            # the site serves `/x`.
            out.append(Finding(
                dimension=self.code, check_id="canonical-mismatch-trailing-slash",
                severity=Severity.LOW,
                summary=f"{f.path} canonicalises to the same path with a different "
                        "trailing slash — almost always an accident.",
                subject=f.path, affected_urls=[f.url],
                evidence={"canonical": f.canonical},
                recommendation="Make the canonical match the URL the site actually "
                               "serves, slash for slash.",
            ))
        elif verdict == "canonical-mismatch-parameter":
            # INFO, and INFO weighs 0.0 in `scoring.SEVERITY_WEIGHTS`, so
            # this is unscored by construction rather than by a second
            # list somebody has to keep in step. The summary says so,
            # because a row that deducts nothing still reads like a
            # deduction unless it tells the reader otherwise.
            out.append(Finding(
                dimension=self.code, check_id="canonical-mismatch-parameter",
                severity=Severity.INFO,
                summary=f"{f.path} canonicalises to the same path without its query "
                        "string — usually deliberate, and not deducted from the score.",
                subject=f.path, affected_urls=[f.url],
                evidence={"canonical": f.canonical},
                recommendation="No action if the parameter is a filter or a tracking "
                               "tag; listed so a canonical that drops a parameter it "
                               "should keep can be seen.",
            ))

        # Q-55, and deliberately NOT an `elif` on the chain above. A
        # canonical to another host is orthogonal to whether the path also
        # differs: `/partner -> other.example/elsewhere` raises this AND
        # `canonical-mismatch`, which is the operator's ruling of
        # 2026-09-07. Making it a branch of the relation would have made
        # the two exclusive and silently resolved every existing
        # `canonical-mismatch` on a page whose canonical left the host.
        out += self._title_entity(f, site)

        off_host = canonical_off_host(f.url, f.canonical)
        if off_host:
            out.append(Finding(
                dimension=self.code, check_id="canonical-off-host",
                severity=Severity.MEDIUM,
                summary=f"{f.path} canonicalises to {off_host} — its content will "
                        "be credited to a domain this site does not control.",
                subject=f.path, affected_urls=[f.url],
                evidence={"canonical": f.canonical, "host": off_host},
                recommendation="Point the canonical at this site unless the content "
                               "is deliberately syndicated and the other domain is "
                               "the original.",
            ))

        for err in f.jsonld_errors:
            out.append(Finding(
                dimension=self.code, check_id="jsonld-invalid", severity=Severity.MEDIUM,
                summary=f"Structured data on {f.path} is not valid JSON.",
                subject=f.path, affected_urls=[f.url],
                evidence={"error": err},
                recommendation="Fix the JSON-LD syntax; invalid blocks are ignored by "
                               "search engines entirely.",
            ))
        out += self._schema_checks(f)
        return out

    def _structured_data_checks(self, facts: list, site=None) -> list[Finding]:
        """The twelve Structured data checks the stored inventory answers
        (brief v16 step AS).

        Site-level, and that is not tidiness: half of these are questions
        about the run rather than about a page. An `@id` is inconsistent
        only against the other pages' `@id`s; an instance is an orphan only
        relative to a canonical node somewhere; a block is redundant only
        beside the block it duplicates. A per-page pass could not see any
        of it, which is why the prompt is handed a SITE INVENTORY too.

        Every row names its basis, as the image checks do, so a reading of
        markup is never mistaken for a validation against Google.
        """
        out: list[Finding] = []
        inventories = {f.url: schema_inventory(getattr(f, "jsonld_blocks", None) or [],
                                               getattr(f, "jsonld_ids", None) or [])
                       for f in facts}
        # One writing of the rule, shared with the stored record: a block
        # counted once here and once per page there would be two answers to
        # how many problems this part has.
        mark_template_blocks(list(inventories.values()))
        # The whole run's nodes, which is what the four site-level checks
        # are about.
        ids: dict[str, set[str]] = {}
        for url, blocks in inventories.items():
            for b in blocks:
                if b.get("id"):
                    ids.setdefault(str(b["id"]), set()).add(url)
        entity_ids = {i for i, _ in ids.items()
                      if any(str(b.get("type") or "").split(",")[0].strip() in ENTITY_TYPES
                             for blocks in inventories.values() for b in blocks
                             if b.get("id") == i)}
        canonical = getattr(site, "canonical_id", None) or canonical_entity_id(
            entity_ids, inventories)
        #: Item 215: several entity @ids and none evidently the site's. The
        #: orphan check is then held rather than run against a guess: the
        #: guess was `sorted(entity_ids)[0]`, which on twenty22 is
        #: `#local_business` ("l" before "o"), and 45 of 45 Organization
        #: blocks became orphans of it.
        canonical_held = canonical is None and len(entity_ids) > 1
        record_nap = (getattr(site, "nap", None) or "").strip()
        owned = {_host_of(u) for u in (getattr(site, "sameas_sources", None) or [])}
        cited = {_host_of(u) for u in (getattr(site, "citation_sources", None) or [])}

        for f in facts:
            blocks = inventories.get(f.url) or []
            types = {str(b.get("type") or "").split(",")[0].strip() for b in blocks}
            page_type = _page_type_for(site, f.url)

            def raise_(*, check_id: str, summary: str, evidence: dict,
                       recommendation: str) -> None:
                out.append(Finding(
                    dimension=self.code, check_id=check_id,
                    severity=DEFAULT_SEVERITY[check_id], summary=summary,
                    subject=f.path, affected_urls=[f.url],
                    evidence=evidence, recommendation=recommendation))

            # Islands, from the raw graph rather than from the flattened
            # inventory: the inventory keeps two levels and a list of
            # objects collapsed to its first member, so a reference three
            # deep inside an `itemListElement` is not in it, and a node
            # wired only through one would be reported as an island it is
            # not. `build_model` walks the blocks as they were served.
            for node in _islands(f, site):
                raise_(check_id="schema-island",
                       summary=f"The {node.type} block on {f.path} is not "
                               "connected by an @id reference to any other "
                               "block on the page.",
                       evidence={"type": node.type, "id": node.id,
                                 "block": node.block,
                                 "basis": "every @id reference on the page, "
                                          "resolved; self-references and a "
                                          "node's own nested definitions do "
                                          "not count as a connection"},
                       recommendation="Reference it from the node it belongs "
                                      "to, or from the WebPage, so an engine "
                                      "reading one node can reach the rest.")

            for n, b in enumerate(blocks):
                if not b.get("parse_ok"):
                    raise_(check_id="schema-invalid-json",
                           summary=f"A structured-data block on {f.path} does not parse.",
                           evidence={"block": n, "error": b.get("error"),
                                     "source": b.get("source"),
                                     "basis": "the block was parsed as JSON and failed"},
                           recommendation="Fix the JSON syntax; a block that does not "
                                          "parse is ignored entirely.")
                if str(b.get("type") or "") in DEPRECATED_RESULTS:
                    raise_(check_id="schema-deprecated-rich-result",
                           summary=f"{f.path} carries {b['type']} markup, for a rich "
                                   "result Google has withdrawn or narrowed.",
                           evidence={"block": n, "type": b.get("type"),
                                     "source": b.get("source"),
                                     "basis": "the block's @type against the withdrawn list"},
                           recommendation="Remove the block unless the page needs it for "
                                          "something other than a rich result.")
                required = REQUIRED_PROPERTIES.get(str(b.get("type") or ""))
                if b.get("parse_ok") and required:
                    props = b.get("properties") or {}
                    absent = [r for r in required
                              if not any(k == r or k.startswith(r + ".") for k in props)]
                    if absent:
                        raise_(check_id="schema-required-missing",
                               summary=f"The {b['type']} block on {f.path} is missing "
                                       + _and_list(absent) + ", which Google marks required.",
                               evidence={"block": n, "type": b.get("type"),
                                         "missing": absent,
                                         "basis": "Google's Required list for this type"},
                               recommendation="Add the required properties, or remove the "
                                              "block if the page is not that thing.")
                # A reference to an `@id` no node in the run defines.
                for key, value in (b.get("properties") or {}).items():
                    if key.endswith(".@id") and str(value) not in ids:
                        raise_(check_id="schema-graph-wiring",
                               summary=f"{f.path} points at {value} from "
                                       f"{key.rsplit('.', 1)[0]}, and no block in this "
                                       "crawl defines it.",
                               evidence={"block": n, "property": key, "target": value,
                                         "basis": "every @id defined anywhere in this crawl"},
                               recommendation="Point the reference at the entity's "
                                              "canonical @id, or define the node it names.")
                same_as = str((b.get("properties") or {}).get("sameAs") or "")
                for url in [u.strip() for u in same_as.split(",") if u.strip()]:
                    host = _host_of(url)
                    if host and (host in cited or (owned and host not in owned)):
                        raise_(check_id="schema-sameas-misplaced",
                               summary=f"sameAs on {f.path} carries {url}, which is not a "
                                       "profile the entity controls.",
                               evidence={"block": n, "url": url, "host": host,
                                         "in_citation_sources": host in cited,
                                         "basis": "the site record's own two lists"},
                               recommendation="Move it to subjectOf or citation; sameAs is "
                                              "for profiles the entity owns.")
                nap_name = str((b.get("properties") or {}).get("name") or "").strip()
                if record_nap and nap_name and nap_name.lower() not in record_nap.lower():
                    raise_(check_id="schema-nap-mismatch",
                           summary=f"The {b.get('type') or 'block'} on {f.path} is marked "
                                   f"up as {nap_name!r}, and the site record says "
                                   f"{record_nap.splitlines()[0]!r}.",
                           evidence={"block": n, "marked_up": nap_name,
                                     "record": record_nap[:200],
                                     "basis": "the site record's exact NAP"},
                           recommendation="Match the marked-up name, address and phone to "
                                          "the record exactly, punctuation included.")
                if (b.get("parse_ok")
                        and str(b.get("type") or "") in ("Article", "BlogPosting", "NewsArticle")
                        and "dateModified" not in (b.get("properties") or {})):
                    raise_(check_id="schema-datemodified-missing",
                           summary=f"The {b['type']} block on {f.path} carries no "
                                   "dateModified.",
                           evidence={"block": n, "type": b.get("type"),
                                     "basis": "the block's own properties"},
                           recommendation="Add dateModified, and keep it in step with the "
                                          "date the page shows.")

            # An entity block that names no canonical @id, and a block that
            # defines one nobody else points at.
            for n, b in enumerate(blocks):
                kind = str(b.get("type") or "").split(",")[0].strip()
                if kind in ENTITY_TYPES and not b.get("id"):
                    raise_(check_id="schema-id-inconsistent",
                           summary=f"The {kind} block on {f.path} carries no @id, so "
                                   "nothing can reference it.",
                           evidence={"block": n, "type": kind, "canonical": canonical,
                                     "basis": "every @id defined anywhere in this crawl"},
                           recommendation="Give the entity one canonical @id and reference "
                                          "it verbatim from every instance.")
                elif kind in ENTITY_TYPES and canonical and b.get("id") != canonical:
                    raise_(check_id="schema-orphan-instance",
                           summary=f"The {kind} block on {f.path} declares "
                                   f"{b.get('id')} rather than the canonical "
                                   f"{canonical}.",
                           evidence={"block": n, "type": kind, "id": b.get("id"),
                                     "canonical": canonical,
                                     "basis": "every @id defined anywhere in this crawl"},
                           recommendation="Reference the canonical @id rather than "
                                          "declaring a second node for one entity.")

            # Two blocks for one subject, which is a plugin and a theme both
            # writing the page's schema.
            seen: dict[str, int] = {}
            for b in blocks:
                key = f"{b.get('type')}|{b.get('id')}"
                seen[key] = seen.get(key, 0) + 1
            for key, count in seen.items():
                if count > 1 and not key.startswith("None"):
                    raise_(check_id="schema-redundant-block",
                           summary=f"{f.path} carries {count} blocks for "
                                   f"{key.split('|')[0]}.",
                           evidence={"type": key.split("|")[0], "count": count,
                                     "sources": sorted({str(b.get("source"))
                                                        for b in blocks}),
                                     "basis": "the blocks' own @type and @id"},
                           recommendation="Keep one block per subject; a plugin and a "
                                          "theme both writing it is the usual cause.")

            expected = SCHEMA_FOR_TYPE.get(page_type)
            if expected and not (types & set(expected)):
                raise_(check_id="schema-missing-for-type",
                       summary=(f"{f.path} is "
                                + ("an " if page_type[:1].lower() in "aeiou" else "a ")
                                + f"{page_type} page and carries no "
                                + _or_list(list(expected)) + " block."),
                       evidence={"page_type": page_type, "expected": list(expected),
                                 "found": sorted(t for t in types if t),
                                 "basis": "the site record's page type against the "
                                          "brief's own type map"},
                       recommendation=f"Add a {expected[0]} block describing what this "
                                      "page is about.")
            if blocks and page_type and page_type != "home" and "BreadcrumbList" not in types:
                raise_(check_id="schema-breadcrumb-missing",
                       summary=f"{f.path} carries no BreadcrumbList.",
                       evidence={"page_type": page_type,
                                 "found": sorted(t for t in types if t),
                                 "basis": "the blocks on the page"},
                       recommendation="Add a BreadcrumbList naming the path to this page.")
        if canonical_held and facts:
            ids_named = sorted(entity_ids)
            out.append(Finding(
                dimension=self.code, check_id="schema-orphan-not-assessed",
                severity=DEFAULT_SEVERITY["schema-orphan-not-assessed"],
                summary=(f"{len(ids_named)} entity @ids are declared and none is evidently "
                         "the site's own, so no block can be called an orphan of it."),
                subject="schema-orphan-canonical", affected_urls=[facts[0].url],
                evidence={"status": "HELD",
                          "needs": "the canonical @id on the site record",
                          "ids": ids_named[:10],
                          "why": "none ends /#organization and no one @id is "
                                 "referenced by more nodes than the others"},
                recommendation="Name the entity's canonical @id on the site record "
                               "(Admin > Sites); the orphan check then runs against it."))
        return out

    def _schema_checks(self, f: PageFacts) -> list[Finding]:
        """Validate the structured data itself, not merely that it parses:
        required properties, deprecated rich-result types, @id integrity."""
        from clauditseo.schema_rules import audit_entities, parse_blocks

        if not f.jsonld_blocks:
            return []
        entities, _ = parse_blocks(f.jsonld_blocks)
        out: list[Finding] = []
        for issue in audit_entities(entities):
            severity = {"info": Severity.INFO, "low": Severity.LOW,
                        "medium": Severity.MEDIUM}[issue["severity_hint"]]
            check_id = f"schema-{issue['kind']}"
            recommendation = issue.get("instead") or (
                "Add the missing properties, or remove the type if the page is "
                "not primarily about that entity.")
            out.append(Finding(
                dimension=self.code, check_id=check_id, severity=severity,
                summary=f"{f.path}: {issue['summary']}",
                subject=f"{f.path}#{issue['kind']}:{issue.get('type') or '-'}",
                affected_urls=[f.url],
                evidence={k: v for k, v in issue.items() if k != "summary"},
                recommendation=recommendation,
            ))
        return out

    # --- duplication -------------------------------------------------------
    #
    # A page that declares rel=canonical to another page does not compete with
    # it for a query: the search engine collapses the two. So a duplicate-title
    # group must be counted over the pages that are still their own canonical,
    # not over every URL that returned the same string. Three decisions were
    # made here, and each is a judgement rather than a deduction:
    #
    # 1. **The target must be in the same crawl.** A canonical pointing at a
    #    URL this run never fetched is an unverified claim — the target may
    #    404, or not exist. Suppressing a real duplicate on an unverified claim
    #    is worse than reporting one that a later crawl will clear, so such a
    #    page stays a member of its group.
    # 2. **Resolution is a single hop; chains are not followed.** The question
    #    a group asks is only "does this URL compete with the others", and one
    #    declaration answers it: A canonicalising to B means A is not competing,
    #    whatever B goes on to say. A canonical cycle (A->B, B->A) therefore
    #    empties its group and raises nothing here — which is correct, because
    #    the per-page `canonical-mismatch` check already reports both halves.
    # 3. **A variant with no canonical is a different finding, not this one.**
    #    Telling a client to differentiate the titles of `/apply` and
    #    `/apply?product_type=loc` is advice that cannot be followed. The
    #    followable advice is to add the canonical, so that is what is raised.

    def _canonical_target(self, f: PageFacts) -> str | None:
        """The normalised URL this page declares itself a copy of, or None.

        Markup first, then the HTTP `Link` header — the same precedence the
        expert analyst applies, so the two cannot disagree about one page.
        """
        declared = (f.canonical or f.link_header_canonical or "").strip()
        return normalise_url(urljoin(f.url, declared)) if declared else None

    def _competitors(self, group: list[PageFacts], crawled: set[str]) -> tuple[
            list[PageFacts], list[PageFacts], list[tuple[PageFacts, str]]]:
        """Split a same-string group into who competes, who is an alias of a
        crawled page, and who is an uncanonicalised variant of one."""
        members: list[PageFacts] = []
        aliases: list[PageFacts] = []
        variants: list[tuple[PageFacts, str]] = []
        for f in group:
            own = normalise_url(f.url)
            target = self._canonical_target(f)
            if target and target != own and target in crawled:
                aliases.append(f)
                continue
            if target is None and urlsplit(f.url).query:
                parts = urlsplit(own)
                base = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                if base != own and base in crawled:
                    variants.append((f, base))
                    continue
            members.append(f)
        return members, aliases, variants

    def _variant_finding(self, f: PageFacts, base: str) -> Finding:
        query = urlsplit(f.url).query
        return Finding(
            dimension=self.code, check_id="canonical-missing-variant",
            severity=Severity.MEDIUM,
            summary=f"{f.path}?{query} serves the same page as {f.path} and "
                    "declares no canonical — both can be indexed.",
            subject=f"{f.path}?{query}", affected_urls=[f.url],
            evidence={"variant": f.url, "base": base, "query": query},
            recommendation=f'Add rel="canonical" pointing at {base}, so the '
                           "parameterised URL consolidates into the clean one "
                           "instead of competing with it.",
        )


    def _marked_inventories(self, facts: list, measured: dict | None,
                            brand: str | None = None) -> dict[str, list[dict]]:
        """Each page's images, with what a browser saw merged in and the
        template rule applied across the run.

        The merge happens here rather than at each use so `template` and
        `top_pct` are on the same row as the markup, which is what
        `mark_template_images` reads and what the stored inventory looks
        like. One writing of the rule, shared with `crawler.evidence`:
        the sweep counting a template image once and the record counting it
        per page would be two answers to how many problems the part has.
        """
        rows: dict[str, list[dict]] = {}
        for f in facts:
            seen = (measured or {}).get(f.url) or {}
            rows[f.url] = []
            for img in (getattr(f, "image_details", None) or []):
                # The image is the file (item 246). A script lazy loader's
                # `src` is a `data:` placeholder and the file is in
                # `lazy_src`; such a row was dropped here, so no image check
                # ever read twenty22's 271 lazy images, and `img-heavy`
                # passed a 102 KB thumbnail the chart drew over budget. The
                # placeholder is kept beside it, as the loading evidence.
                src = str(img.get("src") or "")
                placeholder = src.startswith("data:")
                file = str(img.get("lazy_src") or "") if placeholder else src
                if img.get("tag") != "img" or not file:
                    continue
                rows[f.url].append({**img, "src": file,
                                    **({"placeholder": src} if placeholder else {}),
                                    **(seen.get(file) or {})})
        mark_template_images([(inv, [position_key(i) for i in inv])
                              for inv in rows.values()])
        # The logo is identified after the regions are settled, because it
        # is a header image by definition and `region_class` is what says
        # which those are. The brand refines one of the three signals; the
        # stored record has no site to ask, which is why the signal that
        # needs it is the last word rather than the first.
        for f in facts:
            identify_logo(rows.get(f.url) or [],
                          getattr(f, "jsonld_blocks", None) or [], brand, f.url)
        return rows

    @staticmethod
    def _fold_template_rows(rows: list[tuple[str, str, Finding]]) -> list[Finding]:
        """One finding per (check, template image); everything else as it
        came (brief v16 step AU4).

        The summary was written about one page and has to stop being, so
        the page's own path is taken back out of it - by value, not by
        pattern: the path is carried alongside the row precisely so this is
        a replacement of a known string rather than surgery on a sentence.

        The token replaced is `on <path>`, not the path alone, and the dead
        end is why. The home page's path is `/`, so replacing that bare
        spliced the phrase in at every slash of every URL in the sentence -
        `https://x/logo.svg` came out unreadable. A path is a substring of
        almost anything; `on <path>` is a phrase these summaries actually
        write. A summary that does not contain it is left alone and reads
        as it did, about the first page.
        """
        folded: list[Finding] = []
        groups: dict[tuple[str, str], list[tuple[str, Finding]]] = {}
        for key, path, finding in rows:
            if not finding.evidence.get("template"):
                folded.append(finding)
                continue
            groups.setdefault((finding.check_id, key), []).append((path, finding))
        for (_, _), members in groups.items():
            first_path, first = members[0]
            urls: list[str] = []
            for _, f in members:
                for u in f.affected_urls:
                    if u not in urls:
                        urls.append(u)
            where = (f"on every one of the {len(urls)} pages it is on"
                     if len(urls) > 1 else f"on {first_path}")
            folded.append(Finding(
                dimension=first.dimension, check_id=first.check_id,
                severity=first.severity,
                summary=first.summary.replace(f"on {first_path}", where, 1),
                subject=first.evidence.get("region_class") or "body",
                affected_urls=urls,
                evidence={**first.evidence, "pages": len(urls)},
                recommendation=first.recommendation))
        return folded

    def _logo_check(self, f, inventory: list[dict], brand: str | None,
                    per_image: list) -> None:
        """`ONP/img-logo`, one row per page and one card per site.

        Every sub-finding is on the one row, in `evidence`, because they
        are one change: an SVG logo with the brand as its alt, wrapped in a
        link home, with width and height, is a single replacement. Listing
        them as separate checks would be five cards for one edit, which is
        the shape AU2 exists to remove.

        `also_resolves` names the two checks that replacement closes on the
        way past, so the part page renders them on this card rather than
        again on their own.
        """
        has_header = any((i.get("region_class") or "body") == "header"
                         for i in inventory)
        logo = next((i for i in inventory if i.get("is_logo")), None)
        if logo is None:
            # **Two sentences, and the site gets whichever is true.**
            # Where the page declares a header and every image in it is an
            # icon, that is a finding: we looked where the logo goes and it
            # is not there. Where the page declares no header region at
            # all, "your site has no logo" is a different claim from "I
            # could not find your logo" - `html.parser` builds no tree, and
            # a masthead in an unlabelled `<div>` is invisible to it. The
            # first sentence would be wrong on every page of every site
            # that styles its header without a landmark, which is many of
            # them.
            #
            # AU6 left the second case silent. The operator's ruling on
            # 2026-09-06 is that silence reads as "checked, fine", which is
            # worse than either sentence: a client whose logo row is simply
            # missing learns nothing. So the absence is said - once for the
            # site, at INFO, held rather than failed - and the fix on that
            # row is the landmark, which is what would let every other logo
            # check run.
            if not has_header:
                # A coverage note, not a finding. "We could not measure
                # this, and here is why" is exactly what that mechanism
                # says: it is listed in its own strip, carries no verb and
                # is never counted among the defects - which is right,
                # because the site does not have a *problem* with its
                # logo, it has markup this parser cannot read. Counting it
                # would also put the badge and the record one apart, since
                # they agree on notes and would have had to disagree here.
                per_image.append((
                    "logo|no-header", f.path,
                    Finding(dimension=self.code, check_id="img-logo-not-assessed",
                            severity=Severity.INFO,
                            summary="No header landmark (<header>, <nav>, or "
                                    "role=banner) was found on this site, so no "
                                    "image could be identified as the logo.",
                            subject="img-logo-no-header", affected_urls=[f.url],
                            evidence={"image": None, "region_class": None,
                                      "template": True, "kind": "content-first",
                                      "status": "HELD",
                                      "needs": "a header landmark on the page",
                                      "why": "the logo is identified by where it "
                                             "sits, and nothing here says where "
                                             "the header is"},
                            recommendation=(
                                "Wrap the masthead in <header> (or give it "
                                "role=\"banner\"). Every other logo check reads "
                                "the header, so this one change is what lets "
                                "them run."))))
                return
            per_image.append((
                "logo|none", f.path,
                Finding(dimension=self.code, check_id="img-logo",
                        severity=DEFAULT_SEVERITY["img-logo"],
                        summary=f"No image in the header of {f.path} could be identified "
                                "as the logo.",
                        subject=f.path, affected_urls=[f.url],
                        evidence={"image": None, "region_class": "header",
                                  "template": False, "kind": "content-first",
                                  "basis": "the page declares a header and every image in "
                                           "it is an icon by size or role"},
                        recommendation="Put the organisation's logo in the header, linked "
                                       "to the home page, with the brand name as its alt "
                                       "text.")))
            return

        logo["is_logo"] = True
        src = str(logo.get("src") or "")
        declared = schema_logo(getattr(f, "jsonld_blocks", None) or [])
        alt = (logo.get("alt") or "").strip()
        href = (logo.get("linked_to") or "").strip()
        fmt = _src_format(src)
        width, height = _px(logo.get("width")), _px(logo.get("height"))
        brand_name = (brand or "").strip()

        problems: list[str] = []
        also: list[str] = []
        if not alt or alt.lower() in ("logo", "image", "icon") or (
                brand_name and brand_name.lower() not in alt.lower()):
            problems.append(
                f"its alt reads {alt!r} rather than the brand name"
                if alt else "it carries no alt text")
        if not href:
            problems.append("it is not wrapped in a link")
        elif not _links_home(href, f.url):
            problems.append(f"its link goes to {href} rather than the home page")
        if fmt in _LEGACY_FORMATS:
            problems.append(f"it is delivered as {fmt.upper()} where the source is vector")
            also.append("ONP/img-legacy-format")
        if width is None or height is None:
            problems.append("it carries no width and height, and it is in the first "
                            "viewport of every page")
            also.append("ONP/img-dimensions-missing")
        if declared and src != declared and not src.split("?")[0].lower().endswith(
                declared.rsplit("/", 1)[-1].split("?")[0].lower()):
            problems.append(f"the header shows {src} while the structured data declares "
                            f"{declared} as the logo")

        if not problems:
            return
        per_image.append((
            position_key(logo), f.path,
            Finding(dimension=self.code, check_id="img-logo",
                    severity=DEFAULT_SEVERITY["img-logo"],
                    summary=f"The logo on {f.path}: " + _and_list(problems) + ".",
                    subject=f.path, affected_urls=[f.url],
                    evidence={"image": src, "region_class": "header",
                              "template": bool(logo.get("template")), "is_logo": True,
                              "logo_from": logo.get("logo_from"),
                              "schema_logo": declared, "alt": logo.get("alt"),
                              "linked_to": logo.get("linked_to"), "format": fmt,
                              "also_resolves": also,
                              "basis": "the markup, and the page's own structured data"},
                    recommendation="Serve the logo as SVG, wrapped in a link to the home "
                                   "page, with width and height and the brand name as its "
                                   "alt text, and reference the same file from the "
                                   "entity's `logo` in structured data.")))

    def _image_checks(self, facts: list, measured: dict | None = None,
                      budgets: tuple = (200, 1000, 300, 1.0),
                      brand: str | None = None) -> list[Finding]:
        """The delivery checks the stored inventory can answer (brief v15
        step AQ).

        One row per image, because a fix is per image; the evidence names
        the basis so a reading of markup is never mistaken for a
        measurement. What needs a browser or the file itself - the width
        an image renders at, its weight, whether it is the LCP candidate -
        this crawl does not have, and the checks that need those are the
        brief's to raise, not the sweep's to guess at.

        **One row per image, and a template image is one image** (brief v16
        step AU2). A missing alt on a footer icon was a finding per page:
        on a 248-page site that is 248 findings, 248 fix cards, and a badge
        saying Images has 248 problems when it has one. The check bodies
        below are unchanged and still raise per page; `_fold_template_rows`
        merges each template image's rows into one finding carrying every
        page it appears on, which is the shape the rest of the app already
        renders as `fixes N pages`.
        """
        out: list[Finding] = []
        per_image: list[tuple[str, str, Finding]] = []
        inventories = self._marked_inventories(facts, measured, brand)
        for f in facts:
            self._logo_check(f, inventories.get(f.url) or [], brand, per_image)
            inventory = inventories.get(f.url) or []
            if not inventory:
                continue
            # What a browser saw of this page, where one looked (brief
            # v15). Absent means nobody measured, which is why every check
            # below that needs a number tests for one rather than
            # defaulting it.
            seen_here = (measured or {}).get(f.url) or {}
            first_in_main = next((i for i in inventory if i.get("in_main")), None)
            lcp = next((i for i in inventory
                        if (seen_here.get(i.get("src") or "") or {}).get("lcp_candidate")), None)
            page_kb = sum(m.get("weight_kb") or 0 for m in seen_here.values())
            seen_hrefs: dict[tuple[str, str], int] = {}
            for image in inventory:
                src = str(image["src"])
                # What a browser saw of this one image, read before any
                # check runs: three of them state a saving, and a saving
                # measured after the row was written is a saving nobody
                # can put on it.
                shot = seen_here.get(src) or {}
                fmt = _src_format(src)
                width, height = _px(image.get("width")), _px(image.get("height"))
                # Brief v16 step AU5: which part of the page it is in
                # first, then size and role.
                #
                # **The region alone used to be enough** -
                # `region in ("nav", "header", "footer")` - which called a
                # full-width masthead photograph decorative because of
                # where it sat. It is the *icons* in those regions that are
                # furniture, so what decides is size, and the region only
                # says where to expect it. Read as: an icon is small
                # wherever it sits, and a header image whose size the
                # markup does not state is not called decorative on
                # suspicion.
                #
                # **And the logo is never decorative** (AU6). It is
                # identified before this loop runs, on the same row, so the
                # two rules cannot disagree about the one image in the
                # header that carries meaning.
                small = ((width is not None and width <= _ICON_PX)
                         or (height is not None and height <= _ICON_PX))
                icon = (not image.get("is_logo")
                        and (small
                             or (image.get("role") or "").lower() == "presentation"))

                def raise_(*, check_id: str, summary: str, evidence: dict,
                           recommendation: str) -> None:
                    finding = Finding(
                        dimension=self.code, check_id=check_id,
                        severity=DEFAULT_SEVERITY[check_id], summary=summary,
                        subject=f.path, affected_urls=[f.url],
                        evidence={"image": src,
                                  "region_class": image.get("region_class") or "body",
                                  "template": bool(image.get("template")),
                                  **evidence},
                        recommendation=recommendation)
                    # Collected rather than emitted, so a template image's
                    # rows can be folded once every page has been read.
                    # The path travels with the row because folding has to
                    # take it back out of a summary written about one page.
                    per_image.append((position_key(image), f.path, finding))

                if width is None or height is None:
                    raise_(check_id="img-dimensions-missing",
                           summary=f"{src} on {f.path} carries no width and height, so the "
                           "browser cannot reserve its space.",
                           evidence={"width_attr": image.get("width"), "height_attr": image.get("height"),
                            "basis": "the markup; a CSS aspect-ratio was not inspected"},
                           recommendation="Give the image width and height attributes, or a CSS "
                           "aspect-ratio, so the layout does not shift as it loads.")
                if fmt in _LEGACY_FORMATS and not icon:
                    raise_(check_id="img-legacy-format",
                           summary=f"{src} on {f.path} is delivered as {fmt.upper()}.",
                           evidence={"format": fmt, **_saving(shot),
                                     "basis": "the file extension"},
                           recommendation="Serve AVIF or WebP with a fallback for photographs, and "
                           "SVG where the image is vector or interface furniture.")
                if not (image.get("srcset") or "").strip() and not icon and fmt != "svg":
                    raise_(check_id="img-no-srcset",
                           summary=f"{src} on {f.path} is one file for every screen.",
                           evidence={"srcset": None,
                            "basis": "the markup; the widths it renders at were not measured"},
                           recommendation="Offer the image at several widths with srcset, and say "
                           "which width applies where with sizes.")
                if _GENERIC_NAME.search(_src_stem(src)):
                    raise_(check_id="img-filename-generic",
                           summary=f"{src} on {f.path} has a filename that says nothing about it.",
                           evidence={"stem": _src_stem(src), "basis": "the filename"},
                           recommendation="Rename the file after what the image shows, in the words "
                           "the page is about.")
                if icon and (image.get("alt") or "").strip():
                    raise_(check_id="img-alt-decorative-nonempty",
                           summary=f"{src} on {f.path} is decorative and carries alt text.",
                           evidence={"alt": image.get("alt"), "region": image.get("region"),
                            "width_attr": image.get("width"),
                            "basis": "declared size, role or region"},
                           recommendation='Give a decorative image alt="" so a screen reader passes '
                           "over it.")
                widest = max((v[0] for v in (shot.get("rendered") or {}).values()), default=0)
                intrinsic = shot.get("intrinsic_w")
                if widest and intrinsic and intrinsic >= 2 * widest:
                    raise_(check_id="img-oversized",
                           summary=f"{src} on {f.path} is {intrinsic}px wide and never "
                                   f"renders wider than {widest}px.",
                           evidence={"intrinsic_w": intrinsic, "widest_rendered": widest,
                                     "rendered": shot.get("rendered"),
                                     "basis": "measured in a browser at the site's breakpoints"},
                           recommendation="Serve the image at the widths it is shown at, "
                                          "with srcset, rather than one file sized for "
                                          "the largest screen.")
                weight = shot.get("weight_kb")
                # One image too heavy for what it shows (brief v16 step
                # AU7). Two ways to be too heavy and either is enough: over
                # a flat ceiling, or over a ceiling per rendered pixel - a
                # well-encoded photograph is under 0.5 bytes per pixel, so
                # a 400x300 thumbnail at 300 KB is 2.5 and badly encoded
                # however small the number in kilobytes looks.
                budget_image = budgets[2] if len(budgets) > 2 else BUDGET_IMAGE_KB
                per_pixel_cap = budgets[3] if len(budgets) > 3 else BYTES_PER_PIXEL_CAP
                shown = max(((v[0], v[1]) for v in (shot.get("rendered") or {}).values()),
                            default=(0, 0))
                pixels = shown[0] * shown[1]
                # **A floor under the bytes-per-pixel arm, and it is a
                # departure from AU7's text.** Read on Birch, where a
                # 1 KB social icon rendering at 30x30 is 1.14 bytes a
                # pixel and was raised as too heavy. The arithmetic is
                # right and the finding is not: bytes per pixel measures
                # how well a file is encoded, and below about twenty
                # kilobytes there is nothing an operator could do about
                # the answer. A finding nobody would act on is what
                # crowds out the ones they would - which is the same
                # complaint AU2 is about, one rule further down.
                #
                # The flat ceiling has no floor and needs none: a file
                # over 300 KB is over it whatever it renders at.
                #
                # Both arms live in `image_weight_state` since brief
                # v16c, called from here and from the scatter the Images
                # part page draws: a dot disagreeing with the row beside
                # it is what one function prevents and two cannot.
                state, per_pixel = image_weight_state(
                    weight, pixels, budget_image, per_pixel_cap)
                if state == "over":
                    raise_(check_id="img-heavy",
                           summary=(f"{src} on {f.path} weighs {weight} KB"
                                    + (f" and renders at {shown[0]}\u00d7{shown[1]}, "
                                       f"which is {per_pixel} bytes a pixel"
                                       if per_pixel is not None else "")
                                    + "."),
                           evidence={"weight_kb": weight, "budget_image_kb": budget_image,
                                     "rendered_at": list(shown) if pixels else None,
                                     "bytes_per_pixel": per_pixel,
                                     "bytes_per_pixel_cap": per_pixel_cap,
                                     "weight_source": shot.get("weight_source"),
                                     **_saving(shot),
                                     # Item 241 weighs a file the page never
                                     # fetched by the server's size header;
                                     # the finding says which it is.
                                     "basis": ("by the server's size header, against "
                                               "the rendered size"
                                               if shot.get("weight_source") == "header"
                                               else "measured in a browser from the "
                                                    "resource timing, against the "
                                                    "rendered size")},
                           recommendation="Re-encode the image to AVIF or WebP at the width "
                                          "it is shown at.")
                if weight and shot.get("lcp_candidate") and weight > budgets[0]:
                    raise_(check_id="img-weight-budget",
                           summary=f"{src} is the largest paint on {f.path} and weighs "
                                   f"{weight} KB, over the {budgets[0]} KB budget.",
                           evidence={"weight_kb": weight, "budget_kb": budgets[0],
                                     "lcp_candidate": True, **_saving(shot),
                                     "basis": "measured in a browser from the resource timing"},
                           recommendation="Re-encode the page's main image to AVIF or "
                                          "WebP and serve it at the width it renders.")
                # The lazily-loaded main image: the measured LCP where one
                # was observed, and document order where none was.
                lazy_subject = lcp if lcp is not None else first_in_main
                if image is lazy_subject and (image.get("loading") or "").lower() == "lazy":
                    raise_(check_id="img-lcp-lazy",
                           summary=(f"{src} is the largest paint on {f.path} and is loaded "
                                    "lazily." if lcp is not None else
                                    f"{src} is the first image in the main region of "
                                    f"{f.path} and is loaded lazily."),
                           evidence={"loading": "lazy", "fetchpriority": image.get("fetchpriority"),
                            "basis": ("measured in a browser as the largest paint"
                                      if lcp is not None else
                                      "document order in the main region; the LCP "
                                      "candidate itself was not measured")},
                           recommendation='Load the page\'s main image eagerly with '
                           'fetchpriority="high"; lazy loading is for what is below '
                           "the fold.")
                href = (image.get("linked_to") or "").strip()
                # Item 225: one link's work done twice is a thing one BLOCK
                # does - a card linking its picture, heading and text. The
                # logo linking home, in the header and again in the footer,
                # is the site's furniture: counted page-wide, it raised this
                # on 31 of twenty22's 45 pages, 31 of the part's 35 items.
                region = image.get("region_class") or "body"
                if href and not image.get("is_logo") and region not in ("header", "footer"):
                    seen_hrefs[(region, href)] = seen_hrefs.get((region, href), 0) + 1
            if page_kb > budgets[1]:
                out.append(Finding(
                    dimension=self.code, check_id="img-weight-budget",
                    severity=DEFAULT_SEVERITY["img-weight-budget"],
                    summary=f"The images on {f.path} weigh {page_kb} KB together, over "
                            f"the {budgets[1]} KB budget for a page.",
                    subject=f.path, affected_urls=[f.url],
                    evidence={"page_kb": page_kb, "budget_kb": budgets[1],
                              "images": len(seen_here),
                              "basis": "measured in a browser from the resource timing"},
                    recommendation="Re-encode the heaviest images and serve them at the "
                                   "widths they render at; the inventory names them."))
            # Two links to one place from one page's images and their
            # neighbours are one link's work done twice.
            for (region, href), n in seen_hrefs.items():
                if n >= 2:
                    out.append(Finding(
                        dimension=self.code, check_id="img-duplicate-links",
                        severity=DEFAULT_SEVERITY["img-duplicate-links"],
                        summary=f"{n} images on {f.path} link to {href}.",
                        subject=f.path, affected_urls=[f.url],
                        evidence={"href": href, "images": n, "region_class": region,
                                  "basis": "the anchors around the images in the markup"},
                        recommendation="Wrap the block in one anchor rather than "
                                       "linking the image, the heading and the text "
                                       "separately to the same page."))
        # AU4: a template image's rows become one finding over every page
        # it appears on. Page-level findings above are already one per page
        # and are not image rows, so they pass through untouched.
        out.extend(self._list_images(self._fold_template_rows(per_image)))
        return out

    @staticmethod
    def _list_images(findings: list[Finding]) -> list[Finding]:
        """One finding per identity, naming every image it covers (item 246;
        the operator's ruling of 2026-09-27, option a).

        An image finding's identity is its check and its page - or, for a
        template image, its check and its region, over every page the
        template draws it on. Two images failing one check on one page are
        one identity, and `engine.core._merge_by_identity` kept the first
        and dropped the second's image and numbers: `/website-blogs/` had
        two thumbnails over budget and one `img-heavy`, naming one of them.

        Merged here, where the images are still known: `images` lists each
        file, `per_image` keeps each one's own evidence, and the summary is
        every image's own sentence. The identity is unchanged, so the ledger
        is too. Each page keeps its own finding for an image that is not a
        template's - fixing it on one page does not fix it on another.
        """
        order: list[str] = []
        groups: dict[str, list[Finding]] = {}
        for f in findings:
            if f.fingerprint not in groups:
                order.append(f.fingerprint)
                groups[f.fingerprint] = []
            groups[f.fingerprint].append(f)
        merged: list[Finding] = []
        for fp in order:
            members = groups[fp]
            first = members[0]
            images: list[str] = []
            for m in members:
                image = m.evidence.get("image")
                if image and image not in images:
                    images.append(image)
            if len(images) < 2:
                merged.append(first) if len(members) == 1 else merged.extend(members)
                continue
            # One sentence per image, each as the check wrote it about that
            # image; a second placement of an image already named adds none.
            said: list[str] = []
            per_image: list[dict] = []
            named: set[str] = set()
            urls: list[str] = []
            for m in members:
                for u in m.affected_urls:
                    if u not in urls:
                        urls.append(u)
                image = m.evidence.get("image")
                if image in named:
                    continue
                named.add(image)
                said.append(m.summary)
                per_image.append(m.evidence)
            merged.append(Finding(
                dimension=first.dimension, check_id=first.check_id,
                severity=first.severity,
                summary=f"{len(images)} images: " + " ".join(said),
                subject=first.subject, affected_urls=urls,
                evidence={**first.evidence, "images": images, "per_image": per_image},
                recommendation=first.recommendation))
        return merged

    def _duplication_checks(self, facts: list[PageFacts]) -> list[Finding]:
        out: list[Finding] = []
        crawled = {normalise_url(f.url) for f in facts}
        by_title: dict[str, list[PageFacts]] = {}
        by_desc: dict[str, list[PageFacts]] = {}
        for f in facts:
            if f.title:
                by_title.setdefault(_norm(f.title), []).append(f)
            if f.meta_description:
                by_desc.setdefault(_norm(f.meta_description), []).append(f)

        # A URL can be a variant of its base by title and by description at
        # once; it is one missing canonical, so it is reported once.
        variant_findings: dict[str, Finding] = {}

        for title, group in sorted(by_title.items()):
            if len(group) < 2:
                continue
            members, aliases, variants = self._competitors(group, crawled)
            for f, base in variants:
                variant_findings.setdefault(f.url, self._variant_finding(f, base))
            if len(members) > 1:
                # One row per member page, each carrying the group (brief
                # v11 step AH): the brief answers one row per (check, page),
                # and the record counts the two sources on one line only
                # when the sweep's rows are the same shape. `paths` names
                # every member so a row still says who it competes with.
                evidence: dict = {"group": members[0].title,
                                  "paths": [f.path for f in members]}
                if aliases:
                    evidence["canonical_aliases"] = [
                        f.path + (f"?{urlsplit(f.url).query}"
                                  if urlsplit(f.url).query else "")
                        for f in aliases]
                for f in members:
                    out.append(Finding(
                        dimension=self.code, check_id="title-duplicate",
                        severity=DEFAULT_SEVERITY["title-duplicate"],
                        summary=f'{f.path} shares its title "{members[0].title}" with '
                                f"{len(members) - 1} other page{'s' if len(members) > 2 else ''} "
                                "— they compete for the same query.",
                        subject=f.path, affected_urls=[f.url],
                        evidence=evidence,
                        recommendation="Differentiate each title around the page's specific "
                                       "intent, or consolidate the pages.",
                    ))
        for desc, group in sorted(by_desc.items()):
            if len(group) < 2:
                continue
            members, aliases, variants = self._competitors(group, crawled)
            for f, base in variants:
                variant_findings.setdefault(f.url, self._variant_finding(f, base))
            if len(members) > 1:
                evidence = {"group": (members[0].meta_description or "")[:200],
                            "paths": [f.path for f in members]}
                if aliases:
                    evidence["canonical_aliases"] = [
                        f.path + (f"?{urlsplit(f.url).query}"
                                  if urlsplit(f.url).query else "")
                        for f in aliases]
                for f in members:
                    out.append(Finding(
                        dimension=self.code, check_id="meta-desc-duplicate",
                        severity=DEFAULT_SEVERITY["meta-desc-duplicate"],
                        summary=f"{f.path} shares its meta description with "
                                f"{len(members) - 1} other page{'s' if len(members) > 2 else ''}.",
                        subject=f.path, affected_urls=[f.url],
                        evidence=evidence,
                        recommendation="Write a distinct description per page.",
                    ))
        return out + list(variant_findings.values())


registry.register(OnPageModule())
