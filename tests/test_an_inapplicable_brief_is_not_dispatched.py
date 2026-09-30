"""A brief the product can already decide is inapplicable is never billed.

`QUESTIONS.md` **Q-32**, answered `Gate it server-side` (operator,
2026-08-31); the finding is **CQ-223**, carried for ten reports from 099.

The defect this pins: `locale_evidence` decides the hreflang applicability
question deterministically from the crawl, `clauditseo/analysts/expert.py`
bound the answer to `_multi` and read it nowhere, and the brief was then
dispatched to ask a model the same question in prose — so every single-locale
site paid for an answer the product was already holding.

**The gate must be able to be wrong, or it proves nothing.** Three of the four
tests here exist to give it that chance: a site with two declared languages,
one with existing alternate annotations, and one where the operator states a
target locale the crawl cannot see must each still dispatch. A gate that
refuses everything would pass a test that only checked the refusal, and it
would be the worse defect of the two — a brief that can never run at all.

The provider is a stub that COUNTS what it was asked for. `tokens == 0` in an
envelope is not evidence of a call that did not happen: the cache-hit path
reports exactly that and does call in general. Only the provider itself can
say the dispatch was refused rather than merely cheap.

It counts rather than raises, and that distinction was measured rather than
assumed. `run_expert` wraps its provider call in `except Exception` and
returns `{"status": "unavailable", "reason": "the model provider failed: …"}`
(`clauditseo/analysts/expert.py`), so a stub that raised on being called would
have had its objection swallowed and turned into an envelope — the guard's
evidence absorbed by the code it is judging, which is DISCIPLINE rule 5. The
count survives that path; an exception does not.
"""

from __future__ import annotations

import dataclasses

import pytest

import clauditseo.modules  # noqa: F401
from clauditseo.analysts.base import AnalystResponse
from clauditseo.analysts.expert import run_expert
from clauditseo.config import Settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo, runs

BASE = "https://single.example"


class CountingProvider:
    """Answers like a real provider and records that it was asked.

    One class for both directions on purpose: the refusal case and the
    dispatch case must be told apart by `calls`, not by which stub was
    handed in, or the two halves are measuring different things.
    """

    name = "counting"
    model_id = "counting-1"

    def __init__(self):
        self.calls = 0

    def run_agent(self, system, bundle, toolkit, max_tokens, max_output=0):
        self.calls += 1
        return AnalystResponse(findings=[], tokens_in=10, tokens_out=10,
                               text="## ASSUMPTIONS\nhreflang applies.")


def _page(url: str, lang: str | None = None,
          alternates: list[tuple[str, str]] | None = None) -> dict:
    return {"url": url, "requested_url": url, "status": 200,
            "content_type": "text/html; charset=utf-8",
            "title": "A page", "lang": lang, "hreflang": alternates or [],
            "outlinks": [], "links": [], "redirect_chain": []}


def _evidence(pages: list[dict]) -> dict:
    return {"start_url": BASE + "/", "pages": pages}


@pytest.fixture
def conn_and_run(tmp_path):
    conn = connect(tmp_path / "gate.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Gate Co")
    site_id = repo.create_site(conn, client, "single.example")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    yield conn, run_id
    conn.close()


def _cfg() -> Settings:
    return dataclasses.replace(Settings(), anthropic_api_key="")


def _run(conn, run_id, ev, provider, inputs=None):
    return run_expert(conn, run_id, "hreflang", ev,
                      Site(domain="single.example"), _cfg(), provider,
                      operator_inputs=inputs)


def test_a_single_locale_site_never_reaches_the_model(conn_and_run):
    conn, run_id = conn_and_run
    ev = _evidence([_page(BASE + "/", lang="en"),
                    _page(BASE + "/about", lang="en")])

    provider = CountingProvider()

    envelope = _run(conn, run_id, ev, provider)

    assert envelope["status"] == "not_applicable"
    assert provider.calls == 0
    # The refusal has to carry the evidence and what would change it, because
    # it replaces a deliverable that would have said both. A bare status is
    # indistinguishable from "not run" on the screen that shows it.
    assert "single.example" in envelope["reason"]
    assert "SINGLE locale" in envelope["reason"]
    assert "target locale" in envelope["reason"]
    # Nothing was stored against the run: a refusal is not a report.
    stored = conn.execute(
        "SELECT COUNT(*) AS n FROM expert_reports WHERE run_id=?",
        (run_id,)).fetchone()
    assert stored["n"] == 0


def test_a_second_declared_language_still_dispatches(conn_and_run):
    conn, run_id = conn_and_run
    ev = _evidence([_page(BASE + "/", lang="en"),
                    _page(BASE + "/de/", lang="de")])
    provider = CountingProvider()

    envelope = _run(conn, run_id, ev, provider)

    assert envelope["status"] == "ok" and provider.calls == 1


def test_an_existing_alternate_annotation_still_dispatches(conn_and_run):
    """One `lang` value beside a broken cluster is the case `locale_evidence`
    was written for: a site that declares alternates has alternates to
    declare, so `multi` is true and the gate must stand aside."""
    conn, run_id = conn_and_run
    ev = _evidence([_page(BASE + "/", lang="en",
                          alternates=[["de", BASE + "/de/"]])])
    provider = CountingProvider()

    envelope = _run(conn, run_id, ev, provider)

    assert envelope["status"] == "ok" and provider.calls == 1


def test_a_stated_target_locale_overrules_the_crawl(conn_and_run):
    """The operator's answer to the residual risk. A single-locale crawl plus
    a locale the operator states is precisely the site the crawl could not
    see, and the prompt's own gate says APPLIES when target locales are
    supplied — so the deterministic read must not win over the operator."""
    conn, run_id = conn_and_run
    ev = _evidence([_page(BASE + "/", lang="en")])
    provider = CountingProvider()

    envelope = _run(conn, run_id, ev, provider,
                    inputs={"TARGET_LOCALES": "en-AU, de-DE"})

    assert envelope["status"] == "ok" and provider.calls == 1
