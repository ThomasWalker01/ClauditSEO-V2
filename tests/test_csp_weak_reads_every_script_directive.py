"""`csp-weak` reads every script directive, each by its name (item 276, row 5).

The check read the first directive that started with "script-src", so a
policy leading with `script-src-elem` never had its `script-src` read, and a
gap in `-elem` was said of `script-src`.
"""

from __future__ import annotations

from tests.test_security_is_its_own_dimension import GOOD_HEADERS, _run


def _csp(policy):
    return _run(headers={**GOOD_HEADERS, "content-security-policy": policy})


def test_each_script_directive_is_read_and_named():
    got = _csp("default-src 'self'; script-src-elem 'self' 'unsafe-inline'; "
               "script-src 'self' 'unsafe-eval'; script-src-attr 'unsafe-inline'; "
               "object-src 'none'; frame-ancestors 'self'")
    gaps = got["csp-weak"].evidence["gaps"]
    assert gaps == ["'unsafe-inline' in script-src-elem", "'unsafe-eval' in script-src",
                    "'unsafe-inline' in script-src-attr"], gaps


def test_a_source_is_a_whole_token_not_a_substring():
    # `https://data.example` is a host, not the `data:` scheme.
    got = _csp("default-src 'self'; script-src 'self' https://data.example; "
               "object-src 'none'; frame-ancestors 'self'")
    assert "csp-weak" not in got, got["csp-weak"].evidence["gaps"]
