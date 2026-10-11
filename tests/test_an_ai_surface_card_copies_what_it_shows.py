"""An AI surface card copies the text it shows (item 267, row 5).

The prompt's examples taught the model to write a pointer as the replacement
- "see candidates — each is the sentence as it should read, placed", "see
passage — placed as stated" - and `copy change` copied that pointer. The
examples now write the text itself, and the copy reads the payload the card
draws: the passage, the candidates' sentences (not one still waiting on the
client), the JSON-LD change, and only then the replacement.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
ESBUILD = DASH / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")

#: Resolved once: a bare name is looked up through System32 first on Windows.
NODE = shutil.which("node")

PROBE = """
import { aiSurfaceCopy } from "%s";
console.log(JSON.stringify({
  passage: aiSurfaceCopy("see passage", { payload: { passage: " Birch runs conferences. " } }),
  candidates: aiSurfaceCopy("see candidates", { payload: { candidates: [
    { entity: "Melbourne", source: "record", place: "p1", sentence: "Birch runs events in Melbourne." },
    { entity: "Size", source: "record", place: "p1", sentence: "[client to supply] delegates." },
    { entity: "Sydney", source: "record", place: "p2", sentence: "And in Sydney." }] } }),
  delta: aiSurfaceCopy("x", { payload: { jsonld_delta: { "@type": "Event" } } }),
  plain: aiSurfaceCopy("User-agent: GPTBot\\nAllow: /", {}),
}));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_the_copy_is_the_text_the_card_shows(tmp_path):
    src = (DASH / "src" / "ai_surface").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    assert json.loads(out.stdout) == {
        "passage": "Birch runs conferences.",
        "candidates": "Birch runs events in Melbourne.\nAnd in Sydney.",
        "delta": '{\n  "@type": "Event"\n}',
        "plain": "User-agent: GPTBot\nAllow: /"}, out.stdout


def test_the_prompt_writes_the_text_not_a_pointer_at_it():
    text = (ROOT / "clauditseo" / "prompts" / "ai-surface.md").read_text(encoding="utf-8")
    assert '"replacement": "see candidates' not in text
    assert '"replacement": "see passage' not in text
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert 'copyLabel: "copy change", copyText: aiSurfaceCopy' in src
