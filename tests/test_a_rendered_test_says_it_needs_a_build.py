"""A test that needs the built dashboard says so, and the population is
derived rather than kept by hand.

Item 190. A rendered test without that gate does not fail honestly when the
bundle is absent: it fails with a Playwright timeout or a `FileNotFoundError`,
neither of which tells the reader to run `npm run build`. Measured on a fresh
export of the tree, 317 of 357 failures were exactly that, and the README lists
`pytest` before the build, so it is the order a reader tries.

**Why a guard and not just the markers.** The markers were applied from a
measurement - every test that failed with `dashboard/dist` moved aside, 64
across 15 files. A measurement is a photograph. The next rendered test added
will not be in it, and will fail the same confusing way, which is how this
whole class of thing comes back. So the population is derived from the tree
here and compared against what is marked.

**Why the derivation needs exemptions, stated rather than hidden.** The signals
for "needs a browser" are textual - it reads `DIST`, imports playwright, or
requests a fixture that starts a server and a browser. Those signals
over-match: a file can name `DIST` while testing something about bundle tests,
and a file can request `served` for a clause that only reads a payload off the
wire. The static derivation found 24 files where measurement found 15, and this
guard's own first run turned up six more it matched and should not have. The
difference is not noise to be tuned away: four of those six are not rendered
at all - three wire tests and a meta-test whose `sync_playwright(` is inside a
regex literal - and the other two were already gated in forms the pattern did
not recognise. The first are named in `NOT_RENDERED` with the reason, in the
shape `test_dashboard_a11y.py`'s `PAINTED_BY_NOTHING` uses; the second widened
what counts as saying so, because the claim is "a reader is told to build" and
not "a particular marker is present".

**What this does not do.** It does not assert that a marked test SKIPS. In CI
the bundle is always built, so nothing skips there - `.github/workflows/ci.yml`
fails the browser job on any skip precisely so that a gate cannot become a
green no-op. The claim here is narrower and is the one that rots: every test
that would break without a build says which build.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

#: Textual signals that a test file drives a browser or serves the bundle.
#: `browser_page` and `served` are the indirect cases: a grep for playwright
#: alone misses a file that only ever names a fixture.
NEEDS = re.compile(
    r"\bDIST\b|sync_playwright|import playwright|from playwright|"
    r"\bbrowser_page\b|def test_[a-z_]*\([^)]*\bserved\b")

#: What counts as saying so. Four forms, because the tree already had three
#: before `needs_build` existed and all three are honest:
#:
#:   - the `skipif` on the bundle's own `index.html`, which 108 files carry;
#:   - `needs_build`, the same condition with one reason string behind it;
#:   - `DIST.exists()`, which `test_verify_page_cap.py` uses;
#:   - an inline `pytest.skip` whose reason names the build, which
#:     `test_the_strip_panel_holds_its_tallest_state.py` raises from the helper
#:     that reads the built CSS - the gate is inside the function that needs
#:     the bundle, which is if anything closer to the thing being gated.
#:
#: The claim is "a reader is told to build", not "a particular marker is
#: present". Recognising only the marker would have failed two files that
#: already do the right thing, and the fix would have been to add a second
#: gate beside a working one.
SAYS = re.compile(
    r'DIST\s*/\s*"index\.html"'
    r'|needs_build'
    r'|DIST\.exists\(\)'
    r'|skip\((?:reason=)?"[^"]*(?:dashboard not built|npm run build)')

#: Files the signals match that do not need a build, each with why. Measured,
#: not assumed: these are the files that PASSED with `dashboard/dist` moved
#: aside, while the signals said they would not.
NOT_RENDERED = {
    "test_a_section_reads_its_reference_crawl.py":
        "item 239 step 2: it serves the app for its JSON routes only and "
        "drives no browser; nothing it asserts is drawn by the bundle.",
    "test_prove_fail_refuses_bundle_tests.py":
        "its subject IS bundle tests - it asserts that `scripts/prove_fail.py` "
        "refuses a file which loads the bundle. It names `DIST` as data. A "
        "gate here would make the guard need the thing it is about.",
    "test_real_data_scale.py":
        "already gated, and by a stronger thing than a marker: every clause "
        "takes the `served` fixture from `test_a11y_rendered.py`, whose "
        "module-level skip covers the whole file. It matches the signal "
        "because it names the fixture.",
    "test_targets_meet_the_24px_floor.py":
        "gated the same way through the same fixture.",
    "test_four_findings_at_ten_reports_are_recorded_not_invisible.py":
        "a meta-test about browser-driving code: `sync_playwright(` appears "
        "inside a regex LITERAL, its `DRIVES` pattern. Its own comment already "
        "says \"why the population excludes this file\" - and the reason it "
        "gives is the same one this guard rests on, that a matcher weaker than "
        "the claim closes a finding it did not check.",
    # The three below take the `served` fixture, which starts the API server.
    # That is not the bundle: they drive httpx against routes and never load a
    # page, so they pass with `dashboard/dist` moved aside - measured, not
    # assumed. They match the signal because the signal looks for the fixture
    # name, which is the price of catching the indirect cases at all.
    "test_a_held_client_report_never_pays_for_its_plan.py":
        "a wire test: `served` for the API, httpx for the assertions, no page "
        "ever loaded.",
    "test_one_site_reading_predicate.py":
        "a wire test on the same shape - the predicate is read off the "
        "payload and the runs table.",
    "test_the_images_brief_and_its_checks.py":
        "a wire test on the same shape - the site record's image fields and "
        "its provenance refusal.",
}


def _test_files() -> list[Path]:
    files = sorted(p for p in TESTS.glob("test_*.py"))
    assert len(files) > 100, f"only {len(files)} test files found; the glob broke"
    return files


def _code(text: str) -> str:
    """Source with docstrings and comments removed.

    A file that DISCUSSES the bundle is not a file that loads it, and that
    distinction is the whole value of this guard - several of these docstrings
    quote `DIST` while explaining why the file does not need it.
    """
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("#"))


def test_the_derivation_finds_the_rendered_tests_at_all():
    """DISCIPLINE rule 5: an empty derivation would make the assertion below
    pass for free, and would look identical to a clean tree."""
    matched = [p.name for p in _test_files() if NEEDS.search(_code(
        p.read_text(encoding="utf-8")))]
    assert len(matched) > 50, (
        f"the browser-needing derivation matched {len(matched)} files - the "
        "signals have probably been reworded, and this file is now checking "
        "almost nothing")


def test_every_rendered_test_says_it_needs_a_build():
    """The claim. A file that drives a browser carries a gate naming the
    build, or is exempted above with its reason."""
    quiet = []
    for path in _test_files():
        if path.name in NOT_RENDERED:
            continue
        code = _code(path.read_text(encoding="utf-8"))
        if NEEDS.search(code) and not SAYS.search(code):
            quiet.append(path.name)
    assert not quiet, (
        "these drive a browser or serve `dashboard/dist` and carry no gate "
        "saying so, so they fail with a timeout rather than telling the "
        "reader to run `npm run build`:\n  " + "\n  ".join(quiet)
        + "\n\nAdd `needs_build` from `tests/needs_build.py`, or name the file "
          "in NOT_RENDERED with the reason it does not need one.")


def test_every_exemption_is_still_a_file_that_matches_the_signal():
    """An exemption for a file that no longer exists, or no longer matches, is
    an exception outliving its reason - the shape CQ-145 names. It would sit
    here forever excusing nothing."""
    stale = []
    for name, why in NOT_RENDERED.items():
        path = TESTS / name
        if not path.is_file():
            stale.append(f"{name}: gone from the tree")
            continue
        if not NEEDS.search(_code(path.read_text(encoding="utf-8"))):
            stale.append(f"{name}: no longer matches the signal")
        assert why.strip(), f"{name} is exempted with no reason"
    assert not stale, "stale exemptions in NOT_RENDERED:\n  " + "\n  ".join(stale)
