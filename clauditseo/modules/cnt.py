"""CNT — Content dimension.

Thin and duplicate content, readability, content-to-template ratio, and
freshness/authorship proxy signals. The deeper E-E-A-T judgement belongs to
the CNT-J analyst (P5); these are the deterministic proxies.
"""

from __future__ import annotations

import re

from clauditseo.crawler.types import CrawlResult
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier

from .pagefacts import PageFacts, extract_facts, html_pages, is_question

#: The page-type floors brief v17 step AX names, as placeholders the site
#: record overrides. A page whose type nobody set gets no floor and no
#: finding: `_page_type_for` refuses to guess a page's kind for
#: `schema-missing-for-type`, and inventing the kind here would invent the
#: finding with it.
WORD_FLOORS: dict[str, int] = {"service": 300, "location": 300, "article": 600}
#: Days after which a page's own date is old, per type. Both halves of
#: `stale` are stated in the prompt; only the first is available to a
#: sweep - see `_stale`.
STALE_DAYS: dict[str, int] = {"article": 365, "service": 730, "location": 730}
#: Figures, names, dates and units per hundred words, below which a page is
#: asserting rather than telling.
FACT_FLOORS: dict[str, float] = {"service": 2.0, "location": 2.0, "article": 3.0}
#: Two titles closer than this, once a location entity is taken out of
#: both, are the same title. Measured as a token Jaccard.
TITLE_OVERLAP = 0.8
#: How many overlap groups one row names before it says how many more
#: there are. A site whose blog shares a title template has hundreds, and
#: the finding is the pattern rather than the list.
TITLE_GROUPS_SHOWN = 6
#: A first sentence shorter than this does not answer the question above
#: it. Measured on the sentence rather than the paragraph: "It depends."
#: is not an answer however much detail follows it, and the outline's
#: forty-word window runs past the paragraph's end.
ANSWER_WORDS = 8

#: Every Content check's registered severity, and which of them only a
#: brief can answer (brief v17 steps AV1 and AX). `checks.py` reads both,
#: so the cost of a Content check is decided in one place - the same shape
#: `onp.py` and `links.py` keep.
DEFAULT_SEVERITY: dict[str, Severity] = {
    # The eight the sweep answers.
    "thin": Severity.MEDIUM,
    "stale": Severity.LOW,
    "no-author": Severity.LOW,
    "question-unanswered": Severity.MEDIUM,
    "duplicate-content": Severity.HIGH,
    "title-overlap": Severity.MEDIUM,
    "fact-density": Severity.LOW,
    "answer-first": Severity.MEDIUM,
    # Item 136q commit 6 / 136o Tab 4. INFO and unscored: the verdict is a
    # statement of what the page is about, and the scoring for what is wrong
    # already lives in `topic-drift`, Coverage's `gap` rows and
    # Cannibalisation's clusters. Scoring it here would count one fault twice.
    "entity-page-verdict": Severity.INFO,
    # Coverage's own, from `content-coverage.md`.
    "gap": Severity.MEDIUM, "format-gap": Severity.MEDIUM,
    "intent-gap": Severity.MEDIUM, "topic-drift": Severity.LOW,
    # Substance's.
    "eeat": Severity.MEDIUM, "substance": Severity.MEDIUM,
    "answer-surface": Severity.MEDIUM, "retrieval-cost": Severity.LOW,
    # Cannibalisation's, and Benchmark's four.
    "cannibalisation": Severity.HIGH,
    "term-density": Severity.LOW, "vocabulary-gap": Severity.MEDIUM,
    "demand-gap": Severity.MEDIUM, "optimisation-ratio": Severity.LOW,
}

#: What no sweep can answer. `topic-drift` is here rather than among the
#: free eight because the coverage prompt does not mark it `(free, read
#: only)` as it does `thin` and `title-overlap`: whether a page's subject
#: has a path to the topical map is a judgement about the map, and the
#: engine holds no map.
BRIEF_ONLY_CHECKS: frozenset[str] = frozenset({
    "gap", "format-gap", "intent-gap", "topic-drift",
    "eeat", "substance", "answer-surface", "retrieval-cost",
    "cannibalisation",
    "term-density", "vocabulary-gap", "demand-gap", "optimisation-ratio",
})

THIN_WORDS = 150
LONG_SENTENCE_WORDS = 35
MIN_TEXT_RATIO = 0.05


#: A shingle on at least this share of crawled pages is site furniture.
#: 0.6 rather than a majority: a site with two template families (say a blog
#: and a product section) puts each one's chrome on well under half the
#: pages, and a 0.5 cut would keep both.
CHROME_SHARE = 0.6
#: Below this many shingles of its own, a page has too little to compare.
MIN_UNIQUE_SHINGLES = 40
DUPLICATE_OVERLAP = 0.8
#: Below this many, it is a coincidence rather than how the site is built,
#: and thin-content already speaks to the individual page.
BARE_PAGE_FLOOR = 3



#: What counts as a fact: a figure, a date, a unit, or a capitalised name
#: that is not the first word of its sentence. Deliberately generous - the
#: check is a floor, and a floor that fires on a page full of numbers
#: would be measuring something else.
_FIGURE = re.compile(r"\b\d[\d,.]*\s?(?:%|km|kg|m|mm|cm|hrs?|hours?|days?|weeks?|"
                     r"months?|years?|min(?:utes?)?|sec(?:onds?)?|[$£€])?", re.I)
_NAME = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b")


def fact_count(text: str) -> int:
    """Figures, names, dates and units in a page's own words."""
    return len(_FIGURE.findall(text or "")) + len(_NAME.findall(text or ""))


def _author_of(f: PageFacts) -> str:
    """Who the page says wrote it: an `author` in its structured data, a
    `rel=author` link, or a byline in its own words. Empty where none."""
    for block in (f.jsonld_blocks or []):
        if '"author"' in block:
            return "structured data"
    for link in (f.links or []):
        if "author" in (link.get("rel") or "").lower():
            return "rel=author"
    if re.search(r"\b[Bb]y\s+[A-Z][a-z]+\s+[A-Z][a-z]+", f.text or ""):
        return "byline"
    return ""


def content_hash(text: str) -> str:
    """A page's own words, normalised, as one value.

    Whitespace-collapsed and lower-cased before hashing: a re-render that
    changes indentation has not changed the page, and a check about
    whether anybody edited it must not fire on a deploy.
    """
    import hashlib

    return hashlib.sha256(" ".join((text or "").lower().split()).encode()).hexdigest()


def _stale(f: PageFacts, page_type: str, prior: dict | None) -> tuple[int, str] | None:
    """An old date **and** a page nobody has touched since (operator,
    2026-09-06).

    A date alone over-fires: a CMS nobody configured leaves
    `dateModified` at first publication, and a page rewritten last week
    reads as four years old. So the second condition is asked as it is
    specified - the previous site-wide run's own record of this page,
    hashed the same way - and where there is no previous run the check
    says nothing rather than reporting half of itself as the whole.

    `prior` is `{url: content_hash}` from the last site-wide crawl,
    handed in by the caller, because a module has one crawl and the
    database is the caller's. A crawl stored before the hash existed
    supplies none, and the check then says nothing.
    """
    import datetime as _dt

    threshold = STALE_DAYS.get(page_type)
    if not threshold:
        return None
    seen: list[_dt.date] = []
    for block in (f.jsonld_blocks or []):
        for match in re.findall(r"\"date(?:Modified|Published)\"\s*:\s*\"([0-9]{4}-[0-9]{2}-[0-9]{2})",
                                block):
            try:
                seen.append(_dt.date.fromisoformat(match))
            except ValueError:
                continue
    if not seen:
        return None
    newest = max(seen)
    days = (_dt.date.today() - newest).days
    if days <= threshold:
        return None
    if prior is None:
        # No previous site-wide crawl to compare against. The check is
        # two conditions and only one can be answered, so it answers
        # neither: a row saying "old" while unable to say "and untouched"
        # is the over-firing this rule exists to stop.
        return None
    before = prior.get(f.url)
    if before is None or before != content_hash(f.text):
        return None
    return (days, newest.isoformat())


def _same_page_title(a: PageFacts, b: PageFacts, places: set[str]) -> bool:
    """Whether two pages say the same thing in their title or their H1.

    Either signal is enough: a CMS that templates the title and varies the
    H1 has two pages that read differently, and one that varies the title
    and templates the H1 has two that read the same.
    """
    for left, right in ((a.title, b.title),
                        (a.headings[0][1] if a.headings else None,
                         b.headings[0][1] if b.headings else None)):
        if left and right and same_title(left, right, places):
            return True
    return False


def _place_words(site) -> set[str]:
    """Every word the record uses for a place.

    Read from the fields the record already keeps - the neighbourhoods,
    the service area, and whatever each location page is named for -
    rather than from a field added for this check. A second list of the
    site's suburbs is a second answer to "where does this business work",
    and the first one to go stale would be the one only this check reads.
    """
    names: list[str] = list(getattr(site, "neighbourhoods", None) or [])
    area = getattr(site, "service_area_entity", None)
    if area:
        names.append(str(area))
    for entry in (getattr(site, "location_pages", None) or []):
        if isinstance(entry, dict):
            names += [str(v) for k, v in entry.items()
                      if k in ("entity", "name", "location", "suburb") and v]
        elif entry:
            names.append(str(entry))
    return {w for name in names for w in re.findall(r"[a-z0-9]+", str(name).lower())}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


def same_title(a: str, b: str, places: set[str]) -> bool:
    """Whether two titles say the same thing (operator, 2026-09-06).

    Three steps, and the order of them is the whole rule.

    1. Take the location words out of both. What is left is what each
       page is *about*.
    2. Do the remainders match? Equal, or one inside the other, or close
       enough on a token Jaccard. Containment matters: `plumbing
       melbourne` and `plumbing services melbourne` have remainders
       `{plumbing}` and `{plumbing, services}`, which no similarity
       measure calls equal and which are plainly the same subject.
    3. If they match, ask what the locations say. **Different** location
       entities means two pages doing their job - `Plumber Richmond` and
       `Plumber Hawthorn` - and nothing is emitted. Neither page carrying
       one, or both carrying the same one, means two pages competing for
       one subject, and that is the finding.

    Getting step 3 backwards is how a check like this fires on every
    location page of every local site; skipping step 2's containment is
    how it then misses the pair it exists for.
    """
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return False
    here, there = left & places, right & places
    core_a, core_b = left - places, right - places
    if not core_a or not core_b:
        return False
    same_core = (core_a == core_b
                 or core_a <= core_b or core_b <= core_a
                 or len(core_a & core_b) / len(core_a | core_b) >= TITLE_OVERLAP)
    if not same_core:
        return False
    # The exempt pattern: one subject, two places.
    if here and there and here != there:
        return False
    return True


def _site_chrome(sets: list[set[str]]) -> set[str]:
    """Shingles common to most pages — the header, nav, footer and teasers.

    Needs at least three pages to mean anything: on two, everything shared is
    "on 100% of pages" and the whole comparison would be subtracted away.
    """
    if len(sets) < 3:
        return set()
    counts: dict[str, int] = {}
    for sh in sets:
        for s in sh:
            counts[s] = counts.get(s, 0) + 1
    cut = len(sets) * CHROME_SHARE
    return {s for s, n in counts.items() if n >= cut}


def _shingles(text: str, size: int = 5) -> set[str]:
    words = re.sub(r"[^a-z0-9\s]", "", text.lower()).split()
    return {" ".join(words[i:i + size]) for i in range(max(0, len(words) - size + 1))}


_URL_STOPWORDS = frozenset({
    "the", "and", "for", "our", "your", "with", "from",
    "finance", "services", "service", "solutions", "group",
})


def entity_at_top(f, name: str) -> bool:
    """Whether a page names a record entity where machines look: its URL, its
    title or its H1. The one test both readers use (item 145 BG): Content's
    page verdict counts the entities that reach a page's top with it, and
    `AIS/entity-unnamed` reports the entities that reach no page's top."""
    from clauditseo.modules.links import _mentions
    h1 = " ".join(t for lv, t in f.headings if lv == 1)
    return (_mentions(f.path.replace("-", " "), name)
            or _mentions(f.title or "", name) or _mentions(h1, name))


#: Item 240: properties of the whole crawl (see `onp.CROSS_PAGE_CHECKS`).
CROSS_PAGE_CHECKS: frozenset[str] = frozenset({"duplicate-content", "title-overlap"})


class ContentModule:
    code = "CNT"
    name = "Content"
    default_weight = scoring.DEFAULT_WEIGHTS["CNT"]
    #: Every check is per-document — `thin-content`,
    #: `readability-long-sentences`, `low-text-ratio`, `template-only-page`
    #: and `duplicate-content` all name a page and all are re-measured by
    #: re-reading it. `duplicate-content` is the only one whose *verdict*
    #: needs the rest of the corpus, and it still names the page that carries
    #: the duplicate. See `registry.page_blind_dims`.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        site = context.get("site")
        html = html_pages(crawl.pages)
        facts = [extract_facts(p) for p in html]
        raw_sizes = {f.path: len(p.content) for f, p in zip(facts, html)}
        # The record's own floors where it has them (brief v17 step AX):
        # 300 and 600 are placeholders, and a client whose service pages
        # are deliberately short is not a client with fifty findings.
        floors = {**WORD_FLOORS, **(getattr(site, "word_floors", None) or {})}
        records = {p.url: p for p in html}
        # What `PRIOR_RUN` recorded for each page, so `stale` can ask its
        # second condition (operator, 2026-09-06). `None` - no previous run
        # - is different from an empty map, and the check treats it as
        # "cannot answer" rather than "unchanged".
        #
        # The SET of runs this may come from is the contract's since item
        # 136p, and it moved: a re-check counts and a page scan does not.
        # Before that the caller chose `kind='audit'`, so on Acme `stale`
        # was comparing a fourteen-page site-wide run against a ONE-page
        # scan and could answer for no page at all.
        prior = context.get("prior_pages")
        findings: list[Finding] = []
        for f in facts:
            findings += self._page_checks(f, raw_sizes.get(f.path, 0))
            findings += self._content_checks(f, site, floors, records.get(f.url),
                                             prior)
        findings += self._duplicate_content(facts)
        findings += self._title_overlap(facts, site)
        for f in facts:
            v = self._entity_page_verdict(f, site)
            if v is not None:
                findings.append(v)
        return findings

    # --- item 136q commit 6 / 136o Tab 4 --------------------------------

    def _entity_page_verdict(self, f, site):
        """What ONE page is about, in the record's own entities.

        Three states, engine-computed (item 136o):

          about one entity   exactly one record entity is named in URL AND
                             Title AND H1. PASS.
          about N, owns K    the H1 and H2s name more than one service-kind
                             entity; K of them are owned (named in
                             URL+Title+H1). Coverage's "home page doing every
                             service". FAIL.
          about none         no entity reaches URL, Title or H1 - `topic-drift`
                             from the other side. FAIL.

        Free and structural. INFO and unscored, because the fault is already
        scored by `topic-drift`, the `gap` rows and the clusters; this states
        what the page is about, and `contested[]` names the pairs
        Cannibalisation also reports so the two cannot drift.

        `not_assessable` where the record lists no entities: the question
        cannot be asked, and answering "about none" would report the
        operator's empty record as the page's fault. The item's fuller
        condition ("and no Coverage run exists") is the tab's; the sweep
        cannot see a Coverage run from inside the module, and a record with
        entities is enough to ask the question.
        """
        from clauditseo.modules.links import _entity_rows, _mentions
        from clauditseo.modules.links import _entity_rows, _mentions

        entities, _ = _entity_rows(site) if site is not None else ([], [])
        names = [e["entity"] for e in entities]
        hub_of = {e["entity"]: e.get("hub") or "" for e in entities}
        if not names:
            return Finding(
                dimension=self.code, check_id="entity-page-verdict",
                severity=Severity.INFO,
                summary=f"{f.path}: no entities on the site record to judge "
                        "what this page is about.",
                subject=f.path, affected_urls=[f.url],
                evidence={"verdict": "not_assessable",
                          "needs": "site record entities"},
                recommendation="Set the site record's sub-services, locations "
                               "and authors on Admin › Sites.")

        url_txt = f.path
        title = f.title or ""
        h1 = " ".join(t for lv, t in f.headings if lv == 1)
        h2s = " ".join(t for lv, t in f.headings if lv == 2)

        def in_url(name):
            # A slug rarely carries a multi-word entity name whole, so "named
            # in the URL" is: this page IS the entity's hub, OR a significant
            # word of the name is in the slug. `/bridging` names "Bridging
            # finance"; a stop word like "finance" alone does not.
            hub = hub_of.get(name) or ""
            try:
                from urllib.parse import urlsplit
                if hub and (urlsplit(hub).path or "/").rstrip("/").lower()                         == (f.path or "/").rstrip("/").lower():
                    return True
            except ValueError:
                pass
            slug = url_txt.replace("-", " ").replace("_", " ").lower()
            words = [w for w in name.lower().split()
                     if w not in _URL_STOPWORDS and len(w) > 2]
            return any(_mentions(slug, w) for w in words)

        def in_url_title_h1(name):
            return in_url(name) and _mentions(title, name) and _mentions(h1, name)

        owned = [n for n in names if in_url_title_h1(n)]
        in_headings = [n for n in names
                       if _mentions(h1, n) or _mentions(h2s, n)]
        reaches_top = [n for n in names if entity_at_top(f, n)]

        if len(owned) == 1 and len(in_headings) <= 1:
            verdict = f"About one entity — {owned[0]}"
            status, contested = "PASS", []
        elif len(in_headings) > 1:
            verdict = (f"About {len(in_headings)} entities — and owns "
                       f"{len(owned)} of them")
            status, contested = "FAIL", in_headings
        elif not reaches_top:
            verdict = "About none"
            status, contested = "FAIL", []
        else:
            # Named at the top but not fully owned, and not multi-entity:
            # mentioned, not about. Reported as FAIL of "about one".
            verdict = "About one entity — " + (reaches_top[0]
                      if reaches_top else "—")
            status, contested = "FAIL", []

        return Finding(
            dimension=self.code, check_id="entity-page-verdict",
            severity=Severity.INFO,
            summary=f"{f.path}: {verdict}.",
            subject=f.path, affected_urls=[f.url],
            evidence={"verdict": verdict, "status": status,
                      "entities": reaches_top, "about": len(in_headings),
                      "owns": len(owned), "contested": contested},
            recommendation=("Good - the page names one entity through its URL, "
                            "title and H1." if status == "PASS"
                            else "Narrow the page to one entity, or split it, "
                                 "so its URL, title and H1 agree on what it is "
                                 "about."))

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # This dimension measures page content, so a crawl that fetched no
        # page measured none of it. Without this it inherited coverage 1.0
        # and reported 100 at full weight from nothing.
        return scoring.subscore(self.code, findings, self.default_weight, context,
                                coverage=scoring.page_coverage(context))


    # --- brief v17 step AX ------------------------------------------------

    def _content_checks(self, f: PageFacts, site, floors: dict, record,
                        prior: dict | None) -> list[Finding]:
        """The five per-page checks step AX adds, all of them arithmetic.

        Each says nothing where the page's type is unknown, except the two
        that need no type. That is the rule `schema-missing-for-type`
        set: a check about what a kind of page owes is not a check you can
        run on a page whose kind nobody has stated, and guessing the kind
        would invent the finding with it.
        """
        from clauditseo.modules.onp import _page_type_for

        out: list[Finding] = []
        page_type = _page_type_for(site, f.url) if site is not None else ""

        def raise_(check_id: str, summary: str, recommendation: str) -> None:
            out.append(Finding(
                dimension=self.code, check_id=check_id,
                severity=DEFAULT_SEVERITY[check_id], summary=summary,
                subject=f.path, affected_urls=[f.url],
                recommendation=recommendation))

        floor = floors.get(page_type)
        if floor and 0 < f.word_count < floor:
            raise_("thin",
                   f"{f.word_count} words on a {page_type} page, below the "
                   f"{floor}-word floor",
                   f"Bring it to at least {floor} words of the page's own "
                   "substance — what is included, what it costs, who did it.")

        # Fact density: a page can be long and say nothing.
        density_floor = FACT_FLOORS.get(page_type)
        if density_floor and f.word_count >= 100:
            per_hundred = fact_count(f.text) * 100.0 / f.word_count
            if per_hundred < density_floor:
                raise_("fact-density",
                       f"{per_hundred:.1f} figures, names or dates per 100 "
                       f"words, below the {density_floor:g} floor for a "
                       f"{page_type} page",
                       "Add the specifics a reader is looking for: prices, "
                       "timeframes, named clients, measurements.")

        # Author: only on the type that owes one.
        if page_type == "article" and not _author_of(f):
            raise_("no-author",
                   "An article with no visible author and no author in its "
                   "structured data",
                   "Name who wrote it, with their role, and link a profile "
                   "that says why they are worth reading on this.")

        stale = _stale(f, page_type, prior)
        if stale:
            days, when = stale
            raise_("stale",
                   f"The page's own date is {when}, {days} days old, past "
                   f"the {STALE_DAYS[page_type]}-day threshold for a "
                   f"{page_type} page, and its words have not changed since "
                   "the previous crawl",
                   "Re-read it and either update it or say when it was last "
                   "checked. An old page is not automatically a wrong one.")

        # The questions this page asks itself, and whether it answers them.
        unanswered, late = [], []
        for entry in (f.outline or []):
            if not is_question(entry.get("text") or ""):
                continue
            following = (entry.get("next_text") or "").strip()
            if not following:
                unanswered.append(entry["text"])
            # The first SENTENCE, not the first forty words: the window the
            # outline keeps runs past the end of the paragraph, so "It
            # depends." followed by three hundred words of detail measured
            # as a long answer.
            elif len(re.split(r"(?<=[.!?])\s", following)[0].split()) < ANSWER_WORDS:
                late.append(entry["text"])
        if unanswered:
            raise_("question-unanswered",
                   f"{len(unanswered)} heading{'' if len(unanswered) == 1 else 's'} "
                   "ask a question with no text beneath: "
                   + " · ".join(unanswered[:4]),
                   "Answer each one in the first sentence under the heading.")
        if late:
            raise_("answer-first",
                   f"{len(late)} question heading{'' if len(late) == 1 else 's'} "
                   "whose first words are too few to be the answer: "
                   + " · ".join(late[:4]),
                   "Put the answer in the first sentence, then the detail. A "
                   "reader and a model both stop at the first paragraph.")
        return out

    def _title_overlap(self, facts: list[PageFacts], site) -> list[Finding]:
        """Pages whose titles or H1s say the same thing, in groups.

        Location words are taken out before comparing, because `Plumber
        Richmond` and `Plumber Hawthorn` are two pages doing their job and
        a check that called them duplicates would fire on every location
        page of every local site.

        **Groups, not pairs, and that is what makes it usable.** The first
        cut reported every matching pair: six on a twelve-page site, which
        read well, and **25,651 across 227 pages** on a 260-page site
        whose blog shares one title template. Pairs are the wrong unit at
        any size - what a reader needs is "these nine pages all say the
        same thing", and the pair count is that fact squared. One row per
        group, so the number in front of an operator is a number of pages.
        """
        places = _place_words(site)
        # Grouped by the words that remain once the location is out, which
        # is what "the same title" means here. Pages join a group when
        # they match its first member, so the group is a set of pages that
        # say one thing rather than a transitive chain that drifts.
        groups: list[tuple[PageFacts, list[PageFacts]]] = []
        for page in facts:
            for lead, members in groups:
                if _same_page_title(lead, page, places):
                    members.append(page)
                    break
            else:
                groups.append((page, [page]))
        shared = [(lead, members) for lead, members in groups if len(members) > 1]
        if not shared:
            return []
        shared.sort(key=lambda g: -len(g[1]))
        pages = sorted({p.url for _, members in shared for p in members})
        named = "; ".join(
            f"{len(members)} pages titled like {(lead.title or lead.path)[:48]!r}"
            for lead, members in shared[:TITLE_GROUPS_SHOWN])
        more = len(shared) - TITLE_GROUPS_SHOWN
        return [Finding(
            dimension=self.code, check_id="title-overlap",
            severity=DEFAULT_SEVERITY["title-overlap"],
            summary=f"{len(shared)} group{'' if len(shared) == 1 else 's'} of pages "
                    f"share a title or H1, over {len(pages)} pages: {named}"
                    + (f"; and {more} more" if more > 0 else ""),
            subject="title-overlap",
            # No `affected_total`. That field means "what was found before
            # the emitter cut the list beside it" (Q-26), and this list is
            # whole: every page in every pair is in it. Putting the pair
            # count there said 28 found and 8 kept about a list of 8 that
            # was not cut at all — two different populations, pairs and
            # pages, one of them wearing the other's frame.
            affected_urls=pages,
            recommendation="For each group, decide which page owns the "
                           "subject and make the others say what they are "
                           "for, or fold them together.")]

    def _page_checks(self, f: PageFacts, raw_size: int) -> list[Finding]:
        out: list[Finding] = []

        if 0 < f.word_count < THIN_WORDS:
            out.append(Finding(
                dimension=self.code, check_id="thin-content", severity=Severity.MEDIUM,
                summary=f"{f.path} has only {f.word_count} words of body text.",
                subject=f.path, affected_urls=[f.url],
                evidence={"word_count": f.word_count, "threshold": THIN_WORDS},
                recommendation="Expand the page to genuinely answer its topic, or fold "
                               "it into a stronger page.",
            ))

        sentences = [s for s in re.split(r"[.!?]+", f.text) if s.strip()]
        if sentences:
            avg = sum(len(s.split()) for s in sentences) / len(sentences)
            if avg > LONG_SENTENCE_WORDS:
                out.append(Finding(
                    dimension=self.code, check_id="readability-long-sentences",
                    severity=Severity.LOW,
                    summary=f"Average sentence on {f.path} runs {avg:.0f} words.",
                    subject=f.path, affected_urls=[f.url],
                    evidence={"avg_sentence_words": round(avg, 1),
                              "sentences": len(sentences)},
                    recommendation="Break long sentences up; aim for a mix around "
                                   "15-20 words.",
                ))

        if raw_size > 2000 and f.word_count > 0:
            text_bytes = len(f.text)
            ratio = text_bytes / raw_size
            if ratio < MIN_TEXT_RATIO:
                out.append(Finding(
                    dimension=self.code, check_id="low-text-ratio", severity=Severity.LOW,
                    summary=f"Only {ratio:.1%} of {f.path} is readable text — the rest "
                            "is template and markup.",
                    subject=f.path, affected_urls=[f.url],
                    evidence={"text_bytes": text_bytes, "html_bytes": raw_size,
                              "ratio": round(ratio, 4)},
                    recommendation="Reduce boilerplate markup or add substantive "
                                   "content so the page is more than its template.",
                ))
        return out

    def _duplicate_content(self, facts: list[PageFacts]) -> list[Finding]:
        """Pages that genuinely repeat each other's content.

        Two faults compounded here and this fixes both.

        `f.text` is every text node in <body>, so the comparison counted
        navigation, footer, award banners and blog teasers as content. And
        the metric was `shared / min(len(a), len(b))` — containment against
        the *smaller* page — so any thin page whose text is mostly furniture
        scored near-total against anything sharing that furniture.

        Measured on the site this was found on: /contact-us holds 379
        shingles, 314 of them shared with /careers, giving the 83% that was
        reported as duplicate content. The shared strings were
        "partner portal about about us" and "australias 1 best workplace in"
        — the menu and a banner.

        Chrome is defined by observation rather than by markup: a shingle on
        most of the crawled pages is furniture, whatever tag holds it. That
        needs no per-site configuration and no assumption that a site uses
        <main> honestly, which most audited sites do not.
        """
        out: list[Finding] = []
        substantial = [f for f in facts if f.word_count >= 30]
        raw = {f.path: _shingles(f.text) for f in substantial}
        chrome = _site_chrome(list(raw.values()))
        shingle_map = {path: sh - chrome for path, sh in raw.items()}
        #: Pages with almost nothing of their own once the template is
        #: discounted. Collected rather than dropped — see below.
        bare: set[str] = set()
        seen_pairs: set[tuple[str, str]] = set()
        for i, a in enumerate(substantial):
            for b in substantial[i + 1:]:
                # Two URLs that differ only by a query string reduce to one
                # path, and comparing a page with itself produced
                # "/apply and /apply share 100% of their body text" on the
                # real site. The fact underneath is real — the same page
                # served at /apply and /apply?product_type=loc — but it is
                # parameter duplication and belongs to the URL checks, which
                # already carry `duplicate_forms`. Saying it here would say it
                # twice, in the category where it cannot be acted on.
                if a.path == b.path:
                    continue
                sa, sb = shingle_map[a.path], shingle_map[b.path]
                # Too little of its own to compare. Saying nothing is the
                # honest answer for a page that is mostly template — the
                # thin-content and low-text-ratio checks already speak to
                # that, and each says it once.
                #
                # Item 214: only the page that IS under the floor. This added
                # both pages of every pair with one bare member, so one bare
                # page (/contact-us/, 1.1% text) marked every page it was
                # compared with - all 45 on twenty22, including /website-seo/
                # at 1,889 words - and each finding's own evidence said its
                # `unique_shingles` was far above the floor its sentence named.
                if len(sa) < MIN_UNIQUE_SHINGLES:
                    bare.add(a.path)
                if len(sb) < MIN_UNIQUE_SHINGLES:
                    bare.add(b.path)
                if a.path in bare or b.path in bare:
                    continue
                # Symmetric. Containment against the smaller page made
                # "A is 83% contained in B" read as "A and B are 83% the
                # same", which is only true when the pages are a similar
                # size.
                overlap = len(sa & sb) / len(sa | sb)
                if overlap >= DUPLICATE_OVERLAP:
                    pair = tuple(sorted((a.path, b.path)))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    out.append(Finding(
                        dimension=self.code, check_id="duplicate-content",
                        severity=Severity.MEDIUM,
                        summary=f"{pair[0]} and {pair[1]} share {overlap:.0%} of their "
                                "body text.",
                        subject="|".join(pair),
                        affected_urls=[a.url, b.url],
                        evidence={"overlap": round(overlap, 3),
                                  "pages": list(pair),
                                  # Stated so the number can be argued with.
                                  "unique_shingles": [len(sa), len(sb)],
                                  "site_chrome_shingles": len(chrome),
                                  "metric": "jaccard on non-chrome shingles"},
                        recommendation="Consolidate the duplicates or canonicalise one "
                                       "to the other.",
                    ))

        # The other half of the same question, and the reason this is not
        # simply a quieter check.
        #
        # "Text on most pages" is two different things: site furniture, and a
        # block of content mass-duplicated across the site. Subtracting chrome
        # handles the first and would silently swallow the second — a site of
        # near-identical pages would produce no duplicate findings at all,
        # which is the opposite of what a duplication check is for.
        #
        # So the pages skipped for having nothing of their own are reported as
        # what they are: a template with the copy filled in. One finding per
        # page, not per pair — the pair form was C(n,2), so five identical
        # pages became ten findings for one problem. Per page it is linear,
        # it rates against the crawl like every other page-scoped check, and
        # "8 of 10 pages" costs what it should while "3 of 200" does not.
        if len(bare) >= BARE_PAGE_FLOOR:
            by_path = {f.path: f for f in substantial}
            for path in sorted(bare):
                page = by_path.get(path)
                out.append(Finding(
                    dimension=self.code, check_id="template-only-page",
                    severity=Severity.MEDIUM,
                    summary=f"{path} carries almost no text beyond the site "
                            f"template — fewer than {MIN_UNIQUE_SHINGLES} "
                            "distinct phrases of its own.",
                    subject=path,
                    affected_urls=[page.url] if page else [],
                    evidence={"unique_shingles":
                                  len(shingle_map.get(path, set())),
                              "min_unique_shingles": MIN_UNIQUE_SHINGLES,
                              "site_chrome_shingles": len(chrome)},
                    recommendation="Give the page substantive content of its "
                                   "own, or consolidate it — near-identical "
                                   "pages compete with each other and dilute "
                                   "crawl budget.",
                ))
        return out


registry.register(ContentModule())
