"""Item 143 step BD, first stage: Security & transport is its own dimension.

SEC registers the brief's 56 checks, emits the ones the crawl's evidence
already answers, and names the rest - planned or held - so that no stage of the
build reads a check it never measured as a pass (item 157).
"""

from __future__ import annotations

import re
from pathlib import Path

from clauditseo.crawler.types import CrawlResult, Page, TransportProbe
from clauditseo.engine.types import Tier
from clauditseo.modules import sec

BRIEF = Path("C:/Users/owner/Documents/AI/_relay/attachments/brief-v20/security.md")
ROOT = Path(__file__).resolve().parents[1]

GOOD_HEADERS = {
    "content-type": "text/html",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "content-security-policy": "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'self'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=()",
    "server": "cloudflare",
}


def _run(headers=None, html="<html><head></head><body>ok</body></html>", transport=None,
         start="https://x.test/", site=None):
    page = Page(url=start, requested_url=start, status=200,
                headers=dict(GOOD_HEADERS if headers is None else headers),
                content=html, content_type="text/html")
    crawl = CrawlResult(start_url=start, tier=Tier.T2, pages=[page])
    crawl.transport = transport
    return {f.check_id: f for f in sec.SecurityModule().run([], Tier.T2, {"crawl": crawl, "site": site})}


def _ids_in_brief() -> list[str]:
    if BRIEF.is_file():
        return re.findall(r"^  - SEC/([a-z0-9-]+)", BRIEF.read_text(encoding="utf-8"), re.M)
    return []


def test_every_brief_check_is_registered_once_and_accounted_for():
    ids = _ids_in_brief() or sorted(set(sec.DEFAULT_SEVERITY) | sec.BRIEF_ONLY_CHECKS)
    assert len(ids) == 56
    free = set(sec.DEFAULT_SEVERITY)
    assert set(ids) == free | sec.BRIEF_ONLY_CHECKS
    assert not free & sec.BRIEF_ONLY_CHECKS
    # A planned check is a free check without its collector, never a new id.
    assert set(sec.NOT_YET_COLLECTED) <= free
    from clauditseo.anatomy import CHECK_CATEGORY, DIMENSION_CATEGORIES
    assert all(CHECK_CATEGORY[i] == "security" for i in ids)
    assert DIMENSION_CATEGORIES["SEC"] == ("security",)
    assert "security" not in DIMENSION_CATEGORIES["TEC"]


def test_the_weight_came_out_of_tec_and_the_total_did_not_move():
    from clauditseo.engine.scoring import DEFAULT_WEIGHTS
    assert DEFAULT_WEIGHTS["SEC"] == 0.04 and DEFAULT_WEIGHTS["TEC"] == 0.18


def test_the_old_tec_checks_are_gone_and_purged():
    from clauditseo.modules import tec
    assert "not-https" not in tec.DEFAULT_SEVERITY and "security-headers" not in tec.DEFAULT_SEVERITY
    src = (ROOT / "clauditseo" / "modules" / "tec.py").read_text(encoding="utf-8")
    assert 'check_id="not-https"' not in src and 'check_id="security-headers"' not in src
    mig = (ROOT / "clauditseo" / "db" / "migrations" / "0056_security_becomes_a_dimension.sql").read_text(encoding="utf-8")
    assert "DELETE FROM findings" in mig and "'not-https', 'security-headers'" in mig


def test_a_well_configured_home_page_raises_nothing_from_its_headers():
    got = _run()
    for check in ("hsts", "csp-absent", "csp-weak", "xcto", "referrer-policy",
                  "permissions-policy", "frame-ancestors", "version-banner",
                  "cookie-flags", "deprecated-header"):
        assert check not in got, (check, got[check].summary if check in got else "")


def test_each_missing_or_weak_header_raises_its_own_row():
    got = _run(headers={"content-type": "text/html",
                        "strict-transport-security": "max-age=300",
                        "content-security-policy-report-only": "default-src *",
                        "referrer-policy": "unsafe-url",
                        "x-xss-protection": "1; mode=block",
                        "server": "Apache/2.4.41",
                        "set-cookie": "sid=abc; Path=/\npref=1; Secure; HttpOnly; SameSite=Lax"})
    assert "max-age 300" in got["hsts"].summary
    assert got["csp-weak"].evidence["report_only"] is True
    assert "xcto" in got and "permissions-policy" in got and "frame-ancestors" in got
    assert "unsafe-url" in got["referrer-policy"].summary
    assert got["deprecated-header"].evidence["present"] == {"x-xss-protection": "1; mode=block"}
    assert got["version-banner"].evidence["banners"] == {"server": "Apache/2.4.41"}
    # Two cookies, one line each: only the one missing flags is named.
    assert got["cookie-flags"].evidence["cookies"] == [
        {"cookie": "sid", "missing": ["Secure", "HttpOnly", "SameSite"]}]
    assert "cache-authenticated" in got


def test_a_vendor_name_without_a_version_is_not_a_banner():
    assert "version-banner" not in _run()          # Server: cloudflare


def test_transport_rows_read_the_probe_and_say_nothing_without_one():
    assert not {"tls-legacy", "cert-chain", "cert-san", "http-redirect"} & set(_run(transport=None))
    probe = TransportProbe(host="x.test", tls_floor="TLSv1_1", tls_floor_certain=True,
                           cert_not_after="Jan  1 00:00:00 2020 GMT",
                           cert_subject_alt_names=["x.test"],
                           http_redirects_to_https=False)
    got = _run(transport=probe)
    assert "TLS.1.1" in got["tls-legacy"].summary.replace(" ", ".") or "TLSv1.1" in got["tls-legacy"].summary
    assert "expires in 0 day" in got["cert-chain"].summary
    assert got["cert-san"].evidence["uncovered"] == ["www.x.test"]
    assert "not redirected" in got["http-redirect"].summary
    # An uncertain floor is not a finding: the probe could not ask below it.
    probe.tls_floor_certain = False
    assert "tls-legacy" not in _run(transport=probe)


def test_page_rows_read_the_html():
    html = ('<html><head><meta name="generator" content="WordPress 6.4.2">'
            '<script src="http://x.test/old.js"></script>'
            '<script src="https://cdn.vendor.test/lib.js"></script>'
            '<link rel="stylesheet" href="https://x.test/wp-content/themes/astra/style.css?ver=4.1.0">'
            '</head><body><form action="https://collect.elsewhere.test/pay"></form>'
            '<!-- deploy to staging.x-test.com.au before friday -->'
            '<!-- header section --></body></html>')
    got = _run(html=html)
    assert got["mixed-content"].evidence["insecure"] == ["http://x.test/old.js"]
    # One site row per resource set, counting the pages that load each.
    assert got["sri-missing"].subject == "site"
    assert got["sri-missing"].evidence["resources"] == {"https://cdn.vendor.test/lib.js": 1}
    assert got["cross-origin-form"].evidence["actions"] == ["https://collect.elsewhere.test/pay"]
    assert got["html-comment-leak"].evidence["comments"] == ["deploy to staging.x-test.com.au before friday"]
    assert got["cms-fingerprint"].evidence["generator"] == ["WordPress 6.4.2"]
    assert got["cms-fingerprint"].evidence["components"] == {"astra": "4.1.0"}


def test_a_same_site_form_and_a_first_party_script_are_not_findings():
    html = ('<html><body><script src="/app.js"></script>'
            '<form action="/search"></form><form action="https://www.x.test/c"></form></body></html>')
    got = _run(html=html)
    assert "cross-origin-form" not in got and "sri-missing" not in got


def test_planned_and_held_checks_read_not_assessed_with_their_reason():
    from clauditseo.persistence import runs
    src = (ROOT / "clauditseo" / "persistence" / "runs.py").read_text(encoding="utf-8")
    assert 'f"held: {_sec_held[bare]}"' in src and 'f"not collected yet: {_sec_planned[bare]}"' in src
    assert runs.not_assessed_payload  # the reader the clause above is in
    assert sec.HELD["open-ports"].startswith("pending authorisation")


def test_a_prompt_cannot_claim_a_planned_check_as_free():
    from clauditseo.checks import sweep_checks
    emitted = sweep_checks()
    assert not set(sec.NOT_YET_COLLECTED) & emitted
    assert {"hsts", "cookie-flags", "mixed-content"} <= emitted


def test_nothing_in_the_module_performs_an_active_probe():
    """Passive only: the module reads the crawl. It opens no socket and makes
    no request of its own."""
    src = (ROOT / "clauditseo" / "modules" / "sec.py").read_text(encoding="utf-8")
    for forbidden in ("import socket", "import httpx", "requests.", "urlopen", "subprocess"):
        assert forbidden not in src, forbidden


def test_cors_allows_any_origin_with_credentials_is_the_finding_and_star_alone_is_not():
    star = dict(GOOD_HEADERS, **{"access-control-allow-origin": "*"})
    assert "cors-permissive" not in _run(headers=star)
    both = dict(star, **{"access-control-allow-credentials": "true"})
    got = _run(headers=both)
    assert got["cors-permissive"].evidence["access_control_allow_credentials"] == "true"
    from clauditseo.crawler.evidence import HEADER_KEEP
    assert "access-control-allow-credentials" in HEADER_KEEP


def test_isolation_headers_are_owed_by_an_application_site_only():
    from clauditseo.engine.types import Site
    assert "cross-origin-policies" not in _run(site=Site(domain="x.test", business_type="local-service"))
    assert "cross-origin-policies" not in _run(site=None)
    got = _run(site=Site(domain="x.test", business_type="saas"))
    assert got["cross-origin-policies"].evidence["missing"] == [
        "cross-origin-opener-policy", "cross-origin-embedder-policy", "cross-origin-resource-policy"]


def test_the_script_inventory_reports_only_what_nothing_explains():
    from clauditseo.engine.types import Site
    html = ('<html><head><script src="/app.js"></script>'
            '<script src="https://cdn.x.test/lib.js"></script>'
            '<script src="https://www.googletagmanager.com/gtm.js"></script>'
            '<script src="https://evil-cdn.example/x.js"></script></head>'
            '<body><iframe src="https://widgets.partner.example/w"></iframe></body></html>')
    got = _run(html=html)["script-inventory"]
    assert set(got.evidence["unexplained"]) == {"evil-cdn.example", "widgets.partner.example"}
    assert got.evidence["classified"]["cdn.x.test"] == "first-party"
    assert got.evidence["classified"]["www.googletagmanager.com"] == "known vendor"
    site = Site(domain="x.test", third_party_map={"widgets.partner.example": {"purpose": "booking"}})
    mapped = _run(html=html, site=site)["script-inventory"]
    assert set(mapped.evidence["unexplained"]) == {"evil-cdn.example"}
    assert "script-inventory" not in _run(html='<script src="/a.js"></script>')


def test_obfuscation_needs_a_decoder_beside_a_blob_and_eval_alone_is_not_one():
    blob = "QUJD" * 150
    bad = f'<html><body><script>eval(atob("{blob}"))</script></body></html>'
    got = _run(html=bad)["obfuscated-js"]
    assert got.evidence["signals"] == {"decode/execute beside an encoded blob": 1}
    names = " ".join(f"var _0x{i:04x}=1;" for i in range(12))
    assert "obfuscated-js" in _run(html=f"<script>{names}</script>")
    # Ordinary code, a blob with no decoder, and a JSON-LD data block are not findings.
    assert "obfuscated-js" not in _run(html='<script>eval("1+1"); var t = atob("aGk=");</script>')
    assert "obfuscated-js" not in _run(html=f'<script>var img = "{blob}";</script>')
    assert "obfuscated-js" not in _run(
        html=f'<script type="application/ld+json">{{"a": "eval(atob(\\"{blob}\\"))"}}</script>')


def test_hidden_link_spam_needs_three_unrelated_domains_behind_a_hiding_style():
    spam = ('<html><body><p>ok</p><div style="position:absolute; left:-9999px">'
            '<div><a href="https://pills.example/a">a</a></div>'
            '<a href="https://casino.example/b">b</a><a href="https://loans.example/c">c</a>'
            '</div></body></html>')
    got = _run(html=spam)["hidden-content"]
    assert set(got.evidence["domains"]) == {"pills.example", "casino.example", "loans.example"}
    menu = ('<nav style="display:none"><a href="https://x.test/a">a</a>'
            '<a href="https://www.facebook.com/x">f</a><a href="https://instagram.com/x">i</a>'
            '<a href="https://linkedin.com/x">l</a></nav>')
    assert "hidden-content" not in _run(html=menu)
    visible = spam.replace(' style="position:absolute; left:-9999px"', "")
    assert "hidden-content" not in _run(html=visible)
    # The block ends at its own close tag: links after it do not count.
    after = ('<div style="display:none"><a href="https://one.example/">1</a></div>'
             '<a href="https://two.example/">2</a><a href="https://three.example/">3</a>')
    assert "hidden-content" not in _run(html=after)


def _cloak_run(bot_html, own_html):
    from clauditseo.crawler.ua_matrix import fingerprint
    from clauditseo.crawler.types import CrawlResult, Page
    url = "https://x.test/"
    crawl = CrawlResult(start_url=url, tier=Tier.T2)
    crawl.pages = [Page(url=url, requested_url=url, status=200, content_type="text/html",
                        headers=dict(GOOD_HEADERS), content=own_html)]
    crawl.ua_matrix = [{"agent": "Googlebot", "robots": "allow", "home_status": 200,
                        "probe_status": [], "headers": {}, "error": None,
                        "bodies": {url: fingerprint(bot_html)}}]
    return {f.check_id: f for f in sec.SecurityModule()._cloaking(crawl)}


def test_cloaking_is_googlebot_shown_foreign_links_or_a_different_page():
    clean = "<html><title>Home</title><body>" + "Welcome " * 200 + "</body></html>"
    spam = clean.replace("</body>", '<a href="https://pills.example/">p</a>'
                                    '<a href="https://casino.example/">c</a></body>')
    got = _cloak_run(spam, clean)["cloaking"]
    assert got.evidence["pages"]["https://x.test/"]["links_only_googlebot_sees"] == [
        "casino.example", "pills.example"]
    swapped = "<html><title>Cheap pills</title><body>buy</body></html>"
    assert "cloaking" in _cloak_run(swapped, clean)
    # Rotating copy - same title, text within half - is not cloaking.
    assert _cloak_run(clean.replace("Welcome", "Hello"), clean) == {}
    assert "bodies" in __import__("dataclasses").asdict(
        __import__("clauditseo.crawler.ua_matrix", fromlist=["x"]).UAMatrixRow(agent="a", robots="allow"))


def test_a_run_without_googlebot_bodies_reads_cloaking_as_not_assessed():
    import inspect

    from clauditseo.persistence import runs
    from clauditseo.crawler.types import CrawlResult
    assert sec.SecurityModule()._cloaking(CrawlResult(start_url="https://x.test/", tier=Tier.T1)) == []
    assert "this run did not fetch pages as Googlebot" in inspect.getsource(runs.not_assessed_payload)


def test_the_stack_and_the_third_party_map_are_set_on_the_record(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, repo.ensure_default_operator(conn), "C"), "x.test")
    repo.update_site(conn, site_id, stack="nginx · Cloudflare · WordPress",
                     third_party_map={"plausible.io": "analytics"})
    from clauditseo.api.app import site_of
    site = site_of(repo.site_record(repo.get_site(conn, site_id)))
    assert site.stack == "nginx · Cloudflare · WordPress"
    assert site.third_party_map == {"plausible.io": "analytics"}
    from clauditseo.api.app import SitePatch
    assert {"stack", "third_party_map", "cdn_or_waf"} <= set(SitePatch.model_fields)


def _der(tag, content):
    n = len(content)
    head = bytes([n]) if n < 0x80 else bytes([0x80 | ((n.bit_length() + 7) // 8)]) + n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([tag]) + head + content


def _oid(dotted):
    a, b, *rest = map(int, dotted.split("."))
    out = bytearray([40 * a + b])
    for v in rest:
        chunk = [v & 0x7F]
        v >>= 7
        while v:
            chunk.append(0x80 | (v & 0x7F))
            v >>= 7
        out += bytes(reversed(chunk))
    return _der(0x06, bytes(out))


def _cert(key_oid, key_bits, sig_oid, curve=None):
    seq = lambda *xs: _der(0x30, b"".join(xs))  # noqa: E731
    if key_oid == "1.2.840.113549.1.1.1":
        modulus = _der(0x02, b"\x00" + (1 << (key_bits - 1)).to_bytes(key_bits // 8, "big"))
        bits = _der(0x03, b"\x00" + seq(modulus, _der(0x02, b"\x01\x00\x01")))
        alg = seq(_oid(key_oid), _der(0x05, b""))
    else:
        bits = _der(0x03, b"\x00\x04" + b"\x01" * 64)
        alg = seq(_oid(key_oid), _oid(curve))
    name = seq(_der(0x31, seq(_oid("2.5.4.3"), _der(0x0C, b"x.test"))))
    tbs = seq(_der(0xA0, _der(0x02, b"\x02")), _der(0x02, b"\x01"), seq(_oid(sig_oid)), name,
              seq(_der(0x17, b"260101000000Z"), _der(0x17, b"270101000000Z")), name, seq(alg, bits))
    return seq(tbs, seq(_oid(sig_oid)), _der(0x03, b"\x00\x01"))


def test_the_certificate_key_and_signature_are_read_from_the_der():
    from clauditseo.crawler.transport import cert_key
    assert cert_key(_cert("1.2.840.113549.1.1.1", 2048, "1.2.840.113549.1.1.11")) == (
        "rsa", 2048, "sha256WithRSAEncryption")
    assert cert_key(_cert("1.2.840.113549.1.1.1", 1024, "1.2.840.113549.1.1.5")) == (
        "rsa", 1024, "sha1WithRSAEncryption")
    assert cert_key(_cert("1.2.840.10045.2.1", 0, "1.2.840.10045.4.3.2", curve="1.2.840.10045.3.1.7")) == (
        "ec", 256, "ecdsa-with-SHA256")
    assert cert_key(b"\x30\x03\x02\x01") == (None, None, None)


def test_cert_key_and_http2_rows_read_the_probe():
    strong = TransportProbe(host="x.test", tls_version="TLSv1.3", alpn="h2", cert_key_type="ec",
                            cert_key_bits=256, cert_signature="ecdsa-with-SHA256")
    got = _run(transport=strong)
    assert "cert-key" not in got and "http2-absent" not in got
    weak = TransportProbe(host="x.test", tls_version="TLSv1.2", alpn="http/1.1", cert_key_type="rsa",
                          cert_key_bits=1024, cert_signature="sha1WithRSAEncryption")
    got = _run(transport=weak)
    assert "1024-bit RSA key and a sha1WithRSAEncryption signature" in got["cert-key"].summary
    assert got["http2-absent"].evidence["alpn"] == "http/1.1"
    # HTTP/3 advertised on the home response answers it.
    assert "http2-absent" not in _run(transport=weak, headers=dict(GOOD_HEADERS, **{"alt-svc": 'h3=":443"'}))


def test_a_run_from_before_a_check_was_collected_does_not_read_it_as_passing(tmp_path):
    import json

    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    site = repo.create_site(conn, repo.create_client(conn, repo.ensure_default_operator(conn), "C"), "x.test")
    ev = json.dumps({"start_url": "https://x.test/", "pages": [], "well_known": {"fetched": []}})
    for rid, version in (("old", "0.22.0"), ("mid", "0.23.0"), ("new", sec_version())):
        conn.execute("INSERT INTO audit_runs (id, site_id, dimensions, tier, status, engine_version,"
                     " crawl_evidence, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (rid, site, json.dumps(["SEC"]), "T2", "complete", version, ev,
                      "2026-09-14T00:00:00"))
    conn.commit()
    parts = {"security": ["SEC/script-inventory", "SEC/cert-key"]}
    old = runs.not_assessed_payload(conn, "old", checks_by_part=parts)["security"]
    assert "predates this check, first collected in 0.23.0" in old["SEC/script-inventory"]
    mid = runs.not_assessed_payload(conn, "mid", checks_by_part=parts).get("security", {})
    assert "SEC/script-inventory" not in mid and "first collected in 0.24.0" in mid["SEC/cert-key"]
    assert not runs.not_assessed_payload(conn, "new", checks_by_part=parts).get("security")


def sec_version():
    from clauditseo import ENGINE_VERSION
    return ENGINE_VERSION


def _consent_run(html, requests, facts=False):
    from clauditseo.crawler.types import CrawlResult, Page
    url = "https://x.test/"
    crawl = CrawlResult(start_url=url, tier=Tier.T2)
    crawl.pages = [Page(url=url, requested_url=url, status=200, content_type="text/html",
                        headers=dict(GOOD_HEADERS), content=html)]
    traces = {url: {"traced": True, "resources": [{"url": r, "start_ms": 100 + i}
                                                  for i, r in enumerate(requests)]}}
    if facts:
        return sec.consent_facts(crawl.pages, traces)
    return {f.check_id: f for f in sec.SecurityModule()._consent(crawl, traces)}


def test_trackers_before_consent_need_a_consent_tool_on_the_page():
    beacons = ["https://www.google-analytics.com/g/collect?v=2", "https://connect.facebook.net/en_US/fbevents.js",
               "https://www.googletagmanager.com/gtag/js?id=G-1", "https://plausible.io/js/script.js"]
    banner = '<script src="https://consent.cookiebot.com/uc.js"></script>'
    got = _consent_run(banner, beacons)["trackers-before-consent"]
    assert got.evidence["consent_tool"] == ["Cookiebot"]
    assert got.evidence["trackers"] == [
        {"host": "connect.facebook.net", "start_ms": 101, "pages": 1},
        {"host": "www.google-analytics.com", "start_ms": 100, "pages": 1}]
    # No consent tool: no row, and the facts say so for the brief (option A).
    assert _consent_run("<p>hi</p>", beacons) == {}
    facts = _consent_run("<p>hi</p>", beacons, facts=True)
    assert facts["consent_tool"] == [] and facts["cookieless_analytics"] == ["plausible.io"]
    assert set(facts["trackers_loaded"]) == {"www.google-analytics.com", "connect.facebook.net"}
    # Consent Mode denied by default excuses Google's tags; fbq revoke excuses Meta's.
    denied = banner + "<script>gtag('consent', 'default', {'analytics_storage': 'denied'});</script>"
    assert [t["host"] for t in _consent_run(denied, beacons)["trackers-before-consent"].evidence["trackers"]] == [
        "connect.facebook.net"]
    assert _consent_run(denied + "<script>fbq('consent', 'revoke'); fbq('init', '1');</script>", beacons) == {}
    assert sec.TRACE_DERIVED_CHECKS == {"trackers-before-consent"}


def test_the_brief_is_handed_the_consent_facts_with_a_default_market_marked():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "clauditseo" / "analysts" / "expert.py").read_text(encoding="utf-8")
    assert "(default) Australia, en-AU" in src and "consent_tool: " in src


def test_the_held_inputs_are_recorded_and_the_brief_is_told_nothing_acts_on_them(tmp_path):
    from clauditseo.analysts.expert import _security_context
    from clauditseo.api.app import site_of
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo
    import inspect
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, repo.ensure_default_operator(conn), "C"), "x.test")
    repo.update_site(conn, site_id, active_probing_authorised="true", reputation_source="search-console")
    site = site_of(repo.site_record(repo.get_site(conn, site_id)))
    assert site.active_probing_authorised == "true" and site.reputation_source == "search-console"
    src = inspect.getsource(_security_context)
    assert "nothing in this build performs an active probe either way" in src
    # No sweep or probe reads the authorisation: nothing under crawler/ or
    # modules/ takes it off a site (comments naming it are fine).
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "clauditseo"
    use = re.compile(r"""\.active_probing_authorised\b|["']active_probing_authorised["']""")
    readers = [p.relative_to(root).as_posix() for sub in ("crawler", "modules")
               for p in (root / sub).rglob("*.py") if use.search(p.read_text(encoding="utf-8"))]
    assert readers == [], readers
