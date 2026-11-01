"""What an audit may do at a firewall that refuses its browser: wait and ask once,
find out before the crawl, and show a header the site's owner issued, to that
site alone.
"""
from __future__ import annotations

import httpx
import pytest

from clauditseo import secrets
from clauditseo.crawler import access
from clauditseo.crawler.fetch import Fetcher
from clauditseo.crawler.types import BrowserChallenged


@pytest.fixture(autouse=True)
def no_run_left_behind():
    """A real run has a thread of its own; these share the suite's."""
    yield
    access._run.set(None)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_SECRETS_FILE", str(tmp_path / "secrets.json"))


@pytest.fixture
def waits(monkeypatch):
    slept = []
    monkeypatch.setattr(access.time, "sleep", slept.append)
    return slept


def _refused(*a, **k):
    raise BrowserChallenged("Vercel", "https://shop.test/")


def _run(store=None, say=None):
    return access.open_run("s", "www.shop.test", say)


def test_a_refusal_that_clears_costs_one_wait(store, waits):
    _run()
    answers = iter([BrowserChallenged("Vercel", "u"), "read"])

    def load():
        got = next(answers)
        if isinstance(got, Exception):
            raise got
        return got
    assert access.retried(load) == "read"
    assert waits == [access.RETRY_WAIT_S]


def test_a_second_refusal_stops_every_later_pass_without_a_wait(store, waits):
    run = _run()
    with pytest.raises(BrowserChallenged):
        access.retried(_refused)
    assert run.refused and len(waits) == 1
    asked = []
    assert access.each_page(["a", "b"], asked.append, lambda *a: None) == {}
    assert asked == [] and len(waits) == 1


def test_the_wait_is_said_on_the_run(store, waits):
    said = []
    _run(say=said.append)
    with pytest.raises(BrowserChallenged):
        access.retried(_refused)
    assert "waiting 5 minutes" in said[0] and "stop here" in said[1]


def test_outside_a_run_nothing_waits(waits):
    access._run.set(None)
    with pytest.raises(BrowserChallenged):
        access.retried(_refused)
    assert waits == []


def test_a_refused_probe_spares_the_passes(store, monkeypatch):
    from clauditseo import renderer
    monkeypatch.setenv("CLAUDITSEO_TRACE_PERF", "1")
    monkeypatch.setattr(renderer.Renderer, "available", lambda self: True)
    monkeypatch.setattr(renderer.Renderer, "render", _refused)
    run = _run()
    assert access.probe_browser("https://www.shop.test/") == "Vercel"
    assert run.refused is not None


def test_the_probe_stays_off_where_the_browser_pass_is_off(store, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_TRACE_PERF", "0")
    _run()
    assert access.probe_browser("https://www.shop.test/") is None


def _fetch_through(url, redirect_to=None):
    seen = []

    def answer(request):
        seen.append((str(request.url), request.headers.get("x-pass")))
        if redirect_to and str(request.url) == url:
            return httpx.Response(302, headers={"location": redirect_to})
        return httpx.Response(200, text="ok")
    fetcher = Fetcher(timeout_s=5)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(answer),
                                   follow_redirects=True,
                                   event_hooks=access.event_hooks())
    fetcher.fetch(url)
    return seen


def test_the_pass_goes_to_the_site_and_its_www(store):
    secrets.put_site_header("s", "x-pass", "owners-secret")
    _run()
    assert _fetch_through("https://shop.test/")[0][1] == "owners-secret"
    assert _fetch_through("https://www.shop.test/")[0][1] == "owners-secret"


def test_the_pass_goes_nowhere_else(store):
    secrets.put_site_header("s", "x-pass", "owners-secret")
    _run()
    assert _fetch_through("https://cdn.other.test/")[0][1] is None


def test_a_redirect_off_the_site_loses_the_pass(store):
    secrets.put_site_header("s", "x-pass", "owners-secret")
    _run()
    seen = _fetch_through("https://www.shop.test/", "https://elsewhere.test/")
    assert seen[0][1] == "owners-secret" and seen[1] == ("https://elsewhere.test/", None)


def test_a_browser_sends_the_pass_to_the_site_alone(store):
    secrets.put_site_header("s", "x-pass", "owners-secret")
    _run()

    class Request:
        headers = {"accept": "*/*"}

        def __init__(self, url):
            self.url = url

    class Route:
        def __init__(self, url):
            self.request = Request(url)
            self.sent = None

        def continue_(self, headers=None):
            self.sent = headers

    class Context:
        def route(self, pattern, handler):
            self.handler = handler

    context = Context()
    access.install(context)
    own, third = Route("https://www.shop.test/a"), Route("https://tracker.test/t.js")
    context.handler(own)
    context.handler(third)
    assert own.sent["x-pass"] == "owners-secret" and third.sent is None


def test_no_pass_installs_nothing(store):
    _run()

    class Context:
        def route(self, *a):
            raise AssertionError("routing changes how a page loads")
    access.install(Context())


def test_the_user_agent_matrix_goes_without_the_pass(store):
    fetcher = Fetcher(timeout_s=5, site_pass=False)
    assert not fetcher._client.event_hooks["request"]
    fetcher.close()


def test_the_store_is_not_the_keys_file_and_can_be_emptied(store):
    secrets.put_site_header("s", "x-pass", "owners-secret")
    assert secrets.site_header("s") == ("x-pass", "owners-secret")
    assert "owners-secret" not in str(secrets.load())
    assert secrets.drop_site_header("s") is True
    assert secrets.site_header("s") is None and secrets.drop_site_header("s") is False
