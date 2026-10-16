"""A Security analysis row is judged against the hosts the crawl saw load.

Screen audits round 4, Security AC-02 and AC-03 (High): the proposed
Report-Only CSP left out static.cloudflareinsights.com, which loads a script
on every page, so enforcing it would block Cloudflare's beacon; and the SRI
card, labelled "automatic checks and analysis agree", named cdn.jsdelivr.net
and unpkg.com, which nothing loads from.
"""
from __future__ import annotations

from clauditseo.analysts.contract import Rules, _hosts_named, _security_refusal, csp_blocks

SEEN = {"gate-six.test", "plausible.io", "static.cloudflareinsights.com",
        "challenges.cloudflare.com"}
SCRIPTS = SEEN


def _rules():
    return Rules(resource_origins=SEEN, script_origins=SCRIPTS, site_host="gate-six.test")


def test_a_policy_that_leaves_out_a_loading_host_is_refused():
    policy = ("Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' "
              "https://plausible.io https://challenges.cloudflare.com")
    assert csp_blocks(policy, SCRIPTS, "gate-six.test") == ["static.cloudflareinsights.com"]
    why = _security_refusal("csp-policy", {"replacement": policy}, [], _rules())
    assert why and "would block" in why and "static.cloudflareinsights.com" in why


def test_a_policy_that_allows_every_loading_host_stands():
    policy = ("script-src 'self' https://plausible.io https://*.cloudflare.com "
              "https://static.cloudflareinsights.com")
    assert csp_blocks(policy, SCRIPTS, "gate-six.test") == []
    assert _security_refusal("csp-policy", {"replacement": policy}, [], _rules()) is None
    assert csp_blocks("frame-ancestors 'none'", SCRIPTS, "gate-six.test") == []


def test_an_sri_row_naming_hosts_nothing_loads_is_refused():
    row = {"evidence": "scripts from cdn.jsdelivr.net and unpkg.com load without integrity",
           "replacement": '<script src="https://cdn.jsdelivr.net/npm/x@1/x.min.js" integrity="…">'}
    why = _security_refusal("sri-missing", row, [], _rules())
    assert why and "cdn.jsdelivr.net" in why and "unpkg.com" in why
    ok = {"evidence": "plausible.io/js/pa-1.js loads on 45 pages without integrity"}
    assert _security_refusal("sri-missing", ok, [], _rules()) is None


def test_file_names_are_not_hosts():
    assert _hosts_named("turnstile/v0/api.js and pa-1.js from plausible.io") == {"plausible.io"}
