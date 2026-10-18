"""The local signals brief conforms to the contract (item 278, row 11).

`local-signals.md` was a legacy prompt: a CLARIFY gate that asked up to three
questions and stopped, a scorecard and findings index of its own, and
`[TO CONFIRM]` for inputs the engine supplies. It now declares the five LOC
checks it reads, emits Block 1, and holds an absent input as a
`not_assessable` naming it. The five are registered, at the severities the
sweep has always emitted them at.
"""

from __future__ import annotations

from types import SimpleNamespace

from clauditseo import briefs
from clauditseo.analysts import expert
from clauditseo.checks import default_severities

LOC = ("nap-missing", "nap-inconsistent", "localbusiness-schema-missing",
       "opening-hours-missing", "thin-location-page")


def test_registered():
    got = default_severities()
    assert {c: got[f"LOC/{c}"] for c in LOC} == {
        "nap-missing": "medium", "nap-inconsistent": "medium",
        "localbusiness-schema-missing": "medium", "opening-hours-missing": "low",
        "thin-location-page": "low"}


def test_the_header_and_the_prompt():
    text = (expert.PROMPT_DIR / "local-signals.md").read_text(encoding="utf-8")
    header, body = briefs.split_front_matter(text)
    assert header["checks"] == [f"LOC/{c}" for c in LOC]
    assert expert.conforms("local-signals")
    for gone in ("CLARIFY", "TO CONFIRM", "Then stop and wait"):
        assert gone not in body, gone


def test_every_placeholder_is_filled():
    ev = {"start_url": "https://t.co/", "pages": []}
    site = SimpleNamespace(brand="Birch", business_type="event planner", locale=None,
                           target_market=None)
    ctx = expert._local_signals_context(ev, site, conn=None, run_id="r1")
    assert ctx["RUN_ID"] == "r1" and ctx["BUSINESS_NAME"] == "Birch"
    expert.render_prompt("local-signals", ctx)   # raises on an unfilled placeholder


def test_the_record_s_nap_locations_and_platform_reach_the_brief():
    """Screen audits round 3 (Local US-03): ADDRESS, PHONE, TARGET_LOCATIONS
    and PLATFORM were hard-wired absent, so the brief's canonical judgement
    could never run on any site. Admin > Sites holds them."""
    from types import SimpleNamespace
    from clauditseo.analysts import expert
    site = SimpleNamespace(brand="Twenty22", business_type="web design", locale=None,
                           target_market=None, platform="WordPress",
                           nap="Twenty22, 1 Smith St, Warragul VIC 3820, (03) 5622 0000",
                           locations="Warragul; Drouin", service_area_entity=None)
    ctx = expert._local_signals_context({"start_url": "https://t.co/", "pages": []}, site,
                                        conn=None, run_id="r1")
    assert "1 Smith St, Warragul VIC 3820" in ctx["ADDRESS"]
    assert ctx["PHONE"] == "(03) 5622 0000"
    assert ctx["TARGET_LOCATIONS"] == "Warragul; Drouin"
    assert ctx["PLATFORM"] == "WordPress"
    bare = SimpleNamespace(brand=None, business_type=None, locale=None, target_market=None,
                           platform=None, nap=None, locations=None, service_area_entity=None)
    ctx = expert._local_signals_context({"start_url": "https://t.co/", "pages": []}, bare,
                                        conn=None, run_id="r1")
    assert ctx["ADDRESS"] == ctx["PHONE"] == ctx["PLATFORM"] == expert.ABSENT
