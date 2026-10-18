"""A verdict on a page inside a sweep group does not close it (channel ruling
20261017-1820, screen audits round 4 Content AC-02).

`fixesOf` keyed a sweep row on its first page, so twenty22's 40-page
`title-overlap` group became a card keyed on `/about/`, and the two
cannibalisation verdicts on `/website-hosting/` and `/seo-category/seo-on-page/`
- both inside that group - never merged with it and read "Analysis closes
this" beside it. A verdict now counts with the group wherever its page stands
in the group's pages.

Run as the screen runs it: bundled by the dashboard's esbuild, executed by
node.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from tests.test_one_template_rule import DASH, ESBUILD, NODE

PROBE = """
import { fixesOf, closedByAnalysis } from "%s";
const U = (p) => `https://gate-six.test${p}`;
const base = { dimension: "CNT", check_id: "title-overlap", severity: "medium",
               summary: "s", recommendation: null, affected_total: null, state: "open",
               names_a_page: true };
const states = [
  { ...base, fingerprint: "group", source: "deterministic",
    affected_urls: [U("/about/"), U("/hosting/"), U("/b/")], affected_total: 3 },
  { ...base, fingerprint: "v-in", source: "model-judgement", brief: "content-cannibalisation",
    brief_status: "PASS-OVERRIDE", affected_urls: [U("/hosting/")] },
  { ...base, fingerprint: "v-out", source: "model-judgement", brief: "content-cannibalisation",
    brief_status: "PASS-OVERRIDE", affected_urls: [U("/")] },
];
const part = { key: "content", brief_checks: ["CNT/title-overlap"], check_prefixes: [],
               filed_checks: [], findings: [] };
const fixes = fixesOf(part, states, "");
const byPage = Object.fromEntries(fixes.map((f) => [new URL(f.page).pathname,
  { closed: closedByAnalysis(f), group: f.inSweepGroup ?? null }]));
console.log(JSON.stringify(byPage));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_a_verdict_in_the_group_counts_and_one_outside_it_closes(tmp_path):
    (tmp_path / "probe.ts").write_text(PROBE % (DASH / "src" / "part_page").as_posix(),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    got = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    # Inside the group (not its first page): not closed, and says the group.
    assert got["/hosting/"] == {"closed": False, "group": 3}, got
    # Outside every group: the verdict agrees with the sweep and closes.
    assert got["/"] == {"closed": True, "group": None}, got


def test_the_not_in_build_checks_are_named_once_in_the_module():
    """Channel ruling 20261017-1821 (Security IP-04): three engine holds no
    input or model call releases are drawn apart; `reputation` stays a hold
    because a reputation source on the site record releases it."""
    from clauditseo.modules import sec
    assert sec.NOT_IN_BUILD == {"open-ports", "origin-exposed", "admin-hostnames"}
    assert "reputation" in sec.HELD and "reputation" not in sec.NOT_IN_BUILD
    assert sec.NOT_IN_BUILD <= set(sec.HELD)
