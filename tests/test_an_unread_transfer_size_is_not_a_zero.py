"""A transfer size the browser did not report is unread, not a measured zero.

Screen audits round 3, Speed IP-01 (High): the trace coerced a missing or zero
`transferSize` - a cross-origin response without Timing-Allow-Origin, or one
served from cache - to 0, and nothing downstream could tell the two apart.
Page weight summed it as nothing, third-party hosts read "0 KB", and the
analysis's own hold called it "likely a cached-repeat-view artefact".
"""
from __future__ import annotations

import inspect

from clauditseo import perf
from clauditseo.modules import prf


def test_the_trace_keeps_an_unreported_size_as_null():
    assert "transfer: r.transferSize > 0 ? r.transferSize : null," in perf._READ_TRACE_JS
    assert '"transfer": r.get("transfer") or None,' in inspect.getsource(perf)


def test_the_ledger_says_unread_rather_than_zero():
    trace = {"resources": [
        {"url": "https://cdn.other.test/a.js", "transfer": None},
        {"url": "https://cdn.other.test/b.js", "transfer": 2048},
        {"url": "https://beacon.other.test/p", "transfer": None},
    ]}
    by = {r["host"]: r for r in prf.third_party_ledger(trace, "gate-six.test")}
    assert by["cdn.other.test"]["bytes"] == 2048 and by["cdn.other.test"]["unread"] == 1
    assert by["beacon.other.test"]["bytes"] is None and by["beacon.other.test"]["unread"] == 1


def test_page_weight_says_at_least_where_sizes_went_unread():
    src = inspect.getsource(prf)
    assert "unread = sum(1 for r in resources if not r.get(\"transfer\"))" in src
    assert "{'at least ' if unread else ''}{transfer // 1024} KB transferred" in src
    assert '"transfer_bytes": transfer, "unread": unread,' in src
