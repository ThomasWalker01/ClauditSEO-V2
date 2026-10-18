"""Scope and depth are two axes, and `tier` used to be both of them.

`tier` is a page budget — `Tier.T1` is three pages, which `adaptive.py` uses
as a pulse — so "a shallow site scan" asked for three pages and called the
result a site. These cases pin the separation: scope decides how many pages,
depth decides how hard each is read, and an audit that names neither is
untouched.

That last one is the important one. Every stored run was made under the old
behaviour, and a change that quietly re-pointed the default would make the
trend a comparison between two different things.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import TIER_BUDGETS, Tier
from clauditseo.scanscope import (
    DEPTHS,
    FULL_MAX_PAGES,
    SCOPES,
    crawl_kwargs,
    depth_settings,
)


def test_an_audit_that_names_no_scope_is_left_exactly_as_it_was():
    """The compatibility case, and the reason it is written first."""
    assert crawl_kwargs(None, Tier.T2, "https://x.test/") == {}
    assert depth_settings(None) == {}


def test_each_scope_decides_the_frontier_it_means():
    page = crawl_kwargs("page", Tier.T2, "https://x.test/pricing")
    # Restricting the frontier, not merely the budget: a max_pages of 1 would
    # fetch one page of a crawl that was still trying to be a crawl.
    assert page["only_urls"] == ["https://x.test/pricing"]
    assert page["budget"].max_pages == 1

    nav = crawl_kwargs("nav", Tier.T2, "https://x.test/")
    assert nav == {"nav_only": True}, (
        "nav is a frontier rule, not a page count — the site decides how many "
        "pages its own menu names")

    assert crawl_kwargs("site", Tier.T2, "https://x.test/")["budget"].max_pages \
        == TIER_BUDGETS[Tier.T2].max_pages
    assert crawl_kwargs("full", Tier.T2, "https://x.test/")["budget"].max_pages \
        == FULL_MAX_PAGES


def test_a_scope_keeps_the_tiers_timeouts_and_only_moves_the_budget():
    """Scope owns one axis. Taking the others would make it the new `tier`."""
    for tier in (Tier.T1, Tier.T2, Tier.T3):
        got = crawl_kwargs("full", tier, "https://x.test/")["budget"]
        base = TIER_BUDGETS[tier]
        assert got.request_timeout_s == base.request_timeout_s
        assert got.wall_clock_s == base.wall_clock_s
        assert got.delay_s == base.delay_s
        assert got.max_pages == FULL_MAX_PAGES


def test_full_is_larger_than_site_which_is_larger_than_page():
    """The ladder, asserted rather than assumed by the screen that draws it."""
    sizes = [crawl_kwargs(k, Tier.T2, "https://x.test/").get("budget")
             for k in ("page", "site", "full")]
    pages = [b.max_pages for b in sizes]
    assert pages == sorted(pages) and len(set(pages)) == 3, pages


@pytest.mark.parametrize("key,analyst", [
    ("quick", False), ("standard", True), ("deep", True)])
def test_only_quick_declines_the_model(key, analyst):
    """Quick is free because it runs no model, which is what makes it the
    honest first pass on a large site: a checklist over every page beats
    judgement over a sample when the fault is template-level."""
    assert depth_settings(key)["analyst"] is analyst
    assert (depth_settings(key)["model_tier"] is None) is (key == "quick")


def test_every_depth_names_a_tier_the_product_actually_has():
    """A depth pointing at a tier Admin cannot set would resolve to nothing."""
    from clauditseo.tiers import TIERS
    for key, d in DEPTHS.items():
        assert d["tier"] is None or d["tier"] in TIERS, (key, d["tier"])


def test_every_scope_and_depth_says_what_it_is_for():
    """These strings are the screen's labels. A blank one ships a blank cell."""
    for key, sc in SCOPES.items():
        assert sc.label and sc.what.strip(), key
    for key, d in DEPTHS.items():
        assert d["label"] and d["what"].strip(), key


# --- through the API --------------------------------------------------------


def _api(tmp_path, monkeypatch, name="scope.db"):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    client = TestClient(create_app(db_path=tmp_path / name))
    cid = client.post("/api/clients", json={"name": "C"}).json()["id"]
    site = client.post(f"/api/clients/{cid}/sites",
                       json={"domain": "x.test"}).json()["id"]
    return client, site


@pytest.mark.parametrize("body,detail", [
    ({"scope": "everything", "tier": "T2"}, "scope must be one of"),
    ({"depth": "thorough", "tier": "T2"}, "depth must be one of"),
])
def test_a_scan_the_engine_cannot_run_is_refused_at_the_edge(
        tmp_path, monkeypatch, body, detail):
    """A scan the engine cannot run is refused before a run row exists."""
    client, site = _api(tmp_path, monkeypatch)
    r = client.post(f"/api/sites/{site}/audits", json=body)
    assert r.status_code == 422
    assert detail in r.json()["detail"]


def test_a_depth_picks_the_model_the_operator_set_for_that_tier(
        tmp_path, monkeypatch):
    """Not a constant. Admin exists so `deep` means whatever they chose."""
    captured = {}

    def fake_thread(target=None, args=(), daemon=None):
        captured["args"] = args

        class T:
            def start(self):
                pass
        return T()

    client, site = _api(tmp_path, monkeypatch, "depth.db")
    monkeypatch.setattr("clauditseo.api.app.threading.Thread", fake_thread)
    client.post(f"/api/sites/{site}/audits",
                json={"scope": "nav", "depth": "deep", "tier": "T2"})

    # (path, run_id, site_row, dims, tier, analyst, start_url, model,
    #  nav_only, scope)
    args = captured["args"]
    assert args[5] is True, "deep runs the analyst layer"
    assert args[7] == "claude-opus-5", args[7]
    assert args[9] == "nav"


def test_an_explicit_analyst_false_survives_a_deep_depth(tmp_path, monkeypatch):
    """A caller that asked for Deep and `analyst: false` meant the second.

    Overriding it would run a model they had just declined, which is the one
    way this feature could cost somebody money they refused to spend.
    """
    captured = {}

    def fake_thread(target=None, args=(), daemon=None):
        captured["args"] = args

        class T:
            def start(self):
                pass
        return T()

    client, site = _api(tmp_path, monkeypatch, "decline.db")
    monkeypatch.setattr("clauditseo.api.app.threading.Thread", fake_thread)
    client.post(f"/api/sites/{site}/audits",
                json={"scope": "site", "depth": "deep", "tier": "T2",
                      "analyst": False})
    assert captured["args"][5] is False


def test_a_scope_brings_its_own_timeouts_so_full_finishes_on_pages(
        tmp_path, monkeypatch):
    """The wall clock follows the scope, not the caller.

    A Full scan under T2's fifteen minutes stops on time and reports
    `truncated_by=wall_clock` — a full scan in name only. The operator should
    not have to know that, so the scope picks the tier whose hour is long
    enough and an unnamed tier stops meaning "adaptive" once a scope is given.
    """
    from clauditseo.scanscope import tier_for_scope
    assert tier_for_scope("full") is Tier.T3
    assert TIER_BUDGETS[tier_for_scope("full")].wall_clock_s >         TIER_BUDGETS[Tier.T2].wall_clock_s

    captured = {}

    def fake_thread(target=None, args=(), daemon=None):
        captured["args"] = args

        class T:
            def start(self):
                pass
        return T()

    client, site = _api(tmp_path, monkeypatch, "tiers.db")
    monkeypatch.setattr("clauditseo.api.app.threading.Thread", fake_thread)
    r = client.post(f"/api/sites/{site}/audits",
                    json={"scope": "full", "depth": "quick"})
    assert r.status_code == 202, r.text
    assert captured["args"][4] == "T3", captured["args"][4]
