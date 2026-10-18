"""The Local part's blurb says what its checks measure (item 278, row 12).

It read "NAP consistency", but `nap-inconsistent` compares the phone numbers
the crawled pages show; no check compares a name or an address, or the
site's declared NAP. The blurb names what is measured.
"""

from __future__ import annotations

from clauditseo import anatomy


def test_the_blurb():
    local = next(c for c in anatomy.CATEGORIES if c.key == "local")
    text = " ".join(str(v) for v in vars(local).values()) if hasattr(local, "__dict__") else str(local)
    assert "NAP consistency" not in text
    assert "Phone numbers across the site" in text
