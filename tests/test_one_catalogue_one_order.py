"""One catalogue, one order: every prompt file opens with a header naming
its part, scope and tier; the engine is the one reader of it; and the
drawer, Admin's brief defaults and the run-all confirm panel list the same
briefs in the sidebar's order. A part no brief writes to is a header in
the drawer reading "no brief yet"; triage writes to no part and is not a
row. A prompt whose header lacks `part` fails the catalogue's load with an
error naming the file and the field.

Brief v10 step AD (`_plans/site-screen-brief-v10-2026-09-04.md`).
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from clauditseo import briefs
from clauditseo.anatomy import CATEGORIES, TOOL_CATEGORIES
from clauditseo.analysts.expert import EXPERT_TOOLS
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "clauditseo" / "prompts"
SRC = ROOT / "dashboard" / "src"

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


def test_every_prompt_has_a_header_and_the_registry_reads_it():
    # `_CONTRACT.md` is the layout, not a brief (brief v11 step AH).
    files = sorted(p for p in PROMPTS.glob("*.md") if not p.name.startswith("_"))
    # 24 at step AD; title-desc at AG; headings at v11 AJ; at brief v15
    # step AQ one Images brief replaced `onpage-hygiene` and
    # `image-optimisation`, so the catalogue went one shorter; and at brief
    # v16 step AS the Structured data brief was added, taking it back to 26.
    # Brief v17 step AX added Content's four and, once they had run clean
    # on Birch, retired the four they replace - so the count is back where
    # it started, which is what "replaces" means. Brief v18 step AY added
    # the client plan, which is the 27th. Brief v19 step BB adds the URLs &
    # parameters brief (`urls`) and, once the live Birch and Acme runs were
    # clean (item 141), retired the legacy `url-hygiene` it replaced — one in,
    # one out, so the count held at 27. Brief v19 step BC then adds the Speed
    # brief (`speed`), the 28th; and once the live runs were clean — Birch
    # `ff313d06` and twenty22 `95ac5495`, the two the brief names, with
    # twenty22 standing in for Acme (operator, 2026-09-12) — the legacy
    # `render-blocking` it supersedes retired (item 141 step 3a). One in, one
    # out, so the count is back to 27. `perf-signals` is NOT retired with it:
    # two of its checks have no successor among the thirteen, which
    # `prf.TRACE_SUPERSEDES` records with the reason.
    # Item 165 retires `js-rendering` (superseded by crawl.md and
    # TEC/head-divergent), and nothing replaces it one-for-one: 26.
    # Item 145 step BH installs `ai-surface.md`: 27. `entity-graph` and
    # `llms-txt-builder` retired on the operator's word after its twenty22
    # runs (2026-09-16): 25. Item 196 retired `triage.md`, whose ranking is
    # computed with the audit now rather than bought: 24.
    assert len(files) == 24
    with_part = [p for p in files if re.search(r"^part: \S+", p.read_text(encoding="utf-8"), re.M)]
    assert len(with_part) == 24, sorted(p.name for p in set(files) - set(with_part))
    for b in briefs.catalogue():
        spec = EXPERT_TOOLS[b.id]
        assert (spec["scope"], spec["tier"], spec["part"]) == (b.scope, b.tier, b.part), b.id
        if b.part not in briefs.PARTLESS:
            assert TOOL_CATEGORIES[b.id] == (b.part,), (b.id, TOOL_CATEGORIES[b.id])
    # `triage` was asserted here beside `plan` as the second partless brief,
    # until item 196 retired it. `plan` below carries the same claim.
    # The plan's part names no sidebar section, so it maps to `workflow`
    # like the dispatcher rather than to a part of its own name (brief v18
    # step AY). Asserted rather than left implied: a `report` category
    # appearing in `CATEGORIES` would give the sidebar a section with no
    # checks, no fixes and nothing to count.
    assert briefs.by_id()["plan"].part == briefs.REPORT_PART
    assert briefs.REPORT_PART not in {c.key for c in CATEGORIES}
    # Item 238: placed under no part at all now, not under `workflow`.
    assert "plan" not in TOOL_CATEGORIES


def test_the_order_is_the_sidebars():
    index = {c.key: i for i, c in enumerate(CATEGORIES)}
    keys = [(index.get(b.part, len(index)), b.name.lower()) for b in briefs.catalogue()]
    assert keys == sorted(keys)
    assert [b.order for b in briefs.catalogue()] == list(range(24))


def test_a_header_without_a_part_fails_the_load_with_a_named_error(tmp_path):
    (tmp_path / "good.md").write_text(
        "---\nid: good\nname: Good\npart: content\nscope: site\ntier: standard\nchecks: []\n---\n\n# ROLE\n",
        encoding="utf-8")
    assert [b.id for b in briefs.load(tmp_path, CATEGORIES)] == ["good"]
    (tmp_path / "bad.md").write_text(
        "---\nid: bad\nname: Bad\nscope: site\ntier: standard\nchecks: []\n---\n\n# ROLE\n",
        encoding="utf-8")
    with pytest.raises(briefs.BriefHeaderError, match=r"bad\.md: header lacks `part`"):
        briefs.load(tmp_path, CATEGORIES)
    (tmp_path / "bad.md").write_text("# ROLE\nno header at all\n", encoding="utf-8")
    with pytest.raises(briefs.BriefHeaderError, match=r"bad\.md: no front matter"):
        briefs.load(tmp_path, CATEGORIES)
    (tmp_path / "bad.md").write_text(
        "---\nid: bad\nname: Bad\npart: nowhere\nscope: site\ntier: standard\nchecks: []\n---\n",
        encoding="utf-8")
    with pytest.raises(briefs.BriefHeaderError, match=r"bad\.md: part 'nowhere' is not a sidebar part"):
        briefs.load(tmp_path, CATEGORIES)


def test_the_dashboard_keeps_no_part_mapping():
    """The drawer groups by the `part` each row carries and the parts the
    payload lists; it no longer walks the anatomy's categories for tools."""
    src = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    assert "x.part" in src and "lanes?.parts" in src
    rows_fn = src.split("export function catalogueRows")[1].split("export function")[0]
    assert "categories" not in rows_fn and ".tools" not in rows_fn, rows_fn
    for p in SRC.glob("*.ts*"):
        text = p.read_text(encoding="utf-8")
        for b in briefs.catalogue():
            for c in CATEGORIES:
                assert not re.search(rf"[\"']{re.escape(b.id)}[\"']\s*:\s*[\"']{re.escape(c.key)}[\"']", text), (
                    f"{p.name} maps {b.id} to {c.key}")


_JS = """() => ({
  // The header's words without its re-run glyph (brief v24 step BO).
  groups: [...document.querySelectorAll('.catalogue-table tr.crow-part th')].map((th) => { const c = th.cloneNode(true); c.querySelectorAll('.anat-rerun, .anat-rank, .cat-dot, .sb-model').forEach((e) => e.remove()); return c.textContent.trim(); }),
  rows: [...document.querySelectorAll('.catalogue-table tr.crow code')].map((c) => c.textContent.trim()),
  parts: [...document.querySelectorAll('.catalogue-table tr.crow td:first-child')].map((td) => td.textContent.trim()),
})"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_drawer_admin_and_the_confirm_panel_agree(browser, served):
    base, ids = served
    admin = httpx.get(f"{base}/api/models/briefs", timeout=30).json()["briefs"]
    # The drawer is a list of sidebar sections, so it holds the briefs that
    # write to one. Admin holds every brief, because every brief has a
    # default model to set - the two partless ones, `triage` and `plan`,
    # last (brief v18 step AY).
    admin_order = [b["tool"] for b in admin if b["part"] not in briefs.PARTLESS]
    expected = [b.id for b in briefs.catalogue() if b.part not in briefs.PARTLESS]
    assert admin_order == expected
    # `plan` and `triage` were the two partless briefs, listed last (brief
    # v18 step AY). Item 196 retired `triage`, so `plan` is the only one left
    # and the tail is one entry.
    assert [b["tool"] for b in admin][-1:] == ["plan"], [b["tool"] for b in admin]
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        # With no part open the shop is Analyses' own body (brief v24 step BO).
        pg.wait_for_selector(".catalogue-shop .catalogue-table", timeout=30_000)
        pg.wait_for_selector(".catalogue-table tr.crow", timeout=30_000)
        drawer = pg.evaluate(_JS)
        pg.click(".run-all")
        pg.wait_for_selector(".batch-confirm tbody tr", timeout=15_000)
        confirm = pg.evaluate("() => [...document.querySelectorAll('.batch-confirm tbody tr code')].map((c) => c.textContent.trim())")
    finally:
        pg.close()
    # The drawer holds exactly the briefs that write to a part - the same set
    # Admin holds, less the partless ones - but NOT in the same order, and the
    # difference is brief v24 step BN rather than a screen inventing one: the
    # shop sorts by rank, parts the ranking placed first. Since item 196 the
    # ranking is computed with the audit, so it always exists and the shop
    # always sorts by it; this clause used to pass only because the fixture
    # had never bought one.
    assert sorted(drawer["rows"]) == sorted(expected), drawer["rows"]
    assert "triage" not in drawer["rows"]
    assert "plan" not in drawer["rows"]

    # And the order is the rank's, read from the same API the screen reads
    # rather than restated here. Parts the ranking placed come first, in rank
    # order; the rest keep the order they had.
    lanes = httpx.get(f"{base}/api/runs/{ids['run']}/analyses", timeout=30).json()
    placed, seen = [], set()
    for row in (lanes.get("triage") or {}).get("ranked", []):
        part = row.get("category")
        if part and part not in seen:
            seen.add(part)
            placed.append(part)
    if placed:
        part_of = {b.id: b.part for b in briefs.catalogue()}
        rank_of = {p: i for i, p in enumerate(placed)}
        got = [part_of.get(t) for t in drawer["rows"]]
        ranks = [rank_of[p] for p in got if p in rank_of]
        assert ranks == sorted(ranks), (
            "the shop's rows are not in rank order, so the drawer has stopped "
            f"reading the ranking (brief v24 step BN): {drawer['rows']}")
    # Every part of the sidebar, and no other - the set, not the order. The
    # order is the rank's since brief v24 step BN, and always the rank's since
    # item 196 made the ranking arrive with the audit; a group that appeared
    # or vanished would be the catalogue disagreeing with the registry, which
    # is what this is for.
    labels = [c.label for c in CATEGORIES if c.group != "workflow"]
    assert sorted(g.split(" · ")[0] for g in drawer["groups"]) == sorted(labels), \
        drawer["groups"]
    # "no analysis covers this part", since audit F14: this group is empty
    # because no brief writes to the part, which is not the unread state - and
    # was briefly drawn as it, with the registered `not read`, before that
    # distinction was noticed here.
    empty = [g for g in drawer["groups"] if g.endswith("no analysis covers this part")]
    filed = {b.part for b in briefs.catalogue()}
    assert sorted(g.split(" · ")[0] for g in empty) == sorted(
        c.label for c in CATEGORIES if c.group != "workflow" and c.key not in filed), empty
    # The confirm panel lists what run-all would tick, in the same order.
    assert confirm == [t for t in expected if t in confirm], confirm
    assert confirm, "run-all's confirm panel is empty"
