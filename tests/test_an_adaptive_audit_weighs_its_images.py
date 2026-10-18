"""An adaptive audit weighs its images, and says when nobody did (item 205).

The operator, comparing two full-site audits of twenty22 on Images: "The byte
for pixel results disappear". The fixed-tier launcher took the browser image
pass; `adaptive.run_adaptive` - the launcher's default and what a part's
re-check sends - never did, so every adaptive audit stored images with no
weight and no box, and the screen explained the absence as a CDN without
Timing-Allow-Origin, over same-origin images another audit had weighed.

The pass is one function below both launchers (`imaging.measure_for_run`),
the run stores whether it ran, and the payload says which: measured, not
measured, or no renderer.
"""

from __future__ import annotations

import dataclasses
import json

from clauditseo import imaging
from clauditseo.adaptive import run_adaptive
from clauditseo.config import Settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo, runs
from tests.test_adaptive import FAST, FixtureSite, MockAnalyst, _routes


def _run(tmp_path, monkeypatch, fake):
    for var in ("CLAUDITSEO_BAND_HEALTHY", "CLAUDITSEO_BAND_WATCH", "CLAUDITSEO_BAND_CONCERN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(imaging, "measure_for_run", fake)
    conn = connect(tmp_path / "a.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Adaptive Co")
    site_id = repo.create_site(conn, client, "adaptive.fixture")
    run_id = runs.create_run(conn, site_id, ["TEC", "ONP", "CNT"], "T1", analyst_enabled=True)
    server = FixtureSite(_routes()).start()
    try:
        run_adaptive(conn, run_id, Site(domain="adaptive.fixture"), site_id,
                     server.base_url + "/", dataclasses.replace(Settings(), anthropic_api_key=""),
                     ["TEC", "ONP", "CNT"], provider=MockAnalyst(), budgets=FAST)
    finally:
        server.stop()
    evidence = json.loads(runs.evidence_text(conn, run_id))
    return conn, run_id, evidence


def test_an_escalated_adaptive_audit_takes_the_image_pass(tmp_path, monkeypatch):
    seen: list[int] = []

    def fake(crawl, record, report=None):
        seen.append(len(crawl.pages))
        return {}, True

    _conn, _run_id, evidence = _run(tmp_path, monkeypatch, fake)
    assert seen, "the adaptive launcher never took the image pass"
    assert min(seen) > 3, f"the three-page pulse was measured rather than the escalated crawl: {seen}"
    assert evidence.get("images_measured") is True, evidence.get("images_measured")


def test_no_renderer_is_said_as_no_renderer(tmp_path, monkeypatch):
    conn, run_id, evidence = _run(tmp_path, monkeypatch, lambda c, r, report=None: ({}, "unavailable"))
    assert evidence.get("images_measured") == "unavailable"
    payload = runs.image_budget_payload(conn, run_id)
    if payload is not None:
        assert payload["measured"] == "unavailable", payload


def test_the_pass_reports_its_own_state(monkeypatch):
    class Crawl:
        pages = []

    monkeypatch.setattr(imaging, "available", lambda: False)
    assert imaging.measure_for_run(Crawl(), {}) == ({}, "unavailable")
    monkeypatch.setattr(imaging, "available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("browser died")

    monkeypatch.setattr(imaging, "measure", boom)
    assert imaging.measure_for_run(Crawl(), {}) == ({}, False)
    monkeypatch.setattr(imaging, "measure", lambda urls, breakpoints: {})
    assert imaging.measure_for_run(Crawl(), {}) == ({}, True)


def test_evidence_from_before_the_flag_is_read_from_the_images():
    """A run stored before item 205 says nothing; a pass that ran leaves a
    rendered box somewhere, and one that did not leaves none."""
    from clauditseo.persistence.runs import _images_measured
    weighed = [{"image_inventory": [{"src": "a.png", "rendered": {"480": [100, 80]}}]}]
    never = [{"image_inventory": [{"src": "a.png"}]}]
    assert _images_measured({}, weighed) is True
    assert _images_measured({}, never) is False
    assert _images_measured({"images_measured": "unavailable"}, weighed) == "unavailable"
