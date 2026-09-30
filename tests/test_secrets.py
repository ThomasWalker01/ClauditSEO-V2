"""The operator's key store.

The property that matters is precedence. Everything else here is ordinary
storage; the reason this module exists at all is that an operator could not
replace a key their provider had started rejecting without a shell and a
restart, and the failure mode being fixed is a key that reads as set while a
different, invisible one is what actually gets sent.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from clauditseo import secrets as store
from clauditseo.api.app import create_app
from clauditseo.config import settings

OPR = "CLAUDITSEO_OPENPAGERANK_KEY"


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Never touch the developer's real store or their real keys.

    This used to clear two spellings, because lookups accepted either and
    clearing one left the other answering — a test asserting "nothing in the
    environment" passed or failed depending on whose shell ran it. There is
    one spelling now, so there is one name to clear.
    """
    monkeypatch.setenv("CLAUDITSEO_SECRETS_FILE", str(tmp_path / "secrets.json"))
    monkeypatch.setenv("CLAUDITSEO_NO_ENV_FALLBACK", "1")
    monkeypatch.delenv(OPR, raising=False)
    store._cache.clear()
    yield
    store._cache.clear()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    return TestClient(create_app(db_path=tmp_path / "keys.db"))


def test_a_stored_key_beats_the_environment(monkeypatch) -> None:
    """The whole point. A stale environment key must not win silently."""
    monkeypatch.setenv(OPR, "stale-key-being-refused")
    assert settings().openpagerank_key == "stale-key-being-refused"

    store.put(OPR, "the-new-one")
    assert settings().openpagerank_key == "the-new-one"


def test_removing_a_stored_key_falls_back_rather_than_disabling(monkeypatch) -> None:
    monkeypatch.setenv(OPR, "from-the-environment")
    store.put(OPR, "from-the-panel")
    assert settings().openpagerank_key == "from-the-panel"

    store.drop(OPR)
    assert settings().openpagerank_key == "from-the-environment"


def test_only_managed_names_can_be_written() -> None:
    """The store is written by an HTTP endpoint, so the allowlist is a gate.

    Without it a request could set the database path or the auth token.
    """
    with pytest.raises(KeyError):
        store.put("CLAUDITSEO_DB", "/somewhere/else.db")
    with pytest.raises(KeyError):
        store.put("CLAUDITSEO_TOKEN", "granted")


def test_a_name_smuggled_into_the_file_is_ignored_on_read() -> None:
    """Refusing on write is not enough if reads trust the file's contents."""
    store.path().parent.mkdir(parents=True, exist_ok=True)
    store.path().write_text(json.dumps({
        "CLAUDITSEO_TOKEN": "granted",
        "CLAUDITSEO_DB": "/elsewhere.db",
        OPR: "legitimate",
    }), encoding="utf-8")
    store._cache.clear()
    loaded = store.load()
    assert loaded == {OPR: "legitimate"}


def test_an_unreadable_store_degrades_to_the_environment(monkeypatch) -> None:
    """A corrupt file must not take the app down with it."""
    store.path().parent.mkdir(parents=True, exist_ok=True)
    store.path().write_text("{ this is not json", encoding="utf-8")
    store._cache.clear()
    monkeypatch.setenv(OPR, "still-works")
    assert store.load() == {}
    assert settings().openpagerank_key == "still-works"


def test_the_cache_notices_a_changed_file() -> None:
    """Cached on the file's identity, so a save takes effect immediately."""
    store.put(OPR, "first")
    assert store.get(OPR) == "first"
    store.put(OPR, "second")
    assert store.get(OPR) == "second"


def test_a_masked_key_cannot_be_reassembled() -> None:
    masked = store.mask("opr_live_abcdefghijklmnop")
    assert masked.endswith("mnop")
    assert "abcdefgh" not in masked
    # A short value gives away nothing at all rather than most of itself.
    assert store.mask("tiny") == "•" * 6


def test_the_endpoint_never_returns_a_key(api: TestClient) -> None:
    secret = "opr_live_do_not_echo_this_1234"
    assert api.put(f"/api/keys/{OPR}", json={"value": secret}).status_code == 200

    listing = api.get("/api/keys")
    assert listing.status_code == 200
    assert secret not in listing.text

    row = next(k for k in listing.json()["keys"] if k["name"] == OPR)
    assert row["stored"] is True
    assert row["masked"].endswith("1234")


def test_the_endpoint_refuses_an_unmanaged_name(api: TestClient) -> None:
    assert api.put("/api/keys/CLAUDITSEO_TOKEN",
                   json={"value": "granted"}).status_code == 404
    assert api.delete("/api/keys/CLAUDITSEO_DB").status_code == 404


def test_a_key_is_stripped_before_storage(api: TestClient) -> None:
    """A pasted key with a trailing newline is the classic silent 403."""
    api.put(f"/api/keys/{OPR}", json={"value": "  padded-key\n"})
    assert store.get(OPR) == "padded-key"


def test_the_listing_says_when_the_store_is_overriding(api, monkeypatch) -> None:
    monkeypatch.setenv(OPR, "in-the-environment")
    before = next(k for k in api.get("/api/keys").json()["keys"]
                  if k["name"] == OPR)
    assert before["env_present"] is True
    assert before["overriding_env"] is False

    api.put(f"/api/keys/{OPR}", json={"value": "in-the-panel"})
    after = next(k for k in api.get("/api/keys").json()["keys"]
                 if k["name"] == OPR)
    assert after["overriding_env"] is True


def test_clearing_reports_whether_the_environment_takes_over(api, monkeypatch) -> None:
    monkeypatch.setenv(OPR, "in-the-environment")
    api.put(f"/api/keys/{OPR}", json={"value": "in-the-panel"})
    assert api.delete(f"/api/keys/{OPR}").json()["falls_back_to_env"] is True

    monkeypatch.delenv(OPR, raising=False)
    monkeypatch.setenv("CLAUDITSEO_NO_ENV_FALLBACK", "1")
    api.put(f"/api/keys/{OPR}", json={"value": "only-here"})
    assert api.delete(f"/api/keys/{OPR}").json()["falls_back_to_env"] is False


def test_every_obtain_hint_is_a_link_the_panel_can_follow() -> None:
    """Bare text tells an operator where to go and makes them type it.

    The panel renders these as anchors, so anything not absolute would render
    as a link relative to the dashboard and land back on the dashboard.
    """
    for managed in store.MANAGED:
        if not managed.obtain:
            continue
        assert managed.obtain.startswith("https://"), (
            f"{managed.name}: obtain must be an absolute https URL, "
            f"got {managed.obtain!r}"
        )


def test_the_file_is_not_world_readable() -> None:
    store.put(OPR, "some-key")
    assert store.harden() is True
