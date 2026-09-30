"""PAGE-J page advisor: bundle construction, validation, caching, and the
API path — all driven by fixture servers and scripted providers, no network
beyond localhost and no tokens."""

from __future__ import annotations

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

import clauditseo.modules  # noqa: F401
from clauditseo import anatomy
from clauditseo.analysts.base import AnalystResponse
from clauditseo.analysts.mock import MockAnalyst
from clauditseo.analysts.page_advisor import (advise_url, build_page_bundle,
                                             parse_advice, scope_advice,
                                             stored_advice, validate_advice)
from clauditseo.api.app import create_app
from clauditseo.config import Settings
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.modules.pagefacts import html_pages
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite

FAST = TierBudget(max_pages=20, request_timeout_s=5, wall_clock_s=30, delay_s=0)

BODY = ("We repair burst pipes and blocked drains across the inner suburbs, "
        "arriving with parts stocked so most jobs finish in a single visit. ")


def _routes() -> dict:
    def page(title, path, body):
        return (f"<html><head><title>{title}</title>"
                f'<meta name="description" content="Description for {path}.">'
                '<meta name="viewport" content="width=device-width">'
                f'<link rel="canonical" href="{path}"></head>'
                f"<body>{body}</body></html>")
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nAllow: /\nDisallow: /blocked/\n"),
        "/": (200, {}, page("Advisor Fixture Home Page", "/",
                            "<h1>Home</h1><p>" + BODY * 3 + "</p>"
                            '<a href="/emergency">emergency</a>')),
        "/emergency": (200, {}, page("Emergency Plumbing Fixture Page", "/emergency",
                                     "<h1>Emergency</h1><p>" + BODY * 4 + "</p>")),
        "/blocked/secret": (200, {}, page("Blocked", "/blocked/secret", "<h1>No</h1>")),
    }


@pytest.fixture
def env(tmp_path):
    server = FixtureSite(_routes()).start()
    conn = connect(tmp_path / "advisor.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Advisor Co")
    site_id = repo.create_site(conn, client, "advisor.fixture")
    crawl_result = crawl(server.base_url + "/", Tier.T2, budget=FAST)
    result = run_audit(Site(domain="advisor.fixture"), crawl_result,
                       ["TEC", "ONP", "CNT"], Tier.T2)
    run_id = runs.create_run(conn, site_id, ["TEC", "ONP", "CNT"], "T2")
    runs.complete_run(conn, run_id, result)
    yield server, conn, site_id, run_id, crawl_result
    server.stop()
    conn.close()


def _cfg() -> Settings:
    return dataclasses.replace(Settings(), anthropic_api_key="")


# --- bundle -----------------------------------------------------------------

def test_bundle_carries_page_siblings_and_its_findings(env):
    server, conn, site_id, run_id, crawl_result = env
    page = next(p for p in html_pages(crawl_result.pages)
                if p.url.endswith("/emergency"))
    bundle = build_page_bundle(page, ["/", "/other"],
                              [{"dimension": "ONP", "check_id": "title-length",
                                "severity": "low", "summary": "x"}],
                              Site(domain="advisor.fixture",
                                   business_type="local-service"))
    assert bundle.payload["page"]["title_tag"] == "Emergency Plumbing Fixture Page"
    assert bundle.payload["page"]["untrusted_page_text"].startswith("Emergency")
    assert bundle.payload["site"]["business_type"] == "local-service"
    assert {"path": "/"} in bundle.payload["site"]["other_page_paths"]
    assert bundle.payload["deterministic_findings_on_this_page"][0]["check_id"] \
        == "title-length"
    assert bundle.payload["keyword_provider_available"] is False


# --- validation -------------------------------------------------------------

def _advice(**over) -> dict:
    base = {"recommended_h1": {"text": "Emergency Plumbing in the Inner Suburbs",
                               "why": "matches the page"},
            "title_tag": {"text": "T", "why": "w"},
            "meta_description": {"text": "M", "why": "w"},
            "alternatives": [], "conflicts": [], "assumptions": []}
    base.update(over)
    return base


def test_validation_rejects_invented_numbers_and_title_duplication(env):
    server, conn, site_id, run_id, crawl_result = env
    page = next(p for p in html_pages(crawl_result.pages)
                if p.url.endswith("/emergency"))
    bundle = build_page_bundle(page, [], [], Site(domain="advisor.fixture"))

    assert validate_advice(_advice(), bundle) == []

    # A fabricated figure in copy destined for the page is rejected...
    invented = _advice(answer_line="Conversions rise 4317 percent.")
    assert any("4317" in p for p in validate_advice(invented, bundle))
    invented_h1 = _advice(recommended_h1={"text": "Trusted by 9821 Businesses",
                                          "why": "w"})
    assert any("9821" in p for p in validate_advice(invented_h1, bundle))
    # ...but craft guidance inside a rationale is not client-facing copy.
    guidance = _advice(recommended_h1={
        "text": "Emergency Plumbing in the Inner Suburbs",
        "why": "Fits comfortably under 60 characters for the SERP display window."})
    assert validate_advice(guidance, bundle) == []

    dupe = _advice(recommended_h1={"text": "Emergency Plumbing Fixture Page",
                                   "why": "same as title"})
    assert any("duplicates the existing title tag" in p
               for p in validate_advice(dupe, bundle))


def test_australian_prose_is_not_read_as_fabricated_numbers(env):
    """Regression: json escaping turned an em dash into \\u2014, which the
    number extractor read as a fabricated 2014 and rejected."""
    server, conn, site_id, run_id, crawl_result = env
    page = next(p for p in html_pages(crawl_result.pages)
                if p.url.endswith("/emergency"))
    bundle = build_page_bundle(page, [], [], Site(domain="advisor.fixture"))
    dashes = _advice(answer_line="Emergency plumbing — arranged quickly — "
                                 "for inner-suburb homeowners.")
    assert validate_advice(dashes, bundle) == []


def test_parse_advice_requires_a_real_h1():
    assert parse_advice("no json here") is None
    assert parse_advice('{"recommended_h1": {"text": "  "}}') is None
    assert parse_advice('{"recommended_h1": {"text": "Good H1", "why": "y"}}')


# --- end to end -------------------------------------------------------------

def test_advise_url_runs_caches_and_respects_robots(env):
    server, conn, site_id, run_id, crawl_result = env
    site = Site(domain="advisor.fixture")
    url = server.base_url + "/emergency"

    first = advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())
    assert first["status"] == "ok"
    assert first["advice"]["recommended_h1"]["text"]
    assert first["cached"] is False

    second = advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())
    assert second["cached"] is True and second["tokens"] == 0

    blocked = advise_url(conn, run_id, server.base_url + "/blocked/secret",
                         site, _cfg(), MockAnalyst())
    assert blocked["status"] == "unavailable"
    assert "robots.txt disallows" in blocked["reason"]
    assert "/blocked/secret" not in server.request_log

    missing = advise_url(conn, run_id, server.base_url + "/nope", site,
                         _cfg(), MockAnalyst())
    assert missing["status"] == "unavailable"


def test_advise_url_without_provider_is_honest(env):
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/", Site(domain="x"),
                     _cfg(), None)
    assert out["status"] == "unavailable" and "ANTHROPIC_API_KEY" in out["reason"]


class RogueAdvisor:
    name = "rogue"
    model_id = "rogue-1"

    def run_agent(self, system, bundle, toolkit, max_tokens, max_output=0):
        return AnalystResponse(findings=[], tokens_in=10, tokens_out=10,
                               text=json.dumps(_advice(
                                   answer_line="Traffic grows 9999 percent.")))


def test_rogue_advice_is_rejected_not_stored(env):
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), RogueAdvisor())
    assert out["status"] == "rejected"
    assert any("9999" in p for p in out["problems"])
    assert conn.execute("SELECT COUNT(*) n FROM analyst_cache"
                        " WHERE model_id='rogue-1'").fetchone()["n"] == 0


def test_advise_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    monkeypatch.setenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", "1")
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "api.db"
    api = TestClient(create_app(db_path=db))
    client_id = api.post("/api/clients", json={"name": "API Advisor Co"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "advisor.fixture"}).json()["id"]

    server = FixtureSite(_routes()).start()
    try:
        launched = api.post(f"/api/sites/{site_id}/audits",
                            json={"dims": ["ONP"], "tier": "T2",
                                  "start_url": server.base_url + "/"})
        run_id = launched.json()["run_id"]
        import time
        for _ in range(100):
            if api.get(f"/api/runs/{run_id}").json()["status"] == "complete":
                break
            time.sleep(0.3)
        resp = api.post(f"/api/runs/{run_id}/advise",
                        json={"url": server.base_url + "/emergency"})
    finally:
        server.stop()
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["advice"]["recommended_h1"]["text"]


# --- scoped to the section being read (FEATURES.md F-03) --------------------
#
# Ordinary tests, not guards: the behaviour did not exist, so there was nothing
# to observe failing first. `FEATURES.md` states that DISCIPLINE rule 1 does not
# apply to a feature, and this says so rather than leaving it to be inferred.


def test_scoped_to_headings_advises_on_headings_and_not_the_meta_description(env):
    """F-03's acceptance signal, first half.

    The operator is reading the Headings section and wants advice about it.
    Today the panel answers with its whole fixed remit — H1, title tag, meta
    description and answer line — and the reader has to find the part that
    belongs to what they were looking at.
    """
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst(),
                     scope="headings")

    assert out["status"] == "ok"
    advice = out["advice"]
    assert advice["recommended_h1"]["text"], "the heading is the subject"
    assert "alternatives" in advice
    assert "meta_description" not in advice, \
        "a meta-description rewrite is not advice about headings"
    assert "title_tag" not in advice
    assert out["scope"] == "headings", "the answer says what it was narrowed to"


def test_a_narrowed_view_still_carries_its_caveats(env):
    """The provenance invariant, applied to narrowing.

    `conflicts` and `assumptions` are what the recommendation rests on. A view
    that dropped them would hand the operator a cleaner-looking answer with the
    reasons it might be wrong removed — which is the failure this repository
    keeps finding, arriving through the feature meant to help.
    """
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst(),
                     scope="headings")

    assert out["advice"]["assumptions"], "an assumption survives narrowing"
    assert out["advice"]["conflicts"], "so does a stated conflict"


def _readable_strings(view: dict) -> set[str]:
    """Every string a narrowed view could actually put in front of the reader.

    Walks one level, because that is how deep the advice shape goes: a top
    level of lists, dicts and scalars. Deliberately not a `json.dumps` and a
    substring search — that is the weak-matching shape this repository has
    shipped a fabricated number through once already.
    """
    out: set[str] = set()
    for value in view.values():
        if isinstance(value, str):
            out.add(value)
        elif isinstance(value, list):
            out |= {v for v in value if isinstance(v, str)}
        elif isinstance(value, dict):
            out |= {v for v in value.values() if isinstance(v, str)}
    return out


@pytest.mark.parametrize("scope", sorted(anatomy.ADVICE_SCOPES))
def test_every_narrowed_view_carries_every_caveat(scope: str):
    """UX-26. The test above asserts the two caveats that already survive.

    `ADVICE_ALWAYS`'s own docstring states the rule this checks: *"These are
    what a recommendation rests on and the reasons it might be wrong. A view
    that dropped them would hand back a tidier answer with its caveats
    removed, which is the provenance invariant broken by the feature meant to
    make the answer easier to read."* The tuple did not hold to it. The system
    prompt reserves two further fields for exactly that job — `compliance_notes`
    for "medical, financial or safety outcome claims"
    (`page_advisor.py:60-75`), dropped by **all three** scopes, and
    `keyword_intent.unverified_flags` for brand-coined categories and slogans,
    absent from `title-desc` and `headings` — and both were removed by the
    narrowing on a product whose named users audit lender and finance sites.

    **The assertion is on the caveat text, not on a field name**, so it does
    not encode one remedy. Whether the flag arrives as part of `keyword_intent`
    or is one day split out into its own key, a view that can still show the
    sentence passes and a view that cannot fails.

    Parametrised over `ADVICE_SCOPES` rather than over the three names known
    when this was written: a fourth scope added without a caveat is then a red
    test rather than a silent hole (DISCIPLINE rule 3).
    """
    compliance = ("Finance page: soften the undocumented outcome claim to a "
                  "capability claim before publishing.")
    unverified = ("“Rapid Capital Unlock” is a brand-coined category "
                  "with no verified search demand.")
    full = {
        "assumptions": ["Demand is assumed: no keyword provider is configured."],
        "conflicts": ["The parent page targets the same cluster."],
        "triage": {"commercial": True, "multi_page": True, "ymyl": True,
                   "search_facing": True, "note": "lender, YMYL"},
        "page_read": {"page_type": "service", "primary_topic": "business loans",
                      "audience": "SME owners", "intent": "commercial",
                      "alignment": "aligned"},
        "site_role": None,
        "keyword_intent": {"head_term": "business loans", "demand": "unknown",
                           "unverified_flags": unverified,
                           "verdict": "validate before implementing"},
        "recommended_h1": {"text": "Business loans", "why": "matches the page"},
        "answer_line": "Business loans for Australian SMEs.",
        "title_tag": {"text": "Business loans", "why": "matches the page"},
        "meta_description": {"text": "Business loans.", "why": "short"},
        "alternatives": [],
        "schema_notes": None,
        "compliance_notes": [compliance],
    }
    readable = _readable_strings(scope_advice(full, scope))
    for caveat, why in ((compliance, "a compliance note"),
                        (unverified, "an unverified-demand flag")):
        assert caveat in readable, (
            f"scope {scope!r} drops {why}: a stated limitation on a displayed "
            f"recommendation is removed from rendered text by the feature that "
            f"narrows it. Kept in the view: {sorted(scope_advice(full, scope))}")


def test_no_scope_returns_the_full_remit_exactly_as_before(env):
    """F-03's acceptance signal, second half — and the regression risk. The
    unscoped call is the one every existing caller makes."""
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst())

    advice = out["advice"]
    for field in ("recommended_h1", "title_tag", "meta_description",
                  "answer_line", "alternatives"):
        assert field in advice, f"{field} is part of the unscoped remit"
    assert out["scope"] is None


def test_a_scope_the_advisor_does_not_cover_is_refused_not_ignored(env):
    """The negative case, and the reason it matters.

    `a11y` is a real category on the same screen, and the page advisor does not
    cover it. Ignoring an unrecognised scope would return the full remit and
    read as though the narrowing had worked — the operator would believe they
    were reading accessibility advice from a tool that never judged it.
    """
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst(),
                     scope="a11y")

    assert out["status"] == "rejected"
    assert "a11y" in " ".join(out["problems"])
    assert "advice" not in out, "a refused scope returns no advice at all"


def test_an_unknown_scope_is_refused_before_the_model_is_called(env):
    """A typo must not cost a model call, and must not be answered."""
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst(),
                     scope="headnigs")

    assert out["status"] == "rejected"
    assert out.get("tokens", 0) == 0


def test_a_scope_is_a_view_over_one_judgement_not_a_second_call(env):
    """Deliberate design, recorded because it is not the obvious choice.

    Narrowing happens at the boundary, not in the prompt, so one judgement
    serves every section and a scoped read costs nothing once any read has run.
    The alternative — a scoped prompt — would fragment the cache by section and
    charge the operator again for each one.
    """
    server, conn, site_id, run_id, crawl_result = env
    site, url = Site(domain="advisor.fixture"), server.base_url + "/emergency"

    full = advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())
    assert full["cached"] is False

    scoped = advise_url(conn, run_id, url, site, _cfg(), MockAnalyst(),
                        scope="title-desc")
    assert scoped["cached"] is True and scoped["tokens"] == 0
    assert scoped["advice"]["meta_description"]["text"]
    assert "recommended_h1" not in scoped["advice"]


def test_running_the_specialist_from_a_finding_answers_that_finding(env):
    """FEATURES.md F-02's acceptance signal, end to end.

    Invoked from a findings row, the specialist runs against that finding's
    check and page, and the judgement names the same `check_id` — so the row
    can show that the answer belongs to it rather than to the page.
    """
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst(),
                     check_id="heading-skip")

    assert out["status"] == "ok"
    assert out["check_id"] == "heading-skip", "the judgement names its finding"
    assert out["scope"] == "headings", "the finding named its own scope"
    assert out["advice"]["recommended_h1"]["text"]
    assert "meta_description" not in out["advice"]


def test_the_page_advisor_refuses_a_finding_another_tool_owns(env):
    """A control that ran the wrong tool would return a real, fluent judgement
    about something other than what was clicked. Refused before the model."""
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst(),
                     check_id="jsonld-invalid")

    assert out["status"] == "rejected"
    assert out["check_id"] == "jsonld-invalid"
    assert "schema-auditor" in " ".join(out["problems"])
    assert out["tokens"] == 0
    assert "advice" not in out


def test_a_finding_nothing_judges_is_refused_not_answered_about_the_page(env):
    server, conn, site_id, run_id, crawl_result = env
    out = advise_url(conn, run_id, server.base_url + "/emergency",
                     Site(domain="advisor.fixture"), _cfg(), MockAnalyst(),
                     check_id="not-https")

    assert out["status"] == "rejected"
    assert "no specialist judges" in " ".join(out["problems"])
    assert "advice" not in out


def test_every_scope_the_map_offers_is_a_category_the_tool_claims():
    """Declared, not computed — the convention `DIMENSION_CATEGORIES` follows.

    If `page-advisor` gains or loses a category in `TOOL_CATEGORIES`, this
    fails rather than leaving a section that silently offers nothing or a scope
    that narrows to a category the screen never shows.
    """
    from clauditseo import anatomy

    assert set(anatomy.ADVICE_SCOPES) == set(anatomy.TOOL_CATEGORIES["page-advisor"])
    for fields in anatomy.ADVICE_SCOPES.values():
        assert fields, "a scope that keeps no field would return an empty answer"


# --- read back what was already produced (FEATURES.md F-04) -----------------
#
# Ordinary tests, not guards: the read-back did not exist before this feature,
# so there was nothing to observe failing first. `FEATURES.md` states that
# DISCIPLINE rule 1 does not apply to a feature, and this says so rather than
# leaving it to be inferred. Written with the feature and red until it landed.


def _costs(conn, run_id) -> int:
    return conn.execute("SELECT COUNT(*) n FROM cost_entries WHERE run_id=?",
                        (run_id,)).fetchone()["n"]


class ExplodingAdvisor:
    """A provider that fails the test if anything reaches it.

    `stored_advice` takes no provider argument at all, so a test could "prove"
    it never calls one by reading the signature — which is structure, not
    evidence (DISCIPLINE rule 4). This exists for the `advise_url` half of the
    same claim, where a provider genuinely is in scope.
    """
    model_id = "must-not-be-called"

    def run_agent(self, *a, **kw):
        raise AssertionError("the provider was called for advice already produced")

    def analyse(self, *a, **kw):
        raise AssertionError("the provider was called for advice already produced")


def test_advice_already_produced_is_read_back_without_calling_the_provider(env):
    """F-04's acceptance signal, first clause and the measurement of the second.

    The operator generated advice, moved to another section and back, and was
    offered "Advise on this page" again as though nothing had been made. The
    judgement did survive — in `analyst_cache` — but that key is a hash of a
    bundle assembled from a live fetch, so asking whether a hit existed cost
    the fetch, and `PageAdvice` had no mount-time read at all.
    """
    server, conn, site_id, run_id, crawl_result = env
    site, url = Site(domain="advisor.fixture"), server.base_url + "/emergency"

    produced = advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())
    assert produced["status"] == "ok" and produced["cached"] is False
    costs_after_producing = _costs(conn, run_id)
    assert costs_after_producing > 0, "producing advice charges for it"

    read = stored_advice(conn, run_id, url)

    assert read["status"] == "ok"
    assert read["stored"] is True
    assert read["tokens"] == 0, "second clause: measured as zero tokens"
    assert _costs(conn, run_id) == costs_after_producing, \
        "second clause: and no new cost entry"
    assert read["advice"]["recommended_h1"]["text"] == \
        produced["advice"]["recommended_h1"]["text"], \
        "first clause: it shows that advice, not a different one"


def test_a_section_with_no_advice_offers_to_generate_it(env):
    """F-04's third clause. Absent is a real answer, not an error and not an
    empty judgement: the panel renders `none` as the offer to generate, which
    is what it showed before this feature existed."""
    server, conn, site_id, run_id, crawl_result = env

    read = stored_advice(conn, run_id, server.base_url + "/emergency")

    assert read["status"] == "none"
    assert read["tokens"] == 0
    assert "advice" not in read
    assert _costs(conn, run_id) == 0, "asking cost nothing"


def test_the_read_back_survives_the_page_being_edited(env):
    """Why the row is keyed on (run, url) and not on the evidence hash.

    The workflow F-04 exists for is: read the advice, change the page, come
    back. A read-back keyed on `analyst_cache` would go blank at exactly that
    moment, because the bundle hash is taken over the page's own content —
    which is what ruled that option out. This edits the page under the advisor
    and reads again.
    """
    server, conn, site_id, run_id, crawl_result = env
    url = server.base_url + "/emergency"
    advise_url(conn, run_id, url, Site(domain="advisor.fixture"), _cfg(),
               MockAnalyst())

    server.routes["/emergency"] = (
        200, {}, "<html><head><title>Rewritten After Advice</title></head>"
                 "<body><h1>Rewritten</h1><p>" + BODY * 4 + "</p></body></html>")

    read = stored_advice(conn, run_id, url)
    assert read["status"] == "ok", \
        "the advice belongs to the run's page and outlives an edit to it"
    assert read["tokens"] == 0


def test_a_read_back_is_narrowed_to_the_section_asking(env):
    """F-03 and F-04 together, and the reason the stored row holds the full
    remit. Narrowing is a view taken on the way out; if the scoped answer were
    what got stored, re-entering a different section would read a judgement
    with its own fields missing."""
    server, conn, site_id, run_id, crawl_result = env
    url = server.base_url + "/emergency"
    advise_url(conn, run_id, url, Site(domain="advisor.fixture"), _cfg(),
               MockAnalyst(), scope="headings")

    headings = stored_advice(conn, run_id, url, scope="headings")
    assert headings["advice"]["recommended_h1"]["text"]
    assert "meta_description" not in headings["advice"]

    title_desc = stored_advice(conn, run_id, url, scope="title-desc")
    assert title_desc["advice"]["meta_description"]["text"], \
        "stored wide, so the section that did not produce it still reads"
    assert "recommended_h1" not in title_desc["advice"]

    assert _costs(conn, run_id) == 1, "one judgement, three reads, one charge"


def test_the_read_back_refuses_a_finding_another_tool_owns(env):
    """The two paths share one resolver. A GET that answered in the full remit
    where the POST refuses would show fluent advice about a check this tool
    never judged, with nothing on screen to say so."""
    server, conn, site_id, run_id, crawl_result = env
    url = server.base_url + "/emergency"
    advise_url(conn, run_id, url, Site(domain="advisor.fixture"), _cfg(),
               MockAnalyst())

    read = stored_advice(conn, run_id, url, check_id="jsonld-invalid")

    assert read["status"] == "rejected"
    assert "schema-auditor" in " ".join(read["problems"])
    assert "advice" not in read


def test_a_read_back_from_a_finding_answers_in_that_findings_scope(env):
    server, conn, site_id, run_id, crawl_result = env
    url = server.base_url + "/emergency"
    advise_url(conn, run_id, url, Site(domain="advisor.fixture"), _cfg(),
               MockAnalyst())

    read = stored_advice(conn, run_id, url, check_id="heading-skip")

    assert read["status"] == "ok"
    assert read["scope"] == "headings", "the finding named its own scope"
    assert read["check_id"] == "heading-skip"
    assert "meta_description" not in read["advice"]


def test_re_advising_replaces_the_row_rather_than_accumulating(env):
    """The `expert_reports` precedent (migration 0005), followed deliberately:
    one row per page per run. History would make "what is this page advised"
    ambiguous on the one screen that asks it."""
    server, conn, site_id, run_id, crawl_result = env
    url = server.base_url + "/emergency"
    site = Site(domain="advisor.fixture")

    advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())
    advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())

    rows = conn.execute("SELECT COUNT(*) n FROM page_advice WHERE run_id=?"
                        " AND url=?", (run_id, url)).fetchone()["n"]
    assert rows == 1


def test_advice_reached_through_the_cache_is_still_readable_back(env):
    """The evidence cache and the read-back table answer different questions,
    so the cache-hit path has to write the row as well.

    Advice that arrives as an `analyst_cache` hit never reaches the code that
    stores against the run, unless that path stores too — and the panel would
    then offer to generate what it had just displayed. The row is deleted here
    to put the next call on the cache path deliberately, because the bundle
    carries the run's own findings and a second run therefore misses the cache
    rather than hitting it.
    """
    server, conn, site_id, run_id, crawl_result = env
    url = server.base_url + "/emergency"
    site = Site(domain="advisor.fixture")

    advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())
    with conn:
        conn.execute("DELETE FROM page_advice WHERE run_id=? AND url=?",
                     (run_id, url))
    assert stored_advice(conn, run_id, url)["status"] == "none"
    charged = _costs(conn, run_id)

    hit = advise_url(conn, run_id, url, site, _cfg(), MockAnalyst())
    assert hit["cached"] is True and hit["tokens"] == 0

    read = stored_advice(conn, run_id, url)
    assert read["status"] == "ok"
    assert read["advice"]["recommended_h1"]["text"]
    assert _costs(conn, run_id) == charged, "a cache hit was never charged for"


def test_read_back_endpoint_costs_the_operator_nothing(tmp_path, monkeypatch):
    """F-04's signal at the boundary the dashboard actually calls.

    The panel reads on mount, so this is the request the operator makes every
    time they re-enter a section — measured through the API rather than
    through the function beneath it, and against the cost ledger rather than
    against the envelope's own account of itself.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    monkeypatch.setenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", "1")
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "readback.db"
    api = TestClient(create_app(db_path=db))
    client_id = api.post("/api/clients", json={"name": "Readback Co"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "advisor.fixture"}).json()["id"]

    server = FixtureSite(_routes()).start()
    try:
        run_id = api.post(f"/api/sites/{site_id}/audits",
                          json={"dims": ["ONP"], "tier": "T2",
                                "start_url": server.base_url + "/"}).json()["run_id"]
        import time
        for _ in range(100):
            if api.get(f"/api/runs/{run_id}").json()["status"] == "complete":
                break
            time.sleep(0.3)
        url = server.base_url + "/emergency"

        before = api.get(f"/api/runs/{run_id}/advice", params={"url": url})
        assert before.status_code == 200
        assert before.json()["status"] == "none", \
            "nothing produced yet: the panel offers to generate"

        produced = api.post(f"/api/runs/{run_id}/advise", json={"url": url})
        assert produced.status_code == 200 and produced.json()["status"] == "ok"

        ledger = connect(db)
        spent = _costs(ledger, run_id)
        assert spent > 0, "producing it was charged for"

        after = api.get(f"/api/runs/{run_id}/advice", params={"url": url})
        unchanged = _costs(ledger, run_id)
        ledger.close()
    finally:
        server.stop()

    assert after.status_code == 200
    body = after.json()
    assert body["status"] == "ok" and body["stored"] is True
    assert body["tokens"] == 0
    assert body["advice"]["recommended_h1"]["text"] == \
        produced.json()["advice"]["recommended_h1"]["text"]
    assert unchanged == spent, \
        "no new cost entry: the ledger the operator is billed from is unmoved"
