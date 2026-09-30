"""Open a part the way the screen does since the sidebar's retirement (brief
v24 step BO): through the address. `?part=<key>` is the part in hand, so a
test names the part by its label, as the operator reads it, and this looks the
key up in the anatomy payload the page itself reads.

Label matching mirrors Playwright's `:has-text`, which the sidebar clicks used:
an exact label first, then the first label containing the text.
"""

from __future__ import annotations

_OPEN = """async ([label, wantOpen]) => {
  const m = location.hash.match(/#\\/sites\\/([^?/]+)/);
  if (!m) throw new Error('not on a site screen: ' + location.hash);
  const r = await fetch(`/api/sites/${m[1]}/anatomy`);
  const cats = (await r.json()).categories.filter((c) => c.group !== 'workflow');
  const c = wantOpen
    ? cats.find((x) => (x.total?.value ?? x.total ?? 0) > 0)
    : (cats.find((x) => x.label === label) || cats.find((x) => x.label.includes(label)));
  if (!c) throw new Error('no part ' + (wantOpen ? 'with something open' : label));
  const [path, query = ''] = location.hash.split('?');
  const q = new URLSearchParams(query);
  if (!q.get('tab')) q.set('tab', 'findings');
  q.set('part', c.key);
  location.hash = path + '?' + q.toString();
  return c.key;
}"""


def open_part(pg, label: str, timeout: int = 15_000) -> str:
    """Open the part labelled `label` and wait until its page is the pane."""
    key = pg.evaluate(_OPEN, [label, False])
    _wait(pg, key, timeout)
    return key


def open_first_open_part(pg, timeout: int = 15_000) -> str:
    """The first part, in the product's order, with something open: what
    `.anat-leaf:not(:has(.n-zero))` picked on the sidebar."""
    key = pg.evaluate(_OPEN, ["", True])
    _wait(pg, key, timeout)
    return key


def _wait(pg, key: str, timeout: int) -> None:
    pg.wait_for_function(
        """(key) => new URLSearchParams(location.hash.split('?')[1] || '').get('part') === key
                && document.querySelector('.anat-pane h2.part-h2')""",
        arg=key, timeout=timeout)


#: What a test waits on for "the site's anatomy has loaded", on any pane,
#: which the sidebar's rows used to stand for.
ANATOMY_READY = '.site-main[data-anatomy="loaded"]'


def open_page_filter(pg, timeout: int = 30_000) -> None:
    """Show the page filter, the way an operator does: press "One page".

    Item 174 (channel ruling 20260917-1430): the filter is page mode's control,
    so site mode does not draw it. A page already in scope shows it, and then
    this presses nothing. Every test that types a path calls this first - they
    are testing a page-mode control."""
    pg.wait_for_selector(".mode-switch .mode-seg", timeout=timeout)
    if not pg.locator(".page-find").count():
        pg.locator(".mode-switch .mode-seg", has_text="One page").click()
    pg.wait_for_selector(".page-find", state="visible", timeout=timeout)
