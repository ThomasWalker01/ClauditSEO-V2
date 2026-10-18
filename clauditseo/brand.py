"""Whose name goes on a client-facing document.

Reports carried the product's name and nothing else, so an agency handing one
to a client was handing over a document branded with its supplier's tool. That
is backwards: the client is buying the agency's judgement, and which tool
produced it is the agency's business.

Two names, deliberately kept apart. `APP_NAME` is what the operator's own
screens say — the admin panel should not lie about what it is running. The
brand is what a client sees, and it defaults to the product name so an
operator who never opens this screen gets a document that is at least
consistent rather than blank.

One row, not one per client. This is who the operator IS; an agency has a
single identity across every client, and a per-client version would invite
sending one client's branding to another.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from clauditseo import APP_NAME

#: What a logo may be. Deliberately short, and by content rather than by file
#: extension: an operator uploading `logo.png` that is actually something else
#: should get an error here, not a broken image in a document already sent.
ALLOWED_LOGO: dict[bytes, tuple[str, str]] = {
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"GIF87a": ("image/gif", ".gif"),
    b"GIF89a": ("image/gif", ".gif"),
    b"RIFF": ("image/webp", ".webp"),          # checked further below
}

#: A logo for a document header. Above this it is a photograph somebody
#: dragged in by mistake, and it would be embedded in every report.
MAX_LOGO_BYTES = 2 * 1024 * 1024

#: Which stored logos a browser will accept as a tab icon (FEATURES.md F-08).
#:
#: Every mime `ALLOWED_LOGO` can produce is in here, and that is not an
#: accident to rely on silently: `sniff()` admits PNG, JPEG, GIF and WebP by
#: magic bytes, and all four render as `<link rel="icon">`. So the "a stored
#: logo a browser will not take as an icon" case cannot arise through the
#: upload path today.
#:
#: Stated as its own set anyway, because the two lists answer different
#: questions — one is "may this be a logo", the other "may this be an icon" —
#: and a future format added to the first must be a deliberate decision about
#: the second. A row edited directly in the database is the other way it can
#: differ, and that is exactly when a tab would silently go blank.
ICON_MIMES: frozenset[str] = frozenset(
    mime for mime, _ext in ALLOWED_LOGO.values())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sniff(data: bytes) -> tuple[str, str]:
    """(mime, extension) from the bytes themselves, or raise.

    By signature rather than by the name the browser sent, because a file
    called `logo.png` that is not a PNG fails silently in a PDF and loudly in
    front of a client.
    """
    if len(data) > MAX_LOGO_BYTES:
        raise ValueError(
            f"logo is {len(data) // 1024} kB; the limit is "
            f"{MAX_LOGO_BYTES // 1024} kB — this goes in every report header")
    for magic, (mime, ext) in ALLOWED_LOGO.items():
        if not data.startswith(magic):
            continue
        if magic == b"RIFF":
            # RIFF is a container; only the WEBP flavour is an image.
            if data[8:12] != b"WEBP":
                continue
        return mime, ext
    raise ValueError("not a PNG, JPEG, GIF or WebP image — checked by "
                     "content, not by the file name")


def get(conn: sqlite3.Connection) -> dict:
    """The brand as a client would see it, with what is actually set.

    `name` always answers — a document cannot have a blank header — while
    `name_is_set` says whether that answer is the operator's choice or the
    product's default. A screen that cannot tell them apart shows the
    operator their own name and gives them no way to know it is a placeholder.
    """
    row = conn.execute("SELECT * FROM brand WHERE id=1").fetchone()
    chosen = (row["display_name"] if row else None) or None
    logo = (row["logo_path"] if row else None) or None
    on_disk = bool(logo and Path(logo).exists())
    return {
        "name": chosen or APP_NAME,
        "name_is_set": bool(chosen),
        "product_name": APP_NAME,
        "logo_path": logo if on_disk else None,
        "logo_mime": (row["logo_mime"] if row else None) if on_disk else None,
        # Recorded and present are different states, the same distinction the
        # deliverables list makes: a logo whose file has gone must say so
        # rather than render as a broken image in a client's document.
        "logo_missing": bool(logo and not on_disk),
        "updated_at": row["updated_at"] if row else None,
        # The tab icon, decided here rather than on the screen (F-08).
        #
        # `null` means "keep the built-in default", and it is the answer for
        # every way this can go wrong: no logo, a logo whose file has gone,
        # and a stored mime a browser would not render as an icon. A screen
        # cannot get that wrong by forgetting a case, because there is only
        # one case for it — an href or nothing.
        #
        # Cache-busted by `updated_at`, which changes when a logo is replaced.
        # Without it a new logo under the same URL keeps the old tab mark
        # indefinitely, which is this feature's own defect arriving by a new
        # route. `admin.tsx` already does the same thing with a save counter;
        # this uses the stored timestamp so the answer survives a reload.
        "icon_href": _icon_href(row, on_disk),
    }


def _icon_href(row, on_disk: bool) -> str | None:
    """Where the tab icon lives, or None to keep the default."""
    if not row or not on_disk:
        return None
    mime = row["logo_mime"]
    if mime not in ICON_MIMES:
        return None
    stamp = quote(str(row["updated_at"] or ""), safe="")
    return f"/api/brand/logo?v={stamp}" if stamp else "/api/brand/logo"


def set_name(conn: sqlite3.Connection, name: str | None) -> None:
    """Set the client-facing name, or clear it back to the product's."""
    cleaned = (name or "").strip() or None
    if cleaned and len(cleaned) > 120:
        raise ValueError("a document header is not a paragraph — 120 "
                         "characters at most")
    with conn:
        conn.execute("UPDATE brand SET display_name=?, updated_at=? WHERE id=1",
                     (cleaned, _now()))


def set_logo(conn: sqlite3.Connection, data: bytes, into: Path) -> dict:
    """Store a logo and record where it went. Raises on anything else."""
    mime, ext = sniff(data)
    into.mkdir(parents=True, exist_ok=True)
    # One name, overwritten. Keeping every upload would accumulate the
    # operator's rejected attempts on disk forever, and only the current one
    # is ever rendered.
    path = into / f"logo{ext}"
    for stale in into.glob("logo.*"):
        if stale != path:
            stale.unlink(missing_ok=True)
    path.write_bytes(data)
    with conn:
        conn.execute("UPDATE brand SET logo_path=?, logo_mime=?, updated_at=?"
                     " WHERE id=1", (str(path), mime, _now()))
    return {"mime": mime, "bytes": len(data), "path": str(path)}


def clear_logo(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT logo_path FROM brand WHERE id=1").fetchone()
    if row and row["logo_path"]:
        Path(row["logo_path"]).unlink(missing_ok=True)
    with conn:
        conn.execute("UPDATE brand SET logo_path=NULL, logo_mime=NULL,"
                     " updated_at=? WHERE id=1", (_now(),))


def copy_logo_beside(conn: sqlite3.Connection, report_path: Path) -> str | None:
    """Put the logo next to a generated report and return its relative name.

    A markdown document referencing an absolute path renders only on the
    machine that made it. Beside the file, it survives being emailed as a
    folder — and if the operator sends the .md alone, a missing image is a
    visibly missing image rather than a path disclosing their home directory.
    """
    got = get(conn)
    if not got["logo_path"]:
        return None
    source = Path(got["logo_path"])
    target = report_path.parent / source.name
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return source.name
