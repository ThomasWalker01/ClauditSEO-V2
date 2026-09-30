"""CQ-98 — `_host_matches_site` accepted any ancestor of the stored domain.

The predicate answers one question for two doors: `_validate_start_url`
(`api/app.py`), which decides what URL the crawler may be *pointed at*, and
`refresh_section`, which decides what page may be re-read into an existing
site's findings. Both were enumerated from a grep for the symbol rather than
from the report's list (DISCIPLINE rule 3); the crawler's in-scope link
following does not use it, and `tests/test_crawl_start_url.py` is the only
other reader.

**The defect.** The third clause was `domain.endswith("." + host)` with no
bound on how much of the domain the host had to be. So every ancestor of the
record's own domain matched, and a public suffix is an ancestor:
`_host_matches_site('au', 'www.acme.com.au')` returned `True`, as did
`('com.au', ...)`, `('com', 'example.com')` and `('co.uk', 'shop.co.uk')`.
`www.acme.com.au` is a real row in this install's `sites` table, so the
input is the operator's own data and not a constructed one. The consequence
is the finding's own: a page at an unrelated registrable domain is fetched
and its findings stored against this site, and the refusal message asserted a
check ("a refresh re-reads a page the audit already crawled") that was never
made.

**Why the reverse direction is bounded to `www.` and not to a label count.**
There is no public-suffix list in this repository and adding one to settle a
guard is a data dependency a self-hosted install would have to keep current.
A one-label bound was measured against the same inputs and is a *partial*
fix that reads as a complete one: it rejects `('au', 'www.acme.com.au')`
but still accepts `('com.au', 'acme.com.au')` and `('co.uk',
'shop.co.uk')`, because a two-label public suffix is exactly one label short
of an apex record. `www.` is the only prefix that is an alias by convention
rather than by guess, it is the case the clause was serving, and it is
decidable without a list.

**What that costs, stated rather than left to be discovered.** A site
recorded at a non-`www` subdomain — `shop.example.com` — can no longer reach
its own apex through this predicate. That is a narrowing of an off-site
guard, which is the safe direction, and the refusal message now names the
check that failed so the operator can correct the record. Subdomains of the
record are unaffected: `host.endswith("." + domain)` is untouched.

**The port half is this fix's too, by the repository's own assignment.**
`tests/test_crawl_start_url.py:203-221` records that a site stored as
`host:port` cannot be section-refreshed at all — `host == domain` is false
because `urlsplit().hostname` never carries a port and the stored domain
does — and says in as many words that it "lives one call site away from
CQ-98's suffix-match defect and belongs to that fix". The port is stripped
for the comparison only. `site_host` itself is unchanged, deliberately: its
docstring records that `_probe_target` dials what it returns, so stripping a
port there would move a probe of `example.com:8443` onto 443.
"""

from clauditseo.api.app import _host_matches_site


# --- the defect, at the operator's own stored domain -----------------------

def test_a_public_suffix_is_not_the_site_it_is_a_suffix_of():
    """The four inputs that returned True before this fix.

    `www.acme.com.au` is a row in this install's `sites` table. The other
    three are the same shape at the suffixes a public-suffix list would
    carry: a one-label ccTLD, a two-label ccTLD, and a one-label gTLD.
    """
    assert not _host_matches_site("au", "www.acme.com.au")
    assert not _host_matches_site("com.au", "www.acme.com.au")
    assert not _host_matches_site("com.au", "acme.com.au")
    assert not _host_matches_site("com", "example.com")
    assert not _host_matches_site("co.uk", "shop.co.uk")


def test_the_one_label_bound_that_would_have_read_as_a_fix_is_not_the_one_taken():
    """A guard against re-loosening this to a label count.

    Both inputs below are rejected by the `www.` bound and accepted by a
    one-extra-label bound, so a future change to the cheaper rule reddens
    here rather than passing as an equivalent tightening.
    """
    assert not _host_matches_site("com.au", "acme.com.au")
    assert not _host_matches_site("co.uk", "shop.co.uk")


# --- and the cases the predicate exists to accept, unchanged ---------------

def test_the_record_itself_and_every_subdomain_of_it_still_match():
    assert _host_matches_site("www.acme.com.au", "www.acme.com.au")
    assert _host_matches_site("acme.com.au", "acme.com.au")
    assert _host_matches_site("page.acme.com.au", "acme.com.au")
    assert _host_matches_site("a.b.acme.com.au", "acme.com.au")
    # The stored domain may carry a scheme; `site_host` is what reads it, and
    # this install has two rows that do.
    assert _host_matches_site("www.13acme.com.au", "https://www.13acme.com.au/")
    assert _host_matches_site("meridian.io", "https://meridian.io/")


def test_a_record_stored_with_www_still_matches_its_own_apex():
    """The case the reverse clause was serving, and the whole of what is kept."""
    assert _host_matches_site("acme.com.au", "www.acme.com.au")
    assert _host_matches_site("13acme.com.au", "https://www.13acme.com.au/")


def test_an_unrelated_host_never_matched_and_still_does_not():
    assert not _host_matches_site("evil.com", "www.acme.com.au")
    assert not _host_matches_site("acme.com.au.evil.com", "acme.com.au")
    assert not _host_matches_site("", "www.acme.com.au")
    assert not _host_matches_site("www.acme.com.au", "")


# --- the port half, assigned to this fix by test_crawl_start_url.py --------

def test_a_site_stored_with_a_port_can_be_matched_at_all():
    """`urlsplit().hostname` never carries a port and a stored domain may.

    Before this fix `_host_matches_site('127.0.0.1', '127.0.0.1:55881')` was
    `False`, so a site seeded at `host:port` — which is every driven fixture
    in this suite — could not be section-refreshed whatever else was true.
    """
    assert _host_matches_site("127.0.0.1", "127.0.0.1:55881")
    assert _host_matches_site("example.com", "example.com:8443")
    assert _host_matches_site("page.example.com", "example.com:8443")
    # An IPv6 authority is bracketed in a `host:port` string and bare out of
    # `urlsplit().hostname`, so the two spellings have to meet.
    assert _host_matches_site("::1", "[::1]:8080")
    assert _host_matches_site("::1", "[::1]")


def test_stripping_the_port_does_not_make_two_different_hosts_one():
    assert not _host_matches_site("127.0.0.2", "127.0.0.1:55881")
    assert not _host_matches_site("evil.com", "example.com:8443")
