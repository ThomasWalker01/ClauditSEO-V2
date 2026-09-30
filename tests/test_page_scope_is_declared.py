"""Every dimension declares whether one page is a unit it can be measured in.

A page refresh re-reads one URL and re-measures one dimension against it. A
dimension none of whose checks can be measured that way cannot be cleared by
it, so `refresh_for` withholds the offer and `POST /api/sites/{id}/refresh`
refuses the call. The fact is declared per module as `measured_per_page` and
read by `registry.page_blind_dims`.

**Why this file enumerates the registry and parses each module's own source.**
`QUESTIONS.md` Q-17 chose this shape over a hand-kept tuple beside
`ANALYSIS_ONLY` for one reason: the tuple's guard is unwritable. A guard has to
check the declaration against what the modules actually emit, and the only
corpus in the tree is the sweep `tests/test_coverage.py` builds, which emits 0
page-naming PRF findings against 2 site-scoped while the operator's own
database holds 47 against 10. A guard derived from that fixture would certify
PRF as un-page-refreshable and pass. That is `KNOWN_ISSUES.md` KI-55, and it is
the promoted guard's-population invariant in its fixture spelling: a fixture
that cannot express the case the guard is written against is a population of
zero.

Reading the source instead has neither problem. It is not a sample, so it
cannot be unrepresentative, and it gets PRF right — five of its `Finding`
constructions carry a non-empty `affected_urls`.

**What the check can and cannot see, stated rather than left to be found.**
The signal is whether the module ever constructs a `Finding` with a non-empty
`affected_urls`. That over-approximates in one direction: `nap-inconsistent`
(LOC) lists pages while asserting a cross-page property, and
`ai-crawler-blocked` (TEC, re-homed from AIS at item 137) names
`crawl.start_url` while reading robots.txt — neither is really movable by
re-reading one page. It matters only for a module whose *every* page-naming
check is of that kind, and no module at HEAD is; LOC has a genuinely per-page
check besides, and TEC has many. Each module's declaration
argues its own case in a comment, and those comments are where a reader should
go — this file proves the declaration is not free-floating, not that the prose
above it is right.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import clauditseo.modules  # noqa: F401  (importing registers every dimension)
from clauditseo import anatomy as an
from clauditseo.engine import registry


def _page_naming_checks(cls) -> tuple[list[str], list[str]]:
    """The module's `Finding(...)` constructions, split by whether they name
    a page — `(page-naming check ids, site-scoped check ids)`.

    Parsed, not grepped, for the reason `tests/test_staging_depth.py` records
    against the same class of check: a substring search cannot tell a call
    from a sentence about a call, and every declaration added by Q-17 carries
    a comment naming `affected_urls` to explain itself.

    "Names a page" is `affected_urls` present and not a literal empty list.
    A module that omits the keyword entirely is site-scoped by the field's
    own `default_factory=list`.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    page: list[str] = []
    site: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name != "Finding":
            continue
        urls = None
        check = "<computed>"
        for kw in node.keywords:
            if kw.arg == "affected_urls":
                urls = kw.value
            elif kw.arg == "check_id" and isinstance(kw.value, ast.Constant):
                check = str(kw.value.value)
        empty = urls is None or (isinstance(urls, ast.List) and not urls.elts)
        (site if empty else page).append(check)
    return page, site


def _builtin_modules() -> dict:
    """Registered dimensions defined in this package — a toy module a gate-G3
    test registers is not this file's business, and `AuditModule` deliberately
    does not require this declaration so that G3's "one module file, zero
    changes to the registry" claim stays true."""
    return {code: m for code, m in registry.all_modules().items()
            if type(m).__module__.startswith("clauditseo.modules.")}


def test_every_dimension_declares_whether_a_page_can_move_it():
    """Declared outright, never defaulted.

    `coverage_from_crawl` defaults to True and can afford to: a dimension
    wrongly assumed crawl-derived costs a crawl that was going to be bought
    anyway. This one has no safe default in either direction — assuming True
    bills for a page fetch that cannot change anything, which is UX-39, and
    assuming False silently withdraws a working control. So the module says
    it, or this fails.
    """
    mods = _builtin_modules()
    assert mods, "no built-in dimension was registered"

    undeclared = [code for code, m in sorted(mods.items())
                  if "measured_per_page" not in vars(type(m))]
    assert not undeclared, (
        f"{', '.join(undeclared)} do not declare measured_per_page. It has no "
        "safe default: state it on the module, with the reason, beside "
        "coverage_from_crawl")


#: The one dimension for which "names a page" and "a page refresh can move
#: it" come apart, with why (brief v17 step AW).
#:
#: The rule below is a sound inference for eight dimensions: a finding
#: built with a page in `affected_urls` is a finding about that page, and
#: re-reading that page re-measures it. LNK is the first dimension whose
#: subject is the *graph*. Every one of its checks attributes its finding
#: to the pages it is about — which page nothing links to, which page is
#: four clicks from home, which page is behind a chain — and the answer to
#: every one of them lives in the OTHER pages. Re-fetching `/thin` cannot
#: change how many pages link to `/thin`; a one-page run would see a graph
#: of one page and report the whole site orphaned.
#:
#: So `measured_per_page = False` is right and the pages on the findings
#: are right, and this register is where the two are reconciled rather
#: than one of them being bent to satisfy the other. A second entry here
#: should be argued for, not added.
NAMES_PAGES_BUT_CANNOT_BE_MOVED_BY_ONE = {"LNK"}


def test_the_exception_is_the_declaration_it_claims_to_be():
    """The register above is only honest while both halves hold: the
    module declares False, and it does name pages. If either changes, the
    exemption is describing something that no longer exists."""
    for code in NAMES_PAGES_BUT_CANNOT_BE_MOVED_BY_ONE:
        module = _builtin_modules()[code]
        assert module.measured_per_page is False, code
        page, _site = _page_naming_checks(type(module))
        assert page, (
            f"{code} is exempted for naming pages while declaring False, and "
            "it no longer names any — drop the exemption")


def test_each_declaration_agrees_with_what_that_module_emits():
    """The declaration against the module's own source, not against a corpus.

    A module declaring True must construct at least one `Finding` carrying a
    non-empty `affected_urls`; a module declaring False must construct none.
    """
    mismatched = []
    for code, module in sorted(_builtin_modules().items()):
        if code in NAMES_PAGES_BUT_CANNOT_BE_MOVED_BY_ONE:
            continue
        page, site = _page_naming_checks(type(module))
        declared = getattr(module, "measured_per_page")
        if declared and not page:
            mismatched.append(
                f"{code}: declares measured_per_page=True but every one of its "
                f"{len(site)} findings is built with an empty affected_urls, so "
                "no page refresh can move any of them")
        if not declared and page:
            mismatched.append(
                f"{code}: declares measured_per_page=False but attributes "
                f"{len(page)} check(s) to a page ({', '.join(sorted(page))}), "
                "so a page refresh would move them")
    assert not mismatched, "; ".join(mismatched)


def test_prf_is_the_case_the_fixture_gets_wrong():
    """KI-55, kept as an assertion rather than as a note.

    The corpus reading of this fact certifies PRF un-page-refreshable; the
    source reading does not. If this ever fails, the guard has quietly become
    corpus-derived and KI-55 is live again.
    """
    page, _site = _page_naming_checks(type(registry.get("PRF")))
    assert page, (
        "PRF no longer attributes any finding to a page in its own source — "
        "check this against clauditseo/modules/prf.py before believing it, "
        "because the fixture has always said this and has always been wrong")
    assert registry.get("PRF").measured_per_page is True
    assert "PRF" not in registry.page_blind_dims()


def test_off_page_is_the_one_dimension_a_page_cannot_move():
    """The measurement behind the policy, kept so the count moving is noticed.

    Same shape as `test_staging_depth.py`'s crawl-blind assertion. The two
    sets are equal at HEAD and are not the same fact — if a later dimension
    makes them diverge, that is the divergence Q-17 split them for, and this
    is where it surfaces.
    """
    # LNK joined on 6 September 2026 (brief v17 step AW), and it is the
    # divergence this clause was split to notice: OFP cannot be moved by a
    # page because no page carries the measurement at all, LNK because its
    # measurement is about the graph between pages. Two dimensions, two
    # different reasons, one policy.
    blind = registry.page_blind_dims(list(_builtin_modules()))
    assert blind == {"OFP", "LNK"}, (
        f"the set of dimensions no page refresh can move has changed: "
        f"{sorted(blind)}. Re-read each module's measured_per_page comment "
        "before touching this guard")


def test_the_offer_reads_the_declaration_and_not_the_grouping():
    """`refresh_for`'s `per_page` is the declaration, section by section.

    The counter-assertion is the point: Q-17 rejected `Category.group`, and
    the sections below are the ones grouping would have silently withdrawn.
    """
    blind = registry.page_blind_dims()
    seen = 0
    for c in an.CATEGORIES:
        offer = an.refresh_for(c.key)
        if offer is None:
            continue
        seen += 1
        assert offer["per_page"] is (offer["dimension"] not in blind), (
            f"{c.key} covers {offer['dimension']} and its per_page reads "
            f"{offer['per_page']}")
    assert seen > 1, "the section list resolved to nothing"

    for key in ("ai-surface", "local"):
        assert an.refresh_for(key)["per_page"] is True, (
            f"{key} lost its page refresh — it sits beyond the site as a "
            "heading, and its module emits findings against page URLs")
