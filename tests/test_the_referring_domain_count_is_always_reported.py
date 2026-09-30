"""Item 236 (Backlinks, change 2): the referring-domain count is reported
whatever it is.

`low-referring-domains` fires only under the floor, and nothing else carried
the count. So a site above the floor had its one paid-for backlink number
recorded nowhere the Backlinks part draws, and the page read as if nothing
were known. It is reported the way `domain-authority-reported` is: an info
scope statement, beside the fault row rather than instead of it. (Change 1
was item 218.)
"""

from __future__ import annotations

from clauditseo.modules.ofp import LOW_REFERRING_DOMAINS, OffPageModule
from clauditseo.providers.base import ProviderHub
from clauditseo.engine.types import Tier
from tests.test_providers import FakeProvider, _ofp_context, _snap


def _by_check(rd):
    hub = ProviderHub(backlink_providers=[FakeProvider("moz", _snap(rd=rd, conf="high",
                                                                    source="moz"))])
    return {f.check_id: f for f in OffPageModule().run([], Tier.T2, _ofp_context(hub))}


def test_a_count_above_the_floor_is_reported():
    got = _by_check(LOW_REFERRING_DOMAINS + 40)
    row = got.get("referring-domains-reported")
    assert row is not None, sorted(got)
    assert row.evidence["referring_domains"] == LOW_REFERRING_DOMAINS + 40
    assert row.scope_statement and row.severity.value == "info"
    assert "low-referring-domains" not in got


def test_a_count_under_the_floor_is_reported_and_is_the_fault():
    got = _by_check(3)
    assert {"referring-domains-reported", "low-referring-domains"} <= set(got), sorted(got)


def test_the_new_row_is_registered_where_its_sibling_is():
    from clauditseo import anatomy, playbook
    assert anatomy.CHECK_CATEGORY["referring-domains-reported"] == "backlinks"
    tool = next(t for g in playbook.PLAYBOOK for t in g.get("tools", [])
                if "domain-authority-reported" in (t.get("checks") or []))
    assert "referring-domains-reported" in tool["checks"]
    assert "referring-domains-reported" in tool["gated"]
