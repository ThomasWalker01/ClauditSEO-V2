"""An analysis card the automatic checks corroborated on the other end says
so (item 271, row 3).

The automatic checks file `broken-internal` on the broken TARGET
(`/cdn-cgi/l/email-protection` returns 404, linked from 2 places) and the
analysis files it on the SOURCE page that carries the link (`/contact-us/`,
`/privacy-policy/`). `fixesOf` keys a card by (check, page), so the two never
met, and the analysis cards read "candidate" over a 404 the free checks had
measured in the same run.

Run as the screen runs it: `fixesOf` bundled by the dashboard's esbuild and
executed by node.
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
import { fixesOf } from "%s";
const row = (over) => ({ dimension: "LNK", check_id: "broken-internal", severity: "high",
  state: "open", fingerprint: over.fp, summary: "", affected_urls: [], source: "deterministic",
  ...over });
const states = [
  row({ fp: "s1", affected_urls: ["https://t.co/cdn-cgi/l/email-protection"],
        summary: "/cdn-cgi/l/email-protection is linked from 2 places on the site and returns 404." }),
  row({ fp: "m1", source: "model-judgement", state: "candidate",
        affected_urls: ["https://t.co/contact-us/"],
        summary: "link to /cdn-cgi/l/email-protection anchor 'email' returns 404" }),
  row({ fp: "m2", source: "model-judgement", state: "candidate",
        affected_urls: ["https://t.co/seo/local-seo/"],
        summary: "body link to /seo/general-seo-tips/ not fetched" }),
];
const part = { key: "links", brief_checks: ["LNK/broken-internal"] };
console.log(JSON.stringify(fixesOf(part, states, "").map((f) => ({
  page: f.page, sources: f.sources, by: f.corroboratedBy ?? null }))));
"""


def test_a_source_card_naming_a_raised_target_is_corroborated(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    by = {c["page"]: c for c in json.loads(out.stdout)}
    assert by["https://t.co/contact-us/"]["by"] == ["/cdn-cgi/l/email-protection"], by
    # A card naming a target the automatic checks did not raise is left alone,
    # and the automatic checks' own card is not marked.
    assert by["https://t.co/seo/local-seo/"]["by"] is None, by
    assert by["https://t.co/cdn-cgi/l/email-protection"]["by"] is None, by
    src_text = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert "the automatic checks raised the same target: " in src_text
