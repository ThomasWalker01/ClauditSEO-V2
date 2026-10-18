"""The Places provider and how its result reaches the local briefs.

The property that matters most is the match check. Places is a text search
that will return a plausible neighbour, and a local audit built on the wrong
business is worse than one built on nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

from clauditseo.analysts.expert import build_context
from clauditseo.config import Settings
from clauditseo.engine.types import Site
from clauditseo.providers.base import NotConfigured
from clauditseo.providers.google import PlacesProfile

EVIDENCE = {"start_url": "https://roofco.test/",
            "pages": [{"url": "https://roofco.test/", "status": 200,
                       "content_type": "text/html", "title": "Roof Co",
                       "nap_mentions": [], "local_schema": []}]}


def _profile(**over):
    base = {"match": "confirmed by website", "name": "Roof Co",
            "address": "1 Test St, Melbourne VIC 3000", "phone": "(03) 9111 2222",
            "phone_international": "+61 3 9111 2222", "website": "https://roofco.test/",
            "primary_category": "Roofing contractor",
            "categories": ["roofing_contractor"],
            "hours": ["Monday: 7:00 am - 4:30 pm"], "rating": 4.8,
            "review_count": 77, "status": "OPERATIONAL",
            "maps_url": "https://maps.google.com/?cid=1"}
    return {**base, **over}


def test_provider_reports_unconfigured_rather_than_guessing():
    provider = PlacesProfile(dataclasses.replace(Settings(), places_api_key=""))
    assert provider.available() is False
    with pytest.raises(NotConfigured):
        provider.lookup("anything")


def test_host_comparison_ignores_www_and_scheme():
    assert PlacesProfile._host("https://www.roofco.test/x") == "roofco.test"
    assert PlacesProfile._host("roofco.test") == "roofco.test"
    assert PlacesProfile._host("") == ""


def test_a_confirmed_listing_fills_the_profile_fields():
    ctx = build_context("gbp-audit", EVIDENCE, Site(domain="roofco.test"),
                        places=_profile())
    assert ctx["LISTED_NAME"] == "Roof Co"
    assert ctx["PRIMARY_CATEGORY"] == "Roofing contractor"
    assert "1 Test St" in ctx["NAP_DETAILS"] and "(03) 9111 2222" in ctx["NAP_DETAILS"]
    assert "Monday" in ctx["HOURS"]
    assert "77 reviews" in ctx["REVIEWS_DATA"]
    # Aggregate only: the public record cannot show response rate or recency.
    assert "no individual reviews" in ctx["REVIEWS_DATA"]
    # Still honest about what Places cannot see.
    for pillar in ("POSTS_DATA", "PHOTOS_DATA", "QA_DATA", "ATTRIBUTES"):
        assert "[NOT SUPPLIED]" in ctx[pillar]
    assert "PUBLIC view" in ctx["KEY_PAGES"]


def test_an_unconfirmed_listing_is_never_used_as_profile_data():
    """A neighbouring business matched by name would otherwise be audited as
    if it were the client's."""
    other = _profile(match="unconfirmed", name="Rival Roofing",
                     website="https://rival.test/")
    ctx = build_context("gbp-audit", EVIDENCE, Site(domain="roofco.test"),
                        places=other)
    assert "[NOT SUPPLIED]" in ctx["LISTED_NAME"]
    assert "[NOT SUPPLIED]" in ctx["NAP_DETAILS"]
    assert "[NOT SUPPLIED]" in ctx["PRIMARY_CATEGORY"]
    # It is shown, flagged, and explicitly barred from carrying a finding.
    assert "UNCONFIRMED" in ctx["KEY_PAGES"]
    assert "may be a different business" in ctx["KEY_PAGES"]
    assert "No finding may rest on it" in ctx["KEY_PAGES"]


def test_review_brief_gets_the_aggregate_but_not_a_series():
    ctx = build_context("review-signals", EVIDENCE, Site(domain="roofco.test"),
                        places=_profile())
    assert "4.8 from 77 reviews" in ctx["REVIEW_EXPORT"]
    assert "a total, not a series" in ctx["REVIEW_EXPORT"]
    assert "velocity" in ctx["REVIEW_EXPORT"]


def test_citations_brief_treats_google_as_one_record_not_a_directory_sweep():
    ctx = build_context("citations-nap", EVIDENCE, Site(domain="roofco.test"),
                        places=_profile())
    assert "every other directory remains unchecked" in ctx["LISTING_DATA"]
    assert "Roof Co" in ctx["LISTING_DATA"]


def test_no_places_key_leaves_the_briefs_exactly_as_they_were():
    ctx = build_context("gbp-audit", EVIDENCE, Site(domain="roofco.test"), places={})
    assert "[NOT SUPPLIED]" in ctx["LISTED_NAME"]
    assert "GOOGLE PLACES" not in ctx["KEY_PAGES"]


def test_admin_lists_places_with_where_to_set_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    body = TestClient(create_app(db_path=tmp_path / "places.db")).get("/api/admin").json()
    # Against the prefix constant, not a literal. A hard-coded name here is
    # part of why this screen went on advertising the old product's variables
    # after the rename: the test agreed with the stale string and stayed green.
    from clauditseo.config import PREFIX
    assert body["providers"]["Places"]["env"] == PREFIX + "PLACES_KEY"
    assert "Billed per request" in body["providers"]["Places"]["detail"]


# --- item 167: the operator confirms the listing -----------------------------

#: Three candidates as `places:searchText` returns them. The client's own
#: listing carries no website, so a website match can never confirm it; the
#: third names the domain but is a different branch's listing.
SEARCH = {"places": [
    {"id": "ChIJrival", "displayName": {"text": "Rival Roofing"},
     "formattedAddress": "9 Other St, Melbourne VIC 3000",
     "nationalPhoneNumber": "(03) 9000 0000", "websiteUri": "https://rival.test/",
     "rating": 3.1, "userRatingCount": 12},
    {"id": "ChIJroofco", "displayName": {"text": "Roof Co"},
     "formattedAddress": "1 Test St, Melbourne VIC 3000",
     "nationalPhoneNumber": "(03) 9111 2222",
     "primaryTypeDisplayName": {"text": "Roofing contractor"},
     "types": ["roofing_contractor"],
     "regularOpeningHours": {"weekdayDescriptions": ["Monday: 7:00 am - 4:30 pm"]},
     "rating": 4.8, "userRatingCount": 77, "businessStatus": "OPERATIONAL"},
    {"id": "ChIJbranch", "displayName": {"text": "Roof Co Geelong"},
     "formattedAddress": "5 Bay St, Geelong VIC 3220",
     "websiteUri": "https://www.roofco.test/geelong", "rating": 4.0,
     "userRatingCount": 5},
]}


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


@pytest.fixture
def places_api(monkeypatch):
    """The Places API as a fixture: no request leaves the process, and the
    call count proves it was the fixture that answered."""
    calls = []

    def post(url, **kw):
        calls.append(kw["json"])
        return _Resp(SEARCH)
    monkeypatch.setattr("clauditseo.providers.google.httpx.post", post)
    return calls


def _provider():
    return PlacesProfile(dataclasses.replace(Settings(), places_api_key="fixture"))


def test_lookup_returns_every_candidate_it_chose_between(places_api):
    got = _provider().lookup("roof co melbourne", expect_domain="nowhere.test")
    assert got["match"] == "unconfirmed" and got["candidates_returned"] == 3
    assert [c["place_id"] for c in got["candidates"]] == ["ChIJrival", "ChIJroofco", "ChIJbranch"]
    assert set(got["candidates"][1]) == {"place_id", "name", "address", "phone", "website"}
    assert got["candidates"][1]["website"] is None
    assert got["confirmed_place_id_not_returned"] is None


def test_the_operators_listing_is_chosen_ahead_of_a_website_match(places_api):
    """The branch names the domain; the operator's pick is the client's own."""
    got = _provider().lookup("roof co", expect_domain="roofco.test",
                             confirmed_place_id="ChIJroofco")
    assert got["match"] == "confirmed by operator"
    assert got["place_id"] == "ChIJroofco" and got["name"] == "Roof Co"
    # Without the confirmation the website check still behaves as it did.
    assert _provider().lookup("roof co", expect_domain="roofco.test")["match"] == "confirmed by website"


def test_a_confirmed_listing_the_search_stops_returning_clears_nothing_and_says_so(places_api):
    got = _provider().lookup("roof co", expect_domain="nowhere.test",
                             confirmed_place_id="ChIJclosed")
    assert got["match"] == "unconfirmed"
    assert got["confirmed_place_id_not_returned"] == "ChIJclosed"
    block = build_context("gbp-audit", EVIDENCE, Site(domain="roofco.test"),
                          places=got)["KEY_PAGES"]
    assert "UNCONFIRMED" in block and "ChIJclosed" in block
    assert "may have moved or closed" in block


def test_the_unconfirmed_block_lists_the_candidates_the_operator_acts_on(places_api):
    got = _provider().lookup("roof co", expect_domain="nowhere.test")
    block = build_context("gbp-audit", EVIDENCE, Site(domain="roofco.test"),
                          places=got)["KEY_PAGES"]
    assert "[TO CONFIRM:" in block and "No finding may rest on it" in block
    for name in ("Rival Roofing", "Roof Co —", "Roof Co Geelong"):
        assert name in block
    assert "no website listed" in block


def test_the_confirmed_block_names_its_actual_basis():
    by_site = build_context("gbp-audit", EVIDENCE, Site(domain="roofco.test"),
                            places=_profile())["KEY_PAGES"]
    by_operator = build_context("gbp-audit", EVIDENCE, Site(domain="roofco.test"),
                                places=_profile(match="confirmed by operator"))["KEY_PAGES"]
    assert "Matched by website" in by_site
    assert "Confirmed by the operator" in by_operator and "Matched by website" not in by_operator


def _site(tmp_path, confirmed=None):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo
    conn = connect(tmp_path / "gbp.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Roof Co"), "roofco.test")
    if confirmed:
        conn.execute("UPDATE sites SET gbp_confirmed_place_id=? WHERE id=?", (confirmed, site_id))
        conn.commit()
    return conn, repo.site_record(repo.get_site(conn, site_id))


@pytest.mark.parametrize("confirmed", [None, "ChIJroofco"])
def test_accept_a_listing_with_no_website_confirmed_once_reaches_all_four_consumers(
        tmp_path, monkeypatch, places_api, confirmed):
    """The item's accept criterion. The client's listing has no website, so
    before confirmation all four consumers are empty; after it, all four are
    populated — on the next run, from the site record, without asking again."""
    from clauditseo.api.app import _places_profile, _snapshot_review_metrics
    # Without the branch: no candidate names the domain, so nothing but the
    # operator can confirm the client's listing.
    monkeypatch.setitem(SEARCH, "places", SEARCH["places"][:2])
    conn, row = _site(tmp_path, confirmed)
    # PLACE_QUERY narrows the search; the verdict is the confirmation's.
    places = _places_profile(dataclasses.replace(Settings(), places_api_key="fixture"),
                             row, {"PLACE_QUERY": "roof co melbourne"})
    assert places_api[-1]["textQuery"] == "roof co melbourne"
    site = Site(domain="roofco.test")
    gbp = build_context("gbp-audit", EVIDENCE, site, places=places)
    reviews = build_context("review-signals", EVIDENCE, site, places=places)
    _snapshot_review_metrics(conn, row["id"], places)
    snapshots = {r["metric_key"]: r["value"] for r in conn.execute(
        "SELECT metric_key, value FROM metric_snapshots WHERE site_id=?", (row["id"],))}
    if confirmed is None:
        assert places["match"] == "unconfirmed"
        assert "UNCONFIRMED" in gbp["KEY_PAGES"]
        assert "[NOT SUPPLIED]" in gbp["LISTED_NAME"]
        assert "An aggregate is available" not in reviews["REVIEW_EXPORT"]
        assert snapshots == {}
    else:
        assert places["match"] == "confirmed by operator"
        assert "Confirmed by the operator" in gbp["KEY_PAGES"]
        assert gbp["LISTED_NAME"] == "Roof Co"
        assert "(03) 9111 2222" in gbp["NAP_DETAILS"]
        assert "4.8 from 77 reviews" in reviews["REVIEW_EXPORT"]
        assert snapshots == {"gbp.review_count": 77.0, "gbp.rating": 4.8}


def test_the_confirm_route_stores_only_a_candidate_the_lookup_returned(tmp_path, monkeypatch, places_api):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import _places_profile, _remember_places_lookup, create_app
    from clauditseo.db.connection import connect
    from clauditseo.persistence import repo
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    http = TestClient(create_app(db_path=tmp_path / "confirm.db"))
    client = http.post("/api/clients", json={"name": "Roof Co"}).json()
    site_id = http.post(f"/api/clients/{client['id']}/sites", json={"domain": "roofco.test"}).json()["id"]

    # Before any lookup there is nothing to confirm from.
    refused = http.put(f"/api/sites/{site_id}/gbp-listing", json={"place_id": "ChIJroofco"})
    assert refused.status_code == 422 and "candidates" in refused.text

    conn = connect(tmp_path / "confirm.db")
    row = repo.site_record(repo.get_site(conn, site_id))
    places = _places_profile(dataclasses.replace(Settings(), places_api_key="fixture"), row, None)
    _remember_places_lookup(conn, site_id, places)
    record = http.get(f"/api/sites/{site_id}/record").json()
    assert [c["place_id"] for c in record["gbp_last_lookup"]["candidates"]] == \
        ["ChIJrival", "ChIJroofco", "ChIJbranch"]
    assert record["gbp_confirmed_place_id"] is None

    assert http.put(f"/api/sites/{site_id}/gbp-listing",
                    json={"place_id": "ChIJsomeoneelse"}).status_code == 422
    ok = http.put(f"/api/sites/{site_id}/gbp-listing", json={"place_id": "ChIJroofco"})
    assert ok.status_code == 200 and ok.json()["gbp_confirmed_place_id"] == "ChIJroofco"
    # The site patch does not carry the field, so re-saving the record form
    # cannot clear a confirmation behind the operator's back.
    assert http.put(f"/api/sites/{site_id}", json={"brand": "Roof Co"}).status_code == 200
    assert http.get(f"/api/sites/{site_id}/record").json()["gbp_confirmed_place_id"] == "ChIJroofco"
    cleared = http.put(f"/api/sites/{site_id}/gbp-listing", json={"place_id": ""})
    assert cleared.status_code == 200 and cleared.json()["gbp_confirmed_place_id"] is None
