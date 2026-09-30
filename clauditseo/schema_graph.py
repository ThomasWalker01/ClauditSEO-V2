"""The Structured data picture, built from the crawler's own inventory.

Brief v16a step AT-a. RENDER_RULES §1-§7, ported from the designer's
reference implementation (`L1_stacked_drill.html`, functions `buildModel`,
`markRows`, `markItem`) rather than re-derived - the rules are the
specification and that code is the rules, so a second derivation would be a
second answer to the same question.

**Why this is in the engine and not in the dashboard.** The picture has to be
reproducible from what a crawl stored, months later, without the page being
fetched again. A model built in the browser would be a drawing of whatever
the browser could see; this one is a drawing of the run. The dashboard draws
what this returns and decides nothing about it.

Two of the rules need inputs the JSON cannot supply, and they are passed in
rather than guessed - RESPONSE.md's last point:

* the expected-but-absent ghosts need the page-type map and the crawl context
  (a footer's Google Maps links are what produce `LocalBusiness ×4`);
* the per-item problems in a list ("no url", "no location page") and the
  eligibility verdicts are check outputs, not facts about the JSON.

So `build_model` takes four things and invents none of them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

#: Severity order for badges, rings and the checklist. The worst finding
#: anchored to a thing is the thing's colour, so the order has to be total.
SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Held": 3, "Info": 4}
SEV_CLASS = {"High": "high", "Medium": "med", "Low": "low",
             "Held": "held", "Info": "info"}

#: RENDER_RULES §3. A type that names a business, less the three that look
#: like one and are not: `Service` is what a business sells, `FinancialProduct`
#: is a product, and `SpeakableSpecification` merely ends in a matching word.
ENTITY_TYPE_RE = re.compile(
    r"^(Organization|LocalBusiness|Corporation|NGO|GovernmentOrganization"
    r"|EducationalOrganization|MedicalOrganization|SportsOrganization)$"
    r"|(Business|Contractor|Service|Store|Shop|Agency|Company|Salon|Dealer"
    r"|Clinic|Dentist|Restaurant|Hotel|Bank|School)$")
NOT_ENTITY = frozenset({"FinancialProduct", "Service", "SpeakableSpecification"})

#: The "site & page" tier, and the order within it.
SITE_TYPES = frozenset({"WebSite", "WebPage", "BreadcrumbList", "ImageObject",
                        "CollectionPage", "AboutPage", "ContactPage",
                        "SiteNavigationElement"})
TIER_ORDER = ("WebSite", "WebPage", "BreadcrumbList", "ImageObject")

#: A dangling reference through one of these is a reference at the business,
#: so its ghost belongs in the business tier rather than in "other".
ENTITY_REF_PROPS = frozenset({"parentOrganization", "publisher", "about",
                              "provider", "subOrganization", "brand",
                              "itemReviewed"})

#: What each page type must declare (RENDER_RULES §6). `entity` is the
#: sentinel for "a node of a business type, whatever it is called". The home
#: page is exempt from BreadcrumbList, which is why it is absent from that
#: row rather than filtered out later.
EXPECTED_TYPES: dict[str, list[str]] = {
    "home": ["WebSite", "WebPage", "entity"],
    "service": ["WebSite", "WebPage", "BreadcrumbList", "entity", "Service"],
    "location": ["WebSite", "WebPage", "BreadcrumbList", "entity"],
    "blog": ["WebSite", "WebPage", "BreadcrumbList", "Article"],
    "article": ["WebSite", "WebPage", "BreadcrumbList", "Article"],
    "product": ["WebSite", "WebPage", "BreadcrumbList", "Product"],
    "event": ["WebSite", "WebPage", "BreadcrumbList", "Event"],
}

#: Absent on the entity, these are an added amber row rather than silence: a
#: business node with no way to be phoned or found is the finding.
RECOMMENDED_ON_ENTITY = ("address", "telephone")

#: A dangling `@id`'s type, guessed from the property that pointed at it.
#: Guessed and labelled as guessed - the ghost card says "from the property
#: name", because the page does not say.
_TYPE_FROM_PROP = {
    "parentOrganization": "Organization", "founder": "Person",
    "author": "Person", "publisher": "Organization",
    "provider": "Organization", "about": "Thing", "isPartOf": "WebSite",
    "image": "ImageObject", "logo": "ImageObject",
    "breadcrumb": "BreadcrumbList",
}

_PLACEHOLDER = re.compile(r"^\[.*\]$")
_MAPS = re.compile(r"maps\.app\.goo\.gl|google\.com/maps")
_VERIFIED_REVIEW = re.compile(r"verified .*review", re.I)

#: The four eligibility states. `none targeted` is the fourth, added because
#: a home page targets no rich result and the other three would have to lie
#: about it (RESPONSE.md, "Things in the brief I think are wrong").
ELIGIBILITY_VERDICTS = ("eligible", "not eligible", "degraded", "none targeted")


# --------------------------------------------------------------------------
# small helpers over raw JSON-LD

def _types_of(obj: Any) -> list[str]:
    kind = obj.get("@type") if isinstance(obj, dict) else None
    if isinstance(kind, list):
        return [str(k) for k in kind]
    return [str(kind)] if kind else []


def _is_ref_only(v: Any) -> bool:
    return isinstance(v, dict) and "@id" in v and set(v) == {"@id"}


def is_entity_type(t: str) -> bool:
    return bool(ENTITY_TYPE_RE.search(t)) and t not in NOT_ENTITY


def short_id(node_id: str | None, host: str) -> str:
    """An `@id` as it reads on screen: a local one loses scheme and host.

    A foreign host stays whole, because that is the fact worth seeing - an
    `@id` on somebody else's domain is a different claim from one on this
    site's, and shortening both the same way would hide it.
    """
    if not node_id:
        return ""
    parts = urlsplit(str(node_id))
    if not parts.scheme or not parts.netloc:
        return str(node_id)
    if parts.netloc.removeprefix("www.") != host.removeprefix("www."):
        return str(node_id)
    return (parts.path or "/") + (("#" + parts.fragment) if parts.fragment else "")


def _trunc(s: Any, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def _summarise(v: dict) -> str:
    types = "/".join(_types_of(v))
    scalars = [str(x) for k, x in v.items()
               if not str(k).startswith("@") and not isinstance(x, (dict, list))]
    tail = " · " + _trunc(", ".join(scalars), 70) if scalars else ""
    return f"{{ {types}{tail} }}"


# --------------------------------------------------------------------------
# the model's parts

@dataclass
class Block:
    """One `<script type="application/ld+json">`. Acme's supplied file is
    an array of three objects each carrying its own `@context`: that is three
    blocks, and a `@graph` inside one script is one block with several
    top-level nodes. The two are different facts and the picture draws them
    differently, so the distinction has to survive into here."""

    i: int
    key: str
    source: str
    raw: Any
    node_keys: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    state: str = "clean"

    def as_dict(self) -> dict:
        return {"kind": "block", "i": self.i, "key": self.key,
                "source": self.source, "nodes": list(self.node_keys),
                "findings": [f.get("n") for f in self.findings],
                "state": self.state}


@dataclass
class Collection:
    """A list on a node, drawn as a counted chip rather than as items.

    This is why level 0 never grows with item counts: Summit's twenty-nine
    cities are one chip, and the only things that can add a card are
    top-level nodes, ghosts and inline copies.
    """

    key: str
    node_key: str
    prop: str
    count: int
    item_kind: str
    item_type: str
    items: list[dict]
    container: Any = None
    findings: list[dict] = field(default_factory=list)
    problems: int = 0
    state: str = "clean"
    kind: str = "collection"

    def caption(self) -> str:
        """RENDER_RULES §7b's last sentence: the chip says what is wrong with
        its items, not how many there are - the count is already the pill."""
        if not self.problems:
            return "refs" if self.item_type == "@id" else "clean"
        first = next(i for i in self.items if i["marks"])["marks"][0]["note"]
        return (f"all {first}" if self.problems == self.count
                else f"{self.problems} of {self.count} {first}")

    def as_dict(self) -> dict:
        return {"kind": "collection", "key": self.key, "node": self.node_key,
                "prop": self.prop, "count": self.count,
                "item_kind": self.item_kind, "item_type": self.item_type,
                "items": self.items, "problems": self.problems,
                "container": _summarise(self.container)
                if isinstance(self.container, dict) else None,
                "findings": [f.get("n") for f in self.findings],
                "state": self.state, "caption": self.caption()}


@dataclass
class Node:
    """A top-level node, an inline copy, or a ghost. One class for the three
    because level 0 draws them as one kind of card and the drill opens all
    three the same way; what differs is `kind`, and every difference in the
    picture reads from it."""

    kind: str            # node | inline-copy | ghost-dangling | ghost-expected
    key: str
    types: list[str]
    role: str = "other"  # site | entity | other
    id: str | None = None
    sid: str | None = None
    name: str | None = None
    block: int | None = None
    raw: Any = None
    props: list[dict] = field(default_factory=list)
    collections: list[Collection] = field(default_factory=list)
    refs_out: list[dict] = field(default_factory=list)
    refs_in: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    island: bool = False
    state: str = "clean"
    parent: str | None = None
    via_prop: str | None = None
    covers: list[str] = field(default_factory=list)
    count: int | None = None
    note: str | None = None

    @property
    def type(self) -> str:
        return " / ".join(self.types) or "(no @type)"

    def as_dict(self) -> dict:
        raw = self.raw if isinstance(self.raw, dict) else {}
        return {
            "kind": self.kind, "key": self.key, "role": self.role,
            "type": self.type, "types": list(self.types),
            "id": self.id, "sid": self.sid, "name": self.name,
            "block": self.block, "island": self.island, "state": self.state,
            "flags": list(self.flags), "note": self.note,
            "parent": self.parent, "via_prop": self.via_prop,
            "covers": list(self.covers), "count": self.count,
            "props": [{k: v for k, v in p.items() if k != "nested"}
                      for p in self.props],
            "collections": [c.key for c in self.collections],
            "refs_in": [{"prop": r["prop"], "from": r["from_node"]}
                        for r in self.refs_in],
            "refs_out": [{"prop": r["prop"], "to": r["to"],
                          "resolved": r["resolved"],
                          "target": r.get("target_key")}
                         for r in self.refs_out],
            "findings": [f.get("n") for f in self.findings],
            "raw": self.raw,
            # Level 0's stats line, computed here so the card cannot count
            # one thing and the drill another.
            "stats": {
                "properties": len([k for k in raw if not str(k).startswith("@")]),
                "lists": len(self.collections),
                "refs_out": len([r for r in self.refs_out if not r.get("self")]),
                "dangling": len([r for r in self.refs_out if not r["resolved"]]),
            },
        }


@dataclass
class GraphModel:
    host: str
    locale: str | None
    page: str
    page_type: str
    blocks: list[Block]
    nodes: list[Node]
    ghosts: list[Node]
    edges: list[dict]
    collections: dict[str, Collection]
    refs: list[dict]
    verdict: dict
    counts: dict
    findings: list[dict]
    eligibility: list[dict]
    entity_key: str | None
    tiers: tuple[str, ...] = ("site", "entity", "other")

    def node(self, key: str) -> Node | None:
        return next((n for n in [*self.nodes, *self.ghosts] if n.key == key), None)

    def as_dict(self) -> dict:
        return {
            "host": self.host, "locale": self.locale, "page": self.page,
            "page_type": self.page_type, "tiers": list(self.tiers),
            "entity": self.entity_key,
            "blocks": [b.as_dict() for b in self.blocks],
            "nodes": [n.as_dict() for n in self.nodes],
            "ghosts": [g.as_dict() for g in self.ghosts],
            "collections": [c.as_dict() for c in self.collections.values()],
            "edges": list(self.edges),
            "verdict": self.verdict, "counts": self.counts,
            "eligibility": list(self.eligibility),
            "findings": list(self.findings),
        }


# --------------------------------------------------------------------------

class _Builder:
    """One page's model under construction. A class only so the walk can
    carry its state; the entry point is `build_model` and nothing else should
    reach in here."""

    def __init__(self, host: str, locale: str | None) -> None:
        self.host = host
        self.locale = locale
        self.blocks: list[Block] = []
        self.nodes: list[Node] = []
        self.ghosts: list[Node] = []
        self.by_key: dict[str, Node] = {}
        self.cols: dict[str, Collection] = {}
        self.defined: dict[str, tuple[Node, Any, bool]] = {}
        self.refs: list[dict] = []
        self.edges: list[dict] = []
        self.entity: Node | None = None

    # -- §5 edges -------------------------------------------------------
    def add_edge(self, src: str, dst: str, label: str, kind: str) -> None:
        """Several references between one pair merge into one edge with the
        labels joined - `primaryImageOfPage · image` is one line on the
        picture, because two lines between the same two boxes says there are
        two relationships when there is one."""
        for e in self.edges:
            if e["from"] == src and e["to"] == dst and e["kind"] == kind:
                if label not in e["label"].split(" · "):
                    e["label"] += " · " + label
                return
        self.edges.append({"from": src, "to": dst, "label": label, "kind": kind})

    def owner_key(self, key: str) -> str:
        """A collection key `node#prop` back to its node. Node keys are `@id`s
        and contain `#` themselves, so membership is tested before the split:
        reading the last `#` first would turn `/#organization` into `/`."""
        if key in self.by_key:
            return key
        i = key.rfind("#")
        return key[:i] if i > 0 else key

    # -- §4 the walk ----------------------------------------------------
    def walk(self, n: Node, raw: dict, from_key: str, prefix: str) -> None:
        for k, v in raw.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if k == "@context":
                continue
            if str(k).startswith("@"):
                n.props.append({"k": path, "raw": v,
                                "v": ", ".join(str(x) for x in v)
                                if isinstance(v, list) else str(v)})
                continue
            if isinstance(v, list):
                if len(v) >= 2:
                    kind = ("strings" if all(not isinstance(x, (dict, list)) for x in v)
                            else "refs" if all(_is_ref_only(x) for x in v)
                            else "nodes")
                    c = self.make_collection(n, path, v, kind)
                    n.collections.append(c)
                    label = ("value" if kind == "strings"
                             else "@id" if kind == "refs"
                             else (_types_of(v[0])[0] if _types_of(v[0]) else "item"))
                    n.props.append({"k": path, "v": f"{len(v)} × {label}",
                                    "collection": c.key, "raw": v})
                    # A reference inside any item is a reference from the
                    # collection, not from the node: Summit's fifteen
                    # `provider` references leave the chip, and the edge has
                    # to start where the reader can see them.
                    for item in v:
                        if _is_ref_only(item):
                            self.refs.append({"from_node": n.key, "from_key": c.key,
                                              "prop": path, "to": item["@id"]})
                        elif isinstance(item, dict):
                            self.collect_refs(n, c.key, item, path)
                    continue
                if len(v) == 1:
                    v = v[0]
                    if not isinstance(v, dict):
                        n.props.append({"k": path + "[0]", "v": str(v), "raw": v})
                        continue
                else:
                    n.props.append({"k": path, "v": "[]", "mark": "miss",
                                    "note": "empty list", "raw": v})
                    continue
            if _is_ref_only(v):
                n.props.append({"k": path + ".@id", "v": v["@id"],
                                "ref": v["@id"], "raw": v})
                self.refs.append({"from_node": n.key, "from_key": from_key,
                                  "prop": str(k), "to": v["@id"]})
                continue
            if isinstance(v, dict):
                if self.maybe_inline_copy(n, path, v):
                    continue
                if self.maybe_nested_list(n, path, v):
                    continue
                # A plain nested object: one summary row the drill can pin
                # to, then its properties flattened dot-style - exactly as
                # the crawler's own inventory writes them, so an operator
                # comparing the two is comparing the same strings.
                n.props.append({"k": path, "v": _summarise(v), "nested": v,
                                "raw": v, "group": True})
                self.walk(n, v, from_key, path)
                continue
            n.props.append({"k": path, "v": '""' if v == "" else str(v), "raw": v})
        if not prefix:
            self.mark_rows(n)

    def maybe_inline_copy(self, n: Node, path: str, v: dict) -> bool:
        """§4's inline copy: the entity described again instead of referenced.

        The worst thing a graph can do and the hardest to see in raw JSON,
        because it is valid and a validator says so. Drawn as its own node
        with a red double ring and a dotted `should be {"@id": …}` edge back
        to the entity, so the fix is the picture.
        """
        types = _types_of(v)
        if (v.get("@id") or not any(is_entity_type(t) for t in types)
                or self.entity is None or self.entity is n
                or not v.get("name") or v.get("name") != self.entity.name):
            return False
        d = Node(kind="inline-copy", key=f"{n.key}.{path}", types=types,
                 role="other", block=n.block, raw=v, name=v.get("name"),
                 parent=n.key, via_prop=path,
                 flags=["inline copy of "
                        f"{self.entity.sid or self.entity.name} · not a reference"])
        self.walk(d, v, d.key, "")
        self.nodes.append(d)
        self.by_key[d.key] = d
        n.props.append({"k": path,
                        "v": f"{{ {' / '.join(types)} \"{v.get('name')}\" }} inline",
                        "mark": "bad", "link": d.key, "raw": v,
                        "note": "a second copy of the entity, not a reference to it"})
        self.add_edge(n.key, d.key, path + " (inline)", "ok")
        self.add_edge(d.key, self.entity.key, 'should be { "@id": … }', "expected")
        return True

    def maybe_nested_list(self, n: Node, path: str, v: dict) -> bool:
        """§4's nested collection: an `OfferCatalog` is a container, and what
        an operator wants counted is what is inside it, not the wrapper. An
        array of scalars inside the container (`dayOfWeek`) does not make a
        second collection - seven day names are a value, not a list of
        things with their own problems."""
        list_key = next((kk for kk, vv in v.items()
                         if isinstance(vv, list) and len(vv) >= 2
                         and all(isinstance(x, dict) for x in vv)), None)
        if list_key is None:
            return False
        inner = v[list_key]
        c = self.make_collection(n, path, inner, "nodes", container=v)
        n.collections.append(c)
        types = "/".join(_types_of(v))
        named = f' "{v["name"]}"' if v.get("name") else ""
        first = _types_of(inner[0])[0] if _types_of(inner[0]) else "item"
        n.props.append({"k": path, "collection": c.key, "raw": v,
                        "v": f"{types}{named} · {len(inner)} × {first}"})
        for item in inner:
            if isinstance(item, dict):
                self.collect_refs(n, c.key, item, f"{path}.{list_key}")
        for kk, vv in v.items():
            if kk != list_key and kk != "@type" and not isinstance(vv, (dict, list)):
                n.props.append({"k": f"{path}.{kk}", "v": str(vv), "raw": vv})
        return True

    def collect_refs(self, n: Node, from_key: str, obj: dict, path: str) -> None:
        for k, v in obj.items():
            if _is_ref_only(v):
                self.refs.append({"from_node": n.key, "from_key": from_key,
                                  "prop": f"{path}.{k}", "to": v["@id"]})
            elif isinstance(v, dict):
                self.collect_refs(n, from_key, v, f"{path}.{k}")

    def make_collection(self, n: Node, prop: str, items: list, kind: str,
                        container: Any = None) -> Collection:
        c = Collection(key=f"{n.key}#{prop}", node_key=n.key, prop=prop,
                       count=len(items), item_kind=kind, item_type="item",
                       items=[], container=container)
        self.cols[c.key] = c
        rows = []
        for i, item in enumerate(items):
            detail = ""
            if kind == "strings":
                label = str(item)
            elif _is_ref_only(item):
                label, detail = "{ @id }", short_id(item["@id"], self.host)
            else:
                inner = item
                if isinstance(item, dict) and isinstance(item.get("itemOffered"), dict):
                    inner = item["itemOffered"]     # an Offer is labelled by what it offers
                label = (inner.get("name") if isinstance(inner, dict) else None) \
                    or "/".join(_types_of(inner)) or "(item)"
                if (isinstance(item, dict) and item.get("position")
                        and isinstance(inner, dict) and inner.get("name")):
                    label = f"{item['position']}. {inner['name']}"
                detail = _item_detail(item, inner)
            rows.append({"i": i, "label": label, "detail": detail,
                         "marks": mark_item(item), "raw": item})
        c.items = rows
        head = items[0] if items else {}
        head_inner = head
        if isinstance(head, dict) and isinstance(head.get("itemOffered"), dict):
            head_inner = head["itemOffered"]
        c.item_type = ("value" if kind == "strings" else "@id" if kind == "refs"
                       else (_types_of(head_inner)[0] if _types_of(head_inner) else "item"))
        c.problems = len([r for r in rows if r["marks"]])
        return c

    # -- §7a ------------------------------------------------------------
    def mark_rows(self, n: Node) -> None:
        """Every property row's mark, from the JSON alone. These fire without
        a check having run, because they are readings of the markup rather
        than judgements about it - and a reader looking at a value wants the
        problem beside the value, not in a row they have to go and find."""
        raw = n.raw if isinstance(n.raw, dict) else {}
        logo = raw.get("logo")
        if isinstance(logo, dict):
            logo = logo.get("@id") or logo.get("url")
        for p in n.props:
            if p.get("mark"):
                continue
            ref = p.get("ref")
            if ref:
                d = self.defined.get(ref)
                if d is None:
                    p.update({"mark": "bad", "link": "dangling:" + ref,
                              "note": "not defined anywhere on the page"})
                elif d[0] is n:
                    p.update({"mark": "ok",
                              "note": "self" if d[2]
                              else "nested definition in this node"})
                else:
                    p.update({"mark": "ok", "link": d[0].key,
                              "note": "→ " + (d[0].sid or d[0].type)})
                continue
            value = p.get("raw")
            if (re.search(r"(^|\.)inLanguage$", p["k"]) and self.locale
                    and value != self.locale):
                p.update({"mark": "bad",
                          "note": f"site is {self.host} → {self.locale}"})
                continue
            if isinstance(value, str) and _PLACEHOLDER.match(value):
                p.update({"mark": "bad", "note": "template placeholder"})
                continue
            if isinstance(value, str) and "Â" in value:
                p.update({"mark": "miss", "note": "encoding defect"})
                continue
            if value == "":
                p.update({"mark": "miss", "note": "empty"})
                continue
            if (re.match(r"^image(\.@id)?$", p["k"]) and logo
                    and (value == logo
                         or (isinstance(value, dict) and value.get("@id") == logo))):
                p.update({"mark": "miss", "note": "same file as logo"})
                continue
            if p["k"] == "areaServed" and isinstance(value, str):
                p.update({"mark": "miss", "note": "a string, not a Country"})
        if n.role == "entity":
            for k in RECOMMENDED_ON_ENTITY:
                if k not in raw:
                    n.props.append({"k": k, "v": "(absent)", "mark": "miss",
                                    "note": "missing", "missing": True, "raw": None})
        if not n.id:
            n.props.insert(0, {"k": "@id", "v": "(absent)", "mark": "bad",
                               "missing": True, "raw": None,
                               "note": "no @id: nothing can reference this node"})


def _item_detail(item: Any, inner: Any) -> str:
    """One line of what an item is, so a list of fifteen reads as fifteen
    different things rather than fifteen of the same word."""
    if not isinstance(inner, dict):
        return ""
    bits: list[str] = []
    if inner.get("url"):
        bits.append(re.sub(r"^https?://[^/]+", "", str(inner["url"])))
    rating = inner.get("reviewRating")
    if isinstance(rating, dict):
        bits.append(f"{rating.get('ratingValue')} / {rating.get('bestRating')}")
    author = inner.get("author")
    if isinstance(author, dict) and author.get("name"):
        bits.append(f'author "{author["name"]}"')
    if inner.get("datePublished"):
        bits.append(str(inner["datePublished"]))
    answer = inner.get("acceptedAnswer")
    if isinstance(answer, dict) and answer.get("text"):
        bits.append(f"answer · {len(str(answer['text']).split())} words")
    if isinstance(inner.get("dayOfWeek"), list):
        bits.append(f"{len(inner['dayOfWeek'])} days · "
                    f"{inner.get('opens')}–{inner.get('closes')}")
    for prop, said in (("provider", "provider → self"),
                       ("itemReviewed", "itemReviewed → self")):
        if isinstance(inner.get(prop), dict) and inner[prop].get("@id"):
            bits.append(said)
    target = inner.get("target")
    if isinstance(target, dict) and target.get("urlTemplate"):
        bits.append(re.sub(r"^https?://[^/]+", "", str(target["urlTemplate"])))
    return " · ".join(bits)


def mark_item(item: Any) -> list[dict]:
    """RENDER_RULES §7b, the per-item marks.

    `no location page` is a check output rather than a JSON fact - it needs
    the site's page list - and is drawn only because the Coverage hand-off
    produced it. It is grey for that reason: held, not failing.
    """
    marks: list[dict] = []
    text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
    if "Â" in text:
        marks.append({"mark": "miss", "note": "encoding defect"})
    inner = None
    if isinstance(item, dict):
        inner = (item["itemOffered"] if isinstance(item.get("itemOffered"), dict)
                 else item)
    if inner is not None:
        types = _types_of(inner)
        if "Service" in types and not inner.get("url"):
            marks.append({"mark": "miss", "note": "no url"})
        author = inner.get("author")
        if (isinstance(author, dict)
                and _VERIFIED_REVIEW.search(str(author.get("name") or ""))):
            marks.append({"mark": "bad", "note": "author is not a person"})
        if "City" in types:
            marks.append({"mark": "held", "note": "no location page"})
    if isinstance(item, str) and _PLACEHOLDER.match(item):
        marks.append({"mark": "bad", "note": "placeholder"})
    if isinstance(item, dict) and any(
            isinstance(x, str) and _PLACEHOLDER.match(x) for x in item.values()):
        marks.append({"mark": "bad", "note": "placeholder value"})
    return marks


def resolve_anchor(b: _Builder, anchor: str) -> str | None:
    """§7's anchor forms. An anchor that resolves to nothing is dropped,
    never invented.

    The one construction here is the promotion in the last branch: a finding
    that pins to a nested object rather than a list (Acme's `address`,
    Summit's `aggregateRating`) makes that object a collection of one, so
    it gets a chip and can be drilled. Without it the finding would have
    nowhere on the picture to land and would silently disappear.
    """
    if anchor in b.by_key:
        return anchor
    if anchor.startswith("expected:"):
        wanted = anchor[len("expected:"):]
        g = next((g for g in b.ghosts
                  if g.kind == "ghost-expected" and wanted in g.covers), None)
        return g.key if g else None
    if anchor.startswith("block:"):
        return next((x.key for x in b.blocks if x.key == anchor), None)
    if anchor in b.cols:
        return anchor
    i = anchor.rfind("#")
    if i <= 0:
        return None
    node_key, prop = anchor[:i], anchor[i + 1:]
    n = b.by_key.get(node_key)
    if n is None:
        return None
    c = next((c for c in n.collections if c.prop == prop), None)
    if c is None:
        row = next((p for p in n.props if p["k"] == prop), None)
        if row is None:
            return None
        if row.get("nested") is not None:
            c = b.make_collection(n, prop, [row["nested"]], "nodes")
        else:
            c = b.make_collection(n, prop, [row.get("raw")], "strings")
        n.collections.append(c)
    return c.key


def build_model(blocks: list[dict], page_type_map: dict[str, list[str]] | None,
                crawl_context: dict | None, findings: list[dict] | None,
                eligibility: list[dict] | None = None) -> GraphModel:
    """RENDER_RULES §1-§7 over one page's raw JSON-LD.

    `blocks` is the ordered list of `<script type="application/ld+json">`
    blocks, each `{"source": "plugin:yoast", "json": <parsed>}`.

    `crawl_context` carries what the JSON cannot say: `page`, `page_type`,
    `host`, `footer_profile_links`.

    `findings` are the part's rows already shaped for the picture: `n`,
    `sev`, `name`, `checks`, `src`, `anchors`.

    `eligibility` is a check output and is passed straight through, with the
    fourth verdict `none targeted` for a page that targets no rich result.
    """
    ctx = crawl_context or {}
    host = str(ctx.get("host") or "").removeprefix("www.")
    # `en-AU` for a `.au` host, and nothing at all otherwise. A guessed
    # locale would make `inLanguage` fire on every site in the world.
    locale = "en-AU" if host.endswith(".au") else None
    page_type = str(ctx.get("page_type") or "home")
    expects = dict(EXPECTED_TYPES if page_type_map is None else page_type_map)

    b = _Builder(host, locale)

    # §1 blocks and top-level nodes
    for bi, raw_block in enumerate(blocks or []):
        data = raw_block.get("json")
        block = Block(i=bi + 1, key=f"block:{bi + 1}",
                      source=str(raw_block.get("source") or "inline"), raw=data)
        b.blocks.append(block)
        nodes = (data["@graph"] if isinstance(data, dict)
                 and isinstance(data.get("@graph"), list) else [data])
        for ni, raw in enumerate(nodes):
            if not isinstance(raw, dict):
                continue
            node_id = raw.get("@id")
            n = Node(kind="node", key=node_id or f"b{bi + 1}n{ni}",
                     id=node_id,
                     sid=short_id(node_id, host) if node_id else None,
                     types=_types_of(raw), block=block.i, raw=raw,
                     name=raw.get("name"))
            block.node_keys.append(n.key)
            b.nodes.append(n)
            b.by_key[n.key] = n

    # §2 defined identifiers: any object anywhere with both `@id` and
    # `@type`, nested ones included - Voltaic's logo is defined inside the
    # Organization, and a reference to it resolves.
    def walk_defs(v: Any, owner: Node) -> None:
        if isinstance(v, list):
            for x in v:
                walk_defs(x, owner)
        elif isinstance(v, dict):
            if v.get("@id") and v.get("@type"):
                b.defined.setdefault(v["@id"], (owner, v, owner.raw is v))
            for x in v.values():
                walk_defs(x, owner)

    for n in list(b.nodes):
        walk_defs(n.raw, n)

    # §3 roles. The first qualifying node is the entity; a later one is
    # flagged rather than made a second entity, because two entities is a
    # finding and not a shape.
    for n in list(b.nodes):
        if any(is_entity_type(t) for t in n.types):
            if b.entity is None:
                b.entity = n
                n.role = "entity"
            else:
                n.flags.append("second entity node")
        elif any(t in SITE_TYPES for t in n.types):
            n.role = "site"

    # §4 properties, references, collections, inline copies. After §3
    # because an inline copy is recognised by its name matching the
    # entity's, so the entity has to be known first.
    for n in list(b.nodes):
        if isinstance(n.raw, dict):
            b.walk(n, n.raw, n.key, "")

    # §5 resolve every reference into an edge or a dangling ghost
    for r in b.refs:
        d = b.defined.get(r["to"])
        r["resolved"] = d is not None
        src = b.by_key[r["from_node"]]
        if d is not None:
            owner, _, top = d
            r["target_key"] = owner.key
            r["nested"] = not top
            if owner is src:
                r["self"] = True
                continue
            src.refs_out.append(r)
            owner.refs_in.append(r)
            b.add_edge(r["from_key"], owner.key, r["prop"], "ok")
        else:
            gk = "dangling:" + r["to"]
            g = b.by_key.get(gk)
            if g is None:
                g = Node(kind="ghost-dangling", key=gk, id=r["to"],
                         sid=short_id(r["to"], host),
                         types=[_TYPE_FROM_PROP.get(r["prop"], "Thing")],
                         role="entity" if r["prop"] in ENTITY_REF_PROPS else "other",
                         flags=["referenced · not defined"])
                b.ghosts.append(g)
                b.by_key[gk] = g
            g.refs_in.append(r)
            r["target_key"] = gk
            src.refs_out.append(r)
            b.add_edge(r["from_key"], gk, r["prop"], "dangling")

    # §6 islands. The earlier definition ("top-level nodes nothing points
    # at") calls Voltaic's WebPage an island and Summit's entity an island,
    # which are the two healthiest nodes in the pack. The rule is connection
    # in either direction to a *different* top-level node; self-references,
    # references into a node's own nested definitions, and edges to an
    # inline copy are not connections.
    def top_level(key: str) -> bool:
        t = b.by_key.get(b.owner_key(key))
        return t is not None and t.kind == "node"

    for n in b.nodes:
        if n.kind != "node":
            continue
        n.island = not any(
            e["kind"] == "ok"
            and (b.owner_key(e["from"]) == n.key or b.owner_key(e["to"]) == n.key)
            and b.owner_key(e["from"]) != b.owner_key(e["to"])
            and top_level(e["from"]) and top_level(e["to"])
            for e in b.edges)

    # §6 expected but absent. Only the page-type map's missing types and the
    # footer-places case: a finding about the entity's own type, or about
    # another page, is pinned to the entity and never drawn as a ghost, or
    # the ghost column starts saying things the map did not.
    present = {t for n in b.nodes for t in n.types}
    want = expects.get(page_type) or expects.get("home") or []
    missing = [t for t in want
               if (b.entity is None if t == "entity" else t not in present)]
    missing_types = [t for t in missing if t != "entity"]
    if missing_types:
        g = Node(kind="ghost-expected", key="expected:" + missing_types[0],
                 types=missing_types, role="site", covers=list(missing_types),
                 flags=["expected by the page-type map · absent"])
        if page_type == "home" and "BreadcrumbList" not in present:
            g.note = "BreadcrumbList exempt on the home page"
        b.ghosts.append(g)
        b.by_key[g.key] = g
        if b.entity is not None:
            label = " · ".join(
                {"WebPage": "about", "WebSite": "publisher"}.get(t, t)
                for t in missing_types)
            b.add_edge(g.key, b.entity.key, label, "expected")
    if "entity" in missing:
        g = Node(kind="ghost-expected", key="expected:entity",
                 types=["Organization", "LocalBusiness"], role="entity",
                 covers=["entity"], flags=["expected · absent"])
        b.ghosts.append(g)
        b.by_key[g.key] = g
    maps = [u for u in (ctx.get("footer_profile_links") or [])
            if _MAPS.search(str(u))]
    if maps and not any(isinstance(n.raw, dict) and n.raw.get("address")
                        for n in b.nodes):
        g = Node(kind="ghost-expected", key="expected:LocalBusiness",
                 types=["LocalBusiness"], role="entity",
                 covers=["LocalBusiness"], count=len(maps),
                 flags=[f"the footer links {len(maps)} Maps places · none declared"],
                 props=[{"k": "footer link", "v": u, "mark": "miss",
                         "note": "no node declares this place"} for u in maps])
        b.ghosts.append(g)
        b.by_key[g.key] = g
        if b.entity is not None:
            b.add_edge(g.key, b.entity.key,
                       f"parentOrganization ×{len(maps)}", "expected")

    # §7 findings: anchors, rings, badges
    shaped: list[dict] = []
    for raw_finding in (findings or []):
        f = dict(raw_finding)
        f["sev_class"] = SEV_CLASS.get(f.get("sev", "Info"), "info")
        keys = [k for k in (resolve_anchor(b, a) for a in (f.get("anchors") or []))
                if k]
        f["anchor_keys"] = keys
        for k in keys:
            target = (b.by_key.get(k) or b.cols.get(k)
                      or next((x for x in b.blocks if x.key == k), None))
            if target is not None:
                target.findings.append(f)
        shaped.append(f)
    for target in [*b.nodes, *b.ghosts, *b.cols.values(), *b.blocks]:
        target.findings.sort(
            key=lambda f: (SEV_ORDER.get(f.get("sev"), 9), f.get("n") or 0))
        target.state = (SEV_CLASS.get(target.findings[0].get("sev"), "info")
                        if target.findings else "clean")
    # An inline copy is red with nothing pinned to it: the copy itself is
    # the defect, whether or not a check has been written that says so.
    for n in b.nodes:
        if n.kind == "inline-copy" and n.state == "clean":
            n.state = "high"
    for n in b.nodes:
        n.collections.sort(key=lambda c: (
            SEV_ORDER.get(c.findings[0].get("sev"), 9) if c.findings else 9,
            -c.count))

    # §6 verdicts, in this order. The reason names the condition that decided
    # it, because a verdict a reader cannot check is one they have to take on
    # trust.
    dangling = len([r for r in b.refs if not r["resolved"]])
    copies = len([n for n in b.nodes if n.kind == "inline-copy"])
    pointed_at = bool(b.entity is not None and any(
        b.by_key[r["from_node"]].role == "site" for r in b.entity.refs_in))
    if b.entity is None:
        verdict, why = "UNIDENTIFIED", "no entity node on the page"
    elif not b.entity.id:
        verdict = "UNIDENTIFIED"
        why = ("the entity has no @id, so nothing can reference it"
               + (f"; described {copies + 1} times" if copies else ""))
    elif copies:
        verdict = "UNIDENTIFIED"
        why = f"the entity is described {copies + 1} times"
    elif dangling:
        verdict = "FRAGMENTED"
        why = (f"{dangling} reference{'s' if dangling > 1 else ''} resolve to nothing"
               + ("" if pointed_at else "; nothing points back at the entity"))
    elif not pointed_at:
        verdict = "FRAGMENTED"
        why = "nothing points at the entity (no WebPage.about / WebSite.publisher)"
    else:
        verdict = "CONSOLIDATED"
        why = (f"one @id ({b.entity.sid}) · every reference lands · "
               f"referenced by {', '.join(r['prop'] for r in b.entity.refs_in)}")

    tops = [n for n in b.nodes if n.kind == "node"]
    return GraphModel(
        host=host, locale=locale, page=str(ctx.get("page") or ""),
        page_type=page_type, blocks=b.blocks, nodes=b.nodes, ghosts=b.ghosts,
        edges=b.edges, collections=b.cols, refs=b.refs,
        verdict={"entity": verdict, "why": why, "dangling": dangling,
                 "islands": len([n for n in tops if n.island]),
                 "blocks": len(b.blocks), "nodes": len(tops), "copies": copies},
        counts={"open": len([f for f in shaped
                             if f.get("sev") in ("High", "Medium", "Low")]),
                "held": len([f for f in shaped if f.get("sev") == "Held"]),
                "info": len([f for f in shaped if f.get("sev") == "Info"])},
        findings=sorted(shaped, key=lambda f: (SEV_ORDER.get(f.get("sev"), 9),
                                               f.get("n") or 0)),
        eligibility=list(eligibility or []),
        entity_key=b.entity.key if b.entity else None)
