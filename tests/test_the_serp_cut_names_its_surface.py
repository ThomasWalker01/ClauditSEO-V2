"""Item 152: the SERP cut is measured on the surface Google indexes.

Operator's decision A (2026-09-13): mobile becomes the primary cut. A title
fires `title-length` at 410 px, the desktop width travels in the evidence as
the parity note, and the threshold line names its viewport. The description
stays on desktop until its mobile width is measured. The strip, the facts row
and the snippet card read the same helper the check reads, and the count jump
is marked by an engine version, so a trend reads it as a change in the
measurement rather than as every site regressing at once.
"""

from __future__ import annotations

import json
from pathlib import Path

from clauditseo import ENGINE_VERSION
from clauditseo.modules import onp

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: 410-600 px at the title font: cut on a phone, whole on desktop - the band
#: that was silent before this item (164 of 318 stored titles).
MOBILE_ONLY = "Commercial Business Loans for Growing Australian Companies"
#: Past 600 px: cut on both.
BOTH = ("A title written far past the width of any search result so it is cut "
        "on every surface a searcher could possibly read it on")


def _title_row(text: str) -> dict | None:
    fire_px, vp, other_px, other_vp = onp.cut_of(onp.GUIDELINES["title"])
    return onp._length_row(text, onp.TITLE_FONT, fire_px, other_px, onp.TITLE_MIN,
                           viewport=vp, other_viewport=other_vp)


def test_the_threshold_line_names_its_viewport() -> None:
    row = _title_row(BOTH)
    assert row, "the fixture title is not over the mobile width"
    assert f"cut at {onp.TITLE_PX_MOBILE} px on mobile" in row["says"], row["says"]
    assert row["evidence"]["viewport"] == "mobile", row["evidence"]
    # The desktop width is the parity note, and where desktop cuts it too the
    # words that fall off there travel with it.
    assert row["evidence"]["desktop_px_limit"] == onp.TITLE_PX_DESKTOP
    assert row["evidence"].get("falls_off_desktop"), row["evidence"]
    desc_px, desc_vp, _, _ = onp.cut_of(onp.GUIDELINES["meta_description"])
    drow = onp._length_row("word " * 400, onp.DESC_FONT, desc_px, None, onp.DESC_MIN,
                           viewport=desc_vp)
    assert f"cut at {onp.DESC_PX} px on desktop" in drow["says"], drow["says"]


def test_a_title_cut_on_mobile_only_is_reported() -> None:
    from clauditseo.textmetrics import measure
    px = measure(MOBILE_ONLY, onp.TITLE_FONT)["px"]
    assert onp.TITLE_PX_MOBILE < px <= onp.TITLE_PX_DESKTOP, (
        f"the fixture is {px} px and no longer sits in the mobile-only band")
    row = _title_row(MOBILE_ONLY)
    assert row, "a title cut on a phone and whole on desktop raised nothing"
    assert row["evidence"]["viewport"] == "mobile"
    assert "falls_off_desktop" not in row["evidence"], (
        "a desktop fall-off was reported for a title desktop does not cut")


def test_the_card_and_the_check_read_the_same_constant() -> None:
    fire_px, vp, _, _ = onp.cut_of(onp.GUIDELINES["title"])
    assert (fire_px, vp) == (onp.TITLE_PX_MOBILE, "mobile")
    assert _title_row(BOTH)["evidence"]["limit_px"] == fire_px
    snip = onp.snippet(MOBILE_ONLY, None)
    assert snip["title"]["fires"] == vp and snip["title"]["mobile_state"] == "bad"
    assert snip["description"]["fires"] == "desktop"
    runs_src = (Path(onp.__file__).resolve().parents[1] / "persistence" / "runs.py"
                ).read_text(encoding="utf-8")
    assert '"title_cut_px": cut_of(GUIDELINES["title"])[0]' in runs_src
    strips = (SRC / "title_snippet.tsx").read_text(encoding="utf-8")
    assert "fired(raw).state" in strips and "const tv = fired(title)" in strips
    assert "cut at {cut} px · {viewport}" in strips
    part = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert 'snippetToggle ?? facts.snippet.title.fires === "mobile"' in part


def test_the_count_discontinuity_reads_as_a_threshold_change_not_a_regression(tmp_path) -> None:
    """The count rises 5.7x on the stored corpus. Stamped under a new engine
    version, the first term of `site_trend`'s comparability key, the point after
    the change is not compared with the point before - and the fingerprint is
    unchanged, so the same title is the same finding either side."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.engine.types import fingerprint
    from clauditseo.persistence import repo, runs

    assert ENGINE_VERSION != "0.20.0"
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Trend Co"), "x.test")
    scope = json.dumps({"basis": "declared"})
    for at, engine, score in (("2026-09-12T00:00:00", "0.20.0", 80.0),
                              ("2026-09-14T00:00:00", ENGINE_VERSION, 64.0)):
        conn.execute(
            "INSERT INTO metric_snapshots (id, site_id, metric_key, value, source,"
            " confidence, captured_at, tier, engine_version, scope, run_id)"
            " VALUES (?, ?, 'composite_score', ?, 'engine', 'high', ?, 'T2', ?, ?, NULL)",
            (repo.create_id(), site_id, score, at, engine, scope))
    conn.commit()
    trend = runs.site_trend(conn, site_id)
    assert trend[-1]["comparable"] is False, (
        "the drop across the threshold change reads as a comparison")
    assert fingerprint("ONP", "title-length", "/a") == fingerprint("ONP", "title-length", "/a/")
    conn.close()


def test_the_description_has_no_mobile_cut_until_one_is_set() -> None:
    """Asserts the absence rather than inventing a number: the description's
    mobile width needs the measurement `DESC_PX` got."""
    guide = onp.GUIDELINES["meta_description"]
    assert guide["mobile_px"] is None and onp.cut_of(guide)[1] == "desktop"
    px, vp, other, other_vp = onp.cut_of(guide)
    row = onp._length_row("x " * 700, onp.DESC_FONT, px, other, onp.DESC_MIN,
                          viewport=vp, other_viewport=other_vp)
    assert row and not any(k.startswith("falls_off_") for k in row["evidence"]), row
