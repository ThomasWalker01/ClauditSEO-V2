"""A server that is not answering must say so, not render an empty dashboard.

UX-06, carried since report 001 and the oldest live High in the engineering
cohort at `dashboard/src/App.tsx` (70 reports citing that anchor).

`App` probes `/api/clients` on boot to decide whether the operator is signed
in. The probe had exactly two outcomes it named — 401 meant "ask for a token",
and *everything else* meant `setAuthState("ok")` under the comment "non-auth
errors surface inside views". They do not. Every view then renders its own
empty state against data it never received, so a server that is down, or up
and 500ing, paints a signed-in dashboard reporting no clients, no sites and no
runs — the same pixels as a correctly-working install of a product nobody has
used yet. DISCIPLINE rule 6 draws exactly this line for the loop's own tests:
red and no-result are different answers, and one must never be shown as the
other. The screen owed the operator the same distinction and did not draw it.

**Two outage shapes, because they arrive as different objects and the old code
collapsed both.** A 5xx reaches the `.catch` as an `ApiError` with a status;
a process that is not listening at all makes `fetch` itself reject with a
`TypeError`, which has no `status` — so `e.status === 401` is false and the
`else` claimed the operator was signed in. Both are parametrised here rather
than testing the one that is easier to stage, because it was the second that
made the old branch unfalsifiable: an outage with no HTTP status is the case
a test built on status codes cannot reach.

Served by a stdlib server rather than by `create_app`, because the subject is
what the browser does when the API fails — which the real app, working
correctly, will not do.

**`scripts/prove_fail.py` cannot answer for this file**, for the reason
`test_site_switch.py` and `test_fetch_state.py` both record: it reverts
`dashboard/src` without rebuilding `dashboard/dist`, which is what this test
loads, so its answer would be about the bundle on disk rather than about the
parent commit. Rule 1 was satisfied by hand instead — built from the unfixed
source, watched all four cases fail, fixed, rebuilt, watched all four pass.
The measured before-text is in the fix commit and in the first test's
docstring below.

The second batch below, UX-71 and UX-72, needed no revert at all, and that is
worth recording because it is the cheapest shape a hand proof ever takes: the
defect was live at HEAD and `dashboard/dist` had already been built from it,
so the three new assertions could just be run. Three failed and one passed —
the pass being the `no-reply` half of the headline test, which is the one
case the old fixed prose happened to be true of. Where the bundle on disk is
already the unfixed one, the proof is *run it now*.

`NEEDS_BUILD` is left alone for the fourth time, and the count is on the
record rather than left as an impression: it is a hand-kept tuple of one, and
listing the test files that load DIST names **twenty** of them. Deriving the
tuple from that property is the fix those two files argued for and none has
taken. **Taken since**, on the fifth naming: the tuple is gone, `needs_build`
walks the import graph, and twenty-two files are refused where one was. Report 077 named no finding for it; **report 078 does — CQ-164, at
High** — so the line that used to read "written here so the next round can
raise it as one" has been served. Still not taken here, and now for a
different reason: report 078's open question 2 asks whether this script is
relied on at all, and if the answer is no then the remedy is deleting it
rather than deriving anything. Repair and deletion are opposite changes and
the choice is the operator's, so this file goes on working around it and
saying so.

The sentence above used to quote a `grep -rln` invocation with backslash-b
word boundaries around DIST. It does not any more, and the reason is a defect
rather than a preference: this is a **non-raw** module docstring, so Python
read each of those two-character escapes as one control character, and the
file on disk carried two literal backspace bytes from `b07ae29` until this
commit — the documented command could not be pasted and run. That is
KNOWN_ISSUES KI-21's failure class on a surface it had not been seen on
before: every previous instance was a Markdown table cell, and this one is
Python source. Prose beats a quoted regex here, so the sentence describes the
search rather than quoting it — and it is written that way because the first
attempt at this very paragraph re-introduced both bytes while explaining
them, which is the strongest argument available for a pre-commit check
rather than a note.
"""

from __future__ import annotations

import functools
import http.server
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo import axe

DIST = Path(__file__).resolve().parents[1] / "dashboard" / "dist"

pytestmark = [
    pytest.mark.skipif(not axe.available(),
                       reason="needs clauditseo[render] and `playwright install chromium`"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: The two ways a server stops answering, keyed by what the browser sees.
#: `"http-503"` is a process that is up and broken; `"no-reply"` is nothing
#: listening — the connection is accepted and dropped without a response,
#: which is what `fetch` rejects on.
OUTAGES = ["http-503", "no-reply"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _handler(mode: str):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(DIST), **kw)

        def _api(self) -> None:
            if mode == "no-reply":
                # Nothing written, connection dropped. The browser reports a
                # network error and `fetch` rejects — no status anywhere.
                self.close_connection = True
                return
            body = b'{"detail":"staged outage"}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802  (stdlib spelling)
            if self.path.startswith("/api/"):
                return self._api()
            return super().do_GET()

        def do_POST(self):  # noqa: N802
            return self._api()

        def log_message(self, *a):  # keep pytest output readable
            pass

    return Handler


@pytest.fixture(scope="module", params=OUTAGES)
def outage(request):
    """The built bundle over HTTP, with every `/api/` call failing."""
    port = _free_port()
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), functools.partial(_handler(request.param)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield request.param, f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


@pytest.fixture(scope="module")
def painted(outage):
    """One page load per outage shape, and what it left on the screen."""
    from playwright.sync_api import sync_playwright

    mode, base = outage
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            pg = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                pg.goto(base + "/", timeout=30_000, wait_until="load")
                # Long enough for the boot probe to fail and for whatever the
                # app decides to do about it to render. Deliberately not a
                # wait on the selector this test is about: waiting for the
                # thing under test to appear turns a failure into a timeout
                # and hides which of the two branches painted.
                pg.wait_for_timeout(2_500)
                return {
                    "mode": mode,
                    "topnav": pg.locator(".topnav").count(),
                    "alerts": pg.locator("[role='alert']").count(),
                    "down": pg.locator(".server-down").count(),
                    "text": " ".join((pg.inner_text("body") or "").split()),
                }
            finally:
                pg.close()
        finally:
            browser.close()


def test_the_outage_is_named_rather_than_painted_as_an_empty_dashboard(painted):
    """The signed-in shell must not be what an unreachable server renders.

    Measured before the fix, against bundle `dashboard/dist` built from the
    parent commit: `.topnav` present on both outage shapes, `.server-down`
    absent on both — a full dashboard, every panel empty, nothing anywhere
    saying the server had not answered.
    """
    if painted["topnav"]:
        pytest.fail(
            f"{painted['mode']}: the API never answered and the app still "
            f"painted the signed-in dashboard ({painted['topnav']} .topnav). "
            f"Body text: {painted['text'][:400]!r}")


def test_the_outage_screen_says_the_server_did_not_answer(painted):
    """Naming it is the point; `.topnav` being gone is not enough.

    A blank page also has no `.topnav`, and a blank page is the same failure
    wearing different clothes. So this asserts the positive: a live region an
    assistive technology announces, and prose that names the server rather
    than the operator's token — the outage is not a sign-in problem and must
    not read as one.
    """
    if not painted["down"]:
        pytest.fail(
            f"{painted['mode']}: no .server-down panel. "
            f"Body text: {painted['text'][:400]!r}")
    if not painted["alerts"]:
        pytest.fail(f"{painted['mode']}: the outage is on screen but carries "
                    f"no role=alert, so nothing announces it.")
    lowered = painted["text"].lower()
    if "server" not in lowered:
        pytest.fail(f"{painted['mode']}: the outage panel never names the "
                    f"server. Body text: {painted['text'][:400]!r}")
    if "token" in lowered:
        pytest.fail(f"{painted['mode']}: the outage panel talks about the "
                    f"token, which is the one thing this is not about. "
                    f"Body text: {painted['text'][:400]!r}")


# --- The recovery control, and what the headline is allowed to claim --------
#
# Everything above this line loads the page once and reads what the boot probe
# painted. UX-71 is not reachable that way: it is what happens when the one
# control on that screen is *pressed*, and the guard above says so in its own
# docstring — "a blank page is the same failure wearing different clothes" —
# without ever pressing the button. So the screen it protected shipped with a
# retry that unmounts it.
#
# Staging it needs a third outage shape, not a third parameter on `OUTAGES`.
# Both shapes above fail instantly, so the interval this is about — after the
# press, before the answer — does not exist in either. `slow-drop` accepts the
# connection, waits, and then drops it, which is what an unreachable host
# actually does: it resolves on a TCP timeout, not in a few milliseconds.

SLOW_DROP_SECONDS = 3.0

#: How long after the press to sample. Comfortably inside SLOW_DROP_SECONDS,
#: so the probe is certainly still in flight and the screen is whatever the
#: app decided to show while waiting.
SAMPLE_AFTER_MS = 700


def _slow_handler():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(DIST), **kw)

        def _api(self) -> None:
            time.sleep(SLOW_DROP_SECONDS)
            self.close_connection = True

        def do_GET(self):  # noqa: N802  (stdlib spelling)
            if self.path.startswith("/api/"):
                return self._api()
            return super().do_GET()

        def do_POST(self):  # noqa: N802
            return self._api()

        def log_message(self, *a):
            pass

    return Handler


@pytest.fixture(scope="module")
def retried():
    """Load under a slow outage, press Try again, and sample mid-probe.

    One browser session, three samples: what the outage screen looked like
    before the press, what it looked like while the retry was in flight, and
    whether the control could be pressed twice.
    """
    from playwright.sync_api import sync_playwright

    port = _free_port()
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), functools.partial(_slow_handler()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                pg = browser.new_page(viewport={"width": 1280, "height": 900})
                try:
                    pg.goto(f"http://127.0.0.1:{port}/",
                            timeout=30_000, wait_until="load")
                    pg.wait_for_selector(".server-down", timeout=20_000)
                    button = pg.get_by_role("button", name="Try again")
                    button.click()
                    pg.wait_for_timeout(SAMPLE_AFTER_MS)
                    return {
                        "down": pg.locator(".server-down").count(),
                        "root_children": pg.evaluate(
                            "document.getElementById('root').childElementCount"),
                        "buttons": pg.locator("button").count(),
                        "enabled": pg.locator("button:not([disabled])").count(),
                        "text": " ".join((pg.inner_text("body") or "").split()),
                    }
                finally:
                    pg.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


def test_pressing_try_again_does_not_erase_the_screen(retried):
    """The recovery control must not unmount the screen it is on.

    Measured before the fix, against the bundle built from `aba166b`: at
    +700ms after the press, `#root` held **0** children, `.server-down` count
    was **0**, and the body text was empty — for the whole interval, because
    `probe` re-entered the `checking` state that `App` renders as `null`.
    """
    if not retried["down"]:
        pytest.fail(
            "pressing Try again removed the outage screen: .server-down count "
            f"{retried['down']}, #root children {retried['root_children']}, "
            f"body text {retried['text'][:400]!r}. The one recovery control "
            "the product offers makes it look as though it has crashed.")


def test_the_retry_says_a_check_is_running(retried):
    """A press with no feedback is indistinguishable from a press that missed.

    Two things, because either alone is still ambiguous: the control that was
    pressed must refuse a second press while the first is in flight, and the
    screen must say in visible text that something is happening. A disabled
    button with no sentence beside it reads as broken.
    """
    if retried["enabled"]:
        pytest.fail(
            f"{retried['enabled']} of {retried['buttons']} button(s) are still "
            "enabled while the retry is in flight, so the operator can queue "
            f"probes by clicking. Body text: {retried['text'][:400]!r}")
    lowered = retried["text"].lower()
    if "checking" not in lowered:
        pytest.fail(
            "nothing on the screen says a check is running while the retry is "
            f"in flight. Body text: {retried['text'][:400]!r}")


def test_the_headline_does_not_contradict_the_evidence_line(painted):
    """The screen may not assert the server was silent while printing its reply.

    `describe(err)` renders `503 — staged outage` one line under a headline
    reading "The server did not answer". A 503 carrying a JSON detail *is* a
    server answering, and this is the one screen whose entire subject is the
    difference between empty and unknown.

    Measured before the fix: the `http-503` case painted "The server did not
    answer. Nothing on this page is known to be empty — it is unknown, which
    is a different thing. 503 — staged outage".
    """
    lowered = painted["text"].lower()
    silent = "did not answer" in lowered
    if painted["mode"] == "http-503" and silent:
        pytest.fail(
            "the 503 case claims the server did not answer, directly above "
            f"the answer it gave. Body text: {painted['text'][:400]!r}")
    if painted["mode"] == "no-reply" and not silent:
        pytest.fail(
            "the no-reply case is the one where the server genuinely did not "
            f"answer and the screen no longer says so. "
            f"Body text: {painted['text'][:400]!r}")
