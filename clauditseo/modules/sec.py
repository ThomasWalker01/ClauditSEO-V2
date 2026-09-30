"""SEC — Security & transport dimension (item 143, brief v20 step BD).

A dimension of its own rather than rows in TEC (question channel,
2026-09-13): security is a different collection pass by construction - a TLS
probe per hostname, a well-known path list once per site, public DNS records -
and a re-check of security should not re-run indexability, nor an indexability
re-check pay for a DNS sweep.

**Passive only.** Everything here reads what the crawl already fetched with
ordinary GETs: the pages' HTML and response headers, and the one TLS handshake
and plain-HTTP request `crawler.transport` makes per origin. No port scan, no
login attempt, no WAF probe, no zone transfer - ever. The checks that would
need one are registered so they can be held and named, never so they can run.

**Built in stages, and a stage never reads as a pass.** The brief registers 56
checks. This module emits the ones the crawl's existing evidence answers;
`NOT_YET_COLLECTED` names the free checks whose collector (the well-known path
list, the DNS lookups, the error-page fetch, the consent trace) is not built
yet, and `HELD` the ones that need an input or an authorisation the site does
not have. `runs.not_assessed_payload` reports both with their reason, by item
157's rule: absence of a finding is not a pass.
"""

from __future__ import annotations

import re
import ssl
import time
from urllib.parse import urljoin, urlsplit

from clauditseo import security_headers as sh
from clauditseo.crawler.types import CrawlResult
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier  # noqa: F401  (Severity re-exported for checks.py)

from .pagefacts import html_pages

#: The brief's registered defaults (security.md, "Severity"). A check with a
#: severity per status keeps one word here and the emit site picks the case.
DEFAULT_SEVERITY: dict[str, Severity] = {
    # A · transport
    "tls-legacy": Severity.HIGH, "cert-chain": Severity.HIGH,
    "cert-san": Severity.HIGH, "cert-key": Severity.HIGH,
    "http-redirect": Severity.HIGH, "mixed-content": Severity.HIGH,
    "http2-absent": Severity.LOW, "hsts": Severity.HIGH,
    # B · headers & cookies
    "csp-absent": Severity.MEDIUM, "csp-weak": Severity.MEDIUM,
    "xcto": Severity.MEDIUM, "referrer-policy": Severity.MEDIUM,
    "permissions-policy": Severity.LOW, "frame-ancestors": Severity.HIGH,
    # MEDIUM where it is raised at all: the module raises it for a SaaS site
    # only, where the brief says absence matters.
    "cross-origin-policies": Severity.MEDIUM, "cors-permissive": Severity.MEDIUM,
    "cookie-flags": Severity.MEDIUM, "cache-authenticated": Severity.MEDIUM,
    "deprecated-header": Severity.MEDIUM,
    # C · information disclosure
    "version-banner": Severity.MEDIUM, "cms-fingerprint": Severity.MEDIUM,
    "exposed-file": Severity.CRITICAL, "directory-listing": Severity.MEDIUM,
    "error-leak": Severity.HIGH, "html-comment-leak": Severity.MEDIUM,
    # D · CMS surface
    "cms-xmlrpc": Severity.MEDIUM, "cms-user-enumeration": Severity.HIGH,
    "cms-login-exposed": Severity.MEDIUM, "cms-registration-open": Severity.HIGH,
    "cms-file-editor": Severity.INFO, "cms-component-drift": Severity.MEDIUM,
    # E · DNS & mail
    "spf": Severity.HIGH, "dmarc": Severity.HIGH, "dkim": Severity.INFO,
    "caa": Severity.MEDIUM, "dnssec": Severity.INFO,
    "dangling-cname": Severity.CRITICAL,
    # F · page content & third-party code
    "script-inventory": Severity.MEDIUM, "obfuscated-js": Severity.CRITICAL,
    "hidden-content": Severity.MEDIUM, "cloaking": Severity.CRITICAL,
    "cross-origin-form": Severity.CRITICAL, "sri-missing": Severity.MEDIUM,
    "trackers-before-consent": Severity.MEDIUM,
    # I · operational
    "security-txt": Severity.LOW, "privacy-policy-match": Severity.MEDIUM,
}

#: The nine assessment domains, the layer of the request each lives at (143
#: addendum: E at DNS; A, B, H at the edge; C, D, I at the origin; F, G on the
#: page), and their checks. The part page's layer cards are drawn from this.
DOMAINS: dict[str, dict] = {
    "A": {"name": "Transport & certificate", "layer": "edge",
          "checks": ["tls-legacy", "cert-chain", "cert-san", "cert-key", "http-redirect",
                     "mixed-content", "http2-absent", "hsts"]},
    "B": {"name": "Headers & cookies", "layer": "edge",
          "checks": ["csp-absent", "csp-weak", "xcto", "referrer-policy", "permissions-policy",
                     "frame-ancestors", "cross-origin-policies", "cors-permissive",
                     "cookie-flags", "cache-authenticated", "deprecated-header"]},
    "C": {"name": "Information disclosure", "layer": "origin",
          "checks": ["version-banner", "cms-fingerprint", "exposed-file", "directory-listing",
                     "error-leak", "html-comment-leak"]},
    "D": {"name": "CMS surface", "layer": "origin",
          "checks": ["cms-xmlrpc", "cms-user-enumeration", "cms-login-exposed",
                     "cms-registration-open", "cms-file-editor", "cms-component-drift"]},
    "E": {"name": "DNS & mail", "layer": "dns",
          "checks": ["spf", "dmarc", "dkim", "caa", "dnssec", "dangling-cname"]},
    "F": {"name": "Page content & third parties", "layer": "page",
          "checks": ["script-inventory", "obfuscated-js", "hidden-content", "cloaking",
                     "cross-origin-form", "sri-missing", "trackers-before-consent"]},
    "G": {"name": "Reputation", "layer": "page", "checks": ["reputation"]},
    "H": {"name": "Infrastructure", "layer": "edge",
          "checks": ["open-ports", "origin-exposed", "admin-hostnames"]},
    "I": {"name": "Operational", "layer": "origin",
          "checks": ["security-txt", "privacy-policy-match"]},
}

#: The six analysis checks, which only `security.md` emits.
ANALYSIS_CHECKS = ("compromise-triage", "csp-policy", "header-deploy-risk",
                   "hsts-rollout", "cms-abandoned-plugins", "platform-limits")

#: Held by construction: G needs a reputation source, H needs
#: `active_probing_authorised`, and nothing in this build acts on the latter.
#: Each maps to the input that would release it, which is the reason the part
#: page states.
HELD: dict[str, str] = {
    "reputation": "needs a reputation source (Safe Browsing key or Search "
                  "Console) on the site record",
    "open-ports": "pending authorisation: needs active probing, which this "
                  "build never performs",
    "origin-exposed": "pending authorisation: needs active probing, which this "
                      "build never performs",
    "admin-hostnames": "pending authorisation: reachability needs active "
                       "probing, which this build never performs",
}

#: Brief-only in the registry's sense - no sweep raises them.
BRIEF_ONLY_CHECKS = frozenset(ANALYSIS_CHECKS) | frozenset(HELD)

#: The engine version each check was first collected in (item 143 step BD).
#: A run stored under an older engine never measured it, and the part page
#: must not read its silence as a pass - `not_assessed_payload` says so.
COLLECTED_SINCE: dict[str, str] = {
    **{c: "0.23.0" for c in ("cors-permissive", "cross-origin-policies", "script-inventory",
                             "obfuscated-js", "hidden-content", "cloaking")},
    **{c: "0.24.0" for c in ("http2-absent", "cert-key")},
    "trackers-before-consent": "0.25.0",
}

#: SEC's checks read from the performance trace, joined into the not-assessed
#: rung that says a run took no trace (item 143 step BD).
TRACE_DERIVED_CHECKS: frozenset[str] = frozenset({"trackers-before-consent"})

#: Hosts a tracking beacon is sent to (channel 20260914-1415). Beacons, not
#: loaders: Google Tag Manager's container may load before consent under
#: Consent Mode, so googletagmanager.com is not here.
TRACKER_HOSTS = (
    "google-analytics.com", "analytics.google.com", "doubleclick.net", "googleadservices.com",
    "facebook.net", "facebook.com", "clarity.ms", "hotjar.com", "hotjar.io", "ads.linkedin.com",
    "snap.licdn.com", "analytics.tiktok.com", "bat.bing.com", "ct.pinterest.com",
    "static.ads-twitter.com", "analytics.twitter.com", "taboola.com", "criteo.com", "criteo.net",
    "hs-analytics.net", "track.hubspot.com", "segment.io", "cdn.segment.com", "mixpanel.com",
)
#: Analytics that set no cookie and need no consent. Excluded before any
#: tracker match, so the exclusion is stated here rather than implied by a
#: host's absence from the list above.
COOKIELESS_ANALYTICS_HOSTS = ("plausible.io", "usefathom.com", "simpleanalytics.com",
                              "simpleanalyticscdn.com", "umami.is")
#: A consent tool on the page: its name, and what gives it away in the markup
#: or in a request URL. Google Consent Mode's default call counts as one.
CONSENT_TOOL_SIGNATURES: tuple[tuple[str, re.Pattern], ...] = tuple(
    (name, re.compile(pattern, re.I)) for name, pattern in (
        ("Cookiebot", r"cookiebot"), ("OneTrust", r"cookielaw\.org|onetrust"),
        ("CookieYes", r"cookieyes"), ("Complianz", r"complianz"), ("iubenda", r"iubenda"),
        ("Termly", r"termly\.io"), ("Usercentrics", r"usercentrics"), ("Osano", r"osano"),
        ("Didomi", r"didomi"), ("Cookie-Script", r"cookie-script\.com"),
        ("consentmanager", r"consentmanager"), ("CookieFirst", r"cookiefirst"),
        ("Borlabs Cookie", r"borlabs-cookie"),
        ("Google Consent Mode", r"gtag\(\s*['\"]consent['\"]\s*,\s*['\"]default['\"]"),
    ))
#: Google's tag hosts, which Consent Mode's "denied" default turns into
#: cookieless pings by design - not a bypass.
_GOOGLE_TAG_HOSTS = ("google-analytics.com", "analytics.google.com", "doubleclick.net",
                     "googleadservices.com", "googletagmanager.com")
_CONSENT_MODE_DENIED = re.compile(
    r"gtag\(\s*['\"]consent['\"]\s*,\s*['\"]default['\"]\s*,\s*\{[^}]*['\"]?(?:ad_storage|analytics_storage)"
    r"['\"]?\s*:\s*['\"]denied", re.I)
#: The Meta pixel's own consent hold, which precedes `fbq('init')` when used.
_META_REVOKE = re.compile(r"fbq\(\s*['\"]consent['\"]\s*,\s*['\"]revoke['\"]", re.I)
_META_HOSTS = ("facebook.net", "facebook.com")


def _under(host: str, names) -> bool:
    return any(host == n or host.endswith("." + n) for n in names)


def consent_facts(pages, traces: dict) -> dict:
    """What the traced pages show about consent, for the check and for the
    brief alike (item 143 step BD, channel 20260914-1415): the consent tools
    named, every tracker beacon requested with nothing clicked (earliest
    `start_ms` per host), the cookieless analytics seen, and - only where a
    consent tool is on the same page - the trackers that fired anyway, which
    is the check's finding. Consent Mode's denied default excuses Google's
    tags, and `fbq('consent','revoke')` the Meta pixel, on the page that
    carries them."""
    by_url = {getattr(p, "url", None): p for p in pages}
    tools: set[str] = set()
    loaded: dict[str, float | None] = {}
    cookieless: set[str] = set()
    bypassed: dict[str, dict] = {}
    traced = 0
    for url, trace in (traces or {}).items():
        if not isinstance(trace, dict) or trace.get("traced") is False:
            continue
        traced += 1
        page = by_url.get(url)
        html = (getattr(page, "content", "") if page else "") or ""
        resources = [r for r in (trace.get("resources") or []) if isinstance(r, dict)]
        urls = [str(r.get("url") or "") for r in resources]
        here = {name for name, sig in CONSENT_TOOL_SIGNATURES
                if sig.search(html) or any(sig.search(u) for u in urls)}
        tools |= here
        google_denied = bool(_CONSENT_MODE_DENIED.search(html))
        meta_revoked = bool(_META_REVOKE.search(html))
        for r in resources:
            host = _host(str(r.get("url") or ""))
            if _under(host, COOKIELESS_ANALYTICS_HOSTS):
                cookieless.add(host)
                continue
            if not _under(host, TRACKER_HOSTS):
                continue
            start = r.get("start_ms")
            start = start if isinstance(start, (int, float)) else None
            if host not in loaded or (start is not None and (loaded[host] is None or start < loaded[host])):
                loaded[host] = start
            if not here:
                continue
            if (google_denied and _under(host, _GOOGLE_TAG_HOSTS)) or (meta_revoked and _under(host, _META_HOSTS)):
                continue
            entry = bypassed.setdefault(host, {"pages": [], "start_ms": start})
            if url not in entry["pages"]:
                entry["pages"].append(url)
            if start is not None and (entry["start_ms"] is None or start < entry["start_ms"]):
                entry["start_ms"] = start
    return {"traced_pages": traced, "consent_tool": sorted(tools),
            "trackers_loaded": dict(sorted(loaded.items())),
            "cookieless_analytics": sorted(cookieless), "bypassed": dict(sorted(bypassed.items()))}


#: Free checks whose collector is not built yet, and what it is. Registered so
#: the part page lists them and says why they have no answer; removed from
#: here, one collector at a time, as each lands.
NOT_YET_COLLECTED: dict[str, str] = {
    "cms-file-editor": "only observable from inside the site; the analysis states it as unverified",
    "cms-component-drift": "needs a component version feed, not connected",
    "privacy-policy-match": "needs the tracker inventory and the policy text compared, not built yet",
}

#: The checks the well-known path sweep answers. A run whose evidence has no
#: sweep (a page refresh, a run without SEC, a run stored before it existed)
#: measured none of them, and `runs.not_assessed_payload` says so.
WELL_KNOWN_CHECKS = frozenset({
    "exposed-file", "directory-listing", "error-leak", "cms-xmlrpc",
    "cms-user-enumeration", "cms-login-exposed", "cms-registration-open",
    "security-txt"})

_DNS_FIX = {
    "spf": "Publish one SPF record listing the services that send mail, ending ~all or -all.",
    "dmarc": "Publish DMARC with rua= reporting, then move p=none to quarantine once reports are clean.",
    "dkim": "Confirm the mail provider's DKIM selector is published; if it is outside the list tried, say so.",
    "caa": "Publish CAA naming the certificate authorities the site uses.",
    "dnssec": "Enable DNSSEC at the registrar and DNS host.",
    "dangling-cname": "Remove each CNAME whose target no longer exists, before someone claims the target.",
}

#: The checks SEC's DNS lookups answer (`crawler/dnsq.py`).
DNS_CHECKS = frozenset({"spf", "dmarc", "dkim", "caa", "dnssec", "dangling-cname"})


def dns_verdicts(dns_ev: dict | None) -> tuple[list[dict], dict[str, str]]:
    """Domain E, read from the stored lookups: `(rows, not_assessed)`.

    One reader for both the module (which turns rows into findings) and
    `runs.not_assessed_payload` (which states the reasons), so the part page and
    the record cannot disagree about which DNS checks were measured. Each row is
    `{check, summary, evidence, severity?}`.

    NXDOMAIN and NoAnswer are absence; a resolver that did not answer leaves
    the check not assessed (question channel 2026-09-14)."""
    from clauditseo.crawler import dnsq

    if not dns_ev:
        return [], {c: "this run made no DNS lookups" for c in DNS_CHECKS}
    if not dns_ev.get("available"):
        reason = dns_ev.get("reason") or "no DNS resolver on this install"
        return [], {c: reason for c in DNS_CHECKS}
    qs = dns_ev.get("queries") or []
    apex = dns_ev.get("apex") or ""

    def one(name, rtype):
        return next((q for q in qs if q["name"] == name and q["type"] == rtype
                     and "cname_of" not in q), None)

    def unanswered(q):
        return q is None or q["status"] in (dnsq.NOANSWER_SERVER, dnsq.ERROR)

    rows: list[dict] = []
    skipped: dict[str, str] = {}
    silent = "the resolver did not answer"

    def text(record: str) -> str:
        # A TXT record over 255 bytes arrives as several quoted strings
        # ('"v=spf1 include:a" " include:b ~all"'); receivers join them.
        return record.replace('" "', "").strip('"')

    txt = one(apex, "TXT")
    if unanswered(txt):
        skipped["spf"] = silent
    else:
        spf = [text(r) for r in txt["records"] if text(r).lower().startswith("v=spf1")]
        if not spf:
            rows.append({"check": "spf", "summary": f"{apex} publishes no SPF record.",
                         "evidence": {"txt": txt["records"]}})
        elif len(spf) > 1:
            rows.append({"check": "spf", "summary": f"{apex} publishes {len(spf)} SPF records; "
                         "receivers treat more than one as an error.", "evidence": {"spf": spf}})
        else:
            record = " ".join(spf[0].split())
            lookups = sum(record.lower().count(m) for m in
                          ("include:", " a ", " a:", " mx", "ptr", "exists:", "redirect="))
            if "+all" in record.lower().split():
                rows.append({"check": "spf", "summary": f"{apex}'s SPF ends +all, which "
                             "authorises every server.", "evidence": {"spf": record}})
            elif lookups > 10:
                rows.append({"check": "spf", "summary": f"{apex}'s SPF names {lookups} lookup "
                             "mechanisms at its top level, past the limit of 10.",
                             "evidence": {"spf": record, "top_level_lookups": lookups}})

    dmarc = one(f"_dmarc.{apex}", "TXT")
    if unanswered(dmarc):
        skipped["dmarc"] = silent
    else:
        rec = next((text(r) for r in dmarc["records"]
                    if text(r).lower().startswith("v=dmarc1")), None)
        if rec is None:
            rows.append({"check": "dmarc", "summary": f"{apex} publishes no DMARC record.",
                         "evidence": {"status": dmarc["status"]}})
        else:
            tags = {k.strip().lower(): v.strip() for k, _, v in
                    (part.partition("=") for part in rec.split(";")) if k.strip()}
            gaps = (["p=none - monitoring, not enforcement"] if tags.get("p", "").lower() == "none" else []) + (
                ["no rua - nobody receives the reports"] if "rua" not in tags else [])
            if gaps:
                rows.append({"check": "dmarc", "summary": f"DMARC for {apex}: {'; '.join(gaps)}.",
                             "evidence": {"dmarc": rec}})

    dkim = [one(f"{sel}._domainkey.{apex}", "TXT") for sel in dnsq.DKIM_SELECTORS]
    if any(q and q["status"] == dnsq.OK and q["records"] for q in dkim):
        pass
    elif any(unanswered(q) for q in dkim):
        skipped["dkim"] = silent
    else:
        rows.append({"check": "dkim",
                     "summary": "No DKIM selector found among the common names tried: "
                                + ", ".join(dnsq.DKIM_SELECTORS)
                                + ". A selector outside this list would not be seen.",
                     "evidence": {"selectors_tried": list(dnsq.DKIM_SELECTORS)}})

    caa = one(apex, "CAA")
    if unanswered(caa):
        skipped["caa"] = silent
    elif caa["status"] in (dnsq.NXDOMAIN, dnsq.NOANSWER) or not caa["records"]:
        rows.append({"check": "caa", "summary": f"{apex} publishes no CAA record, so any "
                     "certificate authority may issue for it.", "evidence": {"status": caa["status"]}})

    key = one(apex, "DNSKEY")
    if unanswered(key):
        skipped["dnssec"] = silent
    elif key["status"] in (dnsq.NXDOMAIN, dnsq.NOANSWER) or not key["records"]:
        rows.append({"check": "dnssec", "summary": f"{apex} is not signed with DNSSEC.",
                     "evidence": {"status": key["status"]}})

    dangling, unresolved = [], []
    for q in qs:
        if "cname_of" not in q:
            continue
        if q["status"] == dnsq.NXDOMAIN:
            dangling.append({"host": q["cname_of"], "target": q["name"]})
        elif unanswered(q):
            unresolved.append(q["cname_of"])
    if dangling:
        rows.append({"check": "dangling-cname",
                     "summary": "CNAME(s) point at names that no longer exist: "
                                + ", ".join(f"{d['host']} -> {d['target']}" for d in dangling) + ".",
                     "evidence": {"dangling": dangling, "hosts_probed": list(dnsq.CNAME_HOSTS)}})
    elif unresolved:
        skipped["dangling-cname"] = f"the resolver did not answer for {', '.join(unresolved)}"
    return rows, skipped


#: Per exposed path: the signature that makes a 200 an exposure rather than
#: the site's own page, and whether it carries credentials or a copy of the
#: site (CRITICAL by the brief) or only reveals structure (MEDIUM).
_EXPOSED = {
    "/.git/HEAD": (lambda h: h.lstrip().startswith("ref:") or bool(re.fullmatch(r"[0-9a-f]{40}\s*", h)), True),
    "/.env": (lambda h: bool(re.search(r"^[A-Z][A-Z0-9_]*=", h, re.M)), True),
    "/.svn/entries": (lambda h: h[:3].strip().isdigit() or h.startswith("dir"), True),
    "/wp-config.php.bak": (lambda h: "DB_NAME" in h or "DB_PASSWORD" in h, True),
    "/wp-config.php.old": (lambda h: "DB_NAME" in h or "DB_PASSWORD" in h, True),
    "/wp-config.php.save": (lambda h: "DB_NAME" in h or "DB_PASSWORD" in h, True),
    "/phpinfo.php": (lambda h: "phpinfo()" in h or "PHP Version" in h, False),
    "/debug.log": (lambda h: bool(re.search(r"PHP (Warning|Notice|Fatal|Deprecated)|Stack trace", h)), False),
    "/wp-content/debug.log": (lambda h: bool(re.search(r"PHP (Warning|Notice|Fatal|Deprecated)|Stack trace", h)), False),
    "/error_log": (lambda h: bool(re.search(r"PHP (Warning|Notice|Fatal|Deprecated)|Stack trace", h)), False),
    "/backup.zip": (lambda h: h.startswith("PK"), True),
    "/backup.tar.gz": (lambda h: h.startswith("\x1f") or h.startswith("\ufffd\x08"), True),
    "/.DS_Store": (lambda h: "Bud1" in h, False),
    "/composer.json": (lambda h: h.lstrip().startswith("{") and '"require' in h, False),
    "/package.json": (lambda h: h.lstrip().startswith("{") and '"dependencies"' in h, False),
    "/.htpasswd": (lambda h: bool(re.search(r"^[^:\s<]+:\$?[A-Za-z0-9./$]{8,}", h, re.M)), True),
}
#: Signatures of a server error page that says too much.
_ERROR_LEAK = re.compile(
    r"Stack trace|Traceback \(most recent call last\)|Fatal error|SQLSTATE|"
    r" on line <b>\d+|(?:/var/www|/home/[a-z0-9_-]+/public_html|[A-Z]:\\inetpub)", re.I)

#: HSTS max-age the brief asks for (one year), and the cut below which a
#: certificate's expiry is a finding.
HSTS_FULL_AGE = 31_536_000
CERT_EXPIRY_DAYS = 14

_MAX_AGE = re.compile(r"max-age\s*=\s*(\d+)", re.I)
_VERSIONED = re.compile(r"\d+\.\d+")
_GENERATOR = re.compile(r"<meta[^>]+name=[\"']generator[\"'][^>]*content=[\"']([^\"']+)", re.I)
_ASSET_VER = re.compile(r"/wp-content/(?:plugins|themes)/([a-z0-9_-]+)/[^\"'?]*\?ver=([0-9.]+)", re.I)
_INSECURE_SUB = re.compile(
    r"<(script|img|iframe|audio|video|source|embed)\b[^>]*\bsrc=[\"'](http://[^\"']+)"
    r"|<link\b(?=[^>]*\brel=[\"']?stylesheet)[^>]*\bhref=[\"'](http://[^\"']+)", re.I)
_SCRIPT = re.compile(r"<script\b([^>]*)>", re.I)
_LINK_CSS = re.compile(r"<link\b([^>]*)>", re.I)
_ATTR = lambda name: re.compile(rf"\b{name}\s*=\s*[\"']([^\"']*)[\"']", re.I)  # noqa: E731
_SRC, _HREF, _INTEGRITY, _REL = _ATTR("src"), _ATTR("href"), _ATTR("integrity"), _ATTR("rel")
_IFRAME = re.compile(r"<iframe\b([^>]*)>", re.I)
#: Hosts the inventory names as a known vendor or CDN without the site record
#: saying so. Short on purpose: a host missing here and from the record's
#: third_party_map is reported as unexplained, and the fix for a legitimate one
#: is a line in the map, which is the owner's statement the brief asks for.
KNOWN_VENDORS = (
    "googletagmanager.com", "google-analytics.com", "googleapis.com", "gstatic.com",
    "google.com", "googleadservices.com", "doubleclick.net", "youtube.com",
    "youtube-nocookie.com", "ytimg.com", "vimeo.com", "cloudflare.com",
    "cloudflareinsights.com", "jsdelivr.net", "unpkg.com", "jquery.com",
    "bootstrapcdn.com", "fontawesome.com", "facebook.net", "facebook.com",
    "stripe.com", "paypal.com", "hotjar.com", "clarity.ms", "hubspot.com",
    "hs-scripts.com", "wp.com", "gravatar.com", "recaptcha.net", "hcaptcha.com",
    "shopify.com", "shopifycdn.com", "squarespace.com", "wixstatic.com",
    "calendly.com", "typekit.net", "linkedin.com", "licdn.com", "twitter.com",
    "x.com", "tiktok.com", "pinterest.com", "bing.com", "intercom.io",
    "intercomcdn.com", "zendesk.com", "zdassets.com", "mailchimp.com",
    "list-manage.com", "cookiebot.com", "onetrust.com", "cookielaw.org",
    # Analytics and monitoring: twenty22's first inventory (2026-09-14) raised
    # plausible.io as unexplained, which was the list's gap, not the site's.
    "plausible.io", "usefathom.com", "simpleanalytics.com", "simpleanalyticscdn.com",
    "matomo.cloud", "segment.com", "mixpanel.com", "sentry-cdn.com", "nr-data.net",
    "newrelic.com", "posthog.com", "umami.is", "googleoptimize.com",
)
_FORM = re.compile(r"<form\b([^>]*)>", re.I)
_INLINE_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
#: Data blocks, not code: JSON-LD, import maps, templates.
_DATA_TYPE = re.compile(r"\btype\s*=\s*[\"']?(application/(ld\+)?json|importmap|text/(template|x-template|html))", re.I)
_DECODE_EXEC = re.compile(r"\beval\s*\(|\batob\s*\(|String\.fromCharCode|\bunescape\s*\(|\bnew\s+Function\s*\(", re.I)
_BLOB = re.compile(r"[\"'`](?:[A-Za-z0-9+/]{400,}={0,2}|(?:\\x[0-9a-fA-F]{2}){100,}|[0-9a-fA-F]{400,})[\"'`]")
_HEX_VAR = re.compile(r"\b_0x[0-9a-f]{4,}\b")
#: An element hidden by its own style attribute, the way injected link spam is
#: hidden: display:none, visibility:hidden, far off-screen, zero size with
#: overflow hidden, or zero font size. Class-based hiding lives in stylesheets
#: and is not read.
_HIDDEN_OPEN = re.compile(
    r"<([a-z][a-z0-9]*)\b[^>]*\bstyle\s*=\s*[\"'][^\"']*(?:display\s*:\s*none|visibility\s*:\s*hidden"
    r"|(?:left|top|text-indent)\s*:\s*-\d{4,}px|font-size\s*:\s*0(?:px)?\s*(?:;|[\"'])"
    r"|(?:height|max-height)\s*:\s*0(?:px)?\s*;[^\"']*overflow\s*:\s*hidden)[^\"']*[\"'][^>]*>", re.I)
_ANCHOR_HREF = re.compile(r"<a\b[^>]*\bhref\s*=\s*[\"'](https?://[^\"']+)", re.I)
#: Hosts a hidden block may link to without being spam: social profiles in a
#: collapsed mobile menu are the common legitimate case.
_SOCIAL = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
           "youtube.com", "tiktok.com", "pinterest.com", "threads.net", "google.com")
_ACTION = _ATTR("action")
_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
#: What makes a comment a leak rather than a note: a credential-shaped
#: assignment, or a non-production hostname. Deliberately narrow - a comment
#: naming a template section is not a finding, and a broad match would bury
#: the one that matters under a hundred that do not.
_LEAK = re.compile(
    r"(pass(word|wd)?|secret|api[_-]?key|token)\s*[:=]\s*\S{4,}"
    r"|\b(?:staging|stage|dev|test|uat)\.[a-z0-9-]+\.[a-z]{2,}"
    r"|\b(?:localhost|127\.0\.0\.1)(?::\d+)?\b", re.I)


def _header(headers: dict, key: str) -> str | None:
    return sh.observed(headers, key) if key not in ("x-frame-options", "server") else (
        next((str(v) for k, v in (headers or {}).items() if str(k).lower() == key), None))


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _registrable(host: str) -> str:
    """The last two labels, or three under a two-letter country second level
    (`example.com.au`). Enough to tell first-party from third-party without a
    public-suffix list, and stated as that approximation where it is used."""
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("com", "net", "org", "gov", "edu", "co"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _element_body(html: str, opening: re.Match) -> str:
    """The markup from an opening tag to its matching close, by counting
    same-name tags; capped so an unclosed tag cannot swallow the page."""
    name = opening.group(1).lower()
    tags = re.compile(rf"<(/?){name}\b[^>]*>", re.I)
    depth, end = 1, min(len(html), opening.end() + 20_000)
    for t in tags.finditer(html, opening.end(), end):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return html[opening.end():t.start()]
    return html[opening.end():end]


#: Item 240: cloaking compares what the site serves across agents over the
#: crawl (see `onp.CROSS_PAGE_CHECKS`).
CROSS_PAGE_CHECKS: frozenset[str] = frozenset({"cloaking"})


class SecurityModule:
    code = "SEC"
    name = "Security & transport"
    default_weight = scoring.DEFAULT_WEIGHTS["SEC"]
    #: Most rows are properties of one response, so re-fetching a page
    #: re-measures them; the transport rows are the origin's and re-measure
    #: with any fetch of it.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        out: list[Finding] = []
        out += self._transport(crawl)
        home = self._home(crawl)
        if home is not None:
            out += self._headers(home)
            out += self._isolation(home, context.get("site"))
        out += self._pages(crawl)
        out += self._inventory(crawl, context.get("site"))
        out += self._obfuscation(crawl)
        out += self._hidden(crawl)
        out += self._cloaking(crawl)
        out += self._consent(crawl, context.get("perf_traces") or {})
        out += self._well_known(crawl)
        rows, _skipped = dns_verdicts(getattr(crawl, "dns", None))
        for row in rows:
            out.append(Finding(dimension=self.code, check_id=row["check"],
                               severity=DEFAULT_SEVERITY[row["check"]],
                               summary=row["summary"], subject="site",
                               affected_urls=[crawl.start_url], evidence=row["evidence"],
                               recommendation=_DNS_FIX[row["check"]]))
        return out

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # Weight 0.04 by the design session's ruling (question channel,
        # 2026-09-13): HTTPS is a confirmed signal, the rest is hygiene, and
        # the compromise verdict is a first-line statement, not a score.
        return scoring.subscore(self.code, findings, self.default_weight, context,
                                coverage=scoring.page_coverage(context))

    # --- A · transport ---------------------------------------------------------

    @staticmethod
    def _home(crawl: CrawlResult):
        for p in crawl.pages:
            if (urlsplit(p.url).path or "/") == "/" and p.status == 200:
                return p
        return None

    def _transport(self, crawl: CrawlResult) -> list[Finding]:
        out: list[Finding] = []
        start = crawl.start_url
        if urlsplit(start).scheme != "https":
            out.append(self._site("http-redirect", start,
                                  "The site is not served over HTTPS.",
                                  {"scheme": urlsplit(start).scheme},
                                  "Serve the site over HTTPS with a valid certificate "
                                  "and redirect HTTP to HTTPS."))
            return out
        t = getattr(crawl, "transport", None)
        if t is None or t.error:
            return out
        if t.http_redirects_to_https is False:
            out.append(self._site("http-redirect", start,
                                  f"http://{t.host} is not redirected to https://.",
                                  {"http_redirect_chain": t.http_redirect_chain},
                                  "Redirect every http:// request to https:// with one 301."))
        elif t.http_redirects_to_https and len(t.http_redirect_chain) > 1:
            out.append(self._site("http-redirect", start,
                                  f"http://{t.host} reaches https:// in "
                                  f"{len(t.http_redirect_chain)} hops, not one.",
                                  {"http_redirect_chain": t.http_redirect_chain},
                                  "Redirect http:// straight to the final https:// URL."))
        if t.tls_floor in ("TLSv1", "TLSv1_1") and t.tls_floor_certain:
            out.append(self._site("tls-legacy", start,
                                  f"{t.host} still accepts {t.tls_floor.replace('_', '.')}.",
                                  {"tls_floor": t.tls_floor, "tls_offered": t.tls_offered},
                                  "Disable TLS 1.0 and 1.1 at the server or CDN."))
        if t.cert_not_after:
            try:
                left = (ssl.cert_time_to_seconds(t.cert_not_after) - time.time()) / 86_400
            except ValueError:
                left = None
            if left is not None and left < CERT_EXPIRY_DAYS:
                out.append(self._site("cert-chain", start,
                                      f"The certificate for {t.host} expires in "
                                      f"{max(0, int(left))} day(s).",
                                      {"not_after": t.cert_not_after},
                                      "Renew the certificate and confirm renewal is automated."))
        # cert-key (A): RSA under 2048 bits, or a SHA-1 or MD5 signature on the
        # leaf. An EC or Ed25519 key has no size floor in the brief's rule.
        weak_sig = bool(t.cert_signature and re.search(r"sha1|md5", t.cert_signature, re.I))
        if (t.cert_key_type == "rsa" and t.cert_key_bits and t.cert_key_bits < 2048) or weak_sig:
            out.append(self._site("cert-key", start,
                                  f"The certificate for {t.host} uses "
                                  + " and ".join(x for x in (
                                      f"a {t.cert_key_bits}-bit RSA key" if t.cert_key_type == "rsa"
                                      and t.cert_key_bits and t.cert_key_bits < 2048 else "",
                                      f"a {t.cert_signature} signature" if weak_sig else "") if x) + ".",
                                  {"key_type": t.cert_key_type, "key_bits": t.cert_key_bits,
                                   "signature": t.cert_signature},
                                  "Reissue the certificate with an RSA 2048+ or ECDSA P-256 key "
                                  "and a SHA-256 signature."))
        # http2-absent (A): the TLS handshake offered h2 and the server did not
        # take it, and the home response advertises no h3 in Alt-Svc. A probe
        # whose handshake failed (no tls_version) is not a finding.
        home = self._home(crawl)
        alt_svc = (_header((home.headers or {}) if home else {}, "alt-svc") or "").lower()
        if t.tls_version and t.alpn != "h2" and "h3" not in alt_svc:
            out.append(self._site("http2-absent", start,
                                  f"{t.host} negotiated {t.alpn or 'no protocol'} with h2 offered, "
                                  "and advertises no HTTP/3.",
                                  {"alpn": t.alpn, "alt_svc": alt_svc or None},
                                  "Enable HTTP/2 at the server or CDN; most CDNs also "
                                  "offer HTTP/3 as a switch."))
        if t.cert_subject_alt_names:
            sans = [s.lower() for s in t.cert_subject_alt_names]
            host = t.host.lower()
            apex = host[4:] if host.startswith("www.") else host
            uncovered = [h for h in (apex, f"www.{apex}")
                         if not any(s == h or (s.startswith("*.") and h.endswith(s[1:])
                                               and h.count(".") == s.count("."))
                                    for s in sans)]
            if uncovered:
                out.append(self._site("cert-san", start,
                                      f"The certificate does not cover {', '.join(uncovered)}.",
                                      {"subject_alt_names": t.cert_subject_alt_names,
                                       "uncovered": uncovered},
                                      "Reissue the certificate with both the apex and www names."))
        return out

    # --- B · headers & cookies, and C's banner, on the home page's response ------

    def _headers(self, home) -> list[Finding]:
        out: list[Finding] = []
        h = home.headers or {}
        url = home.url
        # The rows the headers grid also draws are decided by the grid's own
        # function, `security_headers.cell_state`, so the finding and the cell
        # cannot disagree (brief v16h, kept through the move out of TEC).
        def cell(key: str) -> str:
            return sh.cell_state(key, h, anywhere=True)

        hsts = _header(h, "strict-transport-security")
        if cell("strict-transport-security") == sh.MISSING:
            out.append(self._site("hsts", url, "Strict-Transport-Security is not set.",
                                  {"observed": None},
                                  "Set HSTS with a ramped max-age (see the HSTS rollout)."))
        elif cell("strict-transport-security") == sh.WEAK:
            m = _MAX_AGE.search(hsts or "")
            age = int(m.group(1)) if m else 0
            gaps = ([f"max-age {age} is under {HSTS_FULL_AGE}"] if age < HSTS_FULL_AGE else []) + (
                ["no includeSubDomains"] if "includesubdomains" not in (hsts or "").lower() else [])
            out.append(self._site("hsts", url, f"HSTS is set but {'; '.join(gaps)}.",
                                  {"observed": hsts, "max_age": age},
                                  "Raise max-age in steps once the whole estate is on HTTPS."))
        csp = _header(h, "content-security-policy")
        csp_ro = _header(h, "content-security-policy-report-only")
        if csp is None and csp_ro is None:
            out.append(self._site("csp-absent", url, "No Content-Security-Policy, enforced or Report-Only.",
                                  {"observed": None},
                                  "Start a Report-Only CSP built from the site's real origins."))
        else:
            policy = (csp or csp_ro or "").lower()
            weak = []
            if csp is None:
                weak.append("Report-Only only - it enforces nothing")
            script_src = next((d for d in policy.split(";") if d.strip().startswith("script-src")), "")
            for token in ("'unsafe-inline'", "'unsafe-eval'", " data:", " blob:"):
                if token in f" {script_src}":
                    weak.append(f"{token.strip()} in script-src")
            if re.search(r"(^|\s)\*(\s|;|$)", policy):
                weak.append("a wildcard source")
            if "frame-ancestors" not in policy:
                weak.append("no frame-ancestors")
            if "object-src" not in policy:
                weak.append("no object-src")
            if weak:
                out.append(self._site("csp-weak", url, "The CSP is present but " + "; ".join(weak) + ".",
                                      {"observed": csp or csp_ro, "report_only": csp is None, "gaps": weak},
                                      "Tighten the policy from the site's observed origins."))
        if cell("x-content-type-options") != sh.SET:
            out.append(self._site("xcto", url, "X-Content-Type-Options: nosniff is not set.",
                                  {"observed": _header(h, "x-content-type-options")},
                                  "Send X-Content-Type-Options: nosniff on every response."))
        ref = _header(h, "referrer-policy")
        if cell("referrer-policy") != sh.SET:
            out.append(self._site("referrer-policy", url,
                                  "Referrer-Policy is " + ("not set." if ref is None else f"{ref}, which leaks full URLs."),
                                  {"observed": ref},
                                  "Set Referrer-Policy: strict-origin-when-cross-origin."))
        if cell("permissions-policy") != sh.SET:
            out.append(self._site("permissions-policy", url, "Permissions-Policy is not set.",
                                  {"observed": None},
                                  "Declare the browser features the site does not use."))
        xfo = _header(h, "x-frame-options")
        if cell("x-frame-options") != sh.SET:
            out.append(self._site("frame-ancestors", url,
                                  "Neither frame-ancestors nor X-Frame-Options is set.",
                                  {"x_frame_options": None, "csp": csp},
                                  "Set CSP frame-ancestors 'self' (and X-Frame-Options for old browsers)."))
        deprecated = [k for k in ("x-xss-protection", "expect-ct", "public-key-pins")
                      if _header(h, k) is not None]
        if deprecated:
            out.append(self._site("deprecated-header", url,
                                  f"Deprecated header(s) still sent: {', '.join(deprecated)}.",
                                  {"present": {k: _header(h, k) for k in deprecated}},
                                  "Remove them; browsers ignore or have removed them."))
        cookies = [c for c in (_header(h, "set-cookie") or "").split("\n") if c.strip()]
        weak_cookies = []
        for c in cookies:
            attrs = c.lower()
            name = c.split("=", 1)[0].strip()
            missing = [a for a, tok in (("Secure", "secure"), ("HttpOnly", "httponly"), ("SameSite", "samesite"))
                       if tok not in attrs]
            if missing:
                weak_cookies.append({"cookie": name, "missing": missing})
        if weak_cookies:
            out.append(self._site("cookie-flags", url,
                                  f"{len(weak_cookies)} cookie(s) set without "
                                  "Secure, HttpOnly or SameSite.",
                                  {"cookies": weak_cookies},
                                  "Set Secure; HttpOnly (unless read by script); SameSite=Lax or Strict."))
        cache = (_header(h, "cache-control") or "").lower()
        if cookies and ("public" in cache or not cache):
            out.append(self._site("cache-authenticated", url,
                                  "A response that sets a cookie is cacheable "
                                  + ("publicly." if "public" in cache else "(no Cache-Control)."),
                                  {"cache_control": _header(h, "cache-control"),
                                   "cookies": [c.split("=", 1)[0] for c in cookies]},
                                  "Send Cache-Control: private, no-store on responses that set session state."))
        banners = {k: _header(h, k) for k in ("server", "x-powered-by", "x-aspnet-version")
                   if _header(h, k) and _VERSIONED.search(_header(h, k) or "")}
        # `server` is the grid's disclosure row (Server or X-Powered-By);
        # X-AspNet-Version is SEC's own addition and the grid has no cell for it.
        if cell("server") == sh.WEAK or "x-aspnet-version" in banners:
            out.append(self._site("version-banner", url,
                                  "Software versions disclosed in headers: "
                                  + ", ".join(f"{k}: {v}" for k, v in banners.items()) + ".",
                                  {"banners": banners},
                                  "Strip version numbers from Server and X-Powered-By."))
        return out

    def _consent(self, crawl: CrawlResult, traces: dict) -> list[Finding]:
        """Trackers before consent (F): on a traced page carrying a consent
        tool, a tracking beacon requested with nothing clicked - the banner is
        there and is not blocking. A site with no consent tool raises nothing
        here: there is no consent event to be before, and whether trackers
        without one matter depends on the site's market, which the brief
        judges from `consent_facts` (channel 20260914-1415, option A)."""
        facts = consent_facts(crawl.pages, traces)
        bypassed = facts["bypassed"]
        if not bypassed:
            return []
        affected = sorted({u for e in bypassed.values() for u in e["pages"]})
        return [Finding(
            dimension=self.code, check_id="trackers-before-consent",
            severity=DEFAULT_SEVERITY["trackers-before-consent"],
            summary=f"{len(bypassed)} tracker(s) load before consent on {len(affected)} traced "
                    f"page(s) carrying {', '.join(facts['consent_tool'])}: "
                    + ", ".join(list(bypassed)[:5]) + ".",
            subject="site", affected_urls=affected[:20], affected_total=len(affected),
            evidence={"consent_tool": facts["consent_tool"],
                      "trackers": [{"host": h, "start_ms": e["start_ms"], "pages": len(e["pages"])}
                                   for h, e in bypassed.items()],
                      "basis": "the performance trace's requests, taken with no interaction; "
                               "start_ms is when each fired after navigation began"},
            recommendation="Gate these tags on the consent tool's accept event (or Consent Mode), "
                           "so nothing fires until the visitor agrees.")]

    def _cloaking(self, crawl: CrawlResult) -> list[Finding]:
        """Cloaking (F): the UA matrix's Googlebot bodies against the crawl's
        own fetch of the same URLs. Narrow, because the row is CRITICAL:
        Googlebot is shown links to two or more registrable domains the
        crawler's copy does not link to, or a different title together with
        visible text differing by more than half. Rotating copy, dates and
        nonces move neither. No matrix on the run, no row - the part page
        says the run did not fetch as Googlebot."""
        from ..crawler.ua_matrix import FINGERPRINT_AGENT, fingerprint
        row = next((r for r in (getattr(crawl, "ua_matrix", None) or [])
                    if r.get("agent") == FINGERPRINT_AGENT), None)
        if not row or not row.get("bodies"):
            return []
        site_reg = _registrable(_host(crawl.start_url))
        own = {p.url: p for p in crawl.pages if p.status == 200}
        differ: dict[str, dict] = {}
        for url, bot in row["bodies"].items():
            page = own.get(url)
            if page is None:
                continue
            seen = fingerprint(page.content or "")
            reg = lambda hosts: {_registrable(h) for h in hosts} - {site_reg, ""}  # noqa: E731
            extra = sorted(reg(bot["link_hosts"]) - reg(seen["link_hosts"]))
            longer = max(bot["text_len"], seen["text_len"]) or 1
            retitled = bot["title"].lower() != seen["title"].lower() \
                and abs(bot["text_len"] - seen["text_len"]) / longer > 0.5
            if len(extra) >= 2 or retitled:
                differ[url] = {"googlebot": {"title": bot["title"], "text_len": bot["text_len"]},
                               "crawler": {"title": seen["title"], "text_len": seen["text_len"]},
                               "links_only_googlebot_sees": extra[:10]}
        if not differ:
            return []
        return [Finding(
            dimension=self.code, check_id="cloaking",
            severity=DEFAULT_SEVERITY["cloaking"],
            summary=f"{len(differ)} of {len(row['bodies'])} page(s) serve Googlebot "
                    "materially different content from what the crawler was served.",
            subject="site", affected_urls=sorted(differ)[:20], affected_total=len(differ),
            evidence={"pages": dict(sorted(differ.items())[:10]),
                      "basis": "Googlebot's crawler name from this crawler's address, "
                               "compared with the crawler's own fetch; a server that "
                               "verifies Google's IP ranges is not tested by this"},
            recommendation="Fetch the page as Googlebot in Search Console's URL inspection; "
                           "if it differs there too, find what serves it and treat the "
                           "site as compromised.")]

    def _hidden(self, crawl: CrawlResult) -> list[Finding]:
        """Hidden link spam (F): an element hidden by its own style attribute
        that links to three or more registrable domains other than the site's
        and other than social profiles. A hidden menu of the site's own pages,
        or of its social accounts, is not a finding. Close tags are matched by
        counting same-name tags, which is an approximation stated in the
        evidence."""
        site_reg = _registrable(_host(crawl.start_url))
        hits: dict[str, list[str]] = {}
        for page in html_pages(crawl.pages):
            html = page.content or ""
            for m in _HIDDEN_OPEN.finditer(html):
                block = _element_body(html, m)
                domains = {_registrable(_host(u)) for u in _ANCHOR_HREF.findall(block)}
                foreign = sorted(d for d in domains if d and d != site_reg
                                 and not any(d == s or d.endswith("." + s) for s in _SOCIAL))
                if len(foreign) >= 3:
                    for d in foreign:
                        hits.setdefault(d, []).append(page.url)
        if not hits:
            return []
        pages = sorted({u for urls in hits.values() for u in urls})
        return [Finding(
            dimension=self.code, check_id="hidden-content",
            severity=DEFAULT_SEVERITY["hidden-content"],
            summary=f"Hidden markup on {len(pages)} page(s) links to {len(hits)} unrelated "
                    "domain(s): " + ", ".join(sorted(hits)[:5]) + ".",
            subject="site", affected_urls=pages[:20], affected_total=len(pages),
            evidence={"domains": {d: len(set(u)) for d, u in sorted(hits.items())[:20]},
                      "basis": "elements hidden by their own style attribute in the served "
                               "HTML; stylesheet-hidden text is not read, and nesting is "
                               "matched by counting same-name tags"},
            recommendation="Find what writes this block - a plugin, theme file or database "
                           "row - and treat the site as compromised until it is explained.")]

    def _obfuscation(self, crawl: CrawlResult) -> list[Finding]:
        """Obfuscated inline script (F). Narrow, because the row is CRITICAL:
        a decode-or-execute call (eval, atob, String.fromCharCode, unescape,
        new Function) in the same inline script as a long encoded blob, or the
        `_0x` names javascript-obfuscator emits, ten or more. eval or atob
        alone is ordinary minified code and is not a finding. External files
        are not read, and a script injected after load is not seen."""
        hits: dict[str, list[str]] = {}
        for page in html_pages(crawl.pages):
            for attrs, body in _INLINE_SCRIPT.findall(page.content or ""):
                if _SRC.search(attrs) or _DATA_TYPE.search(attrs):
                    continue
                signals = []
                if _DECODE_EXEC.search(body) and _BLOB.search(body):
                    signals.append("decode/execute beside an encoded blob")
                if len(set(_HEX_VAR.findall(body))) >= 10:
                    signals.append("obfuscator-style _0x names")
                for signal in signals:
                    hits.setdefault(signal, []).append(page.url)
        if not hits:
            return []
        pages = sorted({u for urls in hits.values() for u in urls})
        return [Finding(
            dimension=self.code, check_id="obfuscated-js",
            severity=DEFAULT_SEVERITY["obfuscated-js"],
            summary=f"Inline script on {len(pages)} page(s) carries an obfuscation "
                    "signature: " + "; ".join(sorted(hits)) + ".",
            subject="site", affected_urls=pages[:20], affected_total=len(pages),
            evidence={"signals": {k: len(set(v)) for k, v in sorted(hits.items())},
                      "basis": "inline <script> bodies in the served HTML; external files "
                               "and scripts injected after load are not read"},
            recommendation="Find which plugin or theme file emits this script; if nothing the "
                           "site installed accounts for it, treat the site as compromised.")]

    def _inventory(self, crawl: CrawlResult, site) -> list[Finding]:
        """Script inventory (F): every <script src> and <iframe src> origin
        across the fetched HTML, classified first-party, known (the site
        record's third_party_map, then KNOWN_VENDORS) or unexplained. The
        unexplained hosts are the finding - one site row - and a site whose
        every origin is classified raises nothing. The HTML is the served
        markup: a script injected after load is not seen here."""
        site_reg = _registrable(_host(crawl.start_url))
        mapped = {str(k).lower().split("//")[-1].split("/")[0].lstrip("*.")
                  for k in (getattr(site, "third_party_map", None) or {})}
        hosts: dict[str, set[str]] = {}
        for page in html_pages(crawl.pages):
            html = page.content or ""
            for attrs in _SCRIPT.findall(html) + _IFRAME.findall(html):
                s = _SRC.search(attrs)
                src = s.group(1).strip() if s else ""
                if not src or src.startswith(("data:", "about:", "javascript:")):
                    continue
                host = _host(urljoin(page.url, src))
                if host:
                    hosts.setdefault(host, set()).add(page.url)

        def known(host: str) -> str | None:
            for source, names in (("third_party_map", mapped), ("known vendor", KNOWN_VENDORS)):
                if any(host == n or host.endswith("." + n) for n in names):
                    return source
            return None

        classified = {h: ("first-party" if _registrable(h) == site_reg else known(h) or "unexplained")
                      for h in hosts}
        unexplained = sorted(h for h, c in classified.items() if c == "unexplained")
        if not unexplained:
            return []
        pages = sorted({u for h in unexplained for u in hosts[h]})
        return [Finding(
            dimension=self.code, check_id="script-inventory",
            severity=DEFAULT_SEVERITY["script-inventory"],
            summary=f"{len(unexplained)} script or iframe origin(s) are neither first-party "
                    "nor a known vendor: " + ", ".join(unexplained[:5]) + ".",
            subject="site", affected_urls=pages[:20], affected_total=len(pages),
            evidence={"unexplained": {h: len(hosts[h]) for h in unexplained[:20]},
                      "classified": dict(sorted(classified.items())[:40]),
                      "third_party_map": "used" if mapped else "absent from the site record",
                      "basis": "served HTML only; scripts injected after load are not seen"},
            recommendation="Name each origin's purpose in the site record's third-party map, "
                           "and remove any the site does not use on purpose.")]

    def _isolation(self, home, site) -> list[Finding]:
        """COOP / COEP / CORP (B). The brief: absent where the site type is
        SaaS or a portal, INFO otherwise - and its own `do_not_spend_on` on a
        brochure site is exactly these three. So a row is raised only for a
        `saas` site; on any other type they were read and nothing is owed,
        which is a measurement, not a gap."""
        if (getattr(site, "business_type", None) or "").lower() != "saas":
            return []
        h = home.headers or {}
        missing = [k for k in ("cross-origin-opener-policy", "cross-origin-embedder-policy",
                               "cross-origin-resource-policy") if _header(h, k) is None]
        if not missing:
            return []
        return [self._site("cross-origin-policies", home.url,
                           "An application site sends no " + ", ".join(missing) + ".",
                           {"missing": missing, "site_type": "saas"},
                           "Set Cross-Origin-Opener-Policy: same-origin first; add COEP and "
                           "CORP once embedded resources are known to allow it.")]

    # --- C, A and F per page -----------------------------------------------------

    def _pages(self, crawl: CrawlResult) -> list[Finding]:
        out: list[Finding] = []
        # CORS (B): `Access-Control-Allow-Origin: *` with credentials allowed,
        # on any fetched response. The half that needs a request carrying an
        # Origin - does the server reflect an arbitrary one? - is an active
        # probe and is not asked. Read from every page, because an API route
        # is where this is set, not the home page.
        permissive = [p.url for p in html_pages(crawl.pages) + [
                          q for q in crawl.pages if "json" in (q.content_type or "")]
                      if (_header(p.headers or {}, "access-control-allow-origin") or "").strip() == "*"
                      and (_header(p.headers or {}, "access-control-allow-credentials") or "").strip().lower() == "true"]
        if permissive:
            out.append(Finding(
                dimension=self.code, check_id="cors-permissive",
                severity=DEFAULT_SEVERITY["cors-permissive"],
                summary=f"{len(permissive)} response(s) allow any origin with credentials.",
                subject="site", affected_urls=sorted(set(permissive))[:20],
                affected_total=len(set(permissive)),
                evidence={"access_control_allow_origin": "*",
                          "access_control_allow_credentials": "true",
                          "note": "whether an arbitrary Origin is reflected needs a request "
                                  "carrying one, which this passive sweep does not send"},
                recommendation="Name the allowed origins explicitly wherever credentials are allowed."))
        site_host = _host(crawl.start_url)
        site_reg = _registrable(site_host)
        generator: dict[str, str] = {}
        components: dict[str, str] = {}
        # resource -> the pages loading it without integrity=. One site row,
        # not one per page: on twenty22 the first live sweep raised 45 rows for
        # one script the theme loads on every page, which is one fix.
        no_sri_pages: dict[str, list[str]] = {}
        for page in html_pages(crawl.pages):
            html = page.content or ""
            path = urlsplit(page.url).path or "/"
            m = _GENERATOR.search(html)
            if m:
                generator.setdefault(m.group(1).strip(), page.url)
            for slug, ver in _ASSET_VER.findall(html):
                components.setdefault(slug.lower(), ver)
            if page.url.startswith("https://"):
                insecure = sorted({(g[1] or g[2]) for g in _INSECURE_SUB.findall(html)})
                if insecure:
                    out.append(Finding(
                        dimension=self.code, check_id="mixed-content",
                        severity=DEFAULT_SEVERITY["mixed-content"],
                        summary=f"{path} loads {len(insecure)} sub-resource(s) over http://.",
                        subject=path, affected_urls=[page.url],
                        evidence={"insecure": insecure[:10], "count": len(insecure)},
                        recommendation="Load every sub-resource over https://."))
            foreign_forms = []
            for attrs in _FORM.findall(html):
                a = _ACTION.search(attrs)
                if not a or not a.group(1).strip():
                    continue
                target = urljoin(page.url, a.group(1).strip())
                th = _host(target)
                if th and urlsplit(target).scheme in ("http", "https") and _registrable(th) != site_reg:
                    foreign_forms.append(target)
            if foreign_forms:
                out.append(Finding(
                    dimension=self.code, check_id="cross-origin-form",
                    severity=DEFAULT_SEVERITY["cross-origin-form"],
                    summary=f"{path} posts a form to another origin: {foreign_forms[0]}.",
                    subject=path, affected_urls=[page.url],
                    evidence={"actions": foreign_forms[:5],
                              "basis": "registrable domain compared by its last labels, "
                                       "not a public-suffix list"},
                    recommendation="Confirm each foreign form target is a service the "
                                   "site uses on purpose; remove any that is not."))
            no_sri = []
            for attrs in _SCRIPT.findall(html):
                s = _SRC.search(attrs)
                if s and _registrable(_host(urljoin(page.url, s.group(1)))) not in ("", site_reg) \
                        and not _INTEGRITY.search(attrs):
                    no_sri.append(urljoin(page.url, s.group(1)))
            for attrs in _LINK_CSS.findall(html):
                rel, href = _REL.search(attrs), _HREF.search(attrs)
                if rel and "stylesheet" in rel.group(1).lower() and href \
                        and _registrable(_host(urljoin(page.url, href.group(1)))) not in ("", site_reg) \
                        and not _INTEGRITY.search(attrs):
                    no_sri.append(urljoin(page.url, href.group(1)))
            for resource in set(no_sri):
                no_sri_pages.setdefault(resource, []).append(page.url)
            leaks = [c.strip()[:160] for c in _COMMENT.findall(html) if _LEAK.search(c)]
            if leaks:
                out.append(Finding(
                    dimension=self.code, check_id="html-comment-leak",
                    severity=DEFAULT_SEVERITY["html-comment-leak"],
                    summary=f"{path} carries {len(leaks)} HTML comment(s) naming a "
                            "credential or a non-production host.",
                    subject=path, affected_urls=[page.url],
                    evidence={"comments": leaks[:5]},
                    recommendation="Strip developer comments from production markup."))
        if no_sri_pages:
            pages = sorted({u for urls in no_sri_pages.values() for u in urls})
            out.append(Finding(
                dimension=self.code, check_id="sri-missing",
                severity=DEFAULT_SEVERITY["sri-missing"],
                summary=f"{len(no_sri_pages)} third-party script(s) or stylesheet(s) "
                        f"load without integrity= across {len(pages)} page(s).",
                subject="site", affected_urls=pages[:20], affected_total=len(pages),
                evidence={"resources": {r: len(u) for r, u in sorted(no_sri_pages.items())[:20]},
                          "resource_total": len(no_sri_pages)},
                recommendation="Add integrity= to pinned third-party files, or "
                               "self-host them."))
        if generator or components:
            out.append(Finding(
                dimension=self.code, check_id="cms-fingerprint",
                severity=DEFAULT_SEVERITY["cms-fingerprint"],
                summary="The platform and its components are fingerprintable"
                        + (f": {', '.join(generator)}" if generator else "") + ".",
                subject="site", affected_urls=list(generator.values())[:3],
                affected_total=len(generator),
                evidence={"generator": sorted(generator), "components": dict(sorted(components.items())[:40]),
                          "note": "versions are fingerprinted from markup and may be "
                                  "spoofed or backported"},
                recommendation="Remove the generator meta and ?ver= query strings "
                               "where the platform allows."))
        return out

    # --- C, D, I · the well-known path sweep -------------------------------------

    def _well_known(self, crawl: CrawlResult) -> list[Finding]:
        """Read the sweep `crawler/wellknown.py` made. Nothing here fetches.

        A status alone never raises a row: every check needs the content
        signature of the thing it names, because a site that answers every
        path with its own page and a 200 would otherwise read as exposing
        everything."""
        wk = getattr(crawl, "well_known", None)
        if not wk:
            return []
        rows = {r["path"]: r for r in wk.get("fetched") or []}
        start = crawl.start_url
        out: list[Finding] = []

        def ok(row) -> bool:
            return bool(row) and row.get("status") == 200 and not row.get("error")

        def html(row) -> bool:
            return "html" in (row.get("content_type") or "").lower() or \
                (row.get("head") or "").lstrip().lower().startswith(("<!doctype", "<html"))

        exposed, critical = [], False
        for path, (signature, grave) in _EXPOSED.items():
            row = rows.get(path)
            if ok(row) and (path == "/phpinfo.php" or not html(row)) and signature(row.get("head") or ""):
                exposed.append(path)
                critical = critical or grave
        if exposed:
            out.append(Finding(
                dimension=self.code, check_id="exposed-file",
                severity=Severity.CRITICAL if critical else Severity.MEDIUM,
                summary=f"{len(exposed)} file(s) that should not be public are readable: "
                        + ", ".join(exposed) + ".",
                subject="site", affected_urls=[rows[p]["url"] for p in exposed],
                evidence={"paths": {p: {"status": rows[p]["status"],
                                        "content_type": rows[p].get("content_type"),
                                        "length": rows[p].get("length")} for p in exposed},
                          "note": "read with one ordinary GET each; the contents are not stored"},
                recommendation="Remove the files from the web root, or deny them at the "
                               "server; rotate any credential they held."))

        listed = [p for p, r in rows.items()
                  if r.get("purpose") == "directory-listing" and ok(r)
                  and re.search(r"<title>\s*Index of|<h1>\s*Index of", r.get("head") or "", re.I)]
        if listed:
            out.append(self._site("directory-listing", start,
                                  f"Directory listing is on for {', '.join(listed)}.",
                                  {"paths": listed},
                                  "Turn off directory indexes (Options -Indexes, or autoindex off)."))

        nf = wk.get("not_found") or {}
        if not nf.get("error") and _ERROR_LEAK.search(nf.get("head") or ""):
            out.append(self._site("error-leak", start,
                                  "The site's not-found page shows a stack trace, a file path "
                                  "or a database error.",
                                  {"status": nf.get("status"),
                                   "excerpt": _ERROR_LEAK.search(nf.get("head") or "").group(0)},
                                  "Serve a plain error page and send the detail to the log."))

        xml = rows.get("/xmlrpc.php")
        if xml and xml.get("status") in (200, 405) and "XML-RPC server accepts POST requests only" in (xml.get("head") or ""):
            out.append(self._site("cms-xmlrpc", start, "xmlrpc.php is reachable.",
                                  {"status": xml.get("status"),
                                   "note": "system.multicall abuse is held: it needs a probe, "
                                           "which this build never performs"},
                                  "Block xmlrpc.php at the server unless a service needs it."))

        users = rows.get("/wp-json/wp/v2/users")
        author = rows.get("/?author=1")
        enum = []
        if ok(users) and (users.get("head") or "").lstrip().startswith("[{") and '"slug"' in (users.get("head") or ""):
            enum.append("/wp-json/wp/v2/users lists users")
        if author and not author.get("error") and "/author/" in (author.get("final_url") or ""):
            enum.append("?author=1 redirects to a username slug")
        if enum:
            out.append(self._site("cms-user-enumeration", start,
                                  "User names can be listed: " + "; ".join(enum) + ".",
                                  {"signals": enum},
                                  "Restrict the users endpoint and the author redirect."))

        login = rows.get("/wp-login.php")
        if ok(login) and "wp-login.php" in (login.get("final_url") or "") and html(login):
            out.append(self._site("cms-login-exposed", start,
                                  "wp-login.php answers publicly with no challenge in front of it.",
                                  {"final_url": login.get("final_url"),
                                   "note": "whether its errors tell a bad user from a bad "
                                           "password is held: it needs a login attempt"},
                                  "Put the login behind an IP allow-list, a challenge or a moved path."))

        reg = rows.get("/wp-login.php?action=register")
        if ok(reg) and "action=register" in (reg.get("final_url") or "") \
                and "registration=disabled" not in (reg.get("final_url") or "") \
                and "user_email" in (reg.get("head") or ""):
            out.append(self._site("cms-registration-open", start,
                                  "Anyone can register an account.",
                                  {"final_url": reg.get("final_url")},
                                  "Turn off 'Anyone can register' unless the site needs accounts."))

        txt = rows.get("/.well-known/security.txt")
        if not (ok(txt) and not html(txt) and "contact:" in (txt.get("head") or "").lower()):
            out.append(self._site("security-txt", start,
                                  "/.well-known/security.txt is absent or names no contact.",
                                  {"status": (txt or {}).get("status")},
                                  "Publish security.txt with a Contact line."))
        return out

    def _site(self, check: str, url: str, summary: str, evidence: dict,
              recommendation: str) -> Finding:
        return Finding(dimension=self.code, check_id=check,
                       severity=DEFAULT_SEVERITY[check], summary=summary,
                       subject="site", affected_urls=[url], evidence=evidence,
                       recommendation=recommendation)


registry.register(SecurityModule())
