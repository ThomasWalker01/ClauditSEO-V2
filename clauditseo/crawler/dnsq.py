"""Public DNS lookups for SEC's domain E (item 143, brief v20 step BD).

**The operator's own resolver, and nothing else** (question channel,
2026-09-14): `dnspython`, an optional extra (`clauditseo[dns]`), lazily imported
and gated on `available()` like `render` and `image`. No DNS-over-HTTPS
fallback: that would send every client domain and the guessed subdomain list
to a third party at audit time.

**What a result means, so the checks cannot lie on a bad network.**
NXDOMAIN and NoAnswer are evidence of absence. Timeout, SERVFAIL and
NoNameservers are "the resolver did not answer" - never a finding. Each query
is short (`LIFETIME`), so one slow domain costs seconds, not minutes.

Passive: these are ordinary lookups of public records. No zone transfer, no
brute-force of names beyond the fixed lists below, which the findings state.
"""

from __future__ import annotations

import time

#: Common DKIM selectors tried. A named constant because the finding states
#: the list: absence among these is a limit of the guess, not proof.
#:
#: The mail providers' own selectors joined after the first live run: twenty22
#: signs through Migadu as `key1`/`key2`, which the generic list missed, and
#: the row it raised said "no DKIM selector found" of a domain that has DKIM.
DKIM_SELECTORS: tuple[str, ...] = (
    "default", "google", "selector1", "selector2", "k1", "k2", "mail", "dkim", "s1", "s2",
    "key1", "key2", "key3",                           # Migadu
    "fm1", "fm2", "fm3",                              # Fastmail
    "protonmail", "protonmail2", "protonmail3",       # Proton
    "zmail",                                          # Zoho
    "mxvault", "smtp", "mandrill", "cm")              # MXroute-style, generic SMTP, Mailchimp, Campaign Monitor

#: The hosts probed for a dangling CNAME. Stated in the finding.
CNAME_HOSTS: tuple[str, ...] = ("www", "mail", "staging", "dev", "test", "cpanel",
                                "webmail", "autodiscover")

TIMEOUT = 2.5
LIFETIME = 5.0

OK, NXDOMAIN, NOANSWER, NOANSWER_SERVER, ERROR = "ok", "nxdomain", "noanswer", "no-answer-from-resolver", "error"


#: RFC 6761 / 6762 names that never resolve in public DNS. A local fixture or
#: an intranet host is asked nothing: the answer is known and asking costs a
#: resolver timeout per query.
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost", ".local")


def is_public_name(name: str) -> bool:
    import ipaddress
    name = (name or "").strip(".").lower()
    if not name or "." not in name or name == "localhost":
        return False
    try:
        ipaddress.ip_address(name)
        return False
    except ValueError:
        pass
    return not name.endswith(RESERVED_SUFFIXES)


def available() -> bool:
    try:
        import dns.resolver  # noqa: F401
    except ImportError:
        return False
    return True


def query(name: str, rtype: str) -> dict:
    """One lookup: `{name, type, status, records, ad}`. The single seam the
    suite monkeypatches - no live DNS in tests."""
    import dns.exception
    import dns.flags
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.timeout, resolver.lifetime = TIMEOUT, LIFETIME
    resolver.use_edns(0, dns.flags.DO, 1232)
    row = {"name": name, "type": rtype, "status": ERROR, "records": [], "ad": False}
    try:
        answer = resolver.resolve(name, rtype, raise_on_no_answer=True)
        row["status"] = OK
        row["records"] = [r.to_text() for r in answer][:20]
        row["ad"] = bool(answer.response.flags & dns.flags.AD)
    except dns.resolver.NXDOMAIN:
        row["status"] = NXDOMAIN
    except dns.resolver.NoAnswer:
        row["status"] = NOANSWER
    except (dns.exception.Timeout, dns.resolver.NoNameservers, dns.resolver.LifetimeTimeout):
        row["status"] = NOANSWER_SERVER
    except Exception as exc:  # a malformed name, a local resolver fault
        row["status"] = ERROR
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def collect(apex: str) -> dict:
    """Every lookup domain E reads, for one apex domain.

    `{"available": False, "reason"}` where the extra is not installed, so a run
    records WHY it has no DNS evidence rather than looking like one that never
    asked."""
    if not available():
        return {"available": False,
                "reason": "dnspython is not installed - install clauditseo[dns]"}
    if not is_public_name(apex):
        return {"available": False,
                "reason": f"{apex} is not a public DNS name, so it has no public records to read"}
    queries = [query(apex, "TXT"), query(f"_dmarc.{apex}", "TXT"),
               query(apex, "CAA"), query(apex, "DNSKEY"), query(apex, "NS")]
    queries += [query(f"{sel}._domainkey.{apex}", "TXT") for sel in DKIM_SELECTORS]
    for host in CNAME_HOSTS:
        cname = query(f"{host}.{apex}", "CNAME")
        queries.append(cname)
        if cname["status"] == OK and cname["records"]:
            target = cname["records"][0].rstrip(".")
            resolved = query(target, "A")
            resolved["cname_of"] = f"{host}.{apex}"
            queries.append(resolved)
    return {"available": True, "apex": apex, "queries": queries,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
