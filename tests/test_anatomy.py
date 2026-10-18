"""The page-anatomy lens.

The property that matters most is that it is a *lens*: it re-sorts findings
without inventing or losing any. Two screens in this app once reported 359
and 360 for the same metric because each counted independently. A category
tree that does not sum to the total would be that bug again, larger.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from clauditseo import anatomy
from clauditseo.playbook import PLAYBOOK

MODULES = pathlib.Path(__file__).resolve().parents[1] / "clauditseo" / "modules"


def _raised_checks() -> set[str]:
    out: set[str] = set()
    for f in MODULES.glob("*.py"):
        out |= set(re.findall(r'check_id="([a-z0-9-]+)"', f.read_text(encoding="utf-8")))
    # Raised outside modules/, from the playbook's declared schema set.
    for ph in PLAYBOOK:
        for t in ph["tools"]:
            out |= set(t.get("checks", []))
    return out


# ---- completeness ----------------------------------------------------------

def test_every_check_the_suite_can_raise_has_a_category():
    """A new check must be filed deliberately. Without this it would land in
    `workflow` and quietly vanish from the tree an operator reads."""
    missing = sorted(c for c in _raised_checks()
                     if c not in anatomy.CHECK_CATEGORY
                     and not c.startswith("axe-"))
    assert not missing, ("checks with no category — add them to "
                         f"anatomy.CHECK_CATEGORY: {missing}")


def test_every_tool_has_a_category():
    """Item 238: except the tools the operator placed under no part, which
    are named, and named nowhere else."""
    ids = {t["id"] for ph in PLAYBOOK for t in ph["tools"]}
    missing = sorted(ids - set(anatomy.TOOL_CATEGORIES) - anatomy.UNPLACED_TOOLS)
    assert not missing, f"tools with no category: {missing}"
    assert not anatomy.UNPLACED_TOOLS & set(anatomy.TOOL_CATEGORIES)


def test_no_category_is_declared_and_then_never_used():
    used = set(anatomy.CHECK_CATEGORY.values()) | {c for cats in anatomy.TOOL_CATEGORIES.values() for c in cats}
    used |= {c for _, c in anatomy.CHECK_PREFIX_CATEGORY}
    declared = set(anatomy.BY_KEY)
    assert not (used - declared), f"categories used but not declared: {used - declared}"
    assert not (declared - used), f"categories declared but empty: {declared - used}"


def test_every_category_names_at_least_one_tool_to_run():
    """A category an operator can select but not act on is a dead end."""
    for cat in anatomy.CATEGORIES:
        # Item 238: `workflow` is not a part - the catch-all and the engine's
        # run-notes - and no screen lets an operator select it.
        if cat.key == "workflow":
            continue
        assert anatomy.tools_for(cat.key), f"{cat.key} has no tool behind it"


# ---- placement -------------------------------------------------------------

@pytest.mark.parametrize("check_id,dimension,expect", [
    ("title-length", "ONP", "title-desc"),
    ("heading-skip", "ONP", "headings"),
    ("img-alt-missing", "ONP", "images"),
    ("duplicate-content", "CNT", "content"),
    ("html-lang-missing", "A11Y", "a11y"),
    # Security & transport's own dimension since item 143 step BD.
    ("hsts", "SEC", "security"),
    ("nap-missing", "LOC", "local"),
    # axe rule ids move with upstream, so they match by prefix.
    ("axe-color-contrast", "A11Y", "a11y"),
    ("axe-some-rule-invented-in-2027", "A11Y", "a11y"),
    # expert findings carry a model-written code and are placed by tool.
    # A brief's own finding lands in the part its header names (brief v10
    # step AD): crawl writes to Crawl. (js-rendering was the example here
    # until it retired at item 165.)
    ("robots-meta-absent", "EXP:crawl", "crawl"),
    ("schema-placeholder-address", "EXP:gbp-audit", "local"),
    ("whatever-the-model-called-it", "EXP:content-substance", "content"),
])
def test_findings_land_where_an_operator_would_look(check_id, dimension, expect):
    assert anatomy.categorise(check_id, dimension) == expect


def test_a_sweep_spanning_categories_is_split_by_check_not_by_tool():
    """The Images brief raises the image checks; the sweep raises them and
    by tool would put all three under one heading, which is the reason
    CHECK_CATEGORY exists at all."""
    # Images since brief v11 step AJ; Headings is `headings`'s and Title &
    # description is `title-desc`'s.
    assert anatomy.TOOL_CATEGORIES["images"][0] == "images"
    assert anatomy.TOOL_CATEGORIES["title-desc"] == ("title-desc",)
    assert anatomy.TOOL_CATEGORIES["headings"] == ("headings",)
    assert anatomy.categorise("heading-skip", "ONP") == "headings"
    assert anatomy.categorise("img-alt-missing", "ONP") == "images"


def test_an_expert_finding_is_split_by_check_too():
    """The same rule has to hold for briefs, and did not. A brief that
    spans three categories, so placing its findings by tool sent every one of
    them to the first — an image finding written by the brief appeared under
    "Title & description", beside the title facts, describing images.

    Filing by tool is only a fallback for a check id we do not recognise."""
    assert anatomy.categorise("img-alt-missing", "EXP:images") == "images"
    assert anatomy.categorise("heading-skip", "EXP:images") == "headings"
    assert anatomy.categorise("title-length", "EXP:images") == "title-desc"
    # Unrecognised code: the tool is all we have to go on - and the tool's
    # part is Images since brief v11 step AJ.
    assert anatomy.categorise("model-made-this-up",
                              "EXP:images") == "images"


def test_every_category_holds_only_findings_that_belong_to_it():
    """The screen-level guarantee, not just the function's. A finding filed
    under a category whose facts panel describes something else is worse than
    an uncategorised one: it looks answered."""
    for check_id, category in anatomy.CHECK_CATEGORY.items():
        for dimension in ("ONP", "TEC", "EXP:images", "EXP:gbp-audit"):
            assert anatomy.categorise(check_id, dimension) == category


def test_an_unknown_finding_is_filed_rather_than_dropped():
    assert anatomy.categorise("brand-new-check", "TEC") == "workflow"
    assert anatomy.categorise("x", "EXP:unheard-of-tool") == "workflow"


def test_accessibility_does_not_claim_checks_that_have_a_home():
    """Both are accessibility failures, and both are counted elsewhere.
    Claiming them here would double the total."""
    assert anatomy.categorise("img-alt-missing", "ONP") != "a11y"
    assert anatomy.categorise("heading-skip", "ONP") != "a11y"


# ---- the lens property -----------------------------------------------------

def test_categories_partition_the_findings_and_sum_to_the_total():
    findings = [
        ("title-length", "ONP"), ("title-length", "ONP"),
        ("heading-skip", "ONP"), ("img-alt-missing", "ONP"),
        ("duplicate-content", "CNT"), ("hsts", "SEC"),
        ("axe-color-contrast", "A11Y"), ("anything", "EXP:content-substance"),
    ]
    counts: dict[str, int] = {}
    for cid, dim in findings:
        counts[anatomy.categorise(cid, dim)] = counts.get(anatomy.categorise(cid, dim), 0) + 1
    assert sum(counts.values()) == len(findings), "a finding was lost or duplicated"


def test_a_finding_belongs_to_exactly_one_category():
    for cid, dim in [("img-alt-missing", "ONP"), ("axe-color-contrast", "A11Y")]:
        hits = [c.key for c in anatomy.CATEGORIES
                if anatomy.categorise(cid, dim) == c.key]
        assert len(hits) == 1


# ---- co-occurrence ---------------------------------------------------------

def test_jaccard_matches_the_real_shape_of_a_templated_site():
    hundred = {f"/p{i}" for i in range(100)}
    assert anatomy.jaccard(hundred, set(hundred)) == 1.0
    assert round(anatomy.jaccard(hundred, hundred - {"/p0"}), 2) == 0.99
    assert anatomy.jaccard(hundred, set()) == 0.0


def test_containment_alone_would_light_up_the_whole_tree():
    """The reason for Jaccard rather than 'is A inside B'. On a templated
    site every small category sits wholly within the big one; twelve of
    twelve title-length pages were inside the hundred-page heading problem
    in real data. Containment would call that related. It is not."""
    template = {f"/p{i}" for i in range(100)}
    small = {f"/p{i}" for i in range(12)}
    assert small < template                       # fully contained
    assert anatomy.jaccard(template, small) < anatomy.RELATED_AT


def test_related_reports_why_not_just_that():
    pages = {
        "headings": {f"/p{i}" for i in range(100)},
        "images": {f"/p{i}" for i in range(100)},
        "content": {f"/p{i}" for i in range(1, 100)},
        "title-desc": {f"/p{i}" for i in range(12)},
    }
    rel = anatomy.related(pages, "headings")
    assert set(rel) == {"images", "content"}, "title-desc is a subset, not a cause"
    assert rel["images"]["jaccard"] == 1.0
    assert rel["images"]["shared"] == 100
    assert rel["content"]["shared"] == 99


def test_related_is_symmetric():
    pages = {"a": {"/1", "/2", "/3"}, "b": {"/1", "/2", "/3"}}
    assert "b" in anatomy.related(pages, "a")
    assert "a" in anatomy.related(pages, "b")


def test_related_is_empty_when_nothing_is_selected_or_nothing_overlaps():
    pages = {"a": {"/1"}, "b": {"/2"}}
    assert anatomy.related(pages, "a") == {}
    assert anatomy.related(pages, "missing") == {}


# ---- the query and endpoint ------------------------------------------------

def _seeded(tmp_path):
    """A site whose findings deliberately span three categories on the same
    pages, plus one that is elsewhere."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Finding, Severity, Site, Tier
    conn = connect(tmp_path / "a.db"); migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Co"), "x.test")
    run = runs.create_run(conn, site, ["ONP"], "T2")
    shared = [f"https://x.test/p{i}" for i in range(10)]
    found = [
        Finding(dimension=dim, check_id=cid, severity=Severity.MEDIUM,
                summary=f"{cid} here", subject=cid, affected_urls=urls, evidence={})
        for cid, dim, urls in (("heading-skip", "ONP", shared),
                               ("img-alt-missing", "ONP", shared),
                               ("title-length", "ONP", shared[:2]),
                               ("hsts", "SEC", ["https://x.test/"]))
    ]
    runs.complete_run(conn, run, AuditResult(
        site=Site(domain="https://x.test/"), tier=Tier.T2,
        dimensions=["ONP", "TEC", "SEC"], findings=found))
    return conn, site


def test_the_query_sums_to_the_findings_it_was_given(tmp_path):
    from clauditseo.persistence.runs import anatomy_view
    conn, site = _seeded(tmp_path)
    v = anatomy_view(conn, site)
    assert v["total"] == 4
    # `["value"]`: `Category`'s three findings counts carry their population
    # since item 156, and this is arithmetic over them rather than a render.
    by = {c["key"]: c["total"]["value"] for c in v["categories"]}
    assert by["headings"] == 1 and by["images"] == 1
    assert by["title-desc"] == 1 and by["security"] == 1
    conn.close()


def test_co_occurrence_finds_the_shared_template(tmp_path):
    from clauditseo.persistence.runs import anatomy_view
    conn, site = _seeded(tmp_path)
    rel = anatomy_view(conn, site)["related"]
    assert "images" in rel["headings"], "identical page sets must relate"
    assert rel["headings"]["images"]["jaccard"] == 1.0
    assert "title-desc" not in rel["headings"], \
        "2 of 10 pages is a subset, not a shared cause"
    assert "security" not in rel["headings"]
    conn.close()


def test_a_page_filter_narrows_the_counts_and_switches_off_co_occurrence(tmp_path):
    """On one page every category shares that page, so the signal would fire
    everywhere. Better to withhold it than to show something meaningless."""
    from clauditseo.persistence.runs import anatomy_view
    conn, site = _seeded(tmp_path)
    v = anatomy_view(conn, site, page_url="https://x.test/p0")
    # `["value"]`: `Category`'s three findings counts carry their population
    # since item 156, and this is arithmetic over them rather than a render.
    by = {c["key"]: c["total"]["value"] for c in v["categories"]}
    assert by["headings"] == 1 and by["images"] == 1 and by["title-desc"] == 1
    assert by["security"] == 0, "that finding is on a different page"
    assert v["total"] == 3
    assert v["related"] == {}
    conn.close()


def test_the_default_dimensions_include_every_registered_one():
    """A scheduled pass sends no dimensions, so it gets this default. A
    dimension missing from it never runs unattended — which is how the
    accessibility checks sat idle after being built."""
    import clauditseo.modules  # noqa: F401  (registers them)
    from clauditseo.api.app import AuditIn
    from clauditseo.engine import registry
    missing = sorted(set(registry.all_modules()) - set(AuditIn().dims))
    assert not missing, (
        f"registered but never run by default: {missing} — a scheduled audit "
        "sends no dims and would skip them")


# --- the launcher's vocabulary must match this screen's --------------------

def _module_checks() -> dict[str, set[str]]:
    """Every check id each dimension's module can emit, read from source."""
    import re
    from pathlib import Path
    out: dict[str, set[str]] = {}
    for path in (Path(__file__).resolve().parents[1]
                 / "clauditseo" / "modules").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        code = re.search(r'^\s+code = "(\w+)"', src, re.M)
        if not code:
            continue
        out.setdefault(code.group(1), set()).update(
            re.findall(r'check_id="([a-z0-9-]+)"', src))
    # A module that declares its checks is read rather than scraped: LNK
    # raises all eight through one helper, so the regex finds none of them
    # (brief v17 step AW). `sweep_checks()` needed the same thing and is
    # where the rule lives; this reads it rather than keeping a second.
    from clauditseo.checks import _registries
    for code, table, only in _registries():
        out.setdefault(code, set()).update(c for c in table if c not in only)
    return out


def test_dimension_categories_matches_what_the_modules_emit():
    """The launcher tells an operator which sections a dimension refreshes.
    If a check moves category and this table does not, the launcher makes a
    promise the audit does not keep — so it is declared and then held to what
    the modules actually raise."""
    for dim, checks in _module_checks().items():
        # Through `categorise`, which is the product's own rule: one check
        # id can belong to two dimensions and mean two things - TEC's
        # `redirect-chain` is about reaching a page and is filed with the
        # crawl, LNK's is about a link that points through a chain (brief
        # v17 step AW) - and the bare key cannot hold both.
        actual = {anatomy.categorise(c, dim) for c in checks
                  if anatomy.categorise(c, dim) != "workflow"}
        declared = set(anatomy.DIMENSION_CATEGORIES.get(dim, ()))
        assert declared == actual, (
            f"{dim} raises {sorted(actual)} but DIMENSION_CATEGORIES says "
            f"{sorted(declared)}")


def test_analysis_only_categories_really_have_no_sweep():
    """Three sections are filled by an analysis or not at all, and the
    launcher says so — running every dimension leaves them untouched. If a
    sweep ever starts covering one, that sentence becomes a lie."""
    covered = {cat for cats in anatomy.DIMENSION_CATEGORIES.values()
               for cat in cats}
    for key in anatomy.ANALYSIS_ONLY:
        assert key in anatomy.BY_KEY, f"{key} is not a category"
        assert key not in covered, (
            f"{key} is now covered by a sweep — the launcher's "
            "'no sweep covers this' note is no longer true")


def test_every_category_is_either_swept_or_declared_analysis_only():
    """No third state: a category is refreshed by a dimension, or it is named
    as one nothing sweeps. Anything else would sit on the client screen with
    a zero that means neither 'clean' nor 'unlooked-at'."""
    covered = {cat for cats in anatomy.DIMENSION_CATEGORIES.values()
               for cat in cats}
    for cat in anatomy.CATEGORIES:
        if cat.group == anatomy.WORKFLOW:
            continue
        assert cat.key in covered or cat.key in anatomy.ANALYSIS_ONLY, (
            f"{cat.key} is neither swept by a dimension nor declared "
            "analysis-only")
