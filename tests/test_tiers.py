"""The operator picks which model each tier runs on.

The mapping was three environment variables, so changing the model a deep
brief uses meant editing a service configuration and bouncing the server. That
put the most consequential decision in the product behind a deployment step:
five times the price between the cheapest and the most capable, and on a
judgement-heavy brief the difference between a page of usable observations and
a platitude.

Two rules hold it together: absence means the environment still decides, so an
install that never opens the screen is unchanged; and a choice is validated
against models this install actually knows, because a mistyped ID fails at
call time with a provider error that says nothing about the typo — after the
operator has committed to a run.
"""

from __future__ import annotations

import pytest

from clauditseo import tiers
from clauditseo.config import Settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "tiers.db")
    migrate(c)
    from clauditseo.persistence.repo import now_iso
    for model in ("claude-haiku-4-5-20251001", "claude-sonnet-5",
                  "claude-opus-5", "claude-fable-5"):
        c.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                  " entered_at, source) VALUES (?, 1, 5, ?, 'test')",
                  (model, now_iso()))
    c.commit()
    return c


def test_no_choice_means_the_environment_still_decides(conn):
    """An install that never opens this screen must behave exactly as it did
    before the screen existed."""
    base = Settings()
    assert tiers.chosen(conn) == {}
    assert tiers.settings_for(conn, base) is base


def test_a_choice_overrides_that_tier_and_leaves_the_others(conn):
    base = Settings()
    tiers.set_tier(conn, "deep", "claude-fable-5")
    eff = tiers.settings_for(conn, base)
    assert eff.model_for_tier("deep") == "claude-fable-5"
    assert eff.model_for_tier("fast") == base.model_for_tier("fast")
    assert eff.model_for_tier("standard") == base.model_for_tier("standard")


def test_the_shared_settings_object_is_never_mutated(conn):
    """It is process-wide. A request that rewrote it in place would change
    which model every other request in flight was using."""
    base = Settings()
    before = base.model_for_tier("deep")
    tiers.set_tier(conn, "deep", "claude-fable-5")
    tiers.settings_for(conn, base)
    assert base.model_for_tier("deep") == before


def test_an_unknown_model_is_refused_at_the_point_of_choosing(conn):
    """The alternative is a provider error mid-run that names neither the typo
    nor the tier it came from."""
    with pytest.raises(ValueError, match="not a model this install knows"):
        tiers.set_tier(conn, "deep", "claude-opus-9")
    assert tiers.chosen(conn) == {}


def test_an_unknown_tier_is_refused(conn):
    with pytest.raises(ValueError, match="tier must be one of"):
        tiers.set_tier(conn, "turbo", "claude-opus-5")


def test_the_recommendation_is_applied_by_the_button(conn):
    out = tiers.use_recommended(conn)
    assert out["applied"] == tiers.RECOMMENDED
    assert out["skipped"] == {}
    eff = tiers.settings_for(conn, Settings())
    for tier, model in tiers.RECOMMENDED.items():
        assert eff.model_for_tier(tier) == model


def test_the_recommendation_skips_a_model_this_install_cannot_run(
        conn, monkeypatch):
    """Setting a tier to a model with no price and no configuration is worse
    than leaving it alone — the brief would fail when it is launched, not now.

    Note what does NOT count as unavailable: deleting a model's price row
    while the environment still names it. A missing price means nobody has
    said what it costs, not that the install lacks access, and the first
    version of this test confused the two.
    """
    monkeypatch.setitem(tiers.RECOMMENDED, "deep", "claude-unreleased-9")
    out = tiers.use_recommended(conn)
    assert out["skipped"] == {"deep": "claude-unreleased-9"}
    assert "fast" in out["applied"] and "standard" in out["applied"]
    # And the tier it skipped still resolves, via the environment.
    assert tiers.settings_for(conn, Settings()).model_for_tier("deep")


def test_a_model_with_no_price_but_a_configured_tier_is_still_runnable(conn):
    """A missing price is a gap in what we can quote, not in what we can
    call. Treating it as unavailable would disable the tier the install is
    already using."""
    conn.execute("DELETE FROM model_prices")
    conn.commit()
    base = Settings()
    assert base.model_for_tier("deep") in tiers.known_models(conn, base)


def test_clearing_hands_the_decision_back_to_the_environment(conn):
    base = Settings()
    tiers.use_recommended(conn)
    tiers.clear(conn)
    assert tiers.chosen(conn) == {}
    assert tiers.settings_for(conn, base).model_for_tier("deep") == \
        base.model_for_tier("deep")


def test_the_choosable_list_covers_what_is_configured_now(conn):
    """A dropdown that omits the model currently in use would show the
    operator a blank control and invite them to change it by accident."""
    base = Settings()
    known = tiers.known_models(conn, base)
    for tier in tiers.TIERS:
        assert base.model_for_tier(tier) in known


def test_a_chosen_model_survives_disappearing_from_the_price_list(conn):
    """It is still what the tier runs on, so it must still be listed."""
    tiers.set_tier(conn, "deep", "claude-fable-5")
    conn.execute("DELETE FROM model_prices WHERE model='claude-fable-5'")
    conn.commit()
    assert "claude-fable-5" in tiers.known_models(conn, Settings())


def test_every_tier_has_a_purpose_an_operator_can_read(conn):
    """The choice is between "a fixed checklist" and "the judgement is the
    product", not between three adjectives."""
    assert set(tiers.TIER_PURPOSE) == set(tiers.TIERS)
    assert set(tiers.RECOMMENDED) == set(tiers.TIERS)


# --- choosing a model for one launch ---------------------------------------

def test_a_per_run_override_beats_the_tier_without_changing_it(conn):
    """"Run this brief on that model, once" is a different decision from
    re-pointing every brief of that tier, and the first must not quietly
    become the second."""
    from clauditseo.analysts.expert import model_for_tool

    tiers.set_tier(conn, "standard", "claude-sonnet-5")
    cfg = tiers.settings_for(conn, Settings())
    tool = "crawl"                      # a standard-tier brief

    assert model_for_tool(cfg, tool) == "claude-sonnet-5"
    assert model_for_tool(cfg, tool, "claude-opus-5") == "claude-opus-5"
    # The stored choice is untouched by the one-off.
    assert tiers.chosen(conn)["standard"] == "claude-sonnet-5"


def test_no_override_falls_through_to_the_chosen_tier(conn):
    """An empty picker must mean "whatever the tier resolves to", not a
    silently different model."""
    from clauditseo.analysts.expert import model_for_tool

    tiers.set_tier(conn, "standard", "claude-fable-5")
    cfg = tiers.settings_for(conn, Settings())
    assert model_for_tool(cfg, "crawl", None) == "claude-fable-5"
