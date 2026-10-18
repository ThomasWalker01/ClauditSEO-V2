"""The workbench registry must stay honest: a tool marked ready has to point
at checks that actually exist, and one marked planned must not pretend to."""

from __future__ import annotations

import clauditseo.modules  # noqa: F401
from clauditseo.playbook import NEEDS_KEY, PLANNED, PLAYBOOK, READY, summary


def _tools():
    return [t for phase in PLAYBOOK for t in phase["tools"]]


def test_ids_unique_and_phases_ordered():
    ids = [t["id"] for t in _tools()]
    assert len(ids) == len(set(ids))
    numbers = [int(p["phase"].split(".")[0]) for p in PLAYBOOK]
    assert numbers == sorted(numbers) == list(range(1, len(PLAYBOOK) + 1))


def test_every_tool_declares_status_kind_and_purpose():
    for tool in _tools():
        assert tool["status"] in (READY, NEEDS_KEY, PLANNED), tool["id"]
        assert tool["kind"] in ("sweep", "page", "site", "report"), tool["id"]
        assert tool["does"].strip(), tool["id"]
        if tool["status"] == NEEDS_KEY:
            assert tool.get("needs"), f"{tool['id']} must name the key it wants"


def test_ready_sweeps_reference_checks_the_engine_actually_emits():
    """The registry cannot claim a check that no module produces — that is
    exactly the kind of drift that makes a status board worthless."""
    # `sweep_checks()` since brief v17 step AV2, which needed the same
    # derivation and is the reason it has a name now. Two readings of "what
    # does the engine emit" would disagree the first time a module changed
    # how it names a check.
    from clauditseo.checks import brief_only_checks, sweep_checks

    emitted = set(sweep_checks())
    # A brief's own checks come from the model, not a module: the registry
    # names them (brief v11 step AI) and no sweep emits them.
    emitted.update(c.split("/", 1)[1] for c in brief_only_checks())

    for tool in _tools():
        if tool["status"] != READY:
            continue
        for check in tool.get("checks", []):
            assert check in emitted, f"{tool['id']} claims unknown check {check}"


def test_planned_tools_are_not_wired_up():
    for tool in _tools():
        if tool["status"] == PLANNED:
            assert not tool.get("checks"), f"{tool['id']} is planned but claims checks"
            assert not tool.get("endpoint"), f"{tool['id']} is planned but has an endpoint"
            assert not tool.get("expert"), f"{tool['id']} is planned but claims a brief"


def test_expert_briefs_referenced_by_the_registry_exist():
    from clauditseo.analysts.expert import EXPERT_TOOLS
    for tool in _tools():
        brief = tool.get("expert")
        if brief:
            assert brief in EXPERT_TOOLS, f"{tool['id']} names unknown brief {brief}"
            assert tool["status"] != PLANNED
            assert tool.get("spec"), f"{tool['id']} has a brief but no spec summary"


def test_summary_counts_agree_with_the_registry():
    s = summary()
    assert s["total"] == len(_tools())
    assert s["ready"] + s["needs_key"] + s["planned"] == s["total"]
    # Tools built from an operator-supplied expert prompt.
    specced = {t["id"] for t in _tools() if t.get("spec")}
    assert s["with_spec"] == len(specced)
    assert specced == {"page-advisor", "schema-auditor",
                       # phase 1 — `urls` (brief v19 step BB) replaced the
                       # legacy `url-hygiene`, retired once the live runs were
                       # clean (item 141).
                       "crawl", "indexability", "urls",
                       # phase 7 — the Speed brief (brief v19 step BC).
                       "speed",
                       # phase 2
                       "https-security", "mobile-basics", "links",
                       "content-coverage", "content-substance",
                       "content-cannibalisation", "content-benchmark",
                       "hreflang", "migration-redirects",
                       # phase 3
                       "images", "title-desc", "headings",
                       # phase 4 — brief v16 step AS's Structured data brief.
                       # The entity brief and the llms.txt builder retired at
                       # item 145; the AI surface brief carries their work.
                       "structured-data",
                       # phase 5
                       "content-brief",
                       # phase 8
                       "local-signals", "gbp-audit", "citations-nap",
                       # AI surface: the sweep that the brief answers for
                       # (item 145 step BH).
                       "ai-access",
                       "review-signals",
                       # phase 10 — and brief v18 step AY puts the client
                       # plan beside the dispatcher: both decide and tell,
                       # and neither finds anything.
                       # `triage` stood here until item 196 retired the
                       # brief: the ranking it produced is computed with the
                       # audit now, so there is no prompt and no spec.
                       "plan"}


def test_every_brief_declares_a_model_tier():
    """Routing is deliberate: a checklist and an intent judgement should not
    cost the same, and an unset tier would silently bill at the default."""
    from clauditseo.analysts.expert import EXPERT_TOOLS
    for tool_id, spec in EXPERT_TOOLS.items():
        assert spec.get("tier") in ("fast", "standard", "deep"), tool_id


def test_a_key_gated_tool_stops_saying_needs_key_once_its_key_is_present():
    """The workbench is the operator's map of what will actually run. A badge
    that contradicts the configuration makes every other badge suspect."""
    import dataclasses

    from clauditseo.config import Settings
    from clauditseo.playbook import resolved, summary

    def status_of(phases, tool_id):
        return next(t["status"] for p in phases for t in p["tools"]
                    if t["id"] == tool_id)

    bare = dataclasses.replace(Settings(), crux_api_key="", pagespeed_api_key="",
                               moz_token="", dataforseo_login="",
                               openpagerank_key="")
    assert status_of(resolved(bare), "core-web-vitals") == "needs_key"

    keyed = dataclasses.replace(bare, pagespeed_api_key="k")
    assert status_of(resolved(keyed), "core-web-vitals") == "ready"
    # Only the tool that key satisfies is promoted.
    assert status_of(resolved(keyed), "backlink-profile") == "needs_key"
    assert summary(resolved(keyed))["ready"] == summary(resolved(bare))["ready"] + 1


def test_resolving_never_promotes_a_planned_tool():
    import dataclasses

    from clauditseo.config import Settings
    from clauditseo.playbook import resolved

    generous = dataclasses.replace(Settings(), crux_api_key="k", moz_token="k",
                                   pagespeed_api_key="k", openpagerank_key="k")
    planned = [t for p in resolved(generous) for t in p["tools"]
               if t["status"] == "planned"]
    assert planned, "a key must never turn unbuilt work into ready work"
