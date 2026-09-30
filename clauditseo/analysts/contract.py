"""The output contract a brief conforms to (brief v10 step AF).

A conforming brief - one whose prompt header lists the `checks` it may
emit - answers with two blocks: first a fenced JSON block the engine
parses as findings, then the prose a person reads. This module is the
parser. It is strict where the record's integrity needs it: a row whose
`check` is not in the header's list, or whose `page` is not in the run's
page set, is dropped with a logged reason and never kept quietly; a
brief that answered with a question and no block is `needs-input`, not
`read`. Built against `title-desc` (`SPEC_title_description_unit.md` §4a)
and written so every later prompt only has to conform.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

log = logging.getLogger("clauditseo.contract")

#: The first fenced JSON block in the output. `nothing before it` is the
#: prompt's rule; the parser takes the first one wherever it is, since a
#: model that prefixed a sentence has still answered.
FENCE = re.compile(r"```json[ \t]*\r?\n(.*?)```", re.S)

STATUSES = ("FAIL", "WARN", "PASS-OVERRIDE")
SEVERITIES = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

READ = "read"
NEEDS_INPUT = "needs-input"


@dataclass
class Row:
    check: str            # `ONP/title-length` - the header's id, verbatim
    dimension: str        # `ONP`
    check_id: str         # `title-length` - the sweep's own id
    page: str             # the url as the page set spells it
    status: str
    severity: str         # lower-case, the record's vocabulary
    evidence: str
    replacement: str | None
    note: str
    #: The shared string, on a duplicate row (brief v11 step AH).
    group: str | None = None
    #: True where the brief raised the severity above the registered
    #: default with a reason; the engine never lets it lower one.
    raised: bool = False
    #: The image the row is about, where the part has one (brief v15 step
    #: AQ): the src as the inventory spells it. A row's identity is
    #: (check, page, image), so two images on one page are two rows.
    image: str | None = None
    #: The other checks this row's replacement closes. One markup change
    #: can answer six checks on one image, and repeating the markup six
    #: times would read as six changes.
    also_resolves: list[str] = field(default_factory=list)
    #: What one change moves: `image`, `template` or `pipeline`, and the
    #: name of the template or pipeline it moves.
    kind: str | None = None
    #: The structured-data block the row is about (brief v16 step AS), as
    #: the inventory numbers it. The counterpart of `image` on the Images
    #: part: a row's identity is (check, page, block), so two blocks on one
    #: page are two rows and a page with one bad block is one.
    block: str | None = None
    #: Where the change goes, in the operator's words rather than the
    #: engine's - "the theme's header.php", "Rank Math > Titles & Meta".
    #: Prose, because the answer differs per platform and a field with a
    #: fixed vocabulary would be wrong on most of them.
    where: str | None = None
    #: What a brief said about the work a row implies (brief v17 step
    #: AX): demand, business value, difficulty, effort, horizon. Triage
    #: scores on these where they are given and does not re-estimate, so
    #: they must survive the store - `extra` keeps scalars only, which is
    #: what stops a model inventing a nested shape the record has no room
    #: for, and this is the one nested shape the record has room for.
    fields: dict = field(default_factory=dict)
    #: The part's own fields on the row (`page_type` ...), kept as given.
    extra: dict = field(default_factory=dict)
    #: Which entry of the block's `fixes[]` this row is served by (brief v20,
    #: items 147 and 148). A fix can serve rows on several templates, and a
    #: row can be served by one fix, so the link is stored on the row and the
    #: fix is stored once. Repeating the fix per row is how one change came to
    #: read as six on the Images part.
    fix_id: str | None = None
    #: The checks THIS row sets aside, by full id (brief v20, items 147 E3 and
    #: 148 G4). A LIST, on the SURVIVING row.
    #:
    #: **That direction was got wrong first, and real output is what showed
    #: it.** It was written as a because-clause on a suppressed row pointing up
    #: at its owner. Both installed prompts say the opposite in terms -- "a
    #: check set aside emits no row of its own. It is named in `suppressed` on
    #: the row that survives" -- and their schemas give it as
    #: `"suppressed": ["INT/hreflang-reciprocity"]`. So a set-aside check has
    #: no row to hang a clause on; the row that stands carries the list.
    #:
    #: The first International run on Acme (19eeb42e, 2026-09-13) wrote
    #: `"suppressed": []` on every row, correctly. The reader ran `str()` on it,
    #: got the truthy string `'[]'`, and every card would have rendered
    #: "Set aside: []". Hand-built test JSON with a string value never showed it.
    #:
    #: Brief 160 step 5's intent survives the correction: a reader looking for
    #: the set-aside check finds it named on the row that answers for it, which
    #: is "the answer is here" -- not "run deeper", so still not `not_assessed`.
    suppressed: list[str] = field(default_factory=list)
    #: How sure the brief is, where it says. Every International row carries
    #: one (nothing on that part is a measurement) and Mobile's three analysis
    #: rows do. Absent on a row the sweep measured: a measurement's confidence
    #: is not the model's to state.
    confidence: str | None = None
    #: The Security brief's change per layer (brief v20 step BD): a list of
    #: `{layer, stack, block}` - the same header set at the edge and at the
    #: origin are two blocks, and the fix card copies each. A list of objects,
    #: which `extra` (scalars only) would have dropped.
    config: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Parsed:
    #: `read` where a block was found, `needs-input` where the brief asked
    #: instead of answering; `read` with no rows where it answered with an
    #: empty block.
    status: str
    rows: list[Row] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    not_assessable: list[dict] = field(default_factory=list)
    #: The output with the machine block removed - what a person reads.
    body: str = ""
    #: True where a block was found at all.
    block: bool = False
    #: The part the block named for itself, where it did.
    part: str | None = None
    #: The two verdicts the Structured data brief returns beside its rows
    #: (brief v16 step AS), because neither is a finding about a page.
    #:
    #: `eligibility` is one entry per (page, rich result) with a verdict
    #: and a reason - a page can be ineligible for a result with nothing
    #: wrong with its markup, and a row would have to invent a defect to
    #: say so. `entity` is the site's own shape: CONSOLIDATED or
    #: FRAGMENTED, with the reason. Both are stored with the run and
    #: rendered above the fixes rather than among them.
    eligibility: list[dict] = field(default_factory=list)
    entity: dict | None = None
    #: The hub map the Links brief returns beside its rows (brief v17 step
    #: AW), for the same reason those two are beside rather than among
    #: them: a hub's shape - its spokes, how many link up, how many it
    #: links down to - is a fact about a group of pages, and no row about
    #: one page can carry it. The UI draws it; the readable block does not
    #: repeat it.
    hubs: list[dict] = field(default_factory=list)
    #: The three remaining block fields, each a fact about a group of
    #: pages rather than about one (brief v17 step AX). `map` is
    #: Coverage's topical map, which the whole-site view draws and the
    #: generator places a new page on; `clusters` is Cannibalisation's
    #: grouping with its survivor; `ranking` is Triage's order, which the
    #: step-3 pane reads and the next Triage run is shown as its prior.
    #: None of the three could be carried by a row: a row is about a page,
    #: and a cluster is about which of four pages wins.
    #: What a `kind: generator` brief wrote, instead of rows (brief v17
    #: step AX): the page it is a brief for, and the id of the stored
    #: document. A generator has no findings and its empty `rows` must
    #: never be read as "nothing is wrong with this page" - `generator`
    #: being set is what says which kind of answer this is.
    generator: dict | None = None
    map: list[dict] = field(default_factory=list)
    clusters: list[dict] = field(default_factory=list)
    ranking: list[dict] = field(default_factory=list)
    #: The rule a ranking's scores are the sum of, verbatim from the brief
    #: (brief v17 step AX). Carried because a score without the rule that
    #: produced it is a number an operator has to take on trust, and this
    #: is the pane where they decide what to buy.
    model: dict = field(default_factory=dict)
    #: The strategy the block says it applied (brief v11 step AI).
    strategy: str | None = None
    #: The block's own declared schema version, verbatim -- `mobile/2`,
    #: `intl/2` (brief v20). Stored so a reader can tell which shape it is
    #: looking at: a brief bumped to a schema the reader has not been taught
    #: would otherwise store its new keys and silently render none of them,
    #: which is what happened to every one of these fields before this.
    schema: str | None = None
    #: One entry per template, with its verdict (item 147 E1). A template is a
    #: group of pages and no row about one page can carry its verdict, which is
    #: the same reason `hubs` and `clusters` are beside rows rather than among
    #: them.
    templates: list[dict] = field(default_factory=list)
    #: The locales observed and stated, their basis, and the conflict where
    #: they differ (item 148 G1). AN OBJECT, not a list -- the installed
    #: schema is `{"observed": [...], "stated": [...], "basis": "...",
    #: "conflict": "..."}`. It was declared a list first, and the reader
    #: iterated the object's keys, found no dicts among them, and stored
    #: nothing: the first Acme run's `locales` was silently dropped.
    locales: dict | None = None
    #: The fixes themselves, once each, sorted by the pages they affect, each
    #: naming what it serves (items 147 E2, 148 G3). Rows point at these by
    #: `fix_id`. **A low-confidence fix is a different card, not a dimmed
    #: one** -- 147 E2 -- so the confidence travels with the fix and not only
    #: with the row.
    fixes: list[dict] = field(default_factory=list)
    #: The Security brief's "now" (item 143, brief v20 step BD): the compromise
    #: verdict with its basis, the evidence ledger per domain A-I, the transport
    #: summary, and the header, cookie and script inventories, plus the
    #: controls declined for this site. Facts about the site rather than about a
    #: page, so beside the rows like `templates` and `locales`.
    compromise: dict | None = None
    ledger: list[dict] = field(default_factory=list)
    transport: dict | None = None
    headers: list[dict] = field(default_factory=list)
    cookies: list[dict] = field(default_factory=list)
    scripts: list[dict] = field(default_factory=list)
    do_not_spend_on: list[dict] = field(default_factory=list)
    #: The AI surface brief's block beside its rows (item 145, brief v22 BH):
    #: the "now", read-through entries, absences, conflicts, declines and the
    #: count of `[client to supply]` markers. None for every other brief.
    ai_surface: dict | None = None

    def as_dict(self) -> dict:
        return {"status": self.status, "part": self.part, "strategy": self.strategy,
                # Brief v20's four block keys (items 147, 148). Serialised here
                # for the reason the comment below already gives about
                # `eligibility`: this dict is what is stored and what the UI
                # reads, so a field the parser fills and `as_dict` drops is a
                # field that exists only in memory. Every one of these was
                # exactly that until now -- the briefs emitted them and nothing
                # kept them.
                "schema": self.schema, "templates": self.templates,
                "locales": self.locales, "fixes": self.fixes,
                # Brief v20 step BD, stored for the reason above.
                "compromise": self.compromise, "ledger": self.ledger,
                "transport": self.transport, "headers": self.headers,
                "cookies": self.cookies, "scripts": self.scripts,
                "do_not_spend_on": self.do_not_spend_on,
                "ai_surface": self.ai_surface,
                "rows": [r.as_dict() for r in self.rows],
                "dropped": self.dropped, "questions": self.questions,
                "assumptions": self.assumptions,
                "not_assessable": self.not_assessable, "block": self.block,
                # The two verdicts that are not findings (brief v16 step
                # AS). Serialised here or they reach nothing: this dict is
                # what is stored with the run and what the UI reads, and a
                # field the parser fills but `as_dict` drops is a field
                # that exists only in memory.
                "eligibility": self.eligibility, "entity": self.entity,
                "hubs": self.hubs, "map": self.map,
                "clusters": self.clusters, "ranking": self.ranking,
                "model": self.model, "generator": self.generator}


@dataclass
class Rules:
    """What the part's rules need from the registry and the site record
    to judge a replacement (brief v12 step AL): the bounds a title or a
    description must fall within, the strategy in force, and the inputs an
    alignment row cannot be graded without."""
    title_bounds: tuple[int, int] = (30, 60)
    #: The title ceiling under `neighbourhood` on location and service
    #: pages - the prompt's soft ceiling; "other" pages keep `title_bounds`.
    neighbourhood_ceiling: int = 240
    desc_bounds: tuple[int, int] = (120, 160)
    strategy: str = "triple"
    gbp_primary_category: str | None = None
    #: Path -> location entity, from the site record's location pages.
    location_entities: dict[str, str] = field(default_factory=dict)
    #: The hosts the run's markup loaded resources from, plus the site's own
    #: (item 143 step BD). None where the evidence predates the inventory, and
    #: the CSP origin rule then cannot be judged and is not applied.
    resource_origins: set[str] | None = None
    site_host: str = ""
    #: Item 216: the URLs brief's rename rules, from the crawl rather than
    #: from what the model said about it. Path -> distinct pages linking to
    #: it, the cap in force, and every path the crawl fetched. None where no
    #: evidence was given; the rules needing them are then not applied.
    inlinks: dict[str, int] | None = None
    rename_cap: int | None = None
    live_paths: set[str] | None = None
    #: Item 221: what the sweep of the run raised - bare check id -> the paths
    #: it named - and the dimensions it measured. None where the caller gave
    #: no run; the sweep-owned rule is then not applied.
    sweep_raised: dict[str, set[str]] | None = None
    sweep_measured: set[str] | None = None


#: Item 221. Parts whose brief may not raise or hold one of its FREE checks
#: on its own account. Every free URL check is a string function of a URL the
#: sweep already read, so a model row the sweep did not raise is a false
#: positive ("4 pages exceed depth-3" where the sweep counted 11; two
#: `url-length` rows on paths under the bound), and a hold on one is a hold
#: on a check that ran ("not assessable · needs no parameter variants
#: reached" over a measured zero). The brief's analysis checks are untouched.
#: Other parts' briefs do legitimately file free-check rows the sweep cannot
#: pin to one page (Speed's per-template rows), so this is a list, not a rule.
SWEEP_OWNED_PARTS = frozenset({"urls"})


def _sweep_owns(parsed: "Parsed", rules: Rules, check: str) -> bool:
    """Whether `check` (a full id) is a free check the run's sweep measured,
    on a part whose brief may only read it."""
    if rules.sweep_raised is None or (parsed.part or "") not in SWEEP_OWNED_PARTS:
        return False
    dimension = check.split("/")[0] if "/" in check else ""
    if not dimension or dimension not in (rules.sweep_measured or set()):
        return False
    from clauditseo.checks import check_cost
    return check_cost(check) == "free"


#: "entity-unresolvable also fires", "`title-duplicate` fired": a row's claim
#: that another check fired, which is what a raised severity may rest on.
_FIRE_CLAIM = re.compile(r"`?\b([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b`?\s+(?:also\s+|now\s+)?"
                         r"(?:fires|fired|is firing)\b")


def _unsupported_raise(row: "Row", rules: Rules) -> list[str]:
    """Item 234. The free checks a RAISED row says fired that this audit's
    sweep did not raise. On twenty22 `AIS/id-page-absent` was HIGH because
    "entity-unresolvable also fires" - the prompt's own condition for HIGH -
    on a page whose free table says entity-unresolvable was not assessed.
    A paid row may not assert what the free state contradicts."""
    if not row.raised or rules.sweep_raised is None:
        return []
    from clauditseo.checks import check_cost
    dimension = row.check.split("/")[0]
    if dimension not in (rules.sweep_measured or set()):
        return []
    claimed = {m.group(1) for m in _FIRE_CLAIM.finditer(f"{row.note or ''} {row.evidence or ''}")}
    return sorted(c for c in claimed
                  if c != row.check_id and check_cost(f"{dimension}/{c}") == "free"
                  and not rules.sweep_raised.get(c))


def _without_claims(text: str, checks: list[str]) -> str:
    """`text` with every clause that says one of `checks` fired taken out."""
    parts = re.split(r"(?<=[.;])\s+", text or "")
    kept = [p for p in parts
            if not any(m.group(1) in checks for m in _FIRE_CLAIM.finditer(p))]
    return " ".join(kept).strip()


def _registry_default(check: str, status: str) -> str | None:
    from clauditseo.checks import default_severities
    default = default_severities().get(check)
    if isinstance(default, dict):
        default = default.get(status) or default.get("FAIL")
    return default


def _sweep_did_not_raise(parsed: "Parsed", row: "Row", rules: Rules) -> str | None:
    """The drop reason for a free-check row the sweep did not raise, or None."""
    if not _sweep_owns(parsed, rules, row.check):
        return None
    raised = (rules.sweep_raised or {}).get(row.check_id, set())
    if row.group:
        # A template row names no one page; it stands only beside a sweep
        # that raised the check somewhere.
        return None if raised else f"{row.check} is the automatic checks', and the automatic checks did not raise it"
    if _path(row.page) in raised:
        return None
    return f"{row.check} is the automatic checks', and the automatic checks did not raise it on {_path(row.page)}"


#: The one URL check that may propose changing a live URL (`prompts/urls.md`,
#: "url-rename is the only check that proposes changing a live URL").
RENAME_CHECK = "url-rename"
#: A replacement that writes a redirect: "301 /web-design1/ to /web-design/".
_REDIRECT = re.compile(r"\b30[18]\b")


def _rename_rules(row: "Row", rep: str, rules: Rules) -> str | None:
    """Item 216. The URLs brief states three rules and the parser trusted all
    of them to the model: only `url-rename` renames, a rename needs at most
    RENAME_INLINK_CAP inlinks, and the target is not invented. On twenty22 a
    `url-slug-not-descriptive` row carried "301 /web-design1/ to
    /web-design/; update 45 internal links" with a copy button, beside the
    `url-rename` row for the same page saying "inlinks 45 > cap 20 ... keep".

    Rewrites `row` in place and returns the reason, or None. A rewritten row
    is KEPT - the check's finding stands - with nothing to copy, and the
    reason on its note where the card shows it."""
    if row.dimension != "TEC" or not row.check_id.startswith("url-"):
        return None
    if row.check_id != RENAME_CHECK:
        if (row.kind or "").lower() == "rename" or _REDIRECT.search(rep):
            row.kind, row.replacement = "convention", None
            return "rename withheld: only url-rename may propose changing a live URL"
        return None
    if not rep or rep.lower().startswith("keep"):
        return None
    n = (rules.inlinks or {}).get(_path(row.page)) if rules.inlinks is not None else None
    if n is not None and rules.rename_cap is not None and n > rules.rename_cap:
        row.kind = "convention"
        row.replacement = (f"keep — not worth the risk: {n} inlinks, over the rename "
                           f"cap of {rules.rename_cap}")
        return f"rename refused: {n} inlinks over the cap of {rules.rename_cap}"
    return None


def _rename_target_is_live(row: "Row", rep: str, rules: Rules) -> str | None:
    """The target half of the rule, narrowed from the filing (item 216). A
    rename's target is a NEW path by definition - the prompt's own example
    renames /new-page-2 to a slug that does not exist yet - so "the crawl must
    know the target" would hold every honest rename. What can be refused is a
    target that is already a live page: a 301 onto it merges two pages."""
    if row.check_id != RENAME_CHECK or not rep or rep.lower().startswith("keep"):
        return None
    target = _path(rep.split()[0].rstrip(",;"))
    if rules.live_paths is not None and target in rules.live_paths and target != _path(row.page):
        return f"a rename target that is not already a live page ({target} is)"
    return None


TO_CONFIRM = "[TO CONFIRM"
#: A replacement that only points at another row (item 209).
_POINTER = re.compile(r"^\s*see\b", re.I)
ALIGNMENT = "title-entity-alignment"

#: Checks a brief may name only under `not_assessable` (brief v15 step AQ).
#: Imported here rather than read from the registry, because the parser is
#: the layer that refuses the row and must not depend on a module that
#: imports it back.
#: Empty since brief v16 step AS; see `onp.HELD_ONLY_NEEDS` for why the
#: mechanism outlived its first member.
HELD_ONLY: tuple[str, ...] = ()


def _needs_of(replacement: str) -> str:
    inner = replacement.strip()[len(TO_CONFIRM):].strip()
    inner = inner.lstrip(":").strip()
    return inner.rstrip("]").strip() or "confirmation"


#: The checks whose `replacement` IS a title, and the ones whose
#: replacement is a meta description. Named rather than matched on a
#: prefix, which is what these were.
#:
#: `check_id.startswith("title")` held until a different part had a check
#: beginning with the same word. `CNT/title-overlap` does - it is about
#: two pages competing for one subject, and its replacement is a
#: disposition sentence - so every one of its rows was measured against
#: the 60-character title bound and dropped. Six rows of a paid run, lost
#: to a name.
#:
#: A prefix is a guess about what a check is; this is the fact.
TITLE_REPLACEMENTS = frozenset({
    "title-missing", "title-length", "title-duplicate",
    "title-entity-alignment",
})
DESC_REPLACEMENTS = frozenset({
    "meta-desc-missing", "meta-desc-length", "meta-desc-duplicate",
})


def _is_title(check_id: str) -> bool:
    return check_id in TITLE_REPLACEMENTS


def _is_desc(check_id: str) -> bool:
    return check_id in DESC_REPLACEMENTS


def enforce(parsed: "Parsed", rules: Rules) -> "Parsed":
    """The v11 AH rules the parser was given, enforced on the rows it kept
    (brief v12 step AL). In this order: a replacement that begins
    `[TO CONFIRM` is not a replacement - the row moves to `not_assessable`
    with `needs` the bracket's text; an alignment row without the inputs
    alignment is graded against (the GBP primary category; the location
    entity on a location page) is `not_assessable` naming the input,
    whatever the brief wrote; a replacement outside the part's bounds is
    dropped with the measurement; and under `triple` a title using `|`
    where the rule says `-` is dropped. Nothing here is stored as a
    replacement, so nothing here gets a copy button."""
    strategy = (parsed.strategy or rules.strategy or "triple").strip().lower()
    have = {(n.get("check"), _path(str(n.get("page") or ""))) for n in parsed.not_assessable}

    def not_assessable(row: Row, needs: str) -> None:
        key = (row.check, _path(row.page))
        if key not in have:
            have.add(key)
            parsed.not_assessable.append({"check": row.check, "page": _path(row.page), "needs": needs})

    # Item 221: a hold on a free check the sweep measured is a hold on a check
    # that ran. Counted as dropped, so the accounting still sums (item 209).
    held: list[dict] = []
    for n in parsed.not_assessable:
        if isinstance(n, dict) and _sweep_owns(parsed, rules, str(n.get("check") or "")):
            parsed.dropped.append({"row": n, "reason": "a hold on a free check the automatic checks measured"})
        else:
            held.append(n)
    parsed.not_assessable = held
    have = {(n.get("check"), _path(str(n.get("page") or ""))) for n in parsed.not_assessable}

    kept: list[Row] = []
    for row in parsed.rows:
        unsupported = _unsupported_raise(row, rules)
        if unsupported:
            default = _registry_default(row.check, row.status)
            if default:
                row.severity = default
            row.raised = False
            row.evidence = _without_claims(row.evidence, unsupported)
            row.note = "; ".join(filter(None, [
                _without_claims(row.note, unsupported),
                f"raise refused: {', '.join(unsupported)} did not fire in this audit"]))
        rep = (row.replacement or "").strip()
        owned = _sweep_did_not_raise(parsed, row, rules)
        if owned:
            _drop(parsed, row.as_dict(), owned)
            continue
        if rep.upper().startswith(TO_CONFIRM):
            not_assessable(row, _needs_of(rep))
            continue
        if _POINTER.match(rep):
            # Item 209: "see /<slug>/ article-like template row" is not a
            # change, it is a pointer at another row - on Speed, at one the
            # contract had dropped - and it was offered with `copy change`.
            not_assessable(row, "the row it refers to")
            continue
        target = _rename_target_is_live(row, rep, rules)
        if target:
            not_assessable(row, target)
            continue
        withheld = _rename_rules(row, rep, rules)
        if withheld:
            log.warning("contract row rewritten: %s :: %s %s", withheld, row.check, row.page)
            row.note = "; ".join(filter(None, [row.note, withheld]))
            kept.append(row)
            continue
        if row.check_id == ALIGNMENT:
            if not (rules.gbp_primary_category or "").strip():
                not_assessable(row, "GBP primary category")
                continue
            page_type = str(row.extra.get("page_type") or "").lower()
            if page_type == "location" and not rules.location_entities.get(_path(row.page)):
                not_assessable(row, f"location entity for {_path(row.page)}")
                continue
        if rep and rep.lower() != "keep":
            bounds = None
            if _is_title(row.check_id):
                lo, hi = rules.title_bounds
                page_type = str(row.extra.get("page_type") or "").lower()
                if strategy == "neighbourhood" and page_type in ("location", "service"):
                    hi = rules.neighbourhood_ceiling
                bounds = (lo, hi)
            elif _is_desc(row.check_id):
                bounds = rules.desc_bounds
            if bounds:
                n = len(rep)
                lo, hi = bounds
                if n < lo or n > hi:
                    _drop(parsed, row.as_dict(),
                          f"replacement outside bounds ({n} < {lo})" if n < lo
                          else f"replacement outside bounds ({n} > {hi})")
                    continue
            if _is_title(row.check_id) and strategy == "triple" and "|" in rep:
                _drop(parsed, row.as_dict(),
                      "replacement uses \"|\" where the triple strategy says \"-\"")
                continue
        kept.append(row)
    parsed.rows = kept
    # A re-parse runs `enforce` without `parse`, so the holds are cleaned here
    # too (item 211); it is idempotent.
    return clean_holds(parsed)


#: Item 211. A `needs` that is a prompt's input variable - `LOCATION_PAGES`,
#: `SUB_SERVICES`, `AUTHORS` - printed on the card as the reason.
#: Joined by `_` or by spaces ("LOCATION PAGES" is on a stored contract), or
#: one all-capital word of four letters or more. Not "GBP": an acronym in a
#: sentence is a word, and "GBP primary category" is already a sentence.
_INPUT_NAME = re.compile(r"^[A-Z][A-Z0-9]*(?:[_ ][A-Z0-9]+)+$|^[A-Z]{4,}$")
#: A "hold" whose reason says the check found nothing: a pass, filed where
#: the brief puts what it could not assess ("no conflicting forms observed;
#: nothing further to assess"). It read as a hold on Indexability and URLs.
#: And what makes a pass-shaped reason a hold after all (the channel,
#: 20260924-0220-211): "PLATFORM not set; nothing further to assess" says
#: nothing further can be assessed BECAUSE an input is missing. A reason is a
#: pass only when it states an observed absence and names no missing input.
_NAMES_INPUT = re.compile(r"not set|not given|not provided|not supplied|missing|unknown|"
                          r"without|required|\bneeds?\b|\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|\b[A-Z]{4,}\b")
_PASS_REASON = re.compile(r"nothing (?:further )?to assess|no (?:conflicting \w+|conflicts?|issues?|problems?) "
                          r"(?:were )?(?:observed|found)|none observed", re.I)


def _input_words(name: str) -> str:
    """An input variable said as words: `SUB_SERVICES` is "sub-services",
    `LOCATION_PAGES` is "location pages". There is no register of these to
    read from yet (item 166); this is the words the name already holds."""
    words = " ".join(name.lower().replace("_", " ").split())
    return words.replace("sub ", "sub-", 1) if words.startswith("sub ") else words


def clean_holds(parsed: "Parsed") -> "Parsed":
    """What a brief could not assess, made readable before anything draws it
    (item 211). A hold with no check named is dropped with a reason - it drew
    as ", not checked" under an empty title on Content. A hold whose reason is
    a pass is removed, and its check reads clean. A reason that is an input
    variable is said as words. A trailing full stop is taken off, because the
    card adds its own and "AUTHORS.." was on screen."""
    kept: list[dict] = []
    for n in parsed.not_assessable:
        if not isinstance(n, dict):
            continue
        check = str(n.get("check") or "").strip()
        if not check or check.endswith("/") or not check_id_of(check):
            parsed.dropped.append({"row": n, "reason": "held with no check named"})
            continue
        needs = str(n.get("needs") or "").strip().rstrip(".").strip()
        if needs and _PASS_REASON.search(needs) and not _NAMES_INPUT.search(needs):
            # Counted, not vanished: 209's accounting must still sum, so a
            # removed pass is a dropped row with its reason.
            parsed.dropped.append({"row": n, "reason": "a pass, not a hold"})
            continue
        if _INPUT_NAME.match(needs):
            needs = _input_words(needs)
        kept.append({**n, "needs": needs} if needs or "needs" in n else n)
    parsed.not_assessable = kept
    return parsed


def _path(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.strip().lower().rstrip("/") or "/"
    path = parts.path if parts.scheme else url
    return (path or "/").strip().lower().rstrip("/") or "/"


def template_page(template: str, page_set: list[str]) -> str | None:
    """The first page in `page_set` a URL template names (item 217).

    Templates are the URL pattern table's (`urlshape.derive_pattern`):
    `/seo/on-page/<slug>/`, `/blog/YYYY/MM/<slug>/`. A brief may also write the
    display form, `/seo/*`. A `<...>`, `*`, `YYYY`, `MM` or `DD` segment
    matches any one segment; every other segment must be equal. The page set
    is the brief's own input, in its order, so for Speed this is the page the
    trace sampled for that template."""
    def segs(p: str) -> list[str]:
        return [s for s in p.strip().lower().split("/") if s]
    want = segs(template)
    wild = lambda s: s == "*" or (s.startswith("<") and s.endswith(">")) or s in ("yyyy", "mm", "dd")
    for url in page_set:
        have = segs(_path(url))
        if len(have) == len(want) and all(wild(w) or w == h for w, h in zip(want, have)):
            return url
    return None


def page_index(page_set: list[str]) -> dict[str, str]:
    """Path -> the url the page set spells, so a row may name either."""
    out: dict[str, str] = {}
    for url in page_set:
        out.setdefault(_path(url), url)
        out.setdefault(url.strip().lower().rstrip("/"), url)
    return out


def questions_in(text: str) -> list[str]:
    """Lines that ask something of the operator. A conforming brief never
    asks; one that did has stopped rather than answered."""
    out = []
    for line in text.splitlines():
        s = line.strip().strip("*_ ").rstrip()
        if s.endswith("?") and len(s) > 12:
            out.append(s)
    return out


#: A bracketed citation carrying at least one word character: `[TEC/robots-missing]`,
#: `[crawl]`, `[content \u00b7 CNT/gap]`. Empty brackets do not count.
_CITATION = re.compile(r"\[[^\]]*\w[^\]]*\]")
#: The summary the citation rule applies to, up to the next heading of any
#: level. Matched case-insensitively on the heading text rather than on its
#: depth: the prompt fixes the words, and a model that writes `##` where the
#: FORMAT said `###` has still written the executive summary.
_SUMMARY = re.compile(r"^#{1,6}\s*executive summary\s*$(.*?)(?=^#{1,6}\s|\Z)",
                      re.I | re.M | re.S)
#: End of a sentence: terminal punctuation, then whitespace. A citation sits
#: before the full stop by the prompt's own examples, so this never splits one
#: away from the sentence it belongs to.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def uncited_summary_sentences(body: str) -> list[str]:
    """Sentences in the plan's executive summary that cite nothing.

    Brief v18 step AY. A sentence is cited when it carries `[...]` with
    something in it; the prompt asks for a check id or a part, and the
    engine does not police which - a citation naming a part the audit does
    not have is a wrong citation, which the per-part sections beside it
    make visible, while no citation at all is unfalsifiable.

    Fragments with no letters, and anything under fifteen characters, are
    not sentences: a bare "S." from an effort band or a stray bullet
    marker would otherwise fail a document for punctuation.

    An empty list is returned when there is no executive summary at all -
    a document with no summary has no uncited summary sentence, and
    refusing it here would be this function answering a question it was
    not asked. The FORMAT's headings are the generator's own contract.
    """
    match = _SUMMARY.search(body or "")
    if not match:
        return []
    out: list[str] = []
    for line in match.group(1).splitlines():
        # Bullet and ordered-list markers, and the prompt's own "(1)"
        # numbering, are not sentence content.
        text = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", line).strip()
        if not text:
            continue
        for sentence in _SENTENCE.split(text):
            sentence = sentence.strip()
            if len(sentence) < 15 or not re.search(r"[A-Za-z]{3}", sentence):
                continue
            if not _CITATION.search(sentence):
                out.append(sentence)
    return out


def parse(report: str, checks: list[str], page_set: list[str],
          defaults: dict[str, str] | None = None, rules: Rules | None = None,
          reads: list[str] | None = None, inputs: dict[str, str] | None = None) -> Parsed:
    """The first fenced JSON block as rows, each judged against the header's
    checks and the run's pages; the rest as the body a person reads.

    `defaults` is the registry's default severity per check (brief v11
    step AH): a row's severity is the default where the brief's is missing
    or lower, and the brief's where it is higher and the row's note says
    why - a raise with no reason is written back to the default. `rules`
    is the part's own rules on the replacements (brief v12 step AL),
    enforced by `enforce` on the rows that pass the shape checks."""
    match = FENCE.search(report or "")
    if not match:
        asked = questions_in(report or "")
        return Parsed(status=NEEDS_INPUT if asked else READ, questions=asked,
                      body=(report or "").strip(), block=False)
    body = (report[:match.start()] + report[match.end():]).strip()
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        log.warning("contract block is not JSON (%s); treated as no block", e)
        asked = questions_in(body)
        return Parsed(status=NEEDS_INPUT if asked else READ, questions=asked,
                      dropped=[{"row": None, "reason": f"block is not JSON: {e}"}],
                      body=body, block=False)
    # A generator answers with a record of what it wrote, not with rows
    # (brief v17 step AX). Read before the row loop, because that loop
    # would drop every key of this block as an unknown row and report a
    # document as five parse failures.
    if str(data.get("source") or "").strip() == "generator":
        parsed = Parsed(status=READ, body=body, block=True,
                        part=str(data["part"]) if data.get("part") else None)
        parsed.generator = {
            "brief": str(data.get("brief") or ""),
            "page": str(data.get("page") or ""),
            "document_id": data.get("document_id"),
        }
        parsed.assumptions = [str(a) for a in (data.get("assumptions") or []) if a]
        # The plan's own rule (brief v18 step AY): every sentence in the
        # executive summary traces to a check id or a part, in brackets.
        # Enforced here rather than trusted, because this is the one
        # document a client reads on its own - the per-part sections
        # behind it are where a claim can be checked, and a summary
        # sentence with nothing behind it is the model's opinion printed
        # in the operator's name.
        #
        # The whole document is dropped rather than the offending line,
        # and that is the deliberate half. A summary with one sentence
        # silently removed still reads as a summary, so the reader has no
        # way to know something was cut; a plan that could not be
        # generated says so, and the report falls back to the per-part
        # sections, which are all measured.
        if parsed.generator["brief"] == "plan":
            uncited = uncited_summary_sentences(body)
            if uncited:
                _drop(parsed, None,
                      "the executive summary has "
                      f"{len(uncited)} sentence(s) citing no check or part: "
                      + " | ".join(uncited[:3]))
                parsed.generator = None
        return parsed

    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        # **A missing `rows` list is only a defect for a brief that has
        # rows to give.** A brief declaring no checks emits no findings by
        # construction - Triage answers with a `ranking`, the generator
        # with a document - and reporting its block as a parse failure is
        # the engine calling a correct answer malformed.
        #
        # Triage's second paid run on Birch is what found this: the block
        # was read, the guard fired before anything looked at `ranking`,
        # and a good ranking was dropped with "block has no `rows` list".
        if not checks:
            parsed = Parsed(status=READ, body=body, block=True,
                            part=str(data["part"]) if isinstance(data, dict)
                            and data.get("part") else None)
            if isinstance(data, dict):
                parsed.assumptions = [str(a) for a in (data.get("assumptions") or []) if a]
                parsed.not_assessable = [x for x in (data.get("not_assessable") or [])
                                         if isinstance(x, dict)]
                for name in ("map", "clusters", "ranking", "hubs",
                             "templates", "fixes"):
                    setattr(parsed, name, [x for x in (data.get(name) or [])
                                           if isinstance(x, dict)])
                if data.get("schema"):
                    parsed.schema = str(data["schema"])
                if isinstance(data.get("locales"), dict):
                    parsed.locales = data["locales"]
                if isinstance(data.get("model"), dict):
                    parsed.model = {str(k): str(v) for k, v in data["model"].items()}
            return parsed
        log.warning("contract block has no `rows` list; treated as empty")
        return Parsed(status=READ, dropped=[{"row": None, "reason": "block has no `rows` list"}],
                      body=body, block=True)

    allowed = set(checks)
    pages = page_index(page_set)
    parsed = Parsed(status=READ, body=body, block=True,
                    part=str(data["part"]) if data.get("part") else None,
                    strategy=str(data["strategy"]) if data.get("strategy") else None)
    parsed.assumptions = [str(a) for a in (data.get("assumptions") or []) if a]
    parsed.eligibility = [e for e in (data.get("eligibility") or []) if isinstance(e, dict)]
    parsed.hubs = [h for h in (data.get("hubs") or []) if isinstance(h, dict)]
    # Brief v20 (items 147, 148). `clusters` is already here and is reused for
    # International's: the field is per brief, so its SHAPE is whatever that
    # brief wrote -- Cannibalisation's cluster names a survivor and hreflang's
    # names members and a method, and neither reader looks at the other's.
    if data.get("schema"):
        parsed.schema = str(data["schema"])
    # An object, not a list (see `Parsed.locales`). Kept only where it is one:
    # a list here would be a brief answering the field in a shape the screen
    # cannot draw, and storing it would move the failure to the renderer.
    if isinstance(data.get("locales"), dict):
        parsed.locales = data["locales"]
    for name in ("map", "clusters", "ranking", "templates", "fixes"):
        setattr(parsed, name, [x for x in (data.get(name) or [])
                               if isinstance(x, dict)])
    _security_block(parsed, data)
    ai_surface = str(data.get("part") or "") == "ai-surface"
    if ai_surface:
        from . import ai_surface as _ais_block
        _ais_block.read_block(parsed, data, reads or [], checks)
    if isinstance(data.get("model"), dict):
        parsed.model = {str(k): str(v) for k, v in data["model"].items()}
    entity = data.get("entity")
    parsed.entity = entity if isinstance(entity, dict) else None
    parsed.not_assessable = [x for x in (data.get("not_assessable") or []) if isinstance(x, dict)]
    for raw in data["rows"]:
        if not isinstance(raw, dict):
            _drop(parsed, raw, "row is not an object")
            continue
        check = str(raw.get("check") or "").strip()
        if check.split("/")[-1] in HELD_ONLY:
            _drop(parsed, raw, f"{check} can only be held: it is listed in "
                               "not_assessable or not at all")
            continue
        if check not in allowed:
            _drop(parsed, raw, f"check {check!r} is not one this analysis may emit "
                               f"({', '.join(sorted(allowed)) or 'none listed'})")
            continue
        ais_notes: list[str] = []
        if ai_surface and check.startswith("AIS/"):
            from . import ai_surface as _ais_block
            policed, reason, ais_notes = _ais_block.police_row(
                check, raw, llms_txt_build=str((inputs or {}).get("LLMS_TXT_BUILD") or "")
                .strip().lower() == "true")
            if policed is None and reason == _ais_block.HOLD:
                parsed.not_assessable.append({
                    "check": check, "page": raw.get("page"),
                    "needs": str(raw.get("note") or raw.get("evidence") or
                                 "the site record holds no entity to draw a candidate from")})
                continue
            if policed is None:
                _drop(parsed, raw, reason)
                continue
            raw = policed
        page_raw = str(raw.get("page") or "").strip()
        template = str(raw.get("template") or "").strip()
        if not page_raw and template:
            # Item 217. A per-template row (`page: null`, `template` set -
            # every Speed analysis row) fell through to `_path("")`, which
            # is "/", so it was filed on the home page, drawn as a card for
            # the home page, and counted in PAGES as a page. On twenty22 that
            # put a 1.8 s TTFB and a logo LCP on `/`, whose own trace reads
            # 560 ms and a 951 KB photograph. It is filed on the page the
            # page set holds for that template - for Speed, the traced one.
            page = template_page(template, page_set)
            if not page:
                _drop(parsed, raw, f"template {template!r} matches no page in the run's page set")
                continue
        else:
            page = pages.get(_path(page_raw)) or pages.get(page_raw.lower().rstrip("/"))
        if not page and check.startswith("SEC/") and _is_well_known(page_raw):
            # A Security row about a path the well-known sweep requested
            # (`/wp-json/wp/v2/users`, `/.env`) is about the site, not a crawled
            # page. The first live run on twenty22 (2026-09-14) put the users
            # endpoint in `page` and the page-set rule dropped a true HIGH. It is
            # stored site-level with the path kept in its evidence.
            raw = {**raw, "page": None,
                   "evidence": f"{page_raw}: {raw.get('evidence') or ''}".strip()}
            page_raw = ""
            page = pages.get(_path(page_raw)) or pages.get(page_raw)
        if not page and ai_surface and not page_raw:
            # A site-level AI surface row (`page: null`): stored against the
            # site's own entry, as every site row in this part is.
            page = pages.get("/") or (pages.get(_path(page_set[0])) if page_set else None)
        if not page:
            _drop(parsed, raw, f"page {page_raw!r} is not in the run's page set")
            continue
        status = str(raw.get("status") or "").strip().upper()
        if status == "INFO" and (defaults or {}).get(check) == "info":
            # The prompt's INFO rows (`ai-experience-unmeasured`,
            # `llms-txt-authored`): a statement, stored as a FAIL-shaped row
            # at the registry's INFO so no reader has to learn a fourth status.
            status = "FAIL"
        if status not in STATUSES:
            _drop(parsed, raw, f"status {status!r} is not one of {'/'.join(STATUSES)}")
            continue
        severity = SEVERITIES.get(str(raw.get("severity") or "").strip().upper())
        default = (defaults or {}).get(check)
        if isinstance(default, dict):
            # A default per status (brief v11 step AI): FAIL and WARN mean
            # different things on some checks; PASS-OVERRIDE takes FAIL's.
            default = default.get(status) or default.get("FAIL")
        note = str(raw.get("note") or "").strip()
        raised = False
        if default is None:
            if severity is None:
                _drop(parsed, raw, f"severity {raw.get('severity')!r} is not HIGH, MEDIUM or LOW")
                continue
        elif severity is None and default == "info":
            severity = "info"
        elif severity is None or RANK[severity] < RANK[default]:
            severity = default
        elif RANK[severity] > RANK[default]:
            if note:
                raised = True
            else:
                severity = default
        dimension, _, check_id = check.partition("/")
        replacement = raw.get("replacement")
        replacement = str(replacement).strip() if replacement else None
        group = raw.get("group")
        # Fields a part adds beyond the fixed ones (`page_type`, a triple's
        # entities ...) travel with the row (brief v11 step AI).
        extra = {k: v for k, v in raw.items()
                 if k not in ("check", "page", "status", "severity", "evidence",
                              "replacement", "note", "group", "image", "also_resolves",
                              "kind", "block", "where", "fields", "config")
                 and v not in (None, "")}
        config = [c for c in (raw.get("config") or []) if isinstance(c, dict)]
        # Security (brief v20 step BD): two refusals the prompt states and the
        # parser enforces rather than trusts.
        if check.startswith("SEC/"):
            refusal = _security_refusal(check_id_of(check), raw, config, rules)
            if refusal:
                _drop(parsed, raw, refusal)
                continue
        row_fields = raw.get("fields")
        row_fields = row_fields if isinstance(row_fields, dict) else {}
        image = raw.get("image")
        also = [str(c).strip() for c in (raw.get("also_resolves") or []) if str(c).strip()]
        # A row may only say it closes a check the brief may emit at all.
        dropped_also = [c for c in also if c not in allowed]
        if dropped_also:
            _drop(parsed, raw, f"also_resolves names {', '.join(dropped_also)}, "
                               "which the analysis may not emit")
            continue
        kind = raw.get("kind")
        block_ref, where = raw.get("block"), raw.get("where")
        parsed.rows.append(Row(
            check=check, dimension=dimension, check_id=check_id or check, page=page,
            status=status, severity=severity,
            evidence=str(raw.get("evidence") or "").strip(),
            replacement=replacement,
            note="; ".join(filter(None, [note, *ais_notes])),
            group=str(group).strip() if group else None, raised=raised, extra=extra,
            image=str(image).strip() if image else None, also_resolves=also,
            kind=str(kind).strip() if kind else None,
            block=str(block_ref).strip() if block_ref not in (None, "") else None,
            where=str(where).strip() if where else None, fields=row_fields,
            # Brief v20's three row fields (items 147, 148). Each is None where
            # the brief said nothing, which is not the same as empty: a row
            # with no `confidence` is a measurement, and a row with
            # `confidence: ""` is a brief that answered the field badly.
            fix_id=(str(raw["fix_id"]).strip()
                    if raw.get("fix_id") not in (None, "") else None),
            suppressed=_check_list(raw.get("suppressed")),
            confidence=(str(raw["confidence"]).strip()
                        if raw.get("confidence") not in (None, "") else None),
            config=config))
    if rules is not None:
        enforce(parsed, rules)
    clean_holds(parsed)
    if parsed.ai_surface is not None:
        from . import ai_surface as _ais_block
        parsed.ai_surface["client_to_supply"] = (
            sum(_ais_block.count_client_to_supply([r.replacement, r.extra]) for r in parsed.rows))
    return parsed


def _check_list(value) -> list[str]:
    """A row's `suppressed` as a list of check ids, however a brief wrote it.

    The schema says a list. An empty list is the common, correct answer and
    must come back empty -- not as the string `'[]'`, which is what `str()`
    made of it and what put "Set aside: []" on every row of the first real
    run. A bare string is wrapped rather than rejected, because a brief
    naming one check without brackets meant one check. Anything else, or a
    list of non-strings, contributes nothing rather than inventing an id.
    """
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v and v not in ("[]", "none", "null") else []
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value
                if isinstance(x, str) and str(x).strip()]
    return []


def _is_well_known(page: str) -> bool:
    """Whether `page` names a path the well-known sweep requests."""
    from urllib.parse import urlsplit

    from clauditseo.crawler.wellknown import PATHS
    parts = urlsplit(page)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    known = {p for p, _ in PATHS}
    return path in known or path.rstrip("/") in {k.rstrip("/") for k in known}


def check_id_of(check: str) -> str:
    return check.partition("/")[2] or check


def _security_block(parsed: Parsed, data: dict) -> None:
    """The Security brief's block fields (brief v20 step BD), each kept only in
    the shape the screen draws: objects where the schema gives an object,
    lists of objects where it gives a list."""
    for name in ("compromise", "transport"):
        if isinstance(data.get(name), dict):
            setattr(parsed, name, data[name])
    for name in ("ledger", "headers", "cookies", "scripts", "do_not_spend_on"):
        setattr(parsed, name, [x for x in (data.get(name) or []) if isinstance(x, dict)])


#: Text that turns a finding into an attack: credential lists, takeover
#: steps, exploitation tooling. `security.md` forbids all three ("report
#: exposure; do not weaponise"); a row carrying one is dropped and logged
#: rather than stored where a client document could print it. Narrow on
#: purpose - a fix that says "rotate the password" is not a credential list.
_EXPLOIT = __import__("re").compile(
    r"\b(?:wordlist|password list|credential list|rockyou)\b"
    r"|\b(?:sqlmap|hydra|metasploit|msfconsole|wpscan\s+--enumerate)\b"
    r"|\b(?:heroku (?:create|domains:add)|aws s3 mb|az webapp create|gcloud storage buckets create)\b",
    __import__("re").I)


#: The CSP directives whose sources are held to the observed origins. The
#: others (font-src, connect-src, img-src ...) load from CSS and script the
#: crawl does not read, so an origin there cannot be checked against markup.
_CSP_POLICED = ("default-src", "script-src", "script-src-elem", "frame-src", "child-src")
_CSP_HOST = re.compile(r"^(?:https?://)?(\*\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?::\d+)?(?:/.*)?$", re.I)


def csp_unobserved(policy: str, observed: set[str], site_host: str) -> list[str]:
    """The hosts a proposed CSP's script, frame and default sources name that
    the run never saw the markup load from, and that are not the site's own.
    `*.x` counts as observed when any observed host sits under x."""
    from clauditseo.modules.sec import _registrable
    text = re.sub(r"^\s*content-security-policy(?:-report-only)?\s*:\s*", "", policy or "", flags=re.I)
    site_reg = _registrable(site_host) if site_host else ""
    out: list[str] = []
    for directive in text.split(";"):
        tokens = directive.split()
        if not tokens or tokens[0].lower() not in _CSP_POLICED:
            continue
        for token in tokens[1:]:
            m = _CSP_HOST.match(token.strip("\"'"))
            if not m or token.startswith("'"):
                continue
            wildcard, host = bool(m.group(1)), m.group(2).lower()
            if site_reg and _registrable(host) == site_reg:
                continue
            seen = any(o == host or o.endswith("." + host) for o in observed) if wildcard \
                else host in observed
            if not seen:
                out.append(("*." if wildcard else "") + host)
    return sorted(set(out))


def _security_refusal(check_id: str, raw: dict, config: list[dict],
                      rules: "Rules | None" = None) -> str | None:
    """Why a SEC row may not be stored, or None.

    **A held domain answers only under `not_assessable`.** G needs a reputation
    source and H active probing, neither of which this build has; a row for
    one of their checks is the model asserting a result nobody could have
    measured. **An exploit is never a replacement.**"""
    from clauditseo.modules.sec import HELD
    if check_id in HELD:
        return (f"SEC/{check_id} is held ({HELD[check_id]}); it may appear only "
                "under not_assessable, never as a row")
    text = " ".join(str(v) for v in (raw.get("replacement"), raw.get("evidence"),
                                     raw.get("verify"), raw.get("note")) if v)
    text += " " + " ".join(str(c.get("block") or "") for c in config)
    hit = _EXPLOIT.search(text)
    if hit:
        return (f"the row carries exploitation content ('{hit.group(0)}'), which "
                "the Security analysis forbids: exposure is reported, not weaponised")
    # **A proposed CSP names only origins the run observed.** A guessed origin
    # either breaks the site when enforced or allowlists a host nothing loads
    # from, and the brief's own note line claims "guessed origins: none".
    if check_id == "csp-policy" and rules is not None and rules.resource_origins is not None:
        unseen = csp_unobserved(str(raw.get("replacement") or ""), rules.resource_origins,
                                rules.site_host)
        if unseen:
            return ("the proposed CSP names origins the crawl never saw the site load "
                    f"from: {', '.join(unseen[:6])}")
    return None


def _drop(parsed: Parsed, raw, reason: str) -> None:
    log.warning("contract row dropped: %s :: %s", reason, json.dumps(raw, ensure_ascii=False)[:300])
    parsed.dropped.append({"row": raw, "reason": reason})


def legacy_findings(rows: list[Row]) -> list[dict]:
    """The rows in the shape the report envelope has always stored
    (`severity`, `code`, `summary`, `affected_urls`), so every reader that
    counts a brief's findings or takes its worst severity keeps working."""
    return [{"severity": r.severity, "code": r.check_id,
             "summary": r.evidence or r.check, "affected_urls": [r.page],
             "replacement": r.replacement, "status": r.status, "check": r.check}
            for r in rows]
