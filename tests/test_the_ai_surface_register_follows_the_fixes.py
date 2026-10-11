"""The AI surface Register follows the fixes, closed (item 267, row 10).

The Register (3 conflicts, 12 declined items, 5 reads not available) stood
between the reachability card and the checks table, so the first fix card
sat about 3,500px down. Its twelve Declined items were the prompt's standing
non-goals read back, since the prompt has every run decline each one. The
Register now draws below Fixes in a closed `<details>`. It lists a declined
item only where it is not a standing non-goal, or where its `handled_at`
names a row or a conflict of this run; the rest are counted.

Run as the screen runs it: `declinedHere` bundled by the dashboard's esbuild
and executed by node, over twenty22's twelve stored items.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
ESBUILD = DASH / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")

#: Resolved once: a bare name is looked up through System32 first on Windows.
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                                reason="node or the dashboard's esbuild is not installed")

#: twenty22's stored declined items, 5 October (item, handled_at).
TWENTY22 = [
    ("Ranking or traffic impact of any fix in this brief", "ai-experience-unmeasured row"),
    ("CTR framing of title tags", "conflict recorded (title-framing); naming at ONP/title-entity-incomplete"),
    ("Which LLM cites which page, or techniques to 'get quoted verbatim'",
     "ai-experience-unmeasured row; answer-liftable reports structural properties only"),
    ("Harmonic centrality, PageRank, or host-graph connectivity", "not computed anywhere in this brief"),
    ("Term density / co-occurrence targets for enrichment candidates", "not emitted in entity-enrichment rows"),
    ("Page count as an authority signal", "not used in any row"),
    ("Mimicking Wikipedia's link graph",
     "Wikidata/Wikipedia admitted only as sameAs pins, and none proposed since sameas_sources is empty"),
    ("Anticipating a searcher's next question", "routed to Coverage · gap"),
    ("GBP or off-site publishing actions", "routed to the Local brief"),
    ("Schema markup authoring/validation beyond deltas",
     "referenced by id in AIS/entity-alignment and AIS/entity-unresolvable rows"),
    ("Rewriting page voice or drafting testimonials/reviews",
     "not attempted in any answer-liftable or enrichment passage"),
    ("Authoring llms-full.txt", "llms.txt section, readable block"),
]

PROBE = """
import { declinedHere, STANDING_NON_GOALS } from "%s";
const items = %s.map(([item, handled_at]) => ({ item, reason: "r", handled_at }));
const { kept, standing } = declinedHere(items);
const matched = items.filter((d) => STANDING_NON_GOALS.some((re) => re.test(d.item))).length;
const other = declinedHere([{ item: "Rewriting H1s for keyword match", reason: "r" }]);
console.log(JSON.stringify({ kept: kept.map((d) => d.item), standing, matched,
  patterns: STANDING_NON_GOALS.length, other: other.kept.length }));
"""


@needs_node
def test_only_what_points_at_this_run_is_listed(tmp_path):
    src = (DASH / "src" / "ai_surface").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % (src, json.dumps(TWENTY22)), encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    # Every twenty22 item is a standing non-goal ...
    assert out["matched"] == 12, out
    # ... and two of them point at a row or a conflict of this run.
    assert out["kept"] == ["CTR framing of title tags",
                           "Schema markup authoring/validation beyond deltas"], out
    assert out["standing"] == 10, out
    # An item the prompt does not decline is always listed.
    assert out["other"] == 1, out


def test_one_pattern_per_non_goal_in_the_prompt():
    prompt = (ROOT / "clauditseo" / "prompts" / "ai-surface.md").read_text(encoding="utf-8")
    block = prompt.split("Non-goals", 1)[1].split("# CONTEXT", 1)[0]
    bullets = [b for b in re.findall(r"^  - (.+)$", block, re.M)
               if not b.startswith("Anything a check above does not name")]
    src = (DASH / "src" / "ai_surface.tsx").read_text(encoding="utf-8")
    table = src.split("export const STANDING_NON_GOALS: RegExp[] = [", 1)[1].split("];", 1)[0]
    assert len(re.findall(r"^  /.+/i,$", table, re.M)) == len(bullets) == 12


def test_the_register_is_drawn_below_fixes_and_closed():
    page = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert "{!page && render.siteFoot && <render.siteFoot part={part} />}" in page
    # Not in the site picture above the checks any more.
    site_now = page.split("function AiSurfaceSiteNow", 1)[1].split("\n}\n", 1)[0]
    assert "AiRegister" not in site_now
    src = (DASH / "src" / "ai_surface.tsx").read_text(encoding="utf-8")
    assert "<details>" in src.split("export function AiRegister", 1)[1].split("\n}\n", 1)[0]


def test_the_folded_non_goals_can_be_opened():
    src = (DASH / "src" / "ai_surface.tsx").read_text(encoding="utf-8")
    assert '<details className="ai-standing">' in src
    assert "{folded.map((d, i) => (" in src
