"""A Speed row naming the cause of a slow paint, on a page whose LCP is in
the Good band, is dropped.

Screen audits round 3, Speed AC-04 (High): every kept analysis row was on a
template whose LCP met the budget - `critical-path` and `lcp-cause` on
`/webdesign/<slug>/` at 2296 ms ("passes the 2500 ms budget", the card said)
and `lcp-cause` on `/seo/technical/<slug>/` at 1872 ms - all Medium with
Confirm, which opened as a site fault a cause for a paint that was fine.
"""
from __future__ import annotations

from clauditseo.analysts import contract


def _row(check, evidence):
    return contract.Row(check=check, dimension="PRF", check_id=check.split("/")[1],
                        page="/x/", status="WARN", severity="medium",
                        evidence=evidence, replacement="Preload the hero", note="")


def test_a_good_lcp_has_no_paint_cause():
    why = contract._speed_guard(_row(
        "PRF/critical-path", "LCP 2296 ms passes the 2500 ms budget but TTFB is most of it"))
    assert why and "2296 ms" in why and "Good band" in why and "ttfb-slow" in why
    assert contract._speed_guard(_row("PRF/lcp-cause", "LCP 1872 ms lab: ttfb 1240.6"))


def test_a_slow_lcp_or_another_check_stands():
    assert contract._speed_guard(_row("PRF/lcp-cause", "LCP 3120 ms lab: hero image")) is None
    assert contract._speed_guard(_row("PRF/lcp-cause", "hero image 951 KB")) is None
    assert contract._speed_guard(_row("PRF/ttfb-slow", "LCP 1800 ms; TTFB 1240 ms")) is None


def test_a_row_that_also_states_a_poor_lcp_stands():
    # Channel 20261016-1302: the first figure alone dropped a row whose
    # second stated LCP was poor.
    assert contract._speed_guard(_row(
        "PRF/lcp-cause", "LCP 2296 ms lab on /a/; LCP 3100 ms on /b/ template")) is None
    why = contract._speed_guard(_row("PRF/lcp-cause", "LCP 1872 ms lab; LCP 2296 ms on /b/"))
    assert why and "1872 to 2296 ms" in why
