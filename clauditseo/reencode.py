"""What an image would weigh re-encoded, measured rather than estimated
(brief v16 step AU7).

A saving is the only number on the Images part an operator acts on
directly: "3.1 MB recoverable" is what decides whether the work is worth
doing this week. An estimate dressed as a measurement is therefore the
worst thing this part could say, and the rule the brief sets - *measure,
do not estimate* - is enforced here by having nothing to report when the
encode did not happen. There is no formula in this module and no table of
typical ratios: either a file was fetched, decoded, resized and encoded,
or the row carries no saving and says why.

Optional, like `imaging`. Without Pillow the module answers `{}` and every
row reads `savings not measured`, which is a different sentence from
`no saving available` and must stay one.

**Why the largest rendered width.** Re-encoding at the intrinsic size
measures a file nobody needs: the point of the exercise is the file the
page would serve if it served the right one, and that is the width the
image is actually shown at, at the widest breakpoint the site declares.
An image that renders wider than it is intrinsically is not upscaled - it
is encoded at its own size, because inventing pixels is not a saving.
"""

from __future__ import annotations

import io
from typing import Any

#: Where the encoded probe stops mattering. A file this size is a defect
#: on its own and re-encoding it to find out by how much costs more than
#: the answer is worth; the row still says it is over budget.
MAX_FETCH_BYTES = 12 * 1024 * 1024

#: One request each, and no retries: this is a measurement of the site's
#: own assets and a slow one is a fact about the site.
FETCH_TIMEOUT_S = 20.0

#: How many images one run will re-encode. Every candidate is already a
#: failing row, so this is a bound on the work rather than on the finding.
MAX_IMAGES = 40


def available() -> bool:
    """Whether an encoder is installed at all.

    Both halves are asked for, because AVIF is a plugin: a Pillow without
    it can still answer in WebP, and a caller that assumed AVIF would get
    a saving measured in a format it was not told about.
    """
    try:
        import PIL.Image  # noqa: F401
    except ImportError:
        return False
    return True


def _formats() -> list[tuple[str, str]]:
    """(Pillow format, human name) in the order the brief sets: AVIF, then
    WebP where the plugin is absent."""
    out: list[tuple[str, str]] = []
    try:
        import pillow_avif  # noqa: F401
        out.append(("AVIF", "AVIF"))
    except ImportError:
        pass
    from PIL import features
    if features.check("webp"):
        out.append(("WEBP", "WebP"))
    return out


def _fetch(url: str) -> bytes | None:
    import httpx
    try:
        with httpx.Client(follow_redirects=True, timeout=FETCH_TIMEOUT_S) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    return None
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_FETCH_BYTES:
                        return None
                return bytes(body)
    except Exception:
        # Any failure to fetch is "not measured", never a saving of zero.
        return None


def one(url: str, width: int | None, quality: int = 60) -> dict[str, Any]:
    """What `url` weighs re-encoded, or why it does not say.

    Returns `{"measured_kb": N, "encoder": "AVIF q60 at 1440"}` on success
    and `{"reencode_error": "..."}` otherwise. Never both, never a
    `measured_kb` the caller has to know to distrust, and **never an
    exception** - a caller measuring forty images cannot have the
    thirty-first abort the run.

    A bare install is the first failure path, and it used to be the one
    that broke the promise above: `from PIL import Image` sat at the top of
    this function, so a machine without Pillow raised `ModuleNotFoundError`
    rather than answering. `available()` was already right and nothing
    called it here. CI found it on both platforms and four green local runs
    could not, because the developer venv has Pillow installed - which is
    exactly the shape of defect a bare-install path has.
    """
    if not available():
        return {"reencode_error": "no image encoder installed: "
                                  "install clauditseo[image]"}
    from PIL import Image

    formats = _formats()
    if not formats:
        return {"reencode_error": "no encoder: install clauditseo[image]"}
    raw = _fetch(url)
    if raw is None:
        return {"reencode_error": "the file could not be fetched, or is over 12 MB"}
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:
        return {"reencode_error": f"the file could not be decoded ({type(exc).__name__})"}
    if image.mode in ("P", "LA", "PA"):
        image = image.convert("RGBA")
    elif image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGB")
    # Down to the width it renders at, never up: inventing pixels is not a
    # saving, and a file already narrower than its box is already right.
    at = image.width
    if width and 0 < width < image.width:
        height = max(1, round(image.height * width / image.width))
        image = image.resize((width, height), Image.LANCZOS)
        at = width
    fmt, name = formats[0]
    buffer = io.BytesIO()
    try:
        image.save(buffer, format=fmt, quality=quality)
    except Exception as exc:
        return {"reencode_error": f"the file could not be re-encoded ({type(exc).__name__})"}
    return {"measured_kb": max(1, round(buffer.tell() / 1024)),
            "encoder": f"{name} q{quality} at {at}"}


def measure(candidates: list[tuple[str, int | None]], quality: int = 60,
            cap: int = MAX_IMAGES) -> dict[str, dict[str, Any]]:
    """`{url: result}` for each candidate, in order, up to `cap`.

    `{}` where no encoder is installed - the caller keeps its unmeasured
    rows and says so, exactly as it does when no browser measured the
    page. A candidate that fails carries its reason rather than dropping
    out, because "we tried and could not" is a different thing from "we
    did not try" and the card distinguishes them.
    """
    if not available():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for url, width in candidates[:cap]:
        if url in out:
            continue
        out[url] = one(url, width, quality)
    return out
