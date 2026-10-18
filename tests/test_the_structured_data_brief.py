"""The Structured data brief, its checks, and the inventory it reads
(brief v16 step AS).

One brief on the contract where a page-scoped auditor stood, twenty-two
checks registered at the severities its own prompt states, and twelve of
them answered mechanically from what the crawl already stored. Site-scoped,
because half of those twelve are questions about the run rather than about
a page: an `@id` is inconsistent only against the other pages' `@id`s.
"""

from __future__ import annotations

from clauditseo import briefs
from clauditseo.analysts.expert import (EXPERT_TOOLS, NOT_SET, SCHEMA_CHECKS,
                                        _structured_data_context, conforms,
                                        render_prompt)
from clauditseo.checks import default_severities
from clauditseo.crawler.evidence import profile_links, schema_inventory, snapshot
from clauditseo.crawler.types import CrawlResult, Page, Tier
from clauditseo.engine.types import Site
from clauditseo.modules.onp import OnPageModule
from clauditseo.modules.pagefacts import extract_facts

BASE = "https://entity.fixture"

ENTITY = ('{"@context":"https://schema.org","@graph":['
          '{"@type":"Organization","@id":"https://entity.fixture/#organization",'
          '"name":"Entity Co","url":"https://entity.fixture/",'
          '"logo":"https://entity.fixture/logo.svg",'
          '"sameAs":["https://facebook.com/entityco","https://yellowpages.com/entityco"]},'
          '{"@type":"WebSite","@id":"https://entity.fixture/#website",'
          '"publisher":{"@id":"https://entity.fixture/#nobody"}}]}')


def _page(url: str, blocks: str = "", body: str = "<h1>Page</h1>") -> Page:
    head = "".join(f'<script type="application/ld+json">{b}</script>'
                   for b in ([blocks] if isinstance(blocks, str) and blocks else []))
    return Page(url=url, requested_url=url, status=200, content_type="text/html",
                content=f"<html><head>{head}</head><body>{body}</body></html>")


def _site(**kw) -> Site:
    return Site(domain="entity.fixture", **kw)


# --- the registry and the prompt --------------------------------------------

def test_every_check_is_registered_at_the_prompts_own_severity():
    """The prompt states the defaults in its own severity note, and the
    registry is what the sweep and the brief both read. Two writings of a
    severity is two answers to how much a row weighs."""
    sev = default_severities()
    assert len(SCHEMA_CHECKS) == 23
    for check in SCHEMA_CHECKS:
        assert f"ONP/{check}" in sev, check
    for check in ("schema-invalid-json", "schema-deprecated-rich-result",
                  "schema-hidden-markup", "schema-id-inconsistent"):
        assert sev[f"ONP/{check}"] == "high", check
    for check in ("schema-sameas-missing", "schema-breadcrumb-missing",
                  "schema-entity-thin"):
        assert sev[f"ONP/{check}"] == "low", check
    # The two the prompt calls held are registered like any other, and the
    # note says why: a severity is what a row weighs when it is raised;
    # whether it may be raised at all is the parser's question.
    for check in ("schema-triple-mismatch", "schema-review-unsupported"):
        assert sev[f"ONP/{check}"] == "medium", check
    # INFO and not LOW (brief v16a step AT-a): an island is a reading of
    # the graph's shape, and whether a node adrift ought to be wired is a
    # judgement this brief makes rather than a defect the sweep found.
    assert sev["ONP/schema-island"] == "info", sev["ONP/schema-island"]


def test_the_prompt_loads_and_conforms_on_its_own_part():
    brief = briefs.by_id()["structured-data"]
    assert brief.part == "schema" and brief.scope == "site"
    assert len(brief.checks) == 23 and conforms("structured-data")
    assert EXPERT_TOOLS["structured-data"]["prompt"] == "structured-data.md"


def test_the_prompt_renders_with_every_placeholder_filled():
    """A brief handed `{{NAP}}` verbatim would ask the model to invent one.

    Driven against a site record that says nothing, because that is the
    state every site is in before an operator fills it, and the prompt's
    own rule is that an empty field takes a stated fallback rather than a
    blank.
    """
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2,
                        pages=[_page(BASE + "/", ENTITY)])
    text = render_prompt("structured-data",
                         _structured_data_context(snapshot(crawl), _site(), run_id="r1"))
    assert "{{" not in text, [ln for ln in text.split("\n") if "{{" in ln][:5]
    # The empty fields read as unset rather than as empty strings, and the
    # canonical @id the prompt asks for is proposed rather than left blank.
    assert NOT_SET in text
    assert "https://entity.fixture/#organization" in text


# --- the inventory ----------------------------------------------------------

def test_every_block_is_recorded_as_parsed_including_the_one_that_does_not():
    """A block that fails to parse *is* `schema-invalid-json`, so dropping
    it would delete the finding. It is kept with `parse_ok: false` and its
    own error."""
    blocks = schema_inventory([ENTITY, "{ not json"], ["rank-math-schema", ""])
    assert [b["type"] for b in blocks] == ["Organization", "WebSite", None]
    assert [b["parse_ok"] for b in blocks] == [True, True, False]
    assert blocks[2]["error"]
    # A `@graph` is several nodes in one script, and the checks are about
    # nodes: an orphan inside a graph is still an orphan.
    assert all(b["in_graph"] for b in blocks[:2])
    # The plugin names itself in the script's id, which is the difference
    # between "edit this JSON" and "change this setting".
    assert blocks[0]["source"] == "plugin:rank-math"
    assert blocks[2]["source"] == "inline"
    # Properties flattened far enough to reach what the checks read.
    assert blocks[0]["properties"]["name"] == "Entity Co"


def test_profile_links_are_candidates_and_never_a_claim_of_ownership():
    """Whether the entity *controls* a profile is what the site record
    answers, and the whole of `schema-sameas-misplaced` is that the two are
    different questions. The crawl can only say which links are there."""
    links = [{"href": "https://www.facebook.com/entityco"},
             {"href": "https://yellowpages.com.au/entityco"},
             {"href": "/about"}]
    assert profile_links(links) == ["https://www.facebook.com/entityco"]


# --- the twelve the sweep answers -------------------------------------------

def _swept(pages, site=None):
    return OnPageModule()._structured_data_checks(
        [extract_facts(p) for p in pages], site or _site())


def test_the_sweep_answers_the_checks_the_inventory_can_and_names_its_basis():
    pages = [_page(BASE + "/", ENTITY),
             _page(BASE + "/about", "{ broken")]
    site = _site(canonical_id="https://entity.fixture/#organization",
                 sameas_sources=["https://facebook.com/entityco"],
                 citation_sources=["https://yellowpages.com/entityco"],
                 page_types={"/": "home", "/about": "article"})
    found = _swept(pages, site)
    by = {}
    for f in found:
        by.setdefault(f.check_id, []).append(f)
    assert "schema-invalid-json" in by
    assert "schema-graph-wiring" in by
    assert "schema-sameas-misplaced" in by
    assert "schema-missing-for-type" in by
    assert "schema-breadcrumb-missing" in by
    for f in found:
        assert f.evidence.get("basis"), f.check_id
    # The reference that resolves nowhere names both ends.
    wiring = by["schema-graph-wiring"][0]
    assert wiring.evidence["target"] == "https://entity.fixture/#nobody"
    # And the misplaced profile is the one the record calls a citation.
    misplaced = by["schema-sameas-misplaced"][0]
    assert misplaced.evidence["in_citation_sources"] is True
    # An article page with no Article block, named as alternatives rather
    # than as a list of things it needs all of.
    missing = by["schema-missing-for-type"][0]
    assert "Article, BlogPosting or NewsArticle" in missing.summary, missing.summary


def test_a_site_whose_markup_is_in_order_raises_nothing():
    """The fixture's own fitness, asserted rather than assumed: a sweep
    that fired on everything would satisfy the clause above by accident."""
    good = ('{"@context":"https://schema.org","@graph":['
            '{"@type":"Organization","@id":"https://entity.fixture/#organization",'
            '"name":"Entity Co","url":"https://entity.fixture/",'
            '"logo":"https://entity.fixture/logo.svg"},'
            '{"@type":"WebSite","@id":"https://entity.fixture/#website",'
            '"publisher":{"@id":"https://entity.fixture/#organization"}}]}')
    site = _site(canonical_id="https://entity.fixture/#organization")
    assert _swept([_page(BASE + "/", good)], site) == []


def test_a_page_type_nobody_set_is_not_guessed_at():
    """`schema-missing-for-type` is about a page whose kind is known.

    The site root is the exception and it is a fact about the URL rather
    than an inference about content: the home page is the one every entity
    check turns on, and a site with no entity markup on it is a finding
    whatever the record says.
    """
    site = _site(canonical_id="https://entity.fixture/#organization")
    # No page type, no block, no finding about a missing type.
    assert not [f for f in _swept([_page(BASE + "/deep")], site)
                if f.check_id == "schema-missing-for-type"]
    # The home page with no block at all: that one is named.
    home = [f for f in _swept([_page(BASE + "/")], site)
            if f.check_id == "schema-missing-for-type"]
    assert len(home) == 1 and home[0].evidence["page_type"] == "home"


def test_an_entity_block_declaring_a_second_id_is_an_orphan_not_a_new_entity():
    """One entity, one canonical `@id`, referenced verbatim. A second node
    for one business is what `schema-orphan-instance` is, and it is the
    defect the whole brief is organised around."""
    second = ('{"@type":"LocalBusiness","@id":"https://entity.fixture/about#business",'
              '"name":"Entity Co"}')
    site = _site(canonical_id="https://entity.fixture/#organization")
    found = [f for f in _swept([_page(BASE + "/about", second)], site)
             if f.check_id == "schema-orphan-instance"]
    assert len(found) == 1
    assert found[0].evidence["canonical"] == "https://entity.fixture/#organization"
    assert found[0].evidence["id"] == "https://entity.fixture/about#business"


def test_an_entity_block_with_no_id_cannot_be_referenced_and_says_so():
    site = _site(canonical_id="https://entity.fixture/#organization")
    found = [f for f in _swept([_page(BASE + "/", '{"@type":"Organization","name":"X"}')], site)
             if f.check_id == "schema-id-inconsistent"]
    assert len(found) == 1 and "carries no @id" in found[0].summary


def test_the_home_pages_rule_means_the_entity_and_not_merely_a_block():
    """Read on Birch, whose home page carries one `WebSite` block and no
    `Organization` at all.

    The prompt's map asks the home page for three things - the entity, a
    WebSite and a WebPage - and accepting any of the three let that site
    pass the one check every other check turns on: with no entity node
    there is no canonical `@id`, so nothing can be inconsistent with it,
    orphaned from it, or thin against it, and the sweep raised nothing at
    all. The other two nodes are the brief's to ask for, because "this
    page has no WebPage node" is a judgement about what the page is.
    """
    site = _site()
    website_only = '{"@context":"https://schema.org/","@type":"WebSite","name":"Entity Co"}'
    found = [f for f in _swept([_page(BASE + "/", website_only)], site)
             if f.check_id == "schema-missing-for-type"]
    assert len(found) == 1
    assert "Organization or LocalBusiness" in found[0].summary, found[0].summary
    assert found[0].evidence["found"] == ["WebSite"]

    # And an entity node satisfies it, whatever else the page carries.
    org = '{"@context":"https://schema.org/","@type":"Organization","name":"Entity Co"}'
    assert not [f for f in _swept([_page(BASE + "/", org)], site)
                if f.check_id == "schema-missing-for-type"]


def test_the_inventory_is_importable_from_below_both_of_its_callers():
    """The sweep and the stored evidence both need it, and where it lived
    first closed a loop.

    `onp` imported `crawler.evidence`; `evidence` imports `modules.loc`;
    importing `modules` runs `modules/__init__`, which imports `onp`. It
    survived only because the app happens to import `onp` first, and it
    took the brief's first run down the moment anything imported
    `crawler.evidence` before `onp`. `pagefacts` is below both and imports
    neither, which is where the template rule already went for the same
    reason.

    Driven as an import in a fresh interpreter, because the defect is
    entirely about import order and a test running inside a process that
    has already imported everything cannot see it.
    """
    import subprocess
    import sys

    got = subprocess.run(
        [sys.executable, "-c",
         "from clauditseo.crawler.evidence import snapshot; "
         "import clauditseo.modules.onp; print('ok')"],
        capture_output=True, text=True, timeout=120)
    assert got.returncode == 0, got.stderr[-800:]


def test_a_visible_nap_mention_is_a_row_and_the_context_reads_its_value():
    """`nap_mentions` holds `{"value", "context"}`, and joining those as
    if they were strings is what took the brief's first run down with
    `sequence item 0: expected str instance, dict found`."""
    from clauditseo.analysts.expert import _nap_line

    assert _nap_line({"nap_mentions": [{"value": "03 9123 4567",
                                        "context": "Call us on 03 9123 4567"}]}) \
        == "03 9123 4567"
    assert _nap_line({}) == ""


def test_the_two_verdicts_survive_being_stored():
    """A field the parser fills and `as_dict` drops exists only in memory.

    Found on the brief's first successful run against Birch: the parse
    read `eligibility` and `entity` off the model's block, and the stored
    contract carried neither, so the UI would have had nothing to render
    above the fixes.
    """
    import json

    from clauditseo.analysts import contract

    block = json.dumps({
        "rows": [],
        "eligibility": [{"page": "/", "rich_result": "Article",
                         "verdict": "ELIGIBLE BUT DEGRADED", "reason": "no author"}],
        "entity": {"verdict": "FRAGMENTED", "reason": "two @id values for one name"}})
    got = contract.parse("```json\n" + block + "\n```\n", ["ONP/schema-invalid-json"],
                         [BASE + "/"])
    assert got.eligibility[0]["verdict"] == "ELIGIBLE BUT DEGRADED"
    assert got.entity["verdict"] == "FRAGMENTED"
    stored = got.as_dict()
    assert stored["eligibility"] == got.eligibility
    assert stored["entity"] == got.entity


# --- AT: the part page ------------------------------------------------------

def test_structured_data_supplies_two_renderers_and_forks_nothing():
    """The layout is AO's and stays one. Four parts render as three blocks
    now, and one `PartPage` and one `FixCard` serve all of them."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    part_page = (src / "part_page.tsx").read_text(encoding="utf-8")
    defs = {"PartPage": 0, "FixCard": 0}
    for path in src.glob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        for name in defs:
            defs[name] += text.count(f"function {name}(")
    assert defs == {"PartPage": 1, "FixCard": 1}, defs
    assert part_page.count("PART_RENDERERS: Record<string, Renderer>") == 1
    # Item 242 added the site-scope slot; the renderers are still its own.
    assert "schema: { now: SchemaNow, siteNow: SchemaSiteNow, body: SchemaFixBody" in part_page
    assert '"title-desc"' in part_page and "headings:" in part_page and "images:" in part_page


def test_a_content_first_row_has_nothing_to_copy_and_says_why():
    """`kind: content-first` is a row about something the page does not
    say. There is no markup to paste until the content exists, so the card
    shows none - a copy button over an empty panel would be an operator
    pasting nothing into their CMS and believing they had fixed it."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    body = src[src.index("function SchemaFixBody"):src.index("export const PART_RENDERERS")]
    assert 'fix.kind === "content-first"' in body
    first = body[body.index('fix.kind === "content-first"'):]
    assert "Nothing to paste yet" in first[:900], first[:400]
    # And the copy button is `FixCard`'s, which only renders one where a
    # replacement exists - so this branch reaching it at all is the thing
    # the clause is about.
    card = src[src.index("function FixCard"):src.index("export function templateOf")]
    assert "fix.replacement" in card


def test_the_plain_names_cover_every_check_the_brief_may_emit():
    """A check id is the engine's name for a thing and a plain name is the
    operator's. One missing means one card headed by a slug."""
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    named = set(re.findall(r'"(schema-[a-z-]+)":\s*"', src))
    assert set(SCHEMA_CHECKS) <= named, sorted(set(SCHEMA_CHECKS) - named)


def test_a_block_the_site_repeats_is_one_block_and_says_how_many_pages():
    """The same rule the images use, on `@type` + `@id` (brief v16 step
    AS). An Organization node on twelve pages is one node and one card;
    counting the pages instead would offer twelve edits for one."""
    from clauditseo.modules.pagefacts import block_key, mark_template_blocks

    org = {"type": "Organization", "id": "https://entity.fixture/#organization",
           "source": "inline"}
    art = {"type": "Article", "id": "https://entity.fixture/a#article",
           "source": "inline"}
    pages = [[dict(org)], [dict(org), dict(art)], [dict(org)]]
    mark_template_blocks(pages)
    assert [b["template"] for b in pages[1]] == [True, False]
    assert pages[0][0]["pages"] == 3 and pages[1][1]["pages"] == 1
    # An `@id` is the identity where there is one; where there is not, the
    # type and the source are as near as the markup gets.
    assert block_key(org) == "Organization|https://entity.fixture/#organization|"
    assert block_key({"type": "WebPage", "source": "plugin:yoast"}) == "WebPage||plugin:yoast"


# --- what the render rules settled (brief v16a step AT-a) ------------------

def _prompt() -> str:
    from clauditseo import briefs
    return briefs.by_id()["structured-data"].path.read_text(encoding="utf-8")


def test_the_island_definition_is_the_one_the_picture_draws():
    """Two writings of "island" would be two answers about the same node,
    and the earlier one - a top-level node nothing points at - calls the two
    healthiest nodes in the design pack islands, because their references
    come from inside themselves."""
    text = _prompt()
    assert "ONP/schema-island" in text, "the check is not in the prompt's set"
    assert "different* top-level node" in text, text[:0] or "definition absent"
    for excluded in ("own nested definitions", "inline copy"):
        assert excluded in text, excluded
    assert "Self-" in text, "self-references are not named as excluded"

    # And the engine agrees, on the fixtures the rules were written against.
    import json
    from pathlib import Path

    from clauditseo import schema_graph as sg
    ex = (Path(__file__).resolve().parent / "fixtures" / "schema_examples"
          / "2_rich_but_fragmented.json")
    model = sg.build_model([{"source": "inline", "json": json.loads(
        ex.read_text(encoding="utf-8"))}], None,
        {"host": "summit-roofing-fixture.com.au", "page": "/", "page_type": "home"}, [])
    assert sorted(n.types[0] for n in model.nodes if n.island) == [
        "FAQPage", "ItemList"]


def test_eligibility_has_a_fourth_verdict_for_a_page_that_targets_nothing():
    """A home page targets no rich result. With three verdicts the prompt
    has to call that "not eligible", which is a different claim - one says
    the page asked and was refused, the other that it never asked."""
    text = _prompt()
    assert "NONE TARGETED" in text, "the fourth verdict is not offered"
    assert "reads as \"not assessed\"" in text, (
        "the prompt does not say that leaving such a page out is not the "
        "same as saying it targets nothing")
    from clauditseo import schema_graph as sg
    assert "none targeted" in sg.ELIGIBILITY_VERDICTS


def test_the_entity_verdict_is_decided_in_a_stated_order():
    """Three verdicts and five conditions is ambiguous unless the order is
    written down: a page with both an inline copy and a dangling reference
    is UNIDENTIFIED, not FRAGMENTED, and the reason has to say which
    condition decided it."""
    text = _prompt()
    # After the marker, not from the start of the sentence: the three names
    # appear first as an unordered enumeration of what the field may hold,
    # and reading the order off that would pass on a prompt that states no
    # order at all.
    body = text[text.index("decided in this order"):]
    body = body[:body.index("Both are read by the UI")]
    assert body.index("UNIDENTIFIED") < body.index("FRAGMENTED") < body.index(
        "CONSOLIDATED"), body
    assert "copy of it exists" in body, body
    assert "WebPage.about" in body, body


def test_only_two_conditions_may_be_drawn_as_absent():
    """The reference mockups drew a Service ghost for one site and
    FinancialService for another. Those are findings about the entity's type
    or about other pages, and drawing them in the "not on the page" zone
    makes the picture say the page-type map expected something it did not."""
    text = _prompt()
    assert "not on the page" in text, text[:0] or "the zone is not described"
    assert "footer-places case" in text, "the second condition is unnamed"
    assert "pinned to the entity and is never an" in text, (
        "the prompt does not say where a type finding goes instead")

