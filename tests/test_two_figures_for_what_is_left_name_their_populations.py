"""The two figures a reader reads as "what is left" say what they count, and a
count that is not a page subset stops claiming to be the screen's scope.

Audit findings F5, F6 and F7 of 2026-09-18 - one family: a population that the
render did not disclose, or disclosed falsely.

**F5.** Measured on Birch, where the two genuinely diverge:

    h1        It found 164 findings in this audit across 12 of the 12 pages …
    button    Open triage · 164 not yet assessed
    Waiting   Outstanding 167
              167 open, across 11 parts.

164 is `run_assessed.total - assessed` - this run's findings. 167 is
`standing_by_state` open+regressed - the record's, across every audit. One
implicit subject, two populations, adjacent, both bare. On twenty22 they
coincide at 32 by accident (one audit, nothing assessed), which is exactly how
the pair survived review. Acme read 880 against 1740.

**F6.** Every part count on the landing carried this `title`, captured from the
live DOM, on a screen whose scope is 53 pages and whose record is one page:

    2 in the record — the same extent as this screen's scope, so there is
    nothing to disambiguate.

False on all eighteen, on every site, on every tab that draws the strip.
`matchesScope` returns true for `of === null` - a findings count legitimately
has no `of` - and the plain branch then wrote a scope-equality claim for it.
"Not a page subset" and "the same extent as the screen's scope" are different
statements and the code treated them as one.

**F7.** The Analyses headline read:

    … affect the same 1 of 1 pages in the record pages — 30 of 32 open
    findings (94%).

The noun twice, around a ratio over the record - `1 of 1`, 100%, about a
53-page site. `POPULATION_BASIS` says of that population, in as many words:
"Never a prevalence denominator." The server's own comment argued the right
thing ("a what-we-know statement, not a fault rate") and then set `of`, which
IS the ratio form by `Counted`'s contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


# ---- F6: the two reasons a count renders plain are two sentences -----------

def test_a_count_that_is_not_a_page_subset_does_not_claim_the_screens_scope():
    pop = (SRC / "population.tsx").read_text(encoding="utf-8")
    assert "notASubset" in pop, "the plain branch still has one sentence"
    assert "Not a share of this screen's scope." in pop
    # The scope-equality claim survives, for the case it is true of.
    assert "the same extent as this" in pop
    # Read the ternary chain itself, not the file: the phrase appears in the
    # comment that explains the defect too, so a search over the whole text
    # compares a comment's position with a branch's.
    chain = pop[pop.index("const why = ["):]
    chain = chain[:chain.index("].filter(")]
    assert chain.index("notASubset") < chain.index("the same extent as this"), (
        "the scope-equality sentence is still reached before the "
        f"not-a-subset case:\n{chain}")


# ---- F7: the record is never a denominator --------------------------------

def test_the_parts_pages_count_carries_no_denominator():
    src = (ROOT / "clauditseo" / "persistence" / "runs.py").read_text(encoding="utf-8")
    m = re.search(r'"pages": count\(len\(pages\[c\.key\]\)[^\n]*\n?[^\n]*', src)
    assert m, "the categories' pages count moved"
    assert "of=" not in m.group(0), (
        "the record is a prevalence denominator again: " + m.group(0).strip())


def test_the_headline_prints_the_noun_once():
    anat = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    # The literal noun after the count is gone; the count's own `unit` is not
    # used there either, since a plain render draws no noun.
    block = anat[anat.index("affect the same"): anat.index("affect the same") + 900]
    assert 'unit="pages"' not in block, "the count still renders a noun of its own"
    assert "open findings" in block


@pytest.fixture(scope="module")
def served_site():
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("populations")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Populations"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "populations.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, db, run_id, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_payload_sends_the_pages_count_plain(served_site):
    base, db, run_id, site_id = served_site
    got = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                    params={"run_id": run_id}, timeout=60).json()
    cats = [c for c in got["categories"] if c.get("pages")]
    assert cats, "no category carries a pages count"
    for c in cats:
        assert c["pages"]["population"] == "record", c["pages"]
        assert c["pages"]["of"] is None, (
            f"{c['key']}'s pages count is a ratio over the record: {c['pages']}")


# ---- F5: the two figures ---------------------------------------------------

def test_the_record_figure_says_it_is_the_record():
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert '"Outstanding in the record"' in lanes, (
        "the record's outstanding count is still labelled bare")
    assert "across every audit" in lanes


def test_the_runs_figure_says_it_is_this_audits():
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "ofTotal" in lanes, "the primary action takes no total to state"
    assert "of this audit's" in lanes
    # The case that needed it most: nothing assessed, so count == total, and a
    # ratio would read "164 of this audit's 164".
    assert "not yet assessed in this audit" in lanes
    anat = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    assert "ofTotal={data?.headline?.assessed?.total" in anat, (
        "the screen does not pass the total the button states")
