"""The three places that state which version this is, kept in agreement.

`__version__` sat at 0.1.0 through thirteen releases while CHANGELOG.md
climbed to 0.13.0. Nothing failed, because nothing compared them — so the CLI
banner, `/health` and the dashboard footer all named the first version of the
product, confidently and wrongly, which is worse than naming none at all: an
operator reporting a bug quotes it, and it sends the reader to the wrong code.

This does not check that the changelog is *complete* — no test can — only that
the version is not silently left behind, which is the half that is mechanical.
"""

from __future__ import annotations

import pathlib
import re

import clauditseo

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"


def _latest_release() -> str:
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        found = re.match(r"##\s+(\d+\.\d+\.\d+)\s", line)
        if found:
            return found.group(1)
    raise AssertionError("CHANGELOG.md has no '## <version> — <date>' heading")


def test_version_matches_the_top_changelog_entry() -> None:
    assert clauditseo.__version__ == _latest_release(), (
        f"__version__ is {clauditseo.__version__} but the newest CHANGELOG "
        f"entry is {_latest_release()}. Whichever is right, they cannot "
        "disagree: the version is what an operator quotes in a bug report."
    )


def test_the_packaged_version_matches_too() -> None:
    declared = re.search(r'^version\s*=\s*"([^"]+)"',
                         PYPROJECT.read_text(encoding="utf-8"), flags=re.M)
    assert declared, "pyproject.toml declares no version"
    assert declared.group(1) == clauditseo.__version__, (
        f"pyproject.toml says {declared.group(1)}, the package says "
        f"{clauditseo.__version__}. A wheel would install under the wrong one."
    )


def test_the_changelog_versions_descend() -> None:
    """The newest entry has to be first — the readers above assume it."""
    def parts(v: str) -> tuple[int, ...]:
        return tuple(int(n) for n in v.split("."))

    seen = re.findall(r"^##\s+(\d+\.\d+\.\d+)\s",
                      CHANGELOG.read_text(encoding="utf-8"), flags=re.M)
    assert len(seen) > 1
    ordered = sorted(seen, key=parts, reverse=True)
    assert seen == ordered, (
        f"CHANGELOG entries are out of order: {seen}. The newest release must "
        "be the first heading in the file."
    )
