"""Whether this checkout has a built dashboard to serve.

The rendered tests serve `dashboard/dist` and drive a browser against it. On
the machine that builds the bundle it is always there, so a test that needs it
and does not SAY it needs it looks identical to one that does - until someone
clones the repository and runs `pytest` before `npm run build`.

Measured on a fresh export of the tree (item 190, 2026-09-22):

    357 failures   no `dashboard/dist`
     40            with the bundle in place, nothing else changed

So **317 of those failures were "you have not built the dashboard yet"**, and
they were failures rather than skips: a Playwright timeout, or a
`FileNotFoundError` on `index.html`, neither of which says what to do. The
README's Development section lists `pytest` before `npm run build`, so that is
the order a reader tries.

108 files already carry the pattern this module replaces -
`skipif not (DIST / "index.html").is_file()`, which `test_a11y_rendered.py`
states. Nothing here changes what those do; what it adds is one reason string,
so every skip a stranger sees names the two commands rather than the file, and
one place to put the population under a guard.

**The skip is local only, and that is the whole design.** `.github/workflows/
ci.yml`'s `rendered-a11y` job fails on ANY skip, deliberately, so that this
cannot rot into a green no-op: in CI the bundle is built by the job itself, so
`HAVE_BUILD` is true and nothing here fires. A test that skips locally for a
missing prerequisite and runs in CI is gated; one that skips in both is gated
by nothing, which is the defect CQ-37 was about one level up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Where `npm run build` puts the bundle, and the file whose absence means it
#: has not run. `index.html` rather than the directory: a stale empty `dist/`
#: left by a failed build would satisfy a directory check and serve nothing.
DIST = ROOT / "dashboard" / "dist"
HAVE_BUILD = (DIST / "index.html").is_file()

REASON = ("no built dashboard at dashboard/dist: run `npm run build` in "
          "dashboard/ and `playwright install chromium`. These tests serve "
          "the bundle and drive a browser against it.")

#: For a clause that renders. The population is held by
#: `test_a_rendered_test_says_it_needs_a_build.py`, which derives it from the
#: tree rather than trusting this list to be kept.
needs_build = pytest.mark.skipif(not HAVE_BUILD, reason=REASON)


def skip_module() -> None:
    """Skip a whole module before it touches the bundle at import time.

    The same trap `private_register.skip_module` records: a marker is consulted
    after collection, so a module-level read of an absent path aborts the
    collection of every other file in the suite rather than failing one.
    """
    if not HAVE_BUILD:
        pytest.skip(REASON, allow_module_level=True)
