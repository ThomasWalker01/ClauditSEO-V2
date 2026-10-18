"""Shared test infrastructure: a local threaded HTTP server that serves a
dict of routes and logs every request path — the backbone of the crawler and
fixture-site gates. Nothing here ever touches the real internet."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_modal_error_boxes():
    """Keep Windows from putting a modal box on the operator's desktop.

    `test_the_prover_reports_only_a_verdict_it_earned.py` plants a
    `pytest.exe` that is not a runnable image, on purpose. Launched from the
    agent's shell that spawn fails quietly; launched detached, Windows showed
    "Unsupported 16-Bit Application" on the desktop (2026-09-13) and the
    suite sat behind it until someone clicked OK. The process error mode is
    inherited by every child, so setting it once here covers each subprocess
    the suite starts.
    """
    import sys
    if sys.platform == "win32":
        import ctypes
        SEM_FAILCRITICALERRORS, SEM_NOGPFAULTERRORBOX = 0x0001, 0x0002
        SEM_NOOPENFILEERRORBOX = 0x8000
        ctypes.windll.kernel32.SetErrorMode(
            SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX)
    yield


@pytest.fixture(autouse=True)
def _integrity_threshold_is_its_own_subject(request, monkeypatch):
    """Brief v23 step BL: no client report while a Critical or High finding in
    the run is unassessed. Every report fixture in this suite seeds open Highs
    and generates a client document to test what the document SAYS, so the
    threshold, live, turned some sixty clauses about wording into clauses about
    assessment state.

    Off by default here and live under `@pytest.mark.integrity_threshold`,
    which is where it is the subject
    (`test_the_report_cannot_be_generated_with_an_unassessed_critical_or_high.py`).
    Patched at `runs.open_severe` (item 239 step 7: the site's open Critical
    and High, which replaced one run's `unassessed_severe`), the one function
    the refusal reads, so the product has no bypass - only the suite has, and
    only by name.
    """
    if request.node.get_closest_marker("integrity_threshold"):
        yield
        return
    from clauditseo.persistence import runs
    monkeypatch.setattr(runs, "open_severe",
                        lambda *a, **k: {"count": 0, "critical": 0, "high": 0})
    yield


@pytest.fixture(autouse=True, scope="session")
def _reports_out_of_the_operators_directory(tmp_path_factory):
    """Keep generated documents out of the operator's own output directory.

    `generate.OUT_DIR` is a module-level path under the repo, so every test
    that produced a deliverable wrote it next to the real ones. Nothing failed
    — the documents are gitignored — until cleaning up after a throwaway run
    meant globbing a directory holding live files, which destroyed the
    operator's stored deliverables twice.

    Autouse and session-scoped rather than a parameter passed at each of the
    seventeen call sites, for the same reason as `_hermetic_config` below: the
    failure is silent, so the guard has to cover the test nobody has written
    yet. A test that genuinely needs a specific location passes `out_dir=`.
    """
    from clauditseo.reporting import generate

    previous = generate.OUT_DIR
    generate.OUT_DIR = tmp_path_factory.mktemp("reports-out")
    yield
    generate.OUT_DIR = previous


@pytest.fixture(autouse=True, scope="session")
def _hermetic_config(tmp_path_factory):
    """Keep the suite off the developer's real credentials.

    Two sources, both of which would otherwise make "provider unconfigured"
    tests depend on whose machine is running them:

    - On Windows the config falls back to the HKCU registry for keys set with
      `setx`, which a running process never inherits.
    - The operator's key store, which outranks the environment. A test that
      built Settings would read whatever the admin panel had saved — so a
      suite that passed on a fresh checkout could fail the moment someone
      entered a key in the app, and worse, tests would be quietly exercising
      real credentials.

    Both are neutralised here rather than per-file, because the failure is
    silent: nothing announces that a test just read a live key.
    """
    import os
    store = tmp_path_factory.mktemp("secrets") / "secrets.json"
    previous = {name: os.environ.get(name) for name in
                ("CLAUDITSEO_NO_ENV_FALLBACK", "CLAUDITSEO_SECRETS_FILE")}
    os.environ["CLAUDITSEO_NO_ENV_FALLBACK"] = "1"
    os.environ["CLAUDITSEO_SECRETS_FILE"] = str(store)
    # And off the performance trace pass, which is ON by default in the
    # product since item 141's depth-pill stage. This is a cost decision and
    # not a correctness one: the trace is a THROTTLED browser pass - 4x CPU,
    # Slow-4G, a 2.5s settle per page - so a suite that launched one per
    # fixture audit would pay minutes for coverage its own Speed tests already
    # get. `test_the_speed_part_page_visuals` and
    # `test_the_speed_trace_checks` drive stored traces directly, and the one
    # clause that needs the real pass asks for it by unsetting this.
    previous["CLAUDITSEO_TRACE_PERF"] = os.environ.get("CLAUDITSEO_TRACE_PERF")
    os.environ["CLAUDITSEO_TRACE_PERF"] = "0"
    yield
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class FixtureSite:
    """routes: path -> (status, headers, body). Redirects are just routes with
    a 3xx status and a Location header. Every request path is logged."""

    def __init__(self, routes: dict[str, tuple[int, dict[str, str], str]]):
        self.routes = dict(routes)
        self.request_log: list[str] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (http.server API)
                site.request_log.append(self.path)
                entry = site.routes.get(self.path)
                if entry is None:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html><body>not found</body></html>")
                    return
                status, headers, body = entry
                delay = headers.get("X-Fixture-Delay")
                if delay:
                    import time
                    time.sleep(float(delay))
                payload = body.encode("utf-8")
                self.send_response(status)
                if "Content-Type" not in headers and "Location" not in headers:
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # keep pytest output clean
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "FixtureSite":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def make_site():
    """Factory fixture: make_site(routes) -> started FixtureSite, auto-stopped."""
    sites: list[FixtureSite] = []

    def _make(routes: dict[str, tuple[int, dict[str, str], str]]) -> FixtureSite:
        site = FixtureSite(routes).start()
        sites.append(site)
        return site

    yield _make
    for site in sites:
        site.stop()
