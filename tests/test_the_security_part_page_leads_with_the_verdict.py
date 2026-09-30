"""The Security & transport part page (item 143 addendum, operator-approved
2026-09-07): the compromise verdict first, then the layers - nine domain cards
at the layer each lives at - then the headers grid.

Driven against the accessibility sweep's fixture, which audits SEC. The
brief's ledger is injected into the payload for the agreement clause, because
no brief runs in the suite.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.parts import ANATOMY_READY, open_part
from tests.needs_build import needs_build

_READ = """() => {
  const card = document.querySelector('.now-card:has(.secv)');
  return {
    first: card ? card.firstElementChild.className : null,
    verdict: document.querySelector('.secv b')?.textContent || null,
    cards: [...document.querySelectorAll('.seccard')].map((c) => ({
      domain: c.dataset.domain, state: c.dataset.state,
      word: c.querySelector('.seccard-word')?.textContent || '',
      note: c.querySelector('.seccard-note')?.textContent || '',
      layer: c.closest('.seclayer')?.querySelector('.seclayer-name')?.textContent || '',
      dashed: getComputedStyle(c).borderTopStyle === 'dashed',
    })),
  };
}"""


def _open(served, ledger=None):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1200})
        try:
            if ledger is not None:
                def anatomy(route):
                    data = route.fetch().json()
                    for c in data["categories"]:
                        if c["key"] == "security":
                            c["brief_security"] = {"compromise": {"verdict": "none observed",
                                                                  "basis": "all first-party"},
                                                   "ledger": ledger}
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
                pg.route("**/api/sites/*/anatomy*", anatomy)
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            open_part(pg, 'Security')
            pg.wait_for_selector(".seclayers", timeout=15_000)
            pg.wait_for_timeout(300)
            return pg.evaluate(_READ)
        finally:
            browser.close()


@needs_build
def test_the_verdict_is_the_first_thing_on_the_page(served):
    got = _open(served)
    assert got["first"] and "secv" in got["first"], got["first"]
    # No brief ran on the fixture: the line says so and never says "secure".
    assert got["verdict"] == "Compromise not assessable"


@needs_build
def test_a_held_domain_is_hollow_and_says_why(served):
    got = _open(served)
    by = {c["domain"]: c for c in got["cards"]}
    assert set(by) == set("ABCDEFGHI")
    for letter in ("G", "H"):
        assert by[letter]["state"] == "held" and by[letter]["dashed"], by[letter]
        # Item 180: a domain none of whose checks ran says "not measured".
        assert ("held" in by[letter]["word"] or "not measured" in by[letter]["word"]) and by[letter]["note"], by[letter]
    assert "authorisation" in by["H"]["note"] and "reputation source" in by["G"]["note"]
    # Each card sits at the layer the addendum names.
    layers = {"E": "DNS & mail", "A": "Firewall / CDN", "B": "Firewall / CDN", "H": "Firewall / CDN",
              "C": "Origin", "D": "Origin", "I": "Origin", "F": "Page", "G": "Page"}
    assert {k: by[k]["layer"] for k in layers} == layers


@needs_build
def test_the_layers_and_the_ledger_agree(served):
    """Both directions: every ledger entry is drawn in its state, and a card
    the ledger names takes the ledger's state rather than the sweep's."""
    ledger = [{"domain": "A", "status": "assessed"},
              {"domain": "D", "status": "partial", "missing": "login-error probe - pending authorisation"},
              {"domain": "E", "status": "not assessed", "missing": "no resolver"}]
    got = _open(served, ledger)
    by = {c["domain"]: c for c in got["cards"]}
    assert by["A"]["state"] in ("ok", "warn")
    assert by["D"]["state"] == "partial" and "login-error probe" in by["D"]["note"]
    assert by["E"]["state"] == "held" and "no resolver" in by["E"]["note"]
    assert got["verdict"] == "No sign of compromise"
    for entry in ledger:
        card = by[entry["domain"]]
        drawn = {"ok": "assessed", "warn": "assessed", "partial": "partial", "held": "not assessed"}[card["state"]]
        assert drawn == entry["status"], (entry, card)


@needs_build
def test_every_card_states_its_state_in_words(served):
    """WCAG 1.4.1: hollow and hatched are also a word on the card."""
    for card in _open(served)["cards"]:
        assert card["word"].strip(" ·") in ("assessed", "assessed, findings", "partly measured", "held", "not measured"), card


@needs_build
def test_held_checks_split_into_authorisation_and_input_and_the_declined_controls_follow(served):
    """Brief v20 step BD: held checks are lines under two headings - what waits
    on the owner's authorisation, then what waits on an input - and the
    controls the brief declined sit once, muted, under the fixes."""
    from playwright.sync_api import sync_playwright
    base, ids = served
    held = [{"check": "SEC/open-ports", "page": "", "needs": "active_probing_authorised = true on the site record"},
            {"check": "SEC/cloaking", "page": "", "needs": "UA matrix probe bodies were not captured"},
            {"check": "SEC/reputation", "page": "", "needs": "Safe Browsing key on the site record"}]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1200})
        try:
            def anatomy(route):
                data = route.fetch().json()
                for c in data["categories"]:
                    if c["key"] == "security":
                        c["brief_held"] = held
                        c["brief_security"] = {"do_not_spend_on": [{"control": "COOP/COEP", "why": "brochure site"}]}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
            pg.route("**/api/sites/*/anatomy*", anatomy)
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            open_part(pg, 'Security')
            pg.wait_for_selector(".fix-na-head", timeout=15_000)
            got = pg.evaluate("""() => [...document.querySelectorAll('.fix-na-head, .fix-na')]
                .map((e) => [e.className.includes('head') ? 'H' : 'L', e.textContent])""")
            dnso = pg.evaluate("() => [...document.querySelectorAll('.fix-dnso')].map((e) => e.textContent)")
        finally:
            browser.close()
    # Held lines are grouped within each section (Free checks, Analysis), so
    # the claim is per line: each sits under the heading its reason names, and
    # within a section authorisation comes first.
    under = None
    placed = {}
    for kind, text in got:
        if kind == "H":
            under = text
        else:
            placed[text.split(" ")[0]] = under
    assert placed["open-ports"] == "Pending authorisation", got
    # A probe's missing BODIES is an input, not an authorisation.
    assert placed["cloaking"] == "Missing input", got
    assert placed["reputation"] == "Missing input", got
    assert len(dnso) == 1 and "COOP/COEP" in dnso[0]


def test_the_brief_is_told_the_page_checks_were_measured():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "clauditseo" / "analysts" / "expert.py").read_text(encoding="utf-8")
    assert "These eight ARE assessed" in src and "not as not_assessable" in src


@needs_build
def test_pressing_a_layer_card_narrows_the_fix_cards_and_pressing_it_again_clears(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1200})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            open_part(pg, 'Security')
            pg.wait_for_selector(".seclayers", timeout=15_000)
            pg.wait_for_timeout(300)
            read = """() => ({
              cards: [...document.querySelectorAll('[data-fix-check]')].map((e) => e.dataset.fixCheck),
              narrow: document.querySelector('.fix-narrow')?.textContent || null,
              pressed: [...document.querySelectorAll('.seccard[aria-pressed="true"]')].map((e) => e.dataset.domain),
            })"""
            before = pg.evaluate(read)
            assert before["cards"], "the fixture has SEC fix cards"
            got = {}
            for card in pg.query_selector_all(".seccard"):
                card.click()
                pg.wait_for_timeout(150)
                after = pg.evaluate(read)
                got[card.get_attribute("data-domain")] = after
                card.click()
                pg.wait_for_timeout(150)
            cleared = pg.evaluate(read)
        finally:
            browser.close()
    from clauditseo.modules.sec import DOMAINS
    for letter, after in got.items():
        assert after["pressed"] == [letter]
        assert set(after["cards"]) <= set(DOMAINS[letter]["checks"]), (letter, after)
        assert after["narrow"] and f"{len(after['cards'])} of {len(before['cards'])}" in after["narrow"]
    # Every card belongs to some domain, so the narrows together cover them all.
    assert set(before["cards"]) == {c for a in got.values() for c in a["cards"]}
    assert cleared["cards"] == before["cards"] and cleared["narrow"] is None and not cleared["pressed"]


@needs_build
def test_the_hsts_ramp_reads_as_its_steps(served):
    """A brief row's `staged` naming a max-age ramp is drawn as its steps, each
    with the span it means; the text stays beside it. Injected into the site
    payload, because no brief runs in the suite."""
    from playwright.sync_api import sync_playwright
    base, ids = served
    staged = "300 → 86400 → 31536000, each held a week; preload later"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1200})
        try:
            def detail(route):
                data = route.fetch().json()
                sec = [s for s in data["states"] if s.get("dimension") == "SEC"
                       and s.get("state") in ("open", "regressed", "candidate")]
                target = next((s for s in sec if s["check_id"].startswith("hsts")), sec[0])
                target["check_id"] = target["check_id"] if target["check_id"].startswith("hsts") else "hsts-missing"
                target["rollout"] = {"staged": staged, "verify": "curl -sI https://x.test/"}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
            pg.route(lambda url: url.rstrip("/").endswith(f"/api/sites/{ids['site']}"), detail)
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            open_part(pg, 'Security')
            pg.wait_for_selector(".sec-ramp", timeout=15_000)
            got = pg.evaluate("""() => ({
              steps: [...document.querySelectorAll('.sec-ramp li')].map((e) => e.textContent),
              text: document.querySelector('.sec-ramp')?.nextElementSibling?.textContent || null,
            })""")
        finally:
            browser.close()
    assert got["steps"] == ["max-age=300 5 minutes", "max-age=86400 1 day",
                            "max-age=31536000 1 year"], got
    assert got["text"] == staged
