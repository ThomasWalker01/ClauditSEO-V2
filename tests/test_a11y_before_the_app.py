"""axe over the two screens an operator sees when nothing is working.

UI-18, and UX-73 lives on one of them.

**The population, not the sweep, is the finding.** `test_a11y_rendered.py`
derives what it must cover from `parts[0] === "<name>"` in `App.tsx` — the
hash-route dispatcher. `LoginGate` and `Unreachable` are not hash routes.
They render *before* the router, chosen by `authState`, so no derivation keyed
on routes can ever see them however carefully it is written. The product's one
self-made compliance claim is WCAG 2.2 AA on its own dashboard, and it was
enforced over fourteen routes and neither of the two screens that paint when
the operator most needs the product to be legible.

**Measured before this file existed**, by running the population guard below
against an empty `BEFORE_THE_ROUTER` — it named both:

    App.tsx paints screens the accessibility sweep never audits, so the
    WCAG 2.2 AA claim does not hold for them: need-token, unreachable

Sixteen screens were swept (fourteen routes plus two extra states); eighteen
were served. Eighteen of eighteen now.

**Staged the way `test_server_outage_is_named.py` stages its outage**, because
the subject is what the browser draws when the API fails, which the real app
working correctly will not do: the built bundle over a stdlib server whose
`/api/` routes answer 401 or 503 rather than the app's own. Reusing that
shape rather than inventing one keeps both files failing the same way when
the bundle moves.

**Why the state union rather than the component names.** The population is
derived from `useState<"checking" | "need-token" | ...>` in `App.tsx` — the
declared vocabulary of the pre-router state machine. Deriving from the JSX
instead would answer "which components exist", which is not the question; a
state added to the union and handled by a new screen has to fail here, and a
state added and *not* handled has to fail here too. That is the same
inversion `test_every_route_the_app_serves_is_either_swept_or_excused`
records: the old direction iterated the list and asked whether each entry
still existed, so an addition was invisible to it and seven of fourteen
routes went unswept.

**`scripts/prove_fail.py` cannot answer for this file**, for the reason
`test_server_outage_is_named.py`, `test_site_switch.py` and
`test_fetch_state.py` all record: it reverts `dashboard/src` without
rebuilding `dashboard/dist`, which is what this test loads. That is now a
deliberate refusal rather than a gap - `needs_build` derives the set from
each file's own AST and this file is in it, so the script says CANNOT ANSWER
instead of answering wrongly. CQ-164, which this paragraph used to describe
as open, was that the set was a hand-kept tuple; it closed at `2f8eb02` and
report 083 records it under fixed. The count that stood here is removed
rather than updated, because it was a snapshot of a defect that no longer
exists.

Rule 1 was satisfied by hand, which here is the cheapest shape it takes: the
population guard was run with the list empty and printed the two names above.
The axe assertions are coverage rather than a defect guard — they audit two
screens nothing has ever audited — so what they claim is measured (sixteen
screens to eighteen) rather than proven red first.
"""

from __future__ import annotations

import functools
import http.server
import re
import socket
import threading
from pathlib import Path

import pytest

from clauditseo import axe

DIST = Path(__file__).resolve().parents[1] / "dashboard" / "dist"
APP_TSX = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "App.tsx"

pytestmark = [
    pytest.mark.skipif(not axe.available(),
                       reason="needs clauditseo[render] and `playwright install chromium`"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: Every screen `App.tsx` paints before the hash router gets a say, keyed by
#: the `authState` that selects it, with the API status that stages it.
#:
#: A 401 on the boot probe is what `LoginGate` is for; a 503 is one of the two
#: shapes `Unreachable` is for. The other shape — nothing listening at all —
#: is `test_server_outage_is_named.py`'s `no-reply`, and it is deliberately
#: not repeated here: it paints the same component through the same branch,
#: so auditing it would audit one screen twice and call it two.
BEFORE_THE_ROUTER: dict[str, tuple[int, str]] = {
    "need-token": (401, ".inline-form"),
    "unreachable": (503, ".server-down"),
}

#: States that select no screen of their own, with the reason. Only states
#: that render nothing belong here: a state that paints has to be audited.
NOT_A_SCREEN = {
    "checking": "renders null — the boot probe paints nothing until it settles",
    "ok": "hands over to the hash router, which test_a11y_rendered.py sweeps",
}

#: The declared vocabulary of the pre-router state machine.
AUTH_STATES = re.compile(r'useState<((?:"[a-z-]+"\s*\|\s*)*"[a-z-]+")>')


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _handler(status: int):
    """The built bundle, with every `/api/` call answering `status`."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(DIST), **kw)

        def _api(self) -> None:
            body = b'{"detail":"staged"}'
            self.send_response(status)
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


@pytest.fixture(scope="module", params=sorted(BEFORE_THE_ROUTER))
def audited(request):
    """One page load per pre-router screen, with axe run against it."""
    from playwright.sync_api import sync_playwright

    state = request.param
    status, ready = BEFORE_THE_ROUTER[state]
    port = _free_port()
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), functools.partial(_handler(status)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                pg = browser.new_page(viewport={"width": 1280, "height": 900})
                try:
                    pg.goto(f"http://127.0.0.1:{port}/", timeout=30_000,
                            wait_until="load")
                    # Allowed to raise, as the route sweep's `READY` waits are.
                    # A screen whose own content never appears is a failure to
                    # report, not a slower one to sit through — and a flat
                    # sleep makes "never painted" and "painted late" the same
                    # silent outcome.
                    pg.wait_for_selector(ready, timeout=20_000)
                    pg.add_script_tag(
                        content=axe.AXE_JS.read_text(encoding="utf-8"))
                    result = pg.evaluate("""() => axe.run(document, {
                        runOnly: { type: 'tag',
                                   values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] },
                        resultTypes: ['violations'],
                    }).then(r => ({ violations: r.violations.map(v => ({
                        id: v.id, impact: v.impact,
                        nodes: v.nodes.map(n => ({ target: n.target,
                                                   failureSummary: n.failureSummary })),
                    })) }))""")
                    return state, result["violations"]
                finally:
                    pg.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


def test_the_screen_has_no_detectable_violations(audited):
    """The WCAG 2.2 AA claim, on the screens it was never enforced over."""
    state, violations = audited
    if violations:
        lines = []
        for v in violations:
            node = (v.get("nodes") or [{}])[0]
            summary = (node.get("failureSummary") or "").splitlines()
            lines.append(
                f"  {v.get('id')} ({v.get('impact')}, "
                f"{len(v.get('nodes') or [])} node(s)): "
                f"{' '.join(node.get('target') or [])}\n"
                f"      {summary[-1] if summary else ''}")
        pytest.fail(f"axe found {len(violations)} violation(s) on the "
                    f"{state} screen:\n" + "\n".join(lines))


def test_every_screen_the_app_paints_before_the_router_is_audited_or_excused():
    """Inverted, for the reason the route sweep's own population records.

    Iterating `BEFORE_THE_ROUTER` and checking each entry still exists would
    make an *addition* invisible, which is exactly how seven of fourteen
    routes went unswept while the compliance claim was made for all of them.
    So the list is checked against what `App.tsx` declares, not the other way
    round.
    """
    app = APP_TSX.read_text(encoding="utf-8")
    match = AUTH_STATES.search(app)
    assert match, (
        "App.tsx no longer declares its pre-router states as a string union, "
        "so this population cannot be derived — repair the derivation rather "
        "than replacing it with a hand-kept list")
    declared = set(re.findall(r'"([a-z-]+)"', match.group(1)))
    missing = sorted(declared - set(BEFORE_THE_ROUTER) - set(NOT_A_SCREEN))
    assert not missing, (
        "App.tsx paints screens the accessibility sweep never audits, so the "
        "WCAG 2.2 AA claim does not hold for them: " + ", ".join(missing)
        + ". Add them to BEFORE_THE_ROUTER with the API status that stages "
          "them, or name them in NOT_A_SCREEN with the reason — do not trim "
          "the list to make this pass.")


def test_the_staged_screen_is_the_one_the_state_names():
    """Being in the population is not being painted.

    A route can load and paint nothing, which is what the anatomy facts
    panels did for months — `test_a11y_rendered.py` says so about itself, and
    the same hole is open one layer earlier. The `ready` selector in
    `BEFORE_THE_ROUTER` is what closes it: `audited` waits on it and raises
    rather than auditing an empty document, so a clean axe result here cannot
    be a result about a blank page.
    """
    for state, (status, ready) in BEFORE_THE_ROUTER.items():
        assert status >= 400, (
            f"{state} is staged with a {status}, which does not fail the boot "
            "probe, so the screen under test is not the one that paints")
        assert ready.startswith("."), (
            f"{state} names no class of its own to wait on, so the audit "
            "could run against a document that never rendered it")
