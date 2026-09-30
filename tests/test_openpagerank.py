"""The OpenPageRank request shape, pinned.

The provider called domcop's API long after OpenPageRank moved off it. The
old host stayed up and answered every request with 403 "Invalid API key",
which is the worst possible failure: it names a cause that is not the cause,
so the obvious next step — check the key, get a new key — could never work.
A retired endpoint that returned 404 would have been diagnosed in a minute.

Nothing about the call survived the move: different host, Bearer instead of
the custom API-OPR header, POST instead of GET, and different field names in
the reply. So the shape is asserted here rather than only the mapping — a
correct reading of a response nobody is sending is not worth much.

No network. The transport is replaced, which is also the point: the live
check in the admin panel is what catches a *future* move, and a test that
needed a real key could not run in CI at all.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.config import Settings
from clauditseo.providers.backlinks import OPR_ENDPOINT, OpenPageRank

BODY = {
    "as_of": "2026-06-01",
    "count": 1,
    "results": [{
        "domain": "example.com",
        "found": True,
        "open_page_rank": 6.4,
        "rank": 1234,
        "referring_domains": 812,
        "hosts": [],
    }],
    "invalid": [],
}


@pytest.fixture
def sent(monkeypatch):
    """Capture the outgoing request instead of making one."""
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers") or {}
        payload = captured.get("reply", BODY)
        return httpx.Response(
            200, content=json.dumps(payload).encode(),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_OPENPAGERANK_KEY", "opr_live_testkey")
    monkeypatch.setenv("CLAUDITSEO_NO_ENV_FALLBACK", "1")
    return OpenPageRank(Settings())


def test_it_posts_to_the_current_endpoint(provider, sent) -> None:
    provider.snapshot("example.com")
    assert sent["url"] == OPR_ENDPOINT
    assert "keywordseverywhere" in sent["url"]
    assert "openpagerank.com/api" not in sent["url"], (
        "the domcop endpoint answers 403 to everything — a key can never fix it"
    )


def test_it_authenticates_with_a_bearer_token(provider, sent) -> None:
    provider.snapshot("example.com")
    assert sent["headers"].get("Authorization") == "Bearer opr_live_testkey"
    assert "API-OPR" not in sent["headers"], "the old custom header is not read"


def test_it_asks_for_one_domain_without_history(provider, sent) -> None:
    provider.snapshot("example.com")
    assert sent["json"] == {"domains": ["example.com"], "include_history": False}


def test_the_authority_score_is_normalised_to_100(provider, sent) -> None:
    snap = provider.snapshot("example.com")
    assert snap.domain_authority is not None
    # Their scale is 0-10; every other authority figure in the app is 0-100.
    assert snap.domain_authority.value == pytest.approx(64.0)
    assert snap.domain_authority.source == "openpagerank"


def test_referring_domains_are_read(provider, sent) -> None:
    """The old API could not answer this at all; the free tier now does."""
    snap = provider.snapshot("example.com")
    assert snap.referring_domains is not None
    assert snap.referring_domains.value == pytest.approx(812.0)


def test_a_domain_they_have_nothing_on_reports_nothing(provider, sent) -> None:
    """`found: false` is an answer, not a failure — and not an authority of 0.

    Reading the numbers anyway would tell an operator their client's domain
    has zero authority, which is a claim, not an absence of one.
    """
    sent["reply"] = {"as_of": "2026-06-01", "count": 1, "invalid": [],
                     "results": [{"domain": "nowhere.example", "found": False,
                                  "open_page_rank": 0, "referring_domains": 0}]}
    snap = provider.snapshot("nowhere.example")
    assert snap.domain_authority is None
    assert snap.referring_domains is None
    assert snap.sources == ["openpagerank"]


def test_an_empty_result_list_does_not_raise(provider, sent) -> None:
    sent["reply"] = {"as_of": "2026-06-01", "count": 0, "results": [], "invalid": []}
    snap = provider.snapshot("example.com")
    assert snap.domain_authority is None
