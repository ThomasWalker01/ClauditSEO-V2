"""Item 143 step BD, stage two: the well-known path sweep.

One ordinary GET per path, once per site, and the checks it feeds need the
content signature of what they name - never the status alone, because a site
that answers every path with its own page and a 200 would otherwise read as
exposing everything.
"""

from __future__ import annotations

from clauditseo.crawler import wellknown
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Severity, Tier
from clauditseo.modules import sec

HOME = "https://x.test/"


def _row(path, status=200, head="", ctype="text/plain", final=None):
    return {"path": path, "purpose": dict(wellknown.PATHS).get(path, "error-leak"),
            "url": HOME.rstrip("/") + path, "status": status,
            "final_url": final or HOME.rstrip("/") + path,
            "content_type": ctype, "length": len(head), "head": head}


def _run(rows, not_found=None):
    page = Page(url=HOME, requested_url=HOME, status=200,
                headers={"content-type": "text/html"}, content="<html></html>",
                content_type="text/html")
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[page])
    crawl.well_known = {"fetched": rows,
                        "not_found": not_found or _row("/nf", 404, "<html>nope</html>", "text/html"),
                        "user_agent": "UA", "at": "2026-09-14T00:00:00Z"}
    return {f.check_id: f for f in sec.SecurityModule().run([], Tier.T2, {"crawl": crawl})}


def test_a_site_that_answers_every_path_with_its_own_page_exposes_nothing():
    page = "<!doctype html><html><head><title>Twenty22</title></head><body>Home</body></html>"
    rows = [_row(path, 200, page, "text/html; charset=UTF-8") for path, _ in wellknown.PATHS]
    got = _run(rows)
    for check in ("exposed-file", "directory-listing", "cms-xmlrpc", "cms-user-enumeration",
                  "cms-registration-open", "error-leak"):
        assert check not in got, (check, got[check].summary if check in got else "")


def test_an_exposed_credential_file_is_critical_and_a_manifest_alone_is_not():
    got = _run([_row("/.env", head="APP_KEY=base64:abc\nDB_PASSWORD=hunter2\n")])
    assert got["exposed-file"].severity is Severity.CRITICAL
    assert "contents are not stored" in got["exposed-file"].evidence["note"]
    got = _run([_row("/package.json", head='{"name": "x", "dependencies": {"a": "1"}}',
                     ctype="application/json")])
    assert got["exposed-file"].severity is Severity.MEDIUM


def test_a_git_head_needs_its_signature():
    assert "exposed-file" in _run([_row("/.git/HEAD", head="ref: refs/heads/main\n")])
    assert "exposed-file" not in _run([_row("/.git/HEAD", head="Not here")])


def test_listing_xmlrpc_users_registration_and_the_error_page():
    rows = [
        _row("/wp-content/uploads/", head="<html><head><title>Index of /wp-content/uploads</title>",
             ctype="text/html"),
        _row("/xmlrpc.php", 405, "XML-RPC server accepts POST requests only."),
        _row("/wp-json/wp/v2/users", head='[{"id":1,"name":"admin","slug":"admin"}]',
             ctype="application/json"),
        _row("/wp-login.php?action=register", head='<form><input name="user_email"></form>',
             ctype="text/html", final=HOME + "wp-login.php?action=register"),
    ]
    got = _run(rows, not_found=_row("/nf", 404, "<b>Fatal error</b>: Uncaught Error in "
                                                 "/var/www/html/index.php on line <b>12</b>",
                                    "text/html"))
    assert got["directory-listing"].evidence["paths"] == ["/wp-content/uploads/"]
    assert "cms-xmlrpc" in got and "cms-user-enumeration" in got
    assert "cms-registration-open" in got and "error-leak" in got


def test_registration_turned_off_is_not_open():
    rows = [_row("/wp-login.php?action=register", head="<form></form>", ctype="text/html",
                 final=HOME + "wp-login.php?registration=disabled")]
    assert "cms-registration-open" not in _run(rows)


def test_security_txt_needs_a_contact_line():
    assert "security-txt" in _run([_row("/.well-known/security.txt", 404, "")])
    assert "security-txt" not in _run([_row("/.well-known/security.txt",
                                            head="Contact: mailto:security@x.test\n")])


def test_no_sweep_raises_nothing_and_reads_not_assessed():
    page = Page(url=HOME, requested_url=HOME, status=200, headers={}, content="",
                content_type="text/html")
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[page])
    got = {f.check_id for f in sec.SecurityModule().run([], Tier.T2, {"crawl": crawl})}
    assert not got & sec.WELL_KNOWN_CHECKS
    import inspect

    from clauditseo.persistence import runs
    assert "this run did not fetch the well-known paths" in inspect.getsource(runs.not_assessed_payload)


def test_the_sweep_asks_each_path_once_with_get_only(make_site, monkeypatch):
    """Passive: one GET per path plus the not-found probe, and no other method."""
    import httpx

    methods: list[str] = []
    real = httpx.Client.request

    def spy(self, method, url, *a, **k):
        methods.append(method)
        return real(self, method, url, *a, **k)

    monkeypatch.setattr(httpx.Client, "request", spy)
    site = make_site({"/.well-known/security.txt": (200, {"Content-Type": "text/plain"},
                                                    "Contact: mailto:s@x.test\n")})
    out = wellknown.sweep(site.base_url + "/")
    assert set(methods) == {"GET"}
    assert len(methods) == len(wellknown.PATHS) + 1
    assert len(site.request_log) == len(wellknown.PATHS) + 1
    assert out["not_found"]["status"] == 404
    fetched = {r["path"]: r for r in out["fetched"]}
    assert fetched["/.well-known/security.txt"]["status"] == 200


def test_the_sweep_is_opt_in_and_skipped_on_a_verification():
    import inspect

    from clauditseo.crawler import crawl as crawl_mod
    src = inspect.getsource(crawl_mod.crawl)
    assert "if security_paths and only_urls is None:" in src
    from clauditseo import adaptive
    asrc = inspect.getsource(adaptive)
    assert 'security_paths="SEC" in dims' in asrc
    assert "deep_crawl.well_known = pulse_crawl.well_known" in asrc


def test_the_report_discloses_every_well_known_path_the_sweep_fetched():
    """143 addendum: the count in the sentence equals the sweep's own request
    count, the examples are real paths from it, and the user agent and date are
    the ones it used. Rendered in both audiences."""
    from clauditseo.reporting.render import well_known_disclosure
    wk = {"fetched": [_row(p) for p, _ in wellknown.PATHS], "user_agent": "ClauditSEO/0.22",
          "at": "2026-09-14T01:02:03Z"}
    line = well_known_disclosure(wk)
    assert f"requested {len(wellknown.PATHS)} well-known paths" in line
    assert "/.git/HEAD" in line and "/wp-login.php" in line
    assert "ClauditSEO/0.22" in line and "2026-09-14" in line
    assert well_known_disclosure(None) == ""
    import inspect

    from clauditseo.reporting import render
    src = inspect.getsource(render.render_run_report)
    i = src.index("disclosure = well_known_disclosure")
    assert "audience" not in src[i:i + 200], "the disclosure is gated on the audience"


def test_sweep_security_rows_reach_the_client_copy_and_the_injection_note_does_not():
    from clauditseo.reporting import render
    assert render.INTERNAL_SECURITY_CHECKS == frozenset({"prompt-injection-content"})
    import inspect
    src = inspect.getsource(render.render_run_report)
    assert 'f["dimension"] != "SEC"' not in src
