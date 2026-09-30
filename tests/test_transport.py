"""The host-level TLS probe.

`_tls_facts` did one handshake with a default context and recorded
`tls.version()` — the *highest* version both ends agreed on. An operator
asking "does this site still accept TLS 1.0?" got the opposite end of the
range, and a server happily speaking 1.0 reported `TLSv1.3` exactly like one
that refuses it (BACKLOG B-15).

Finding the floor means offering each version deliberately and reading what
comes back. The hazard, measured against www.acme.com.au before this was
written:

    default context, pinned to TLS 1.0   NO_PROTOCOLS_AVAILABLE
    the same pin at SECLEVEL=0           TLSV1_ALERT_PROTOCOL_VERSION

The first never reached the network — our own OpenSSL refused to send it.
The second is a real alert from the server. Only the second is evidence
about the site, and a probe that treats them alike manufactures the false
claim this whole change exists to remove: "TLS 1.0 not supported", asserted
confidently about a server that was never asked.

So classification is a pure function over outcomes, tested here without a
socket. Whether a handshake succeeds is the network's business; what a
failure *means* is ours, and that is the part that can be wrong.
"""

from __future__ import annotations

import ssl

from clauditseo.crawler.transport import (
    ACCEPTED, FAILED, NOT_OFFERED, REJECTED, classify_attempt, floor_from,
)


def _ssl_error(text: str) -> ssl.SSLError:
    return ssl.SSLError(1, f"[SSL: {text}] something ({text.lower()}.c:1082)")


def test_a_successful_handshake_is_acceptance():
    assert classify_attempt(None) == ACCEPTED


def test_our_own_refusal_is_not_the_servers():
    """The distinction the whole entry rests on."""
    assert classify_attempt(_ssl_error("NO_PROTOCOLS_AVAILABLE")) == NOT_OFFERED


def test_a_protocol_alert_is_the_server_saying_no():
    assert classify_attempt(_ssl_error("TLSV1_ALERT_PROTOCOL_VERSION")) == REJECTED


def test_anything_else_is_not_evidence_either_way():
    assert classify_attempt(TimeoutError("timed out")) == FAILED
    assert classify_attempt(ConnectionResetError("reset")) == FAILED


def test_the_floor_is_the_lowest_version_the_server_took():
    floor, certain = floor_from({
        "TLSv1": REJECTED, "TLSv1_1": REJECTED,
        "TLSv1_2": ACCEPTED, "TLSv1_3": ACCEPTED,
    })
    assert floor == "TLSv1_2"
    assert certain is True


def test_a_version_we_could_not_offer_leaves_the_floor_uncertain():
    """Everything below the floor must have been *asked* and refused.

    With TLS 1.0 unsent, "the floor is 1.2" is a guess: the server may take
    1.0 perfectly well. The figure is still reported — it is the best thing
    known — but it is marked as not settled, so nothing downstream can print
    it as a measured fact.
    """
    floor, certain = floor_from({
        "TLSv1": NOT_OFFERED, "TLSv1_1": REJECTED,
        "TLSv1_2": ACCEPTED, "TLSv1_3": ACCEPTED,
    })
    assert floor == "TLSv1_2"
    assert certain is False


def test_no_acceptance_anywhere_is_no_floor_rather_than_a_default():
    floor, certain = floor_from({"TLSv1": FAILED, "TLSv1_2": FAILED})
    assert floor is None
    assert certain is False


def test_the_snapshot_carries_the_floor_it_measured():
    """A measurement dropped at the persistence boundary is worse than one
    never taken: the cost is paid on every crawl and no one can read it.

    `_tls_floor` performs up to four extra handshakes per crawl and writes
    `tls_floor`, `tls_floor_certain` and `tls_offered` onto the probe.
    `evidence.snapshot()` serialised eight transport fields and none of
    these, so the answer never reached the database, a module, a report or a
    screen — while the claim it was built to correct stayed on the panel.
    """
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import CrawlResult, TransportProbe
    from clauditseo.engine.types import Tier

    probe = TransportProbe(host="example.test")
    probe.tls_version = "TLSv1.3"
    probe.tls_floor = "TLSv1_2"
    probe.tls_floor_certain = True
    probe.tls_offered = {"TLSv1": REJECTED, "TLSv1_2": ACCEPTED}

    crawl = CrawlResult(start_url="https://example.test/", tier=Tier.T2)
    crawl.transport = probe
    carried = (snapshot(crawl).get("transport") or {})

    for field in ("tls_floor", "tls_floor_certain", "tls_offered"):
        assert field in carried, (
            f"snapshot() drops {field}; the probe measured it and nothing "
            f"downstream can read it. Carried: {sorted(carried)}")
    assert carried["tls_floor"] == "TLSv1_2"
    assert carried["tls_floor_certain"] is True
