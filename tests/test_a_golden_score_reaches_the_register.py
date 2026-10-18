"""The golden score must survive the run that produced it — relay item 087.

`scripts/run_golden.py` is the instrument for *does the deep tier earn its
price*. It was written, and for nine days never run. When it was finally run
twice, on the operator's explicit authorisation to spend, it **printed the
score and wrote it nowhere**: the raw run persisted — 20 findings, 4 expert
reports, 6 cost rows — while the score document itself existed only in a
terminal. Nine days of not-running was one reason there was no measurement on
disk; this is the other, and it survives the first being fixed.

The clauses, one test each:

  - a scored run's score lands in a **tracked** register, written by the run
    itself, with no shell redirection and no run id known in advance;
  - it lands **inside the golden table**, not past the file's end, which is
    the failure `scripts/timings-append.ps1` exists for and which has taken
    `TIMINGS.md` red at HEAD twice;
  - **CodeDash cannot read a golden row as an audit round.** That repository
    ingests this same `TIMINGS.md`, and a row whose first cell is three digits
    with nine columns is a round to it. This is the clause that would be
    vacuous if written carelessly, so it is paired with a counter-assertion:
    the same matcher must still find every round row. A guard that matched
    nothing would otherwise pass by matching nothing;
  - the **rate carries its denominator**. `run_golden.py` records a past run
    where three of five labels sat unscored behind an overall 1.0;
  - a run whose stores are a measurement of **KI-56** rather than of a model
    says so in the row, detected from the database rather than asserted.

Every test writes to a copy of `TIMINGS.md` under `tmp_path`. A guard that
appends to the real register would leave the tree dirty and refuse the next
preflight — and would be indistinguishable, in the file, from a real score.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.golden import (REGISTER, REGISTER_SECTION, append_row, record,
                               row_for, score)
from clauditseo.persistence import repo, runs
from tests.private_register import REASON, needs_register

ROOT = Path(__file__).resolve().parent.parent

LABELS = {
    "expected": [
        {"tool": "onpage-hygiene", "page": "/blocked-drains",
         "mentions": ["h1"]},
        {"tool": "onpage-hygiene", "page": "/hot-water",
         "mentions": ["description"]},
        {"tool": "crawl", "code": "sitemap-coverage"},
    ],
    "known_absent": [
        {"tool": "hreflang", "code": "missing-return-tags"},
    ],
}

#: CodeDash's row matcher, copied from `codedash/ingest/timings.py` rather
#: than approximated: first cell exactly three digits, then eight more cells.
#: The counter-assertion below is what keeps this honest — if this drifts from
#: the real one and stops matching anything, `test_the_same_matcher_still_finds
#: _every_round_row` fails rather than this file quietly passing.
CODEDASH_ROW = re.compile(
    r"^\|\s*(?P<round>\d{3})\s*\|\s*(?P<date>[^|]+?)\s*\|"
    r"\s*(?P<pf>[^|]+?)\s*\|\s*(?P<au>[^|]+?)\s*\|"
    r"\s*(?P<fx>[^|]+?)\s*\|\s*(?P<to>[^|]+?)\s*\|"
    r"\s*(?P<lev>[^|]+?)\s*\|\s*(?P<work>[^|]+?)\s*\|"
    r"\s*(?P<what>[^|]*?)\s*\|\s*$", re.M)


@pytest.fixture
def register(tmp_path):
    """A copy of the real `TIMINGS.md`, so the table's shape under test is
    the shape actually in the tree rather than a fixture that agrees with the
    code by construction."""
    # On the FIXTURE rather than on each test that wants it: eight clauses
    # request this, and eight markers would be eight places for the reason to
    # drift. `TIMINGS.md` is the operator's working record and does not ship
    # (item 187), so in a tree without it every one of those clauses skips
    # here, once, with the reason `private_register` gives.
    if not REGISTER.is_file():
        pytest.skip(REASON)
    dest = tmp_path / "TIMINGS.md"
    shutil.copyfile(REGISTER, dest)
    return dest


@pytest.fixture
def scored(tmp_path):
    """One run, stored the way a paid run stores: a report per tool, findings
    against pages, and a `cost_entries` row per call."""
    conn = connect(tmp_path / "golden.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "G"),
                            "http://127.0.0.1/")

    def make(model: str, *, calls: dict[str, int] | None = None):
        run_id = runs.create_run(conn, site, ["TEC"], "T2")

        def report(tool, page=None):
            runs.store_expert_report(
                conn, run_id, tool,
                {"model": model, "report": "r", "tokens": 100}, page_url=page)
            conn.execute(
                "UPDATE expert_reports SET model_id=? WHERE run_id=?"
                " AND tool_id=?", (model, run_id, tool))
            conn.commit()

        def raise_finding(tool, check_id, summary, url=None):
            import json as _json
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id,"
                " severity, source, confidence, summary, affected_urls,"
                " fingerprint, created_at) VALUES (?, ?, ?, ?, 'medium',"
                " 'model-judgement', 'medium', ?, ?, ?, datetime('now'))",
                (f"{run_id}{check_id}{url}", run_id, f"EXP:{tool}", check_id,
                 summary, _json.dumps([f"http://127.0.0.1{url}"] if url
                                      else []),
                 f"fp{run_id}{check_id}{url}"))
            conn.commit()

        for tool, n in (calls or {}).items():
            for _ in range(n):
                runs.log_cost(conn, run_id, "anthropic", f"EXPERT:{tool}",
                              "tokens", 1000.0, actual_cost=0.02)
        return run_id, report, raise_finding

    return conn, make


def _golden_rows(text: str) -> list[str]:
    """Every body row of the golden table, by walking to the heading rather
    than by matching a row shape — the shape is what is under test."""
    rows, seen = [], False
    for line in text.splitlines():
        if line.strip().startswith("## "):
            seen = line.strip() == f"## {REGISTER_SECTION}"
            continue
        if seen and line.lstrip().startswith("|") and "---" not in line:
            rows.append(line)
    return rows[1:] if rows else []      # drop the header


# --------------------------------------------------------------------------
# The defect: the score existed only in a terminal.
# --------------------------------------------------------------------------

def test_a_scored_run_writes_its_score_into_the_register(scored, register):
    """The whole item, in one assertion. Before this, the only way a score
    reached disk was the operator redirecting stdout — which nobody did on
    either of the two runs that were actually paid for."""
    conn, make = scored
    run_id, report, raise_finding = make("claude-sonnet-5",
                                         calls={"onpage-hygiene": 1})
    report("onpage-hygiene")
    raise_finding("onpage-hygiene", "h1-missing", "No h1 present.",
                  "/blocked-drains")

    before = register.read_text(encoding="utf-8")
    out = score(conn, run_id, LABELS)
    where = record(conn, out, on="2026-08-24", path=register)

    assert register.read_text(encoding="utf-8") != before, "nothing was written"
    # The DELTA, not the count. `register` is a copy of the real file, so an
    # absolute `len(rows) == 1` held only while the live table was empty and
    # went red the first time a run was genuinely recorded there — this test
    # would have failed on the very event it exists to guarantee.
    added = [r for r in _golden_rows(register.read_text(encoding="utf-8"))
             if r not in _golden_rows(before)]
    assert len(added) == 1
    assert added[0].startswith("| claude-sonnet-5 | 2026-08-24 |")
    assert run_id in added[0]
    assert where["line"] > 0 and where["section"] == REGISTER_SECTION


def test_the_row_lands_in_the_golden_table_and_not_past_the_end(scored,
                                                                register):
    """The failure `scripts/timings-append.ps1` exists for. A row appended
    against the *file's* end lands under whatever the last table happens to
    be — `b90f568` → `8537598` and `bdb3390` → `04359e9` are the two repairs
    that cost — and an append against a *table's* end cannot."""
    conn, make = scored
    run_id, report, _ = make("claude-opus-5", calls={"crawl": 1})
    report("crawl")

    record(conn, score(conn, run_id, LABELS), on="2026-08-24", path=register)

    lines = register.read_text(encoding="utf-8").splitlines()
    heading = lines.index(f"## {REGISTER_SECTION}")
    row = next(i for i, ln in enumerate(lines) if run_id in ln)
    assert row > heading
    # And directly under this table's own header, not adrift below it.
    assert "| --- |" in lines[row - 1] or lines[row - 1].lstrip().startswith("|")


def test_every_row_matches_the_golden_table_header_width(register, scored):
    """The width guard's own rule, asserted here so a defect in the writer is
    found by the writer's test rather than by `test_loop_instructions` going
    red at HEAD over a file it did not write."""
    conn, make = scored
    run_id, report, _ = make("claude-sonnet-5", calls={"hreflang": 1})
    report("hreflang")
    record(conn, score(conn, run_id, LABELS), on="2026-08-24", path=register)

    text = register.read_text(encoding="utf-8")
    header = next(ln for ln in text.splitlines()
                  if ln.startswith("| model | date |"))
    width = header.count("|") - 1
    assert width == 8
    for row in _golden_rows(text):
        assert row.replace(r"\|", "X").count("|") - 1 == width, row


# --------------------------------------------------------------------------
# CodeDash. Another repository reads this file.
# --------------------------------------------------------------------------

def test_codedash_cannot_read_a_golden_row_as_an_audit_round(scored, register):
    """A golden row ingested as a round is silent: no error anywhere, a wrong
    row in another repository's database, and nothing in this one to say so.
    The `## Verification crawls` table is safe only because it has seven
    columns, which is a coincidence rather than a decision — so the model
    goes in column one, and that cannot be three digits."""
    conn, make = scored
    run_id, report, _ = make("claude-opus-5", calls={"onpage-hygiene": 1})
    report("onpage-hygiene")
    record(conn, score(conn, run_id, LABELS), on="2026-08-24", path=register)

    for row in _golden_rows(register.read_text(encoding="utf-8")):
        assert not CODEDASH_ROW.match(row), row


def test_the_same_matcher_still_finds_every_round_row(register):
    """The counter-assertion, and the reason the clause above is not vacuous.

    A matcher that had drifted from CodeDash's, or that matched nothing at
    all, would pass that test by finding nothing. This one fails unless the
    matcher genuinely recognises the rounds table — which is the population it
    is supposed to be able to see.
    """
    text = register.read_text(encoding="utf-8")
    rounds = {m.group("round") for m in CODEDASH_ROW.finditer(text)}
    assert len(rounds) > 50, f"matched only {len(rounds)} rounds"
    assert "098" in rounds


@needs_register
def test_the_appender_refuses_a_round_shaped_first_cell():
    """Not solved by counting columns and hoping. A column added to the
    golden table later must not be able to make its rows ingestible, so the
    refusal is on the first cell rather than on the width."""
    with pytest.raises(ValueError, match="three digits"):
        append_row("| 099 | 2026-08-24 | x | 1.00 | 0 | 1 | 1 | n |",
                   path=REGISTER)


def test_the_appender_refuses_a_row_of_the_wrong_width(register):
    """`timings-append.ps1`'s second hard refusal, in Python. A short row is
    exactly what lands when a caller appends a six-cell `## Other work` row
    into an eight-cell table."""
    before = _golden_rows(register.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="cells"):
        append_row("| claude-sonnet-5 | 2026-08-24 | x |", path=register)
    # Unchanged, rather than empty: what is asserted is that the refusal
    # wrote nothing, and a copy of the real register stopped being empty the
    # first time a run was recorded in it.
    assert _golden_rows(register.read_text(encoding="utf-8")) == before


def test_the_appender_refuses_a_section_that_has_no_table(tmp_path):
    """The first refusal. A heading typed with different words is a caller
    error worth a message, not a row silently dropped."""
    doc = tmp_path / "T.md"
    doc.write_text("# T\n\n## Golden accuracy runs\n\nprose only.\n",
                   encoding="utf-8")
    with pytest.raises(ValueError, match="no table"):
        append_row("| a | b | c | d | e | f | g | h |", path=doc)


# --------------------------------------------------------------------------
# What the row has to say beyond the number.
# --------------------------------------------------------------------------

def test_the_catch_rate_carries_its_denominator(scored, register):
    """`run_golden.py` records a run where three of five labels sat unscored
    behind an overall catch rate of 1.0 — a flattering number measuring two
    labels out of five. A rate whose denominator is not stated cannot be read
    at all, so the row states the count."""
    conn, make = scored
    run_id, report, raise_finding = make("claude-sonnet-5",
                                         calls={"crawl": 1})
    report("crawl")
    raise_finding("crawl", "sitemap-coverage", "Sitemap misses pages.")

    out = score(conn, run_id, LABELS)
    assert out["labels_caught"] == 1 and out["labels_scored"] == 1
    row = row_for(conn, out, "2026-08-24")
    assert "caught 1 of 1 labels scored" in row
    # And the rate itself, which is 1.0 here and means one-for-one.
    assert "| 1.00 |" in row


def test_a_partial_run_says_which_briefs_it_never_bought(scored, register):
    """Q-22, 2026-08-28. The two paid runs of 2026-08-24 bought four of the
    six labelled briefs, so three of the fixture's eight `expected` labels
    could not be caught by them at any price. The scorer already excludes a
    brief that never ran, which keeps the *rate* honest and moves the problem
    into the *denominator*: 5 of 5 and 5 of 8 then sit in one column, and a
    reader comparing them is comparing two things.

    The operator priced that cost when they chose to record the pair — *"the
    `catch` column stops being one denominator down the table"* — and it stops
    being one denominator whether or not anyone writes it down. So the row
    says which it is, derived from `tools_not_run` rather than remembered for
    the one pair this was noticed on.
    """
    conn, make = scored
    run_id, report, raise_finding = make("claude-sonnet-5",
                                         calls={"crawl": 1})
    report("crawl")
    raise_finding("crawl", "sitemap-coverage", "Sitemap misses pages.")

    out = score(conn, run_id, LABELS)
    # One of three `expected` labels reachable; `onpage-hygiene` never ran.
    assert out["labels_scored"] == 1 and out["labels_in_fixture"] == 3
    assert out["tools_not_run"] == ["hreflang", "onpage-hygiene"]

    row = row_for(conn, out, "2026-08-28")

    assert "PARTIAL" in row
    assert "not comparable with a row scored over all 3" in row
    assert "onpage-hygiene did not run" in row or "onpage-hygiene," in row
    # And the rate itself is untouched: 1.00 out of the one label it could
    # reach, not 0.33 out of a fixture two of whose briefs it never bought.
    assert "| 1.00 |" in row


def test_a_run_that_bought_every_labelled_brief_does_not_say_partial(scored,
                                                                     register):
    """The counter-assertion, and the reason the clause above is not vacuous.

    A note that appeared on every row would say nothing. `79a1fc02…` is the
    row in the live register that ran all six labelled briefs, and it must
    stay unqualified — otherwise `PARTIAL` degrades into decoration and the
    pair of 2026-08-24 stops being marked out by it.
    """
    conn, make = scored
    run_id, report, raise_finding = make(
        "claude-opus-5", calls={"crawl": 1, "onpage-hygiene": 1,
                                "hreflang": 1})
    for tool in ("crawl", "onpage-hygiene", "hreflang"):
        report(tool)
    raise_finding("crawl", "sitemap-coverage", "Sitemap misses pages.")

    out = score(conn, run_id, LABELS)
    assert out["tools_not_run"] == []
    assert out["labels_scored"] == out["labels_in_fixture"] == 3

    assert "PARTIAL" not in row_for(conn, out, "2026-08-28")
    # The live row for the one run that bought everything, read from the
    # register rather than from a fixture that agrees by construction.
    full = [r for r in _golden_rows(register.read_text(encoding="utf-8"))
            if "79a1fc02" in r]
    assert len(full) == 1 and "PARTIAL" not in full[0]


def test_a_replayed_rate_can_say_so_and_the_rest_is_still_derived(scored,
                                                                  register):
    """`extra_notes` is the escape hatch, and it is narrow on purpose.

    The pair of 2026-08-24 is scored from findings restored out of
    `analyst_cache`, which is not a fact any query against the run can reach —
    the rows KI-56 deleted are gone from `findings` and nothing links a cache
    row to a run id. Everything else in the cell is still derived, so a note
    that *could* have been derived cannot hide in here.
    """
    conn, make = scored
    run_id, report, _ = make("claude-sonnet-5", calls={"onpage-hygiene": 3})
    report("onpage-hygiene", page="/hot-water")

    row = row_for(conn, score(conn, run_id, LABELS), "2026-08-28",
                  ["the rate is a REPLAY, not a read of what is stored"])

    assert "the rate is a REPLAY" in row
    # Derived notes are not displaced by it: the denominator and the KI-56
    # caveat are both still there, and the row is still one row.
    assert "labels scored" in row and "KI-56" in row
    assert row.replace(r"\|", "X").count("|") - 1 == 8


def test_a_run_measuring_ki_56_says_so_in_its_own_row(scored, register):
    """The two paid runs of 2026-08-24 were billed for three `onpage-hygiene`
    pages each and stored one, because `record_expert_findings` deletes by
    `(run_id, dimension)`. The resulting 0.33-against-0.67 was quoted as a
    tier difference until the cache was replayed and both models turned out
    to have caught it.

    Detected from the database — more calls billed than reports stored — and
    not from a hard-coded warning, so the note stops appearing on the day
    KI-56 is fixed rather than becoming false.
    """
    conn, make = scored
    run_id, report, _ = make("claude-opus-5", calls={"onpage-hygiene": 3})
    report("onpage-hygiene", page="/hot-water")

    row = row_for(conn, score(conn, run_id, LABELS), "2026-08-24")

    assert "KI-56" in row
    assert "billed for 3 calls" in row and "stored 1 report" in row


def test_a_label_that_missed_on_a_page_the_brief_named_says_so_in_the_row(
        scored, register):
    """Q-20's amendment, carried out of the terminal.

    A page label degrades to a visible miss — that is why it was chosen over
    a label matching two ways, which degrades to an invisible pass. But the
    miss is only visible where it is read, and the lesson this register
    exists for is that a score printed to a terminal is not something a later
    reader finds. A miss where the brief DID name the page is the label's
    problem and not the model's, so reading the rate without it understates
    the model."""
    conn, make = scored
    run_id, report, raise_finding = make("claude-sonnet-5",
                                         calls={"onpage-hygiene": 1})
    report("onpage-hygiene")
    # The page IS named. The words are not: this brief called it something
    # else, so `/blocked-drains[h1]` reads as a miss it did not earn.
    raise_finding("onpage-hygiene", "image-alt-missing",
                  "Two images on this page have no alt text.",
                  "/blocked-drains")

    out = score(conn, run_id, LABELS)
    assert out["labels_missed_on_a_named_page"] == [
        "onpage-hygiene:/blocked-drains[h1]"]
    row = row_for(conn, out, "2026-08-25")

    assert "missed on a page the brief did name" in row
    assert "onpage-hygiene:/blocked-drains[h1]" in row
    # And the other miss is not swept in with it: nothing was raised for
    # /hot-water at all, which is a miss about the model and not the label.
    assert "/hot-water[description]" not in row


def test_the_token_count_is_a_count_and_not_a_float(scored, register):
    """`cost_entries.quantity` is REAL, so the real 2026-08-24 rows came out
    as `48216.0`. A count is not a measurement to one decimal place, and the
    trailing `.0` invites the next reader to wonder what a fraction of a token
    would be. Found by running this writer against the two stored paid runs
    rather than by reading the schema."""
    conn, make = scored
    run_id, report, _ = make("claude-sonnet-5", calls={"crawl": 2})
    report("crawl")

    row = row_for(conn, score(conn, run_id, LABELS), "2026-08-24")

    assert row.split("|")[6].strip() == "2000"


def test_a_run_with_no_price_says_why_rather_than_zero(scored, register):
    """A money column reading `0` says the run was free, and free is the one
    thing a paid run was not. `run_spend` fills `usd_absent_because`; the row
    has to carry it rather than formatting `None` as a number."""
    conn, make = scored
    run_id, report, _ = make("claude-sonnet-5")     # no cost entries at all
    report("crawl")

    row = row_for(conn, score(conn, run_id, LABELS), "2026-08-24")

    assert "no cost was recorded against this run" in row
    assert "| 0 |" not in row.split("|")[7]


def test_a_pipe_in_a_value_cannot_split_the_row(scored, register):
    """A caveat sentence, a model id or an absent-price reason is prose from
    somewhere else, and `|` is a column boundary in GFM. One unescaped pipe
    turns a register row into a malformed one — the class of defect the width
    guard exists to catch, arriving through the writer."""
    conn, make = scored
    run_id, report, _ = make("weird|model", calls={"crawl": 1})
    report("crawl")

    row = row_for(conn, score(conn, run_id, LABELS), "2026-08-24")

    assert r"weird\|model" in row
    assert row.replace(r"\|", "X").count("|") - 1 == 8
