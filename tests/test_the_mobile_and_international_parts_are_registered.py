"""The Mobile and International parts at schema mobile/2 and intl/2 (items
147 and 148, brief v20).

Both briefs are installed, both check sets are registered, and Mobile's six
parse-only checks are emitted by the sweep. The three render-dependent Mobile
checks (147's step 8) and both parts' part-page work are NOT in this round.

**Two decisions this file pins, because each brief asked for one and they came
out opposite ways:**

- **147: the ids take the `TEC` prefix.** `MOB/` appeared in no source file
  anywhere, `anatomy` already files the `mobile` category under TEC, and
  `tec.py` is where the viewport checks live. A MOB dimension would have bought
  a separate audit target nobody asked for.
- **148: `INT` is registered label-only.** Opposite call, for a reason the item
  states: `intl` is in `ANALYSIS_ONLY`, no sweep covers it, and putting `INT`
  into `DIMENSION_CATEGORIES` would claim one — which
  `test_analysis_only_categories_really_have_no_sweep` would then fail. One part
  has a dimension behind it and the other does not.

**And one premise in both briefs that measurement contradicted.** Both say that
the moment `checks:` goes from `[]` to a real list, `_uncovered` starts
reporting every declared check the sweep never emitted — 148 calls it
"the one thing here that is not optional" and makes it a blocking step.

It does not. `_uncovered` reports *sweep rows the brief's answer does not
cover*: it queries `findings WHERE source='deterministic'`, so with no sweep
there is nothing to be uncovered by. Driven directly below with eleven declared
ids and no findings, it returns zero. The blocking step was not built because it
was not needed, and this clause is the record of why.
"""

from __future__ import annotations

import pytest

from clauditseo import anatomy, briefs
from clauditseo.checks import check_cost
from clauditseo.modules import tec
from clauditseo.modules.tec import _viewport_checks

#: The six a parse of the crawl's own `viewport_tags` can answer.
PARSED = ("viewport-missing", "viewport-width", "viewport-scale",
          "zoom-suppressed", "viewport-duplicate", "viewport-legacy")

#: The six the TRACE answers (brief 160 steps 1-3): three from
#: `mobile_render`, taken in perf's own 412 x 823 Pixel 5 pass, and three from
#: diffing `head_fetched` against `head_rendered`.
TRACED = ("horizontal-overflow", "tap-target", "viewport-units",
          "viewport-injected", "viewport-divergent", "viewport-late")

#: Twelve swept, which is item 147's own end state -- reached by each id
#: joining `DEFAULT_SEVERITY` on the run where a sweep could actually raise it,
#: never before.
SWEPT = PARSED + TRACED

#: The three that are JUDGEMENT, so no capture moves them: which authoring
#: location owns the tag, whether the layout survives the soft keyboard, and
#: whether the notch inset matches the design's intent.
BRIEF_ONLY = ("viewport-source", "viewport-keyboard", "safe-area")

INTL = ("hreflang-missing", "hreflang-reciprocity", "hreflang-self",
        "hreflang-x-default", "hreflang-code", "hreflang-target",
        "hreflang-method-mixed", "hreflang-sitemap-conflict",
        "locale-redirect", "architecture", "consolidation")


class _Facts:
    """Just enough of `PageFacts` for the viewport checks, which read two
    fields. A real crawl is not needed: `viewport_tags` is already captured
    verbatim, which is the whole reason these six need no new capture."""

    path = "/x"

    def __init__(self, tags: list[str]):
        self.viewport_tags = tags


def _ids(tags: list[str]) -> list[str]:
    return [f.check_id for f in _viewport_checks("TEC", _Facts(tags),
                                                 "https://x.test/x")]


# --- 147, the six the sweep now raises --------------------------------------


def _rendered(mobile_render=None, fetched=None, rendered=None):
    """One trace, with only the fields the six trace-fed checks read."""
    tr = {"traced": True, "device_profile": "d"}
    if mobile_render is not None:
        tr["mobile_render"] = mobile_render
    if fetched is not None:
        tr["head_fetched"] = fetched
    if rendered is not None:
        tr["head_rendered"] = rendered
    return tr


def _traced_ids(trace, tags=("width=device-width, initial-scale=1",)):
    from clauditseo.modules.tec import _mobile_render_checks
    return [f.check_id for f in _mobile_render_checks(
        "TEC", _Facts(list(tags)), "https://x.test/x", trace)]


def test_no_trace_means_the_render_checks_are_silent_not_clean() -> None:
    """3b's shape. A page the trace never loaded gets no verdict from these
    six, and item 157's `not_assessed` covers it on screen -- rather than a
    proxy guessing from markup that cannot show overflow at all."""
    assert _traced_ids(None) == []
    assert _traced_ids({"traced": False}) == []


def test_the_three_layout_checks_read_the_render_and_state_the_viewport() -> None:
    """Item 147's step 8, taken in perf's existing pass. The width travels in
    the evidence the way `device_profile` does on the Speed part, because an
    overflow figure means nothing without the viewport it overflowed."""
    render = {
        "viewport_width": 412, "viewport_height": 823,
        "document_width": 520, "overflow_px": 108,
        "overflowing": [{"tag": "div", "cls": "banner wide", "right": 520,
                         "left": 0, "width": 520}],
        "small_tap_targets": [{"tag": "a", "text": "x", "w": 18, "h": 18}],
        "tap_target_min_px": 24,
        "viewport_unit_elements": [{"tag": "section", "cls": "hero",
                                    "used": ["height:100vh"]}],
    }
    from clauditseo.modules.tec import _mobile_render_checks
    found = _mobile_render_checks("TEC", _Facts(["width=device-width"]),
                                  "https://x.test/x", _rendered(render))
    by = {f.check_id: f for f in found}
    assert set(by) == {"horizontal-overflow", "tap-target", "viewport-units"}
    # The element is NAMED: `scrollWidth` alone cannot say what to fix, and a
    # finding nobody can act on is not worth raising.
    assert "div.banner" in by["horizontal-overflow"].summary
    assert by["horizontal-overflow"].evidence["viewport"] == "412 x 823 CSS px"
    assert by["tap-target"].evidence["minimum_px"] == 24
    assert "2.5.8" in by["tap-target"].summary
    # A clean render fires nothing -- the control.
    clean = {**render, "overflow_px": 0, "overflowing": [],
             "small_tap_targets": [], "viewport_unit_elements": []}
    assert _traced_ids(_rendered(clean)) == []


def test_injected_is_a_tag_only_the_rendered_head_has() -> None:
    """The diff, not a second render pass. And the reason the rename mattered:
    while both heads came from `document.head`, this comparison was a thing
    against itself and could only ever find them identical."""
    got = _traced_ids(_rendered(
        fetched="<head><title>t</title></head>",
        rendered='<head><title>t</title><meta name="viewport" '
                 'content="width=device-width"></head>'))
    assert got == ["viewport-injected"]


def test_divergent_is_a_tag_both_heads_have_and_disagree_on() -> None:
    got = _traced_ids(_rendered(
        fetched='<head><meta name="viewport" content="width=1024"></head>',
        rendered='<head><meta name="viewport" content="width=device-width"></head>'))
    assert got == ["viewport-divergent"]
    # Agreeing heads fire neither.
    same = '<head><meta name="viewport" content="width=device-width"></head>'
    assert _traced_ids(_rendered(fetched=same, rendered=same)) == []


def test_late_is_read_from_the_fetched_head_because_order_is_the_servers() -> None:
    """`viewport-late` is about the order the SERVER sent things in. The
    rendered head's order is whatever a script left behind, so reading it there
    would judge the page on something the browser never laid out against."""
    late = ('<head><link rel="stylesheet" href="/a.css">'
            '<meta name="viewport" content="width=device-width"></head>')
    early = ('<head><meta name="viewport" content="width=device-width">'
             '<link rel="stylesheet" href="/a.css"></head>')
    assert "viewport-late" in _traced_ids(_rendered(fetched=late, rendered=late))
    assert "viewport-late" not in _traced_ids(_rendered(fetched=early,
                                                        rendered=early))
    # An async script ahead of it does not block layout, so it is not "late".
    async_first = ('<head><script async src="/a.js"></script>'
                   '<meta name="viewport" content="width=device-width"></head>')
    assert "viewport-late" not in _traced_ids(
        _rendered(fetched=async_first, rendered=async_first))


def test_one_missing_head_makes_the_diff_unknown_not_clean() -> None:
    """With either head absent or `unavailable` the answer is unknown, and
    these checks say nothing. A fallback to the rendered head for both -- which
    is what the old single `head_html` amounted to -- would have reported every
    page clean."""
    only_rendered = '<head><meta name="viewport" content="width=device-width"></head>'
    assert _traced_ids(_rendered(rendered=only_rendered)) == []
    assert _traced_ids(_rendered(fetched="unavailable",
                                 rendered=only_rendered)) == []


def test_a_page_with_no_viewport_raises_only_that() -> None:
    """The precedence rule, and the reason it is applied in the sweep rather
    than left to the brief: with no tag, a claim about what the tag says would
    be a claim about nothing.

    `viewport-missing` sets aside `viewport-width`, `viewport-scale`,
    `zoom-suppressed` and `viewport-legacy` -- all four of which would
    otherwise fire, because a missing tag has no device-width and no
    initial-scale either.
    """
    assert _ids([]) == ["viewport-missing"]


def test_a_correct_viewport_raises_nothing() -> None:
    """The control. Without it every clause below would pass against a
    function that raised all six unconditionally."""
    assert _ids(["width=device-width, initial-scale=1"]) == []


@pytest.mark.parametrize("tag,expected", [
    ("width=1024, initial-scale=1", "viewport-width"),
    ("width=device-width", "viewport-scale"),
    ("width=device-width, initial-scale=1, user-scalable=no", "zoom-suppressed"),
    ("width=device-width, initial-scale=1, maximum-scale=1", "zoom-suppressed"),
    ("width=device-width, initial-scale=1, target-densitydpi=medium-dpi",
     "viewport-legacy"),
])
def test_each_parse_only_defect_raises_its_own_check(tag, expected) -> None:
    assert _ids([tag]) == [expected], tag


def test_minimum_scale_alone_never_suppresses_zoom() -> None:
    """The prompt says this in terms, and it is the mistake worth a clause of
    its own: a low `minimum-scale` lets a user zoom OUT. It suppresses nothing,
    and reading it as a zoom block would report a defect that is not there.
    """
    assert _ids(["width=device-width, initial-scale=1, minimum-scale=0.5"]) == []


def test_a_duplicate_tag_sets_aside_nothing_and_the_last_one_wins() -> None:
    """Per the prompt, `viewport-duplicate` suppresses nothing: the effective
    tag is judged on its own merits and the duplication is its own defect.

    The last tag wins in a browser, so that is the one read -- here a correct
    tag followed by `width=1024`, which means the page IS broken despite the
    first tag being right. Reading the first would have called it clean.
    """
    got = _ids(["width=device-width, initial-scale=1", "width=1024"])
    assert "viewport-duplicate" in got
    assert "viewport-width" in got and "viewport-scale" in got, (
        "the EFFECTIVE tag is the last one, and it is the broken one")


def test_a_malformed_scale_is_not_read_as_a_number() -> None:
    """`initial-scale=one` is absent as far as a comparison goes, not zero."""
    assert _ids(["width=device-width, initial-scale=one"]) == ["viewport-scale"]


# --- registration, both parts ----------------------------------------------


def test_the_mobile_brief_is_installed_under_the_tec_prefix() -> None:
    brief = next(b for b in briefs.catalogue() if b.id == "mobile-viewport")
    assert brief.part == "mobile" and len(brief.checks) == 15
    assert all(c.startswith("TEC/") for c in brief.checks), (
        "decision A option 1: no MOB dimension, the ids take TEC's prefix")
    assert {c.split("/")[-1] for c in brief.checks} == set(SWEPT) | set(BRIEF_ONLY)
    assert len(SWEPT) == 12 and len(BRIEF_ONLY) == 3, (
        "item 147's own registration, reached by each id joining the severity "
        "table on the run where a sweep could raise it")


def test_the_international_brief_is_installed_under_int() -> None:
    brief = next(b for b in briefs.catalogue() if b.id == "hreflang")
    assert brief.part == "intl" and len(brief.checks) == 11
    assert all(c.startswith("INT/") for c in brief.checks)
    assert {c.split("/")[-1] for c in brief.checks} == set(INTL)


def test_only_the_checks_the_sweep_raises_are_priced_free() -> None:
    """The registration split, and a deliberate departure from 147's literal
    instruction: it lists severities for all fifteen and puts only three in the
    brief-only register, which is the END state after its step 8 builds the
    360 px render harness.

    `DEFAULT_SEVERITY`'s own rule is that it is pinned to exactly what the
    sweep raises. Registering twelve there today would price six checks FREE
    while nothing emits them -- which is the defect 147's section A warns about
    (`check_cost` returns FREE for an id the app has never heard of), arriving
    from the other side.
    """
    for check in SWEPT:
        assert check_cost(f"TEC/{check}") == "free", check
        assert check in tec.DEFAULT_SEVERITY, check
    for check in BRIEF_ONLY:
        assert check_cost(f"TEC/{check}") == "model", check
        assert check not in tec.DEFAULT_SEVERITY, (
            f"{check} needs a capture that does not exist; a severity here "
            "would price it free")
    for check in INTL:
        assert check_cost(f"INT/{check}") == "model", check


def test_every_check_of_both_parts_knows_its_part() -> None:
    """An id with no category has no part page to appear on, and nothing fails
    when it goes missing -- it simply is not drawn."""
    for check in SWEPT + BRIEF_ONLY:
        assert anatomy.CHECK_CATEGORY.get(check) == "mobile", check
    for check in INTL:
        assert anatomy.CHECK_CATEGORY.get(check) == "intl", check


def test_int_is_label_only_and_claims_no_sweep() -> None:
    """148's decision A, and the opposite of 147's. `INT` must name where a
    finding came from without implying a sweep covers `intl`, which is in
    `ANALYSIS_ONLY`."""
    from clauditseo.checks import LABEL_ONLY_REGISTRIES

    assert [code for code, _sev, _only in LABEL_ONLY_REGISTRIES] == ["INT"]
    assert "INT" not in anatomy.DIMENSION_CATEGORIES, (
        "an entry here claims a sweep refreshes those categories")
    assert "intl" in anatomy.ANALYSIS_ONLY
    covered = {cat for cats in anatomy.DIMENSION_CATEGORIES.values()
               for cat in cats}
    assert "intl" not in covered
    # Mobile is the other way round, and that is the point of the pair.
    assert "mobile" in anatomy.DIMENSION_CATEGORIES["TEC"]


def test_uncovered_does_not_report_declared_checks_a_sweep_never_emitted(
        tmp_path) -> None:
    """Both briefs assert the opposite, and 148 makes it a blocking step: that
    declaring the checks would make `_uncovered` report all of them forever.

    Driven here rather than argued. `_uncovered` reports *sweep rows the
    brief's rows do not cover* -- it queries
    `findings WHERE source='deterministic'` -- so an analysis-only part with no
    sweep has nothing to be uncovered by, and the answer is zero. The blocking
    step was not built because it was not needed, and this is the record.
    """
    from clauditseo.analysts.expert import _uncovered
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    conn = connect(tmp_path / "t.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn, "148")
    site = repo.create_site(conn, repo.create_client(conn, op, "Co"), "x.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")

    got = _uncovered(conn, run_id, [f"INT/{c}" for c in INTL],
                     rows=[], page_set=["https://x.test/"])
    assert got == [], (
        f"eleven declared ids and no sweep findings produced {len(got)} "
        "uncovered rows")
    conn.close()


# --- brief 160 step 7: the contract reader, built once for both parts -------


def _parsed(block: dict, checks: list[str], pages: list[str]):
    import json

    from clauditseo.analysts.contract import parse
    report = ("```json\n" + json.dumps(block) + "\n```\n\n"
              "## Block 2 — readable\nprose")
    return parse(report, checks, pages)


def test_the_contract_reader_keeps_brief_v20s_block_keys() -> None:
    """Until now the parser dropped every one of these: the briefs emitted
    `schema`, `templates`, `locales` and `fixes[]` and nothing kept them.

    `contract.py` already warns about exactly this failure — *"a field the
    parser fills but `as_dict` drops is a field that exists only in memory"* —
    so this asserts they survive **`as_dict`**, which is what is stored and
    what the screen reads, not just the dataclass.

    One reader for both parts, per brief 160 step 7, rather than two.
    """
    # Shapes as the INSTALLED schemas define them. This clause first built its
    # JSON with `locales` as a list and passed, because the reader shared the
    # same wrong assumption -- which is exactly how the defect reached a real
    # run. `locales` is an object.
    got = _parsed({
        "schema": "mobile/2", "part": "mobile",
        "templates": [{"template": "blog", "pages": 38, "verdict": "defective"}],
        "locales": {"observed": ["en-AU"], "stated": ["en-AU", "en-NZ"],
                    "basis": "lang attributes", "conflict": None},
        "fixes": [{"fix_id": "F1", "edit_point": "theme header",
                   "change": "add initial-scale=1", "pages_affected": 7}],
        "rows": [],
    }, ["TEC/viewport-scale"], ["https://x.test/a"]).as_dict()

    assert got["schema"] == "mobile/2", "the schema version tells a reader which shape it has"
    assert got["templates"] == [{"template": "blog", "pages": 38, "verdict": "defective"}]
    assert got["locales"]["stated"] == ["en-AU", "en-NZ"]
    assert got["fixes"][0]["fix_id"] == "F1"
    assert got["fixes"][0]["pages_affected"] == 7


def test_a_row_carries_its_fix_its_suppression_and_its_confidence() -> None:
    """The three row fields, as the installed schemas define them.

    `suppressed` is a LIST, on the row that SURVIVES, naming what it set aside
    -- "a check set aside emits no row of its own; it is named in `suppressed`
    on the row that survives". This clause first asserted the opposite: a
    because-clause string on the suppressed row pointing up at its owner. It
    passed, because the reader was built on the same misreading. The first real
    run disproved both.

    The distinction brief 160 step 5 wanted survives the correction: a reader
    looking for the set-aside check finds it named on the row that answers for
    it, which is "the answer is here" and not "run deeper".
    """
    rows = _parsed({
        "schema": "mobile/2", "part": "mobile",
        "rows": [
            {"check": "TEC/viewport-missing", "page": "https://x.test/a",
             "status": "FAIL", "severity": "high", "evidence": "no viewport tag",
             "fix_id": "F1", "confidence": None,
             "suppressed": ["TEC/viewport-width", "TEC/viewport-scale"]},
            {"check": "TEC/viewport-legacy", "page": "https://x.test/b",
             "status": "FAIL", "severity": "medium", "evidence": "e",
             "suppressed": [], "confidence": "high"},
        ],
    }, ["TEC/viewport-missing", "TEC/viewport-legacy", "TEC/viewport-width",
        "TEC/viewport-scale"], ["https://x.test/a", "https://x.test/b"]
    ).as_dict()["rows"]

    by = {r["check_id"]: r for r in rows}
    assert by["viewport-missing"]["suppressed"] == ["TEC/viewport-width",
                                                    "TEC/viewport-scale"]
    assert by["viewport-missing"]["fix_id"] == "F1"
    assert by["viewport-legacy"]["suppressed"] == []
    # Absent is not empty and not low: a `null` confidence is a measurement's.
    assert by["viewport-missing"]["confidence"] is None
    assert by["viewport-legacy"]["confidence"] == "high"


# --- brief 160 step 6: the gate says which reason ---------------------------


def test_the_gate_distinguishes_settled_from_undetermined() -> None:
    """`_hreflang_applies` refused for two different reasons and returned one
    string for both. They lead a reader to opposite actions, so they are two
    states (brief 160 step 6).

    - pages read, one language declared -> **`na`**: settled, nothing to fix,
      a zero under the part is honest.
    - nothing readable, or no page declaring a language at all -> **`not_assessed`**:
      the product cannot tell, and a zero under it is the vacuous pass item
      157 exists to stop.

    A site whose pages declare no `lang` is not demonstrably single-locale,
    and the gate was reading that as grounds to refuse as though it were.
    """
    from clauditseo.analysts.expert import ABSENT, _hreflang_applies

    def gate(pages):
        return _hreflang_applies({"start_url": "https://x.test/", "pages": pages},
                                 {"TARGET_LOCALES": ABSENT})

    settled = gate([{"url": "https://x.test/", "status": 200,
                     "content_type": "text/html", "lang": "en-AU"}])
    assert settled["state"] == "na"
    assert "does not apply" in settled["reason"]

    for pages, label in (([], "no readable page"),
                         ([{"url": "https://x.test/", "status": 200,
                            "content_type": "text/html", "lang": ""}],
                          "a page declaring no language")):
        unsettled = gate(pages)
        assert unsettled["state"] == "not_assessed", label
        assert "could not be determined" in unsettled["reason"], label
        assert "NOT a finding that the site is single-locale" in unsettled["reason"], (
            f"{label}: the refusal must deny the claim it would otherwise imply")


def test_locale_certainty_separates_single_from_unknown() -> None:
    """The judgement on its own, because `locale_evidence`'s boolean answers a
    different question (is it multi) and its False was doing double duty."""
    from clauditseo.analysts.expert import locale_certainty

    assert locale_certainty([]) == "unknown"
    assert locale_certainty([{"url": "https://x/", "lang": ""}]) == "unknown"
    assert locale_certainty([{"url": "https://x/", "lang": "en-AU"}]) == "single"
    assert locale_certainty([{"url": "https://x/", "lang": "en"},
                             {"url": "https://x/fr/", "lang": "fr"}]) == "multi"
    # Already annotated is multi whatever the langs say: a site with hreflang
    # in place is a site hreflang applies to.
    assert locale_certainty([{"url": "https://x/", "lang": "en",
                              "hreflang": [("en", "/")]}]) == "multi"


# --- brief 160 steps 5 and 7 on screen: the three pieces both parts share ---


def test_the_three_shared_pieces_are_written_once() -> None:
    """147 E2/E3/E4 and 148 G3/G4/G5 are the same three pieces, and brief 160
    says to build them once. Asserted off the source rather than a rendered
    screen, because the claim is that there is ONE of each -- a second
    spelling somewhere else is exactly what the instruction forbids, and a
    rendered clause can only check the parts a fixture happens to open.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src")
    part_page = (src / "part_page.tsx").read_text(encoding="utf-8")

    for name in ("ConfidenceChip", "SuppressedStrip", "BriefFixes"):
        assert f"export function {name}(" in part_page, name
        # Declared once, in the file both parts render through.
        others = [f for f in src.glob("*.tsx") if f.name != "part_page.tsx"
                  and f"function {name}(" in f.read_text(encoding="utf-8")]
        assert not others, f"{name} is declared again in {[f.name for f in others]}"


def test_a_low_confidence_fix_has_no_block_to_paste() -> None:
    """147 E2 in terms: *a low-confidence fix is a different card, not a dimmed
    one: it has no corrected-tag block at all.*

    A replacement rendered in a copyable block IS an instruction, and an
    instruction the brief is unsure of must not be offered as one. The card
    says what it suspects instead. Asserted on the source because it is a
    structural claim about the component, not about one fixture's data.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    i = src.index("export function BriefFixes(")
    body = src[i:i + 2600]
    # The change block is gated on NOT low, and the candidate sentence on low.
    assert "{change && !low &&" in body, (
        "the corrected block must be withheld from a low-confidence card, not "
        "merely styled differently")
    assert "Candidate, not a fix" in body
    # And the card is a different card, by its own class.
    assert "brief-fix-low" in body


def test_the_suppressed_strip_and_the_confidence_chip_are_mounted_in_the_row() -> None:
    """E3 puts the strip *inside the row, under the evidence* and E4 puts the
    chip on the row's head. Both matter: above the body the strip would read as
    a reason not to read on, and a chip anywhere but the head is not a label on
    the row.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    assert "<ConfidenceChip value={fix.confidence} />" in src
    assert "<SuppressedStrip checks={fix.suppressed} />" in src
    # Under the body, not above it.
    body_at = src.index("<render.body fix={fix} facts={facts} />")
    strip_at = src.index("<SuppressedStrip checks={fix.suppressed} />")
    assert body_at < strip_at, "the strip belongs under the evidence"


def test_a_measured_row_carries_no_confidence_chip() -> None:
    """Absent is NOT low. A row the sweep measured carries no confidence
    because a measurement's confidence is not the model's to state, and
    drawing "low" there would grade the engine's own work as a guess. So the
    component renders nothing rather than a neutral chip.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    i = src.index("export function ConfidenceChip(")
    body = src[i:i + 900]
    assert "if (!value) return null;" in body


def test_the_fixes_list_is_data_gated_not_part_gated() -> None:
    """Mounted for every part and filled only by a brief that emits `fixes[]`.

    The alternative -- a conditional on the part -- is what item 4's slot
    settled from the other side: there the part chooses, here the payload
    does, and neither leaves a row every other part has to opt out of.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    assert "<BriefFixes fixes={(part.brief_fixes ?? []) as BriefFix[]} />" in src
    i = src.index("export function BriefFixes(")
    assert "if (!fixes.length) return null;" in src[i:i + 700]


def test_the_payload_carries_the_block_keys_and_the_row_fields() -> None:
    """The reader stores them (guarded above) and `anatomy_view` must put them
    on the category, or they reach the parser and stop there -- which is the
    failure `contract.py` already warns about one layer down."""
    from pathlib import Path

    runs = (Path(__file__).resolve().parents[1] / "clauditseo" / "persistence"
            / "runs.py").read_text(encoding="utf-8")
    for key in ("brief_templates", "brief_locales", "brief_fixes",
                "brief_schema"):
        assert f'"{key}": brief_' in runs, key
    for field in ("fix_id", "suppressed", "confidence"):
        assert f'"{field}": r.get("{field}")' in runs, field


def test_the_overflow_list_names_only_what_can_cause_the_scroll() -> None:
    """Found on the first live run that exercised `mobile_render` (twenty22
    `ed718610`, 2026-09-13), and fixed before anything was built on it.

    The first version listed every element whose box crossed the viewport
    edge. On all twelve traced pages it named `mm__mobile-nav
    bricks-lazy-hidden` -- a HIDDEN off-canvas menu 6 px past 412 -- while
    `overflow_px` was 0 and the document did not scroll at all.

    No false finding fired: `horizontal-overflow` is gated on `overflow_px`.
    But its summary says "starting with" the first element listed, so on a
    page that genuinely overflowed it would have sent a reader to fix a menu
    that was never the cause. The evidence would have been wrong exactly when
    it was needed.

    Re-run live after the fix (`93ba9c80`): zero pages list elements where
    nothing overflows, the menu is named nowhere, and tap-target and
    viewport-units still measure the same pages -- so the fix touched only the
    list.

    Asserted on the source because this is browser JavaScript, which no Python
    test executes; the live runs above are the behavioural proof.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "clauditseo"
           / "perf.py").read_text(encoding="utf-8")
    i = src.index("const overflowing = [];")
    block = src[i:i + 1800]
    # Nothing listed where nothing overflows.
    assert "if (docw > vw) {" in block
    # Hidden elements skipped: a box is still reported for an element no one
    # can see.
    assert 'cs.visibility === "hidden"' in block
    assert 'parseFloat(cs.opacity) === 0' in block
    # An element clipped by an ancestor that hides overflow does not scroll.
    assert "clipped(el)" in block and 'o === "hidden" || o === "clip"' in block
    # The element that sets the scroll width is named first.
    assert "overflowing.sort((a, b) => b.right - a.right);" in block


# --- the shapes the INSTALLED schemas use, pinned against real output --------
#
# Every clause above that built contract JSON by hand used the shapes I assumed,
# and three of them were wrong. The first real International run (Acme
# 19eeb42e, 2026-09-13) found all three: `suppressed` is a LIST on the surviving
# row, `locales` is an OBJECT, and `fixes[]` names its fields `edit_point`,
# `pages_affected` and `templates`/`clusters`. The fixture below is built from
# what that run's corrected re-parse actually contained, not from assumption.

REAL_INTL_BLOCK = {
    "schema": "intl/2", "part": "intl",
    "locales": {
        "observed": ["en-AU"],
        "stated": ["en-AU", "en-SG", "en-NZ", "en-GB"],
        "basis": ('lang="en" observed on all 100 crawled pages; rel=alternate '
                  "annotations on 1 of 100 pages"),
        "conflict": None,
    },
    "clusters": [{"cluster_id": "C1", "members": ["https://www.acme.com.au/"],
                  "method": "head", "closed": False, "x_default": True,
                  "members_fetched": 1, "verdict": "partial"}],
    "fixes": [{"fix_id": "F1", "clusters": ["C1"],
               "edit_point": "homepage head template, acme.com.au",
               "change": "emit reciprocal alternates on each market host",
               "closes": ["INT/hreflang-reciprocity"],
               "pages_affected": 1, "confidence": "low"}],
    "rows": [
        {"check": "INT/hreflang-reciprocity", "dimension": "INT",
         "check_id": "hreflang-reciprocity", "cluster": "C1",
         "page": "https://www.acme.com.au/", "kind": "cluster",
         "status": "WARN", "severity": "MEDIUM",
         "evidence": "declares en-sg, en-nz, en-gb on other hosts",
         "fix_id": "F1", "suppressed": [], "confidence": "medium"},
        {"check": "INT/hreflang-target", "dimension": "INT",
         "check_id": "hreflang-target", "cluster": "C1",
         "page": "https://www.acme.com.au/", "kind": "cluster",
         "status": "WARN", "severity": "HIGH",
         "evidence": "alternate targets on hosts the crawl did not fetch",
         "fix_id": None, "suppressed": [], "confidence": "low"},
    ],
    "not_assessable": [{"check": "INT/hreflang-method-mixed", "scope": "site",
                        "reason": "HTTP Link headers are not reached by the crawl"}],
}


def _parse_real(block):
    return _parsed(block, [f"INT/{c}" for c in INTL],
                   ["https://www.acme.com.au/"]).as_dict()


def test_an_empty_suppressed_list_is_empty_not_the_string_brackets() -> None:
    """The defect that would have put "Set aside: []" on every card. The model
    wrote `"suppressed": []`, correctly, and the reader ran `str()` on it."""
    rows = _parse_real(REAL_INTL_BLOCK)["rows"]
    assert rows, "the fixture must produce rows"
    for r in rows:
        assert r["suppressed"] == [], (
            f"{r['check_id']}: got {r['suppressed']!r}; an empty list must stay "
            "empty, never become the truthy string '[]'")


def test_suppressed_names_what_the_surviving_row_sets_aside() -> None:
    """Direction pinned to the installed prompt: "a check set aside emits no row
    of its own. It is named in `suppressed` on the row that survives." A list of
    full ids, on the row that stands."""
    block = {**REAL_INTL_BLOCK, "rows": [
        {**REAL_INTL_BLOCK["rows"][0],
         "suppressed": ["INT/hreflang-self", "INT/hreflang-x-default"]}]}
    row = _parse_real(block)["rows"][0]
    assert row["suppressed"] == ["INT/hreflang-self", "INT/hreflang-x-default"]


@pytest.mark.parametrize("raw,want", [
    ([], []), (None, []), ("", []), ("[]", []), ("none", []),
    ("INT/hreflang-self", ["INT/hreflang-self"]),
    (["INT/a", "", 3, "INT/b"], ["INT/a", "INT/b"]),
])
def test_suppressed_is_read_as_a_list_however_it_was_written(raw, want) -> None:
    """A bare string meant one check; a list with junk in it keeps only the ids;
    the literal strings a model might write for "nothing" mean nothing."""
    from clauditseo.analysts.contract import _check_list
    assert _check_list(raw) == want


def test_locales_is_kept_as_the_object_the_schema_defines() -> None:
    """It was declared a list and read as one, which iterated the object's keys,
    found no dicts, and dropped it: the first Acme run's locales vanished."""
    loc = _parse_real(REAL_INTL_BLOCK)["locales"]
    assert isinstance(loc, dict), f"locales must be the object, got {loc!r}"
    assert loc["observed"] == ["en-AU"]
    assert loc["stated"] == ["en-AU", "en-SG", "en-NZ", "en-GB"]
    # A brief answering it as a list is a shape the screen cannot draw, so it is
    # not stored as though it were one.
    as_list = _parse_real({**REAL_INTL_BLOCK, "locales": [{"observed": ["en"]}]})
    assert as_list["locales"] is None


def test_the_fix_card_reads_the_schemas_field_names() -> None:
    """`BriefFixes` first read `where`, `serves` and `pages` -- none of which
    either installed brief emits -- so every card would have said "where it goes
    is not stated" with no page count. Pinned to the names both schemas use.
    Asserted on the component source, because the fields it reads are the
    claim."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    i = src.index("export function BriefFixes(")
    body = src[i:i + 3000]
    for name in ("f.edit_point", "f.pages_affected", "f.templates ?? f.clusters"):
        assert name in body, f"BriefFixes does not read {name}"
    for wrong in ("f.where", "f.serves", "f.pages ", "f.pages)"):
        assert wrong not in body, f"BriefFixes still reads a field no brief emits: {wrong}"
    # And the parsed real fix actually carries them.
    fix = _parse_real(REAL_INTL_BLOCK)["fixes"][0]
    assert fix["edit_point"] and fix["pages_affected"] == 1 and fix["clusters"] == ["C1"]


# --- the two parts on the three-block layout, verified on screen ------------


def _src(name: str) -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "dashboard" / "src"
            / name).read_text(encoding="utf-8")


def test_both_parts_render_where_their_shared_pieces_live() -> None:
    """The shared fixes list, strip and chip were built into part_page.tsx and
    never reached either part: both fell through to the across-the-site layout,
    and a screen check found zero fix cards on International beside a payload
    holding a real fix. Registered here, on the slot that keeps the checks
    table."""
    src = _src("part_page.tsx")
    assert "intl: { noPageBlock: true, now: IntlNow, siteNow: IntlSiteNow" in src
    assert "mobile: { noPageBlock: true, now: MobileNow, siteNow: MobileSiteNow" in src


def test_neither_part_uses_the_slot_that_drops_the_checks_table() -> None:
    """`siteScope` was used first, and it takes the branch that skips
    ChecksTable -- so the "N checks pass" and "not assessed" lines item 157
    keeps honest vanished from both parts. `siteNow` draws picture, then checks
    table, then fixes."""
    src = _src("part_page.tsx")
    for key in ("intl", "mobile"):
        start = src.index(f"  {key}: {{ noPageBlock: true, now: ")
        entry = src[start:src.index("},", start) + 2]
        assert "siteScope" not in entry, f"{key} is on the slot that drops the table"


def test_the_clean_line_states_the_denominator_each_check_was_measured_over() -> None:
    """On twenty22 four of Mobile's ten clean checks had been read on 12 traced
    pages and the line said "every page this run fetched (45 crawled)". Split
    now: the parse checks over the crawl, the trace checks over the traced
    pages, with the population still the crawl and only the word moving."""
    src = _src("part_page.tsx")
    assert "clean on every page this audit traced" in src
    assert "spotlessTraced" in src and "part.trace_derived" in src


def test_a_not_applicable_part_is_not_worded_not_assessed() -> None:
    """The gate card said "Not applicable" and the line beneath it said "11
    checks not assessed -- no brief has run for this part yet". The "yet"
    promised a run the gate refuses forever, and brief 160 step 6 made `na` a
    settled state. Two states, two words."""
    src = _src("part_page.tsx")
    phrase = 'part.gate?.state === "na" ? "not applicable" : "not assessed"'
    assert src.count(phrase) == 2


def test_the_verdict_and_confidence_tones_exist_in_the_vocabulary() -> None:
    """They used `level-*` tones, which exist nowhere -- `pill.tsx`'s `Tone`
    union reserves coloured fills for `sev-*`. The confidence chip passed them
    as raw class strings, so no type check could see it render unstyled."""
    src = _src("part_page.tsx")
    for invented in ("level-good", "level-poor", "level-ni"):
        assert invented not in src, invented
    tones = (Path_ := __import__("pathlib").Path)(__file__).resolve().parents[1] \
        / "dashboard" / "src" / "pill.tsx"
    vocabulary = tones.read_text(encoding="utf-8")
    for tone in ("count-zero", "sev-medium", "sev-high", "state-candidate",
                 "source-brief"):
        assert f'"{tone}"' in vocabulary, tone


def test_the_gate_is_read_from_evidence_and_cannot_fail_silently() -> None:
    """It was `except Exception` around `json.loads`, with `json` never imported
    at module level in app.py: NameError, swallowed, gate None on every site.
    On a multi-locale site None is also the right answer, so a live check could
    not see the breakage. Only malformed evidence is tolerated now."""
    from pathlib import Path
    app = (Path(__file__).resolve().parents[1] / "clauditseo" / "api"
           / "app.py").read_text(encoding="utf-8")
    i = app.index("gate_state = None")
    block = app[i:i + 1800]
    assert "except (TypeError, ValueError):" in block
    # With the colon: the comment in that block names the old handler as
    # `except Exception` to explain the defect, and a bare substring match
    # found the explanation and failed on it.
    assert "except Exception:" not in block
    # The parse goes through the shared evidence parser now, which is
    # reachable from the module-level `runs` import - the name that was
    # missing when this was a bare `json.loads`.
    assert "runs.parsed_evidence(" in block


def test_a_v20_not_assessable_entry_keeps_its_reason_on_the_held_card() -> None:
    """Brief v20 writes `not_assessable` as `{check, scope, reason}` with no
    `needs`. The reader copied `needs` alone, stored "", and the card - which
    keys "held" on `needs` - drew five blank `info` cards on Acme
    International, one a second "Hreflang target" beside the real row."""
    import inspect

    from clauditseo.persistence import runs
    src = inspect.getsource(runs)
    i = src.index("brief_held.setdefault(part, []).extend(")
    block = src[i - 900:i + 200]
    assert 'h.get("reason")' in block and 'h.get("scope")' in block
    assert '"needs": _needs(h)' in block
