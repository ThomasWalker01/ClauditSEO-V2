"""The Headings holds are one ledger (screen audits round 4, Headings AC-01,
AC-02, AC-03, IP-01, IP-02, r3 IP-02).

The reader held seven `h1-triple-restated` rows on read, and after it the
provenance said "17 rows returned" where the model returned 24, the Fixes
heading said "20 cards" over four, and one blank in the site record was
drawn as three hold lines in three wordings, the reader's paths without
their trailing slash. On the outline cards a key stood for every heading
spelled alike, so an empty duplicate H3 matched the full one and read as
kept on the card about removing it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from clauditseo.analysts import contract
from tests.test_one_template_rule import DASH, ESBUILD, NODE

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def _parsed(rows, held=()):
    return contract.Parsed(status=contract.READ, rows=rows, dropped=[], assumptions=[],
                           not_assessable=list(held), block=True, part="headings",
                           strategy=None)


def _row(page, evidence):
    return contract.Row(check="ONP/h1-triple-restated", dimension="ONP",
                        check_id="h1-triple-restated", page=page, status="WARN",
                        severity="low", evidence=evidence, replacement="New H1", note="")


NO_TRIPLE = ('h1 "SEO" - location entity absent (location_entity n/a per TRIPLES, '
             "primary_entity also n/a)")


def test_rows_the_reader_holds_are_counted_and_keep_their_spelling():
    parsed = contract.enforce(_parsed([
        _row("/web-design1/", NO_TRIPLE), _row("/webdesign/slow-website/", NO_TRIPLE)]),
        contract.Rules())
    assert parsed.rows == []
    held = {h["page"]: h for h in parsed.not_assessable}
    # As the cards write them, trailing slash and all.
    assert set(held) == {"/web-design1/", "/webdesign/slow-website/"}, held
    # Each says how many returned rows it holds, so "rows returned" counts them.
    assert all(h["rows"] == 1 for h in held.values()), held
    assert {h["needs"] for h in held.values()} == {contract.TRIPLE_NONE}


def test_the_models_own_triple_hold_reads_as_the_readers():
    cleaned = contract.clean_holds(_parsed([], held=[
        {"check": "ONP/h1-triple-restated", "page": "/",
         "needs": "page triple"},
        {"check": "ONP/h1-triple-restated", "page": "/website-seo/",
         "needs": "page triple (location_entity n/a, primary_entity n/a in TRIPLES)"}]))
    assert {h["needs"] for h in cleaned.not_assessable} == {contract.TRIPLE_NONE}


def test_the_readers_own_reasons_are_kept_through_cleaning():
    # The location-only hold read back as the no-triple one on the running
    # product: the reader's sentence names an entity, and was mapped again.
    cleaned = contract.clean_holds(_parsed([], held=[
        {"check": "ONP/h1-triple-restated", "page": "/a/", "needs": contract.TRIPLE_LOCATION},
        {"check": "ONP/h1-triple-restated", "page": "/b/", "needs": contract.TRIPLE_NONE}]))
    assert [h["needs"] for h in cleaned.not_assessable] == [
        contract.TRIPLE_LOCATION, contract.TRIPLE_NONE]


def test_the_provenance_counts_held_rows_as_returned():
    src = SRC.read_text(encoding="utf-8")
    assert "brief.rows + (part.brief_dropped ?? 0) + (brief.held_rows ?? 0)} rows returned" in src
    assert "b.rows + b.dropped + (b.held_rows ?? 0)} rows returned" in src
    # A check held on some pages with a card on another was assessed.
    assert "held on some pages and assessed on" in src


PROBE = """
import { pairLines } from "%s";
const before = ["services", "just getting started", "outdated design", "rebranding",
                "speed and performance", "about", "outdated design", "contact"];
const after = ["services", "about", "outdated design", "contact"];
console.log(JSON.stringify(pairLines(before, after)));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_two_headings_spelled_alike_are_two_lines(tmp_path):
    (tmp_path / "probe.ts").write_text(PROBE % (DASH / "src" / "part_page").as_posix(),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    before_of, after_of = json.loads(subprocess.run(
        [NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
        text=True, encoding="utf-8").stdout)
    # The kept "Outdated design" is the full one after "About"; the empty
    # duplicate among the four removed H3s is matched by nothing, so struck.
    assert before_of == [0, 5, 6, 7], before_of
    assert after_of[2] is None and after_of[6] == 2, after_of
