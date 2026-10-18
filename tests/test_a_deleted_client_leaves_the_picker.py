"""A deleted client leaves the add-site picker (operator report, 10 October).

Home's "Add a client or site" holds two lists of clients: the Clients
disclosure, where one is deleted, and the `Client…` picker beside the domain
field. The disclosure re-read after a delete; the picker had fetched once and
never again, so a deleted client stayed on offer until the page was reloaded,
and a site added to it would have been posted to a client that no longer
exists.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from tests.needs_build import needs_build

pw = pytest.importorskip("playwright")

PICKER = "select[aria-label='client for the new site']"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    import httpx
    import uvicorn

    from clauditseo.api.app import create_app

    db = tmp_path_factory.mktemp("picker") / "clauditseo.db"
    server = uvicorn.Server(uvicorn.Config(create_app(db_path=db), host="127.0.0.1",
                                           port=_free_port(), log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")
    base = f"http://127.0.0.1:{server.config.port}"
    for name in ("Keeper", "Leaver"):
        httpx.post(f"{base}/api/clients", json={"name": name}, timeout=30)
    try:
        yield base
    finally:
        server.should_exit = True


def _offered(page) -> list[str]:
    return page.eval_on_selector_all(
        f"{PICKER} option", "els => els.filter(e => e.value).map(e => e.textContent)")


@needs_build
def test_a_deleted_client_leaves_the_picker(served):
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(f"{served}/#/", wait_until="networkidle")
            page.click(".home-add-open")
            page.wait_for_selector(f"{PICKER} option[value]:not([value=''])",
                                   state="attached", timeout=15000)
            # The guard can disagree: the client under test must be on offer
            # first, and chosen, so the clearing is exercised too.
            assert sorted(_offered(page)) == ["Keeper", "Leaver"], _offered(page)
            page.select_option(PICKER, label="Leaver")

            page.click(".home-clients summary")
            page.click("button[aria-label='delete client Leaver']")
            page.click(".confirm-dialog .confirm-go")

            page.wait_for_function(
                "() => fetch('/api/clients').then(r => r.json())"
                ".then(cs => !cs.some(c => c.name === 'Leaver'))", timeout=15000)
            try:
                page.wait_for_function(
                    "s => ![...document.querySelectorAll(s + ' option')]"
                    ".some(o => o.textContent === 'Leaver')",
                    arg=PICKER, timeout=8000)
            except PWTimeout:
                pass

            assert _offered(page) == ["Keeper"], (
                "a client deleted under Clients is still offered by the add-site "
                f"picker until the page is reloaded: {_offered(page)}")
            assert page.eval_on_selector(PICKER, "e => e.value") == "", (
                "the picker still holds the deleted client as its choice")
        finally:
            browser.close()
