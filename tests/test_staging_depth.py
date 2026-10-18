"""Which dimensions a deeper crawl can actually help.

`staging.plan` splits two claims that used to be one: "this score is not a
measurement" and "look harder". The second costs money — up to 100 pages at
T2 against a client site — so it may only be made for a dimension whose
coverage a crawl can obtain.

The property is declared per module as `coverage_from_crawl` and read by
`registry.crawl_blind_dims`. A declaration nobody checks is how the next
provider-derived dimension would inherit round 046's defect silently, so
this file enumerates the registry rather than naming dimensions: it reads
each registered module's own source and asserts the declaration agrees with
whether that module derives its coverage from `scoring.page_coverage`.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import clauditseo.modules  # noqa: F401  (importing registers every dimension)
from clauditseo.engine import registry, staging


def _calls_page_coverage(cls) -> bool:
    """Whether this module's own code calls `scoring.page_coverage`.

    Parsed, not grepped. The first version of this check was a substring
    search over `inspect.getsource`, and it failed on the one module it was
    written for: OFP's declaration carries a comment naming `page_coverage`
    to say it is *not* used, and a substring search cannot tell a call from a
    sentence about a call. That is the same class of defect as CQ-55, in the
    guard written to prevent this one.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name == "page_coverage":
            return True
    return False


def _builtin_modules() -> dict:
    """Registered dimensions defined in this package — a toy module a gate-G3
    test registers is not this file's business."""
    return {code: m for code, m in registry.all_modules().items()
            if type(m).__module__.startswith("clauditseo.modules.")}


def test_every_dimension_declares_where_its_coverage_comes_from():
    """The declaration is checked against the module's own source, not against
    a list kept beside it. `page_coverage` in the scoring path means a deeper
    crawl raises the number; its absence means nothing about the crawl can."""
    mods = _builtin_modules()
    assert mods, "no built-in dimension was registered"

    mismatched = []
    for code, module in sorted(mods.items()):
        page_derived = _calls_page_coverage(type(module))
        declared = getattr(module, "coverage_from_crawl", True)
        if page_derived != declared:
            mismatched.append(
                f"{code}: declares coverage_from_crawl={declared} but its "
                f"source {'does' if page_derived else 'does not'} call "
                f"page_coverage")
    assert not mismatched, "; ".join(mismatched)


def test_ofp_is_the_dimension_no_crawl_can_cover():
    """The measurement behind the policy, stated as a number rather than
    inherited. If a second dimension ever joins OFP here, the planner change
    it needs is already written — but the count moving is worth noticing."""
    blind = registry.crawl_blind_dims(list(_builtin_modules()))
    assert blind == {"OFP"}, (
        f"the set of dimensions no crawl can cover moved: {sorted(blind)}")


def test_crawl_blind_dims_answers_for_a_subset_and_ignores_unknown_codes():
    """`run_adaptive` passes the run's own dimension list, which routinely
    omits OFP and may name a code that is not registered."""
    assert registry.crawl_blind_dims(["TEC", "ONP"]) == set()
    assert registry.crawl_blind_dims(["TEC", "OFP"]) == {"OFP"}
    assert registry.crawl_blind_dims([]) == set()
    assert registry.crawl_blind_dims(["NOPE"]) == set()


# --------------------------------------------------------------------------
# WF-53 / WF-54 — the per-module half above answers "can any crawl obtain this
# dimension's coverage". It cannot answer "can *this run's* deeper crawl obtain
# it", and that is where the surviving cost regression lives: a T1 crawl that
# fetched no eligible page leaves every page-derived dimension uncovered, all
# of them declared crawl-obtainable, and a T2 crawl of the same site repeats
# the same refusal. The depth decision therefore belongs to the run.

CFG = staging.StagingConfig.from_env()

#: Run 93bdd2b2's own stored subscores: five applicable dimensions, each
#: coverage 0.0 and score 100.0, because the crawl fetched nothing. Named
#: rather than invented — three of eleven stored runs are `blocked`, and this
#: is what the planner is handed on one of them.
_BLOCKED_RUN_SCORES = {d: 100.0 for d in ("AIS", "CNT", "LOC", "ONP", "PRF")}


def test_a_crawl_that_fetched_nothing_does_not_buy_a_deeper_one():
    """Measured at HEAD before this guard existed: all five escalate at WATCH
    with `buys_depth=True` and `escalated_tier` returns "T2" — a second,
    larger crawl bought on the strength of five fabricated 100.0s, against a
    site that just refused the first one.

    They must still escalate. The absence is real and the operator has to be
    told; what it may not do is spend.
    """
    esc = staging.plan(_BLOCKED_RUN_SCORES, set(), set(),
                       set(_BLOCKED_RUN_SCORES), set(), None, CFG,
                       crawl_obtained_pages=False)

    assert set(esc) == set(_BLOCKED_RUN_SCORES), "the absences must be reported"
    assert all(e.band is staging.Band.WATCH for e in esc.values())
    assert not any(e.buys_depth for e in esc.values())
    assert staging.escalated_tier(esc) is None, (
        "a crawl that fetched nothing bought a second one")
    assert all(any("fetched no eligible page" in r for r in e.reasons)
               for e in esc.values()), "and it must say which absence this is"


def test_the_same_absence_does_buy_depth_when_the_crawl_did_reach_the_site():
    """The other side of the same argument, so the guard cannot be satisfied
    by never buying depth at all. Identical inputs, one eligible page
    obtained: a deeper crawl can plausibly raise page-derived coverage, so it
    is bought.
    """
    esc = staging.plan(_BLOCKED_RUN_SCORES, set(), set(),
                       set(_BLOCKED_RUN_SCORES), set(), None, CFG,
                       crawl_obtained_pages=True)

    assert all(e.buys_depth for e in esc.values())
    assert staging.escalated_tier(esc) == "T2"


def test_an_override_does_not_buy_a_crawl_that_still_cannot_obtain_coverage():
    """WF-54. Both overrides used to set `buys_depth = True` unconditionally,
    which bought the exact crawl the module-level rule had just refused —
    one path over, on the same dimension.

    The override is still right to lift the band: a regression and a critical
    finding are evidence. What it cannot do is make a futile crawl useful.
    OFP's coverage comes from backlink providers and `paid_provider_dims`
    authorises those only at CRITICAL; neither override reaches CRITICAL from
    WATCH, so the crawl each would buy still reads no backlink signal.
    """
    regressed = staging.plan({"OFP": 100.0}, {"OFP"}, set(), {"OFP"}, {"OFP"},
                             None, CFG, crawl_obtained_pages=True)
    assert regressed["OFP"].band is staging.Band.CONCERN, "still escalated"
    assert not regressed["OFP"].buys_depth
    assert staging.escalated_tier(regressed) is None
    assert staging.paid_provider_dims(regressed) == set(), (
        "the band that would make the crawl useful is the one it never reaches")

    critical = staging.plan({"OFP": 100.0}, set(), {"OFP"}, {"OFP"}, {"OFP"},
                            None, CFG, crawl_obtained_pages=True)
    assert critical["OFP"].band is staging.Band.CONCERN
    assert not critical["OFP"].buys_depth
    assert staging.escalated_tier(critical) is None

    # And the override still restores depth where depth can deliver: a
    # page-derived dimension, on a run whose crawl did reach the site.
    live = staging.plan({"CNT": 100.0}, {"CNT"}, set(), {"CNT"}, set(),
                        None, CFG, crawl_obtained_pages=True)
    assert live["CNT"].buys_depth
    assert staging.escalated_tier(live) == "T2"


def test_the_stored_reason_does_not_survive_the_override_that_reverses_it():
    """The depth decision is made once, from the settled band, so a reason
    explaining why depth was refused is written only when it was.

    Measured at HEAD before this guard: a regressed OFP carried both "no
    crawl can obtain it, so this alone does not buy a deeper crawl" and
    "regression override", with `buys_depth=True` — the stored note told the
    operator depth was refused on the run that bought it.
    """
    reg = staging.plan({"OFP": 100.0}, {"OFP"}, set(), {"OFP"}, {"OFP"},
                       None, CFG, crawl_obtained_pages=True)
    assert any("regression override" in r for r in reg["OFP"].reasons)
    assert not reg["OFP"].buys_depth
    assert any("no crawl can obtain it" in r for r in reg["OFP"].reasons), (
        "depth was refused, so the note must say so")

    live = staging.plan({"CNT": 100.0}, {"CNT"}, set(), {"CNT"}, set(),
                        None, CFG, crawl_obtained_pages=True)
    assert live["CNT"].buys_depth
    assert not any("does not buy a deeper crawl" in r
                   for r in live["CNT"].reasons), (
        "depth was bought, so no reason may claim it was refused")


def test_a_run_that_obtained_nothing_buys_no_tier_no_analyst_no_provider():
    """WF-55 and CQ-91. `buys_depth` is computed correctly and then ignored by
    all three functions that spend money on a band.

    Measured at HEAD before this guard: this exact call returns ONP at
    CRITICAL with `buys_depth=False` and the reason "and this run's crawl
    fetched no eligible page, so a deeper crawl of the same site would repeat
    the refusal rather than obtain it" — and then `escalated_tier` returns
    "T3", `paid_provider_dims` returns `{'ONP'}` and `analyst_tasks` returns
    `['PRI-J', 'ONP-J']`. The most expensive outcome the planner can produce,
    on a run that obtained nothing, with the refusal written into its own
    stored note.

    Reachable without contrivance: `tec.py` raises CRITICAL for any page
    status >= 500 and a 500 is not eligible, so a site returning 500s yields
    a dimension both uncovered and critical in one pulse; the regression half
    comes from stored `finding_states` on a repeat client.
    """
    esc = staging.plan({"ONP": 100.0}, {"ONP"}, {"ONP"}, {"ONP"}, set(),
                       None, CFG, crawl_obtained_pages=False)

    assert esc["ONP"].band is staging.Band.CRITICAL, "the premise: both overrides fired"
    assert not esc["ONP"].buys_depth
    assert staging.escalated_tier(esc) is None, (
        "a crawl that fetched nothing bought the deepest tier")
    assert staging.paid_provider_dims(esc) == set(), (
        "a paid provider call authorised by an absence")
    assert staging.analyst_tasks(esc) == [], (
        "two model tasks commissioned on the strength of an absence")


def test_a_measured_dimension_still_buys_everything_its_band_authorises():
    """The counter-assertion, so the guard above cannot be satisfied by never
    spending at all. Same band, same overrides, one difference: the crawl
    reached the site and the score is a measurement rather than an absence.
    """
    esc = staging.plan({"ONP": 40.0}, set(), set(), set(), set(),
                       None, CFG, crawl_obtained_pages=True)

    assert esc["ONP"].band is staging.Band.CRITICAL
    assert esc["ONP"].buys_depth
    assert staging.escalated_tier(esc) == "T3"
    assert staging.paid_provider_dims(esc) == {"ONP"}
    assert staging.analyst_tasks(esc) == ["PRI-J", "ONP-J"]

    # And the escape hatch WF-54 documented still opens. An uncovered
    # dimension is banded WATCH whatever its score, so OFP reaches CRITICAL
    # only when both overrides fire — and there `_depth_could_obtain` returns
    # True for a crawl-blind dimension, because CRITICAL is the band that
    # authorises the backlink call its coverage comes from.
    ofp = staging.plan({"OFP": 100.0}, {"OFP"}, {"OFP"}, {"OFP"}, {"OFP"},
                       None, CFG, crawl_obtained_pages=True)
    assert ofp["OFP"].band is staging.Band.CRITICAL
    assert ofp["OFP"].buys_depth
    assert staging.escalated_tier(ofp) == "T3"
    assert staging.paid_provider_dims(ofp) == {"OFP"}
