"""Probes a brief names, and the ones it only names.

A brief writes `[TO CONFIRM: requires openssl s_client -status]` where it has
no measurement. That sentence is the provenance invariant working -- the
analyst declining to invent a number -- and F-05 is everything that was
missing after it: no way to run the probe, no way to record the answer, no
way to mark one settled.

**The brief's text is never executed.** It is prose written by a language
model, and a product that shelled out to a command it composed would have
built a remote-execution path out of a report. What happens instead is a
lookup: the text is matched against this registry, and the registry's own
Python runs. The command each probe carries is what a human would type to
settle the same question by hand -- it is a label and a source tag, not an
argv, and nothing here ever passes it to a shell.

**The target is never supplied by the caller either.** A probe runs against
the site the run belongs to, resolved from the database by the route. There
is no parameter on this request through which an operator, or anything
reaching the API in their name, can point a handshake at a host of their
choosing.

That was written as though it settled the question, and it did not (CQ-112).
The request carries no target; the *site record* does, and nothing validated
what went into it — `SiteIn.domain` is `Field(min_length=3)` and checks
nothing else, so a site created with domain `127.0.0.1` was two calls from a
TLS handshake against this machine, returned as an ordinary measurement with
`source: 'TLS handshake to 127.0.0.1:443 from this machine'`. The absent
parameter was never the safety property; the address check the crawler makes
is, and the probe path now makes the same one through the same predicate
(`api/app.py:_private_or_loopback`, behind the same
`CLAUDITSEO_ALLOW_ARBITRARY_START_URL`). Recorded here rather than quietly
reworded, because a module that argues from a property it does not enforce
reads as safer than one that says nothing.

**Two of the six are runnable, and four are not.** The `https-security`
entry named cipher ordering, chain completeness, OCSP stapling, apex
redirect, HTTP/2 and the origin inference as genuinely unmeasured. Chain
completeness and the apex redirect are answerable here with a socket and a
request. The other four are not, and they are left alone rather than
approximated:

- **OCSP stapling** has no API in Python's `ssl`; only the OpenSSL binary
  answers it, and `crawler/transport.py` decided for this whole area that a
  scanner is not shelled out to. That decision is followed, not reopened.
- **Cipher ordering** needs the handshake repeated with the client's
  preference reversed, and TLS 1.3's suites cannot be ordered through
  `set_ciphers` at all -- so the measurement would be about TLS 1.2 while
  reading as though it were about the server.
- **HTTP/2** needs `h2`, which is not a dependency. httpx without it
  negotiates 1.1 every time, so "no HTTP/2" would be a fact about this
  machine and not about the server -- the exact confusion `transport.py`
  built `NOT_OFFERED` to refuse.
- **The origin inference** behind a CDN is not measurable from the outside.

Those four keep rendering as `[TO CONFIRM: ...]` and offer nothing. That is
the feature, not a gap in it: the register's own words are "the honesty is
the feature, not the thing being removed".

The verdicts are pure functions over what came back, tested without a
socket, on `transport.py`'s reasoning: whether a handshake succeeds is the
network's business, and what its outcome *means* is ours -- and ours is the
part that can be wrong.
"""

from __future__ import annotations

import re
import socket
import ssl
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

from .crawler.types import USER_AGENT

TIMEOUT = 8.0

#: Every `[TO CONFIRM: ...]` a brief writes, capturing what it says it needs.
#: Non-greedy and bounded by the first `]`: the marker never spans a
#: paragraph, and a greedy match would swallow every item between the first
#: and the last.
CONFIRM_RE = re.compile(r"\[TO CONFIRM:\s*([^\]]*?)\s*\]")

#: A probe ran and the answer is a measurement.
MEASURED = "measured"
#: A probe ran and the network refused to answer. Recorded, and deliberately
#: not rendered as settled: a timeout is not a finding about the site.
FAILED = "failed"


@dataclass
class Measurement:
    probe_id: str
    target: str
    status: str
    value: str
    source: str
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"probe_id": self.probe_id, "target": self.target,
                "status": self.status, "value": self.value,
                "source": self.source, "detail": self.detail}


# --------------------------------------------------------------------------
# Chain completeness.
# --------------------------------------------------------------------------

#: What a chain handshake concluded. Prefixed, and not the bare words.
#:
#: `"complete"` is spelled here and nowhere else in `clauditseo/` on purpose:
#: it is the audit-run status owned by `persistence/runs.py`, and
#: `tests/test_status_vocabulary.py` forbids any other module spelling it --
#: because nineteen query sites once compared that literal and fifteen were
#: missed when a new status arrived. A certificate chain being complete is an
#: unrelated fact that happens to want the same English word, which is exactly
#: the ambiguity that rule exists to stop before it starts.
#:
#: Prefixing also matches the probe beside this one: `detail["state"]` is one
#: column shared by every probe, and `apex-redirect` writes `canonical`,
#: `split` and `one-host` into it. A per-probe vocabulary in a shared column
#: reads better named than bare.
CHAIN_COMPLETE = "chain-complete"
CHAIN_INCOMPLETE = "chain-incomplete"
CHAIN_UNVERIFIED = "unverified"


def chain_verdict(sent: int, built: int, error: str | None) -> tuple[str, str]:
    """Did the server transmit the intermediates, or did our trust store?

    The distinction is the whole question. `get_unverified_chain` is what
    came down the wire; `get_verified_chain` is what the chain became once
    the local store had contributed. A root is always local, so one
    certificate of difference is the healthy case and two is a server
    relying on its visitors already holding the intermediate -- which
    desktop browsers often do, from some other site, and mobile clients and
    API consumers often do not. That is the intermittent "works for me"
    certificate failure, and it is invisible to any check that only asks
    whether the handshake succeeded, because for the machine asking, it did.
    """
    if error:
        # An issuer that cannot be found locally *is* the finding: the server
        # sent an incomplete chain and nothing on this machine could finish
        # it. Any other failure is about the connection, not the chain.
        if "unable to get local issuer" in error.lower():
            return (CHAIN_INCOMPLETE,
                    "the chain could not be built: the server sent no usable "
                    "intermediate and no local certificate could complete it")
        return (CHAIN_UNVERIFIED,
                f"the handshake did not complete: {error}")
    extra = built - sent
    if extra <= 1:
        added = "the root only" if extra == 1 else "nothing added"
        return (CHAIN_COMPLETE,
                f"the server sent {_certs(sent)}; the chain verified with "
                f"{added} from this machine's trust store")
    return (CHAIN_INCOMPLETE,
            f"the server sent {_certs(sent)} but the verified chain needed "
            f"{built}: {_certs(extra - 1)} beyond the root came from this "
            "machine's trust store rather than from the server, so a client "
            "without them cached would fail")


def _certs(n: int) -> str:
    return f"{n} certificate" + ("" if n == 1 else "s")


def _run_chain(target: str) -> Measurement:
    host, port = _host_port(target)
    source = (f"TLS handshake to {host}:{port} from this machine "
              "-- the answer `openssl s_client -showcerts` reads off")
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                sent = len(tls.get_unverified_chain() or ())
                built = len(tls.get_verified_chain() or ())
    except Exception as exc:                      # noqa: BLE001 -- classified
        state, value = chain_verdict(0, 0, f"{type(exc).__name__}: {exc}")
        # An unfindable issuer is a measurement about the server; a timeout
        # is not, and must not reach the screen wearing a source tag.
        status = MEASURED if state == CHAIN_INCOMPLETE else FAILED
        return Measurement("cert-chain", target, status, value, source,
                           {"state": state, "sent": None, "built": None})
    state, value = chain_verdict(sent, built, None)
    return Measurement("cert-chain", target, MEASURED, value, source,
                       {"state": state, "sent": sent, "built": built})


# --------------------------------------------------------------------------
# The apex redirect.
# --------------------------------------------------------------------------

def apex_verdict(apex: dict, www: dict) -> tuple[str, str]:
    """Which host serves the site, and does the other one hand over?

    Both hosts answering on their own is not a redirect that failed; it is
    two sites, with every link, canonical and backlink split between them.
    Naming that is the point of asking.
    """
    if not apex.get("final") and not www.get("final"):
        return ("unverified",
                "neither the apex nor the www host answered: "
                + "; ".join(str(h.get("error") or "no answer")
                            for h in (apex, www)))
    if not apex.get("final"):
        return ("one-host",
                f"the apex host did not answer ({apex.get('error')}); "
                f"{_host_of(www['final'])} serves the site")
    if not www.get("final"):
        return ("one-host",
                f"the www host did not answer ({www.get('error')}); "
                f"{_host_of(apex['final'])} serves the site")

    apex_host, www_host = _host_of(apex["final"]), _host_of(www["final"])
    if apex_host == www_host:
        canonical = apex_host
        # Whichever request did not end where it started is the one that
        # handed over. Both can hand over -- an apex and a www that both
        # redirect to a third host is a perfectly ordinary arrangement, and
        # phrasing the answer around "the other one" would misname it.
        moved = [h for h in (apex, www) if _start_host(h) != canonical]
        if not moved:
            return ("canonical",
                    f"{canonical} serves the site and no redirect was needed")
        handovers = "; ".join(
            f"{_start_host(h)} redirects to {h['final']} -- {_chain_text(h)}"
            for h in moved)
        return ("canonical",
                f"{canonical} is the canonical host: {handovers}")
    return ("split",
            f"both hosts serve the site on their own: {apex['final']} and "
            f"{www['final']} -- neither redirects to the other")


def _start_host(host: dict) -> str:
    chain = host.get("chain") or []
    return _host_of(chain[0][0]) if chain else _host_of(host["final"])


def _chain_text(host: dict) -> str:
    steps = host.get("chain") or []
    return " -> ".join(f"{url} ({code})" for url, code in steps) or "one hop"


def _run_apex(target: str) -> Measurement:
    host, _ = _host_port(target)
    bare = host[4:] if host.startswith("www.") else host
    source = (f"one HTTPS request to each of {bare} and www.{bare} from this "
              "machine, redirects followed -- the answer `curl -sIL` reads off")
    apex, www = _fetch_host(bare), _fetch_host(f"www.{bare}")
    state, value = apex_verdict(apex, www)
    # Settled only when both hosts were actually reached. This probe's answer
    # is a *comparison*, and a comparison with one side missing has not
    # measured the thing the item asked about -- "www serves the site" is not
    # an answer to "does the apex hand over to it". The observation is stored
    # either way, and the offer stays: a host that timed out once is the case
    # the operator will want to try again, and a settled sentence produced by
    # a timeout is what the marker exists to prevent.
    settled = state in ("canonical", "split")
    return Measurement("apex-redirect", target,
                       MEASURED if settled else FAILED,
                       value, source,
                       {"state": state, "apex": apex, "www": www})


def _fetch_host(host: str) -> dict:
    import httpx

    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                          follow_redirects=True, max_redirects=5) as client:
            response = client.get(f"https://{host}/")
    except Exception as exc:                      # noqa: BLE001 -- reported
        return {"final": None, "chain": [],
                "error": f"{type(exc).__name__}: {exc}"}
    chain = [[str(r.url), r.status_code] for r in response.history]
    chain.append([str(response.url), response.status_code])
    return {"final": str(response.url), "chain": chain, "error": None}


# --------------------------------------------------------------------------
# The registry.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Probe:
    id: str
    label: str
    #: What a human would type to settle this by hand. Shown to the operator
    #: so the offer says what is about to happen, and never executed.
    command: str
    #: Matched against the text inside `[TO CONFIRM: ...]`. `subject` asks
    #: what the item is about and `qualifier` asks which aspect of it, and
    #: both have to hit -- with no word doing both jobs, which was the first
    #: version's defect. "chain" appeared in each, so "the redirect chain
    #: beyond three hops was not followed" matched the certificate probe on
    #: that one word and would have offered a TLS handshake as the answer to
    #: a question about redirects. A term precise enough to settle both at
    #: once (`showcerts`) may appear in both; a term as broad as "chain" may
    #: not appear in `subject` at all.
    subject: re.Pattern
    qualifier: re.Pattern
    run: Callable[[str], Measurement]


PROBES: dict[str, Probe] = {
    "cert-chain": Probe(
        id="cert-chain",
        label="Certificate chain completeness",
        command="openssl s_client -connect <host>:443 -showcerts",
        # `s_client` is in neither: `-showcerts` and `-status` are the same
        # command settling different questions, and the second is OCSP
        # stapling, which this product cannot measure at all.
        subject=re.compile(r"\b(certificates?|certs?|intermediates?|showcerts|"
                           r"ca bundle)\b", re.I),
        qualifier=re.compile(r"\b(chain|intermediates?|showcerts|completeness|"
                             r"complete|incomplete|bundle|inspected|sent)\b",
                             re.I),
        run=_run_chain),
    "apex-redirect": Probe(
        id="apex-redirect",
        label="Apex and www canonical host",
        command="curl -sIL https://<host>/ ; curl -sIL https://www.<host>/",
        # Neither a bare `www` nor a bare `curl`, and the running product is
        # what said so. Against a real https-security brief this matched
        # "HTTP/2/HTTP/3 availability not observable ... requires `curl
        # --http2 -I https://www.13acme.com.au/`" -- `www` out of the host in
        # the example command, `curl` out of the command itself. It would
        # have offered a redirect measurement as the answer to a question
        # about protocol negotiation, which is the failure the two-term rule
        # exists to prevent and which every fixture-only test passed over:
        # invented item text does not put a hostname inside the sentence.
        subject=re.compile(r"\b(apex|naked domain|root domain|non-www|"
                           r"canonical host)\b", re.I),
        qualifier=re.compile(r"\b(redirects?|redirected|redirecting|canonical|"
                             r"resolves?|resolved|serves?|served|points?|www)\b",
                             re.I),
        run=_run_apex),
}


def normalise(text: str) -> str:
    """The key an item is looked up by, on both sides of the wire.

    Every run of whitespace becomes one space. This is not tidying: it is
    what makes the screen's key and the server's key the same string, and
    the running product is what said so.

    A brief writes these markers inline, and they are long, so they wrap in
    the stored markdown. The server parses that markdown and sees the
    newline; the renderer joins a paragraph's lines with a space before
    tokenising, so the screen sees a space. Keyed on the raw text the two
    disagree for every wrapped marker, the lookup misses, and the item
    renders as plain `[TO CONFIRM: ...]` offering nothing -- which is
    indistinguishable, on screen, from an item this product genuinely cannot
    measure. Of thirteen items in the live `https-security` brief exactly one
    was runnable, and it was one of the wrapped ones.

    Invisible to every test that wrote its own fixture text: a marker typed
    into a test string is on one line.
    """
    return " ".join((text or "").split())


def probe_for(text: str) -> str | None:
    """Which registered probe, if any, settles what this item says it needs.

    Returns `None` far more often than not, and that is the intended
    behaviour rather than a shortfall: an unrecognised item is one this
    product cannot measure, and the register is explicit that such an item
    keeps saying so and offers nothing.
    """
    for probe in PROBES.values():
        if probe.subject.search(text) and probe.qualifier.search(text):
            return probe.id
    return None


def confirm_items(report: str) -> list[dict]:
    """Every `[TO CONFIRM: ...]` in a brief, in document order, deduped.

    Deduped on the exact text because the same question is usually raised in
    the analysis and again in the remediation, and the operator settles a
    question once rather than once per mention. Order is the report's, so
    the list reads down the page.
    """
    seen: dict[str, dict] = {}
    for match in CONFIRM_RE.finditer(report or ""):
        text = normalise(match.group(1))
        if text in seen:
            continue
        probe_id = probe_for(text)
        seen[text] = {"text": text, "probe": probe_id,
                      "command": PROBES[probe_id].command if probe_id else None,
                      "label": PROBES[probe_id].label if probe_id else None}
    return list(seen.values())


def run_probe(probe_id: str, target: str) -> Measurement:
    """Run one registered probe against the run's own site.

    `target` comes from the database, never from the request body -- see the
    module docstring. `probe_id` is a registry key or this raises, so an
    unknown id cannot fall through to anything executable.
    """
    if probe_id not in PROBES:
        raise KeyError(probe_id)
    return PROBES[probe_id].run(target)


def _host_port(target: str) -> tuple[str, int]:
    parts = urlsplit(target if "//" in target else f"https://{target}")
    return parts.hostname or "", parts.port or 443


def _host_of(url: str) -> str:
    return urlsplit(url).hostname or url
