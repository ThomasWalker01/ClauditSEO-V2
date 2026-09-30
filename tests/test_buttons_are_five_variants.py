"""Item 182: five button variants, registered, with a reference page, and the
old families held so they can only shrink (UI audit pattern H, 11-7).

- The five exist as components with one shared box and a 24 px floor.
- Each variant's tone is registered in the glossary (item 166).
- `#/buttons` draws every variant, held and live, and is linked from the design
  doc. At the four viewports the auditors used, every variant is at least 24 px
  in its smaller dimension and none overflows the page.
- The deprecated families (tests/button_families.py) may lose uses and never
  gain one. Item 183 migrates them and lowers `BASELINE`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.button_families import FAMILIES, count_all
from tests.needs_build import needs_build

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"

#: Uses per deprecated family. Item 183 migrated every screen, so each is zero
#: but one: the paid pills that ARE a confirmation or open one - Tools' three
#: choices inside its confirm dialog and Run all, which opens it, and a part's
#: "Run the N not run", which opens the batch confirmation. A SpendButton there
#: would ask twice. Never raise a figure here.
BASELINE = {
    "pill-button-free": 0, "pill-button-nav": 0, "pill-link-nav": 0, "pill-primary": 0,
    "pill-paid-raw": 5, "pill-danger-raw": 0, "linklike": 0, "bare-button": 0,
    "bl-secondary": 0, "anat-rerun": 0, "catalogue-fab": 0, "ctx-jump": 0,
}
#: One file since item 188 retired Tools, which held four of the five.
CONFIRMATION_INTERNAL = {"anatomy.tsx": 1}


def test_the_five_variants_exist_as_components():
    src = (SRC / "buttons.tsx").read_text(encoding="utf-8")
    for name in ("PrimaryButton", "SecondaryButton", "LinkButton"):
        assert f"export const {name} =" in src, name
    assert 'export { DangerButton, SpendButton } from "./spend"' in src
    spend = (SRC / "spend.tsx").read_text(encoding="utf-8")
    assert "btn btn-spend" in spend and "btn btn-danger" in spend, "spend and danger share the box"


def test_each_variant_has_a_registered_tone():
    entries = {e["id"]: e for e in json.loads(
        (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))["entries"]}
    tones = {e["class"].removeprefix("tone-") for e in entries.values() if e.get("class")}
    variants = [e for e in entries.values() if e.get("vocabulary") == "button variants"]
    assert {e["engine"] for e in variants} == {
        "PrimaryButton", "SecondaryButton", "SpendButton", "DangerButton", "LinkButton"}
    for e in variants:
        assert e["tone"] in tones, (e["id"], e["tone"])
    src = (SRC / "buttons.tsx").read_text(encoding="utf-8")
    for e in variants:
        assert f'registry: "{e["id"]}"' in src and f'tone: "{e["tone"]}"' in src, e["id"]


def test_no_deprecated_family_gains_a_use():
    now = {f: sum(by.values()) for f, by in count_all().items()}
    assert set(now) == set(BASELINE) == set(FAMILIES)
    grew = {f: (BASELINE[f], n, count_all()[f]) for f, n in now.items() if n > BASELINE[f]}
    assert not grew, (
        "a new use of a deprecated button family - draw it with one of the five variants "
        f"in buttons.tsx instead: {grew}")


def test_every_button_is_one_of_the_five():
    """Item 183, commit 6: no deprecated family is used anywhere but the named
    confirmation internals."""
    now = count_all()
    left = {f: by for f, by in now.items() if by and f != "pill-paid-raw"}
    assert not left, f"deprecated button families still drawn: {left}"
    assert now["pill-paid-raw"] == CONFIRMATION_INTERNAL, now["pill-paid-raw"]


def test_the_design_doc_links_the_reference_page():
    doc = (ROOT / "docs" / "design-language.md").read_text(encoding="utf-8")
    assert "#/buttons" in doc
    for name in ("PrimaryButton", "SecondaryButton", "SpendButton", "DangerButton", "LinkButton"):
        assert name in doc, name


pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)

VIEWPORTS = (("1440 dark", 1440, "dark"), ("1440 light", 1440, "light"),
             ("1100", 1100, "dark"), ("390", 390, "dark"))


@needs_build
def test_every_variant_renders_at_every_viewport(served):
    from playwright.sync_api import sync_playwright

    base, _ = served
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for label, width, scheme in VIEWPORTS:
                ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
                pg = ctx.new_page()
                pg.goto(f"{base}/#/buttons", wait_until="networkidle")
                pg.wait_for_selector(".btn-ref [data-variant]", timeout=30_000)
                got = pg.evaluate("""() => ({
                  overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
                  rows: [...document.querySelectorAll('.btn-ref [data-variant]')].map((row) => {
                    const b = row.querySelector('.btn');
                    const r = b.getBoundingClientRect();
                    return { variant: row.dataset.variant, held: row.dataset.held === 'true',
                             w: r.width, h: r.height, tone: [...b.classList].find((c) => c.startsWith('tone-')),
                             disabled: b.getAttribute('aria-disabled') };
                  }),
                })""")
                seen = {r["variant"] for r in got["rows"]}
                if seen != {"primary", "secondary", "spend", "danger", "link"}:
                    problems.append(f"{label}: variants drawn {sorted(seen)}")
                for r in got["rows"]:
                    if min(r["w"], r["h"]) < 24:
                        problems.append(f"{label}: {r} under the 24px floor")
                    if r["held"] and r["disabled"] != "true":
                        problems.append(f"{label}: {r} held but not aria-disabled")
                if got["overflow"]:
                    problems.append(f"{label}: the reference page scrolls sideways")
                ctx.close()
        finally:
            browser.close()
    assert not problems, "\n".join(problems)
