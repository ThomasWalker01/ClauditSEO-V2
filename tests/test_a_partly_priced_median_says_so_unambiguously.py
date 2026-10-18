"""UX-83: the caveat on a partly-priced median stops reading as its opposite.

UX-74 put a population beside every brief price at round 079 —
`tests/test_a_brief_price_says_which_runs_it_came_from.py` guards that it is
*there*, on all five sites. Report 088 then read the shipped string off the
running instance and raised **UX-83**: the words chosen parse first as the
opposite of what they mean, and it was carried unchanged through report 107.

The string was `from {costed} of {sampled} priced run(s)`, painted at
`#/tools/2537f69f…/crawl` as **`from 1 of 3 priced runs`**. `priced`
modifies `runs`, so the natural first reading is *"three runs were priced and
this median came from one of them"* — two priced runs discarded. The intended
reading is *"three runs were sampled and one of them carried a price"*. The
two differ in what they say was thrown away, and the second is a much weaker
caveat than the first.

**The product already had the words.** `dashboard/src/schedule.tsx` states the
same fact at length and correctly — *"N of these prices are medians over runs
that were not all costed"* — so this was never a question of what to say, only
that the per-figure frame did not say it.

**The reader most exposed is not a person.** `clauditseo/api/app.py`'s
`_triage_data` puts the identical words into the prompt the dispatcher model is
asked to fit a SPEND NEXT recommendation inside, and gives it no other form to
read. UX-83's Impact names three screens *and* that prompt for this reason.

**The fix is a predicate, not a modifier.** `1 of 3 runs carried a price` puts
`carried a price` on the whole clause instead of hanging `priced` off `runs`,
so there is no reading in which three runs were priced. `1 of 3` is retained
verbatim, which is what UX-74's own behavioural guard asserts, so this file
strengthens that one rather than replacing it.

**Asserted from source for the screens and behaviourally for the prompt**, on
exactly the split the UX-74 file records: the shipped `served` fixture carries
no `model_prices` row, so no browser clause can reach a partly-priced brief,
while `_triage_data` can be called directly. Said plainly because a source
assertion that reads as a rendered one is the inherited-coverage claim
DISCIPLINE rule 4 forbids.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo.api.app import _triage_data, settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from tests.test_a_brief_price_says_what_it_covers import _seed  # one fixture shape

ROOT = Path(__file__).resolve().parents[1]

#: The reading the finding is about. `priced` as an adjective on `runs` makes
#: `{sampled}` the count of priced runs, which is the opposite of the fact.
AMBIGUOUS = re.compile(r"priced runs?\b")

#: The reading that replaced it.
PLAIN = "carried a price"


def _frame_body() -> str:
    """`BriefPriceFrame`'s own source, from its definition to the next one."""
    source = (ROOT / "dashboard" / "src" / "components.tsx").read_text(
        encoding="utf-8")
    assert "export function BriefPriceFrame" in source, (
        "BriefPriceFrame has moved out of components.tsx; the UX-74 owner "
        "guard in test_a_brief_price_says_which_runs_it_came_from.py names "
        "this file as the single definition site")
    after = source.split("export function BriefPriceFrame", 1)[1]
    return after.split("\nexport ", 1)[0]


def _triage_frame_body() -> str:
    """The `frame` assignment in `_triage_data`, read as source.

    The behavioural clause below is the one that matters, but it can only see
    the string on one seeded population. This reads the literal itself, so a
    future edit that reintroduces the modifier form on a branch the fixture
    does not reach still fails.
    """
    source = (ROOT / "clauditseo" / "api" / "app.py").read_text(
        encoding="utf-8")
    body = source.split("def _triage_data(", 1)[1].split("\ndef ", 1)[0]
    lines = [ln for ln in body.split("\n")
             if "frame = " in ln and "{costed}" in ln]
    assert lines, (
        "no `frame = ` literal naming {costed} was found in _triage_data; the "
        "prompt half of UX-74 has moved and this guard cannot see it")
    return "\n".join(lines)


@pytest.mark.parametrize("name", ["components.tsx (BriefPriceFrame)",
                                  "app.py (_triage_data)"])
def test_neither_site_hangs_priced_off_the_population(name):
    """The finding, at both sites that carry the sentence.

    Proven to fail first, per DISCIPLINE rule 1: against HEAD before the fix
    `components.tsx` read `from {costed} of {sampled} priced run{...}` and
    `app.py` read `" (from {costed} of {sampled} priced runs)"`, and both
    matched `AMBIGUOUS`.
    """
    text = _frame_body() if name.startswith("components") else _triage_frame_body()
    found = AMBIGUOUS.search(text)
    assert not found, (
        f"{name} still says {found.group(0)!r}: `priced` modifying `runs` "
        "makes the sampled count read as the number of runs that were priced, "
        "which is UX-83 — the caveat reading as its own opposite")
    assert PLAIN in text, (
        f"{name} no longer says what the population is; UX-83's fix is the "
        f"predicate form {PLAIN!r}, not the removal of the caveat")


def test_the_two_sites_say_it_the_same_way():
    """One sentence, two languages, and no third wording.

    They cannot share an implementation — one is JSX and one is an f-string —
    so what is bound is the wording. CQ-199, fixed in the same round, is the
    same shape at the persistence layer: two spellings of one rule that drifted
    because nothing held them together.
    """
    tsx, py = _frame_body(), _triage_frame_body()
    for fragment in ("of ", PLAIN):
        assert fragment in tsx and fragment in py, (
            f"{fragment!r} appears at one site and not the other; the screens "
            "and the prompt would state the same caveat two ways")


def test_the_price_the_model_is_given_cannot_be_read_backwards(tmp_path,
                                                               monkeypatch):
    """The prompt, driven rather than read.

    `test_the_price_the_model_is_given_names_its_population` in the UX-74 file
    asserts `1 of 3` is present at all. This asserts the sentence around it
    cannot be read as *three priced runs*, which is the half UX-83 added.

    Called directly rather than through `POST /api/runs/{id}/expert/triage`,
    which would spend against a provider — the same reason the UX-74 clause
    gives.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    conn = connect(tmp_path / "unambiguous-price.db")
    migrate(conn)
    try:
        site_id = _seed(conn)
        site_row = repo.get_site(conn, site_id)
        run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
        run = runs.get_run(conn, run_id)
        data = _triage_data(conn, run, site_row, settings(), {"pages": []})
    finally:
        conn.close()

    brief = next(b for b in data["available_briefs"]
                 if b["tool"] == "indexability")
    price = brief["price"]

    assert "1 of 3" in price, (
        f"the model is given {price!r} — UX-74's population is gone")
    assert not AMBIGUOUS.search(price), (
        f"the model is given {price!r}, which reads first as three priced "
        "runs with two of them discarded")
    assert f"1 of 3 runs {PLAIN}" in price, (
        f"the model is given {price!r} rather than the predicate form the "
        "screens use; the one reader with no second wording to compare "
        "against is the one being asked to recommend spending")
