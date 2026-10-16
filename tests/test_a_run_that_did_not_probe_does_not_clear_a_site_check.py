"""A run that got no answer from a site-level instrument does not clear the
checks that instrument answers.

Screen audits round 4, Security AC-01 and AI surface AC-01 (High): "13 open, 5
of them back after a fix" and four firewall blocks "back after a fix", when
nothing was fixed. A T1 page scan (25 Sept) ran no DNS lookups, no well-known
path sweep and no crawler access test; its silence cleared dmarc, caa, dnssec,
security-txt and four `edge-blocks-ai-ua` rows, and the next full sweep raised
them again as regressed. And `cms-user-enumeration` went fixed on 2 Oct
because its own probe timed out.
"""
from __future__ import annotations

from clauditseo.persistence.runs import Reading, instruments_of, measured

FULL = {"dns": {"available": True, "queries": [{"name": "gate-six.test", "type": "TXT"}]},
        "well_known": {"fetched": [{"path": "/.env", "status": 404, "purpose": "exposed-file"},
                                   {"path": "/wp-json/wp/v2/users", "status": None,
                                    "purpose": "cms-user-enumeration",
                                    "error": "ReadTimeout: The read operation timed out"}]},
        "ua_matrix": [{"agent": "GPTBot"}]}


def _reading(instruments, failed=frozenset(), site=True):
    return Reading("r", frozenset({"SEC", "AIS"}), frozenset({"/"}), frozenset(), frozenset(),
                   site, frozenset(), frozenset(instruments), frozenset(failed))


def test_the_evidence_says_which_instruments_answered():
    have, failed = instruments_of(FULL["dns"], FULL["well_known"], FULL["ua_matrix"])
    assert have == {"dns", "well_known", "ua_matrix"}
    assert failed == {"cms-user-enumeration"}
    assert instruments_of(None, None, []) == (set(), set())
    assert instruments_of({"available": False, "reason": "no resolver"}, None, None)[0] == set()


def test_a_page_scan_with_no_probes_measures_none_of_their_checks():
    scan = _reading(set())
    for dim, check in (("SEC", "dmarc"), ("SEC", "caa"), ("SEC", "dnssec"),
                       ("SEC", "security-txt"), ("AIS", "edge-blocks-ai-ua")):
        state, why = measured(scan, dim, check, ["https://gate-six.test/"])
        assert state == "unmeasured", (check, state)
        assert "instrument" in why


def test_an_errored_probe_does_not_clear_its_check():
    have, failed = instruments_of(FULL["dns"], FULL["well_known"], FULL["ua_matrix"])
    state, why = measured(_reading(have, failed), "SEC", "cms-user-enumeration",
                          ["https://gate-six.test/"])
    assert state == "unmeasured" and "probe errored" in why


def test_a_run_with_the_instrument_still_clears():
    have, _ = instruments_of(FULL["dns"], FULL["well_known"], FULL["ua_matrix"])
    assert measured(_reading(have), "SEC", "dmarc", ["https://gate-six.test/"])[0] == "clean"
    # And a reading that does not know its instruments is not asked.
    unknown = Reading("r", frozenset({"SEC"}), frozenset({"/"}), frozenset(), frozenset(), True)
    assert measured(unknown, "SEC", "dmarc", ["https://gate-six.test/"])[0] == "clean"


def test_a_run_that_did_not_render_a_page_does_not_clear_its_rendered_checks():
    # Round 4 replay: axe-color-contrast and links-behind-js on /seo/technical/
    # went fixed on a run whose rendered pass sampled other pages.
    from clauditseo.persistence.runs import _rendered_paths
    rendered = _rendered_paths([{"text_blocks": {"https://gate-six.test/a/": []}}])
    assert rendered == frozenset({"/a/"})
    r = Reading("r", frozenset({"A11Y", "TEC"}), frozenset({"/a/", "/b/"}), frozenset(), frozenset(),
                True, rendered=rendered)
    assert measured(r, "A11Y", "axe-color-contrast", ["https://gate-six.test/b/"])[0] == "unmeasured"
    assert measured(r, "TEC", "links-behind-js", ["https://gate-six.test/b/"])[0] == "unmeasured"
    assert measured(r, "A11Y", "axe-color-contrast", ["https://gate-six.test/a/"])[0] == "clean"
    assert _rendered_paths([{"other": 1}]) is None


def test_a_run_whose_http_probe_and_certificate_went_unread_does_not_clear_them():
    # Round 4 replay: a crawl with 22 fetch errors got no answer from
    # http:// and read no certificate, and cleared http-redirect and cert-san.
    have, _ = instruments_of(None, None, None, {"http_redirects_to_https": None,
                                                "cert_subject_alt_names": []})
    assert "http_probe" not in have and "certificate" not in have
    r = _reading(have)
    assert measured(r, "SEC", "http-redirect", [])[0] == "unmeasured"
    assert measured(r, "SEC", "cert-san", [])[0] == "unmeasured"
    ok, _ = instruments_of(None, None, None, {"http_redirects_to_https": True,
                                              "cert_subject_alt_names": ["gate-six.test"]})
    assert {"http_probe", "certificate"} <= ok


def test_the_rendered_tec_checks_need_the_render():
    from clauditseo.persistence.runs import _render_derived
    for check in ("links-behind-js", "render-only", "scripts-blocked-by-csp", "page-script-error"):
        assert _render_derived("TEC", check), check
    assert _render_derived("A11Y", "axe-color-contrast")
    assert not _render_derived("A11Y", "axe-sampled") and not _render_derived("TEC", "title-missing")
