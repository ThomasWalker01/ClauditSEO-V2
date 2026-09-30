from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo


def _client(tmp_path):
    db = tmp_path / "api.db"
    conn = connect(db)
    migrate(conn)
    repo.seed_demo(conn)
    conn.close()
    return TestClient(create_app(db_path=db))


def test_health(tmp_path):
    resp = _client(tmp_path).get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "engine_version" in body


def test_clients_seeded(tmp_path):
    api = _client(tmp_path)
    clients = api.get("/api/clients").json()
    names = {c["name"] for c in clients}
    assert {"Acme Plumbing", "Beacon Books"} <= names

    detail = api.get(f"/api/clients/{clients[0]['id']}").json()
    assert detail["sites"], "seeded client should have a site"


def test_client_404(tmp_path):
    assert _client(tmp_path).get("/api/clients/nope").status_code == 404


def test_run_pages_lists_crawled_urls_with_the_homepage_first(tmp_path, monkeypatch):
    """The page picker's default is the homepage, so the ordering is the
    feature — not an incidental of however the crawl happened to run."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs as runs_repo

    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    path = tmp_path / "pages.db"
    conn = connect(path)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Co"), "x.test")
    run_id = runs_repo.create_run(conn, site_id, ["TEC"], "T2")
    runs_repo.store_evidence(conn, run_id, {
        "start_url": "https://x.test/",
        "pages": [
            {"url": "https://x.test/deep/", "status": 200,
             "content_type": "text/html", "title": "Deep", "click_depth": 2},
            {"url": "https://x.test/", "status": 200,
             "content_type": "text/html", "title": "Home", "click_depth": 0},
            {"url": "https://x.test/a.pdf", "status": 200,
             "content_type": "application/pdf"},          # not a page to audit
            {"url": "https://x.test/gone/", "status": 404,
             "content_type": "text/html"},                 # nothing to read
        ]})
    conn.close()

    client = TestClient(create_app(db_path=path))
    body = client.get(f"/api/runs/{run_id}/pages").json()
    urls = [p["url"] for p in body["pages"]]
    assert urls == ["https://x.test/", "https://x.test/deep/"]
    assert body["start_url"] == "https://x.test/"


def test_a_sites_business_type_can_be_corrected_after_the_fact(tmp_path):
    """It could only be set at creation, and it is exactly the field you get
    wrong before reading the site.

    A lender filed as "ecommerce" makes every brief reason about a product
    catalogue and branch locations that do not exist — and say so with
    confidence, because the profile is an input it trusts.
    """
    from clauditseo.api.app import create_app
    from fastapi.testclient import TestClient

    client = TestClient(create_app(db_path=tmp_path / "profile.db"))
    cl = client.post("/api/clients", json={"name": "C"}).json()
    site = client.post(f"/api/clients/{cl['id']}/sites",
                       json={"domain": "https://x.test/",
                             "business_type": "ecommerce"}).json()
    # Creation answers with the id only, so the profile is read back.
    assert client.get(f"/api/sites/{site['id']}").json()["business_type"]         == "ecommerce"

    r = client.put(f"/api/sites/{site['id']}",
                   json={"business_type": "local-service"})
    assert r.status_code == 200, r.text
    assert r.json()["business_type"] == "local-service"
    assert r.json()["changed"] == ["business_type"]

    again = client.get(f"/api/sites/{site['id']}").json()
    assert again["business_type"] == "local-service", "it has to survive a read"


def test_api_meta_names_the_business_type_vocabulary(tmp_path):
    """DISPOSITIONS.md, 18 rounds: the vocabulary lived in three places —
    `home.tsx`'s own list, `views.tsx`'s separately hardcoded `<option>`s, and
    an unvalidated backend field. `/api/meta` is the single source both
    screens now read; if it names none, there is nothing to make them agree.
    """
    body = _client(tmp_path).get("/api/meta").json()
    assert "business_types" in body, body.keys()
    assert body["business_types"], "must name at least one type"
    assert "local-service" in body["business_types"]


def test_creating_a_site_with_an_unknown_business_type_is_refused(tmp_path):
    """Unvalidated meant a lender could be typo'd into a vocabulary that
    exists nowhere the product recognises, and no brief would ever say so."""
    client = _client(tmp_path)
    cl = client.post("/api/clients", json={"name": "C"}).json()
    r = client.post(f"/api/clients/{cl['id']}/sites",
                    json={"domain": "https://x.test/",
                          "business_type": "not-a-real-type"})
    assert r.status_code == 422, r.text


def test_correcting_a_site_to_an_unknown_business_type_is_refused(tmp_path):
    client = _client(tmp_path)
    cl = client.post("/api/clients", json={"name": "C"}).json()
    site = client.post(f"/api/clients/{cl['id']}/sites",
                       json={"domain": "https://x.test/",
                             "business_type": "ecommerce"}).json()
    r = client.put(f"/api/sites/{site['id']}",
                   json={"business_type": "not-a-real-type"})
    assert r.status_code == 422, r.text
    # Refused, not silently partial — the prior value must survive.
    assert client.get(f"/api/sites/{site['id']}").json()["business_type"] \
        == "ecommerce"


def test_correcting_a_profile_says_how_much_was_written_under_the_old_one(tmp_path):
    """The correction does not reach backwards. A brief written while the site
    was mis-filed still reasons about the wrong business, so the count is what
    lets the UI say "re-run these" instead of implying they were fixed."""
    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs
    from fastapi.testclient import TestClient

    db = tmp_path / "stale.db"
    client = TestClient(create_app(db_path=db))
    cl = client.post("/api/clients", json={"name": "C"}).json()
    site = client.post(f"/api/clients/{cl['id']}/sites",
                       json={"domain": "https://x.test/",
                             "business_type": "ecommerce"}).json()
    conn = connect(db)
    run_id = runs.create_run(conn, site["id"], ["ONP"], "T2")
    runs.record_expert_findings(conn, run_id, "eeat-analyst", "m",
                                [{"code": "x", "severity": "low",
                                  "summary": "s", "affected_urls": []}])
    # The real column list: no id (the key is run+tool+page), and `figures`.
    # `page_url` is `''` and not NULL — migration 0029 put the page in the key
    # and made the column NOT NULL, because SQLite treats NULLs in a primary
    # key as distinct and one there would stop `INSERT OR REPLACE` replacing a
    # site-scoped row. `''` IS the site-scoped case, which is what this row is.
    conn.execute("INSERT INTO expert_reports (run_id, tool_id, model_id,"
                 " page_url, report, findings, figures, tokens, cost,"
                 " truncated, created_at) VALUES (?, 'eeat-analyst', 'm',"
                 " '', 'text', '[]', '[]', 1, 0, 0, '2026-01-01')", (run_id,))
    conn.commit()

    out = client.put(f"/api/sites/{site['id']}",
                     json={"business_type": "local-service"}).json()
    assert out["analyses_before"] == 1, (
        "one analysis was written under the old profile and is now suspect")

    # No change, nothing to warn about.
    same = client.put(f"/api/sites/{site['id']}",
                      json={"business_type": "local-service"}).json()
    assert same["changed"] == [] and same["analyses_before"] == 0


def test_analyst_insights_on_screen_match_the_section_in_the_document(tmp_path):
    """`run_detail` listed every model-judgement row; `_analyst_section`
    excludes `EXP:*`.

    So the operator reviewed an "Analyst insights" band on screen and handed
    the client a document whose section of that name held a different, shorter
    list — and on a run whose only model finding came from a brief, a section
    that was absent entirely. Two surfaces, one name, two answers. Carried
    open from round 004 to round 015.

    Specialist briefs are not lost: they have their own index and their own
    section in the document.
    """
    import json

    from clauditseo.persistence import runs

    db = tmp_path / "expfilter.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Filter Co")
    site_id = repo.create_site(conn, client, "filter.example")
    run_id = runs.create_run(conn, site_id, ["CNT"], "T2")

    # One brief finding, stored the way the expert path stores it.
    runs.record_expert_findings(
        conn, run_id, "crawl", "m-1",
        [{"severity": "high", "code": "sitemap-coverage",
          "summary": "22 indexable pages are absent from the sitemap.",
          "affected_urls": []}])

    # One ordinary analyst finding, which the band is for and must keep.
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
        " source, model_id, confidence, summary, affected_urls, evidence,"
        " recommendation, fingerprint, created_at)"
        " VALUES ('f-analyst', ?, 'CNT', 'thin-copy', 'medium',"
        " 'model-judgement', 'm-1', 'medium', 'The service pages read thin.',"
        " '[]', ?, '', 'fp-analyst', '2026-08-16T00:00:00Z')",
        (run_id, json.dumps({"confidence_stated": True})))
    conn.commit()
    conn.close()

    api = TestClient(create_app(db_path=db))
    detail = api.get(f"/api/runs/{run_id}").json()
    dims = [f["dimension"] for f in detail["analyst_findings"]]

    assert "CNT" in dims, "an ordinary analyst finding must still reach the band"
    assert not any(d.startswith("EXP:") for d in dims), (
        f"brief findings must not appear in Analyst insights; got {dims}")

    # The brief itself is still reachable, by its own route.
    index = api.get(f"/api/runs/{run_id}/expert-reports").json()
    assert index, "the specialist-brief index must still list the brief"
