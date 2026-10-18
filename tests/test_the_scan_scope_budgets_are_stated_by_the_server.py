"""The scan grid's page budgets come from the server, and mean what they say.

CQ-245 and UX-100, both from report 139, and both the same duplicated
constant. `clauditseo/scanscope.py` sets the `site` scope's cap from the
crawler's own table; `dashboard/src/scanmatrix.tsx` typed `Math.min(100, full)`
beside it. They agreed at HEAD and nothing anywhere asserted that they did, so
changing one tier budget in Python would have made a purchase screen state a
page count the crawl would not visit — in one language, with no test in either
going red. UX-100 is the same fact on screen: the `Site` row's figure sat under
a caption attributing every count on the screen to the precheck, and the
precheck declined to produce that one on purpose.

**Q-45 chose where the constant lives**: the server states the scope table on
`/api/meta`, keyed as `scanscope.SCOPES` already is, and the grid reads it. The
precheck's response shape and its stored rows are untouched — the cap is a tier
budget, not a measurement, so asking the precheck to carry it would have filed
a product constant as a thing measured about a site.

**What this file can and cannot guard.** It guards the half the constant now
lives in. The client half is guarded by construction rather than by assertion:
there is no literal left to drift, and Q-45 rejected a test that reads a
TypeScript literal for the reason this repository has twice rejected that shape
— a matcher weaker than the population is not the assertion. The dashboard has
no JavaScript test runner, so the rendered caption is not asserted here either;
that is stated rather than left to be discovered.

**The binding with teeth is the last test.** Asserting the API's number equals
`scanscope.SCOPES`' number would be near-tautological — one reads the other.
The claim worth holding is CQ-245's own harm statement: the number a screen is
told is the number the crawler will actually enforce. `crawl_kwargs` is what
the audit route calls, so that is what is asked.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.crawler.types import Tier
from clauditseo.scanscope import SCOPES, crawl_kwargs

START = "https://x.test/"


def _meta(tmp_path) -> dict:
    client = TestClient(create_app(db_path=tmp_path / "scopes.db"))
    r = client.get("/api/meta")
    assert r.status_code == 200, r.text
    return r.json()


def test_api_meta_states_every_scan_scope(tmp_path):
    """The population is `scanscope.SCOPES` itself, not a list written here.

    A scope the API omits is a row of the grid with no budget to read, and
    the grid withholds the figure rather than guessing — so an omission is a
    blank cell on the screen that decides what gets bought, not a crash
    anyone would notice.
    """
    body = _meta(tmp_path)
    assert SCOPES, "clauditseo.scanscope declares no scopes at all"
    assert "scopes" in body, sorted(body.keys())

    missing = [k for k in SCOPES if k not in body["scopes"]]
    assert not missing, (
        f"/api/meta omits {', '.join(missing)} from its scope table; the scan "
        "grid reads this and has no other source for a page budget")

    extra = [k for k in body["scopes"] if k not in SCOPES]
    assert not extra, (
        f"/api/meta names {', '.join(extra)}, which scanscope.SCOPES does not")


def test_each_scope_carries_the_page_budget_it_was_defined_with(tmp_path):
    """Every scope carries `max_pages`, including the ones where it is null.

    `null` is a value here, not an absence: it means "the tier's own budget",
    which is the one thing this table cannot resolve, and the grid has to be
    able to tell it apart from a scope the server forgot.
    """
    stated = _meta(tmp_path)["scopes"]
    wrong = []
    for key, scope in SCOPES.items():
        entry = stated[key]
        if "max_pages" not in entry:
            wrong.append(f"{key} carries no max_pages at all ({entry})")
        elif entry["max_pages"] != scope.max_pages:
            wrong.append(f"{key}: API says {entry['max_pages']}, "
                         f"scanscope says {scope.max_pages}")
    assert not wrong, "; ".join(wrong)


def test_the_site_scope_has_a_cap_the_screen_can_state(tmp_path):
    """The one figure the client used to type, asserted as resolvable.

    `site` is "a representative sample, capped", and a sample with no cap is
    a Full scan under another name. If this ever became null the grid would
    have nothing to state for the row and would show no figure — which is
    honest, but it is not the row working.
    """
    site = _meta(tmp_path)["scopes"]["site"]
    assert isinstance(site["max_pages"], int) and site["max_pages"] > 0, site


def test_the_budget_the_screen_is_told_is_the_one_the_crawl_enforces(tmp_path):
    """CQ-245's harm statement, as an assertion.

    `crawl_kwargs` is what `POST /api/sites/{id}/audits` calls to turn a scope
    into crawl arguments, so its `budget` is the number of pages that will
    actually be visited. A scope whose stated cap and enforced cap disagree is
    a screen quoting a page count the crawl will not honour, which is the
    finding rather than a tidier way of writing it.
    """
    stated = _meta(tmp_path)["scopes"]
    checked = 0
    wrong = []
    for key, scope in SCOPES.items():
        kwargs = crawl_kwargs(key, Tier.T2, START)
        budget = kwargs.get("budget")
        if scope.max_pages is None:
            # No budget of its own — the crawl keeps the tier's, which is
            # exactly what the null on the wire tells the screen.
            if budget is not None:
                wrong.append(f"{key} states no cap but the crawl sets "
                             f"{budget.max_pages}")
            continue
        checked += 1
        if budget is None:
            wrong.append(f"{key} is stated as capped at "
                         f"{stated[key]['max_pages']} but the crawl is given "
                         "no budget, so the tier's applies instead")
        elif budget.max_pages != stated[key]["max_pages"]:
            wrong.append(f"{key}: the screen is told "
                         f"{stated[key]['max_pages']} and the crawl will "
                         f"visit {budget.max_pages}")
    assert not wrong, "; ".join(wrong)
    assert checked > 1, (
        "no scope resolved to an enforced budget, so this test asserted "
        "nothing about any of them")
