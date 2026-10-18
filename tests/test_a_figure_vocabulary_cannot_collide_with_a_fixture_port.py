"""A test figure may not be a number the fixture server could be listening on.

KI-51's sixteenth instance, and the first in that row's history with no
Playwright, no selector and no timeout. CI run `33437584252` failed
`python (windows-latest)` attempt 1 on

    tests/test_figure_cap_declares_what_it_withheld.py::test_a_recalled_brief_states_the_total_it_was_drawn_from
    AssertionError: the flagged total is not what the brief flagged:
    expected 55 (stored 40 + withheld 15), got 54

and attempt 2, on the same unchanged tree, passed. Fifteen rounds read that
row as runner capacity. This one is not: it is a **collision**, and it was
reproduced at round 127 in two lines rather than inferred.

`ungrounded_figure_details` calls a figure *grounded* when its digits appear
anywhere in the crawl evidence, and the evidence carries the fixture site's
own URL — `http://127.0.0.1:<port>/`. `FixtureSite` binds
`ThreadingHTTPServer(("127.0.0.1", 0), ...)` (`tests/conftest.py:105`), so the
OS hands it an **ephemeral** port. The stub brief in
`test_figure_cap_declares_what_it_withheld` writes figures `50001`-`50055`.
Those two ranges overlap. When the OS happens to hand out a port in the span,
that one figure reads as grounded, `withheld` falls from 15 to 14, and
`figures_flagged` reports 54 instead of 55 — the exact arithmetic CI printed.

Measured directly, holding everything but the port constant:

    port 61234 (outside span): declared=40 withheld=15 flagged=55
    port 50017 (inside span):  declared=40 withheld=14 flagged=54

So the guard is on the *vocabulary*, not on the extractor: a test that grounds
figures against a fixture crawl may not spend a number the fixture's own port
can take.

**The band is the ephemeral range, not every legal port.** `port 0` cannot
return 80 or 4444, so banning those would fail on year literals (`2024`) and
on the `file.py:2127` line citations these modules' docstrings are full of,
and a guard that cries at a docstring is a guard someone deletes. The band is
the union of the two platforms CI runs: Linux 32768-60999
(`net.ipv4.ip_local_port_range`) and Windows 49152-65535 (`netsh int ipv4 show
dynamicport tcp`), so 32768-65535.

The population is derived from the tree, per the loop's guard-population
invariant, and both halves of it are asserted non-empty below: a regex that
stopped matching would otherwise pass by finding nothing.
"""

from __future__ import annotations

import ast
import pathlib
import re

# The union of the ephemeral ranges of the two platforms CI runs. A port
# obtained by binding to 0 is drawn from one of these; nothing outside them
# can appear in a fixture URL, so nothing outside them is a collision risk.
EPHEMERAL_LO = 32768
EPHEMERAL_HI = 65535

TESTS = pathlib.Path(__file__).resolve().parent


def _grounds_figures_against_a_fixture_crawl(src: str) -> bool:
    """Both halves, because either alone is a different kind of module.

    A module that stands up a `FixtureSite` but never reaches the figure
    extractor cannot collide — nothing of its prose is compared against the
    evidence. A module that exercises the extractor against a hand-written
    evidence string has no port in its evidence at all.
    """
    crawls = "make_site" in src or "site_fixture" in src
    figures = ("FIGURES_TO_VERIFY_CAP" in src
               or "ungrounded_figure" in src
               or "figures_to_verify" in src)
    return crawls and figures


def _numbers_written_into_prose(src: str) -> set[int]:
    """Every integer this module puts into text a figure extractor would read.

    Figures live in prose, so the scan is over string and f-string literals
    rather than over every integer in the file: a token count or a byte length
    passed as a `dict` value never reaches the extractor. Inside an f-string
    both halves count — the literal text and the integer constants of its
    interpolated expressions — because `f"Metric {50000 + n}"` spends 50000 as
    surely as `"Metric 50001"` does.
    """
    found: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.JoinedStr):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, int):
                    found.add(inner.value)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.update(int(m) for m in re.findall(r"\b\d{4,5}\b", node.value))
    return found


def test_no_grounded_figure_vocabulary_can_be_handed_out_as_a_port():
    modules = []
    for path in sorted(TESTS.glob("test_*.py")):
        # This module itself, excluded by name and for a stated reason rather
        # than by weakening the predicate. It matches on both halves because
        # it *names* them, and its docstring quotes the very numbers it
        # forbids — 50017 and 61234 are the measurement that identified the
        # collision. Holding the vocabulary under test is the same standing
        # `tests/test_check_anchors.py` has for holding addresses that do not
        # resolve: the corpus is the subject, not a breach of it. Run against
        # the unfixed tree at round 127 the guard named four modules, this one
        # among them, which is how the exclusion came to be written.
        if path.name == pathlib.Path(__file__).name:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if _grounds_figures_against_a_fixture_crawl(src):
            modules.append((path, src))

    # Population, half one: the modules. Derived from the tree above, and
    # asserted here so a predicate that stopped matching cannot pass by
    # searching nothing.
    assert modules, (
        "no test module was found that both stands up a fixture site and "
        "reaches the figure extractor; the predicate has stopped matching, "
        "and an empty population would let this guard pass on anything")

    scanned = 0
    collisions: dict[str, list[int]] = {}
    for path, src in modules:
        numbers = _numbers_written_into_prose(src)
        scanned += len(numbers)
        bad = sorted(n for n in numbers if EPHEMERAL_LO <= n <= EPHEMERAL_HI)
        if bad:
            collisions[path.name] = bad

    # Population, half two: the numbers. A module set that parses to no prose
    # numbers at all is the same vacuity wearing a different hat.
    assert scanned, (
        f"{len(modules)} modules matched but not one number was extracted "
        "from their prose; the literal scan has stopped matching")

    assert not collisions, (
        "a test grounds figures against a fixture crawl using a number the "
        f"fixture's own ephemeral port can take ({EPHEMERAL_LO}-"
        f"{EPHEMERAL_HI}), so the figure reads as grounded whenever the OS "
        "hands out that port and the withheld count silently drops by one — "
        f"KI-51's sixteenth instance: {collisions}")
