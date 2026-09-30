"""A check may be reported as passing only if the run measured it; absence of a
finding is not a pass (item 157, channel 20260912-0940).

THE RULE is stated once, at the top of `clauditseo/playbook.py`, because three
local fixes for three instances were not enough to stop a fourth. The instances,
each fixed on its own and each comment written after it bit:

- `img-sitemap-missing` read as passing on Birch's home page while the brief was
  saying site-wide that it could not judge it (`part_page.tsx`);
- "link-gap runs in every audit" on screen for a tool that is not built
  (`anatomy.tsx`);
- and the one that produced the rule, found by looking at a screen rather than
  by any test here: on `www.acme.com.au`, run `19eeb42e`, recorded dimensions
  `["TEC","ONP","AIS","CNT"]` and **zero** PRF findings, the Speed part rendered
  *"18 checks pass"* — `cwv-not-assessed` among them, the finding whose whole job
  is to say a measurement did not happen. Links claimed 12 with LNK absent from
  the run; Crawl certified its LNK half.

Two rungs, one state. `not_assessed` carries a because-clause rather than the
screen growing a status member per cause — a status enum grows one per cause and
every call site that switches on it has to learn each one. The third cause (no
network, quota exhausted, a page set too small to judge) is not far off.

**The sharpest clause in this file is
`test_a_renderer_installed_today_does_not_rewrite_what_an_old_run_measured`.**
Rung 2 is read from the run's stored evidence and never from the config. Deriving
it from what is installed now would let tomorrow's `pip install
clauditseo[render]` silently change what a June run claims to have measured,
which is the same class of lie the rule exists to forbid. The workbench, having
no run to read, uses the capability predicate instead: same vocabulary, two call
sites, different inputs.

DISCIPLINE rule 1: measured against the pre-change tree. Every clause below that
asserts a check is *not* reported as passing was red there, because there was no
`not_assessed` field and every unmeasured check was in the pass list.
"""

from __future__ import annotations

import json

import pytest

from clauditseo import briefs, playbook
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.modules import prf
from clauditseo.persistence import repo, runs

# --- the rule's two readers -------------------------------------------------


@pytest.fixture
def site(tmp_path):
    """A migrated database with one site, and nothing else. No server and no
    crawl: every clause here reads a stored run, which is the whole point of
    rung 2 being historical."""
    conn = connect(tmp_path / "clauditseo.db")
    migrate(conn)
    op_id = repo.ensure_default_operator(conn, "Item 157")
    client = repo.create_client(conn, op_id, "Item 157 Co")
    site_id = repo.create_site(conn, client, "x.test")
    yield conn, site_id
    conn.close()


def _plant(conn, site_id: str, dims: list[str], *, traced: bool) -> str:
    """One complete run with a chosen dimension list, and a crawl whose pages
    either carry a trace or do not."""
    run_id = runs.create_run(conn, site_id, dims, "T2")
    pages = [{"url": "https://x.test/", "status": 200,
              **({"perf": {"traced": True, "ttfb_ms": 10.0}} if traced else {})}]
    conn.execute("UPDATE audit_runs SET status='complete', crawl_evidence=?"
                 " WHERE id=?", (json.dumps({"pages": pages}), run_id))
    conn.commit()
    return run_id


def _speed_checks() -> list[str]:
    return list(next(b for b in briefs.catalogue() if b.id == "speed").checks)


def test_a_dimension_that_did_not_run_reports_no_passes(site) -> None:
    """Rung 1, and the larger share of the defect. The exact shape of Acme's
    `19eeb42e`: a complete audit whose dimension list does not name PRF."""
    conn, site_id = site
    run_id = _plant(conn, site_id, ["TEC", "ONP", "AIS", "CNT"], traced=False)

    out = runs.not_assessed_payload(conn, run_id,
                                    checks_by_part={"speed": _speed_checks()})
    speed = out.get("speed", {})
    assert set(speed) == set(_speed_checks()), (
        "every check of a part whose dimension did not run is unmeasured — a "
        "subset would mean some of them were being certified")
    assert all("PRF did not run" in r for r in speed.values())
    assert "PRF/cwv-not-assessed" in speed, (
        "the finding that exists to say a measurement did not happen is the "
        "one this most obviously must not report as passing")


def test_a_run_with_no_trace_does_not_certify_the_trace_checks(site) -> None:
    """Rung 2. PRF ran, so rung 1 is silent and this is the instrument alone."""
    conn, site_id = site
    run_id = _plant(conn, site_id, ["PRF"], traced=False)

    speed = runs.not_assessed_payload(
        conn, run_id, checks_by_part={"speed": _speed_checks()}).get("speed", {})
    # Two rungs answer here, and this clause first asserted only one. The trace
    # checks are unmeasured because no trace was taken (rung 2); the Speed
    # brief's five ANALYSIS checks are unmeasured because no Speed brief ran
    # (rung 3). The old assertion -- that the map was exactly the trace checks
    # -- held only while rung 3 did not exist, i.e. while an analysis check
    # with no brief behind it read as measured, which is the defect rung 3
    # fixes.
    trace = {c: r for c, r in speed.items()
             if c.split("/")[-1] in prf.TRACE_DERIVED_CHECKS}
    assert {c.split("/")[-1] for c in trace} == set(prf.TRACE_DERIVED_CHECKS)
    assert all("took no performance trace" in r for r in trace.values())
    analysis = {c: r for c, r in speed.items()
                if c.split("/")[-1] in prf.BRIEF_ONLY_CHECKS}
    assert {c.split("/")[-1] for c in analysis} == set(prf.BRIEF_ONLY_CHECKS)
    assert all("no analysis has run" in r for r in analysis.values())

    # Item 168, inverted from the old premise: migration 0054 retired the
    # HTML-bytes page-weight, so since then only a trace measures it and an
    # untraced run is not assessed on it. (A run from before 0054 is the
    # proxy's; `test_a_run_from_before_0054_measured_page_weight_by_proxy`.)
    assert "PRF/page-weight" in speed, (
        "page-weight is trace-only since migration 0054, so an untraced run "
        "did not measure it and must not read it as passing")
    assert "PRF/cwv-not-assessed" not in speed, (
        "PRF ran, so this one was measured and its answer is the finding")


def test_a_run_that_took_a_trace_certifies_the_trace_checks(site) -> None:
    """The control. Without it the two clauses above would pass against a
    payload that called every check unmeasured always."""
    conn, site_id = site
    run_id = _plant(conn, site_id, ["PRF"], traced=True)
    speed = runs.not_assessed_payload(
        conn, run_id, checks_by_part={"speed": _speed_checks()}).get("speed", {})
    # A traced PRF run certifies the TRACE checks: rung 2 is silent, and no
    # trace-derived check may appear here. It does NOT certify the brief's five
    # analysis checks -- no Speed brief ran -- so those remain, by rung 3. This
    # clause first asserted the whole map was empty, which was only true while
    # an analysis check with no brief behind it read as measured.
    assert not any(c.split("/")[-1] in prf.TRACE_DERIVED_CHECKS for c in speed), (
        f"a traced run left trace checks unmeasured: {sorted(speed)}")
    assert {c.split("/")[-1] for c in speed} == set(prf.BRIEF_ONLY_CHECKS)


def test_a_renderer_installed_today_does_not_rewrite_what_an_old_run_measured(
        site, monkeypatch) -> None:
    """The load-bearing clause. The anatomy of a finished run is a historical
    fact: those checks are unmeasured on that run forever.

    Driven from both ends — a renderer present and a renderer absent — over one
    stored run that holds no trace. The answer must not move. If it ever reads
    the config, one of these two directions fails.
    """
    conn, site_id = site
    run_id = _plant(conn, site_id, ["PRF"], traced=False)

    answers = []
    for present in (True, False):
        monkeypatch.setitem(
            playbook.CAPABILITIES, "renderer",
            playbook.Capability(lambda _cfg, p=present: p,
                                playbook.CAPABILITIES["renderer"].remedy))
        answers.append(runs.not_assessed_payload(
            conn, run_id, checks_by_part={"speed": _speed_checks()}))

    assert answers[0] == answers[1], (
        "installing a renderer changed what a stored run claims to have "
        "measured — that is the lie this item exists to forbid")
    assert answers[0].get("speed"), "and it must still name the unmeasured set"


def test_a_run_this_cannot_read_says_nothing_rather_than_guessing(
        site) -> None:
    """Three silences, and the third is deliberate: this reader may say
    "unmeasured", and it may say nothing, but it may never manufacture a pass.
    A `{}` return leaves the pass list exactly as it was."""
    conn, site_id = site
    checks = {"speed": _speed_checks()}
    assert runs.not_assessed_payload(conn, None, checks_by_part=checks) == {}
    assert runs.not_assessed_payload(conn, "nosuchrun",
                                     checks_by_part=checks) == {}
    run_id = runs.create_run(conn, site_id, [], "T2")
    assert runs.not_assessed_payload(conn, run_id, checks_by_part=checks) == {}


# --- the join, and the two lists that do not contain each other -------------


def test_neither_check_list_contains_the_other(site) -> None:
    """Why the answer is a join and not a switch of source, as an exact set.

    Asserting the *intersection* rather than the rendered pass list: a rendered
    clause only catches a drifting id if a fixture happens to cover that part,
    and this claim is about all 28 briefs. When a brief id drifts from its
    tool's id the intersection shrinks and this names the id that left.
    """
    brief_ids = {c.split("/")[-1] for b in briefs.catalogue() for c in b.checks}
    tool_ids = {c for ph in playbook.PLAYBOOK for t in ph["tools"]
                for c in (t.get("checks") or [])}

    brief_only = brief_ids - tool_ids
    tool_only = tool_ids - brief_ids
    # 53 before brief v20; +9 Mobile and +11 International at items 147 and
    # 148, none of which any playbook tool claims — Mobile's nine are held on
    # captures that do not exist, and `intl` is ANALYSIS_ONLY so no tool ever
    # will claim its eleven.
    # +28 at item 143 step BD: `security.md` declares 56 SEC ids and the
    # https-security sweep claims the 28 it emits, so the six analysis checks,
    # the four held and the eighteen not yet collected are brief-only here.
    # -6 when the DNS checks gained their collector and the sweep claimed them.
    # -8 for the cors-permissive, cross-origin-policies, script-inventory,
    # obfuscated-js, hidden-content, cloaking, http2-absent, cert-key and
    # trackers-before-consent collectors.
    # +10 at item 145 step BH: `ai-surface.md`'s analysis checks, which no
    # sweep raises and so no playbook tool claims.
    assert len(brief_only) == 96, (
        f"brief-declared ids no tool names moved from 96 to {len(brief_only)}: "
        f"{sorted(brief_only ^ set(_BRIEF_ONLY))}")
    # 42 before migration 0054; `slow-response` and `caching-headers` left the
    # playbook with the retired `perf-signals` tool, and neither was ever
    # brief-declared, so both came off this side of the difference. Then -1 at
    # item 147: `mobile-viewport` was a tool id no brief named, and the
    # playbook's mobile sweep now names `viewport-missing` and its five
    # siblings, all of which the rewritten brief declares.
    # Then 57 at item 143 step BD's first stage: -2 for `not-https` and
    # `security-headers` (purged) and +20 for the SEC checks the https-security
    # sweep emits. No installed brief names them until `security.md` replaces
    # `https-security.md`, which carries `checks: []`; that install brings this
    # back down.
    # +8 at stage two: the well-known path sweep's checks (exposed-file,
    # directory-listing, error-leak, four CMS checks, security-txt).
    # Back to 37 once `security.md` replaced `https-security.md` (which declared
    # `checks: []`): the brief now names every SEC check the sweep claims.
    # 38 at item 165: `head-divergent`, which the crawl sweep raises from the
    # head pair; crawl.md predates it and is installed verbatim.
    # 41 at item 151: `mobile-parity`, `mobile-parity-size` and `bot-parity`,
    # which the crawl sweep raises from the parity probe; same reason.
    # 42 at item 145 step BG: `edge-blocks-ai-ua`, which the AI-surface sweep
    # raises from the UA matrix; `ai-surface.md` is not installed yet, and its
    # install brings this back down. 50 with the step's other eight free
    # checks (ai-crawler-allowed-unstated, noai-meta, ua-sensitive,
    # content-behind-js, llms-txt-stale, entity-unresolvable, entity-unnamed,
    # ai-experience-unmeasured).
    # Back to 40 once `ai-surface.md` is installed (item 145 step BH): the
    # brief names all ten of the AIS sweep's reachability and free checks.
    # 41 at item 236: `referring-domains-reported`, the count reported beside
    # `domain-authority-reported`; Backlinks has no brief to name either.
    assert len(tool_only) == 41, (
        f"tool ids no brief names moved from 41 to {len(tool_only)}")
    assert brief_only and tool_only, (
        "if either side empties, one list contains the other and a "
        "single-source answer becomes possible — re-decide rather than "
        "loosening this")


def test_the_unclaimed_are_declared_and_not_left_to_absence() -> None:
    """The 53 get an explicit state. A check missing from the gating map must
    not read as "gated and live", which is this item's own defect class."""
    class Cfg:
        crux_api_key = pagespeed_api_key = moz_token = ""
        dataforseo_login = openpagerank_key = ""

    every = [c for b in briefs.catalogue() for c in b.checks]
    got = playbook.gating_for(every, Cfg())
    assert set(got) == set(every), "one entry per id asked for, no silent drops"
    assert {v["state"] for v in got.values()} <= {"live", "dark", "unclaimed"}
    # 101 since `security.md` (item 143 step BD): +28 SEC ids no tool claims.
    # 95 once the six DNS checks were claimed by the sweep.
    # 96 with `ai-surface.md`'s ten analysis checks (item 145 step BH).
    assert sum(1 for v in got.values() if v["state"] == "unclaimed") == 96


def test_a_tool_only_check_never_reaches_the_part_screen() -> None:
    """Correct as behaviour — the screen lists what a brief writes — but
    asserted, so a check that gains a tool and not a brief is noticed rather
    than invisible."""
    brief_ids = {c.split("/")[-1] for b in briefs.catalogue() for c in b.checks}
    tool_only = {c for ph in playbook.PLAYBOOK for t in ph["tools"]
                 for c in (t.get("checks") or [])} - brief_ids
    for part_checks in (_speed_checks(),):
        assert not {c.split("/")[-1] for c in part_checks} & tool_only


# --- the capability registry ------------------------------------------------


def test_the_renderer_gate_is_the_trace_derived_set() -> None:
    """`playbook.py` is a literal table, so the gate's ids are written out
    rather than imported — importing a module into a data table at import time
    is how an import cycle starts. This is what stops the two drifting."""
    tool = next(t for ph in playbook.PLAYBOOK for t in ph["tools"]
                if t["id"] == "speed")
    gated_on_renderer = {c for c, needs in (tool.get("gated") or {}).items()
                         if needs == ["renderer"]}
    assert gated_on_renderer == set(prf.TRACE_DERIVED_CHECKS)
    assert "page-weight" in gated_on_renderer, (
        "page-weight is trace-only since migration 0054, so the renderer is "
        "what makes it answerable")


def test_a_config_key_is_just_a_predicate() -> None:
    """The five that existed before item 157 are in the registry with their
    behaviour unchanged: `resolved()` went from reading the attribute inline to
    asking this, at one line."""
    class Cfg:
        crux_api_key = "set"
        pagespeed_api_key = ""
    assert playbook.satisfied("crux_api_key", Cfg()) is True
    assert playbook.satisfied("pagespeed_api_key", Cfg()) is False
    assert set(playbook.KEY_NAMES) <= set(playbook.CAPABILITIES)


def test_a_capability_the_registry_does_not_have_is_not_satisfied() -> None:
    """A `gated` map naming an unknown capability is a mistake, and the safe
    reading of a mistake here is that the check cannot fire. A map that
    silently granted itself a capability is the failure this item is about."""
    assert playbook.satisfied("no-such-capability", object()) is False


def test_a_probe_that_raises_is_dark_rather_than_satisfied(monkeypatch) -> None:
    """Probes are not attribute reads. Treating a throwing probe as truthy
    would reproduce this item's own defect with extra steps."""
    def boom(_cfg):
        raise RuntimeError("no chromium, and the check for one exploded")

    monkeypatch.setitem(playbook.CAPABILITIES, "renderer",
                        playbook.Capability(boom, "irrelevant"))
    # `satisfied` must not propagate it either — one exploding probe cannot
    # take down the workbench for every other tool.
    try:
        got = playbook.satisfied("renderer", object())
    except RuntimeError:
        raise AssertionError("a raising probe escaped as an exception") from None
    assert got is False


def test_the_renderer_is_not_probed_at_import_time() -> None:
    """`perf.available()` touches the filesystem and can spawn a process, so a
    module-level probe would put a subprocess in the import path of everything
    that imports the playbook.

    Asserted against the source rather than by timing an import: the claim is
    that the call is inside a function, which is a structural fact.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(playbook))
    depth = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                depth[id(child)] = True
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "available"):
            assert depth.get(id(node)), (
                "perf.available() is called at module level in playbook.py")


def test_the_dark_note_words_a_non_key_capability(monkeypatch) -> None:
    """The note used to end "supplies the data they read", which is true of a
    provider key and false of the first capability that is not one: a renderer
    supplies no data an operator signs up for, it is a package they install."""
    class Cfg:
        crux_api_key = pagespeed_api_key = moz_token = ""
        dataforseo_login = openpagerank_key = ""

    monkeypatch.setitem(
        playbook.CAPABILITIES, "renderer",
        playbook.Capability(lambda _c: False,
                            playbook.CAPABILITIES["renderer"].remedy))
    speed = next(t for ph in playbook.resolved(Cfg()) for t in ph["tools"]
                 if t["id"] == "speed")
    assert speed["status"] == playbook.PARTIAL, (
        "eleven of its checks cannot fire, so it is not ready — and it is not "
        "needs_key either, because no key would free them")
    note = speed["dark_note"]
    assert "supplies the data" not in note and "supply the data" not in note
    assert "renderer extra" in note and "Chromium" in note
    assert "it needs" in note or "they need" in note


def test_the_rule_is_stated_in_source() -> None:
    """Item 5 of the build order, and the cheapest thing here: the general rule
    written down once, so a fourth occurrence does not need a fourth local fix.

    A test on a comment, deliberately. Three of these fixes already exist as
    local comments and the class still recurred; what was missing was the rule
    in the file that decides what can fire.
    """
    import inspect
    src = inspect.getsource(playbook)
    assert "may be reported as passing only if the run measured it" in src
    assert "Absence of a finding is not a pass" in src


#: The 53, recorded so the set-difference assertion above can name what moved
#: rather than only that the count changed.
_BRIEF_ONLY = {
    "anchor-entity", "anchor-flow", "answer-first", "answer-surface",
    "cannibalisation", "canonical-missing-variant", "crawl-budget-waste",
    "demand-gap", "eeat", "fact-density", "format-gap", "gap", "hub-spoke-gap",
    "img-heavy", "img-link-alt-not-destination", "img-logo", "img-oversized",
    "img-sitemap-missing", "img-sizes-wrong", "img-text-in-image",
    "img-weight-budget", "intent-gap", "link-suggestion", "no-author",
    "noindex-intent", "optimisation-ratio", "parameter-policy",
    "redirect-map-correctness", "render-policy", "retrieval-cost",
    "schema-author-missing", "schema-catalog-mismatch", "schema-entity-model",
    "schema-entity-thin", "schema-hidden-markup", "schema-id-page",
    "schema-island", "schema-review-unsupported", "schema-sameas-missing",
    "schema-subtype-shallow",
    # Brief v20: Mobile's nine held checks (item 147) and every one of
    # International's eleven (item 148). None is claimed by a playbook tool.
    "viewport-injected",
    "viewport-divergent",
    "viewport-late",
    "horizontal-overflow",
    "tap-target",
    "viewport-units",
    "viewport-source",
    "viewport-keyboard",
    "safe-area",
    "hreflang-missing",
    "hreflang-reciprocity",
    "hreflang-self",
    "hreflang-x-default",
    "hreflang-code",
    "hreflang-target",
    "hreflang-method-mixed",
    "hreflang-sitemap-conflict",
    "locale-redirect",
    "architecture",
    "consolidation",
}


# --- found when Mobile and International reached the three-block layout -----


def test_a_label_only_dimension_never_triggers_rung_one(site) -> None:
    """`INT` owns no sweep, so it is never in any run's dimension list, and rung
    1 said "INT did not run in this audit" on every site forever -- including
    beneath a gate card reading "Not applicable", and on Acme, where the
    International brief HAD run. Its checks are brief-only and rung 3 answers
    for them instead."""
    conn, site_id = site
    run_id = _plant(conn, site_id, ["TEC", "ONP"], traced=False)
    intl = list(next(b for b in briefs.catalogue() if b.id == "hreflang").checks)
    got = runs.not_assessed_payload(conn, run_id, checks_by_part={"intl": intl})
    reasons = set(got.get("intl", {}).values())
    assert not any("INT did not run" in r for r in reasons), (
        f"rung 1 fired on a label-only dimension: {reasons}")


def test_a_brief_only_check_with_no_brief_run_is_not_a_pass(site) -> None:
    """Rung 3, and the fourth instance of this file's class. Mobile's three
    analysis checks read "3 checks clean" on twenty22, where no Mobile brief had
    ever run: TEC ran (rung 1 silent), none is trace-derived (rung 2 silent).
    A check only a brief can raise, with no brief behind it, was measured by
    nothing."""
    conn, site_id = site
    run_id = _plant(conn, site_id, ["TEC"], traced=True)
    mobile = list(next(b for b in briefs.catalogue()
                       if b.id == "mobile-viewport").checks)
    got = runs.not_assessed_payload(conn, run_id,
                                    checks_by_part={"mobile": mobile})["mobile"]
    for check in ("TEC/viewport-source", "TEC/viewport-keyboard", "TEC/safe-area"):
        assert check in got, check
        assert "no analysis has run" in got[check]


def test_a_brief_that_has_run_clears_rung_three(site) -> None:
    """The control for rung 3: once the part's brief has answered, its
    brief-only checks were measured and may pass. Acme International read 0
    not-assessed on screen because its brief had run."""
    conn, site_id = site
    run_id = _plant(conn, site_id, ["TEC"], traced=True)
    conn.execute("INSERT INTO expert_reports (run_id, tool_id, model_id, report,"
                 " findings, created_at) VALUES (?, 'mobile-viewport', 'm', '',"
                 " '[]', '2026-09-13T00:00:00')", (run_id,))
    conn.commit()
    mobile = list(next(b for b in briefs.catalogue()
                       if b.id == "mobile-viewport").checks)
    got = runs.not_assessed_payload(conn, run_id,
                                    checks_by_part={"mobile": mobile}).get("mobile", {})
    assert "TEC/viewport-source" not in got


def test_every_modules_trace_checks_read_as_unmeasured_on_an_untraced_run(site) -> None:
    """Rung 2 knew only PRF's set. Mobile's six trace-fed checks are TEC, so on
    a run with no trace they hit no rung and read CLEAN -- a tap-target check
    passed by a run that never rendered a page. The parse checks, which read the
    crawl's own viewport tags, stay measured."""
    from clauditseo.modules import tec
    conn, site_id = site
    run_id = _plant(conn, site_id, ["TEC"], traced=False)
    mobile = list(next(b for b in briefs.catalogue()
                       if b.id == "mobile-viewport").checks)
    payload = runs.not_assessed_payload(conn, run_id, checks_by_part={
        "mobile": mobile, "crawl": ["TEC/head-divergent"]})
    got = payload["mobile"]
    # `head-divergent` (item 165) is Crawl's, so it is asked of that part.
    for check in tec.TRACE_DERIVED_CHECKS - {"head-divergent"}:
        assert f"TEC/{check}" in got, check
        assert "no performance trace" in got[f"TEC/{check}"]
    assert "no performance trace" in payload["crawl"]["TEC/head-divergent"]
    for check in ("viewport-missing", "viewport-width", "zoom-suppressed"):
        assert f"TEC/{check}" not in got, f"{check} is a parse check, measured regardless"


# --- page mode (brief v23 step BK) -------------------------------------------


def test_a_page_the_run_did_not_trace_does_not_pass_the_trace_checks(tmp_path) -> None:
    """Rung 2 is run-level: a run that traced ANY page leaves the trace checks
    measured. In page mode that certified tap-target on twenty22 /about/, which
    the sampled trace never rendered ("12 checks pass on this page"). The page
    in scope now owes its own reason; a traced page does not."""
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    db = tmp_path / "clauditseo.db"
    app = create_app(db_path=db)
    conn = connect(db)
    op_id = repo.ensure_default_operator(conn, "BK")
    client = repo.create_client(conn, op_id, "BK Co")
    site_id = repo.create_site(conn, client, "x.test")
    run_id = runs.create_run(conn, site_id, ["TEC", "PRF"], "T2")
    traced = {"traced": True, "device_profile": "pixel5", "ttfb_ms": 10.0}
    pages = [{"url": "https://x.test/", "status": 200, "perf": traced},
             {"url": "https://x.test/about/", "status": 200,
              "perf": {"traced": False}}]
    conn.execute("UPDATE audit_runs SET status='complete', crawl_evidence=?"
                 " WHERE id=?", (json.dumps({"pages": pages}), run_id))
    conn.commit()
    conn.close()

    with TestClient(app) as http:
        def mobile(page: str) -> dict:
            body = http.get(f"/api/sites/{site_id}/anatomy",
                            params={"page": page, "run_id": run_id}).json()
            return next(c for c in body["categories"] if c["key"] == "mobile")

        untraced = mobile("https://x.test/about/")
        assert untraced["trace_derived"], "the part names no trace checks to test"
        for full in untraced["trace_derived"]:
            assert "not among the pages this run traced" in untraced["not_assessed"].get(full, ""), full
        home = mobile("https://x.test/")
        assert not any("not among the pages this run traced" in r
                       for r in home["not_assessed"].values())


# --- item 168: page-weight is trace-only since migration 0054 ----------------

def test_a_run_from_before_0054_measured_page_weight_by_proxy(site) -> None:
    """The other direction. 0054 retired the HTML-bytes reading and purged none
    of its `page-weight` rows, so an untraced run created before 0054 was
    applied did measure it, and must not now read as unmeasured."""
    conn, site_id = site
    before = _plant(conn, site_id, ["PRF"], traced=False)
    applied = conn.execute("SELECT applied_at FROM schema_migrations WHERE filename=?",
                           (prf.PAGE_WEIGHT_PROXY_UNTIL,)).fetchone()[0]
    conn.execute("UPDATE audit_runs SET created_at='2020-01-01T00:00:00+00:00' WHERE id=?", (before,))
    conn.commit()
    after = _plant(conn, site_id, ["PRF"], traced=False)
    assert applied, "0054 is applied on every migrated database"
    old = runs.not_assessed_payload(conn, before, checks_by_part={"speed": _speed_checks()})["speed"]
    new = runs.not_assessed_payload(conn, after, checks_by_part={"speed": _speed_checks()})["speed"]
    assert "PRF/page-weight" not in old and "PRF/lcp-slow" in old
    assert "PRF/page-weight" in new


def test_the_trace_is_the_only_instrument_that_raises_page_weight() -> None:
    """The derivation the set's comment promises: PRF over a heavy trace raises
    page-weight, and PRF over a 5 MB page with no trace cannot."""
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Tier
    from clauditseo.modules.prf import PerformanceModule
    url = "https://x.test/"
    page = Page(url=url, requested_url=url, status=200, content_type="text/html",
                content="<html>" + "x" * 5_000_000 + "</html>")
    heavy = {"device_profile": "d", "ttfb_ms": 200, "fcp_ms": 700,
             "lcp": {"ms": 1000, "sub_parts": {}}, "cls": {"value": 0.0, "shifts": []},
             "tbt_ms": 0, "long_tasks": [], "fonts": [],
             "resources": [{"url": url + "big.js", "type": "script", "bytes": 3_000_000,
                            "transfer": 3_000_000, "blocking": False, "compression": "br",
                            "cache_control": "max-age=600", "whitespace_ratio": 0.0,
                            "coverage": "unavailable"}]}

    def fired(traces):
        crawl = CrawlResult(start_url=url, tier=Tier.T2, pages=[page])
        return {f.check_id for f in PerformanceModule().run(
            crawl.pages, Tier.T2, {"crawl": crawl, "perf_traces": traces, "site": None})}
    assert "page-weight" in fired({url: heavy})
    assert "page-weight" not in fired({})
    assert "page-weight" in prf.TRACE_DERIVED_CHECKS
