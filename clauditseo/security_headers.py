"""What a response's security headers say, decided once.

Brief v16h (item 136i). The grid on the Security & transport part page and
the `security-headers` finding must never disagree, so neither decides
anything: both call `cell_state` here.

**What the check actually covers, and what the grid shows.** The check reads
three headers on the home page alone (`tec.SECURITY_HEADERS`). The grid shows
eight rows across every fetched page. So "grid and finding agree" is a claim
about the three they share, and the other five are shown with no finding
behind them — which is honest and is why `covered_by_check` exists: a reader
can tell which rows a check would have raised and which are the grid's own
reading. Widening the check to eight rows would change what every existing
run scores, and that is not this item's to do.
"""

from __future__ import annotations

import re

#: The rows, in the order the grid draws them. Fixed by the brief; nothing
#: is added here without one.
ROWS: tuple[tuple[str, str], ...] = (
    ("strict-transport-security", "Strict-Transport-Security"),
    ("content-security-policy", "Content-Security-Policy"),
    ("x-content-type-options", "X-Content-Type-Options"),
    ("x-frame-options", "X-Frame-Options / frame-ancestors"),
    ("referrer-policy", "Referrer-Policy"),
    ("permissions-policy", "Permissions-Policy"),
    ("set-cookie", "Set-Cookie · SameSite"),
    ("server", "Server / X-Powered-By"),
)

#: The rows a SEC check decides through `cell_state` on the home page (item
#: 143 step BD): `hsts`, `xcto`, `referrer-policy`, `permissions-policy`,
#: `frame-ancestors` and `version-banner`. Imported by the payload so the grid
#: marks which rows a check stands behind. CSP and Set-Cookie are not here:
#: their SEC checks ask more than the cell does (Report-Only, Secure and
#: HttpOnly), so a cell reading SET beside a finding would not be a
#: disagreement, and the grid must not imply one stands behind them.
COVERED_BY_CHECK = frozenset({
    "strict-transport-security", "x-content-type-options", "referrer-policy",
    "permissions-policy", "x-frame-options", "server",
})

#: A row whose SET state means "not disclosed". The disclosure row is
#: inverted: a `Server:` header that names the software is the defect, and
#: its absence is the good state.
INVERTED = frozenset({"server"})

#: HSTS below this is present but not doing the job. One year since brief v20
#: (`SEC/hsts`: "max-age < 31536000"), which supersedes v16h's one day - the
#: check and the grid read this one number, so they moved together.
HSTS_MIN_AGE = 31_536_000

_MAX_AGE = re.compile(r"max-age\s*=\s*(\d+)", re.I)
#: Referrer policies that leak the full URL cross-origin.
WEAK_REFERRER = frozenset({"unsafe-url", "no-referrer-when-downgrade", ""})
#: Software and version banners. A bare `Server: cloudflare` is a vendor
#: name and not a version, so it is not treated as disclosure - what matters
#: is a version an attacker can look up a CVE for.
_VERSIONED = re.compile(r"\d+\.\d+")

SET, MISSING, WEAK, ABSENT, NA = "set", "missing", "weak", "absent", "n/a"


def observed(headers: dict, key: str) -> str | None:
    """The header's value, or None. Case-insensitive, because a stored
    snapshot is whatever the origin spelled and HTTP does not care."""
    if not headers:
        return None
    for k, v in headers.items():
        if str(k).lower() == key:
            return str(v)
    # `X-Frame-Options` is satisfied by CSP `frame-ancestors`, and a site
    # that set the modern one and dropped the legacy one is protected. The
    # grid's row is named for both and so is this.
    if key == "x-frame-options":
        csp = observed(headers, "content-security-policy") or ""
        if "frame-ancestors" in csp.lower():
            return "frame-ancestors (via CSP)"
    if key == "server":
        return observed(headers, "x-powered-by")
    return None


def cell_state(key: str, headers: dict, anywhere: bool,
               sets_cookies: bool = True) -> str:
    """One cell.

    `anywhere` is whether the site carries this header on ANY page: it is
    what separates `missing` from `absent`. The brief's distinction is the
    useful one - a header the rest of the site has and this route does not
    is a gap; one nobody has is a decision not yet taken, and colouring the
    second like the first would tell an operator to chase two hundred
    identical cells.
    """
    value = observed(headers, key)

    if key == "set-cookie":
        if not sets_cookies:
            return NA
        return SET if _samesite(value) else (MISSING if anywhere else ABSENT)

    if key in INVERTED:
        # SET means "not disclosed", so present-and-versioned is the defect.
        if value is None:
            return SET
        return WEAK if _VERSIONED.search(value) else SET

    if value is None:
        return MISSING if anywhere else ABSENT
    if _weak(key, value):
        return WEAK
    return SET


def _samesite(value: str | None) -> bool:
    return bool(value) and "samesite" in value.lower()


def _weak(key: str, value: str) -> bool:
    """Present, and not doing what the header is for."""
    if key == "strict-transport-security":
        found = _MAX_AGE.search(value)
        return (not found or int(found.group(1)) < HSTS_MIN_AGE
                or "includesubdomains" not in value.lower())
    if key == "referrer-policy":
        return value.strip().lower() in WEAK_REFERRER
    return False


def anywhere_on_site(pages: list[dict], key: str) -> bool:
    """Whether any fetched page carries this header at all.

    Read across the whole run rather than per group, because that is the
    question `absent` asks: a header no page has is a decision the site has
    not taken, and one some pages have is a gap on the rest.
    """
    if key in INVERTED:
        # The inverted row is never "absent": not disclosing is the good
        # state and every page is in one state or the other.
        return True
    return any(observed(p.get("headers") or {}, key) for p in pages)
