"""Two brief rules the contract now enforces rather than trusts (items 216, 217).

**216.** The URLs brief says `url-rename` is the only check that proposes
changing a live URL, that a rename needs at most RENAME_INLINK_CAP inlinks,
and that no target is invented. The parser trusted all three to the model. On
twenty22 a `url-slug-not-descriptive` row carried "301 /web-design1/ to
/web-design/; update 45 internal links" with a `copy change` button, directly
under the `url-rename` row for the same page saying "inlinks 45 > cap 20 ...
keep". A client acting on the one copyable URL change on the page would have
301'd a 45-inlink page.

**217.** Speed analysis rows are per template (`page: null`, `template`
set). `_path("")` is "/", so every one was filed on the home page and drawn as
a home-page card - a 1.8 s TTFB and a logo LCP on a page whose own trace
reads 560 ms and a 951 KB photograph.

The target half of 216 is narrowed from the filing, and says why in
`contract._rename_target_is_live`: a rename's target is new by definition, so
"the crawl must know it" would hold every honest rename. A target that is
already a live page is what gets held.
"""

from __future__ import annotations

import json

from clauditseo.analysts import contract

BASE = "https://t.fixture"
PAGES = [BASE + "/", BASE + "/web-design1/", BASE + "/new-page-2/",
         BASE + "/seo/on-page/meta-descriptions/", BASE + "/webdesign/"]
URL_CHECKS = ["TEC/url-slug-not-descriptive", "TEC/url-rename"]


def _parse(rows, checks, rules=None):
    block = json.dumps({"rows": rows})
    return contract.parse("```json\n" + block + "\n```\n", checks, PAGES, rules=rules)


def _rules(inlinks):
    return contract.Rules(inlinks=inlinks, rename_cap=20,
                          live_paths={contract._path(p) for p in PAGES})


def _row(check, page, replacement, kind=None):
    r = {"check": check, "page": page, "status": "FAIL", "severity": "MEDIUM",
         "evidence": "x", "replacement": replacement, "note": ""}
    if kind:
        r["kind"] = kind
    return r


def test_a_rename_from_any_check_but_url_rename_keeps_its_finding_and_loses_its_copy():
    got = _parse([_row("TEC/url-slug-not-descriptive", "/web-design1/",
                       "/web-design/, 301 /web-design1/ to /web-design/; update 45 internal links",
                       kind="rename")],
                 URL_CHECKS, _rules({"/web-design1": 45}))
    assert len(got.rows) == 1, "the finding is real; only its rename is refused"
    row = got.rows[0]
    assert row.replacement is None, f"a 301 is still offered to copy: {row.replacement!r}"
    assert row.kind == "convention"
    assert "only url-rename" in row.note, row.note


def test_a_rename_over_the_inlink_cap_is_forced_to_keep():
    got = _parse([_row("TEC/url-rename", "/web-design1/",
                       "/web-design/ — 301 /web-design1/ → /web-design/; update 45 internal links",
                       kind="rename")],
                 URL_CHECKS, _rules({"/web-design1": 45}))
    row = got.rows[0]
    assert row.replacement.startswith("keep"), row.replacement
    assert "45 inlinks" in row.replacement and "cap of 20" in row.replacement, row.replacement


def test_a_rename_under_the_cap_to_a_new_path_stands():
    """The prompt's own example: an honest rename must still get through, or
    the rule is a mute button."""
    rep = "/event-styling/ — 301 /new-page-2 → /event-styling/; update 3 internal links"
    got = _parse([_row("TEC/url-rename", "/new-page-2/", rep, kind="rename")],
                 URL_CHECKS, _rules({"/new-page-2": 3}))
    assert got.rows and got.rows[0].replacement == rep, got.rows


def test_a_rename_onto_a_page_that_is_already_live_is_held():
    got = _parse([_row("TEC/url-rename", "/web-design1/",
                       "/webdesign/ — 301 /web-design1/ → /webdesign/", kind="rename")],
                 URL_CHECKS, _rules({"/web-design1": 3}))
    assert not got.rows, got.rows
    held = [n for n in got.not_assessable if n["check"] == "TEC/url-rename"]
    assert held and "already a live page" in held[0]["needs"], got.not_assessable


def test_without_the_crawl_the_cap_is_not_guessed():
    """No evidence, no inlink counts: the cap rule is off rather than
    applied to a number the model wrote."""
    rep = "/web-design/ — 301 /web-design1/ → /web-design/"
    got = _parse([_row("TEC/url-rename", "/web-design1/", rep, kind="rename")],
                 URL_CHECKS, contract.Rules())
    assert got.rows[0].replacement == rep


SPEED = ["PRF/ttfb-slow"]


def test_a_per_template_row_is_filed_on_its_templates_page_not_the_home_page():
    row = {"check": "PRF/ttfb-slow", "page": None, "template": "/seo/on-page/<slug>/",
           "status": "FAIL", "severity": "MEDIUM", "evidence": "TTFB 1793 ms",
           "replacement": "cache the template", "note": ""}
    got = _parse([row], SPEED)
    assert got.rows, got.dropped
    assert got.rows[0].page == BASE + "/seo/on-page/meta-descriptions/", got.rows[0].page
    assert got.rows[0].extra.get("template") == "/seo/on-page/<slug>/", (
        "the template the row was written against is not kept with it")


def test_the_display_form_of_a_template_resolves_too():
    assert contract.template_page("/seo/*/*", PAGES) == BASE + "/seo/on-page/meta-descriptions/"


def test_a_template_no_page_matches_is_dropped_not_filed_on_the_home_page():
    row = {"check": "PRF/ttfb-slow", "page": None, "template": "/shop/<slug>/",
           "status": "FAIL", "severity": "MEDIUM", "evidence": "x",
           "replacement": "y", "note": ""}
    got = _parse([row], SPEED)
    assert not got.rows, f"a template with no page was filed somewhere: {got.rows}"
    assert any("matches no page" in d["reason"] for d in got.dropped), got.dropped


def test_a_row_that_names_its_page_is_untouched():
    row = {"check": "PRF/ttfb-slow", "page": "/", "status": "FAIL", "severity": "MEDIUM",
           "evidence": "x", "replacement": "y", "note": ""}
    got = _parse([row], SPEED)
    assert got.rows and got.rows[0].page == BASE + "/", got.rows
