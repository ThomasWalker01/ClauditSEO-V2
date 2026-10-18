"""Headless rendering: the post-hydration DOM for pages built by JavaScript.

Optional in the same way google-auth is: Playwright is imported lazily,
`available()` is the gate, and everything downstream keeps working — and
keeps saying "provisional, no renderer configured" — when it is absent.
Install with:

    pip install clauditseo[render]
    playwright install chromium      # separate post-install step, always

The one design rule: rendered output is always labelled as rendered. The raw
server response and the hydrated DOM answer different questions, and a brief
that cannot tell which it is holding will confidently compare a page against
itself.
"""

from __future__ import annotations

from clauditseo import BOT_NAME

RENDER_TIMEOUT_MS = 25_000
SETTLE_MS = 1_500        # after load: hydration frameworks paint late


class Renderer:
    name = "renderer"

    def available(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            return False
        return True

    def render(self, url: str) -> dict:
        """Fetch and render one page. Returns {html, console_errors, status}
        or raises — the caller decides whether a render failure downgrades to
        the raw path or aborts, because that depends on what the brief is for.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent=f"{BOT_NAME}/1.0 (+headless render for audit)")
                errors: list[str] = []
                page.on("console", lambda m: errors.append(m.text)
                        if m.type == "error" else None)
                response = page.goto(url, timeout=RENDER_TIMEOUT_MS,
                                     wait_until="load")
                page.wait_for_timeout(SETTLE_MS)
                return {
                    "html": page.content(),
                    "status": response.status if response else None,
                    "console_errors": errors[:20],
                }
            finally:
                browser.close()
