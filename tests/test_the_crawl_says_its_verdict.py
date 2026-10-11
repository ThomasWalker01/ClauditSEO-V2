"""The Crawl part says its verdict in the crawl's own figures (item 275,
row 12).

The only sentence about the crawl's shape was the model's prose, in the
model's counts ("43 reached" where the crawl counted 41). A verdict built
from the crawl-now payload stands over the tiles it summarises.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "crawl_now.tsx"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_the_sentence():
    src = SRC.read_text(encoding="utf-8")
    body = src.split("export function crawlVerdict", 1)[1].split("\n}\n", 1)[0]
    body = body.split("): string {", 1)[1]
    body = re.sub(r"\(n: number\)", "(n)", body)
    js = ("function crawlVerdict(now) {" + body + "\n}\n"
          + "console.log(JSON.stringify([crawlVerdict({reached: 41, published: 45, venn: "
          + "{published_not_reached: 4, reached_not_in_sitemap: 2, in_sitemap_and_reached: 39}}),"
          + "crawlVerdict({reached: 3, published: 3, venn: {published_not_reached: 0, "
          + "reached_not_in_sitemap: 0, in_sitemap_and_reached: 3}})]))")
    out = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert out == ["The crawl reached 41 of 45 published URLs; 4 sitemap URLs the crawl did not "
                   "reach and 2 reached pages in no sitemap.",
                   "The crawl reached 3 of 3 published URLs, and every one is in a sitemap."]
    assert '<p className="cn-verdict">{crawlVerdict(now)}</p>' in src
