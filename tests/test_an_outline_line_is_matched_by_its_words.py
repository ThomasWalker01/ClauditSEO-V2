"""A heading card matches a line by its words, not its spelling (item 268,
row 2).

`parseOutline` kept the model's tokens in the heading text and the diff matched
on exact text after case and spacing. So "Lets find the right steps together"
was struck and "Let's find the right steps together [proposed]" added; a
curly apostrophe did the same; every FAQ question carrying an `[answer stub:
...]` read as removed and proposed; and the model's own `[proposed]` sat
beside the card's "[proposed]" chip. `copy outline` copied all of it.

Run as the screen runs it: `part_page.tsx` bundled by the dashboard's own
esbuild and executed by node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1] / "dashboard"
ESBUILD = DASH / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")

#: Resolved once: a bare name is looked up through System32 first on Windows.
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                                reason="node or the dashboard's esbuild is not installed")

PROBE = """
import { parseOutline, outlineKey, outlineCopy } from "%s";
console.log(JSON.stringify({
  lines: parseOutline("h2 Let\\u2019s find the right steps together / "
    + "h3 How long does it take? [answer stub: About six weeks.] / h3 Our team [proposed]"),
  lets: outlineKey("Lets find the right steps together")
        === outlineKey("Let\\u2019s find the right steps together"),
  question: outlineKey("How long does it take?") === outlineKey("how long does it take"),
  other: outlineKey("Our team") === outlineKey("Our people"),
  copy: outlineCopy("h2 A [proposed] / h3 B? [answer stub: x]"),
}));
"""


@pytest.fixture(scope="module")
def got(tmp_path_factory):
    d = tmp_path_factory.mktemp("outline")
    src = (DASH / "src" / "part_page").as_posix()
    (d / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(d / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={d / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(d / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    return json.loads(out.stdout)


def test_the_models_tokens_are_fields_not_heading_text(got):
    lines = got["lines"]
    assert [l["text"] for l in lines] == ["Let’s find the right steps together",
                                         "How long does it take?", "Our team"], lines
    assert lines[1]["next"] == "About six weeks.", lines[1]
    assert [l.get("proposed") for l in lines] == [False, False, True], lines


def test_two_spellings_of_one_heading_share_a_key(got):
    assert got["lets"] and got["question"], got
    assert not got["other"], got


def test_copy_outline_copies_the_parsed_lines(got):
    # A question's stub is pasted under it (screen audits round 4, Headings UX-01).
    assert got["copy"] == "H2 A\nH3 B?\n  answer: x", got["copy"]


def test_the_marks_say_what_changed():
    """Screen audits round 3 (headings AC-03): a letter-case change read
    "reworded" (263 marks on one page), `[proposed]` was drawn on any
    unmatched line whatever the model flagged, and a typo fix matched a later
    duplicate because the map kept the last line per key."""
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8").replace("\r\n", "\n")
    body = src.split("const change = (line: Line, j: number): string | null => {", 1)[1].split("\n  };", 1)[0]
    assert 'if (!was) return line.proposed ? "[proposed]" : "reworded";' in body
    assert "if (was.line.level === line.level) return null;" in body
    assert "if (!byText.has(norm(l.text))) byText.set(" in src
