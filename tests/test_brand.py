"""Whose name goes on a client-facing document.

Reports carried the product's name and nothing else, so an agency handing one
to a client was handing over a document branded with its supplier's tool. The
client is buying the agency's judgement; which tool produced it is the
agency's business.

Two names, kept apart on purpose. The operator's own screens say what they are
actually running — an admin panel should not lie about that — while the
document says whoever the operator is.
"""

from __future__ import annotations

import base64
import struct
import zlib

import pytest

from clauditseo import APP_NAME, brand
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate


def _png(width: int = 4, height: int = 4) -> bytes:
    """A real PNG, built rather than pasted, so the signature check is being
    tested against an actual image and not against a hand-typed prefix."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "brand.db")
    migrate(c)
    return c


def test_unset_falls_back_to_the_product_name(conn):
    """A document cannot have a blank header, so `name` always answers — and
    `name_is_set` says whether that answer is a choice or a default."""
    got = brand.get(conn)
    assert got["name"] == APP_NAME
    assert got["name_is_set"] is False
    assert got["product_name"] == APP_NAME


def test_the_operator_name_replaces_it_on_the_document(conn):
    brand.set_name(conn, "Northbound Digital")
    got = brand.get(conn)
    assert got["name"] == "Northbound Digital" and got["name_is_set"] is True
    # The product name is still reported, so the operator's own screens can
    # say what they are running without pretending to be the agency.
    assert got["product_name"] == APP_NAME


def test_clearing_returns_to_the_product_name(conn):
    brand.set_name(conn, "Northbound Digital")
    brand.set_name(conn, "")
    assert brand.get(conn)["name"] == APP_NAME
    assert brand.get(conn)["name_is_set"] is False


def test_a_name_long_enough_to_be_a_paragraph_is_refused(conn):
    with pytest.raises(ValueError, match="not a paragraph"):
        brand.set_name(conn, "x" * 200)


# --- the logo ---------------------------------------------------------------

def test_a_real_png_is_accepted_and_recorded(conn, tmp_path):
    out = brand.set_logo(conn, _png(), tmp_path / "brand")
    assert out["mime"] == "image/png"
    got = brand.get(conn)
    assert got["logo_mime"] == "image/png"
    assert got["logo_path"] and got["logo_missing"] is False


def test_the_content_decides_not_the_file_name(conn, tmp_path):
    """A file called logo.png that is not a PNG fails silently in a document
    and loudly in front of a client."""
    with pytest.raises(ValueError, match="checked by content"):
        brand.set_logo(conn, b"<svg>not really a png</svg>", tmp_path / "brand")
    assert brand.get(conn)["logo_path"] is None


def test_a_riff_container_that_is_not_webp_is_refused(conn, tmp_path):
    """RIFF is a container — a WAV starts the same way as a WebP."""
    with pytest.raises(ValueError, match="checked by content"):
        brand.set_logo(conn, b"RIFF\x00\x00\x00\x00WAVEfmt ", tmp_path / "brand")


def test_a_photograph_dragged_in_by_mistake_is_refused(conn, tmp_path):
    big = _png()[:8] + b"\x00" * (brand.MAX_LOGO_BYTES + 1)
    with pytest.raises(ValueError, match="the limit is"):
        brand.set_logo(conn, big, tmp_path / "brand")


def test_replacing_a_logo_leaves_no_stale_file(conn, tmp_path):
    """Keeping every upload would accumulate an operator's rejected attempts
    on disk forever, and only the current one is ever rendered."""
    into = tmp_path / "brand"
    brand.set_logo(conn, _png(), into)
    gif = b"GIF89a" + b"\x00" * 32
    brand.set_logo(conn, gif, into)
    assert sorted(p.name for p in into.glob("logo.*")) == ["logo.gif"]


def test_a_logo_whose_file_vanished_says_so_rather_than_breaking(conn, tmp_path):
    """Recorded and present are different states. A broken image in a
    client's document is worse than no image."""
    into = tmp_path / "brand"
    brand.set_logo(conn, _png(), into)
    next(into.glob("logo.*")).unlink()
    got = brand.get(conn)
    assert got["logo_path"] is None and got["logo_missing"] is True


def test_clearing_removes_the_file_too(conn, tmp_path):
    into = tmp_path / "brand"
    brand.set_logo(conn, _png(), into)
    brand.clear_logo(conn)
    assert brand.get(conn)["logo_path"] is None
    assert not list(into.glob("logo.*"))


def test_the_logo_is_copied_beside_the_report(conn, tmp_path):
    """A markdown document referencing an absolute path renders only on the
    machine that made it — and puts the operator's home directory into a
    client's document."""
    brand.set_logo(conn, _png(), tmp_path / "brand")
    report = tmp_path / "out" / "report.md"
    report.parent.mkdir(parents=True)
    report.write_text("# report", encoding="utf-8")

    name = brand.copy_logo_beside(conn, report)
    assert name == "logo.png"
    assert (report.parent / "logo.png").exists()


def test_no_logo_means_nothing_is_copied(conn, tmp_path):
    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")
    assert brand.copy_logo_beside(conn, report) is None


# --- what a client actually receives ---------------------------------------

def test_the_client_report_carries_the_operator_not_the_product(conn, tmp_path):
    from clauditseo.reporting.render import render_run_report

    brand.set_name(conn, "Northbound Digital")
    mark = dict(brand.get(conn))
    mark["logo_file"] = "logo.png"
    run = {"id": "a1b2c3d4e5f6a7b8", "tier": "T2", "dimensions": ["ONP"],
           "engine_version": "0.5.0", "composite_score": 90.0,
           "finished_at": "2026-08-14T00:00:00+00:00", "subscores": {},
           "findings": []}
    md, _ = render_run_report({"domain": "x.test"}, run, "client", brand=mark)
    assert md.startswith("![Northbound Digital](logo.png)")
    assert "**Northbound Digital**" in md


def test_the_internal_copy_does_not_wear_the_agency_logo(conn):
    """An internal document does not need the operator's own mark explaining
    who they are."""
    from clauditseo.reporting.render import render_run_report

    brand.set_name(conn, "Northbound Digital")
    mark = dict(brand.get(conn))
    mark["logo_file"] = "logo.png"
    run = {"id": "a1b2c3d4e5f6a7b8", "tier": "T2", "dimensions": ["ONP"],
           "engine_version": "0.5.0", "composite_score": 90.0,
           "finished_at": "2026-08-14T00:00:00+00:00", "subscores": {},
           "findings": []}
    md, _ = render_run_report({"domain": "x.test"}, run, "internal", brand=mark)
    assert "logo.png" not in md


def test_an_unbranded_install_still_produces_a_headed_document():
    from clauditseo.reporting.render import render_run_report

    run = {"id": "a1b2c3d4e5f6a7b8", "tier": "T2", "dimensions": ["ONP"],
           "engine_version": "0.5.0", "composite_score": 90.0,
           "finished_at": "2026-08-14T00:00:00+00:00", "subscores": {},
           "findings": []}
    md, _ = render_run_report({"domain": "x.test"}, run, "client", brand=None)
    assert md.startswith("# SEO audit report")
