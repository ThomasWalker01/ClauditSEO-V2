"""The three Local builders supply the run (item 278, row 11).

`gbp-audit`, `citations-nap` and `review-signals` are being rewritten to the
contract, whose Block 1 carries `"run_id": "{{RUN_ID}}"`. A conforming brief's
placeholder the engine does not fill is a load error, and none of the three
builders filled it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from clauditseo.analysts import expert


@pytest.mark.parametrize("tool", ["gbp-audit", "citations-nap", "review-signals"])
def test_run_id(tool):
    site = SimpleNamespace(brand=None, business_type=None, locale=None, target_market=None,
                           gbp_primary_category=None, platform=None, domain="t.co")
    ctx = expert.build_context(tool, {"start_url": "https://t.co/", "pages": []}, site,
                               None, conn=None, run_id="r-278")
    assert ctx["RUN_ID"] == "r-278"
