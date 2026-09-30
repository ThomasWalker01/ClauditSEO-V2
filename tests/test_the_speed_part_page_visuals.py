"""The Speed part's six visuals and its per-template vitals strip (item 141,
brief v19 step BC).

The brief asks for six pictures, each drawn from a Block 1 field and none
decorative, plus a strip of the four vitals per template with `lab`/`field`
labelled. `runs.speed_now_payload` is what they are drawn from; this pins that
payload, and the rendered clauses below pin the six actually being on screen.

**Five of these clauses are regressions on defects the FIRST LIVE BIRCH TRACE
put on the page, and they are named as such rather than written as if the code
had been right.** DISCIPLINE rule 1 has no "before" for a payload that did not
exist, but it does for these five — each was observed on screen against the
committed code and each is asserted here in the shape that failed:

  * the template read `/https:/www.beacon.com.au/<slug>` — `derive_pattern`
    takes a PATH and was handed a whole URL;
  * the strip read `traced 12 of 0 pages crawled` — the denominator was filtered
    by the START URL's host, and the crawl started at the apex while every page
    came back on `www.`;
  * `www.beacon.com.au` sat in its own third-party ledger with 1,658 ms
    against it, above two real third parties;
  * a 1,388 ms image that blocks nothing drew the longest bar in a table headed
    "resources by blocking time";
  * two hosts that shipped nothing read `1 KB`.

The sixth clause — that the sub-parts sum to the LCP — is the brief's own
accept criterion and passed from the start; it is here so that the day a
sub-part is computed from a different page than the figure above it, the
screen's central claim fails loudly.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.parts import open_part

#: One trace, in the stored shape `perf.trace` writes. Deliberately built with
#: the two spellings of the host that broke the ledger: the page is on `www.`
#: and the crawl started at the apex.
FIRST_PARTY = "https://www.x.test"


@pytest.fixture
def browser():
    """A browser rather than a page: the rendered clause serves a doctored
    anatomy payload, and a route has to be attached before the navigation."""
    from clauditseo import axe

    if not axe.available():
        pytest.skip("needs clauditseo[render] and `playwright install chromium`")
    if not (DIST / "index.html").is_file():
        pytest.skip("dashboard not built (npm run build in dashboard/)")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


def _trace(*, lcp_ms=2500.0, ttfb=300.0, sub=None, resources=None,
           long_tasks=None, frames=None, tbt=120.0, cls=0.05):
    return {
        "device_profile": "mid-tier mobile, 4G; applied throttling",
        "ttfb_ms": ttfb, "fcp_ms": 800.0,
        "lcp": {"ms": lcp_ms, "element": "img", "url": f"{FIRST_PARTY}/hero.jpg",
                "is_image": True, "observed": True,
                "sub_parts": sub if sub is not None else {
                    "ttfb": ttfb, "load_delay": 900.0,
                    "load_time": 1200.0, "render_delay": lcp_ms - ttfb - 2100.0}},
        "cls": {"value": cls, "shifts": []},
        "tbt_ms": tbt, "long_tasks": long_tasks if long_tasks is not None else [
            {"start_ms": 900, "duration_ms": 300, "scripts": [
                # The first party, spelled WITH `www.` — the apex is the start
                # URL, so a ledger comparing as-written charges the site itself.
                {"url": f"{FIRST_PARTY}/app.js", "ms": 200},
                {"url": "https://cdn.third.test/w.js", "ms": 90}]}],
        "resources": resources if resources is not None else [
            {"url": f"{FIRST_PARTY}/theme.css", "type": "css", "bytes": 40000,
             "transfer": 41000, "blocking": True, "async": False, "defer": False,
             "media": None, "discovered_by": "head", "cache_control": None,
             "compression": "br", "coverage": "unavailable",
             "whitespace_ratio": 0.02, "start_ms": 310.0, "duration_ms": 120.0},
            # Blocks nothing and takes the longest — the row that drew the
            # biggest bar in a table headed by blocking time.
            {"url": f"{FIRST_PARTY}/hero.jpg", "type": "image", "bytes": 18000,
             "transfer": 18500, "blocking": False, "async": True, "defer": True,
             "media": None, "discovered_by": "img", "cache_control": None,
             "compression": "none", "coverage": "unavailable",
             "whitespace_ratio": "unavailable", "start_ms": 400.0,
             "duration_ms": 1388.0},
            # A third party that shipped no bytes at all.
            {"url": "https://beacon.third.test/p", "type": "other", "bytes": 0,
             "transfer": 0, "blocking": False, "async": False, "defer": False,
             "media": None, "discovered_by": "script", "cache_control": None,
             "compression": "none", "coverage": "unavailable",
             "whitespace_ratio": "unavailable", "start_ms": 500.0,
             "duration_ms": 20.0},
            {"url": "https://cdn.third.test/w.js", "type": "script",
             "bytes": 90000, "transfer": 91000, "blocking": False,
             "async": True, "defer": False, "media": None,
             "discovered_by": "script", "cache_control": "max-age=60",
             "compression": "br", "coverage": "unavailable",
             "whitespace_ratio": 0.01, "start_ms": 520.0, "duration_ms": 210.0},
        ],
        "fonts": [], "head_rendered": "<head></head>",
        "frames": frames if frames is not None else [
            {"name": "a" * 32 + "-frame0.jpg", "order": 0, "t_ms": 0.0,
             "label": "loading"},
            {"name": "a" * 32 + "-frame1.jpg", "order": 1, "t_ms": 800.0,
             "label": "FCP"},
            {"name": "a" * 32 + "-frame2.jpg", "order": 2, "t_ms": lcp_ms,
             "label": "LCP"}],
    }


def _seed(tmp_path, pages):
    """A stored run whose evidence carries `perf` on each page record — which is
    where `crawler.evidence.snapshot` puts a trace, and so where the payload
    reads it back from."""
    conn = connect(tmp_path / "bc.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "BC Co")
    site_id = repo.create_site(conn, client, "x.test")
    run_id = runs.create_run(conn, site_id, ["PRF"], "T2")
    runs.store_evidence(conn, run_id, {
        # The apex, while every page is on `www.` — the live case.
        "start_url": "https://x.test/",
        "sitemap_entries": [], "sitemaps": [],
        "pages": [{"url": url, "status": 200, "content_type": "text/html",
                   "content": "<html></html>", "outlinks": [],
                   "perf": trace} for url, trace in pages],
    })
    runs.mark_complete(conn, run_id, "2026-09-11T00:00:00")
    return conn, run_id


def _payload(tmp_path, pages):
    conn, run_id = _seed(tmp_path, pages)
    return runs.speed_now_payload(conn, run_id)


# --- the brief's own accept criterion ---------------------------------------

def test_the_sub_parts_sum_to_the_lcp_they_explain(tmp_path):
    """The brief's accept, and the reason every picture below the strip is ONE
    named page rather than the template's average: an average of four pages'
    sub-parts sums to an average that is no page's LCP, so the bar would not
    explain the figure above it."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace(lcp_ms=2500.0)),
                              (f"{FIRST_PARTY}/b", _trace(lcp_ms=3100.0))])
    t = now["templates"][0]
    sub = t["lcp"]["sub_parts"]
    assert isinstance(sub, dict), sub
    assert t["lcp"]["sub_total"] == pytest.approx(t["lcp"]["ms"], abs=0.11), (
        f"the sub-parts do not sum to the LCP they explain: {sub} against "
        f"{t['lcp']['ms']}")
    # And the page they were read off is NAMED, so nobody reads the bar as the
    # template's average.
    assert t["page"] in (f"{FIRST_PARTY}/a", f"{FIRST_PARTY}/b"), t["page"]
    # The dominant part is the payload's call, not the renderer's: two
    # components picking a maximum is two chances to pick differently.
    assert t["lcp"]["dominant"] == max(sub, key=lambda k: sub[k])


# --- the five the live trace found ------------------------------------------

def test_a_template_is_the_url_pattern_and_not_the_whole_url(tmp_path):
    """`derive_pattern` takes a PATH — its own signature says so. Handed the
    whole URL it produced `/https:/www.beacon.com.au/<slug>`, a template
    nothing on the site matches and a picker chip nobody could read."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/blog/one", _trace()),
                              (f"{FIRST_PARTY}/blog/two", _trace()),
                              (f"{FIRST_PARTY}/", _trace())])
    patterns = {t["pattern"] for t in now["templates"]}
    assert patterns == {"/blog/<slug>", "/"}, patterns
    for pattern in patterns:
        assert "http" not in pattern and "x.test" not in pattern, pattern
    # Two blog pages under one template, and the largest template first: the
    # part opens on the one most of the site is built from.
    assert now["templates"][0]["pattern"] == "/blog/<slug>"
    assert now["templates"][0]["pages"]["value"] == 2


def test_the_traced_count_states_a_denominator_it_could_have_traced(tmp_path):
    """The strip read `traced 12 of 0 pages crawled` on the first live trace:
    the denominator was filtered by the START URL's host, and the crawl started
    at the apex while every page came back on `www.`. The crawl is same-site by
    construction — that is the crawler's rule, not this payload's to re-apply."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace()),
                              (f"{FIRST_PARTY}/b", _trace())])
    traced = now["traced"]
    assert traced["value"] == 2 and traced["of"] == 2, traced
    # Item 155: and it says which population that is.
    assert traced["population"] == "crawl" and traced["basis"] == "crawled"
    assert traced["value"] <= traced["of"], traced


def test_the_first_party_is_not_a_third_party_to_itself(tmp_path):
    """`www.beacon.com.au` sat in its own ledger with 1,658 ms of
    main-thread work against it, above two real third parties — the site's own
    host, charged as a vendor, because the start URL was the apex and the
    resources came back on `www.`.

    A subdomain that is not `www.` is deliberately still a third party:
    `static.parastorage.com` is a vendor to `parastorage.com` in every sense
    that matters here, and collapsing it would hide the heaviest host on the
    live site."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace())])
    hosts = {r["host"] for r in now["templates"][0]["third_parties"]}
    assert "www.x.test" not in hosts and "x.test" not in hosts, hosts
    assert "cdn.third.test" in hosts, hosts
    # The main thread is charged from Long Animation Frames' per-script
    # attribution, which is the only source that can charge a host at all.
    cdn = next(r for r in now["templates"][0]["third_parties"]
               if r["host"] == "cdn.third.test")
    assert cdn["main_thread_ms"] == 90, cdn


def test_a_resource_that_blocks_nothing_carries_no_blocking_time(tmp_path):
    """A 1,388 ms image drew the longest bar in a table headed "resources by
    blocking time". Its blocking cost is nothing; its duration is 1,388 ms, and
    those are two different columns."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace())])
    rows = {(r["url"] or "").rsplit("/", 1)[-1]: r
            for r in now["templates"][0]["resources"]}
    hero = rows["hero.jpg"]
    assert hero["cost"] == "fine", hero
    assert hero["ms"] is None, (
        f"a resource that blocks nothing carries a blocking time: {hero}")
    assert hero["duration_ms"] == 1388.0, hero
    # The render-blocking stylesheet does carry one, and it is its duration.
    css = rows["theme.css"]
    assert css["cost"] == "render" and css["ms"] == 120.0, css
    # Render-blocking first, whatever it cost: the order a reader fixes in.
    assert now["templates"][0]["resources"][0]["cost"] == "render"


def test_a_host_that_shipped_nothing_is_not_reported_as_a_kilobyte(tmp_path):
    """Two Birch hosts read `1 KB` having transferred nothing: a floor meant to
    stop a 300-byte script reading as zero, applied to an actual zero.

    Asserted on the payload rather than on the rendered string, because the
    payload is where the number is decided — the renderer's job is only to draw
    a dash for it."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace())])
    beacon = next(r for r in now["templates"][0]["third_parties"]
                  if r["host"] == "beacon.third.test")
    assert beacon["bytes"] == 0, beacon


# --- the strip, the bands and the two honesty clauses -----------------------

def test_the_gauge_bands_are_googles_and_come_from_one_place(tmp_path):
    """"Thresholds are Google's … stored in the registry, never ours." The
    three Core Web Vitals are DERIVED from `CWV_BANDS` rather than retyped, so
    a threshold cannot be Google's in the check and ours on the gauge — the
    divergence the BC checkpoint already found once, when the gauge drew fixed
    40/66% stops against a value coloured by the real thresholds."""
    from clauditseo.modules import prf

    assert prf.GAUGE_BANDS["lcp"]["good"] == prf.CWV_BANDS["lcp_ms"][0]
    assert prf.GAUGE_BANDS["lcp"]["poor"] == prf.CWV_BANDS["lcp_ms"][1]
    assert prf.GAUGE_BANDS["cls"]["good"] == prf.CWV_BANDS["cls"][0]
    assert prf.GAUGE_BANDS["inp"]["poor"] == prf.CWV_BANDS["inp_ms"][1]
    # The brief's published figures, so a silent edit to either table fails.
    assert (prf.GAUGE_BANDS["lcp"]["good"], prf.GAUGE_BANDS["lcp"]["poor"]) == (2500, 4000)
    assert (prf.GAUGE_BANDS["cls"]["good"], prf.GAUGE_BANDS["cls"]["poor"]) == (0.1, 0.25)
    assert (prf.GAUGE_BANDS["inp"]["good"], prf.GAUGE_BANDS["inp"]["poor"]) == (200, 500)
    assert (prf.GAUGE_BANDS["ttfb"]["good"], prf.GAUGE_BANDS["ttfb"]["poor"]) == (800, 1800)
    # TTFB is NOT in CWV_BANDS on purpose: it is not a Core Web Vital and CrUX
    # does not serve it, so putting it there would make the field-data loop ask
    # a provider for a metric it does not have.
    assert "ttfb_ms" not in prf.CWV_BANDS
    # One function decides the band, so the marker's colour and the band it is
    # drawn on cannot disagree.
    assert prf.gauge_band("lcp", 2499) == "good"
    assert prf.gauge_band("lcp", 2501) == "needs improvement"
    assert prf.gauge_band("lcp", 4001) == "poor"

    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace(lcp_ms=4500.0))])
    served = now["bands"]
    assert served["lcp"]["good"] == 2500 and served["lcp"]["poor"] == 4000
    lcp = next(g for g in now["templates"][0]["vitals"] if g["key"] == "lcp")
    assert lcp["band"] == "poor" and lcp["value"] == 4500.0


def test_inp_is_a_labelled_proxy_and_never_synthesised(tmp_path):
    """There is no interaction trace in this step, so INP is not lab-measurable
    at all. It is shown as its TBT proxy and LABELLED — the read-and-report step
    says "do not synthesise an INP figure" in as many words, and a figure on a
    gauge headed INP with nothing saying it is TBT would be exactly that."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace(tbt=420.0))])
    inp = next(g for g in now["templates"][0]["vitals"] if g["key"] == "inp")
    assert inp["proxy"] == "TBT", inp
    assert inp["value"] == 420.0 and inp["basis"] == "lab", inp
    # Every vital is lab until a field source is connected — the brief's accept.
    assert {g["basis"] for g in now["templates"][0]["vitals"]} == {"lab"}
    # And no other gauge claims a proxy it does not have.
    assert [g["key"] for g in now["templates"][0]["vitals"] if g["proxy"]] == ["inp"]


def test_the_field_bar_is_greyed_with_what_to_connect_and_never_zeros(tmp_path):
    """Visual 2. `good 0 · NI 0 · poor 0` is a claim about the site rather than
    about our data, and it is the claim a client reads first. So the shares are
    None and the note says what to connect — the one thing on this block the
    client themselves can act on."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace())])
    field = now["field_data"]
    assert field["connected"] is False
    assert field["good"] is None and field["poor"] is None
    assert field["needs_improvement"] is None
    assert "CrUX" in field["note"] and "Search Console" in field["note"]
    assert "lab" in field["note"]


def test_a_run_with_no_trace_says_so_rather_than_reading_empty(tmp_path):
    """"The trace was not taken" and "the trace found nothing" are different
    sentences. A run stored without the pass carries `traced: False` on every
    page record, and the block says the pass did not run rather than drawing
    four empty gauges."""
    conn = connect(tmp_path / "none.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site_id, ["PRF"], "T2")
    runs.store_evidence(conn, run_id, {
        "start_url": "https://x.test/", "sitemap_entries": [], "sitemaps": [],
        "pages": [{"url": "https://x.test/", "status": 200,
                   "content_type": "text/html", "content": "<html></html>",
                   "outlinks": [], "perf": {"traced": False}}]})
    runs.mark_complete(conn, run_id, "2026-09-11T00:00:00")
    now = runs.speed_now_payload(conn, run_id)
    assert now is not None and now["recorded"] is False, now
    assert now["templates"] == []
    # The device profile is stated even with nothing traced: it is what the
    # pass WOULD run under, and the brief asks for it on every run.
    assert "mid-tier mobile" in now["device_profile"]
    # And no run at all is None, which is a third thing again.
    assert runs.speed_now_payload(conn, None) is None


def test_the_filmstrip_carries_the_frames_the_pass_wrote(tmp_path):
    """Visual 4. The frames are files, so the payload carries their names and
    the run that addresses them — one `run_id` on the block rather than an
    absolute URL on each of forty frames."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace(lcp_ms=2500.0))])
    frames = now["templates"][0]["frames"]
    assert isinstance(frames, list) and len(frames) == 3, frames
    assert [f["label"] for f in frames] == ["loading", "FCP", "LCP"]
    # In time order, which is the whole point of a filmstrip.
    assert [f["t_ms"] for f in frames] == sorted(f["t_ms"] for f in frames)
    for f in frames:
        assert f["name"].endswith(".jpg")


def test_the_frame_route_refuses_a_name_it_did_not_write(tmp_path):
    """The second route in the API that serves a file from `data/`, so it
    follows the first one's rules: a name that reaches `Path` unchecked is a
    path traversal, and this is one of only two places that is reachable."""
    import re

    from clauditseo.api import app as app_mod

    src = (app_mod.__file__)
    text = open(src, encoding="utf-8").read()
    pattern = re.search(r'r"(\[0-9a-f\]\{32\}-frame[^"]+)"', text)
    assert pattern, "the frame route no longer validates its name"
    rx = re.compile(pattern.group(1))
    assert rx.fullmatch("a" * 32 + "-frame0.jpg")
    assert rx.fullmatch("a" * 32 + "-frame12.jpg")
    for bad in ("../../secret.jpg", "a" * 32 + "-frame0.png",
                "a" * 31 + "-frame0.jpg", "..%2fx-frame0.jpg",
                "a" * 32 + "-frame0.jpg/../../x", "zz" + "a" * 30 + "-frameA.jpg"):
        assert not rx.fullmatch(bad), bad


def test_the_payload_is_on_the_speed_part_and_no_other(tmp_path):
    """One part carries it: a filmstrip of one page painting is not a shape the
    Headings or Images parts have anything to draw. Asserted at the wiring,
    which is where the three blocks before this one were each attached."""
    from clauditseo.api import app as app_mod

    text = open(app_mod.__file__, encoding="utf-8").read()
    assert 'if cat["key"] == "speed" and speed_now:' in text
    assert text.count('cat["speed_now"] = speed_now') == 1


def test_every_template_count_states_its_population(tmp_path):
    """Item 155, on the largest new count surface the product has gained in one
    pass — the 139a risk item 154 names by hand, and the reason the population
    rule landed before these visuals did."""
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/blog/a", _trace()),
                              (f"{FIRST_PARTY}/blog/b", _trace()),
                              (f"{FIRST_PARTY}/", _trace())])
    counts = [now["traced"]]
    for t in now["templates"]:
        counts.append(t["pages"])
        counts.extend(g["over"] for g in t["vitals"])
    assert len(counts) > 6, counts
    for c in counts:
        assert set(c) == {"value", "population", "basis", "of"}, c
        assert c["population"] in runs.POPULATIONS, c
        # Every one of them is over the crawl: a template's pages are the ones
        # this run fetched and traced. The record is never a denominator here.
        assert c["population"] == "crawl", c
        assert c["of"] is not None and c["value"] <= c["of"], c


# --- and the six actually on screen ----------------------------------------

def test_all_six_visuals_render_for_a_traced_template(tmp_path, served, browser):  # noqa: F811
    """The brief's accept names them one by one: "the four gauges, the greyed
    field bar, the sub-part bar summing to the LCP, the filmstrip, the
    waterfall and the third-party bars all render for the blog template".

    Served through route interception, for the reason item 155's clauses record
    on this same payload: the render fixture has no performance trace at all —
    the pass is a third throttled browser launch and no fixture run takes one —
    so a clause driving the fixture's own payload would assert six absences.
    What is injected is the payload `speed_now_payload` produced above, not a
    hand-built screen, so the render rule is what is under test.
    """
    base, ids = served
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/blog/a", _trace(lcp_ms=3100.0)),
                              (f"{FIRST_PARTY}/blog/b", _trace(lcp_ms=2900.0)),
                              (f"{FIRST_PARTY}/", _trace(lcp_ms=4800.0))])
    assert now["templates"], "nothing to render"

    pg = browser.new_page(viewport={"width": 1400, "height": 1200})

    def anatomy(route):
        data = route.fetch().json()
        for cat in data["categories"]:
            if cat["key"] == "speed":
                cat["speed_now"] = {**now, "run_id": data.get("latest_run")}
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(data))

    pg.route("**/api/sites/*/anatomy*", anatomy)
    pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=20_000)
    open_part(pg, "Speed")
    pg.wait_for_selector(".sp-card", timeout=15_000)
    pg.wait_for_timeout(400)

    got = pg.evaluate("""() => ({
      gauges: [...document.querySelectorAll('.sp-gauge')]
        .map((e) => e.getAttribute('data-vital')),
      bands: [...document.querySelectorAll('.sp-gauge')]
        .map((e) => e.getAttribute('data-band')),
      fieldOff: !!document.querySelector('.sp-field-off'),
      fieldNote: (document.querySelector('.sp-f-note')?.textContent || '').trim(),
      sub: [...document.querySelectorAll('.sp-sub-bar .sp-s')].length,
      dominant: [...document.querySelectorAll('.sp-s-dominant')].length,
      subWhy: (document.querySelector('.sp-sub-why')?.textContent || '')
        .replace(/\\s+/g, ' ').trim(),
      frames: document.querySelectorAll('.sp-frame').length,
      wf: document.querySelectorAll('.sp-wf tbody tr').length,
      costs: [...new Set([...document.querySelectorAll('.sp-cost')]
        .map((e) => e.textContent.trim()))],
      tp: document.querySelectorAll('.sp-tp tbody tr').length,
      tpBars: document.querySelectorAll('.sp-tp-bar').length,
      picks: [...document.querySelectorAll('.sp-pick code')]
        .map((e) => e.textContent.trim()),
      profile: (document.querySelector('.sp-profile')?.textContent || '').trim(),
      counts: [...document.querySelectorAll('.sp-card [data-population]')]
        .map((e) => e.getAttribute('data-population')),
    })""")

    # (1) four gauges, each on its own band and each saying which band.
    assert got["gauges"] == ["lcp", "cls", "inp", "ttfb"], got["gauges"]
    assert all(b in ("good", "needs improvement", "poor") for b in got["bands"]), got
    # (2) the field bar, greyed, with what to connect.
    assert got["fieldOff"] and "CrUX" in got["fieldNote"], got
    # (3) the sub-part bar: four parts, the dominant one marked, and the
    # sentence that says it sums to the paint it explains.
    assert got["sub"] == 4 and got["dominant"] == 1, got
    assert "they sum" in got["subWhy"], got["subWhy"]
    # (4) the filmstrip.
    assert got["frames"] == 3, got
    # (5) the waterfall, with more than one cost type drawn.
    assert got["wf"] >= 3, got
    assert len(got["costs"]) >= 2, got["costs"]
    # (6) the ledger, with a bar per host.
    assert got["tp"] >= 2 and got["tpBars"] == got["tp"], got
    # The strip is per template, largest first, and the profile is stated.
    assert got["picks"][0] == "/blog/<slug>", got["picks"]
    assert "applied throttling" in got["profile"], got["profile"]
    # Item 155 on this block too: every count it draws carries a population,
    # and all of them are over the crawl.
    assert got["counts"] and set(got["counts"]) == {"crawl"}, got["counts"]


def test_the_ledger_has_one_implementation(tmp_path):
    """The `third-party-weight` check and this block's ledger read the same
    function. This rule written out twice is how six places came to count
    `len(pages)` instead — `crawler.types` records that case by name."""
    from clauditseo.modules import prf

    tr = _trace()
    direct = prf.third_party_ledger(tr, "x.test")
    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", tr)])
    drawn = now["templates"][0]["third_parties"]
    assert [r["host"] for r in drawn] == [r["host"] for r in direct], (
        drawn, direct)
    assert (open(prf.__file__, encoding="utf-8").read()
            .count("def third_party_ledger") == 1)
    # And the payload calls it rather than re-deriving the two axes.
    runs_src = open(runs.__file__, encoding="utf-8").read()
    assert "prf.third_party_ledger(" in runs_src


def test_the_device_profile_states_the_throttling_method(tmp_path):
    """Stated on every run, per the brief — and it states the METHOD, because
    we APPLY the throttle where Lighthouse and PageSpeed simulate it. Ours
    reads lower by design (measured on Birch: LCP 2.6 s against PSI's 6.0 s),
    and a client comparing the two is owed that sentence rather than left to
    read it as a disagreement."""
    from clauditseo import perf

    now = _payload(tmp_path, [(f"{FIRST_PARTY}/a", _trace())])
    assert "applied throttling" in now["device_profile"], now["device_profile"]
    # The stated profile is the trace's OWN, not a constant this payload
    # repeats: a run traced under an older profile must report the profile it
    # was traced under, or the figures are read against conditions they were
    # not measured in.
    assert now["device_profile"] == _trace()["device_profile"]
    # And with nothing traced it falls back to what the pass WOULD use, which
    # is the module's constant.
    assert "applied throttling" in perf.DEVICE_PROFILE
