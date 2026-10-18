"""Golden evaluation: score the expert briefs against hand-labelled truth.

Twenty-three briefs whose correctness has never been measured. This harness
is the measuring instrument; the labels are the part only a human can supply,
because "which of these pages is genuinely thin" is a judgement, not a query.

Labels file (JSON):

    {
      "site": "https://example.com/",
      "labelled_by": "your name",
      "labelled_at": "2026-08-08",
      "expected": [
        {"tool": "local-signals", "code": "opening-hours-missing",
         "note": "hours shown in footer image only"},
        {"tool": "crawl", "code": "sitemap-coverage"}
      ],
      "known_absent": [
        {"tool": "hreflang", "code": "missing-return-tags",
         "note": "single-locale site; raising this would be a false positive"}
      ]
    }

`expected` are issues a competent auditor agrees exist. `known_absent` are
traps: issues the site does NOT have, where a brief raising them is a false
positive worth counting.

TWO WAYS TO WRITE A LABEL, and the second is usually the right one.

A `code` label matches the brief's machine-readable index exactly. That works
only where the vocabulary is fixed, and for expert briefs it is not: the model
names its own checks, and this database holds 199 distinct ids against 22
deterministic ones. `cost-disclosure-absent` and `regulatory-identity-missing`
were both invented in the moment. Labelling by code would score a brief on
whether it guessed the same name, not on whether it found the problem.

A `page` label matches on what is objective — the URL the finding names —
with `mentions` keywords that must appear in its code or summary so an
unrelated finding on the same page is not counted as a hit:

    {"tool": "onpage-hygiene", "page": "/thin", "mentions": ["title"]}

Omit `page` only where the brief genuinely raises the finding with no URL,
and check that against a stored run rather than against the brief's declared
`scope`. Scope is not the test: `indexability` and `mobile-viewport` both
declare `scope: site` and both put the page in `affected_urls` anyway, which
is what run `79a1fc02…` measured. A site-scoped label reads `check_id` and
`summary` only, so pointing one at a brief that does name the URL throws the
sharpest evidence there is away and scores a correct finding as a miss.

Use `code` when a brief genuinely emits a fixed vocabulary. Use `page`
everywhere else, and drop it only where the run shows no URL to match on —
`hreflang` and `citations-nap` really do raise findings with an empty
`affected_urls`.

A page label costs one guarantee, and `_miss_reason` is what pays for it: on
the day a brief reports the same defect without naming the URL, the label
stops matching and reads as a clean miss. So every miss says WHICH KIND it
was — no finding carried this URL, or a finding carried it and the words did
not match. The second is the label drifting from the brief's vocabulary and
is not a statement about the model at all. Q-20, 2026-08-25.

Usage:
    python -m clauditseo.golden labels.json <run_id>
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


def label_id(item: dict) -> str:
    """How a label is named in the report. Its code when it has one, else the
    page and the words that had to appear."""
    if item.get("code"):
        return item["code"]
    where = item.get("page") or "site"
    return f"{where}[{'+'.join(item.get('mentions') or [])}]"


def _on_page(row: dict, page: str) -> bool:
    """Does this finding name that page?

    One implementation, because `_matches` and `_miss_reason` must agree
    about it exactly: a miss reason derived from a second, slightly different
    rule would explain a match that never happened.
    """
    return any(u.rstrip("/").endswith(page.rstrip("/")) or page in u
               for u in row["urls"])


def _matches(label: dict, rows: list[dict]) -> bool:
    """Did any raised finding satisfy this label?

    A `code` label is an exact match on the brief's own id. A `page` label
    matches on the URL — a fact about the site rather than about the model's
    naming — and requires every `mentions` keyword to appear in the finding's
    id or summary, so a different problem on the same page is not counted as
    a hit.
    """
    if label.get("code"):
        return any(r["check_id"] == label["code"] for r in rows)
    words = [w.lower() for w in (label.get("mentions") or [])]
    if not words:
        return False
    page = label.get("page")
    for row in rows:
        # A label with no page is site-scoped, and matches on the words
        # alone. That is for the briefs which really do raise with no URL —
        # `hreflang` is one, and the first version of this scorer reported
        # zero false positives for a brief that raised eight hreflang
        # findings on a single-locale site. A check that says "clean"
        # because it could not look is the exact failure this harness exists
        # to catch. It is not a licence to drop the page wherever a brief
        # declares `scope: site`: Q-20 measured two such briefs naming the
        # URL in `affected_urls`, where the words alone are the weaker test.
        if page is not None and not _on_page(row, page):
            continue
        hay = f"{row['check_id']} {row['summary']}".lower()
        if all(w in hay for w in words):
            return True
    return False


def _miss_reason(label: dict, rows: list[dict]) -> tuple[str, str]:
    """Why this label was not caught: `(kind, sentence)`.

    The amendment Q-20's answer attaches to page labels, and the reason page
    labels were chosen over a label that matches two ways. Both options
    degrade when a brief's behaviour changes, and they degrade in opposite
    directions: a page label degrades to a FALSE NEGATIVE — the rate drops,
    an operator sees it and investigates — where a two-way match degrades to
    a FALSE POSITIVE, quietly passing on words alone with nothing changed on
    screen. This harness's known failure mode is the flattering score (the
    run that reported 1.0 with three of five labels unscored behind it), so
    the visible miss wins. This function is what removes the one real cost:
    a miss that names its own reason is diagnosable rather than silent.

    The kinds, and why the split is the useful one:

      `no-url`    no finding named the page. An honest miss the brief earned.
      `words`     a finding DID name the page and the words did not match.
                  That is the label drifting from the brief's vocabulary, and
                  it is not a statement about the model at all — it is the
                  failure the `hreflang` trap recorded, made visible.
    """
    if label.get("code"):
        return "code", (f"no finding carried the check id {label['code']!r}"
                        f" ({len(rows)} raised by this brief)")
    words = [w.lower() for w in (label.get("mentions") or [])]
    if not words:
        return "no-words", ("the label lists no words to match on, so no"
                            " finding can satisfy it")
    shown = "+".join(words)
    page = label.get("page")
    if page is None:
        return "site-words", (
            f"site-scoped label: no finding's id or summary carried {shown}"
            f" ({len(rows)} raised by this brief)")
    on_page = [r for r in rows if _on_page(r, page)]
    if not on_page:
        return "no-url", (
            f"no finding named {page} ({len(rows)} raised by this brief,"
            " none on that page)")
    named = ", ".join(sorted(r["check_id"] for r in on_page))
    return "words", (
        f"{len(on_page)} finding(s) named {page} and none carried {shown}:"
        f" {named}. The label may have drifted from the brief's wording")


def _raised_rows(conn: sqlite3.Connection, run_id: str) -> dict[str, list[dict]]:
    """Every finding this run raised, grouped by the brief that produced it.

    Attribution, and the reason it is not just the dimension (item 137, brief
    v18 step AZ). A LEGACY brief writes its rows under `EXP:<tool>`; a CONTRACT
    brief corroborating a sweep check writes under the sweep's own dimension
    (`TEC/sitemap-invalid`, the Q-56 rule in `record_contract_findings`) and
    records the brief in `evidence.from_brief` instead — set server-side to the
    `tool_id`, never by the model, so it cannot be mislabelled from the prompt.
    crawl is the first contract brief scored against a sweep-check golden label,
    and under an EXP-only read it scored 0 on a finding it had raised.

    Read `from_brief` where present and fall back to the dimension suffix, so
    each row is attributed EXACTLY ONCE. `EXP:` rows carry `from_brief` too
    (the same writer sets it), so a `dimension OR from_brief` union that appended
    per matched clause would count them twice; the fallback reads one value per
    row and appends one entry."""
    out: dict[str, list[dict]] = {}
    for row in conn.execute(
            "SELECT dimension, check_id, summary, affected_urls, evidence FROM findings"
            " WHERE run_id=? AND (dimension LIKE 'EXP:%'"
            "   OR json_extract(evidence, '$.from_brief') IS NOT NULL)", (run_id,)):
        try:
            from_brief = (json.loads(row["evidence"] or "{}") or {}).get("from_brief")
        except (TypeError, ValueError):
            from_brief = None
        tool = from_brief or row["dimension"][4:]
        try:
            urls = json.loads(row["affected_urls"] or "[]")
        except (TypeError, ValueError):
            urls = []
        out.setdefault(tool, []).append({
            "check_id": row["check_id"] or "",
            "summary": row["summary"] or "",
            "urls": urls if isinstance(urls, list) else [],
        })
    return out


def score(conn: sqlite3.Connection, run_id: str, labels: dict) -> dict:
    """Catch rate per brief for one run. Only tools that both carry labels and
    actually ran are scored — a brief that never ran has not missed anything,
    and scoring it as a miss would punish the operator's tool choice rather
    than the model."""
    # One map, not two. `raised: dict[str, set[str]]` stood here beside this
    # one and was filled in the same loop without ever being consulted — a
    # reader looking for what decides a catch found two candidate structures
    # and only one live (CQ-224, ten reports). `raised_rows` carries the
    # check_id its twin held, so nothing is lost by its going.
    raised_rows = _raised_rows(conn, run_id)
    ran = {row["tool_id"] for row in conn.execute(
        "SELECT tool_id FROM expert_reports WHERE run_id=?", (run_id,))}

    expected: dict[str, list[dict]] = {}
    for item in labels.get("expected", []):
        expected.setdefault(item["tool"], []).append(item)
    traps: dict[str, list[dict]] = {}
    for item in labels.get("known_absent", []):
        traps.setdefault(item["tool"], []).append(item)

    per_tool = {}
    #: Misses of the `words` kind, qualified by tool. Collected here rather
    #: than re-derived from the sentences, so the register row below can name
    #: them without parsing prose back into a fact.
    drifted: list[str] = []
    for tool in sorted(set(expected) | set(traps)):
        if tool not in ran:
            per_tool[tool] = {"scored": False, "reason": "tool did not run"}
            continue
        rows = raised_rows.get(tool, [])
        want = expected.get(tool, [])
        hit = [label_id(w) for w in want if _matches(w, rows)]
        gone = [w for w in want if not _matches(w, rows)]
        missed = [label_id(w) for w in gone]
        reasons = {label_id(w): _miss_reason(w, rows) for w in gone}
        drifted += [f"{tool}:{lid}" for lid, (kind, _why) in reasons.items()
                    if kind == "words"]
        fps = [label_id(t) for t in traps.get(tool, []) if _matches(t, rows)]
        # Everything raised that no label speaks to. Not wrong — unmeasured.
        claimed = {r["check_id"] for w in want + traps.get(tool, [])
                   for r in rows if _matches(w, [r])}
        per_tool[tool] = {
            "scored": True,
            "caught": sorted(hit),
            "missed": sorted(missed),
            # WHY each miss was a miss, per Q-20's amendment. A page label's
            # one cost is that it can stop matching silently; this is the
            # line that stops it being silent.
            "missed_because": {lid: why for lid, (_k, why) in
                               sorted(reasons.items())},
            "false_positives": sorted(fps),
            "unlabelled_raised": sorted(
                {r["check_id"] for r in rows} - claimed),
            "catch_rate": round(len(hit) / len(want), 2) if want else None,
        }
    scored = [t for t in per_tool.values() if t.get("scored")]
    total_want = sum(len(expected.get(t, [])) for t in expected
                     if per_tool.get(t, {}).get("scored"))
    total_hit = sum(len(t["caught"]) for t in scored)
    # The labels this run could never have caught, because the brief that
    # carries them was never run for it. `total_want` already excludes them —
    # that is the "a brief that never ran has not missed anything" rule above
    # — so the rate is honest and its DENOMINATOR is the thing that moves. A
    # run over four of six labelled briefs is scored out of five where a full
    # run is scored out of eight, and the two rates sit in one column.
    # Q-22, 2026-08-28: the pair of 2026-08-24 is exactly that row.
    absent = sorted(t for t in set(expected) | set(traps)
                    if not per_tool.get(t, {}).get("scored"))
    fixture_want = sum(len(v) for v in expected.values())
    return {
        "run_id": run_id,
        "labelled_by": labels.get("labelled_by"),
        "tools": per_tool,
        "overall_catch_rate": (round(total_hit / total_want, 2)
                               if total_want else None),
        "total_false_positives": sum(len(t["false_positives"]) for t in scored),
        # The rate's denominator, beside the rate. `scripts/run_golden.py`
        # records a run where three of five labels sat unscored behind an
        # overall 1.0; a rate whose denominator is not stated cannot be read
        # at all, and the register row below has to be able to say "3 of 5".
        "labels_caught": total_hit,
        "labels_scored": total_want,
        # What the denominator would have been had every labelled brief run,
        # and which briefs are missing. Two rates in one column are readable
        # only if the short one says it is short — see `row_for`.
        "labels_in_fixture": fixture_want,
        "tools_not_run": absent,
        # The misses that are not about the model: a finding named the page
        # and the label's words did not match it. Beside the rate because
        # this is the one class of miss an operator should read as "check the
        # label", and a terminal-only score is not something a later reader
        # finds — see REGISTER below, which carries this into `TIMINGS.md`.
        "labels_missed_on_a_named_page": sorted(drifted),
        "note": ("unlabelled_raised are findings outside the label set — not "
                 "wrong, just unmeasured. Review them; the good ones become "
                 "new labels."),
    }


# --------------------------------------------------------------------------
# The register — relay item 087.
#
# The harness printed its score and wrote it nowhere. Nine days of never being
# run was one reason there was no measurement on disk; this was the other, and
# it survives the first being fixed. A score that exists only in a terminal is
# not something a later reader finds by opening the repository.
# --------------------------------------------------------------------------

#: The tracked file a scoring run records into, and the table inside it.
#: `TIMINGS.md` rather than a new `ACCURACY.md`: the decision and what it cost
#: are written out in that file's own `## Golden accuracy runs` section, where
#: the next reader wondering about it is already standing.
#:
#: **Relative, resolved against the working directory** — not against this
#: module's own location. `pyproject.toml` packages `clauditseo*`, so this
#: module ships in the wheel, and the previous default
#: (`Path(__file__).resolve().parent.parent / "TIMINGS.md"`) walked out of
#: the package to whatever sat beside it: the checkout root in a source tree,
#: and `<site-packages>/TIMINGS.md` in an install. That is an undeclared
#: dependency on the checkout, and it arrived as an `OSError` raised by
#: `open` inside library code rather than as a refusal naming the register.
#: A relative default depends on the working directory instead — a
#: dependency the caller can see, and one `append_row` states when it fails.
REGISTER = Path("TIMINGS.md")
REGISTER_SECTION = "Golden accuracy runs"

#: A first cell of exactly three digits is how CodeDash recognises an audit
#: round. `_ROW` in `codedash/ingest/timings.py` matches `^\|\s*(\d{3})\s*\|`
#: followed by eight more cells, and it is pointed at this same `TIMINGS.md`
#: — so a golden row carrying both properties would be ingested as a round in
#: another repository's database, silently and with no error anywhere.
#:
#: The existing `## Verification crawls` table is safe only because it has
#: seven columns, which is a coincidence of its shape rather than a decision.
#: This appender does not rely on the count: it refuses the round-shaped first
#: cell outright, so a column added to the golden table later cannot make it
#: ingestible. Guarded over the live file by
#: `tests/test_a_golden_score_reaches_the_register.py`.
_ROUND_FIRST_CELL = re.compile(r"^\d{3}$")


def _cell(value: object) -> str:
    r"""One value, safe to sit between two pipes.

    `|` is a column boundary in GFM unless escaped, and a newline ends the
    table — so a model id, a caveat sentence or an absent-price reason
    reaching a cell unprocessed is how one register row becomes two malformed
    ones. `None` is an em-dash and never a zero: `TIMINGS.md` already uses the
    em-dash literally to mean unknown, and CodeDash's `_num` reads it that way.
    """
    text = "—" if value is None else str(value)
    return " ".join(text.split()).replace("|", r"\|") or "—"


def _cells(line: str) -> int:
    r"""GFM cell count. `\|` is one character inside a cell, not a boundary.

    The same rule as `tests/test_loop_instructions.py`'s width guard and as
    `scripts/timings-append.ps1`, which is the PowerShell counterpart of the
    appender below: the loop's skills append a timings row through that one,
    a scoring run appends through this one, and if the two disagreed about
    what a row is, the guard would go red on whichever wrote last.

    Python rather than shelling out to that script, deliberately. CI runs this
    suite on `ubuntu-latest` as well as `windows-latest`, and a harness that
    could only record its score on Windows would be untested on half the gate.
    """
    return line.replace(r"\|", "X").count("|") - 1


def append_row(row: str, path: Path | None = None,
               section: str = REGISTER_SECTION) -> int:
    """Insert `row` after the last body row of the table under `## section`.

    Returns the 1-based line it landed on.

    Free-hand appending against a file's end is what fails — a row appended to
    `TIMINGS.md` lands under `## Verification crawls`'s seven-column header
    and takes the width guard red at HEAD, twice already (`b90f568` →
    `8537598`, `bdb3390` → `04359e9`). An append against a *table's* end
    cannot, which is `scripts/timings-append.ps1`'s reasoning and is why three
    of the four table refusals below are its refusals; the fourth is
    CodeDash's. The first is this module's own — see `REGISTER`.

    Refuses rather than writing, all loud:

      1. there is no register at `path` at all;
      2. the row is not a row at all (no leading pipe);
      3. the row's first cell is round-shaped — see `_ROUND_FIRST_CELL`;
      4. no such section, or no delimited table under it;
      5. the row's cell count does not match the table's header width.
    """
    path = Path(path) if path is not None else REGISTER
    # Refused before `open`, so a missing register reads as a sentence naming
    # what was looked for and where, rather than as an `OSError` out of
    # library code. `REGISTER` is relative, so "where" is the working
    # directory, and saying so is the whole point of the refusal.
    if not path.is_file():
        raise FileNotFoundError(
            f"no register at {path} (looked in {path.resolve().parent}). "
            "The default is relative to the working directory, so a scoring "
            "run records into the checkout it is run from; pass `path=` to "
            "name another file.")
    # `newline=""` on both ends, so the file's own terminator is seen and
    # kept. Without it `read_text` reports `\n` for a CRLF file and Windows
    # translates on the way back out — the round trip happens to survive on
    # Windows and would rewrite every line of a CRLF file checked out on
    # Linux, which is a 573-line diff hiding one appended row.
    with open(path, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)

    if not row.strip().startswith("|"):
        raise ValueError(f"not a table row: {row!r}")
    first = row.strip().strip("|").split("|")[0].strip()
    if _ROUND_FIRST_CELL.match(first):
        raise ValueError(
            f"first cell {first!r} is three digits, which CodeDash reads as an"
            " audit round number. Put the model or the date in column one.")

    start = next((i for i, ln in enumerate(lines)
                  if ln.strip() == f"## {section}"), -1)
    if start < 0:
        raise ValueError(f"no section '## {section}' in {path}")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))

    delim = -1
    for i in range(start + 1, end):
        if (lines[i].lstrip().startswith("|") and "---" in lines[i]
                and set(lines[i]) <= set("| -:") and "|" in lines[i - 1]):
            delim = i
            break
    if delim < 0:
        raise ValueError(f"no table under '## {section}' in {path}")

    width = _cells(lines[delim])
    got = _cells(row)
    if got != width:
        raise ValueError(
            f"row has {got} cells, the '## {section}' table needs {width}")

    # Walk to the last contiguous body row of THIS table. A blank line ends a
    # table per GFM and a heading ends the section — the same rule the width
    # guard's `_ENDS_A_TABLE` uses. An empty table stops at the delimiter,
    # which is the correct insertion point for its first row.
    last = delim
    for i in range(delim + 1, end):
        if not lines[i].lstrip().startswith("|"):
            break
        last = i

    lines.insert(last + 1, row.rstrip())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(eol.join(lines))
    return last + 2


def row_for(conn: sqlite3.Connection, out: dict, on: str,
            extra_notes: list[str] | None = None) -> str:
    """The register row for one scored run.

    Eight cells: `model | date | run_id | catch | false_pos | tokens | usd |
    notes`. The model is column one so the row can never be round-shaped, and
    it is read back from `expert_reports` rather than taken from whatever was
    passed to `--model` — the flag says what was asked for, the database says
    what ran, and `--model` may be absent entirely on a per-tier run.

    `notes` carries the three things a bare rate cannot carry: its
    denominator, whether that denominator is the whole fixture, and any reason
    this run's stores are not a measurement of a model at all. The caveats
    come from `_caveats`, which detects KI-56 from the gap between calls
    billed and reports stored, so the note stopped appearing for runs made
    after the fix without anyone editing this — and still appears for the runs
    of 2026-08-24, which really are unscoreable.

    **A partial run says so, derived rather than remembered.** Q-22 chose to
    record the two paid runs of 2026-08-24 as a four-tool partial, and the
    cost the operator priced for that choice was that *"the `catch` column
    stops being one denominator down the table"*. It stops being one
    denominator whether or not anyone writes it down; what this pays for is
    that the short rate is never silently short. The scorer already excludes a
    brief that never ran, so the fact is in `tools_not_run` and needs no
    memory of which run was which.

    `extra_notes` is for what the database cannot know — the row for a run
    whose findings were replayed out of `analyst_cache` is the case it was
    added for. Everything derivable is derived; this is the escape hatch, and
    a note that could have been derived belongs above rather than here.
    """
    from clauditseo.persistence.runs import run_spend

    spend = out.get("spend") or run_spend(conn, out["run_id"])
    models = spend.get("models") or []
    if not models and out.get("model"):
        models = [out["model"]]

    rate = out.get("overall_catch_rate")
    # `cost_entries.quantity` is REAL, so a token count arrives as `48216.0`.
    # A count is not a measurement to one decimal place, and the `.0` invites
    # the next reader to wonder what the fraction of a token was.
    tokens = spend.get("tokens")
    if isinstance(tokens, float) and tokens.is_integer():
        tokens = int(tokens)
    if spend.get("usd") is None:
        usd = "— " + (spend.get("usd_absent_because") or "not priced")
    else:
        usd = f"{spend['usd']:.4f}" + (
            " (floor)" if spend.get("is_floor") else "")

    notes = [f"caught {out.get('labels_caught')} of"
             f" {out.get('labels_scored')} labels scored"]
    # The rate is out of what this run could reach, not out of the fixture.
    # Said here so a reader comparing two rows in this column is told they are
    # two denominators rather than left to work it out from the run ids.
    absent = out.get("tools_not_run") or []
    in_fixture = out.get("labels_in_fixture")
    if absent and in_fixture:
        notes.append(
            f"PARTIAL, not comparable with a row scored over all"
            f" {in_fixture}: {', '.join(absent)} did not run for this run, so"
            f" {in_fixture - (out.get('labels_scored') or 0)} of the"
            f" fixture's {in_fixture} expected labels were never purchased"
            " and are excluded from the rate rather than counted as missed")
    # A miss on a page the brief DID name is the label's problem, not the
    # model's, and reading the rate without it would understate the model.
    # The other kind of miss needs no note: it is what the rate already says.
    drifted = out.get("labels_missed_on_a_named_page") or []
    if drifted:
        notes.append(
            f"{len(drifted)} label(s) missed on a page the brief did name,"
            f" so the words and not the finding are what failed: "
            + ", ".join(drifted))
    notes += _caveats(conn, [out["run_id"]])
    notes += list(extra_notes or [])

    return "| " + " | ".join(_cell(v) for v in (
        "+".join(models) or "unknown",
        on,
        out["run_id"],
        f"{rate:.2f}" if rate is not None else None,
        out.get("total_false_positives"),
        tokens,
        usd,
        "; ".join(notes),
    )) + " |"


def record(conn: sqlite3.Connection, out: dict, on: str,
           path: Path | None = None,
           section: str = REGISTER_SECTION,
           extra_notes: list[str] | None = None) -> dict:
    """Write one scored run into the register. Returns where it landed.

    `on` is the date the run was scored, passed in rather than read off the
    clock so the caller — and a test — decides what the row says.
    """
    row = row_for(conn, out, on, extra_notes)
    line = append_row(row, path, section)
    return {"path": str(Path(path) if path is not None else REGISTER),
            "line": line, "row": row, "section": section}


def _qualified(out: dict, key: str) -> set[str]:
    """One flat set of `tool:label` keys, so two runs can be diffed at all.

    The scorer reports per tool, and two different briefs can produce the same
    `label_id` — `site[hreflang]` is not `site[nap]`'s neighbour by accident.
    Flattening on the bare id would let one tool's gain cancel another's loss.
    """
    return {f"{tool}:{lid}" for tool, res in out["tools"].items()
            if res.get("scored") for lid in res.get(key, [])}


def _caveats(conn: sqlite3.Connection, run_ids: list[str]) -> list[str]:
    """Reasons this pair cannot be read as a model difference, from evidence.

    KI-56, **fixed in the product and still true of runs stored before the
    fix**, which is exactly the case this function exists for. Until migration
    0029 and `QUESTIONS.md` Q-23, `record_expert_findings` deleted by
    `(run_id, dimension)` and `expert_reports` was keyed `(run_id, tool_id)`,
    so a page-scoped brief run against three pages kept only the last one. The
    runs of 2026-08-24 were billed for three `onpage-hygiene` calls each and
    stored one report each, and the resulting 0.33-against-0.67 was quoted as
    a tier difference until the cache was replayed and both models turned out
    to have caught it. Those runs are still on disk and still unscoreable, and
    this is what says so when one of them is read.

    Detected rather than asserted: `cost_entries` holds one row per call, so
    more calls than stored reports IS the deletion, visible without knowing
    the bug exists. That is why the repair needed no edit here — a hard-coded
    warning would now be false about every run made since the fix, while this
    one has gone quiet for them on its own and stayed loud about 2026-08-24.
    It is also why the two halves of KI-56 had to land together: repairing
    `expert_reports` alone would have made calls equal reports and silenced
    this while the findings went on being deleted.
    """
    out = []
    for run_id in run_ids:
        for row in conn.execute(
                "SELECT substr(ce.operation, 8) AS tool, COUNT(*) AS calls"
                " FROM cost_entries ce WHERE ce.run_id=?"
                " AND ce.operation LIKE 'EXPERT:%' GROUP BY ce.operation"
                " HAVING calls > 1", (run_id,)):
            stored = conn.execute(
                "SELECT COUNT(*) AS n FROM expert_reports WHERE run_id=?"
                " AND tool_id=?", (run_id, row["tool"])).fetchone()["n"]
            if row["calls"] > stored:
                out.append(
                    f"run {run_id[:8]} was billed for {row['calls']} calls to"
                    f" {row['tool']} and stored {stored} report(s): all but"
                    " the last page were deleted before scoring (KI-56), so"
                    " this brief's score measures the defect, not the model")
    return out


def _side(conn: sqlite3.Connection, run_id: str, labels: dict) -> tuple[dict, dict]:
    """One run's score, and the summary the comparison prints for it."""
    from clauditseo.persistence.runs import run_spend

    out = score(conn, run_id, labels)
    models = [r["model_id"] for r in conn.execute(
        "SELECT DISTINCT model_id FROM expert_reports WHERE run_id=?"
        " AND model_id IS NOT NULL ORDER BY model_id", (run_id,))]
    return out, {
        "run_id": run_id,
        "models": models,
        "overall_catch_rate": out["overall_catch_rate"],
        "total_false_positives": out["total_false_positives"],
        "spend": run_spend(conn, run_id),
    }


def _ratio(baseline: float | None, candidate: float | None) -> float | None:
    """None rather than a number wherever the division would be meaningless —
    a missing price and a free run are different facts, and `0` or `inf` in a
    column headed "x the money" reads as the second."""
    if not baseline or candidate is None:
        return None
    return round(candidate / baseline, 4)


def compare(conn: sqlite3.Connection, baseline_id: str, candidate_id: str,
            labels: dict) -> dict:
    """Two scored runs, and which labels moved in each direction.

    The question `scripts/run_golden.py` is for — "does the deep tier earn its
    price" — needs both halves in one place: what the candidate caught that
    the baseline did not, and what each one cost. Until this existed the
    harness advertised a `--compare` flag it did not have, and the arithmetic
    was done by hand from two JSON blobs.

    The vocabulary is `expert_delta`'s, over labels instead of check ids:
    `new`, `resolved` and `persisting` mean here what they mean there. Two
    additions, both because a catch is not a finding:

      - `lost` — caught by the baseline and not by the candidate. A newer
        model losing a label is the fact a comparison is most likely to omit
        and the one most worth knowing.
      - `missed_by_both` — a shared blind spot. Two runs agreeing is not two
        runs being right, and a difference of zero must not read as coverage.

    Says nothing about which model is better. It reports what the two runs
    stored, with `caveats` naming any reason those stores are not comparable.
    """
    base_score, baseline = _side(conn, baseline_id, labels)
    cand_score, candidate = _side(conn, candidate_id, labels)

    caught_a = _qualified(base_score, "caught")
    caught_b = _qualified(cand_score, "caught")
    missed_a = _qualified(base_score, "missed")
    missed_b = _qualified(cand_score, "missed")
    fp_a = _qualified(base_score, "false_positives")
    fp_b = _qualified(cand_score, "false_positives")

    return {
        "baseline": baseline,
        "candidate": candidate,
        "caught": {
            "new": sorted(caught_b - caught_a),
            "lost": sorted(caught_a - caught_b),
            "persisting": sorted(caught_a & caught_b),
            "missed_by_both": sorted(missed_a & missed_b),
        },
        "false_positives": {
            "new": sorted(fp_b - fp_a),
            "resolved": sorted(fp_a - fp_b),
            "persisting": sorted(fp_a & fp_b),
        },
        "tokens_ratio": _ratio(baseline["spend"]["tokens"],
                               candidate["spend"]["tokens"]),
        "usd_ratio": _ratio(baseline["spend"]["usd"],
                            candidate["spend"]["usd"]),
        "caveats": _caveats(conn, [baseline_id, candidate_id]),
        "note": ("`new` and `lost` are labels, not findings: what each run was"
                 " scored as catching. Read `caveats` first — a difference"
                 " listed there is not a difference between the models."),
    }


def main() -> int:
    import sys

    from clauditseo.config import settings
    from clauditseo.db.connection import connect

    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    labels = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    conn = connect(settings().db_path)
    print(json.dumps(score(conn, sys.argv[2], labels), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
