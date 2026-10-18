"""A test that needs something the runner may not have is gated only where it has it.

Two questions of one shape, and the second was added because the first did not
generalise on its own. CQ-37 asked whether a clause needing a *browser* runs in
a job that installs one. CQ-209 asks the same about a clause needing *history*:
`checkout`'s default depth of 1 carries the tip commit and nothing else, so a
clause reading a pinned blob skips there exactly as a browser clause skips
without Chromium - and skips the same way, silently, inside a count nobody
reads.

CQ-37, reports 043 onward. Test files in this repository skip themselves when
Chromium or the built dashboard is missing, and in the `python` job that skip
is correct and deliberate: a bare `pip install -e .[dev]` still runs green,
which is what makes the suite usable on a machine with no browser.

**There were eight of them when this was written, all spelling the condition
as `not axe.available()`. There are now 126, spelling it six ways.** Item 192
measured that, and the measurement is the reason this file changed: the
predicate here could see 36 of the 126, so for 90 files the question CQ-37
asks was never actually asked. 87 of them run in no browser job at all -
recorded in `NOT_IN_CI` below, with what that register is and is not.

The consequence is that such a file gates **nothing** unless it is also named
in the one job that installs a browser. `tests/test_site_switch.py` was named
in no job at all: it skipped in `python` for want of Chromium and was absent
from `rendered-a11y`'s invocation, so its two assertions — that nothing on the
client screen survives a change of client — had never run in CI. The screen it
guards, `dashboard/src/selection.tsx`, is the subject of a live finding in
three registers at once (WF-14, `BACKLOG.md` B-20, `KNOWN_ISSUES.md` KI-34),
and the two regressions this project has shipped both landed on unguarded
dashboard screens.

**Both sides are derived from source, so this check can disagree with the
workflow.** The browser-gated set is read from `tests/`, not listed here; the
covering set is read from the jobs that actually install Playwright, not from
the job name. DISCIPLINE rule 5 — a check drawing its evidence from the thing
it checks can only pass — and rule 3's corollary that a hard-coded list of
seven is how file eight ships ungated. It is the same defect CQ-83 and CQ-90
record against other guards in this suite: a set written out by hand is a
guard shaped like today's answer.

**Why the predicate is "launches a browser" and not "carries a marker".**
A check keyed on `pytestmark` would see only the files that gate the whole
module, and report the rest as unguarded when they are not: many build a
marker in a helper and apply it per test, precisely so their static clauses
keep running in the browserless job (`test_heading_fault.py:211` says so). A
check keyed on the SKIP CONDITION - which is what this file used to do - has
the subtler version of the same fault: it finds the files that gate in the one
form it knows and is silent about the others, and silence from a guard is
indistinguishable from a clean tree.

So the population is what the file DOES: `sync_playwright(` called, or a
clause taking a fixture that launches a browser. Read from tokenised source,
so a pattern inside a string literal does not count - which is also why this
file no longer has to exclude itself by identity, as it did when it scanned
raw source for text it holds as a pattern. How a file gates is then a second
question, asked separately, with all six known forms accepted.

**CQ-209, the history half.** `aa5a11c` gave the rendered-a11y job
`fetch-depth: 0` and wrote out why: the pinned-blob lens in
`test_a_score_band_meaning_is_reachable_without_a_mouse.py` skipped at depth 1,
and that job turns any skip red, so it was caught on run 32630811647. The
`python` matrix job - the only job that runs the suite on Windows, and the only
one that runs the *whole* suite - was not given the same treatment, so there
the same clause resolved nothing, skipped, and was absorbed into the `44
skipped` that job's own comment says never names its members. The confidence
the loop places in that lens rested on one job.

Both sides of that check are derived too: the history-reading set is read from
`tests/`, and the jobs that would collect each file are read from their pytest
invocations - a job naming no path runs everything, which is what makes the
matrix job the one that matters here.

Parsed by indentation rather than with a YAML library, for the reason
`test_ci_bounds.py` records: nothing else here depends on PyYAML, and a key
under a known parent is a shape an indentation walk reads reliably.
"""

from __future__ import annotations

import ast
import pathlib
import re
import tokenize

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
TESTS = ROOT / "tests"

#: A job name: exactly two spaces, then a key, then nothing else on the line.
#: Same shape `test_ci_bounds.py` parses on, and for the same reason.
JOB = re.compile(r"^  ([A-Za-z][\w-]*):\s*$")

#: How a file says it drives a browser, and the source it is read from is
#: TOKENISED - every string literal dropped. That is not tidiness: the
#: previous matcher read raw source for `not axe.available()`, and this file
#: had to exclude itself by identity because it contains that text as the
#: pattern it scans with. Tokenising solves that class structurally rather
#: than by exception, so the identity exclusion is gone. It also drops the
#: false positive item 190 recorded - a meta-test whose `sync_playwright(`
#: sits inside a regex literal is describing browser-driving code, not
#: driving any.
DRIVES_CALL = re.compile(r"\bsync_playwright\s*\(")

#: Fixtures that start a browser. `served` is NOT one: it starts the API
#: server, and item 190 measured three files that take it, drive httpx and
#: never load a page.
BROWSER_FIXTURES = ("browser", "browser_page", "page")
FIXTURE_ARG = re.compile(r"\bdef\s+test_\w*\s*\(([^)]*)\)")

#: Every form in which this suite gates a browser clause. **Six, where the
#: previous version of this file knew one** and its comment said that one was
#: "written identically in all eight". There are no longer eight: 126 files
#: drive a browser now, and the single-pattern matcher could see 36 of them.
#: A guard whose population is a third of its subject is the weaker-matcher
#: defect this suite records against other guards, turned on itself.
#:
#: Read from source with docstrings and comment lines removed, but OTHER
#: strings kept - because the gates are strings. Strip every literal and
#: `find_spec("playwright")` disappears along with the prose, which is how the
#: first measurement of this reported 111 of 126 files ungated.
GATES = {
    "axe.available()": re.compile(r"not\s+axe\.available\(\)"),
    "find_spec": re.compile(r'find_spec\(\s*["\']playwright'),
    "importorskip": re.compile(r'importorskip\(\s*["\']playwright'),
    "needs_build": re.compile(r"\bneeds_build\b"),
    'DIST / "index.html"': re.compile(r'DIST\s*/\s*"index\.html"'),
    "DIST.exists()": re.compile(r"DIST\.exists\(\)"),
    "skip() naming the build":
        re.compile(r'skip\((?:reason=)?["\'][^"\']*'
                   r'(?:dashboard not built|npm run build|playwright)'),
}

#: Gated through an imported fixture rather than in its own source, with the
#: reason each. This is the honest form of the exemption item 190 also needed:
#: a file can be covered by a gate it does not contain.
GATED_THROUGH = {
    "tests/test_real_data_scale.py":
        "every rendered clause takes `served`, imported from "
        "`test_a11y_rendered`, whose module-level skip covers this file too. "
        "Measured by item 190: it passes with `dashboard/dist` moved aside.",
}

#: Browser-driving tests that NO CI job runs.
#:
#: **This register is a bound, not a coverage claim, and the difference is the
#: point.** Each of these files drives a browser, gates itself so it skips
#: cleanly rather than timing out, and is named in no job that installs one -
#: so in CI it reports green having executed nothing. That is CQ-37's defect,
#: at the scale of 87 files, and it was invisible because the matcher above
#: could not see them.
#:
#: It is recorded rather than closed because closing it means adding files to
#: `rendered-a11y`, and that job's runtime is what decides how long CI takes
#: (KI-17: one step in it has a 250x spread). How many of these are worth that
#: is the operator's call on CI minutes, filed as item 192. What is NOT
#: negotiable is that the number be visible and not grow.
#:
#: Written out rather than derived. A derived exemption list excuses exactly
#: what it derives and can never fail, which is the shape DISCIPLINE rule 5
#: refuses. Held to the tree by two clauses below: nothing outside this list
#: may be uncovered, and nothing in it may have stopped needing to be here.
NOT_IN_CI = (
    "tests/test_a_brief_never_runs_against_a_nav_scan.py",
    "tests/test_a_cause_opens_to_its_templates.py",
    "tests/test_a_headline_figure_reaches_what_it_counts.py",
    "tests/test_a_re_run_is_one_press_from_the_shop.py",
    "tests/test_a_measurement_says_how_old_it_is.py",
    "tests/test_a_read_pill_carries_its_run.py",
    "tests/test_a_running_audit_is_a_state_of_its_own.py",
    "tests/test_a_site_domain_can_be_corrected_in_the_product.py",
    "tests/test_buttons_are_five_variants.py",
    "tests/test_canonical_chains_are_walked.py",
    "tests/test_causes_come_before_instances.py",
    "tests/test_control_edges_meet_three_to_one.py",
    "tests/test_every_tone_and_term_has_one_definition.py",
    "tests/test_find_and_deliver.py",
    "tests/test_five_small_labels_say_what_is_shown.py",
    "tests/test_free_work_is_not_offered_for_sale.py",
    "tests/test_home_is_the_landing_one_floor_up.py",
    "tests/test_money_and_deletes_ask_first.py",
    "tests/test_nothing_false_renders_while_it_loads.py",
    "tests/test_one_catalogue_one_order.py",
    "tests/test_one_scope_per_pane.py",
    "tests/test_page_mode_narrows_the_record_to_the_page.py",
    "tests/test_run_all_confirms_at_the_defaults.py",
    "tests/test_scan_scope_is_written_and_trusted.py",
    "tests/test_scope_is_a_mode.py",
    "tests/test_targets_meet_the_24px_floor.py",
    "tests/test_the_admin_screen_is_one_section_at_a_time.py",
    "tests/test_the_analyses_pane_reads_one_audit.py",
    "tests/test_the_audit_pane_lists_runs_once.py",
    "tests/test_the_bar_is_picker_and_counts.py",
    "tests/test_the_cadence_grid_is_admins.py",
    "tests/test_the_catalogue_is_a_drawer.py",
    "tests/test_the_client_landing_is_three_lanes.py",
    "tests/test_the_contract_agrees_with_the_sweep.py",
    "tests/test_the_crawl_depth_block_is_drawn.py",
    "tests/test_the_crawl_diff_gates_on_comparability.py",
    "tests/test_the_drawers_numbers_agree.py",
    "tests/test_the_first_prompt_is_title_and_description.py",
    "tests/test_the_fix_step_is_done_when_nothing_awaits_a_look.py",
    "tests/test_the_four_destinations.py",
    "tests/test_the_frame_is_two_rows.py",
    "tests/test_the_free_only_filter.py",
    "tests/test_the_head_is_a_headline_then_actions.py",
    "tests/test_the_headings_outline_blocks_are_drawn.py",
    "tests/test_the_headings_part_page.py",
    "tests/test_the_images_budget_blocks_are_drawn.py",
    "tests/test_the_images_part_page.py",
    "tests/test_the_landing_matches_the_reference.py",
    "tests/test_the_legend_is_a_strip_above_the_content.py",
    "tests/test_the_links_part_page.py",
    "tests/test_the_narrowable_site_slot.py",
    "tests/test_the_pane_can_be_reached_past_the_chrome.py",
    "tests/test_the_parser_enforces_the_contract.py",
    "tests/test_the_part_page_column.py",
    "tests/test_the_part_page_is_three_blocks.py",
    "tests/test_the_part_page_regressions_stay_fixed.py",
    "tests/test_the_precheck_pane_compares_and_suggests.py",
    "tests/test_the_precheck_pane_is_tile_one.py",
    "tests/test_the_rail_is_a_strip.py",
    "tests/test_the_rail_says_partial_where_work_remains.py",
    "tests/test_the_re_audit_column_puts_the_run_first.py",
    "tests/test_the_re_audit_drawer_never_pretends_to_narrow.py",
    "tests/test_the_record_filters_are_chips.py",
    "tests/test_the_record_filters_by_part.py",
    "tests/test_the_record_headline_is_the_check.py",
    "tests/test_the_record_opens_grouped_by_check.py",
    "tests/test_the_registry_and_the_site_record_serve_the_briefs.py",
    "tests/test_the_reports_screen_generates_first.py",
    "tests/test_the_reports_verbs_sit_behind_the_row.py",
    "tests/test_the_scope_bar_is_three_columns.py",
    "tests/test_the_site_screen_picks_no_audit.py",
    "tests/test_the_score_trend_is_drawn.py",
    "tests/test_the_screen_lands_where_the_work_is.py",
    "tests/test_the_security_part_page_leads_with_the_verdict.py",
    "tests/test_the_sidebar_count_is_the_records_count.py",
    "tests/test_the_site_record_has_a_brand.py",
    "tests/test_the_standing_position_outlives_the_tab.py",
    "tests/test_the_step_names_are_the_navigation.py",
    "tests/test_the_strip_panel_holds_its_tallest_state.py",
    "tests/test_the_strip_survives_the_position_failing.py",
    "tests/test_the_structured_data_picture_is_drawn.py",
    "tests/test_the_tab_row_is_retired.py",
)

#: A test path as it is written in a `pytest` invocation.
TEST_PATH = re.compile(r"tests/test_\w+\.py")

#: How a test reads an object that only exists in history: a `git` executable
#: and a `show` subcommand in the same file. Two tokens rather than one regex
#: over the whole invocation, because the call is built as a list and the
#: executable is resolved separately - `shutil.which("git")` then
#: `[git, "show", SHA + ":path"]` - so no single line carries both.
#:
#: Coarse on purpose. A file that runs `git show` for some other reason would
#: be swept in, and the answer for it is the same: it needs history to be
#: there. What must not happen is the opposite, a file that reads a pinned blob
#: and is not counted, which is the defect this pair of clauses exists for.
GIT_EXE = re.compile(r'which\("git"\)|"git"')
GIT_SHOW = re.compile(r'"show"')

#: `actions/checkout`, and the one option that makes history present. Any
#: finite depth expires - the pinned SHA only ever recedes - so `0` is the
#: property, not "some depth was set". The a11y job's own comment argues this
#: at `.github/workflows/ci.yml:242`.
CHECKOUT = re.compile(r"^\s*-\s+uses:\s*actions/checkout")
STEP = re.compile(r"^      - ")
FULL_HISTORY = re.compile(r"^\s*fetch-depth:\s*0\s*$")


def _job_bodies() -> dict[str, str]:
    """Map every job in `ci.yml` to its own lines, job header excluded.

    `test_ci_bounds.py` parses the same file for a key at job level and needs
    only the match; this needs the slice between one job header and the next,
    which is why the walk is here rather than imported.
    """
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        header = JOB.match(line)
        if header:
            current = header.group(1)
            bodies[current] = []
        elif current is not None:
            bodies[current].append(line)
    return {name: "\n".join(body) for name, body in bodies.items()}


def _code(path: pathlib.Path) -> str:
    """Source with every string literal and comment removed.

    Tokenised rather than regexed. The distinction it buys is the one this
    guard kept getting wrong: a file that NAMES `sync_playwright(` inside a
    regex literal describes browser-driving code and drives none, and the
    previous version of this file had to exempt itself by identity for exactly
    that reason - it holds its own patterns as strings. Structural, so no
    exemption is needed and none can be forgotten.
    """
    out: list[str] = []
    try:
        with open(path, "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type in (tokenize.STRING, tokenize.COMMENT):
                    continue
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return path.read_text(encoding="utf-8")
    return " ".join(out)


def _live(path: pathlib.Path) -> str:
    """Source with docstrings and comment lines removed, other strings kept.

    The complement of `_code`, and both are needed because the two questions
    differ: driving a browser is a CALL, so every literal must go; gating on
    one is often a literal - `find_spec("playwright")` - so only the prose
    may. Measured: stripping every string reports 111 of 126 files ungated,
    all but two of them wrongly.

    Docstring spans come from `ast` rather than a triple-quote regex, because
    this suite is full of triple-quoted values that are not docstrings - the
    JavaScript it evaluates in the page.
    """
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    drop: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)) or not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            drop.update(range(first.lineno,
                              (first.end_lineno or first.lineno) + 1))
    return "\n".join(ln for n, ln in enumerate(text.splitlines(), 1)
                      if n not in drop and not ln.lstrip().startswith("#"))


def _browser_driving() -> list[str]:
    """Every test file with a CLAUSE that launches a browser, repo-relative.

    Launching, not merely needing: `sync_playwright(` called, or a clause
    taking a fixture that starts one. 126 files, where the predicate this
    replaced could see 36.

    **And it must have a clause.** Two files in this suite hold only fixtures
    - a server, a browser, a seeded site - because 29 others import from them;
    item 196 emptied them of tests and they cannot be deleted for that reason.
    They still call `sync_playwright(`, so they matched, and the CQ-37 clause
    then asked which job runs them. None does, and none should: there is
    nothing in them to run. Naming such a file in the browser job adds a path
    that collects zero tests; putting it in the recorded bound records a
    coverage gap that does not exist. A fixture module's driving belongs to
    the files that import it, which are counted on their own account.
    """
    out = []
    for path in sorted(TESTS.glob("test_*.py")):
        code = _code(path)
        if not re.search(r"\bdef test_\w+\s*\(", code):
            continue
        if DRIVES_CALL.search(code) or any(
                any(re.search(r"\b" + f + r"\b", args)
                    for f in BROWSER_FIXTURES)
                for args in FIXTURE_ARG.findall(code)):
            out.append(path.relative_to(ROOT).as_posix())
    return out


def _gates(rel: str) -> list[str]:
    """Which gate forms a file states, if any."""
    live = _live(ROOT / rel)
    return [name for name, pat in GATES.items() if pat.search(live)]


def _covered() -> set[str]:
    """Test paths named by a `pytest` invocation in a job that has a browser.

    The job is identified by the step that installs one, not by its name: a
    renamed or a second browser job counts the moment it installs Playwright,
    and a job named `rendered-a11y` that stopped installing one would stop
    counting, which is the honest answer in both directions.
    """
    covered: set[str] = set()
    for body in _job_bodies().values():
        if "playwright install" not in body:
            continue
        for line in body.splitlines():
            if "pytest " in line:
                covered.update(TEST_PATH.findall(line))
    return covered


def _history_reading() -> list[str]:
    """Every test file that reads a git object, repo-relative.

    Excluded by identity like `_browser_gated`, and for the same reason: this
    file carries the patterns it scans with, so a scan that did not exclude
    itself would report itself as a history reader and be "fixed" by an
    assertion about a file that reads no history at all.
    """
    out = []
    for path in sorted(TESTS.glob("test_*.py")):
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if GIT_EXE.search(text) and GIT_SHOW.search(text):
            out.append(path.relative_to(ROOT).as_posix())
    return out


def _jobs_collecting(path: str) -> set[str]:
    """Jobs whose `pytest` invocation would collect `path`.

    A job that names test paths collects those; a job that names none - the
    `python` matrix job's `pytest -n auto --dist loadfile -ra` - collects
    everything, and that is the case CQ-209 turns on. Comment lines are
    skipped: three of them in this workflow mention pytest while running
    nothing.
    """
    out = set()
    for name, body in _job_bodies().items():
        for line in body.splitlines():
            if line.lstrip().startswith("#") or "pytest " not in line:
                continue
            named = TEST_PATH.findall(line)
            if not named or path in named:
                out.add(name)
    return out


def _checkout_has_history(body: str) -> bool:
    """Whether any `actions/checkout` step in this job asks for full history.

    Walked by step boundary rather than by looking for `fetch-depth` anywhere
    in the job: a `with:` block belongs to the step above it, and a job may
    check out more than once.
    """
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not CHECKOUT.match(line):
            continue
        for follower in lines[index + 1:]:
            if STEP.match(follower):
                break
            if FULL_HISTORY.match(follower):
                return True
    return False


def test_the_history_reading_set_is_not_empty():
    """The floor, stated on its own so the clause below cannot pass through it.

    CQ-207 and CQ-210 are both the case: a derivation that quietly returns
    nothing makes the real assertion vacuous and reads exactly like a clean
    tree. If the pinned-blob lens is ever reworded out of this shape, this goes
    red and says so, rather than the clause below going green for a workflow
    nobody checked.
    """
    readers = _history_reading()
    assert readers, (
        "no test file under tests/ was found to read a git object, so the "
        "clause below is asking about nothing. Either the pinned-blob lens "
        "has been reworded away from `git show`, or GIT_EXE/GIT_SHOW have "
        "stopped matching how it is written.")


def test_a_clause_reading_history_runs_only_where_history_was_checked_out():
    """CQ-209. A pinned-blob lens in a job checked out at depth 1 gates nothing.

    It does not fail there - it skips, which is the whole problem. In the
    rendered-a11y job a skip is red by an explicit gate; in the `python` matrix
    job it joins a count that job's own comment describes as never saying which
    tests it holds. So the lens proving the UX-07 matcher can still see the
    defect gated nothing on the only job that runs the suite on Windows, and
    its absence was invisible there by design.
    """
    bodies = _job_bodies()
    blind = [f"{path} would be collected by job `{job}`"
             for path in _history_reading()
             for job in sorted(_jobs_collecting(path))
             if not _checkout_has_history(bodies[job])]
    assert not blind, (
        "these clauses read a git object in a job whose checkout has no "
        "history, so they skip there and gate nothing - give the job's "
        "`actions/checkout` step `fetch-depth: 0`:\n  " + "\n  ".join(blind))


def test_the_browser_driving_set_is_not_empty():
    """DISCIPLINE rule 5: a derivation that silently returned nothing would
    make every assertion below it vacuous, and would look identical to a tree
    with nothing to check."""
    driving = _browser_driving()
    assert len(driving) >= 100, (
        f"the browser-driving derivation found {len(driving)} files; it read "
        "126 when item 192 widened it, so the signals have probably been "
        "reworded and this file is now checking almost nothing")


def test_every_browser_driving_test_says_it_needs_a_browser():
    """A file that drives a browser and gates on nothing does not skip where
    there is no browser - it fails, with a Playwright timeout that names no
    cause. Item 190 measured that class at 317 failures in an exported tree.

    Six gate forms are accepted, and the count is the point: the predicate
    this replaced knew one and its comment claimed that one was universal.
    Where a file is covered by a gate it does not contain, `GATED_THROUGH`
    names it with the reason.
    """
    quiet = [rel for rel in _browser_driving()
             if not _gates(rel) and rel not in GATED_THROUGH]
    assert not quiet, (
        "these launch a browser and state no condition on having one, so "
        "they fail with a timeout rather than skipping:\n  "
        + "\n  ".join(quiet)
        + "\n\nGate them, or name the file in GATED_THROUGH with the gate "
          "that already covers it.")


def test_every_gated_through_entry_is_still_a_file_that_needs_the_exemption():
    """An exemption outliving its reason is the CQ-145 shape: it sits there
    excusing nothing, and the next reader trusts it."""
    stale = []
    for rel, why in GATED_THROUGH.items():
        assert why.strip(), f"{rel} is exempted with no reason"
        if not (ROOT / rel).is_file():
            stale.append(f"{rel}: gone from the tree")
        elif rel not in _browser_driving():
            stale.append(f"{rel}: no longer drives a browser")
        elif _gates(rel):
            stale.append(f"{rel}: now states its own gate, so the exemption "
                         "is excusing nothing")
    assert not stale, "stale GATED_THROUGH entries:\n  " + "\n  ".join(stale)


def test_a_job_with_a_browser_exists_and_names_files():
    """The covering set is read from a real job, not from an empty parse."""
    covered = _covered()
    assert covered, (
        "no job in ci.yml both installs Playwright and names test files in a "
        "pytest invocation — every browser-gated test in this suite is "
        "therefore running nowhere")


def test_every_file_the_browser_job_names_still_exists():
    """The other direction, and the one that took CI down.

    Its neighbour below asks whether every browser-gated test is NAMED in a
    job that has a browser. This asks whether every name in that job is still
    a file - and the failure mode is worse than a red test, which is why it
    earns a clause of its own.

    `pytest` treats a missing path as a usage error: it exits 4 before running
    anything. So on 2026-09-22, with two files deleted by item 188 still named
    in the list, `rendered-a11y` reported "no tests ran in 0.00s" - the axe
    pass over every screen, the reflow pass, the chrome-width sweep, all of it
    executed nothing - and the step's own skip-check then printed a message
    about the sweep having skipped, which it had not. The private suite was
    green throughout, because nothing in the tree reads that list for
    existence.

    Derived from ci.yml rather than hand-kept, like its neighbours: a file
    removed from the tree and left in the list fails here, in the repository,
    rather than in a CI run whose message names the wrong cause.
    """
    covered = _covered()
    assert covered, "no browser job names any test files"
    missing = sorted(p for p in covered if not (ROOT / p).is_file())
    assert not missing, (
        "ci.yml's browser job names files that no longer exist, so pytest "
        "exits 4 and the whole job runs NOTHING rather than failing one "
        f"clause: {', '.join(missing)}")


def test_every_browser_driving_test_runs_in_ci_or_is_a_recorded_bound():
    """CQ-37. A file that drives a browser and is named in no browser job is
    gated by nothing: it reports green in the job that cannot run it, and the
    job that could run it never asks for it.

    The failure this was written against is `tests/test_site_switch.py`, whose
    two assertions had never executed in CI.

    **What changed at item 192.** The predicate this clause reads went from 36
    files to 126, and 87 of those turned out to run in no browser job. They are
    in `NOT_IN_CI` with the reason recorded there - a bound on CI minutes, not
    a coverage claim. So this clause no longer says "every browser test runs
    in CI"; it says every one either runs there or is on a list somebody
    decided to put it on. That is weaker, and it is true, which the previous
    version was not.

    The teeth are in the direction that matters: a NEW browser-driving test
    fails here until it is named in the browser job. `NOT_IN_CI` cannot absorb
    it without an edit that shows up in a diff and raises the count.
    """
    covered = _covered()
    orphans = [rel for rel in _browser_driving()
               if rel not in covered and rel not in NOT_IN_CI]
    assert not orphans, (
        "these launch a browser, are named in no job that installs one, and "
        "are not in the recorded bound - so they execute nowhere in CI while "
        f"reporting green:\n  " + "\n  ".join(orphans)
        + "\n\nName them in `rendered-a11y`'s pytest invocation. Adding them "
          "to NOT_IN_CI instead is a decision about CI coverage and needs to "
          "be taken deliberately, not to make this pass.")


def test_the_recorded_bound_has_not_gone_stale():
    """The ratchet's other half, and the only direction that can be checked
    without the operator: an entry that stopped needing to be there must go.

    A file that has since been added to the browser job, or that no longer
    drives one, leaves the register - so the count only falls. Without this
    the list would keep its 87 entries long after the gap had been closed, and
    read as a standing excuse.
    """
    covered = _covered()
    driving = set(_browser_driving())
    stale = []
    for rel in NOT_IN_CI:
        if not (ROOT / rel).is_file():
            stale.append(f"{rel}: gone from the tree")
        elif rel not in driving:
            stale.append(f"{rel}: no longer drives a browser")
        elif rel in covered:
            stale.append(f"{rel}: now runs in a browser job - remove it")
    assert not stale, (
        "the recorded bound names files that no longer belong in it:\n  "
        + "\n  ".join(stale)
        + "\n\nThis list is allowed to shrink and nothing else.")


