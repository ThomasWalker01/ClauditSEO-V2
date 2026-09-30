"""Host-level transport facts: TLS and the HTTP to HTTPS path.

A security brief that cannot see the transport layer has to write
"[TO CONFIRM]" against half its scope. One handshake and one plain-HTTP
request answer most of it, without shelling out to an external scanner.

Nothing here is a substitute for a full TLS scan — cipher ordering, chain
completeness and OCSP stapling are not covered, and the brief is told so
rather than left to assume.
"""

from __future__ import annotations

import socket
import ssl
import warnings
from urllib.parse import urlsplit

from .types import USER_AGENT, TransportProbe

TIMEOUT = 5.0

#: What one pinned handshake attempt meant. Four outcomes, not two, because
#: "it did not connect" hides the distinction the floor depends on.
ACCEPTED = "accepted"        # the server spoke this version
REJECTED = "rejected"        # the server refused it — evidence about the site
NOT_OFFERED = "not-offered"  # our own OpenSSL would not send it — evidence
                             # about this machine, and about nothing else
FAILED = "failed"            # timeout, reset, DNS — evidence about neither

#: Lowest first. The probe walks up until the server takes one, so the first
#: acceptance is the floor and everything below it has been asked.
PROBE_VERSIONS: tuple[str, ...] = ("TLSv1", "TLSv1_1", "TLSv1_2", "TLSv1_3")


def classify_attempt(exc: BaseException | None) -> str:
    """What a pinned handshake's outcome says — and about whom.

    `NO_PROTOCOLS_AVAILABLE` never reaches the network: OpenSSL 3's default
    security level declines to send TLS 1.0 at all. Reporting that as "the
    site does not support TLS 1.0" would be a claim about a server that was
    never asked, which is precisely the false confidence this probe exists
    to avoid.
    """
    if exc is None:
        return ACCEPTED
    text = str(exc)
    if "NO_PROTOCOLS_AVAILABLE" in text:
        return NOT_OFFERED
    if isinstance(exc, ssl.SSLError) and (
            "ALERT_PROTOCOL_VERSION" in text or "WRONG_SSL_VERSION" in text
            or "UNSUPPORTED_PROTOCOL" in text):
        return REJECTED
    return FAILED


def floor_from(outcomes: dict[str, str]) -> tuple[str | None, bool]:
    """The lowest version accepted, and whether that is settled.

    Settled means every version below the floor was actually offered and
    actually refused. One `NOT_OFFERED` below it and the floor becomes the
    lowest version we *happened to try*, which is a different statement — so
    the figure still travels, flagged, rather than being either withheld or
    printed as measured.
    """
    floor = next((v for v in PROBE_VERSIONS
                  if outcomes.get(v) == ACCEPTED), None)
    if floor is None:
        return None, False
    below = PROBE_VERSIONS[:PROBE_VERSIONS.index(floor)]
    return floor, all(outcomes.get(v) == REJECTED for v in below)


def probe(start_url: str) -> TransportProbe:
    parts = urlsplit(start_url)
    host = parts.hostname or ""
    result = TransportProbe(host=host)
    if not host:
        result.error = "no host in start URL"
        return result

    if parts.scheme == "https":
        _tls_facts(host, parts.port or 443, result)
        _tls_floor(host, parts.port or 443, result)

    # The HTTP-to-HTTPS check only means anything on the default ports. A
    # site served on an explicit non-standard port (staging, a local fixture)
    # has no port-80 story to tell, and probing for one just blocks until it
    # times out.
    if parts.port in (None, 80, 443):
        _http_upgrade_path(host, result)
    else:
        result.error = ((result.error + "; ") if result.error else "") + \
            f"HTTP upgrade path not probed: site is served on port {parts.port}"
    return result


def _der(data: bytes, i: int) -> tuple[int, int, int]:
    """One DER element at `i`: (tag, content start, content end)."""
    tag, length = data[i], data[i + 1]
    i += 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(data[i:i + n], "big")
        i += n
    return tag, i, i + length


def _children(data: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    out, i = [], start
    while i < end:
        el = _der(data, i)
        out.append(el)
        i = el[2]
    return out


def _oid(b: bytes) -> str:
    parts, value = [b[0] // 40, b[0] % 40], 0
    for byte in b[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(value)
            value = 0
    return ".".join(map(str, parts))


_SIGNATURES = {
    "1.2.840.113549.1.1.4": "md5WithRSAEncryption", "1.2.840.113549.1.1.5": "sha1WithRSAEncryption",
    "1.2.840.10045.4.1": "ecdsa-with-SHA1", "1.2.840.113549.1.1.11": "sha256WithRSAEncryption",
    "1.2.840.113549.1.1.12": "sha384WithRSAEncryption", "1.2.840.113549.1.1.13": "sha512WithRSAEncryption",
    "1.2.840.113549.1.1.10": "rsassa-pss", "1.2.840.10045.4.3.2": "ecdsa-with-SHA256",
    "1.2.840.10045.4.3.3": "ecdsa-with-SHA384", "1.2.840.10045.4.3.4": "ecdsa-with-SHA512",
    "1.3.101.112": "ed25519",
}
_CURVES = {"1.2.840.10045.3.1.7": 256, "1.3.132.0.34": 384, "1.3.132.0.35": 521}


def cert_key(der: bytes) -> tuple[str | None, int | None, str | None]:
    """The key type, key size and signature algorithm of one DER certificate,
    without a crypto library: the three fields SEC/cert-key judges ("RSA <
    2048 or SHA-1 signature"). Anything unexpected yields Nones, never a
    guess."""
    try:
        _, s, e = _der(der, 0)
        cert = _children(der, s, e)
        tbs = _children(der, cert[0][1], cert[0][2])
        if tbs[0][0] == 0xA0:                       # explicit version
            tbs = tbs[1:]
        spki = _children(der, tbs[5][1], tbs[5][2])
        alg = _children(der, spki[0][1], spki[0][2])
        key_oid = _oid(der[alg[0][1]:alg[0][2]])
        sig_alg = _children(der, cert[1][1], cert[1][2])
        sig_oid = _oid(der[sig_alg[0][1]:sig_alg[0][2]])
        signature = _SIGNATURES.get(sig_oid, sig_oid)
        if key_oid == "1.2.840.113549.1.1.1":       # rsaEncryption
            _, bs, be = spki[1]
            _, ks, ke = _der(der, bs + 1)           # skip the unused-bits byte
            modulus = _children(der, ks, ke)[0]
            return "rsa", int.from_bytes(der[modulus[1]:modulus[2]], "big").bit_length(), signature
        if key_oid == "1.2.840.10045.2.1":          # id-ecPublicKey
            curve = _oid(der[alg[1][1]:alg[1][2]]) if len(alg) > 1 and alg[1][0] == 0x06 else None
            return "ec", _CURVES.get(curve or ""), signature
        if key_oid == "1.3.101.112":
            return "ed25519", 256, signature
        return key_oid, None, signature
    except (IndexError, ValueError):
        return None, None, None


def _tls_facts(host: str, port: int, result: TransportProbe) -> None:
    context = ssl.create_default_context()
    # Offer h2 beside http/1.1 so the server's choice is the answer to
    # SEC/http2-absent (item 143 step BD). Offering it changes nothing else
    # this handshake reads.
    context.set_alpn_protocols(["h2", "http/1.1"])
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                result.tls_version = tls.version()
                cipher = tls.cipher()
                result.cipher = cipher[0] if cipher else None
                cert = tls.getpeercert() or {}
                result.cert_not_after = cert.get("notAfter")
                result.cert_subject_alt_names = [
                    value for kind, value in cert.get("subjectAltName", ())
                    if kind == "DNS"][:20]
                result.alpn = tls.selected_alpn_protocol()
                der = tls.getpeercert(binary_form=True)
                if der:
                    (result.cert_key_type, result.cert_key_bits,
                     result.cert_signature) = cert_key(der)
    except Exception as exc:
        result.error = f"TLS probe failed: {type(exc).__name__}: {exc}"


def _http_upgrade_path(host: str, result: TransportProbe) -> None:
    """Does plain HTTP reach HTTPS, and in how many hops? A site can be fully
    HTTPS and still leave port 80 open and unredirected."""
    import httpx

    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                          follow_redirects=True, max_redirects=5) as client:
            response = client.get(f"http://{host}/")
        chain = [str(r.url) for r in response.history] + [str(response.url)]
        result.http_redirect_chain = chain
        result.http_version = response.http_version
        result.http_redirects_to_https = str(response.url).startswith("https://")
    except Exception as exc:
        result.error = ((result.error + "; ") if result.error else "") + \
            f"HTTP upgrade probe failed: {type(exc).__name__}: {exc}"


def _tls_floor(host: str, port: int, result: TransportProbe) -> None:
    """Offer each version from the bottom up and record what came back.

    One extra handshake per version, all short and none carrying a request.
    `SECLEVEL=0` is what lets 1.0 and 1.1 actually go out; without it OpenSSL
    3 declines locally and every answer below 1.2 is about this machine.

    Deliberately after `_tls_facts`, and deliberately not replacing it: the
    negotiated version and cipher are a real fact about a normal connection,
    and the floor is a different question. Both are reported.
    """
    outcomes: dict[str, str] = {}
    # Python deprecates TLSv1 and TLSv1_1, which is the correct advice for
    # code choosing a version and the opposite of what this loop is for:
    # offering a deprecated version is the only way to learn whether the
    # server still takes one. Silenced here, narrowly, rather than letting
    # four versions × every probing test bury the next real warning — this
    # suite ran on one warning before this function existed.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        _offer_each(host, port, outcomes)
    result.tls_offered = outcomes
    result.tls_floor, result.tls_floor_certain = floor_from(outcomes)


def _offer_each(host: str, port: int, outcomes: dict[str, str]) -> None:
    for name in PROBE_VERSIONS:
        version = getattr(ssl.TLSVersion, name, None)
        if version is None:                       # a build without it at all
            outcomes[name] = NOT_OFFERED
            continue
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE       # the floor, not the chain
        try:
            context.minimum_version = version
            context.maximum_version = version
            context.set_ciphers("DEFAULT@SECLEVEL=0")
        except (ValueError, ssl.SSLError, OSError) as exc:
            outcomes[name] = classify_attempt(exc)
            continue
        try:
            with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
                with context.wrap_socket(raw, server_hostname=host):
                    outcomes[name] = ACCEPTED
        except Exception as exc:                  # noqa: BLE001 — classified
            outcomes[name] = classify_attempt(exc)
