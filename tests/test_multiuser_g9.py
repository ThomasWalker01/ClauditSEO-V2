"""Gate G9 (multi-operator): per-operator tokens, role scoping, and the
open-mode/token-mode boundary.

- open local mode (no config token, no operator tokens): everything works
  unauthenticated, exactly as before;
- once any operator token exists, unauthenticated requests get 401;
- owners see every client; members see only clients they own, and other
  clients' resources answer 404 (existence is not leaked);
- a configured CLAUDITSEO_TOKEN keeps full access alongside operator tokens.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "g9.db"
    conn = connect(db)
    migrate(conn)
    yield conn, TestClient(create_app(db_path=db))
    conn.close()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_open_mode_until_first_operator_token(setup):
    conn, api = setup
    assert api.get("/api/clients").status_code == 200  # open local mode

    _, token = repo.create_operator(conn, "Casey", role="owner")
    assert api.get("/api/clients").status_code == 401  # tokens now required
    assert api.get("/api/clients", headers=_bearer(token)).status_code == 200
    assert api.get("/api/clients", headers=_bearer("wrong")).status_code == 401


def test_member_scoping_and_owner_visibility(setup):
    conn, api = setup
    _, owner_token = repo.create_operator(conn, "Olive Owner", role="owner")
    _, mem_a_token = repo.create_operator(conn, "Avery Member", role="member")
    _, mem_b_token = repo.create_operator(conn, "Blake Member", role="member")

    a_client = api.post("/api/clients", json={"name": "Avery Co"},
                        headers=_bearer(mem_a_token)).json()["id"]
    b_client = api.post("/api/clients", json={"name": "Blake Co"},
                        headers=_bearer(mem_b_token)).json()["id"]
    a_site = api.post(f"/api/clients/{a_client}/sites", json={"domain": "avery.example"},
                      headers=_bearer(mem_a_token)).json()["id"]

    owner_names = {c["name"] for c in api.get("/api/clients",
                                              headers=_bearer(owner_token)).json()}
    assert {"Avery Co", "Blake Co"} <= owner_names

    a_names = {c["name"] for c in api.get("/api/clients",
                                          headers=_bearer(mem_a_token)).json()}
    assert a_names == {"Avery Co"}

    # Blake cannot see or reach Avery's client or site — 404, not 403.
    assert api.get(f"/api/clients/{a_client}",
                   headers=_bearer(mem_b_token)).status_code == 404
    assert api.get(f"/api/sites/{a_site}",
                   headers=_bearer(mem_b_token)).status_code == 404
    assert api.post(f"/api/clients/{a_client}/sites", json={"domain": "x.example"},
                    headers=_bearer(mem_b_token)).status_code == 404
    assert api.post(f"/api/sites/{a_site}/audits", json={"dims": ["TEC"], "tier": "T1"},
                    headers=_bearer(mem_b_token)).status_code == 404

    # Avery and the owner both reach it fine.
    assert api.get(f"/api/sites/{a_site}",
                   headers=_bearer(mem_a_token)).status_code == 200
    assert api.get(f"/api/sites/{a_site}",
                   headers=_bearer(owner_token)).status_code == 200


def test_a_deliverable_is_scoped_like_every_other_resource(setup):
    """`/api/client-reports/{id}` resolved on the report id alone.

    It took `operator` and never used it, while `list_client_reports` six
    lines above scoped the same data — the one hole in an otherwise uniform
    authorisation layer, and it is on the endpoint that returns the document
    a client is actually sent. Carried open from round 001 to round 015.

    404 rather than 403, matching `check_client`: a member should not learn
    which report ids exist.
    """
    conn, api = setup
    _, owner_token = repo.create_operator(conn, "Olive Owner", role="owner")
    _, mem_a_token = repo.create_operator(conn, "Avery Member", role="member")
    _, mem_b_token = repo.create_operator(conn, "Blake Member", role="member")

    a_client = api.post("/api/clients", json={"name": "Avery Co"},
                        headers=_bearer(mem_a_token)).json()["id"]
    a_site = api.post(f"/api/clients/{a_client}/sites",
                      json={"domain": "avery.example"},
                      headers=_bearer(mem_a_token)).json()["id"]

    # A stored deliverable for Avery's site. The path deliberately does not
    # exist: `client_report` has two return branches and both must carry the
    # site the scoping check needs.
    conn.execute(
        "INSERT INTO reports (id, site_id, run_ids, template, audience, path,"
        " created_at, renderer_version) VALUES (?,?,?,?,?,?,?,?)",
        ("rep-avery", a_site, "[]", "run", "client", "/nonexistent/a.md",
         "2026-08-16T00:00:00Z", "1.7.0"))
    conn.commit()

    assert api.get("/api/client-reports/rep-avery",
                   headers=_bearer(mem_b_token)).status_code == 404
    assert api.get("/api/client-reports/rep-avery",
                   headers=_bearer(mem_a_token)).status_code == 200
    assert api.get("/api/client-reports/rep-avery",
                   headers=_bearer(owner_token)).status_code == 200
    assert api.get("/api/client-reports/no-such-report",
                   headers=_bearer(mem_a_token)).status_code == 404


def test_the_config_token_keeps_full_access_beside_operator_tokens(tmp_path, monkeypatch):
    """Was `test_legacy_config_token_keeps_full_access`, which set the
    pre-rename variable and so proved the fallback rather than the setting.
    The behaviour under test is unchanged; only the name it is configured
    under is. That the retired name no longer resolves is asserted in
    tests/test_naming.py, where the removal guards live."""
    monkeypatch.setenv("CLAUDITSEO_TOKEN", "config-secret")
    db = tmp_path / "g9b.db"
    conn = connect(db)
    migrate(conn)
    repo.create_operator(conn, "Member", role="member")
    api = TestClient(create_app(db_path=db))
    assert api.get("/api/clients").status_code == 401
    assert api.get("/api/clients", headers=_bearer("config-secret")).status_code == 200
    conn.close()


def test_operator_tokens_are_stored_hashed(setup):
    conn, _ = setup
    _, token = repo.create_operator(conn, "Hash Check", role="member")
    stored = conn.execute("SELECT token_hash FROM operators WHERE name='Hash Check'")\
        .fetchone()["token_hash"]
    assert stored != token
    assert len(stored) == 64  # sha256 hex
    assert repo.operator_by_token(conn, token)["name"] == "Hash Check"
