"""Item 143 step BD, domain E: SPF, DMARC, DKIM, CAA, DNSSEC, dangling CNAME.

Read through the operator's own resolver (`crawler/dnsq.py`, the `dns` extra).
NXDOMAIN and NoAnswer are absence; a resolver that did not answer is not
assessed - never a finding (question channel 2026-09-14). No live DNS here: the
one query seam is replaced.
"""

from __future__ import annotations

from clauditseo.crawler import dnsq
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Severity, Tier
from clauditseo.modules import sec

APEX = "x.test"


def _q(name, rtype, status=dnsq.OK, records=(), ad=False, **extra):
    return {"name": name, "type": rtype, "status": status, "records": list(records), "ad": ad, **extra}


def _ev(*queries):
    return {"available": True, "apex": APEX, "queries": list(queries), "at": "2026-09-14T00:00:00Z"}


def _healthy():
    return [
        _q(APEX, "TXT", records=['"v=spf1 include:_spf.google.com ~all"']),
        _q(f"_dmarc.{APEX}", "TXT", records=['"v=DMARC1; p=quarantine; rua=mailto:d@x.test"']),
        _q(APEX, "CAA", records=['0 issue "letsencrypt.org"']),
        _q(APEX, "DNSKEY", records=["257 3 13 abc"], ad=True),
        _q(f"google._domainkey.{APEX}", "TXT", records=['"v=DKIM1; k=rsa; p=MIIB"']),
        *[_q(f"{s}._domainkey.{APEX}", "TXT", dnsq.NXDOMAIN) for s in dnsq.DKIM_SELECTORS if s != "google"],
    ]


def _findings(dns_ev):
    page = Page(url=f"https://{APEX}/", requested_url=f"https://{APEX}/", status=200,
                headers={}, content="", content_type="text/html")
    crawl = CrawlResult(start_url=f"https://{APEX}/", tier=Tier.T2, pages=[page])
    crawl.dns = dns_ev
    return {f.check_id: f for f in sec.SecurityModule().run([], Tier.T2, {"crawl": crawl})
            if f.check_id in sec.DNS_CHECKS}


def test_a_well_configured_domain_raises_nothing():
    rows, skipped = sec.dns_verdicts(_ev(*_healthy()))
    assert rows == [] and skipped == {}


def test_absence_on_an_answer_is_the_finding():
    got = _findings(_ev(_q(APEX, "TXT", dnsq.NOANSWER), _q(f"_dmarc.{APEX}", "TXT", dnsq.NXDOMAIN),
                        _q(APEX, "CAA", dnsq.NOANSWER), _q(APEX, "DNSKEY", dnsq.NOANSWER),
                        *[_q(f"{s}._domainkey.{APEX}", "TXT", dnsq.NXDOMAIN) for s in dnsq.DKIM_SELECTORS]))
    assert set(got) == {"spf", "dmarc", "caa", "dnssec", "dkim"}
    assert got["spf"].severity is Severity.HIGH and got["dmarc"].severity is Severity.HIGH
    # DKIM is worded as a limit of the guess list, never "DKIM absent".
    assert "among the common names tried" in got["dkim"].summary
    assert all(s in got["dkim"].summary for s in dnsq.DKIM_SELECTORS)


def test_a_resolver_that_did_not_answer_is_not_assessed_not_a_finding():
    rows, skipped = sec.dns_verdicts(_ev(
        _q(APEX, "TXT", dnsq.NOANSWER_SERVER), _q(f"_dmarc.{APEX}", "TXT", dnsq.NOANSWER_SERVER),
        _q(APEX, "CAA", dnsq.ERROR), _q(APEX, "DNSKEY", dnsq.NOANSWER_SERVER)))
    assert rows == []
    assert {"spf", "dmarc", "caa", "dnssec", "dkim"} <= set(skipped)
    assert all("did not answer" in r for r in skipped.values())


def test_spf_defects_and_dmarc_that_only_monitors():
    rows, _ = sec.dns_verdicts(_ev(_q(APEX, "TXT", records=['"v=spf1 +all"']),
                                   _q(f"_dmarc.{APEX}", "TXT", records=['"v=DMARC1; p=none"'])))
    by = {r["check"]: r for r in rows}
    assert "+all" in by["spf"]["summary"]
    assert "p=none" in by["dmarc"]["summary"] and "no rua" in by["dmarc"]["summary"]
    rows, _ = sec.dns_verdicts(_ev(_q(APEX, "TXT", records=['"v=spf1 -all"', '"v=spf1 ~all"'])))
    assert "2 SPF records" in {r["check"]: r for r in rows}["spf"]["summary"]


def test_a_cname_to_a_name_that_no_longer_exists_is_dangling_and_a_slow_one_is_not():
    got = _findings(_ev(*_healthy(),
                        _q(f"staging.{APEX}", "CNAME", records=["old-app.herokuapp.com."]),
                        _q("old-app.herokuapp.com", "A", dnsq.NXDOMAIN, cname_of=f"staging.{APEX}")))
    assert got["dangling-cname"].severity is Severity.CRITICAL
    assert got["dangling-cname"].evidence["dangling"] == [
        {"host": f"staging.{APEX}", "target": "old-app.herokuapp.com"}]
    rows, skipped = sec.dns_verdicts(_ev(*_healthy(),
                                         _q("slow.example", "A", dnsq.NOANSWER_SERVER, cname_of=f"dev.{APEX}")))
    assert not [r for r in rows if r["check"] == "dangling-cname"]
    assert "dangling-cname" in skipped


def test_without_the_extra_every_dns_check_says_why():
    rows, skipped = sec.dns_verdicts({"available": False, "reason": "dnspython is not installed - install clauditseo[dns]"})
    assert rows == [] and set(skipped) == set(sec.DNS_CHECKS)
    assert all("clauditseo[dns]" in r for r in skipped.values())
    rows, skipped = sec.dns_verdicts(None)
    assert set(skipped) == set(sec.DNS_CHECKS)


def test_collect_records_the_missing_extra_rather_than_looking_like_it_never_asked(monkeypatch):
    monkeypatch.setattr(dnsq, "available", lambda: False)
    out = dnsq.collect(APEX)
    assert out == {"available": False, "reason": "dnspython is not installed - install clauditseo[dns]"}


def test_collect_asks_the_fixed_lists_through_the_one_seam(monkeypatch):
    asked = []

    def fake(name, rtype):
        asked.append((name, rtype))
        if rtype == "CNAME" and name.startswith("www."):
            return _q(name, rtype, records=[f"{APEX}."])
        return _q(name, rtype, dnsq.NXDOMAIN)

    monkeypatch.setattr(dnsq, "available", lambda: True)
    monkeypatch.setattr(dnsq, "is_public_name", lambda n: True)
    monkeypatch.setattr(dnsq, "query", fake)
    out = dnsq.collect(APEX)
    assert out["available"] and (APEX, "TXT") in asked and (f"_dmarc.{APEX}", "TXT") in asked
    assert sum(1 for n, t in asked if t == "CNAME") == len(dnsq.CNAME_HOSTS)
    assert (APEX, "A") in asked          # the www CNAME's target was resolved
    assert not any(t == "AXFR" for _, t in asked)


def test_dns_evidence_reaches_the_brief_and_the_not_assessed_reasons():
    from clauditseo.analysts.expert import _dns_block
    block = _dns_block(_ev(*_healthy()))
    assert "operator's own resolver" in block and "_dmarc.x.test" in block
    assert "not installed" in _dns_block({"available": False, "reason": "dnspython is not installed"})
    import inspect

    from clauditseo.persistence import runs
    assert "dns_skipped" in inspect.getsource(runs.not_assessed_payload)


def test_a_long_txt_record_split_into_strings_is_read_whole():
    rows, _ = sec.dns_verdicts(_ev(_q(APEX, "TXT", records=['"v=spf1 include:a.test" " +all"'])))
    assert "+all" in {r["check"]: r for r in rows}["spf"]["summary"]


def test_a_reserved_or_local_name_is_asked_nothing(monkeypatch):
    monkeypatch.setattr(dnsq, "available", lambda: True)
    monkeypatch.setattr(dnsq, "query", lambda *a: (_ for _ in ()).throw(AssertionError("asked")))
    for name in ("127.0.0.1", "fixture.test", "localhost", "intranet.local", "x.example"):
        out = dnsq.collect(name)
        assert out["available"] is False and "not a public DNS name" in out["reason"], name
    assert dnsq.is_public_name("twenty22.co") and dnsq.is_public_name("acme.com.au")
