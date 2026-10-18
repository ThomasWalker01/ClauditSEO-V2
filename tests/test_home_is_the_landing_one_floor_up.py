"""Item 176, "Home adopts the landing language" (concept H1).

Home is the client landing's structure one floor up: eyebrow, headline, one row
of real actions, then the sites as cards, then nothing else. The pieces were
settled on the client landing by items 168 and 171 to 175, and this file holds
that they travel: the headline's 2rem at 68ch without balancing (175), the
action row, the cards' container rhythm, nothing between the actions and the
content.

It also holds the four things the old Home did that stop:

- **No destructive control is one click from a resting state.** `delete site`
  sat on every row beside the name; it is behind the card's closed "Edit this
  site", and still asks.
- **Type and brand are facts, not live fields** on the card's face.
- **The score key and "seen once" are the shared legend's** (item 166), not
  body prose - `test_a_score_band_meaning_is_reachable_without_a_mouse` opens it
  from the keyboard.
- **The scheduler caution is the headline's last clause**, not a yellow box.

And a site no audit has completed on says so in words, where its score was an
em-dash in a column.

**Why a browser.** Every claim is about what paints where and what one click
reaches; the source cannot say either. A second site with no audit is added to
this module's own fixture, so "not audited" is read off a real row.
"""

from __future__ import annotations

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (module fixture)

pytestmark = [
    pytest.mark.skipif(
        __import__("importlib.util", fromlist=["util"]).find_spec("playwright") is None,
        reason="playwright is not installed"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]


@pytest.fixture(scope="module")
def workspace(served):
    """The fixture's audited site, plus a site no audit has run on."""
    import httpx
    base, ids = served
    client = httpx.post(f"{base}/api/clients", json={"name": "Never Audited"}, timeout=30).json()
    site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": "never-audited.test"}, timeout=30).json()
    return base, ids, site["id"]


def _home(workspace, fn, width=1440):
    from playwright.sync_api import sync_playwright
    base, _ids, _never = workspace
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": width, "height": 1000}, color_scheme="dark")
        try:
            pg.goto(f"{base}/#/", wait_until="load", timeout=30_000)
            pg.wait_for_selector(".home-card", timeout=30_000)
            pg.wait_for_timeout(300)
            return fn(pg)
        finally:
            browser.close()


def test_the_head_is_the_landings_head(workspace):
    got = _home(workspace, lambda pg: pg.evaluate("""() => {
      const s = document.querySelector('.home-head .bl-sentence');
      const cs = getComputedStyle(s);
      const probe = document.createElement('span'); probe.textContent = '0';
      probe.style.font = cs.font; probe.style.letterSpacing = cs.letterSpacing;
      probe.style.position = 'absolute'; probe.style.visibility = 'hidden';
      document.body.appendChild(probe); const ch = probe.getBoundingClientRect().width; probe.remove();
      const acts = [...document.querySelectorAll('.home-head .bl-buttons > *')].map((a) => ({
        text: a.textContent.trim(), href: a.getAttribute('href'), primary: a.classList.contains('tone-action-primary') }));
      return { eyebrow: (document.querySelector('.home-head .eyebrow')?.textContent || '').trim(),
               text: s.textContent.replace(/\\s+/g, ' ').trim(), fontSize: parseFloat(cs.fontSize),
               measure: parseFloat(cs.maxWidth) / ch, balance: (cs.textWrapStyle || cs.textWrap || '').includes('balance'),
               acts, cautionBox: document.querySelectorAll('.home-setup:not(.error)').length,
               tables: document.querySelectorAll('#content table').length };
    }"""))
    assert got["eyebrow"] == "Where the workspace stands", got
    assert got["fontSize"] >= 30 and 64 <= got["measure"] <= 72 and not got["balance"], got
    assert "open finding" in got["text"] and "Nothing is scheduled, so nothing runs unless you start it." in got["text"], got
    assert [a["text"] for a in got["acts"]][:1] == ["Set a cadence"], got
    cadence = got["acts"][0]
    assert cadence["href"] == "#/admin?tab=cadence" and cadence["primary"], (
        f"Set a cadence is not the primary action onto Admin's grid while nothing is scheduled: {got}")
    assert any(a["text"] == "Add a client or site" for a in got["acts"]), got
    assert got["cautionBox"] == 0 and got["tables"] == 0, f"the caution box or the table is back: {got}"


def test_nothing_between_the_actions_and_the_cards_and_the_cards_are_the_landings(workspace):
    got = _home(workspace, lambda pg: pg.evaluate("""() => {
      const actions = document.querySelector('.home-head .bl-actions').getBoundingClientRect();
      const cards = document.querySelector('.home-cards').getBoundingClientRect();
      const row = document.querySelector('.home-row');
      const between = [...document.querySelector('#content').querySelectorAll('*')].filter((e) => {
        const b = e.getBoundingClientRect();
        return b.height > 0 && b.top >= actions.bottom - 1 && b.bottom <= cards.top + 1
          && !row.contains(e) && !e.contains(row) && !e.closest('.sr-only'); })
        .map((e) => e.className || e.tagName);
      const card = getComputedStyle(document.querySelector('.home-card'));
      const all = [...document.querySelectorAll('.home-card')].map((c) => c.getBoundingClientRect());
      return { between, gap: Math.round(all[1].left - all[0].right),
               pad: card.paddingTop, radius: card.borderTopLeftRadius,
               lighter: card.backgroundColor !== getComputedStyle(document.body).backgroundColor };
    }"""))
    assert got["between"] == [], f"something stands between the actions and the cards: {got}"
    assert got["gap"] == 16 and got["pad"] == "16px" and got["radius"] == "10px" and got["lighter"], got


def test_no_destructive_control_is_one_click_from_rest_and_facts_are_not_fields(workspace):
    def read(pg):
        rest = pg.evaluate("""() => ({
          deletes: [...document.querySelectorAll('button[aria-label^="delete the site"]')]
            .filter((b) => b.checkVisibility()).length,
          fields: [...document.querySelectorAll('.home-card select, .home-card input')]
            .filter((b) => b.checkVisibility()).length,
          cards: document.querySelectorAll('.home-card').length,
          tags: [...document.querySelectorAll('.home-card .home-card-foot')].map((f) => f.textContent) })""")
        pg.click(".home-card .home-card-manage > summary")
        rest["afterOne"] = pg.evaluate("""() => [...document.querySelectorAll('button[aria-label^="delete the site"]')]
            .filter((b) => b.checkVisibility()).length""")
        return rest
    got = _home(workspace, read)
    assert got["cards"] >= 2, got
    assert got["deletes"] == 0, f"a delete is reachable from the resting screen: {got}"
    assert got["fields"] == 0, f"a type or brand field is live on a card's face: {got}"
    assert got["afterOne"] == 1, f"opening one card's editor did not reach exactly its delete: {got}"


def test_a_site_no_audit_has_completed_on_says_so_in_words(workspace):
    _base, _ids, never = workspace
    got = _home(workspace, lambda pg: pg.evaluate("""(id) => {
      const c = document.querySelector(`.home-card[data-site="${id}"]`);
      return c && { score: c.querySelector('.home-card-score').textContent.trim(),
                    line: c.querySelector('.home-card-line').textContent.replace(/\\s+/g, ' ').trim(),
                    last: [...document.querySelectorAll('.home-card')].pop() === c };
    }""", never))
    assert got, "the site with no audit has no card"
    assert got["score"] == "not audited" and "—" not in got["score"], got
    assert "No audit has completed, so there is no score." in got["line"], got
    assert got["last"], f"newest audit first puts a site with no audit last: {got}"
