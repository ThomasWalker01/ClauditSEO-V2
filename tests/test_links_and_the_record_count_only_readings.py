"""Round 4 Mediums on Links and the Record (screen audits round 4).

- Links AC-01: a `broken-internal` row naming only the CDN's
  `/cdn-cgi/l/email-protection` was open from 3 Oct and could never close;
  a site reading now sets it aside.
- Record IP-02: the trend sentence no longer says "left of the first rule".
- Record IP-04, UX-02, UX-03: the Audits view keys no severity and has no
  filter strip; one audit's history has one way back.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs
from clauditseo.persistence.runs import Reading, measured

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_a_cdn_path_finding_is_set_aside_by_a_site_reading():
    site = Reading("r", frozenset({"LNK"}), frozenset({"/"}), frozenset(), frozenset(), True)
    state, why = measured(site, "LNK", "broken-internal",
                          ["https://gate-six.test/cdn-cgi/l/email-protection"])
    assert state == "inapplicable" and "CDN" in why
    scan = Reading("r", frozenset({"LNK"}), frozenset({"/"}), frozenset(), frozenset(), False)
    assert measured(scan, "LNK", "broken-internal",
                    ["https://gate-six.test/cdn-cgi/l/email-protection"])[0] == "unmeasured"


def test_the_record_views_say_only_what_they_draw():
    t = (SRC / "score_trend.tsx").read_text(encoding="utf-8")
    assert "everything left of the first rule is history" not in t
    v = (SRC / "views.tsx").read_text(encoding="utf-8")
    assert '!(tab === "all" && recordView === "audits")' in v
    assert '<RunDetailView runId={run.id} embedded />' in v
    assert '<Legend ids={["action-danger", "danger-undone"]} />' in v


def test_a_passed_check_is_not_also_unreturned():
    """Structured data AC-01: schema-review-unsupported read "returned no row
    for" two lines above "judged and found nothing wrong with"."""
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "spotlessAll.filter((r) => !spotlessPassed.includes(r))" in p
