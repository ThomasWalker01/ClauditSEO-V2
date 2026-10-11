"""A clean line certifies only what was read (item 272, row 4).

On twenty22's Images the analysis line named `img-link-alt-not-destination`
and `img-sitemap-missing` as returning no row, though the analysis returned
rows for both, dropped because they named page `*`. The free line certified
`img-lcp-lazy` over 45 pages where no largest paint had been measured, so the
sweep had judged the first image in the main region instead. Each is now
said as what it is.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_payload_says_whether_a_largest_paint_was_seen():
    src = inspect.getsource(runs.image_budget_payload)
    assert 'lcp_found = lcp_found or bool(record.get("lcp_candidate"))' in src
    assert '"lcp_found": lcp_found,' in src


def test_dropped_and_document_order_checks_have_their_own_lines():
    page = SRC.read_text(encoding="utf-8")
    assert "spotlessAll.filter((r) => droppedIds.has(r.checkId))" in page
    assert "the dropped rows below say why" in " ".join(page.split()).lower()
    assert "clean on document order: no largest paint was measured" in " ".join(page.split())
    # Neither is left in the certifying line.
    # Since screen audits round 3 the line also sets aside a partly measured
    # check (Security AC-01) and, in page mode, a site-level one (Speed AC-01).
    assert ("&& !byOrder(r) && !spotlessDropped.includes(r) && !partly(r) "
            "&& !siteLevel(r));") in page
