"""The browser tab carries the product's own identity.

`FEATURES.md` F-08. The tab showed a blue tile lettered **A**, from a name the
product no longer has, while `APP_NAME` and the page title were both
`ClauditSEO`. Meanwhile the admin panel held a brand logo that never reached
the tab.

**Ordinary tests, not guards**, per the rule stated in `FEATURES.md`: the
behaviour did not exist, so there was nothing to observe failing first. They
were written with the feature and were red until it was built. DISCIPLINE rule
1 does not apply and is not being skipped quietly.

The decision lives on the server — `/api/brand` answers `icon_href`, a URL or
`null` — so the cases that matter are testable here rather than only in a
browser. `null` is the answer for every way this can fail, which is why the
screen cannot forget one: there is only an href or nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

from clauditseo import brand
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate

ROOT = Path(__file__).resolve().parents[1]
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _conn(tmp_path):
    c = connect(tmp_path / "brand.db")
    migrate(c)
    return c


# --- clause 1: the default, when nothing is registered ----------------------

def test_with_no_logo_the_answer_is_the_built_in_default(tmp_path):
    assert brand.get(_conn(tmp_path))["icon_href"] is None, (
        "null means keep the default; anything else would point the tab at a "
        "logo that does not exist")


def test_the_default_mark_is_no_longer_the_retired_letterform():
    """The `A` was the whole observation. It must not survive as the default,
    which is what every install shows on first run."""
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

    icons = re.findall(r'<link rel="icon"[^>]*>', html)
    assert len(icons) == 1, f"expected exactly one icon link, found {len(icons)}"
    assert "M8 22 L13 10 L18 22" not in html, (
        "the retired A letterform is still the default favicon")
    assert "data:image/svg+xml" in icons[0], (
        "the default must stay a data URI — index.html is served before any "
        "API call, so a default that needs a request has no answer to give")


# --- clause 2: a registered logo, and replacing it --------------------------

def test_a_registered_logo_becomes_the_tab_icon(tmp_path):
    conn = _conn(tmp_path)
    brand.set_logo(conn, PNG, tmp_path / "brand")

    href = brand.get(conn)["icon_href"]
    assert href and href.startswith("/api/brand/logo"), href


def test_replacing_the_logo_changes_the_href_so_the_tab_cannot_stay_stale(tmp_path):
    """The cache-bust, which is clause 2's real content. A replacement under
    the same URL would otherwise keep the old mark in the tab indefinitely —
    this feature's own defect arriving by a new route."""
    conn = _conn(tmp_path)
    brand.set_logo(conn, PNG, tmp_path / "brand")
    first = brand.get(conn)["icon_href"]

    conn.execute("UPDATE brand SET updated_at='2099-01-01T00:00:00+00:00'"
                 " WHERE id=1")
    conn.commit()
    second = brand.get(conn)["icon_href"]

    assert first != second, (
        "the href must move when the logo does, or the browser keeps serving "
        f"the old icon from cache: {first!r}")
    assert "2099" in second


# --- clause 3: the negative cases, the half that will bite ------------------

def test_a_logo_whose_file_has_gone_falls_back_rather_than_breaking(tmp_path):
    """A tab with no icon is harder to find than a tab with the wrong one."""
    conn = _conn(tmp_path)
    got = brand.set_logo(conn, PNG, tmp_path / "brand")
    Path(got["path"]).unlink()

    answer = brand.get(conn)
    assert answer["logo_missing"] is True, "the state must still be reported"
    assert answer["icon_href"] is None, (
        "a recorded logo whose file is gone must fall back to the default, "
        "not point the tab at a 404")


def test_a_mime_a_browser_will_not_render_as_an_icon_falls_back(tmp_path):
    """Unreachable through the upload path today — `sniff()` admits only PNG,
    JPEG, GIF and WebP, and a browser takes all four. Asserted anyway, because
    the row can be edited directly and because a format added to
    `ALLOWED_LOGO` must be a deliberate decision about `ICON_MIMES` rather
    than an inherited one. A blank tab looks identical to the app failing to
    load, so this must never be the silent case."""
    conn = _conn(tmp_path)
    brand.set_logo(conn, PNG, tmp_path / "brand")
    conn.execute("UPDATE brand SET logo_mime='application/pdf' WHERE id=1")
    conn.commit()

    assert brand.get(conn)["icon_href"] is None


def test_every_uploadable_format_is_also_acceptable_as_an_icon():
    """The two lists answer different questions and are allowed to differ —
    but where they do, a logo the operator can upload would silently fail to
    become an icon. Today they agree, and this says so out loud."""
    uploadable = {mime for mime, _ext in brand.ALLOWED_LOGO.values()}

    assert uploadable <= brand.ICON_MIMES, (
        f"these can be uploaded but not used as an icon: "
        f"{sorted(uploadable - brand.ICON_MIMES)}")
