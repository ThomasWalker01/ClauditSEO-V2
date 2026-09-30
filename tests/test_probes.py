"""Running the probe a brief names (`FEATURES.md` F-05).

**Ordinary tests, not guards**, on the rule `FEATURES.md` states for its
entries and `test_heading_fault.py` and `test_section_refresh.py` record for
F-07 and F-06: the behaviour did not exist, so there was no prior failure to
observe and DISCIPLINE rule 1 does not apply. `probes.py`, `probe_results`
and both routes are new in this commit; `[TO CONFIRM: …]` reached the screen
as literal text and nothing anywhere read it.

The split follows `test_transport.py`, which is the nearest neighbour and
made the argument first: whether a handshake succeeds is the network's
business, and what its outcome *means* is ours -- so the meaning is a pure
function tested without a socket, and the socket is exercised only where it
can be pointed at loopback.

Nothing here reaches the internet. The one test that opens a real connection
opens it to a closed port on 127.0.0.1, and it is there for the distinction
that matters most in this feature: a probe that could not reach the host has
measured nothing, and must not render as though it had.
"""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.probes import (CHAIN_COMPLETE, CHAIN_INCOMPLETE,
                               CHAIN_UNVERIFIED, FAILED, MEASURED,
                               apex_verdict, chain_verdict, confirm_items,
                               probe_for, run_probe)

# --- which items name a probe this product can actually run -----------------

def test_an_item_naming_the_certificate_chain_names_a_runnable_probe():
    assert probe_for("intermediate certificates not inspected; requires "
                     "openssl s_client -showcerts") == "cert-chain"


def test_an_item_naming_the_apex_redirect_names_a_runnable_probe():
    assert probe_for("whether the apex redirects to www was not measured") \
        == "apex-redirect"


@pytest.mark.parametrize("text,why", [
    ("requires openssl s_client -status",
     "OCSP stapling: no API in Python's ssl, and this area does not shell out"),
    ("cipher ordering requires a full TLS scan such as testssl.sh",
     "cipher order needs the handshake repeated with preference reversed"),
    ("HTTP/2 support was not recorded for this origin",
     "needs h2, which is not a dependency -- the answer would be about us"),
    ("the origin server behind the CDN could not be inferred",
     "not measurable from outside at all"),
])
def test_the_four_this_product_cannot_measure_name_nothing(text, why):
    """The negative half of the signal, and the half that gets dropped.

    Every one of these is a real item from the `https-security` brief. The
    register's words are that the honesty is the feature, not the thing being
    removed -- so an item this product cannot settle has to keep saying so,
    and a probe offered against any of these would be a measurement of
    something else wearing this question's label.
    """
    assert probe_for(text) is None, why


#: Item text lifted verbatim from a real `https-security` brief, on the run
#: this feature was verified against at `http://localhost:8020`. Every other
#: negative case in this file was written by hand, and hand-written item text
#: does not contain a hostname or an example command -- which is exactly why
#: none of them caught this. The first one matched `apex-redirect` on the
#: `www` inside the host and the `curl` inside the command, and would have
#: offered a redirect measurement as the answer to a protocol question.
LIVE_ITEMS_THAT_MUST_OFFER_NOTHING = [
    "HTTP/2/HTTP/3 availability not observable from supplied input - requires "
    "`curl --http2 -I https://www.13acme.com.au/` or ALPN inspection",
    "full page HTML body",
    "sitemap XML content and HTTP response headers",
    "list of locale/regional URL variants that should form a cluster with "
    "`https://www.13acme.com.au/`, if any exist",
]


@pytest.mark.parametrize("text", LIVE_ITEMS_THAT_MUST_OFFER_NOTHING)
def test_real_brief_items_this_product_cannot_measure_offer_nothing(text):
    assert probe_for(text) is None


def test_the_real_brief_item_that_does_name_a_chain_probe_still_matches():
    """The other side, from the same brief, so the fix above cannot be a
    matcher that has quietly stopped matching anything."""
    assert probe_for("requires `openssl s_client -showcerts` or SSL Labs "
                     "chain view.") == "cert-chain"


def test_a_redirect_chain_is_not_a_certificate_chain():
    """Why the match needs a subject *and* a qualifier.

    "chain" on its own appears in redirect chains, supply chains and value
    chains. A TLS handshake offered against a redirect chain would answer a
    question nobody asked and label it with one they did.
    """
    assert probe_for("the redirect chain beyond three hops was not followed") \
        is None


def test_items_come_back_in_document_order_and_once_each():
    report = (
        "## Analysis\n"
        "TLS floor [TO CONFIRM: requires openssl s_client -status]\n"
        "Chain [TO CONFIRM: intermediate certificates not inspected]\n"
        "## Remediation\n"
        "Chain again [TO CONFIRM: intermediate certificates not inspected]\n")
    items = confirm_items(report)
    assert [i["text"] for i in items] == [
        "requires openssl s_client -status",
        "intermediate certificates not inspected"]
    assert [i["probe"] for i in items] == [None, "cert-chain"]


def test_a_runnable_item_carries_the_command_and_an_unrunnable_one_does_not():
    """The offer has to say what is about to happen; the refusal has nothing
    to say, and says nothing rather than something vague."""
    runnable, unrunnable = confirm_items(
        "[TO CONFIRM: intermediate certificates not inspected]\n"
        "[TO CONFIRM: requires openssl s_client -status]")
    assert "showcerts" in runnable["command"]
    assert runnable["label"]
    assert unrunnable["command"] is None and unrunnable["label"] is None


def test_a_marker_that_wraps_is_keyed_as_one_line():
    """The second defect the running product found, and the reason every
    test here that writes its own item text could not have found it.

    These markers are long, so a brief wraps them across lines. The renderer
    joins a paragraph's lines with a space before tokenising, so the screen's
    key has a space where the stored markdown has a newline. Keyed on raw
    text the two disagree, the lookup misses, and a runnable item renders as
    a plain `[TO CONFIRM: …]` that offers nothing — which on screen is
    indistinguishable from an item this product cannot measure. It was one of
    thirteen in the live `https-security` brief, and it was the runnable one.
    """
    wrapped = ("Chain [TO CONFIRM: intermediate certificates not\n"
               "inspected; requires openssl s_client -showcerts]\n")
    flat = ("Chain [TO CONFIRM: intermediate certificates not inspected; "
            "requires openssl s_client -showcerts]\n")
    assert confirm_items(wrapped) == confirm_items(flat)
    assert confirm_items(wrapped)[0]["probe"] == "cert-chain"


def test_the_key_is_what_the_renderer_will_have_after_joining_lines():
    """Stated as the contract rather than left implicit in a regex: the
    screen normalises the same way, and `markdown.tsx` names this function
    where it does it."""
    from clauditseo.probes import normalise

    assert normalise("  a \n  b\tc  ") == "a b c"


def test_a_brief_that_confirmed_everything_produces_no_items():
    assert confirm_items("Every claim here is measured.") == []


def test_one_marker_does_not_swallow_the_next():
    """Non-greedy, or a report's first and last markers become one item
    containing everything between them."""
    items = confirm_items("[TO CONFIRM: a] and [TO CONFIRM: b]")
    assert [i["text"] for i in items] == ["a", "b"]


# --- what an outcome means: chain completeness ------------------------------

def test_a_server_sending_its_intermediates_has_a_complete_chain():
    state, value = chain_verdict(sent=2, built=3, error=None)
    assert state == CHAIN_COMPLETE
    assert "2 certificates" in value


def test_a_leaf_issued_by_a_trusted_root_needs_no_intermediate():
    state, _ = chain_verdict(sent=1, built=2, error=None)
    assert state == CHAIN_COMPLETE


def test_an_intermediate_supplied_by_our_own_store_is_an_incomplete_chain():
    """The defect this probe exists to find.

    The handshake succeeded, so every check that only asks "did it connect"
    reports a healthy site. It is healthy for a client that already holds the
    intermediate and broken for one that does not -- which is the shape of
    the intermittent certificate failure nobody can reproduce.
    """
    state, value = chain_verdict(sent=1, built=3, error=None)
    assert state == CHAIN_INCOMPLETE
    assert "1 certificate beyond the root" in value


def test_an_issuer_nothing_can_find_is_a_measurement_about_the_server():
    state, _ = chain_verdict(0, 0, "SSLCertVerificationError: unable to get "
                                   "local issuer certificate")
    assert state == CHAIN_INCOMPLETE


def test_a_connection_that_failed_measured_nothing():
    """A timeout is evidence about the network, not about the site --
    `transport.py`'s `FAILED`, in this feature's vocabulary."""
    state, value = chain_verdict(0, 0, "TimeoutError: timed out")
    assert state == CHAIN_UNVERIFIED
    assert "did not complete" in value


# --- what an outcome means: the apex redirect -------------------------------

def _host(start: str, final: str, code: int = 200) -> dict:
    chain = [[start, 301], [final, code]] if start != final else [[final, code]]
    return {"final": final, "chain": chain, "error": None}


def test_an_apex_that_hands_over_to_www_names_the_canonical_host():
    state, value = apex_verdict(
        _host("https://x.test/", "https://www.x.test/"),
        _host("https://www.x.test/", "https://www.x.test/"))
    assert state == "canonical"
    assert "www.x.test is the canonical host" in value
    assert "x.test redirects to https://www.x.test/" in value


def test_www_handing_over_to_the_apex_is_the_same_answer_the_other_way():
    state, value = apex_verdict(
        _host("https://x.test/", "https://x.test/"),
        _host("https://www.x.test/", "https://x.test/"))
    assert state == "canonical"
    assert "x.test is the canonical host" in value


def test_both_hosts_serving_the_site_is_named_rather_than_called_a_failure():
    """Not a redirect that broke: two sites, with every link, canonical and
    backlink split between them. That is the finding."""
    state, value = apex_verdict(
        _host("https://x.test/", "https://x.test/"),
        _host("https://www.x.test/", "https://www.x.test/"))
    assert state == "split"
    assert "neither redirects to the other" in value


def test_a_host_that_did_not_answer_is_reported_as_not_answering():
    state, value = apex_verdict(
        {"final": None, "chain": [], "error": "ConnectError: nope"},
        _host("https://www.x.test/", "https://www.x.test/"))
    assert state == "one-host"
    assert "the apex host did not answer" in value


def test_neither_host_answering_settles_nothing():
    state, _ = apex_verdict(
        {"final": None, "chain": [], "error": "ConnectError: a"},
        {"final": None, "chain": [], "error": "ConnectError: b"})
    assert state == "unverified"


def test_a_comparison_missing_one_side_is_not_a_measurement(monkeypatch):
    """One rule across both probes: an answer is settled only when every
    input it compares was actually observed.

    "www.x serves the site" is a true sentence and not an answer to "does the
    apex hand over to it" -- and if the apex merely timed out, storing it as
    settled would replace the marker with a claim produced by a timeout.
    """
    from clauditseo import probes

    hosts = {"x.test": {"final": None, "chain": [], "error": "ConnectError: x"},
             "www.x.test": _host("https://www.x.test/", "https://www.x.test/")}
    monkeypatch.setattr(probes, "_fetch_host", lambda h: hosts[h])
    measured = probes.run_probe("apex-redirect", "www.x.test")
    assert measured.detail["state"] == "one-host"
    assert measured.status == FAILED


def test_both_hosts_reached_is_a_measurement(monkeypatch):
    """The other side of the same rule, so it cannot be satisfied by a probe
    that never settles anything."""
    from clauditseo import probes

    hosts = {"x.test": _host("https://x.test/", "https://www.x.test/"),
             "www.x.test": _host("https://www.x.test/", "https://www.x.test/")}
    monkeypatch.setattr(probes, "_fetch_host", lambda h: hosts[h])
    measured = probes.run_probe("apex-redirect", "https://www.x.test/")
    assert measured.status == MEASURED
    assert "www.x.test is the canonical host" in measured.value


# --- the socket, pointed at loopback ----------------------------------------

def test_a_refused_connection_is_stored_as_failed_and_never_as_settled():
    """The one test here that opens a real socket, and the reason it exists.

    `status` is what the screen reads to decide whether an item is settled.
    A probe that could not reach the host has confirmed nothing, and the
    worst outcome this feature could ship is a `[TO CONFIRM: …]` replaced by
    a confident sentence produced by a timeout.
    """
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()

    measured = run_probe("cert-chain", f"127.0.0.1:{port}")
    assert measured.status == FAILED
    assert measured.detail["state"] == CHAIN_UNVERIFIED


def test_an_unknown_probe_id_cannot_reach_anything_that_runs():
    with pytest.raises(KeyError):
        run_probe("rm-rf", "x.test")


# --- through the API --------------------------------------------------------

BRIEF = ("## Transport\n"
         "OCSP stapling [TO CONFIRM: requires openssl s_client -status]\n"
         "Chain [TO CONFIRM: intermediate certificates not inspected]\n")


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "probes.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client_id = repo.create_client(conn, op, "Probe Co")
    site_id = repo.create_site(conn, client_id, "probe.fixture")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, "https-security",
                             {"report": BRIEF, "model": "m"})
    conn.close()
    return TestClient(create_app(db_path=db)), run_id


def _canned(monkeypatch, status=MEASURED, value="the server sent 2 certificates"):
    from clauditseo import probes

    def fake(probe_id: str, target: str):
        return probes.Measurement(probe_id, target, status, value,
                                  "TLS handshake to " + target,
                                  {"state": CHAIN_COMPLETE})

    monkeypatch.setattr(probes, "run_probe", fake)


def test_the_items_a_run_raised_reach_the_screen_with_their_verdicts(api):
    client, run_id = api
    body = client.get(f"/api/runs/{run_id}/probes").json()
    by_text = {i["text"]: i for i in body["items"]}
    assert by_text["intermediate certificates not inspected"]["probe"] == "cert-chain"
    assert by_text["requires openssl s_client -status"]["probe"] is None
    assert body["target"] == "probe.fixture"
    assert body["results"] == []


def test_reading_the_items_spends_nothing_and_measures_nothing(api, monkeypatch):
    """The read runs on render, so it must not be able to reach the network
    at all -- the offer is the operator's click, not a page load."""
    from clauditseo import probes

    def explode(*_a, **_k):
        raise AssertionError("the read ran a probe")

    monkeypatch.setattr(probes, "run_probe", explode)
    client, run_id = api
    assert client.get(f"/api/runs/{run_id}/probes").status_code == 200


def test_running_a_probe_records_the_result_against_that_run(api, monkeypatch):
    _canned(monkeypatch)
    client, run_id = api
    posted = client.post(f"/api/runs/{run_id}/probes/cert-chain")
    assert posted.status_code == 200
    assert posted.json()["value"] == "the server sent 2 certificates"

    stored = client.get(f"/api/runs/{run_id}/probes").json()["results"]
    assert len(stored) == 1
    assert stored[0]["probe_id"] == "cert-chain"
    assert stored[0]["status"] == MEASURED
    assert stored[0]["created_at"]


def test_a_stored_result_carries_the_source_it_was_measured_from(api, monkeypatch):
    """A measured value with no provenance is the thing `[TO CONFIRM: …]`
    exists to prevent; replacing one with the other would be a regression
    wearing the shape of the feature."""
    _canned(monkeypatch)
    client, run_id = api
    client.post(f"/api/runs/{run_id}/probes/cert-chain")
    stored = client.get(f"/api/runs/{run_id}/probes").json()["results"][0]
    assert stored["source"].startswith("TLS handshake to probe.fixture")


def test_the_probe_runs_against_the_runs_own_site_not_a_supplied_host(api,
                                                                     monkeypatch):
    """There is no target on the wire, and this is what says so.

    The question comes out of prose a language model wrote. If the host were
    a parameter, a brief could name one -- so the host is read from the
    database and the request has nowhere to put another.
    """
    seen: list[str] = []
    from clauditseo import probes

    def fake(probe_id, target):
        seen.append(target)
        return probes.Measurement(probe_id, target, MEASURED, "v", "s", {})

    monkeypatch.setattr(probes, "run_probe", fake)
    client, run_id = api
    client.post(f"/api/runs/{run_id}/probes/cert-chain",
                json={"target": "evil.test", "host": "evil.test"})
    assert seen == ["probe.fixture"]


def _api_for_domain(tmp_path, monkeypatch, domain: str):
    """The `api` fixture with the site's domain chosen by the caller.

    `repo.create_site` is called directly rather than through the API,
    because the API's own shape check is CQ-108 and is still open: writing
    this through `POST /api/sites` would make the test pass for the wrong
    reason the day that lands.
    """
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "probe-target.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client_id = repo.create_client(conn, op, "Probe Co")
    site_id = repo.create_site(conn, client_id, domain)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.close()
    return TestClient(create_app(db_path=db)), run_id


@pytest.mark.parametrize("domain", [
    "127.0.0.1", "10.0.0.5", "::1",
    # CQ-117. The three above are the shapes CQ-112's fix was written for, and
    # each is a bare literal. `ipaddress.ip_address` answers False for anything
    # carrying a port or a trailing dot, so the rule walked past the shapes the
    # product already stores — UX-40 records that a site can be stored as
    # `host:port`, and the audit drove `127.0.0.1:443` end to end for a real
    # `connect()` to loopback. `probes._host_port` resolves all six to the same
    # two addresses, which is why one predicate has to as well.
    #
    # Three of these four failed against the unfixed source and one did not:
    # `[::1]:443` was already refused, by the *dotless* clause rather than by
    # the address rule, so it proves nothing about CQ-117 and is kept only to
    # show the fix does not lose it. The three that fail are the guard.
    "127.0.0.1:443", "10.0.0.5:8443", "127.0.0.1.", "[::1]:443",
])
def test_a_site_recorded_as_a_private_address_cannot_be_handshaken(
        tmp_path, monkeypatch, domain):
    """CQ-112, widened by CQ-117. The crawler refuses these hosts; the probe
    path did not, and then refused only the bare literal forms of them.

    The two paths reach the same kind of place — `_validate_start_url`
    refuses loopback and private literals before the crawler opens a socket,
    and `_probe_target` opened one against whatever the site record held.
    Reproduced by the audit against a throwaway database: a site created with
    domain `127.0.0.1` returned HTTP 200 and
    `source: 'TLS handshake to 127.0.0.1:443 from this machine'`.

    The dead end worth recording: `_validate_start_url` has always judged
    `urlsplit(start_url).hostname` and `_probe_refusal` judged the stored
    string, so the two predicates were never the same predicate — they only
    agreed on the inputs the first tests chose. A parametrisation drawn from
    the reproduction rather than from the shapes the storage layer accepts is
    what let that stand.

    The assertion is on `seen`, not only on the status. A refusal that still
    opened the connection would satisfy a status check and would have already
    done the thing the check exists to prevent.
    """
    seen: list[str] = []
    from clauditseo import probes

    def fake(probe_id, target):
        seen.append(target)
        return probes.Measurement(probe_id, target, MEASURED, "v", "s", {})

    monkeypatch.setattr(probes, "run_probe", fake)
    client, run_id = _api_for_domain(tmp_path, monkeypatch, domain)
    refused = client.post(f"/api/runs/{run_id}/probes/cert-chain")
    assert refused.status_code == 422, refused.text
    assert seen == [], f"a socket was opened at {seen} before the refusal"


def test_a_site_whose_domain_is_not_a_host_cannot_be_handshaken(
        tmp_path, monkeypatch):
    """The other half of CQ-112: a name with no dot is not a registrable host.

    `SiteIn.domain` is `Field(min_length=3)` and checks nothing else, so
    `localhost` — three characters, resolvable, and pointing at this machine —
    reaches `_probe_target` intact.
    """
    seen: list[str] = []
    from clauditseo import probes

    def fake(probe_id, target):
        seen.append(target)
        return probes.Measurement(probe_id, target, MEASURED, "v", "s", {})

    monkeypatch.setattr(probes, "run_probe", fake)
    client, run_id = _api_for_domain(tmp_path, monkeypatch, "localhost")
    refused = client.post(f"/api/runs/{run_id}/probes/cert-chain")
    assert refused.status_code == 422, refused.text
    assert seen == [], f"a socket was opened at {seen} before the refusal"


def test_the_escape_hatch_the_crawler_offers_is_the_one_the_probe_offers(
        tmp_path, monkeypatch):
    """One switch, not two. `CLAUDITSEO_ALLOW_ARBITRARY_START_URL` is how the
    operator audits a staging target, and a probe against that same site has
    to follow it or the setting means different things on two paths.
    """
    monkeypatch.setenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", "1")
    seen: list[str] = []
    from clauditseo import probes

    def fake(probe_id, target):
        seen.append(target)
        return probes.Measurement(probe_id, target, MEASURED, "v", "s", {})

    monkeypatch.setattr(probes, "run_probe", fake)
    client, run_id = _api_for_domain(tmp_path, monkeypatch, "127.0.0.1")
    allowed = client.post(f"/api/runs/{run_id}/probes/cert-chain")
    assert allowed.status_code == 200, allowed.text
    assert seen == ["127.0.0.1"]


def test_re_running_a_probe_replaces_its_answer_rather_than_stacking_one(
        api, monkeypatch):
    """Re-running is how a fix is checked, so the newest answer is the one on
    screen -- a history would put the stale one on top."""
    client, run_id = api
    _canned(monkeypatch, value="the server sent 1 certificate")
    client.post(f"/api/runs/{run_id}/probes/cert-chain")
    _canned(monkeypatch, value="the server sent 2 certificates")
    client.post(f"/api/runs/{run_id}/probes/cert-chain")

    stored = client.get(f"/api/runs/{run_id}/probes").json()["results"]
    assert len(stored) == 1
    assert stored[0]["value"] == "the server sent 2 certificates"


def test_a_probe_this_product_does_not_have_is_refused_not_attempted(api):
    client, run_id = api
    refused = client.post(f"/api/runs/{run_id}/probes/ocsp-stapling")
    assert refused.status_code == 404
    assert "cannot measure" in refused.json()["detail"]


def test_a_failed_probe_is_recorded_as_failed(api, monkeypatch):
    _canned(monkeypatch, status=FAILED, value="the handshake did not complete")
    client, run_id = api
    client.post(f"/api/runs/{run_id}/probes/cert-chain")
    stored = client.get(f"/api/runs/{run_id}/probes").json()["results"][0]
    assert stored["status"] == FAILED


# --- clauses 3 and 4, on the screen, in a browser ---------------------------
#
# What a component *draws* in a state is not readable from the source, which
# is `test_accessibility_headline.py`'s argument for F-09 and applies here
# with the same force: the difference between an item that renders settled
# and one that renders `[TO CONFIRM: …]` beside an offer is the whole
# acceptance signal, and every static check that could be written would pass
# on a component that drew neither. So these run at a real server, in a real
# browser, against the built bundle.
#
# Both amend what was *stored* rather than arranging a screen state, on
# `test_heading_fault.py`'s reasoning: the case being rendered is a real
# stored brief and a real stored measurement, which is the only way the
# signal's second sentence can be read honestly.

import json
import sqlite3

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

#: The two conditions the live tests need, copied from `test_heading_fault.py`
#: rather than invented — the same browser and the same built bundle.
#: Guarded at collection: the `python` job installs no extras by design, so a
#: `pytest.skip` inside the body would turn a skip into a red run. A skip is
#: not the clause going quiet — `.github/workflows/ci.yml` runs this file in
#: `rendered-a11y` too, where both conditions hold and the job fails on any
#: skip.
def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@pytest.fixture()
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            yield pg
        finally:
            browser.close()


SCREEN_BRIEF = (
    "## Transport\n\n"
    "OCSP stapling was not verified [TO CONFIRM: requires openssl s_client "
    "-status].\n\n"
    "The chain was not inspected [TO CONFIRM: intermediate certificates not "
    "inspected].\n")


def stage_brief(db: str, run_id: str, result: dict | None = None) -> None:
    """Put a brief — and optionally an answer — where the screen reads them.

    The fixture database is shared, so both callers remove what they added.
    """
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT OR REPLACE INTO expert_reports (run_id, tool_id, model_id,"
        " report, findings, figures, created_at)"
        " VALUES (?, 'security', 'test-model', ?, '[]', '[]',"
        " '2026-08-19T00:00:00Z')", (run_id, SCREEN_BRIEF))
    if result:
        conn.execute(
            "INSERT OR REPLACE INTO probe_results (run_id, probe_id, target,"
            " status, value, source, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '2026-08-19T01:00:00Z')",
            (run_id, result["probe_id"], "fixture.test", result["status"],
             result["value"], result["source"], json.dumps({})))
    conn.commit()
    conn.close()


def unstage(db: str, run_id: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM expert_reports WHERE run_id=? AND"
                 " tool_id='security'", (run_id,))
    conn.execute("DELETE FROM probe_results WHERE run_id=?", (run_id,))
    conn.commit()
    conn.close()


def open_the_brief(pg, base: str, run_id: str) -> None:
    """Admin's Workbench tab on this run, with the security brief's report
    open. The list of briefs by phase stood on the run page until 2026-09-03;
    it is parked under Admin now, against the selection's audit, and `?run=`
    is how a route names the audit it wants selected."""
    pg.goto(f"{base}/#/admin?tab=workbench&run={run_id}", wait_until="load")
    pg.wait_for_selector(".arow", timeout=20_000)
    pg.click(".arow:has-text('Security & transport') button.tone-nav")
    pg.wait_for_selector(".to-confirm-text", timeout=20_000)
    pg.wait_for_timeout(400)


@live
def test_only_the_item_naming_a_runnable_probe_offers_anything(served,
                                                               browser_page):
    """Both halves of the signal, on one screen, in one brief.

    Two unresolved questions, written the way the analyst writes them. One
    names something this product can measure and one does not, and the
    difference has to be visible without leaving the paragraph.
    """
    base, ids = served
    stage_brief(ids["db"], ids["run"])
    try:
        open_the_brief(browser_page, base, ids["run"])
        markers = browser_page.eval_on_selector_all(
            ".to-confirm-text", "els => els.map(e => e.textContent)")
        offers = browser_page.eval_on_selector_all(
            ".to-confirm-run", "els => els.map(e => e.textContent)")
    finally:
        unstage(ids["db"], ids["run"])

    assert len(markers) == 2, markers
    # The unrunnable one still says exactly what it said before.
    assert any("openssl s_client -status" in m and m.startswith("[TO CONFIRM:")
               for m in markers), markers
    assert len(offers) == 1, offers
    assert "Certificate chain completeness" in offers[0]


@live
def test_a_measured_item_renders_settled_with_its_value_and_its_source(
        served, browser_page):
    """Clause 3, read off the screen rather than off the endpoint.

    The source tag is asserted beside the value deliberately. A measured
    sentence that arrived with no provenance would be the product doing the
    one thing `[TO CONFIRM: …]` exists to stop it doing, and it would look
    like success.
    """
    base, ids = served
    stage_brief(ids["db"], ids["run"], result={
        "probe_id": "cert-chain", "status": "measured",
        "value": "the server sent 2 certificates; the chain verified with "
                 "the root only from this machine's trust store",
        "source": "TLS handshake to fixture.test:443 from this machine"})
    try:
        open_the_brief(browser_page, base, ids["run"])
        settled = browser_page.eval_on_selector_all(
            ".confirmed-value", "els => els.map(e => e.textContent)")
        sources = browser_page.eval_on_selector_all(
            ".confirmed-source", "els => els.map(e => e.textContent)")
        remaining = browser_page.eval_on_selector_all(
            ".to-confirm-text", "els => els.map(e => e.textContent)")
    finally:
        unstage(ids["db"], ids["run"])

    assert len(settled) == 1, settled
    assert "the server sent 2 certificates" in settled[0]
    assert "TLS handshake to fixture.test:443" in sources[0]
    # And the other one is untouched: settling one question does not settle
    # the brief. This is the clause that would go quiet first.
    assert len(remaining) == 1, remaining
    assert "openssl s_client -status" in remaining[0]


# --- rule 3: every screen that renders a brief, not the three I found -------

def test_every_brief_on_every_screen_can_settle_its_own_items():
    """Enumerated from the source, not from a list written by hand.

    A brief is opened from four places — the briefs panel, the run page's two
    report modals and the client screen's section reading — and a probe
    offered on one of them and not the others is exactly the partial fix
    DISCIPLINE rule 3 exists to stop. A hard-coded list of three is how that
    passes, so this reads the call sites out of the bundle's own source.

    The one exemption is named and justified rather than pattern-matched: a
    client deliverable is read where nothing can be run, so its markers stay
    text. It is imported under a different name for that reason, and a new
    consumer fails this until somebody decides which of the two it is.

    The sweep catches a fifth `<ReportView` in `App.tsx`, which is the
    *other* component of that name — `views.ReportView`, the screen that
    generates a deliverable. It already takes a `runId` for its own reasons
    and so passes here without meaning anything. Left in rather than
    special-cased: a name collision between two components is worth having
    visible, and excluding it by filename is the hard-coded list this test
    exists to avoid.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    missing = []
    for path in sorted(src.glob("*.tsx")):
        if path.name == "markdown.tsx":          # where the component lives
            continue
        text = path.read_text(encoding="utf-8")
        for n, line in enumerate(text.split("\n")):
            if "<ReportView" not in line:
                continue
            # The prop may wrap onto the following line.
            window = "\n".join(text.split("\n")[n:n + 3])
            if "runId" not in window:
                missing.append(f"{path.name}:{n + 1}")

    assert missing == [], (
        "these render a brief with no run to settle its items against: "
        + ", ".join(missing))


def test_the_deliverable_screen_is_the_exemption_and_still_takes_it():
    """The other half, so the guard above cannot be satisfied by wiring a run
    into the one place that must not have one."""
    from pathlib import Path

    views = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
             / "views.tsx").read_text(encoding="utf-8")
    assert "<RenderedMarkdown source={markdown} />" in views
    assert "<RenderedMarkdown source={markdown} runId" not in views


# --- the table this migration had to take back ------------------------------

def test_the_migration_reconciles_a_table_left_by_the_abandoned_attempt(tmp_path):
    """Observed at the running product, not reasoned about here first.

    An earlier abandoned attempt at F-05 (git stash `ffca91d`, untracked
    files only) shipped its own `0025_probe_results.sql` with a different
    shape, and it had already been applied to the operator's live database
    before the work was set aside. So `probe_results` existed there, keyed on
    `(run_id, tool_id, item_key)`, and `0025_probe_results.sql` was already
    in `schema_migrations`.

    Every layer of that is silent. A same-named migration is skipped by
    filename; `CREATE TABLE IF NOT EXISTS` is skipped by name; and the whole
    suite passes either way, because a fresh database has neither the row nor
    the table. The first real probe against the running product returned
    HTTP 500:

        sqlite3.OperationalError: table probe_results has no column named target

    This is the case that produced, and it is the one thing in this file that
    is a guard rather than an ordinary test — the failure was seen before the
    fix, at `http://localhost:8020`, with that message.
    """
    import sqlite3 as sq
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate

    db = tmp_path / "ghost.db"
    raw = sq.connect(db)
    raw.executescript(
        "CREATE TABLE schema_migrations (filename TEXT PRIMARY KEY);"
        "INSERT INTO schema_migrations (filename)"
        " VALUES ('0025_probe_results.sql');"
        "CREATE TABLE probe_results (run_id TEXT NOT NULL, tool_id TEXT NOT"
        " NULL, item_key TEXT NOT NULL, probe_id TEXT NOT NULL, value TEXT,"
        " detail TEXT, source TEXT, created_at TEXT);")
    raw.commit()
    raw.close()

    conn = connect(db)
    migrate(conn)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(probe_results)")}
    conn.close()

    assert "target" in columns, columns
    assert "status" in columns, columns
    # And the shape the abandoned attempt used is gone rather than merged, so
    # nothing downstream can read a column that is no longer written.
    assert "item_key" not in columns, columns


# --- one reader of `sites.domain`, not five (CQ-132, CQ-120) ---------------

def test_a_real_domain_beginning_with_the_four_characters_http_is_probed(
        tmp_path, monkeypatch):
    """CQ-132. `httpwatch.com` is a real domain and `startswith("http")` is
    not a test for a scheme.

    `crawl.start_url_for`'s docstring diagnosed exactly this and named the
    input; the fix stayed in `crawl.py` while four copies of the same two
    lines went on shipping in `api/app.py` and `reporting/generate.py`.
    `_probe_target` is the copy that falls back with `or ""` rather than
    `or domain`, so it does not merely mangle the host -- it loses it, and
    the route then answers 422 "this run has no site host to probe" about a
    site whose host is in the record.

    The assertion is on `seen`, not only on the status: the defect is that
    the handshake never happened, so a status check alone would pass the day
    the refusal is reworded.
    """
    seen: list[str] = []
    from clauditseo import probes

    def fake(probe_id, target):
        seen.append(target)
        return probes.Measurement(probe_id, target, MEASURED, "v", "s", {})

    monkeypatch.setattr(probes, "run_probe", fake)
    client, run_id = _api_for_domain(tmp_path, monkeypatch, "httpwatch.com")
    ran = client.post(f"/api/runs/{run_id}/probes/cert-chain")
    assert ran.status_code == 200, ran.text
    assert seen == ["httpwatch.com"], (
        "the site's own host never reached the probe")


def test_a_domain_urlsplit_cannot_parse_is_refused_rather_than_crashing(
        tmp_path, monkeypatch):
    """CQ-120. `SiteIn.domain` is `Field(min_length=3)` and nothing else, so
    `a]b` is stored; `_probe_refusal` then hands it to `urlsplit`, which
    raises `ValueError: Invalid IPv6 URL` -- an unhandled 500 with no
    `detail`, on the same field the route answers 422 for on every host the
    tests above parametrise.

    Named as first lever by reports 060 and 061 and deferred by the cohort
    rule both times.

    Not a claim that `a]b` should be storable: that is CQ-108, and it is
    gated on a back-fill decision recorded in `audits/DISPOSITIONS.md`. This
    asserts only that a row already in the database cannot crash the route
    that reads it.
    """
    seen: list[str] = []
    from clauditseo import probes

    def fake(probe_id, target):
        seen.append(target)
        return probes.Measurement(probe_id, target, MEASURED, "v", "s", {})

    monkeypatch.setattr(probes, "run_probe", fake)
    client, run_id = _api_for_domain(tmp_path, monkeypatch, "a]b")
    refused = client.post(f"/api/runs/{run_id}/probes/cert-chain")
    assert refused.status_code == 422, refused.text
    assert refused.json().get("detail"), "a refusal with nothing to read"
    assert seen == [], f"a socket was opened at {seen} before the refusal"


# --- the same refusal at the four doors an operator types into ---------------

def _api_for_typed_url(tmp_path, monkeypatch, domain: str = "example.com"):
    """`_api_for_domain`'s sibling, returning the site id as well.

    The four routes below split two ways: one is addressed by site and three
    by run, so a helper handing back only the run id cannot reach all four.
    Kept separate rather than widening `_api_for_domain`'s return, because
    eight call sites above unpack exactly two values.
    """
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", raising=False)
    db = tmp_path / "typed-url.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client_id = repo.create_client(conn, op, "Typed Co")
    site_id = repo.create_site(conn, client_id, domain)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.close()
    return TestClient(create_app(db_path=db)), site_id, run_id


#: The four callers of `_validate_start_url`, each as (label, path, body).
#: `{site}` and `{run}` are filled in below. Derived by grepping
#: `_validate_start_url` in `clauditseo/api/app.py` at `42454b6` -- not from
#: the audit's anchors, three of which had already drifted `+21` by then.
#: `content-brief` is the expert tool because it is page-scoped (so it reaches
#: the check) while being none of `triage`, the places tools, `freshness` or
#: `content-gap`, each of which does work before the check is reached. It was
#: `js-rendering` until that brief retired at item 165, then `entity-graph` until
#: item 145 retired that one.
_TYPED_URL_ROUTES = [
    ("audits", "/api/sites/{site}/audits",
     {"dims": ["TEC"], "tier": "T2", "start_url": "{url}"}),
    ("advise", "/api/runs/{run}/advise", {"url": "{url}"}),
    ("schema-audit", "/api/runs/{run}/schema-audit", {"url": "{url}"}),
    ("expert", "/api/runs/{run}/expert/content-brief", {"url": "{url}"}),
]


def _post_typed_url(client, site_id, run_id, route, url):
    _label, path, body = route
    filled = {k: v.replace("{url}", url) if isinstance(v, str) else v
              for k, v in body.items()}
    return client.post(path.format(site=site_id, run=run_id), json=filled)


@pytest.mark.parametrize("route", _TYPED_URL_ROUTES,
                         ids=[r[0] for r in _TYPED_URL_ROUTES])
def test_a_start_url_urlsplit_cannot_parse_is_refused_rather_than_crashing(
        tmp_path, monkeypatch, route):
    """CQ-133. CQ-120's twin above proved this for a *stored* domain on the
    probe route; the same unguarded predicate sits in `_validate_start_url`,
    which four routes call with a string the operator types.

    `host = urlsplit(start_url).hostname or ""` has no `try`, so
    `http://a]b/` raises `ValueError: Invalid IPv6 URL` and FastAPI answers
    500 with no body -- on the same field that answers 422 with a readable
    sentence for every well-formed foreign host.

    The commit that closed CQ-120 edited two lines *inside* this function and
    guarded only the probe path, which is why this is a second guard rather
    than a parametrisation of the first: they are different doors.
    """
    client, site_id, run_id = _api_for_typed_url(tmp_path, monkeypatch)
    refused = _post_typed_url(client, site_id, run_id, route, "http://a]b/")
    assert refused.status_code == 422, refused.text
    assert refused.json().get("detail"), "a refusal with nothing to read"


@pytest.mark.parametrize("route", _TYPED_URL_ROUTES,
                         ids=[r[0] for r in _TYPED_URL_ROUTES])
def test_a_foreign_host_is_still_refused_with_the_sentence_it_always_had(
        tmp_path, monkeypatch, route):
    """The control for the guard above, and the reason it is not enough to
    assert 422 alone: a `try` that swallowed the `ValueError` and returned
    `None` would turn the crash into a *pass*, letting the crawler be pointed
    off-site. This asserts the refusal the guard sits in front of survives.
    """
    client, site_id, run_id = _api_for_typed_url(tmp_path, monkeypatch)
    refused = _post_typed_url(client, site_id, run_id, route,
                              "http://evil.example.org/")
    assert refused.status_code == 422, refused.text
    assert "does not match the site domain" in refused.json()["detail"]
