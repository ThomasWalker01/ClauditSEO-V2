"""The dashboard's HTTP client, which no other test reaches.

Every test in this suite talks to the API through TestClient, so the API was
always exercised with well-formed requests and the browser's own request
builder was never exercised at all. A defect there is invisible to a green
suite: for several releases `api.put` sent

    Content-Type: application/json, application/json

because the helper spread a caller's lowercase "content-type" over the
default "Content-Type" in a plain object. Object keys are case-sensitive and
header names are not, so both survived the spread and fetch joined them. That
is not a media type any parser accepts, and *every* PUT in the app — display
currency, model price, tier model, brand name, site schedule — answered 422.

Two guards, because either alone would have missed it. The first pins the
client-side invariant that one place names the header. The second pins what
the server does with a duplicate, so the trap stays documented even if the
client is rewritten in something else entirely.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app

API_TS = pathlib.Path(__file__).resolve().parents[1] / "dashboard" / "src" / "api.ts"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    return TestClient(create_app(db_path=tmp_path / "http.db"))


def test_content_type_is_named_in_exactly_one_place() -> None:
    """A second mention is how the duplicate got in, whatever its casing."""
    src = API_TS.read_text(encoding="utf-8")
    # Comments explain the incident and legitimately say the header's name.
    code = re.sub(r"//.*?$|/\*.*?\*/", "", src, flags=re.S | re.M)
    named = re.findall(r"""["']content-type["']\s*:""", code, flags=re.I)
    assert len(named) == 1, (
        f"Content-Type is named {len(named)} times in api.ts. Set it once, in "
        "the shared request builder; a second one differing only in case does "
        "not override the first, it joins it."
    )


def test_caller_headers_are_merged_case_insensitively() -> None:
    """Merging through Headers is what makes an override actually override."""
    src = API_TS.read_text(encoding="utf-8")
    assert "new Headers(" in src and ".set(" in src, (
        "api.ts must merge request headers through Headers and .set(). Object "
        "spread cannot override a header whose casing differs."
    )


def test_a_duplicated_content_type_is_rejected(api: TestClient) -> None:
    """Why the invariant matters: the server cannot read such a body.

    The value is the one a browser actually puts on the wire. Given an object
    carrying both casings, fetch does not send two header lines — it folds
    them into one comma-joined value, which was verified in the browser
    against the running server before this test was written.
    """
    dup = api.put(
        "/api/rates/currency",
        content=b'{"currency":"AUD"}',
        headers={"Content-Type": "application/json, application/json"},
    )
    assert dup.status_code == 422

    ok = api.put("/api/rates/currency", json={"currency": "AUD"})
    assert ok.status_code == 200
    assert ok.json()["display_currency"] == "AUD"


def test_the_currency_survives_a_rate_refresh(api: TestClient) -> None:
    """The operator-visible symptom: picking AUD, refreshing, seeing USD.

    Refreshing rates writes fx_rates and must not touch the display choice.
    The refresh itself may fail here — there is no network in CI — but the
    stored currency is what this asserts, and a failed refresh must not lose
    it either.
    """
    assert api.put("/api/rates/currency",
                   json={"currency": "AUD"}).status_code == 200
    api.post("/api/rates/refresh", json={})
    assert api.get("/api/rates").json()["display_currency"] == "AUD"
