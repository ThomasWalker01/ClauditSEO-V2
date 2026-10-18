"""The evidence bundle is cached, and what that costs is counted.

The bundle is resent in full on every round of the tool loop, so a five-round
brief paid for it five times at full input price. One cache breakpoint on the
first message fixes that — and because the API renders tools, then system,
then messages, that one breakpoint covers the tool definitions and the system
prompt too.

The half that is easy to forget: caching introduces two token buckets the API
bills separately and does NOT include in `input_tokens`. A caller that keeps
adding up only input and output under-states a cached call, and under-stating
a client-facing cost is the worse direction to be wrong in.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.analysts.anthropic_provider import agent_loop
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.providers import fx

BUNDLE = {"pages": [{"url": "/", "title": "t"}], "site": "x.test"}


def _reply(text: str, usage: dict) -> dict:
    return {"content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn", "usage": usage}


@pytest.fixture
def conn(tmp_path):
    from clauditseo.persistence.repo import now_iso
    c = connect(tmp_path / "cache.db")
    migrate(c)
    c.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
              " entered_at, source) VALUES ('m', 10.0, 50.0, ?, 'test')",
              (now_iso(),))
    c.commit()
    return c


def test_the_bundle_carries_a_cache_breakpoint():
    """Without it the whole bundle is re-billed at full price every round."""
    seen: list[list] = []

    def call(messages, tools):
        seen.append(messages)
        return _reply("[]", {"input_tokens": 10, "output_tokens": 2})

    agent_loop(call, BUNDLE, None, max_tokens=1000)
    first = seen[0][0]
    assert first["role"] == "user"
    block = first["content"][0]
    assert block["cache_control"] == {"type": "ephemeral"}
    assert json.loads(block["text"])["site"] == "x.test"


def test_the_cached_prefix_is_byte_identical_across_rounds():
    """Caching is a prefix match — any byte change anywhere before the
    breakpoint invalidates it. The bundle must therefore be built once and
    never rewritten; the loop may only append."""
    seen: list[str] = []

    def call(messages, tools):
        seen.append(messages[0]["content"][0]["text"])
        if len(seen) < 3:
            return {"content": [{"type": "tool_use", "id": f"t{len(seen)}",
                                 "name": "fetch_page", "input": {}}],
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 5, "output_tokens": 1}}
        return _reply("[]", {"input_tokens": 5, "output_tokens": 1})

    class _Kit:
        names = ("fetch_page",)
        def execute(self, name, args):    # noqa: D102, ARG002
            return {"ok": True}, False

    agent_loop(call, BUNDLE, _Kit(), max_tokens=1000)
    assert len(seen) >= 2, "the loop did not run more than one round"
    assert len(set(seen)) == 1, "the cached prefix changed between rounds"


def test_cache_tokens_are_counted_separately_from_input():
    """They are separate buckets at separate prices, and neither is included
    in `input_tokens`."""
    def call(messages, tools):
        return _reply("[]", {"input_tokens": 100, "output_tokens": 20,
                             "cache_creation_input_tokens": 4000,
                             "cache_read_input_tokens": 9000})

    resp = agent_loop(call, BUNDLE, None, max_tokens=1000)
    assert (resp.tokens_in, resp.tokens_out) == (100, 20)
    assert (resp.cache_write, resp.cache_read) == (4000, 9000)


def test_a_response_with_no_cache_fields_reports_zero_not_none():
    """Mock providers and older replies omit them; zero keeps the arithmetic
    total rather than making every sum guard for None."""
    resp = agent_loop(lambda m, t: _reply("[]", {"input_tokens": 1,
                                                 "output_tokens": 1}),
                      BUNDLE, None, max_tokens=100)
    assert resp.cache_write == 0 and resp.cache_read == 0


# --- what it costs ---------------------------------------------------------

def test_a_cached_call_is_priced_on_four_buckets(conn):
    """1M uncached in at $10, 1M written at 1.25x, 1M read at 0.1x, 1M out at
    $50 = 10 + 12.50 + 1 + 50."""
    assert fx.cost_of(conn, "m", 1_000_000, 1_000_000,
                      cache_write=1_000_000, cache_read=1_000_000) == 73.5


def test_ignoring_the_cache_buckets_under_states_the_cost(conn):
    """The direction matters: the cached tokens are absent from
    `input_tokens`, so pricing only input and output bills for less than was
    actually consumed."""
    naive = fx.cost_of(conn, "m", 1_000, 1_000)
    real = fx.cost_of(conn, "m", 1_000, 1_000,
                      cache_write=500_000, cache_read=500_000)
    assert real > naive


def test_an_uncached_call_costs_exactly_what_it_did_before(conn):
    """Zero cache tokens must leave the old arithmetic untouched, or every
    stored cost from before caching becomes incomparable."""
    assert fx.cost_of(conn, "m", 1_000_000, 100_000) == 10.0 + 5.0
