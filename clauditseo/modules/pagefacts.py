"""One-pass HTML fact extraction shared by the page-level checks.

Modules reason over PageFacts, not raw HTML, so parsing quirks live in one
place."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from clauditseo.crawler.types import Page

_VOID_CAPTURE = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "script"}


#: The attributes script lazy loaders keep the real file in, in the order the
#: common ones use them: WP Rocket, lazysizes and most themes, jQuery Lazy.
LAZY_SRC_ATTRS = ("data-lazy-src", "data-src", "data-original", "data-lazy")


def _lazy_src(attrs: dict) -> str | None:
    """The file a script lazy loader will swap in, or None (item 241)."""
    for name in LAZY_SRC_ATTRS:
        value = (attrs.get(name) or "").strip()
        if value and not value.startswith("data:"):
            return value
    return None


@dataclass
class PageFacts:
    url: str
    path: str
    title: str | None = None
    meta_description: str | None = None
    meta_robots: str | None = None
    viewport: str | None = None
    # Every viewport tag verbatim, in document order: a duplicate or
    # conflicting declaration is itself the finding, so one parsed value
    # is not enough.
    viewport_tags: list[str] = field(default_factory=list)
    hreflang: list[tuple[str, str]] = field(default_factory=list)  # (lang, href)
    canonical: str | None = None
    #: rel=canonical delivered as an HTTP `Link` header rather than markup.
    #: Binding on crawlers and stored on every page record, so a check that
    #: reasons about canonicals must see it as well as the `<link>` tag.
    link_header_canonical: str | None = None
    headings: list[tuple[int, str]] = field(default_factory=list)
    #: The outline the Headings brief reads (brief v11 step AJ): each
    #: heading with whether it sits in the main region and the first forty
    #: words after it; and how the main region was found.
    outline: list[dict] = field(default_factory=list)
    main_region: str = "whole body"
    images: list[tuple[str, str | None]] = field(default_factory=list)
    # Full delivery attributes per image, for the image-optimisation brief:
    # src, alt, width, height, loading, fetchpriority, decoding, srcset, sizes.
    image_details: list[dict] = field(default_factory=list)  # (src, alt)
    jsonld_blocks: list[str] = field(default_factory=list)              # raw script text
    #: The `id` or `class` on each block's `<script>`, parallel to
    #: `jsonld_blocks` (brief v16 step AS). A plugin names itself there.
    jsonld_ids: list[str] = field(default_factory=list)
    jsonld_errors: list[str] = field(default_factory=list)
    # Every `<script src>` verbatim, in document order, resolved no further
    # than the attribute itself — the classifier needs to tell `//host/a.js`
    # from `/a.js`, and resolving here would erase that difference. Scripts
    # inside `<noscript>` are not collected: that markup renders only when
    # scripting is off, so the script never runs.
    script_srcs: list[str] = field(default_factory=list)
    word_count: int = 0
    text: str = ""
    #: The text inside `main_region` alone; equal to `text` where the region
    #: is the whole body (item 151's main-region hash). Not stored.
    main_text: str = ""

    # --- accessibility -----------------------------------------------------
    # Everything below is read by the A11Y dimension. It is collected in the
    # same pass because re-parsing every page a second time to ask a
    # different question would double the cost of a crawl for no benefit.
    lang: str | None = None
    #: Every id in the document, in order, so duplicates are detectable.
    #: A repeated id silently breaks label/for and every aria reference to it.
    ids: list[str] = field(default_factory=list)
    #: Whether the page carries a `<form method=post>` (brief v16h).
    #: A route that takes a customer's details is the one to fix first
    #: when headers differ, and nothing recorded which routes those are.
    has_post_form: bool = False
    #: One entry per element carrying an `id`, with where it sits
    #: (136j Part A). Beside `ids` rather than replacing it, because
    #: three checks read that list as bare strings.
    id_where: list[dict] = field(default_factory=list)
    #: (attribute, referenced id) for aria-labelledby / describedby / controls.
    aria_refs: list[tuple[str, str]] = field(default_factory=list)
    #: Raw tabindex values; anything above 0 rewrites the tab order.
    tabindexes: list[str] = field(default_factory=list)
    #: tag, plus whatever could give it an accessible name.
    form_controls: list[dict] = field(default_factory=list)
    label_for: list[str] = field(default_factory=list)
    #: Links and buttons with their computed-ish accessible name.
    links: list[dict] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)
    iframes: list[dict] = field(default_factory=list)
    #: One entry per table: whether it has header cells and how many rows.
    tables: list[dict] = field(default_factory=list)
    #: Landmark elements and roles present anywhere in the document.
    landmarks: set[str] = field(default_factory=set)


#: Elements with no children. They must never be pushed onto the element
#: stack: `html.parser` does not call `handle_endtag` for them, so a pushed
#: `<img>` would swallow every following sibling as its descendant and every
#: selector after it on the page would be wrong.
VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr"})

#: What an unclosed element is closed BY. Real markup omits `</li>` and
#: `</p>` constantly, and a stack that believes the omission nests every
#: later item one level deeper than it is. Only the cases that actually
#: occur in page markup are listed; the full HTML5 table is long and the
#: rest of it does not appear in the documents this crawler reads.
IMPLICIT_CLOSE = {
    "li": {"li"}, "p": {"p"}, "option": {"option"}, "optgroup": {"optgroup", "option"},
    "td": {"td", "th"}, "th": {"td", "th"}, "tr": {"tr", "td", "th"},
    "dd": {"dd", "dt"}, "dt": {"dd", "dt"}, "thead": {"td", "th", "tr"},
    "tbody": {"td", "th", "tr"}, "tfoot": {"td", "th", "tr"},
}

#: Ids a framework generated rather than an author chose. They are stable
#: within one render and different on the next, so a selector built on one
#: identifies an element on this page and nothing on the page beside it -
#: which is the opposite of what 136f groups by. Stripped from the
#: normalised form and kept in the raw one, so the operator can still paste
#: something that resolves today.
GENERATED_ID = re.compile(
    r"^(w-node-|w-dyn-|comp-|gatsby-|__next|ember\d|react-aria|radix-|mui-|"
    r"headlessui-|ext-gen|yui_|ui-id-)", re.I)

#: How deep a selector may go. A path from `html` on a deeply nested page is
#: unreadable and no more identifying than its tail.
SELECTOR_DEPTH = 4

#: The outer HTML kept per instance.
INSTANCE_HTML = 200


class _FactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.facts_title: str | None = None
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.viewport_tags: list[str] = []
        self.hreflang: list[tuple[str, str]] = []
        self.headings: list[tuple[int, str]] = []
        # Brief v11 step AJ: the outline with region and following text.
        self.outline: list[dict] = []
        self._main_stack: list[str] = []
        #: The anchor being read, and the image last opened inside it, so
        #: an image can say where its link goes (brief v15 step AQ).
        self._link_href: str | None = None
        self._link_depth = 0
        #: (tag, region) per open landmark. Keyed by tag because a
        #: landmark can be declared by role on any element - `<div
        #: role="banner">` - and the pop used to test the tag against
        #: `_LANDMARK_TAGS`, which that div is not in. So it pushed and
        #: never popped, and every image after it on the page reported
        #: that region. Found while deriving `region_class` (brief v16
        #: step AU1), where the wrong region moves an image between the
        #: header row and the body grid rather than mislabelling a line.
        self._region_stack: list[tuple[str, str]] = []
        #: The open element path, innermost last. Each entry carries what a
        #: selector needs plus a count of the children seen under it so far,
        #: so `nth-of-type` is known at the moment a child opens rather than
        #: requiring a second pass.
        self._el_stack: list[dict] = []
        #: Children of the document root, for the same reason.
        self._root_kids: dict[str, int] = {}
        #: Source offsets, so an element's outer HTML can be sliced out of
        #: the document it came from. `html.parser` reports (line, column);
        #: this turns that into an absolute index.
        self._line_starts: list[int] = []
        self._doc: str = ""
        self._image_open: int | None = None
        self._figure_open: int | None = None
        self._figcaption = False
        self.main_region: str = "whole body"
        self._after: dict | None = None
        self.images: list[tuple[str, str | None]] = []
        self.image_details: list[dict] = []
        self.jsonld: list[str] = []
        #: What carried each block, parallel to `jsonld` (brief v16 step
        #: AS). A plugin names itself in the script's `id` - `rank-math`,
        #: `slim-seo-schema` - and knowing which plugin wrote a block is
        #: the difference between "edit this JSON" and "change this
        #: setting", which is what a fix card has to say.
        self.jsonld_ids: list[str] = []
        self.script_srcs: list[str] = []
        self.text_parts: list[str] = []
        #: The words inside the main region only, for the parity probe's
        #: main-region hash (item 151). Empty where no region was found.
        self.main_parts: list[str] = []
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._in_jsonld = False
        # Inside a <script> or <style>: their text is code, not the page's
        # words, and until this it flowed into `text_parts`, so `text`,
        # `word_count` and `opening` carried inline JavaScript (a Wix
        # first-paint blob shown as the page's opening on the Content tab).
        self._in_script = False
        self._in_body = False

        # --- accessibility state ------------------------------------------
        self.lang: str | None = None
        self.ids: list[str] = []
        self.aria_refs: list[tuple[str, str]] = []
        self.tabindexes: list[str] = []
        self.form_controls: list[dict] = []
        self.label_for: list[str] = []
        self.links: list[dict] = []
        self.buttons: list[dict] = []
        self.iframes: list[dict] = []
        self.tables: list[dict] = []
        self.landmarks: set[str] = set()
        # An accessible name is built from everything inside the element,
        # including nested text and the alt of any image it contains, so this
        # is a stack rather than the single-slot _capture used for headings —
        # a link inside a heading must not steal that slot.
        self._named: list[dict] = []
        #: One entry per element carrying an `id`, with where it sits.
        self.id_where: list[dict] = []
        self._label_depth = 0
        self.has_post_form = False
        self._table_stack: list[dict] = []
        # Markup inside <noscript> is never rendered for anyone running
        # JavaScript, which is nearly everyone, and a rendered checker never
        # sees it either. Counting it would report a barrier that does not
        # exist — a tag manager's noscript iframe being the usual culprit.
        self._noscript_depth = 0

    #: Elements and roles that make a page navigable by region.
    _LANDMARK_TAGS = {"main", "nav", "header", "footer", "aside", "form"}
    _LANDMARK_ROLES = {"main", "navigation", "banner", "contentinfo",
                       "complementary", "search", "form", "region"}
    _CONTROL_TAGS = {"input", "select", "textarea"}

    # -- the element path (136j Part A) ---------------------------------

    def _abs_pos(self) -> int:
        line, col = self.getpos()
        if 1 <= line <= len(self._line_starts):
            return self._line_starts[line - 1] + col
        return 0

    def _push(self, tag: str, a: dict) -> dict:
        """Open `tag`, after closing anything it implicitly closes."""
        closes = IMPLICIT_CLOSE.get(tag)
        while closes and self._el_stack and self._el_stack[-1]["tag"] in closes:
            self._el_stack.pop()
        kids = self._el_stack[-1]["kids"] if self._el_stack else self._root_kids
        kids[tag] = kids.get(tag, 0) + 1
        entry = {"tag": tag, "id": (a.get("id") or "").strip() or None,
                 "cls": ((a.get("class") or "").split() or [None])[0],
                 "nth": kids[tag], "kids": {}, "start": self._abs_pos()}
        if tag not in VOID_ELEMENTS:
            self._el_stack.append(entry)
        return entry

    def _selector(self, entry: dict, normalise: bool) -> str:
        """A CSS path to `entry`, from the nearest usable id or the root.

        An id wins outright and the path stops there - that is what the item
        asks for and it is also the only part of this that is guaranteed
        unique. Otherwise it is tag plus first class plus `nth-of-type`,
        capped at `SELECTOR_DEPTH` because a path from `html` is unreadable
        and identifies no better than its tail.
        """
        chain = [*self._el_stack, entry] if entry not in self._el_stack else list(self._el_stack)
        parts: list[str] = []
        for e in reversed(chain):
            eid = e["id"]
            if eid and not (normalise and GENERATED_ID.match(eid)):
                parts.append("#" + eid)
                break
            bit = e["tag"]
            if e["cls"]:
                cls = e["cls"]
                if not (normalise and GENERATED_ID.match(cls)):
                    bit += "." + cls
            if e["nth"] > 1:
                bit += f":nth-of-type({e['nth']})"
            parts.append(bit)
            if len(parts) >= SELECTOR_DEPTH:
                break
        return " > ".join(reversed(parts))

    def _landmark(self) -> str:
        """The nearest ancestor landmark, or `none`. The region stack was
        already maintained for images (brief v16 step AU1); this reads it."""
        return self._region_stack[-1][1] if self._region_stack else "none"

    def _outer_html(self, entry: dict) -> str:
        """The element as it was written, cut at its own close tag.

        A window forward from the element's source offset rather than a
        buffered subtree: the instance is captured when the element OPENS,
        so its end is not known yet, and holding every open element's text
        against the chance it is captured would cost the whole document.
        The window is generous enough that the close tag falls inside it for
        anything short enough to be worth showing, and where it does not the
        text is truncated - which is what an operator gets either way at 200
        characters.
        """
        start = entry["start"]
        if not self._doc or start <= 0:
            return ""
        window = self._doc[start:start + INSTANCE_HTML * 3]
        close = window.find(f"</{entry['tag']}>")
        if close >= 0:
            window = window[:close + len(entry["tag"]) + 3]
        return " ".join(window.split())[:INSTANCE_HTML]

    def _where(self, entry: dict) -> dict:
        """The position fields every instance carries, whatever the check."""
        return {"selector": self._selector(entry, normalise=False),
                "selector_norm": self._selector(entry, normalise=True),
                "landmark": self._landmark(),
                "html": self._outer_html(entry)}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._here = self._push(tag, a)

        # The main region (brief v11 step AJ): <main>, then role=main, then
        # <article>, in that order of confidence; headings inside it are
        # the ones h1-missing and h1-multiple judge.
        role = (a.get("role") or "").lower()
        if tag == "main" or role == "main" or tag == "article":
            self._main_stack.append(tag)
            how = "<main>" if tag == "main" else "role=main" if role == "main" else "<article>"
            rank = {"<main>": 0, "role=main": 1, "<article>": 2, "whole body": 3}
            if rank[how] < rank[self.main_region]:
                self.main_region = how

        # The region an image sits in and the link it sits inside (brief
        # v15 step AQ). Both are what the markup says, and both are what a
        # linked image's alt is judged against.
        if tag in self._LANDMARK_TAGS or role in self._LANDMARK_ROLES:
            self._region_stack.append(
                (tag, tag if tag in self._LANDMARK_TAGS else role))
        if tag == "a":
            self._link_depth += 1
            if self._link_depth == 1:
                self._link_href = (a.get("href") or "").strip()[:300] or None
        if tag == "figure":
            self._figure_open = len(self.image_details)
        if tag == "figcaption":
            self._figcaption = True

        if tag == "noscript":
            self._noscript_depth += 1

        # Unconditional first: these attributes can appear on any element, so
        # they cannot live in the if/elif chain below, which already claims
        # img, meta, link and script.
        if tag == "html" and a.get("lang") is not None:
            self.lang = a["lang"]
        if a.get("id"):
            self.ids.append(a["id"])
            # Beside `ids` rather than inside it: three checks read that list
            # as bare strings, and widening it would move the defect into
            # them. `duplicate-id` reads this one.
            self.id_where.append({"id": a["id"], **self._where(self._here)})
        for attr in ("aria-labelledby", "aria-describedby", "aria-controls"):
            for ref in (a.get(attr) or "").split():
                self.aria_refs.append((attr, ref))
        if a.get("tabindex") is not None:
            self.tabindexes.append(a["tabindex"])
        if tag in self._LANDMARK_TAGS:
            self.landmarks.add(tag)
        role = (a.get("role") or "").lower().strip()
        if role in self._LANDMARK_ROLES:
            self.landmarks.add(f"role={role}")
        # An image inside a link or button contributes its alt to that
        # element's accessible name — an icon-only link is only nameless when
        # the icon is nameless too.
        if tag == "img" and self._named and (a.get("alt") or "").strip():
            self._named[-1]["parts"].append(a["alt"])

        if self._noscript_depth:
            # Collected above (ids and aria refs still matter for duplicate
            # detection across the document), but nothing below is a barrier
            # a user will meet.
            pass
        elif tag in ("a", "button"):
            # `where` is taken here and not at the close: by then the
            # element has been popped and the stack describes its parent.
            self._named.append({"tag": tag, "attrs": a, "parts": [],
                                "where": self._where(self._here)})
        elif tag == "form":
            if (a.get("method") or "").strip().lower() == "post":
                self.has_post_form = True
        elif tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.label_for.append(a["for"])
        elif tag in self._CONTROL_TAGS:
            self.form_controls.append({
                "tag": tag,
                "type": (a.get("type") or "").lower(),
                "id": a.get("id"),
                "name": a.get("name"),
                "aria_label": a.get("aria-label"),
                "aria_labelledby": a.get("aria-labelledby"),
                "title": a.get("title"),
                "placeholder": a.get("placeholder"),
                # A control written inside its <label> is labelled without
                # needing for/id at all.
                "wrapped_in_label": self._label_depth > 0,
                **self._where(self._here),
            })
        elif tag == "iframe":
            self.iframes.append({"src": a.get("src") or "",
                                 "title": a.get("title"),
                                 "aria_label": a.get("aria-label")})
        elif tag == "table":
            self._table_stack.append({"th": 0, "rows": 0,
                                      "role": (a.get("role") or "").lower()})
        elif tag == "th" and self._table_stack:
            self._table_stack[-1]["th"] += 1
        elif tag == "tr" and self._table_stack:
            self._table_stack[-1]["rows"] += 1

        if tag == "meta":
            name = (a.get("name") or "").lower()
            if name and a.get("content") is not None:
                self.meta[name] = a["content"]
                if name == "viewport":
                    self.viewport_tags.append(a["content"])
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href")
        elif tag == "link" and (a.get("rel") or "").lower() == "alternate" \
                and a.get("hreflang"):
            self.hreflang.append((a["hreflang"], a.get("href") or ""))
        elif tag in ("img", "source"):
            if tag == "img":
                self.images.append((a.get("src") or "", a.get("alt")))
            src = a.get("src") or a.get("srcset") or ""
            # Everything an image's own markup says about it (brief v15
            # step AQ). What needs a browser - the width it renders at, the
            # CSS aspect ratio, whether it is the LCP candidate - is not
            # here and is not guessed at; `evidence.py` records those as
            # null with the reason.
            self.image_details.append({
                "tag": tag,
                "src": src,
                # Item 241: where a script lazy loader keeps the real file
                # while `src` holds a placeholder (`data:` on twenty22's WP
                # Rocket markup, 271 of 366 images). The browser pass keys an
                # image by this attribute where it has one, so the markup
                # and the measurement meet on the file and not on a
                # placeholder a hundred images share.
                "lazy_src": _lazy_src(a),
                "alt": a.get("alt"),
                "width": a.get("width"),
                "height": a.get("height"),
                "loading": a.get("loading"),
                "fetchpriority": a.get("fetchpriority"),
                "decoding": a.get("decoding"),
                "srcset": (a.get("srcset") or "")[:300],
                "sizes": a.get("sizes"),
                "type": a.get("type"),
                "role": a.get("role"),
                "css_class": (a.get("class") or "")[:120],
                # The anchor this image sits inside, if any: an image in a
                # link is anchor context, and its alt is about the
                # destination rather than the picture.
                "linked_to": self._link_href,
                # Where on the page it sits, as far as the markup says.
                "region": self._region(),
                # And which of the page's three parts that region is
                # (brief v16 step AU1). `region` names the landmark and is
                # what a reader wants on the card; `region_class` is what
                # the grid groups by and what the template rule counts.
                "region_class": self._region_class(),
                "in_main": bool(self._main_stack),
                # Filled as the document is read past this point.
                "caption": None,
                "adjacent_text": "",
            })
            self._image_open = len(self.image_details) - 1
        elif tag == "body":
            self._in_body = True
        elif tag == "script":
            # `src` was dropped here for the whole life of this parser: only
            # the JSON-LD branch existed, so the one attribute saying where a
            # page's code comes from was parsed and discarded on every crawl.
            self._in_script = True
            src = (a.get("src") or "").strip()
            if src:
                self.script_srcs.append(src[:500])
            if (a.get("type") or "").lower() == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_id = (a.get("id") or a.get("class") or "").strip()[:120]
                self._buffer = []
        elif tag == "style":
            self._in_script = True
        elif tag in _VOID_CAPTURE and tag != "script":
            self._capture = tag
            self._buffer = []

    def _region(self) -> str:
        """The innermost landmark this element sits in, or the body."""
        return self._region_stack[-1][1] if self._region_stack else "body"

    #: The landmarks that make a region the page's furniture rather than
    #: its content, per brief v16 step AU1.
    _HEADER_REGIONS = {"header", "nav", "banner", "navigation"}
    _FOOTER_REGIONS = {"footer", "contentinfo"}

    def _region_class(self) -> str:
        """`header`, `footer` or `body` - which of the three parts of the
        page this element is in, rather than which landmark encloses it.

        Footer wins where both are on the stack, which is a `<nav>` inside
        a `<footer>`: that nav is footer furniture, and grouping it with
        the masthead would put the site's legal links above the content.
        Read off the whole stack rather than the innermost landmark for
        the same reason - the innermost of `<footer><nav>` is the nav.
        """
        seen = {region for _, region in self._region_stack}
        if seen & self._FOOTER_REGIONS:
            return "footer"
        if seen & self._HEADER_REGIONS:
            return "header"
        return "body"

    def _close(self, tag: str) -> None:
        """Pop back to `tag`, tolerating stray closes.

        A `</div>` with no matching open must not empty the stack - real
        markup carries them and a cleared stack makes every later selector
        root-relative and wrong. So the tag is looked for first and the
        close ignored when it is not there.
        """
        for i in range(len(self._el_stack) - 1, -1, -1):
            if self._el_stack[i]["tag"] == tag:
                del self._el_stack[i:]
                return

    def handle_endtag(self, tag):
        self._close(tag)
        # The nearest region this tag opened, not the top of the stack:
        # unbalanced markup is common enough that popping blindly
        # mis-attributes, which is the reason `_named` below does the same.
        for i in range(len(self._region_stack) - 1, -1, -1):
            if self._region_stack[i][0] == tag:
                self._region_stack.pop(i)
                break
        if tag == "a" and self._link_depth:
            self._link_depth -= 1
            if not self._link_depth:
                self._link_href = None
        if tag == "figure":
            self._figure_open = None
        if tag == "figcaption":
            self._figcaption = False
        if tag == "noscript" and self._noscript_depth:
            self._noscript_depth -= 1
        if self._main_stack and tag == self._main_stack[-1]:
            self._main_stack.pop()

        if tag in ("a", "button") and self._named:
            # Unbalanced markup is common enough that popping blindly would
            # mis-attribute names; close the nearest matching element.
            for i in range(len(self._named) - 1, -1, -1):
                if self._named[i]["tag"] == tag:
                    el = self._named.pop(i)
                    at = el["attrs"]
                    record = {
                        "href": at.get("href"),
                        "text": " ".join(" ".join(el["parts"]).split()),
                        "aria_label": at.get("aria-label"),
                        "aria_labelledby": at.get("aria-labelledby"),
                        "title": at.get("title"),
                        "role": (at.get("role") or "").lower(),
                        **el.get("where", {}),
                    }
                    (self.links if tag == "a" else self.buttons).append(record)
                    break
        elif tag == "label" and self._label_depth:
            self._label_depth -= 1
        elif tag == "table" and self._table_stack:
            self.tables.append(self._table_stack.pop())

        if tag in ("script", "style"):
            self._in_script = False
        if tag == "script" and self._in_jsonld:
            self.jsonld.append("".join(self._buffer).strip())
            self.jsonld_ids.append(getattr(self, "_jsonld_id", ""))
            self._in_jsonld = False
        elif tag == self._capture:
            text = " ".join("".join(self._buffer).split())
            if tag == "title":
                self.facts_title = text
            elif tag.startswith("h"):
                self.headings.append((int(tag[1]), text))
                entry = {"level": int(tag[1]), "text": text,
                         "in_main": bool(self._main_stack), "next_text": ""}
                self.outline.append(entry)
                self._after = entry
            self._capture = None

    def handle_data(self, data):
        if self._named and data.strip():
            # Every open link/button, not just the innermost: nested text
            # belongs to each ancestor's accessible name.
            for el in self._named:
                el["parts"].append(data.strip())
        if self._in_jsonld or self._capture:
            self._buffer.append(data)
        if self._in_body and not self._in_jsonld and not self._in_script:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)
                if self._main_stack:
                    self.main_parts.append(stripped)
                # The first forty words after the last heading, for the
                # brief's question-unanswered and overstuffed checks.
                if self._after is not None and not self._capture:
                    have = self._after["next_text"].split()
                    if len(have) < 40:
                        self._after["next_text"] = " ".join((have + stripped.split())[:40])
                    else:
                        self._after = None
                # The same forty words for the image last opened (brief v15
                # step AQ): what a reader sees beside the picture, which is
                # where an image's meaning lives when it is not in the alt.
                if self._image_open is not None:
                    img = self.image_details[self._image_open]
                    if self._figcaption:
                        img["caption"] = " ".join(
                            ((img["caption"] or "") + " " + stripped).split())[:300]
                    else:
                        words = img["adjacent_text"].split()
                        if len(words) < 40:
                            img["adjacent_text"] = " ".join((words + stripped.split())[:40])
                        elif self._figure_open is None:
                            self._image_open = None



#: The share of a run's HTML pages an image must appear on, at the same
#: position, to be the site's furniture rather than one page's content
#: (brief v16 step AU1).
TEMPLATE_SHARE = 0.8

#: And the fewest pages that share can be read from. On a two-page crawl
#: every image on both pages is on 100% of them, which is arithmetic rather
#: than evidence of a template - and the cost of believing it is a fix card
#: reading "fixes 2 pages" about a photograph. Three is the smallest number
#: at which 80% is not simply "all of them".
TEMPLATE_MIN_PAGES = 3

#: How near the top or the bottom of the document an image must sit to be
#: read as furniture where the page declares no landmarks at all.
TEMPLATE_EDGE = 0.2


def position_key(img: dict) -> str:
    """Where an image sits, as near a selector as this parser gets.

    The brief asks for "the same `src` at the same selector". There is no
    selector here - `html.parser` builds no tree - so the key is the src,
    the part of the page it is in, and its class attribute, which is what a
    template writes the same way on every page it renders. Stated rather
    than approximated silently: two different images sharing a src, a
    region and a class are one image to this rule, and a template that
    varies its classes per page defeats it.

    The file, not a lazy loader's placeholder (item 246): keyed on `src`,
    every lazy image in one region with one class - a hundred WP Rocket
    thumbnails sharing a `data:` SVG - was one image to this rule.
    """
    return "|".join([str(img.get("lazy_src") or img.get("src") or ""),
                     str(img.get("region_class") or "body"),
                     str(img.get("css_class") or "")])


def mark_template_images(pages: list[tuple[list[dict], list[str]]]) -> None:
    """Set `template` on every inventory row of a run, in place.

    Takes (inventory, keys) per page rather than reading the keys off the
    rows, because the key wants the class attribute and the stored row does
    not carry it - a class is noise on a card and a selector to this rule.

    Landmarks first, as everywhere in AU1: an image the markup puts in the
    header or the footer is furniture whatever its share, because that is
    what those landmarks mean, and a site whose header carries one image
    should not need three pages crawled before it says so. The share rule
    finds the rest - a CTA banner in every post template is body content
    that is still one change. The vertical rule is the fallback for pages
    that declare no landmark at all, where the top and bottom fifth of the
    document is the only statement of "header" and "footer" there is; it
    moves an image's `region_class` only alongside the share, because
    position on one page is not evidence of a template on its own.

    One writing, called from `crawler.evidence.snapshot` for what is stored
    and from the ONP sweep for what is raised. Two would be two answers to
    "how many problems does Images have", which is the count AU2 is about.
    """
    counts: dict[str, int] = {}
    for _, keys in pages:
        for key in set(keys):
            counts[key] = counts.get(key, 0) + 1
    threshold = round(len(pages) * TEMPLATE_SHARE)
    enough = len(pages) >= TEMPLATE_MIN_PAGES
    for inventory, keys in pages:
        for img, key in zip(inventory, keys):
            region = img.get("region_class") or "body"
            share = enough and counts.get(key, 0) >= threshold
            img["template"] = bool(region in ("header", "footer") or share)
            top = img.get("top_pct")
            if region == "body" and share and isinstance(top, (int, float)):
                if top <= TEMPLATE_EDGE or top >= 1 - TEMPLATE_EDGE:
                    img["region_class"] = "header" if top <= TEMPLATE_EDGE else "footer"
                    # Never confused with what the markup said: a card that
                    # reads "footer" off a measurement says which.
                    img["region_from"] = "position"


#: The largest an image can be declared and still be an icon rather than
#: the logo. The sweep applies the same number under its own name; both are
#: 48 because that is where an interface glyph stops and a mark starts.
LOGO_ICON_PX = 48


def _px_attr(value) -> int | None:
    """A width or height attribute as a number, or None where the markup
    gives a percentage, a calc, or nothing at all."""
    try:
        return int(str(value).strip().rstrip("px"))
    except (TypeError, ValueError):
        return None


def schema_logo(jsonld_blocks: list[str]) -> str | None:
    """The `logo` a page's own structured data declares for its entity.

    `logo` only, never `image`: an entity's `image` is routinely a
    photograph - a Google-hosted shopfront, most often - and treating it as
    the logo would have the part page telling an operator to replace their
    masthead with a picture of their door.

    Read out of every node and every `@graph` member, because a site that
    publishes one `@graph` per page puts the Organization inside it and a
    reader of top-level nodes alone finds nothing.
    """
    for raw in jsonld_blocks:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            logo = node.get("logo")
            if isinstance(logo, str) and logo.strip():
                return logo.strip()
            if isinstance(logo, dict):
                url = logo.get("url") or logo.get("contentUrl")
                if isinstance(url, str) and url.strip():
                    return url.strip()
    return None


#: A heading that asks something. `?` is the signal; a heading that opens
#: with an interrogative and drops the mark is one too, because a CMS that
#: strips punctuation from headings is common and the reader still reads a
#: question.
#:
#: Here rather than in `cnt.py` because two parts ask it (brief v17 step
#: AX): Content raises `question-unanswered` when nothing follows the
#: heading, and the Headings brief judges `h2-question-unanswered` - whether
#: the page answers it *in substance* - from the same set of headings. One
#: detector, two questions about what it found; two detectors would be two
#: answers to "is this a question", and the parts would disagree about
#: which headings they were even discussing.
_QUESTION_WORDS = ("what", "why", "how", "when", "where", "who", "which",
                   "can", "do", "does", "is", "are", "should", "will")


def is_question(text: str) -> bool:
    words = (text or "").strip().lower().split()
    if not words:
        return False
    return text.strip().endswith("?") or words[0] in _QUESTION_WORDS


def _links_home(href: str | None, page_url: str | None) -> bool:
    """Whether an anchor goes to the site's home page.

    `/` is the common form and was the only one this understood, so a
    masthead wrapped in `https://www.example.com/` - which is what several
    site builders emit - did not read as linked home at all. Compared
    against the page's own origin rather than against a stored domain,
    because the crawl's own URL is the one thing here that is certainly
    right about which site this is.
    """
    href = (href or "").strip()
    if not href:
        return False
    if href in ("/", "./", "#"):
        return href == "/"
    if not page_url:
        return False
    try:
        base = urlsplit(page_url)
        target = urlsplit(urljoin(page_url, href))
    except ValueError:
        return False
    return (target.netloc == base.netloc and target.path in ("", "/")
            and not target.query)


def identify_logo(inventory: list[dict], jsonld_blocks: list[str],
                  brand: str | None = None,
                  page_url: str | None = None) -> dict | None:
    """Mark the header image that is the logo, and say which signal found
    it (brief v16 step AU6).

    Three signals, and the order is the whole point: the schema is what the
    site itself says its logo is, so a heuristic that disagreed with it
    would be the part page arguing with the site's own declaration. Only
    where the schema is silent does the markup get a say, and only where
    the markup says nothing does position decide.

    `logo_from` travels with the answer. A card that says which signal
    found the logo is one an operator can disagree with; one that just
    asserts it is not.

    Called with no brand where the record is made - the crawl has no site
    to ask - and with one from the sweep, where it refines the second
    signal only. The brand's real work is judging the alt text, which is
    the sweep's job and not this function's.
    """
    header = [i for i in inventory if (i.get("region_class") or "body") == "header"]
    if not header:
        return None
    declared = schema_logo(jsonld_blocks)
    if declared:
        tail = declared.rsplit("/", 1)[-1].split("?")[0].lower()
        for img in header:
            src = str(img.get("src") or "")
            if src == declared or (tail and src.split("?")[0].lower().endswith(tail)):
                img["is_logo"] = True
                img["logo_from"] = "the entity's declared logo in structured data"
                return img
    words = {"logo"} | {w for w in (brand or "").lower().split() if len(w) > 2}
    for img in header:
        text = " ".join([str(img.get("src") or ""), str(img.get("alt") or ""),
                         str(img.get("css_class") or "")]).lower()
        # A link to home, not the absence of one. `in ("/", "")` read an
        # unlinked image as linked to the home page, so this signal claimed
        # a logo the very next check reported as "not wrapped in a link" -
        # one row asserting and denying the same fact.
        if _links_home(img.get("linked_to"), page_url) and any(w in text for w in words):
            img["is_logo"] = True
            img["logo_from"] = "a header image linked to the home page naming the brand"
            return img
    for img in header:
        # Declared size only, and only when it says small. A logo is
        # routinely an SVG, and the sweep's own icon test would call every
        # SVG in the header furniture - which is the one image AU6 exists
        # to say is not.
        width, height = _px_attr(img.get("width")), _px_attr(img.get("height"))
        if not ((width is not None and width <= LOGO_ICON_PX)
                or (height is not None and height <= LOGO_ICON_PX)):
            img["is_logo"] = True
            img["logo_from"] = "the first image in the header that is not an icon"
            return img
    return None

#: How many structured-data blocks one page's inventory keeps. Measured
#: across the stored crawls: a page carries one to four, and the sites that
#: carry more are carrying duplicates - which is `schema-redundant-block`
#: and is a finding rather than a reason to store forty of them.
SCHEMA_BLOCK_CAP = 20

#: How many raw blocks one page keeps for the picture, and the ceiling on
#: what they may weigh together. The graph (RENDER_RULES section 1) needs
#: the blocks as served, not the flattened inventory: the inventory keeps
#: two levels and collapses a list of objects to its first member, so a
#: reference three deep inside an `itemListElement` is not in it.
#:
#: Whole blocks are dropped, never truncated. A block cut mid-object does
#: not parse, and `schema-invalid-json` would then fire on markup that is
#: valid on the page - a storage limit inventing a finding about the site.
JSONLD_RAW_CAP = 20
JSONLD_RAW_BYTES = 200_000

#: How deep a block's properties are flattened. Two levels reaches
#: `address.streetAddress` and `aggregateRating.ratingValue`, which is what
#: the checks read; deeper is a graph, and the graph is what `@id` is for.
SCHEMA_FLAT_DEPTH = 2

#: Hosts a profile link points at. The brief's distinction is between
#: profiles the entity *controls* and places that merely mention it, and
#: that is a fact about ownership which no crawl can see - so this list is
#: the candidates, handed to the brief beside the site record's own two
#: lists, and never a claim that the entity owns any of them.
PROFILE_HOSTS = (
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "pinterest.com", "wikidata.org",
    "wikipedia.org", "g.page", "goo.gl", "maps.google.com", "maps.app.goo.gl",
)


def _flatten(value: Any, prefix: str = "", depth: int = 0) -> dict[str, Any]:
    """A block's properties as `key -> value`, two levels down.

    Lists of scalars are joined; a list of objects keeps its first member
    and says how many there were, because "three offers" and "one offer"
    are different findings and the first one is representative.
    """
    out: dict[str, Any] = {}
    if depth > SCHEMA_FLAT_DEPTH:
        return out
    if isinstance(value, dict):
        for key, inner in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(inner, (dict, list)):
                out.update(_flatten(inner, name, depth + 1))
            elif inner is not None:
                out[name] = inner if isinstance(inner, (int, float, bool)) else str(inner)[:300]
    elif isinstance(value, list):
        scalars = [v for v in value if not isinstance(v, (dict, list))]
        if scalars and len(scalars) == len(value):
            out[prefix or "value"] = ", ".join(str(v)[:120] for v in scalars[:10])
        elif value:
            out.update(_flatten(value[0], prefix, depth))
            if len(value) > 1:
                out[f"{prefix}._count"] = len(value)
    return out


def _block_source(script_id: str) -> str:
    """Where a block came from, as far as the markup says.

    A plugin names itself in the script's `id` - `rank-math-schema`,
    `slim-seo-schema`, `yoast-schema-graph`. Anything else is `inline`,
    which is the honest answer: a theme and a hand-written block are
    indistinguishable from the HTML, and guessing between them would put a
    fix card's instructions in the wrong place.
    """
    name = (script_id or "").strip().lower()
    if not name:
        return "inline"
    for marker in ("rank-math", "rankmath", "slim-seo", "yoast", "wpseo",
                   "seopress", "aioseo", "squarespace", "wix", "shopify"):
        if marker in name:
            return f"plugin:{marker}"
    return f"inline:{name[:60]}"


def jsonld_raw(jsonld_blocks: list[str], jsonld_ids: list[str]) -> list[dict]:
    """Each block as it was served, with the source the markup names.

    `schema_inventory` is what the checks read and `jsonld_raw` is what the
    picture is built from; they are two readings of the same blocks and not
    two sources. The inventory flattens to `SCHEMA_FLAT_DEPTH` and keeps a
    list's first member only, which is the right shape for a row about a
    property and the wrong one for a graph - Summit's fifteen `provider`
    references live inside an `itemListElement` and the inventory cannot see
    any of them.

    Blocks are kept whole or not at all, per `JSONLD_RAW_CAP` and
    `JSONLD_RAW_BYTES`. Truncating one would produce a block that does not
    parse, and the parse failure is itself a finding.

    A block that does not parse *on the page* is kept exactly as served: the
    picture draws no nodes for it, and `schema-invalid-json` is what says so.
    """
    out: list[dict] = []
    budget = JSONLD_RAW_BYTES
    for n, raw in enumerate(jsonld_blocks[:JSONLD_RAW_CAP]):
        text = raw if isinstance(raw, str) else ""
        if len(text) > budget:
            break
        budget -= len(text)
        out.append({"source": _block_source(jsonld_ids[n]
                                            if n < len(jsonld_ids) else ""),
                    "text": text})
    return out


def schema_inventory(jsonld_blocks: list[str], jsonld_ids: list[str]) -> list[dict]:
    """Every JSON-LD block on one page, as parsed (brief v16 step AS).

    **Microdata and RDFa are not here, and the absence is stated rather
    than silent.** The prompt's inventory row names three formats; this
    parser reads `<script type="application/ld+json">` and nothing else,
    so a page whose markup is in Microdata reports no blocks - which the
    brief must not read as "this page has no structured data". The context
    builder says so under its assumptions.

    A block that does not parse is kept with `parse_ok: false` and its own
    error, because that *is* `schema-invalid-json` and dropping it would
    delete the finding.
    """
    out: list[dict] = []
    for n, raw in enumerate(jsonld_blocks[:SCHEMA_BLOCK_CAP]):
        script_id = jsonld_ids[n] if n < len(jsonld_ids) else ""
        record: dict[str, Any] = {"format": "json-ld", "source": _block_source(script_id)}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            record.update({"parse_ok": False, "error": str(exc)[:200],
                           "type": None, "id": None, "properties": {}})
            out.append(record)
            continue
        # A `@graph` is several blocks in one script, and the checks are
        # about nodes rather than about scripts: an orphan instance inside
        # a graph is still an orphan.
        nodes = data.get("@graph") if isinstance(data, dict) and "@graph" in data else data
        for node in (nodes if isinstance(nodes, list) else [nodes]):
            if not isinstance(node, dict):
                continue
            kind = node.get("@type")
            out.append({**record, "parse_ok": True,
                        "type": kind if isinstance(kind, str) else
                                ", ".join(str(k) for k in kind) if isinstance(kind, list) else None,
                        "id": node.get("@id"),
                        "in_graph": nodes is not data,
                        "properties": _flatten({k: v for k, v in node.items()
                                                if k not in ("@context", "@graph")})})
            if len(out) >= SCHEMA_BLOCK_CAP:
                break
        if len(out) >= SCHEMA_BLOCK_CAP:
            break
    return out


def block_key(block: dict) -> str:
    """What makes two structured-data blocks the same block.

    `@type` and `@id`, per brief v16 step AS. Not the properties: an
    Organization node whose `@id` is the site's entity is the same node on
    every page it appears on even where one page adds a `telephone`, and a
    rule that compared the whole block would call each page's copy its own
    and give an operator twelve cards for one edit. A block with no `@id`
    is keyed on its type and its source, which is as near as this gets to
    identity when the markup declines to state one.
    """
    return "|".join([str(block.get("type") or ""), str(block.get("id") or ""),
                     "" if block.get("id") else str(block.get("source") or "")])


def mark_template_blocks(pages: list[list[dict]]) -> None:
    """Set `template` on every block of a run, in place.

    The same share and the same floor as the images, and for the same
    reason: on a two-page crawl every block on both is on 100% of them,
    which is arithmetic rather than evidence. There is no landmark rule
    here - a block has no position on the page that means anything - so
    repetition is the whole test.
    """
    counts: dict[str, int] = {}
    for blocks in pages:
        for key in {block_key(b) for b in blocks}:
            counts[key] = counts.get(key, 0) + 1
    threshold = round(len(pages) * TEMPLATE_SHARE)
    enough = len(pages) >= TEMPLATE_MIN_PAGES
    for blocks in pages:
        for b in blocks:
            b["template"] = bool(enough and counts.get(block_key(b), 0) >= threshold)
            b["pages"] = counts.get(block_key(b), 0)


def profile_links(links: list[dict]) -> list[str]:
    """The page's links to profile hosts, deduplicated and in order.

    Candidates, never a claim of ownership: whether the entity controls a
    profile is what the site record's `sameas_sources` says, and the whole
    of `schema-sameas-misplaced` is that the two are different questions.
    """
    seen: list[str] = []
    for link in links:
        # `href` is what the parser records and `url` is what the crawler's
        # own link list carries; both are read so this works off either,
        # and reading only one is how it returned nothing at all first try.
        url = str((link or {}).get("href") or (link or {}).get("url") or "")
        host = urlsplit(url).netloc.lower().removeprefix("www.")
        if host and any(host == h or host.endswith("." + h) for h in PROFILE_HOSTS):
            if url not in seen:
                seen.append(url)
    return seen[:30]


def extract_facts(page: Page) -> PageFacts:
    parser = _FactParser()
    # The document and its line offsets, so an element captured mid-parse can
    # be sliced back out of the source for its outer HTML (136j Part A).
    # `html.parser` reports (line, column) and nothing absolute.
    parser._doc = page.content or ""
    offset, starts = 0, []
    for line in parser._doc.splitlines(keepends=True):
        starts.append(offset)
        offset += len(line)
    parser._line_starts = starts
    try:
        parser.feed(page.content)
    except Exception:
        pass
    facts = PageFacts(url=page.url, path=urlsplit(page.url).path or "/")
    facts.title = parser.facts_title
    facts.meta_description = parser.meta.get("description")
    facts.meta_robots = parser.meta.get("robots")
    facts.viewport = parser.meta.get("viewport")
    facts.viewport_tags = parser.viewport_tags
    facts.hreflang = parser.hreflang
    facts.canonical = parser.canonical
    facts.link_header_canonical = page.link_header_canonical
    facts.headings = parser.headings
    facts.outline = parser.outline
    facts.main_region = parser.main_region
    facts.images = parser.images
    facts.image_details = parser.image_details
    facts.jsonld_blocks = parser.jsonld
    facts.jsonld_ids = parser.jsonld_ids
    facts.script_srcs = parser.script_srcs
    for block in parser.jsonld:
        try:
            json.loads(block)
        except json.JSONDecodeError as exc:
            facts.jsonld_errors.append(str(exc))
    facts.text = " ".join(parser.text_parts)
    facts.word_count = len(facts.text.split())
    facts.main_text = (" ".join(parser.main_parts) if parser.main_parts
                       else facts.text)

    facts.lang = parser.lang
    facts.ids = parser.ids
    facts.has_post_form = parser.has_post_form
    facts.id_where = parser.id_where
    facts.aria_refs = parser.aria_refs
    facts.tabindexes = parser.tabindexes
    facts.form_controls = parser.form_controls
    facts.label_for = parser.label_for
    facts.links = parser.links
    facts.buttons = parser.buttons
    facts.iframes = parser.iframes
    # Anything still open at EOF (truncated or unbalanced markup) is closed
    # here rather than dropped, so a broken page still reports what it has.
    facts.tables = parser.tables + parser._table_stack
    facts.landmarks = parser.landmarks
    return facts


def html_pages(pages: list[Page]) -> list[Page]:
    return [p for p in pages if p.status == 200 and p.content_type.startswith("text/html")]


def rendered_words(blocks: list[dict]) -> int:
    """The words a browser rendered, from the a11y pass's text blocks, counting
    each piece of text once. The blocks nest (a nav `li` holds its links' words
    and each link is a block too), so a block drawn inside another block's box
    is skipped and the outermost carries the words. Summing every block counted
    twenty22's pages at 41-89% of their initial HTML when the pages are
    server-rendered: the first acceptance run raised five false HIGH rows.

    Here rather than in `ais`, because two checks ask the same question of the
    same blocks and had two answers: `AIS/content-behind-js` counted each piece
    once and `TEC/render-only` summed them, so the same page could be called
    render-dependent by one and not the other (item 145's BH report, open item
    5). One owner, beside the raw-HTML `word_count` it is compared against.
    """
    def inside(a: dict, b: dict) -> bool:
        ra, rb = a.get("rect") or {}, b.get("rect") or {}
        try:
            return (ra["x"] >= rb["x"] and ra["y"] >= rb["y"]
                    and ra["x"] + ra["w"] <= rb["x"] + rb["w"]
                    and ra["y"] + ra["h"] <= rb["y"] + rb["h"])
        except (KeyError, TypeError):
            return False
    total = 0
    for i, b in enumerate(blocks):
        if any(j != i and inside(b, o) and (o.get("rect") != b.get("rect") or j < i)
               for j, o in enumerate(blocks)):
            continue
        total += int(b.get("words") or 0)
    return total
