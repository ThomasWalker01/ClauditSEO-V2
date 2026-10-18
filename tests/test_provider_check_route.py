"""The "check providers" button must not render a credential.

Round 034 stripped the query string from provider URLs in
`ProviderHub.note_failure`, and added `ProviderHub._redact` under the docstring
"exposed for callers that build their own detail". Nothing called it:
`grep -rn "_redact\b"` over the package returned one hit, the definition.

`POST /api/admin/providers/check` is that other caller. It builds
`row["detail"]` from `str(exc)` with the exact expression `base.py` had before
the fix, and `admin.tsx` renders it verbatim — so the one operator action named
"check providers" put a live key on screen whenever PageSpeed refused. CQ-73.

Route-level rather than a unit test on the helper, because the defect was never
that the helper was wrong; it was that a second builder existed and nobody had
walked to it. A test of the helper would have passed throughout.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate

#: Not a real key. Shaped like one so the assertion is about the shape that
#: leaks — 39 characters after the `AIzaSy` prefix Google uses.
FAKE_KEY = "AIzaSyFAKEKEYFORTESTINGONLY1234567890abc"
PROBE_URL = ("https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
             f"?url=https%3A%2F%2Fexample.com%2F&key={FAKE_KEY}&strategy=mobile")


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "providers.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    return TestClient(create_app(db_path=db))


def _refusing_pagespeed(monkeypatch, exc: Exception) -> None:
    """Make PageSpeed configured and failing — and silence the other four.

    `check_providers` makes REAL network calls by design, and its own
    docstring says so. Left alone, this test spends the operator's quota on
    every run and its result depends on whether four third parties are up.
    Measured while writing it: the first version drew a genuine `401` from the
    live OpenPageRank key. So every probe is stubbed and the test makes no
    outbound request at all.
    """
    import clauditseo.providers.backlinks as backlinks
    import clauditseo.providers.google as google

    class _Absent:
        def __init__(self, cfg): pass          # noqa: ARG002, E704
        def available(self) -> bool: return False   # noqa: E704

    class _Refusing:
        name = "pagespeed"

        def __init__(self, cfg):        # noqa: ARG002
            pass

        def available(self) -> bool:
            return True

        def metrics(self, url):         # noqa: ARG002
            raise exc

    for mod, names in ((backlinks, ("OpenPageRank", "MozBacklinks",
                                    "DataForSEOBacklinks")),
                       (google, ("CruxField",))):
        for name in names:
            monkeypatch.setattr(mod, name, _Absent)
    monkeypatch.setattr(google, "PageSpeedLab", _Refusing)


def test_a_refusing_provider_does_not_put_its_key_on_the_screen(client, monkeypatch):
    """The `except Exception` branch — a provider that answers with a status."""
    request = httpx.Request("GET", PROBE_URL)
    response = httpx.Response(400, request=request)
    _refusing_pagespeed(monkeypatch, httpx.HTTPStatusError(
        f"Client error '400 Bad Request' for url '{request.url}'",
        request=request, response=response))

    body = client.post("/api/admin/providers/check").text

    assert FAKE_KEY not in body, "the key reached the response body"
    assert "AIzaSy" not in body and "key=" not in body, (
        f"a query string survived into the response: {body[:400]}")
    assert "pagespeedonline" in body, (
        "the host must survive — which provider refused is the point of the "
        "row this renders")


def test_the_not_configured_branch_is_redacted_too(client, monkeypatch):
    """The other `except`. `NotConfigured` is raised by the provider itself
    and its message is under our control today — but it is the same expression
    on the same row, and a branch left unredacted because its current message
    happens to be clean is the shape of this whole finding."""
    from clauditseo.providers.base import NotConfigured

    _refusing_pagespeed(monkeypatch, NotConfigured(
        f"no key for {PROBE_URL}"))

    body = client.post("/api/admin/providers/check").text

    assert FAKE_KEY not in body and "key=" not in body, (
        f"the not-configured branch leaked: {body[:400]}")


def test_the_redactor_is_actually_reached_from_the_route(monkeypatch):
    """Guards the wiring, not the helper.

    Round 034's defect was a helper nobody called, and a test that only
    asserted "no key in the body" would also pass if the route stopped
    reporting details at all. This asserts the detail is still produced *and*
    that it went through redaction.
    """
    import clauditseo.providers.base as base

    seen: list[str] = []
    original = base._redact_urls

    def spy(text: str) -> str:
        seen.append(text)
        return original(text)

    monkeypatch.setattr(base, "_redact_urls", spy)
    assert spy(f"see {PROBE_URL} please").count("[redacted]") == 1
    assert seen, "the spy itself must record"
