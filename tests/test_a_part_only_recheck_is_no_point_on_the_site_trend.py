"""A re-check of a part is no point on the site's trend (channel ruling
20261017-1130, screen audits round 4 Record IP-01).

twenty22's two Links-only re-checks drew as green points at 87.4 and 87.9,
partnered to each other above the site's 68 to 72, and the analysts and the
client report read the same series. `site_trend` now drops `part_only_runs`
before keying and pairing, for site-level series only.
"""
from __future__ import annotations

from clauditseo.persistence import runs as runs_repo
from tests.test_a_point_reads_against_the_nearest_same_basis_run import _plant, _site

BASE = ["A11Y", "AIS", "CNT", "ONP", "PRF", "TEC"]


def _point(at, score, dims):
    return {"at": at, "score": score, "tier": "T2", "engine": "0.29.0",
            "basis": "coverage+breadth", "dims": dims, "recorded": True}


def test_a_recheck_is_dropped_from_the_composite_and_kept_in_its_subscore(tmp_path):
    conn, site_id = _site(tmp_path)
    first = _plant(conn, site_id, _point("2026-10-01T00:00:00+00:00", 70.0, BASE))
    recheck = _plant(conn, site_id, _point("2026-10-03T00:00:00+00:00", 87.4, ["ONP"]))
    full = _plant(conn, site_id, _point("2026-10-05T00:00:00+00:00", 71.0, BASE))

    assert recheck in runs_repo.part_only_runs(conn, site_id)
    trend = runs_repo.site_trend(conn, site_id)
    assert [p["run_id"] for p in trend] == [first, full], trend
    # The partner of the next full reading skips the dropped point.
    assert trend[-1]["partner_run_id"] == first, trend[-1]
    assert trend[-1]["comparable"] is True, trend[-1]
    # Said, so the chart can say it.
    label = runs_repo.part_only_label(runs_repo.part_only_runs(conn, site_id)[recheck])
    assert trend[-1]["rechecks_hidden"] == [label], trend[-1]
    # ONP's own series keeps it: a fair reading of onp.subscore.
    onp = runs_repo.site_trend(conn, site_id, "onp.subscore")
    assert recheck in [p["run_id"] for p in onp], onp


def test_a_first_narrow_audit_stays_a_point(tmp_path):
    conn, site_id = _site(tmp_path)
    narrow = _plant(conn, site_id, _point("2026-10-01T00:00:00+00:00", 60.0, ["ONP"]))
    wide = _plant(conn, site_id, _point("2026-10-05T00:00:00+00:00", 71.0, BASE))
    trend = runs_repo.site_trend(conn, site_id)
    assert [p["run_id"] for p in trend] == [narrow, wide], trend
    assert "rechecks_hidden" not in trend[-1]
