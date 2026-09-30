"""A configured provider that refuses is not an absent provider.

Both branches of the hub's error handling did the same thing — `continue` —
so "no key configured" and "the key was rejected with a 403" arrived
downstream identical. The audit then told the operator "No backlink data
provider is configured" for a site where one WAS configured and answering 403,
while Admin showed the same provider green because a key string existed.

Two confident messages, neither of them the truth, and the actual state — a
present key being refused — was the one thing neither could express.
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.providers.base import NotConfigured, ProviderHub


class _Refusing:
    name = "openpagerank"

    def snapshot(self, domain):                      # noqa: ARG002
        request = httpx.Request("GET", "https://openpagerank.test/api")
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("Client error '403 Forbidden'",
                                    request=request, response=response)


class _Absent:
    name = "moz"

    def snapshot(self, domain):                      # noqa: ARG002
        raise NotConfigured("no token")


class _Working:
    name = "crux"

    def metrics(self, url):                          # noqa: ARG002
        return {"lcp_ms": 1200}


class _Broken:
    name = "pagespeed"

    def metrics(self, url):                          # noqa: ARG002
        raise RuntimeError("upstream timed out")


def test_a_refusal_is_recorded_with_its_status():
    hub = ProviderHub(backlink_providers=[_Refusing()])
    hub.backlink_snapshot("example.com")
    assert "openpagerank" in hub.failures
    assert hub.failures["openpagerank"]["status"] == 403
    assert "403" in hub.failure_note()


def test_an_unconfigured_provider_is_not_recorded_as_a_failure():
    """It was never asked. Counting it would turn a deliberate choice into an
    incident, which is the same conflation in the other direction."""
    hub = ProviderHub(backlink_providers=[_Absent()])
    hub.backlink_snapshot("example.com")
    assert hub.failures == {}
    assert hub.failure_note() == ""


def test_the_two_are_told_apart_when_both_are_present():
    hub = ProviderHub(backlink_providers=[_Absent(), _Refusing()])
    hub.backlink_snapshot("example.com")
    assert list(hub.failures) == ["openpagerank"]


def test_a_broken_provider_still_never_breaks_the_run():
    """The original behaviour that must survive: degrade, do not raise."""
    hub = ProviderHub(cwv_providers=[_Broken(), _Working()])
    assert hub.cwv_metrics("https://example.test/") == {"lcp_ms": 1200}
    assert "pagespeed" in hub.failures, "it degraded, but silently before"


def test_no_failures_means_everything_asked_replied():
    hub = ProviderHub(cwv_providers=[_Working()])
    hub.cwv_metrics("https://example.test/")
    assert hub.failures == {}


def test_the_finding_says_refusing_rather_than_not_configured():
    """The sentence that reached a client report. A provider answering 403 is
    configured, and telling the operator otherwise sends them looking for a
    setting that is already set."""
    from clauditseo.engine.types import Site, Tier
    from clauditseo.modules.ofp import OffPageModule

    hub = ProviderHub(backlink_providers=[_Refusing()])
    findings = OffPageModule().run(
        [], Tier.T2, {"site": Site(domain="example.test"), "providers": hub})
    note = next(f for f in findings if f.check_id == "backlinks-not-assessed")
    assert "answered with an error" in note.summary
    assert "openpagerank (403)" in note.summary
    assert "No backlink data provider is configured" not in note.summary
    assert note.evidence["providers_failing"][0]["status"] == 403
    assert "configured and refusing" in note.recommendation


def test_with_nothing_configured_the_old_sentence_is_still_right():
    """The message was only wrong when a provider WAS configured."""
    from clauditseo.engine.types import Site, Tier
    from clauditseo.modules.ofp import OffPageModule

    hub = ProviderHub(backlink_providers=[])
    findings = OffPageModule().run(
        [], Tier.T2, {"site": Site(domain="example.test"), "providers": hub})
    note = next(f for f in findings if f.check_id == "backlinks-not-assessed")
    assert "No backlink data provider is configured" in note.summary


# --- asked, and not asked, are different states -----------------------------

def _prf_unmeasured(tier, cwv_providers):
    """The cwv-not-assessed finding, at a given tier, with no CWV data back."""
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Site
    from clauditseo.modules.prf import PerformanceModule

    class _Silent(ProviderHub):
        def cwv_metrics(self, url):        # noqa: ARG002
            return None

    page = Page(url="https://x.test/", requested_url="https://x.test/",
                status=200, content_type="text/html",
                content="<html></html>", elapsed_ms=10.0, headers={})
    crawl = CrawlResult(start_url="https://x.test/", tier=tier, pages=[page])
    findings = PerformanceModule().run(
        [], tier, {"crawl": crawl, "site": Site(domain="x.test"),
                   "providers": _Silent(cwv_providers=cwv_providers)})
    return next(f for f in findings if f.check_id == "cwv-not-assessed")


def _client_line(finding):
    from clauditseo.reporting.render import _not_assessed_line

    return _not_assessed_line({"dimension": finding.dimension,
                               "summary": finding.summary,
                               "evidence": finding.evidence}, "client")


def test_a_tier_that_makes_no_calls_does_not_claim_the_sources_were_silent():
    """T1 makes no external calls by contract, and it is where `auto` and
    adaptive mode start. Deriving "answering" from what is *configured* rather
    than from what was *asked* put a definite claim about the client's own
    site — that the configured sources were consulted and report nothing — on
    a measurement that was never taken."""
    from clauditseo.engine.types import Tier

    note = _prf_unmeasured(Tier.T1, [_Working()])
    assert note.evidence["providers_answering"] == [], \
        "nothing was asked at this tier, so nothing answered"
    assert "this audit tier does not call external data sources" in _client_line(note)


def test_a_tier_that_does_call_still_says_the_sources_reported_nothing():
    """The other half: at T2 a configured provider WAS asked and returned no
    field data, and that is a true and different sentence."""
    from clauditseo.engine.types import Tier

    note = _prf_unmeasured(Tier.T2, [_Working()])
    assert note.evidence["providers_answering"] == ["crux"]
    assert "the sources configured for this site do not report it" in _client_line(note)


def test_neither_sentence_names_the_vendor():
    from clauditseo.engine.types import Tier

    for tier in (Tier.T1, Tier.T2):
        line = _client_line(_prf_unmeasured(tier, [_Working()]))
        assert "crux" not in line.lower() and "pagespeed" not in line.lower()


def test_a_crawl_that_fetched_nothing_neither_claims_a_fetch_nor_spends_a_call():
    """A page object survives a DNS failure, so counting pages counts attempts.

    Round 031 split `tier_calls_external` from `pages_fetched` and then built
    the second from `bool(crawl.pages)` — the same attempt count it was
    written to replace. On the operator's own blocked run `93bdd2b2` the
    stored evidence therefore reads `pages_fetched: True` for a crawl that
    fetched nothing, and the client is told the data source was unavailable
    rather than that there was no page to measure.

    The call gate has the same defect and costs money rather than accuracy:
    one DNS-failed page object is enough to send a keyed CWV request for a
    host that does not resolve.

    Driven through the module on purpose. Both values under test are ones the
    producer computes, and the round that introduced the defect asserted them
    over hand-written literals — which is why a green suite did not see it.
    """
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Site, Tier
    from clauditseo.modules.prf import PerformanceModule

    asked_for: list[str] = []

    class _Recording(ProviderHub):
        def cwv_metrics(self, url):
            asked_for.append(url)
            return None

    dead = Page(url="https://seed-blocked.test/",
                requested_url="https://seed-blocked.test/",
                status=0, content_type="", content="", elapsed_ms=0.0,
                headers={}, error="ConnectError: getaddrinfo failed")
    crawl = CrawlResult(start_url="https://seed-blocked.test/",
                        tier=Tier.T2, pages=[dead])
    findings = PerformanceModule().run(
        [], Tier.T2, {"crawl": crawl, "site": Site(domain="seed-blocked.test"),
                      "providers": _Recording(cwv_providers=[_Working()])})

    note = next(f for f in findings if f.check_id == "cwv-not-assessed")
    assert note.evidence["pages_fetched"] is False, \
        "a page object left by a DNS failure is an attempt, not a fetch"
    assert asked_for == [], \
        "a keyed provider call was spent on a host that did not resolve"


# --- the data we already pay for -------------------------------------------

def _prf(metrics):
    """Run the performance module over one page with these CWV metrics."""
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Site, Tier
    from clauditseo.modules.prf import PerformanceModule

    class _Hub(ProviderHub):
        def cwv_metrics(self, url):        # noqa: ARG002
            return metrics

    page = Page(url="https://x.test/", requested_url="https://x.test/",
                status=200, content_type="text/html",
                content="<html></html>", elapsed_ms=10.0,
                headers={"cache-control": "max-age=600"})
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[page])
    return PerformanceModule().run(
        [], Tier.T2, {"crawl": crawl, "site": Site(domain="x.test"),
                      "providers": _Hub()})


def _sv(value, source="crux", confidence="high"):
    from clauditseo.providers.base import SourcedValue
    return SourcedValue(value=value, source=source, confidence=confidence)


def test_inp_is_used_rather_than_fetched_and_discarded():
    """CrUX returned inp_ms on every audit and the module read only lcp_ms,
    so two thirds of what the API call paid for was dropped. INP replaced FID
    as a Core Web Vital in March 2024."""
    ids = {f.check_id for f in _prf({"inp_ms": _sv(640)})}
    assert "inp-poor" in ids


def test_cls_is_used_too():
    ids = {f.check_id for f in _prf({"cls": _sv(0.31)})}
    assert "cls-poor" in ids


def test_the_middle_band_is_reported_instead_of_passing_in_silence():
    """3663 ms LCP is not passing, and only "poor" spoke — so the audit's
    silence read as approval of a genuinely mediocre number."""
    found = _prf({"lcp_ms": _sv(3663)})
    lcp = next(f for f in found if f.check_id.startswith("lcp-"))
    assert lcp.check_id == "lcp-needs-improvement"
    assert lcp.severity.value == "low", "reported, not scored like a failure"
    assert "3663 ms" in lcp.summary


def test_a_good_number_still_says_nothing():
    """Narrowed to its own subject when F-01 landed, not weakened.

    It read `== []` because at the time a CWV band was the only thing this
    module could say about a fast, clean page. PRF now also states whether the
    page carries third-party scripts, and that statement is INFO, deducts
    nothing, and has nothing to do with whether a good number stayed quiet.
    Asserting on the band findings is what the name always claimed, and it is
    the stronger assertion: an empty list could be satisfied by the module
    failing to run at all.
    """
    found = _prf({"lcp_ms": _sv(1200), "inp_ms": _sv(90), "cls": _sv(0.02)})
    bands = [f for f in found
             if f.check_id.startswith(("lcp-", "inp-", "cls-"))]
    assert bands == []


def test_a_finding_says_whether_it_is_field_or_lab_data():
    """They are different measurements. On the operator's own site CrUX said
    3663 ms and PageSpeed said 14746 for the same page — four times apart —
    and the hub returns whichever answers first, so a page with no field data
    silently falls back to a lab number that reads far worse."""
    field = next(f for f in _prf({"lcp_ms": _sv(5000, "crux")}))
    lab = next(f for f in _prf({"lcp_ms": _sv(5000, "pagespeed", "medium")}))
    assert "field data from real users" in field.summary
    assert "a single lab run, not real-user data" in lab.summary
    assert field.evidence["source"] == "crux"
    assert lab.confidence.value == "medium", "lab data is not high confidence"


# --- a lab-only answer is not field data (answer 20260916-0140) -------------

class _Named:
    def __init__(self, name):
        self.name = name


def _prf_lab(metrics, cwv_providers=(), failures=None):
    """`_prf` with the hub's providers and failures set, returning the context
    too so the score can be read against the same page coverage."""
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Site, Tier
    from clauditseo.modules.prf import PerformanceModule

    class _Hub(ProviderHub):
        def cwv_metrics(self, url):        # noqa: ARG002
            return metrics

    hub = _Hub(cwv_providers=[_Named(n) for n in cwv_providers])
    hub.failures.update(failures or {})
    page = Page(url="https://x.test/", requested_url="https://x.test/",
                status=200, content_type="text/html",
                content="<html></html>", elapsed_ms=10.0,
                headers={"cache-control": "max-age=600"})
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[page])
    ctx = {"crawl": crawl, "site": Site(domain="x.test"), "providers": hub}
    return PerformanceModule().run([], Tier.T2, ctx), ctx


def test_a_lab_only_answer_is_not_field_coverage():
    """twenty22's `lcp-poor` came from PageSpeed on every run, and the sweep
    raised no `cwv-not-assessed`, so Speed credited the field share for one
    synthetic run while the brief and the field bar both said lab."""
    from clauditseo.engine import scoring
    from clauditseo.modules.prf import PerformanceModule

    findings, ctx = _prf_lab({"lcp_ms": _sv(4200, source="pagespeed", confidence="medium")})
    lcp = next(f for f in findings if f.check_id == "lcp-poor")
    assert lcp.evidence["source"] == "pagespeed"
    rows = [f for f in findings if f.check_id == "cwv-not-assessed"]
    assert len(rows) == 1
    assert rows[0].evidence["lab_source"] == "pagespeed"
    assert rows[0].evidence["lab_metrics"] == ["lcp_ms"]
    assert rows[0].scope_statement and rows[0].severity.value == "info"
    sub = PerformanceModule().score(findings, ctx)
    assert sub.coverage == pytest.approx(
        (1.0 - PerformanceModule.FIELD_SHARE) * scoring.page_coverage(ctx))
    assert "Core Web Vitals field data" in sub.unmeasured


def test_a_field_answer_needs_no_scope_row():
    findings, _ = _prf_lab({"lcp_ms": _sv(4200)})
    assert not any(f.check_id == "cwv-not-assessed" for f in findings)


@pytest.mark.parametrize("providers, failures, reason", [
    (["pagespeed"], None, "no CrUX key is configured"),
    (["crux", "pagespeed"], {"crux": {"provider": "crux", "detail": "timed out"}},
     "CrUX was unavailable during this run"),
    (["crux", "pagespeed"], None, "CrUX holds no record for this URL"),
])
def test_lab_only_names_the_reason(providers, failures, reason):
    findings, _ = _prf_lab({"lcp_ms": _sv(4200, source="pagespeed", confidence="medium")},
                           providers, failures)
    row = next(f for f in findings if f.check_id == "cwv-not-assessed")
    assert row.summary == (f"Core Web Vitals field data not assessed: {reason}. "
                           "The vitals below are one PageSpeed lab run, not real-user data.")
    assert "API key" not in " ".join(row.evidence["needs"])


def test_every_band_boundary_falls_the_documented_way():
    """Google's bands are good at-or-under, poor strictly above."""
    from clauditseo.modules.prf import _band

    assert _band("lcp_ms", 2500) == "good"
    assert _band("lcp_ms", 2501) == "needs improvement"
    assert _band("lcp_ms", 4000) == "needs improvement"
    assert _band("lcp_ms", 4001) == "poor"
    assert _band("cls", 0.1) == "good" and _band("cls", 0.26) == "poor"
    assert _band("inp_ms", 200) == "good" and _band("inp_ms", 501) == "poor"


# --- the credential must not reach storage (round 034, CQ-59 / UX-11) -------

def test_a_failure_detail_carries_no_query_string(tmp_path):
    """A provider URL is a credential carrier, and the exception text is a
    verbatim copy of it.

    `httpx.HTTPStatusError` stringifies to include the full request URL, and
    the PageSpeed call carries `key=<39-char Google API key>`. That string went
    into `findings.evidence` unaltered and from there into every whole-database
    backup. Two rows on run `93bdd2b2` are the measured instance.
    """
    request = httpx.Request(
        "GET", "https://pagespeedonline.test/v5/run?url=https%3A%2F%2Fx.test"
               "&key=AIzaSyFAKEKEYFORTESTINGONLY1234567890abc&strategy=mobile")
    response = httpx.Response(400, request=request)
    exc = httpx.HTTPStatusError("Client error '400 Bad Request' for url "
                                f"'{request.url}'",
                                request=request, response=response)

    hub = ProviderHub()
    hub.note_failure(_Broken(), exc)
    detail = hub.failures["pagespeed"]["detail"]

    assert "AIzaSy" not in detail, f"the key survived into the record: {detail}"
    assert "key=" not in detail, f"a query string survived: {detail}"
    assert "pagespeedonline.test" in detail, (
        "the host must survive — which provider failed is the point of the "
        f"record: {detail}")


def test_backlinks_reports_only_its_own_providers_as_failing():
    """A PageSpeed failure made a *backlinks* finding assert that a provider
    exists and is refusing, when none is configured for backlinks.

    `prf.py` scopes `providers_failing` to its own CWV providers; `ofp.py` was
    byte-identical except that it did not. That asymmetry is how the CWV
    credential reached a backlinks row — the second of the two stored rows.
    """
    from clauditseo.engine.types import Site, Tier
    from clauditseo.modules.ofp import OffPageModule

    class _Hub(ProviderHub):
        def backlink_snapshot(self, domain):     # noqa: ARG002
            return None

    hub = _Hub(cwv_providers=[_Working()])
    hub.note_failure(_Broken(), RuntimeError("pagespeed exploded"))

    findings = OffPageModule().run([], Tier.T2, {"site": Site(domain="x.test"),
                                                 "providers": hub})
    note = next(f for f in findings if f.check_id == "backlinks-not-assessed")
    failing = [d.get("provider") for d in note.evidence["providers_failing"]]

    assert "pagespeed" not in failing, (
        "a CWV provider's failure is not a backlinks provider's failure: "
        f"{failing}")
