"""Contrast and markup regressions in the dashboard's own stylesheet.

Every contrast bug in this UI has been arithmetic done by hand, and one of
them — a border at 2.99:1 against a 3.0 requirement — was reported as fixed
before being recomputed. That is what a test is for.

What this can and cannot do: CSS does not say what is composited over what,
so PAIRS below is a hand-maintained table of decisions, not a crawl of the
rendered page. Adding a colour combination to the app means adding a row
here. In exchange the check is free, needs no browser, and runs on every
push. Anything positional — focus order, landmarks, live regions — is out of
its reach; that is what the axe pass over rendered pages covers.

Two failures have already escaped this file, and both are worth remembering
because neither is fixable by adding more rows:

  * source order. `.tool-mark` set `color: #fff` after the severity block at
    equal specificity, so a chip declaring dark ink painted white. Every
    declared pair passed; the cascade painted something else.
  * opacity. `.seg-count` carried `opacity: 0.75`, which blended a passing
    colour toward its ground and painted 3.29:1. Nothing in the stylesheet
    says #808691 anywhere.

Both were caught by axe rendering the page. Static analysis checks what the
author declared; only a browser knows what was painted. Neither check
replaces the other.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "styles.css"
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

# WCAG 2.2 thresholds.
AA_TEXT = 4.5        # 1.4.3, text below 18.66px / 24px bold
AA_LARGE = 3.0       # 1.4.3, large text
AA_NON_TEXT = 3.0    # 1.4.11, control boundaries and meaningful graphics


# ---- colour maths ----------------------------------------------------------

def _channel(v: float) -> float:
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ---- reading the real stylesheet -------------------------------------------

TOKEN_RE = re.compile(
    r"--([a-z0-9-]+):\s*light-dark\(\s*(#[0-9a-fA-F]{3,6})\s*,\s*(#[0-9a-fA-F]{3,6})\s*\)")


def tokens() -> dict[str, tuple[str, str]]:
    """{name: (light, dark)} straight from :root, so the test cannot drift
    from the values the app actually ships."""
    found = dict((m.group(1), (m.group(2), m.group(3)))
                 for m in TOKEN_RE.finditer(CSS.read_text(encoding="utf-8")))
    assert found, "no light-dark() tokens found — did the palette move?"
    return found


def resolve(value: str, theme: int) -> str:
    """A token name or a literal. theme: 0 light, 1 dark."""
    if value.startswith("#"):
        return value
    table = tokens()
    assert value in table, f"unknown token --{value}"
    return table[value][theme]


# (label, foreground, background, minimum). Literals allowed for colours that
# are deliberately theme-independent.
PAIRS: list[tuple[str, str, str, float]] = [
    # Body and prose.
    ("body text",              "text",         "bg",              AA_TEXT),
    ("muted text on card",     "text-muted",   "surface",         AA_TEXT),
    ("dim text on card",       "text-dim",     "surface",         AA_TEXT),
    # A token is only safe on the grounds it is actually painted on. --text-dim
    # passed on a card and failed on the page and on a sunken panel, which axe
    # found by rendering; the pair table only knew about the card.
    ("dim text on page",       "text-dim",     "bg",              AA_TEXT),
    ("dim text on sunken",     "text-dim",     "surface-sunken",  AA_TEXT),
    ("muted text on sunken",   "text-muted",   "surface-sunken",  AA_TEXT),
    ("muted text on page",     "text-muted",   "bg",              AA_TEXT),
    ("faint text on card",     "text-faint",   "surface",         AA_TEXT),
    ("link on page",           "accent",       "bg",              AA_TEXT),
    ("link on card",           "accent",       "surface",         AA_TEXT),

    # Controls — text.
    ("primary button label",   "#ffffff",      "accent-solid",    AA_TEXT),
    ("selected nav label",     "#ffffff",      "accent-solid",    AA_TEXT),
    ("segment label",          "text-muted",   "surface-sunken",  AA_TEXT),

    # Controls — boundaries. The failure that started this file.
    ("control edge on page",   "edge",         "bg",              AA_NON_TEXT),
    ("control edge on card",   "edge",         "surface",         AA_NON_TEXT),
    ("selected nav vs page",   "accent-solid", "bg",              AA_NON_TEXT),

    # Severity chips. Fixed hues in both themes: severity belongs to the
    # finding, not the viewer's theme.
    ("severity critical",      "#ffffff",      "#b3261e",         AA_TEXT),
    ("severity high",          "#17130c",      "#d9730d",         AA_TEXT),
    ("severity medium",        "#17130c",      "#e0a800",         AA_TEXT),
    ("severity low",           "#ffffff",      "#5a6270",         AA_TEXT),
    ("severity info",          "#ffffff",      "#4a515c",         AA_TEXT),

    # Sweep status chips, same reasoning as severity.
    ("mark running",           "#17130c",      "#d9730d",         AA_TEXT),
    ("mark queued",            "#ffffff",      "#4a515c",         AA_TEXT),
    ("mark failed",            "#ffffff",      "#b3261e",         AA_TEXT),
    ("mark needs input",       "#ffffff",      "#6a5518",         AA_TEXT),

    # Status colours used as text.
    ("good text on card",      "good",         "surface",         AA_TEXT),
    ("danger text on card",    "danger",       "surface",         AA_TEXT),
    ("accent text on accent",  "accent-text",  "accent-bg",       AA_TEXT),

    # Score and state badges: a status colour on its own tinted ground. This
    # trio was missing from the table, and axe found --good on --good-bg at
    # 4.47:1 by rendering the page — the gap between "pairs someone thought
    # to list" and "pairs the page actually paints" is exactly why both
    # checks exist.
    ("good on good bg",        "good",         "good-bg",         AA_TEXT),
    ("warn on warn bg",        "warn",         "warn-bg",         AA_TEXT),
    ("danger on danger bg",    "danger",       "danger-bg",       AA_TEXT),
    ("sev-low chip",           "accent-text",  "accent-bg",       AA_TEXT),
    ("sev-info chip",          "text-muted",   "surface-sunken",  AA_TEXT),
    # The model badge on run detail. Missing from this table until the
    # rendered sweep was widened to `#/runs/{id}` and axe painted it at
    # 4.01:1 — the gap between "pairs someone thought to list" and "pairs the
    # page actually paints", for the second time.
    ("model badge light",      "#ffffff",      "#6d4cbf",         AA_TEXT),
    ("model badge dark",       "#17130c",      "#cfc2f5",         AA_TEXT),

    # The heading a `heading-skip` finding points at (F-07). Its own ground,
    # so all three of the things painted on it need a row: the heading text,
    # the H-level chip beside it, and the words that say what the mark means.
    # `--text-dim`, which every other level chip uses, measures 4.30:1 here
    # in dark — which is why `.out-fault code` overrides it.
    ("outline fault text",     "text",         "warn-bg",         AA_TEXT),
    ("outline fault level",    "text-muted",   "warn-bg",         AA_TEXT),
    ("outline fault note",     "warn-strong",  "warn-bg",         AA_TEXT),

    # The busy control (UI-16). `disabled` is this product's only in-flight
    # indicator, so these are read while something is happening — the state
    # 1.4.3's inactive-control exception is not about. The edge carries two
    # rows because a disabled control sits on its own ground and on the card
    # behind it, and 1.4.11 asks about the boundary against both.
    ("busy control label",     "disabled-text", "disabled-bg",    AA_TEXT),
    ("busy control edge",      "disabled-edge", "disabled-bg",    AA_NON_TEXT),
    ("busy control on card",   "disabled-edge", "surface",        AA_NON_TEXT),

    # The Images budget blocks (brief v16c). A dot and a frame are graphics
    # that carry meaning, so 1.4.11 applies to them against the card they are
    # drawn on and against the tile ground they frame; `--warn-strong` reads
    # as text as well, on the "over budget" figure above the wall.
    ("over-budget dot",        "warn-strong",  "surface",         AA_NON_TEXT),
    ("over-budget figure",     "warn-strong",  "surface",         AA_TEXT),
    ("unscored dot",           "edge",         "surface",         AA_NON_TEXT),
    ("missing-alt frame",      "danger",       "surface-sunken",  AA_NON_TEXT),
    ("over-budget frame",      "warn-strong",  "surface-sunken",  AA_NON_TEXT),
    ("tile caption",           "text",         "surface",         AA_TEXT),

    # The Headings outline blocks (brief v16d). A rung, a gap and a
    # connector are graphics that carry meaning, so 1.4.11 applies to them
    # against the card they are drawn on; the gap's own label and the shape
    # code in the table read as text on the same ground. `--danger` and
    # `--warn-strong` as text are already above, on their own rows.
    ("outline rung",           "text",         "surface",         AA_NON_TEXT),
    ("skipped-level rung",     "warn-strong",  "surface",         AA_NON_TEXT),
    ("missing-H1 rung",        "danger",       "surface",         AA_NON_TEXT),
    ("outline connector",      "edge",         "surface",         AA_NON_TEXT),
    ("template bar",           "warn-strong",  "surface",         AA_NON_TEXT),

    # The Score trend chart (brief v16f). A dot, a join and a provenance
    # ring are graphics that carry meaning, so 1.4.11 applies to them
    # against the card they are drawn on; the score above a point and the
    # date under it are text on the same ground, at 13px and 11px, so they
    # are held to 1.4.3's ordinary ratio rather than the large-text one.
    # `--warn-strong` on `--surface` is already above in both roles, on the
    # over-budget rows, and the break rules and their labels are that pair.
    #
    # Two things this chart draws are deliberately NOT here, and saying why
    # is the point of the omission: the 80 and 60 threshold rules and the
    # current-basis band are drawn at reduced opacity, and neither carries a
    # fact of its own. The threshold's meaning is its own label beside it,
    # at full strength and on a row below; the band's is the legend and the
    # sentence under the chart. A rule this table cannot express is a rule
    # that must not be relied on to convey anything, and neither is.
    ("trend dot, good",        "good",         "surface",         AA_NON_TEXT),
    ("trend dot, poor",        "danger",       "surface",         AA_NON_TEXT),
    ("trend join",             "text",         "surface",         AA_NON_TEXT),
    ("trend recovered ring",   "text-muted",   "surface",         AA_NON_TEXT),
    ("trend threshold label",  "good",         "surface",         AA_TEXT),
    ("trend point score",      "text",         "surface",         AA_TEXT),
    ("trend point date",       "text-muted",   "surface",         AA_TEXT),
    ("trend sentence",         "text-strong",  "surface",         AA_TEXT),

    # The canonical chain cards (brief v16g). A dot, an arrow and a legend
    # swatch are graphics that carry meaning - the kind of a chain is the
    # colour and nothing else on the drawing itself - so 1.4.11 applies to
    # them against the card they sit on. The path under each node and the
    # generated note beneath the drawing are text on the same ground, at
    # 11px and 0.78rem, so they owe 1.4.3's ordinary ratio.
    #
    # Four kinds, four tokens, no fifth: `--good`, `--warn-strong`,
    # `--danger` and `--text-muted` are each already in this table in one
    # role or another, which is item 140's rule showing up as an absence of
    # new rows rather than a paragraph. What is here is the pairs those
    # tokens take in roles the table did not yet hold: `--good` and
    # `--text-muted` as graphics, and `--text-muted` as the monospace path.
    ("chain dot, healthy",     "good",         "surface",         AA_NON_TEXT),
    ("chain dot, mismatch",    "warn-strong",  "surface",         AA_NON_TEXT),
    ("chain dot, dead end",    "danger",       "surface",         AA_NON_TEXT),
    ("chain dot, variant",     "text-muted",   "surface",         AA_NON_TEXT),
    ("chain node path",        "text-muted",   "surface",         AA_TEXT),
    ("chain loop word",        "good",         "surface",         AA_TEXT),
    ("chain note",             "text-muted",   "surface",         AA_TEXT),
    ("chain all-healthy line", "good",         "surface",         AA_TEXT),

    # The probe panel (F-05). Three more tinted grounds, and the third time
    # this table has learned a pair from something else finding it first —
    # both notes above say so in the same words. `.confirmed-source` shipped
    # at 4.39:1 in light and neither register saw it: not this table, because
    # nobody added the row, and not the axe sweep, because these states only
    # paint with a brief and a measured probe staged.
    ("probe offer text",       "warn",         "warn-bg-soft",    AA_TEXT),
    ("probe value",            "text",         "good-bg-soft",    AA_TEXT),
    ("probe source",           "text-muted",   "good-bg-soft",    AA_TEXT),
]

THEMES = [(0, "light"), (1, "dark")]


@pytest.mark.parametrize("theme_i,theme", THEMES)
@pytest.mark.parametrize("label,fg,bg,minimum", PAIRS,
                         ids=[p[0].replace(" ", "-") for p in PAIRS])
def test_contrast(label, fg, bg, minimum, theme_i, theme):
    f, b = resolve(fg, theme_i), resolve(bg, theme_i)
    got = contrast(f, b)
    assert got >= minimum, (
        f"{label} in {theme}: {f} on {b} is {got:.2f}:1, needs {minimum}:1")


CHIP_RULE = re.compile(r"^\.(sev|mark)-[a-z-]+[^{]*\{([^}]*)\}", re.MULTILINE)


def test_every_chip_declares_its_own_ink():
    """A chip that sets a background but not a colour inherits one from
    whatever shared class it is combined with — and inheritance loses to
    source order, silently.

    This is the real bug: `.tool-mark` set `color: #fff` and, being declared
    after the severity block at equal specificity, overrode a chip whose own
    rule asked for dark ink. The result rendered at 2.15:1 while the pair
    table in this file passed, because the table checks what was declared
    together, not what the cascade resolves to. Keeping background and colour
    in the same rule is what makes the pair checkable at all.
    """
    offenders = []
    for m in CHIP_RULE.finditer(CSS.read_text(encoding="utf-8")):
        body = m.group(2)
        if "background" in body and "color" not in body:
            offenders.append(m.group(0).split("{")[0].strip())
    assert not offenders, (
        "chip rules setting a background with no colour of their own: "
        + ", ".join(offenders))


# Anchored at the start of a line rather than keyed on `.` or `#`, and that is
# the whole of UI-16's guard half. The previous pattern was
# `([.#][\w-][^{}]*?)\{...`, which required a selector to begin with a class or
# an id — so every bare element selector was outside the population, and the
# only live `opacity` declaration left in this stylesheet is on one:
# `button:disabled` at `styles.css:168`. Measured before changing it: the old
# pattern matched **zero** rules in the file it was reading. A guard whose
# evidence set is empty can only pass, which is why the non-vacuity assertion
# below is part of this check rather than a nicety.
#
# `[^{}@/]` for the first character excludes at-rules and a comment block
# standing where a selector would.
#
# **Comments are stripped before matching, and the dead end is worth recording
# because the obvious pattern walks straight into it.** Excluding `/` at the
# start of the selector is not enough: a comment *inside* a rule body is still
# inside `[^}]*`, so the check reads the prose. Six of the nine mentions of
# `opacity` in this stylesheet are comments recording that opacity was
# **removed**, each quoting the ratio it produced - `.pill-cost` at 0.65,
# `.seg-count` at 0.75, a tile at .55 - so a pattern that reads comments
# reports every fix as a fresh defect. Adding the disabled tokens made `:root`
# itself an offender at "opacity 0.65", quoted inside the comment explaining
# why those tokens exist.
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _declarations_only(css: str) -> str:
    """The stylesheet with its comments blanked, line structure intact.

    Blanked rather than deleted so a rule following a multi-line comment
    still begins a line, which `OPACITY_RULE` anchors on.
    """
    return COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), css)


#: Every rule in the stylesheet, and separately the declaration being looked
#: for. Keeping them apart is the whole correction: the pattern this replaces
#: required a selector *and* an opacity declaration in one match, so "no rule
#: fades anything" and "this regex matches nothing" were the same result, and
#: the check could not tell you which one it had. The rule population is what
#: the non-vacuity assertion below is measured on.
CSS_RULE = re.compile(r"^[ 	]*([^{}@/][^{}]*?)\{([^}]*?)\}", re.MULTILINE)
OPACITY_DECL = re.compile(r"opacity\s*:\s*([\d.]+)")

#: The rule this check was blind to for its whole life, kept as a canary on the
#: population rather than as an exemption. `button:disabled` carried the only
#: live `opacity` in the file and began with `b`, so the old selector pattern
#: - which required `.` or `#` - never had it in scope. If it stops being found
#: here, the population has narrowed again and the check says so instead of
#: going quiet.
POPULATION_CANARY = "button:disabled"
# Containers that hold no text a reader has to make out.
# `.sw` is the screen-reader-only helper and `[hidden]` is not painted at all,
# so neither composites a colour a reader has to make out.
#
# **`:disabled` used to be on this list and is not any more — UI-16.** The
# reasoning it carried, "1.4.3 excludes them", is true of WCAG and false of this
# product: `disabled` is the *only* in-flight indicator the dashboard has. Every
# control that reaches a server sets it while the request is out, so the greyed
# label is reporting live state rather than reporting inactivity, and 1.4.3's
# inactive-control exception does not reach it. Measured at the exemption's own
# last consumer — `.pill-btn` at `opacity: 0.5` over a card — the label composited
# to 2.12:1 light and 2.85:1 dark, by the same arithmetic that reproduces the
# 3.83:1 this stylesheet records for `.pill-cost` at 0.65.
#
# The dead end, so it is not re-walked: narrowing the exemption to "controls that
# are disabled for a reason other than being busy" is not expressible here. CSS
# has one `:disabled`, and which of the two meanings a given control intends is a
# fact about the component, not about the rule. Removing the exemption and giving
# the disabled state a measured colour pair is the only version of this that a
# stylesheet can hold.
OPACITY_ALLOWED = (".sw", "[hidden]")


def test_no_text_is_dimmed_by_opacity():
    """Opacity below 1 blends a colour toward whatever is behind it, and the
    result is invisible to every check in this file: the token it started
    from passes, so the pair table passes, and the rendered pixels fail.

    This has now bitten three times — `.seg-count` at 0.75 rendered 3.29:1,
    `.pill-cost` at 0.65 rendered 3.83:1, and `.tool-mark` before them. Each
    was found by running axe against real pixels, which is not something a
    unit test can do. So the rule here is structural instead: de-emphasise
    with a colour that has been measured on its ground, never by fading a
    colour that has not.

    The fourth instance was this check's own exemption list. `button:disabled`
    sat in `OPACITY_ALLOWED` for the whole life of this file, so the one live
    `opacity` declaration left in the stylesheet was the one declaration this
    guard was told not to look at — see the note above the tuple for why the
    exemption's reasoning does not hold in this product.
    """
    offenders, seen = [], []
    for m in CSS_RULE.finditer(
            _declarations_only(CSS.read_text(encoding="utf-8"))):
        selector = m.group(1).strip()
        seen.append(selector)
        faded = [v for v in OPACITY_DECL.findall(m.group(2)) if float(v) < 1.0]
        if not faded or any(ok in selector for ok in OPACITY_ALLOWED):
            continue
        offenders.append(f"{selector} (opacity {faded[0]})")
    # Rule 4: what the guard reports having read, not what it was configured to
    # read. Both clauses would have failed on the day the pattern stopped seeing
    # `button:disabled`, instead of the green that followed it.
    assert len(seen) > 100, (
        f"only {len(seen)} rules were read out of a stylesheet of "
        f"{len(CSS.read_text(encoding='utf-8').splitlines())} lines — "
        "CSS_RULE has narrowed and this check is grading a fraction of the file")
    assert POPULATION_CANARY in seen, (
        f"{POPULATION_CANARY!r} is not in the population this check read. "
        "Either the rule was removed — move the canary to another one and "
        "say why — or the selector pattern has narrowed the way it had "
        "silently narrowed before UI-16 found it")
    assert not offenders, (
        "text dimmed by opacity — set a measured colour instead: "
        + "; ".join(offenders))


#: Custom properties in `styles.css` that carry a LENGTH and never a colour,
#: so a light/dark pair would be meaningless for them.
#:
#: The clause below read `declared == paired` and its comment said tokens
#: without `light-dark()` are legitimate only if they never carry colour,
#: "today there are none, and this keeps it that way". Item 136m made some:
#: four block stylesheets each carried their own unmeasured pixel breakpoint,
#: and moving them into the one `@container part` rule in `styles.css` brought
#: their length tokens with them.
#:
#: An allow-list rather than a pattern on the name, for the reason the repo
#: uses allow-lists elsewhere: a rule like "ends in -gap" would silently admit
#: the first colour token somebody happens to name that way.
NOT_COLOUR = frozenset({
    "part-narrow",   # the one part-page breakpoint (item 136m, F-12)
    "cd-plot",       # crawl-depth plot height
    "cd-gap",        # crawl-depth bar gap
    "sg-sticky",     # the structured-data graph's sticky height
    "switch-rows",   # item 185: the rows the part switcher may spend
    # Item 174: the landing reference's type scale, 4 px spacing scale and
    # headline measure - sizes, not colours.
    "fs-headline", "fs-title", "fs-body", "fs-ui", "fs-label",
    "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "measure-headline",
})


def test_the_palette_is_defined_once_per_theme():
    """Every token carries both halves, so a light-only value cannot slip in
    and leave dark mode inheriting something arbitrary."""
    css = CSS.read_text(encoding="utf-8")
    declared = set(re.findall(r"--([a-z0-9-]+):", css))
    paired = set(tokens())
    assert declared - NOT_COLOUR == paired, (
        "these tokens are not light-dark() pairs: "
        + ", ".join(sorted(declared - paired - NOT_COLOUR))
        + ". A token that carries no colour goes in NOT_COLOUR with the "
          "reason; anything else needs both halves.")
    # And the allow-list is held to its own claim: a token listed there must
    # not be a colour. Without this the list is a way to opt out of the guard.
    for name in sorted(NOT_COLOUR):
        for value in re.findall(rf"--{name}:\s*([^;]+);", css):
            assert not re.search(r"#[0-9a-f]{3}|rgb|hsl|light-dark", value, re.I), (
                f"--{name} is in NOT_COLOUR and carries a colour: {value!r}")


# ---- markup regressions ----------------------------------------------------

# Rows and cards were once bare onClick handlers on <tr> and <li>: no tab
# stop, no Enter, nothing announced. Anchors replaced them; this stops the
# pattern coming back.
NON_INTERACTIVE = ("li", "tr", "td", "div", "span", "h1", "h2", "h3", "p")
OPEN_TAG = re.compile(r"<(" + "|".join(NON_INTERACTIVE) + r")\b((?:[^<>]|\n)*?)>",
                      re.MULTILINE)


def _tsx_files() -> list[Path]:
    files = sorted(SRC.glob("*.tsx"))
    assert files, "no dashboard sources found"
    return files


@pytest.mark.parametrize("path", _tsx_files(), ids=lambda p: p.name)
def test_no_click_handlers_on_non_interactive_elements(path: Path):
    offenders = []
    for m in OPEN_TAG.finditer(path.read_text(encoding="utf-8")):
        tag, attrs = m.group(1), m.group(2)
        if "onClick" not in attrs:
            continue
        # A handler is fine once the element is given a role and a tab stop.
        if "role=" in attrs and "tabIndex" in attrs:
            continue
        # A modal backdrop is the one honest exception: it is not a control,
        # it is a second way to dismiss something that must already be
        # dismissable by Escape and by a real close button. role="presentation"
        # says exactly that, and giving it a tab stop would put a focusable
        # nothing in the middle of the dialog's tab order.
        if 'role="presentation"' in attrs:
            continue
        line = path.read_text(encoding="utf-8")[:m.start()].count("\n") + 1
        offenders.append(f"{path.name}:{line} <{tag}>")
    assert not offenders, (
        "click handlers on non-interactive elements — use a button or an "
        "anchor, or add role + tabIndex + key handling:\n  "
        + "\n  ".join(offenders))


#: A `<th>` whose entire content is a visually-hidden span. The header is
#: announced to a screen reader and drawn for nobody else.
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
HIDDEN_TH = re.compile(
    r"<th\b[^<>]*>\s*<span\s+className=\"sr-only\">[^<]*</span>\s*</th>",
    re.MULTILINE)


@pytest.mark.parametrize("path", _tsx_files(), ids=lambda p: p.name)
def test_no_column_header_is_visible_only_to_a_screen_reader(path: Path):
    """A column whose name exists only in `sr-only` is unnamed for a mouse.

    `sr-only` is right for text that *supplements* a visible label — "out of
    100" beside a score, " not scored" beside an em dash. It is wrong when it
    carries the control's whole name, because then a sighted operator gets a
    bare checkbox and has to guess. That is how the fix-loop tick went
    undiscovered: the capability worked, and only assistive tech was told
    what it did.

    Enumerated from source rather than from a list of known sites. The header
    was duplicated across two screens because `fixloop.tsx` exported the cell
    and not the column, so a hard-coded list of two would have passed the
    moment a third table copied it.
    """
    # Comments blanked, not deleted, so line numbers still point at source.
    # This codebase records each defect it has shipped in a comment beside the
    # fix, so a guard that reads prose flags its own explanation — which it
    # did, on the very comment describing this one.
    text = COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                       path.read_text(encoding="utf-8"))
    offenders = [f"{path.name}:{text[:m.start()].count(chr(10)) + 1}"
                 for m in HIDDEN_TH.finditer(text)]
    assert not offenders, (
        "column headers with no visible name — give the <th> real text, and "
        "share one header component rather than copying it:\n  "
        + "\n  ".join(offenders))


# ---- reading JSX source: the primitives two scanners share ------------------

#: Moved here from the money scanner's section when the title lens was built
#: on the same walker. Both scanners must answer the same three questions —
#: is this `/` a divide or a regex, does this quote open a string, and what
#: line is this index on — and a primitive answering them for two callers
#: cannot go on living inside one of them.

#: A `/` opens a regex literal iff the previous token cannot end an
#: expression: division follows a value, a regex follows an operator.
#:
#: `<` is deliberately absent, and its presence here cost 30% of this scanner's
#: surface. Every JSX closing tag is `</`, so a `<` in this set made `</div>`
#: open a regex that then ran to end of line, and 2,870 of 9,519 scanned lines
#: were never examined past their first closing tag.
_REGEX_CAN_FOLLOW = "(,=:[!&|?{};+-*%^~>"
_REGEX_KEYWORDS = ("return", "typeof", "case", "in", "of", "do", "else")
_NL = chr(10)
_BQ = chr(96)


def _opens_regex(text: str, i: int) -> bool:
    j = i - 1
    while j >= 0 and text[j] in " \t" + _NL:
        j -= 1
    if j < 0:
        return True
    if text[j] == "<":            # a closing tag, never a regex
        return False
    if text[j] in _REGEX_CAN_FOLLOW:
        return True
    head = text[:j + 1]
    return any(head.endswith(k) for k in _REGEX_KEYWORDS)


def _skip_delimited(text: str, i: int, closer: str, *, classes: bool) -> int | None:
    """Index just past `closer`, or **None** if the line ends first.

    Tentative on purpose. Deciding what opens a string or a regex needs the
    grammar, and this has a heuristic; the recovery is what makes the heuristic
    safe. A quote or slash whose partner is not on the same line was not an
    opener — it was an apostrophe in JSX prose, or the `/` of a closing tag —
    so the caller rewinds and treats it as ordinary text.

    Without this, a misread opener silently consumed the rest of its line.
    `you haven't spent ${cost}` reported nothing, and neither did anything
    following a `</td>`, which is most of a JSX file.
    """
    i += 1
    while i < len(text) and text[i] != closer:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == _NL:
            return None
        if classes and ch == "[":          # a class may hold a bare /
            while i < len(text) and text[i] not in ("]", _NL):
                i += 2 if text[i] == "\\" else 1
            continue
        i += 1
    return i + 1 if i < len(text) else None


def _line_no(text: str, i: int) -> int:
    """Derived from the index when a hit is reported, never accumulated.

    A running counter must be advanced in every branch that skips ahead —
    comments, strings, regex literals, character classes — and one branch that
    forgets reports the right source line under the wrong number, which is
    worse than reporting none. Hits are rare, so O(n) each is free.
    """
    return text.count(_NL, 0, i) + 1


#: The phrase every narrow-run explanation is built around.
NARROW_RUN_PHRASE = re.compile(r"re-read a named handful", re.I)
#: UX-80. The direction of a caveat on a money figure — that the total
#: understates — is itself a stated limitation, so the provenance clause
#: above binds it identically. Home carries the sentence four lines below a
#: comment saying a `title` is "not a place an operator reads".
FLOOR_PHRASE = re.compile(r"\bis a floor\b", re.I)
#: Every place a `title` attribute can begin. Deliberately dumber than the
#: extractor below, and separate from it on purpose: this is the parity
#: assertion's *independent* enumeration of what there is to read. A check
#: drawing its evidence from the thing it checks can only ever pass, so the
#: list of sites to account for must not come from the walker accounting for
#: them.
_TITLE_SITE = re.compile(r"\btitle=")
#: The join in `"one " + "two"`, plus the delimiters and the wrapping around
#: it. Either delimiter on either side, because a template literal
#: concatenates with a quoted piece as readily as two quoted pieces do — and
#: that mixed shape is what `probes.tsx:145` and `anatomy.tsx:183` are.
CONCAT = re.compile(r"[\"`]\s*\+\s*[\"`]", re.DOTALL)
#: An interpolation's delimiters, **removed rather than blanked**, so the
#: static text either side of it abuts. Same reason `CONCAT` removes its join:
#: prose in this codebase is wrapped to 79 columns, so a wrap lands mid-phrase
#: and a space inserted at the seam invents a word boundary the browser never
#: renders.
INTERP = re.compile(r"\$\{|\}")


def _balanced(text: str, i: int) -> int | None:
    """Index just past the `}` closing the `{` at `i`, or None if none does.

    **This is the whole of the step.** `TITLE_ATTR` was
    `title=(\\{[^{}]*\\}|"[^"]*")`, which is a *depth-one* matcher: it stops at
    the first `}` it meets, so a value holding an interpolation, a nested
    ternary or an object is read to the wrong end or not read at all.
    Measured over the 21 `.tsx` in `dashboard/src`, it saw 58 of the 84 live
    `title` attributes and was blind to 26 across 10 files — among them
    `components.tsx:73` and `probes.tsx:145`, two of the findings the lens
    exists to count.

    Balancing needs the context tracking `rendered_dollars` needs, for its
    reasons: a brace inside a string, inside a regex character class, or
    inside a nested template literal is not a brace. Hence the shared
    primitives above rather than a second set of them.

    **Not `_skip_delimited` for the balancing, and its signature says why.**
    It returns None when the line ends first — deliberately; the recovery is
    what makes its heuristic safe — and the two title values that matter most
    span lines (`probes.tsx:145-146`, `anatomy.tsx:183-186`). It remains the
    right tool for the single-line strings and regexes *inside* the value,
    which is exactly how `rendered_dollars` uses it.
    """
    stack = ["{"]                      # "{" expression context, "`" template
    i, n = i + 1, len(text)
    while i < n and stack:
        c = text[i]
        in_tpl = stack[-1] == _BQ
        if not in_tpl:
            if text.startswith("//", i):
                nxt = text.find(_NL, i)
                if nxt < 0:
                    return None
                i = nxt
                continue
            if text.startswith("/*", i):
                end = text.find("*/", i)
                if end < 0:
                    return None
                i = end + 2
                continue
            if c == "/" and _opens_regex(text, i):
                j = _skip_delimited(text, i, "/", classes=True)
                i = j if j is not None else i + 1
                continue
            if c in "'\"":
                j = _skip_delimited(text, i, c, classes=False)
                i = j if j is not None else i + 1
                continue
        if c == "\\":
            i += 2
            continue
        if c == _BQ:
            stack.pop() if in_tpl else stack.append(_BQ)
            i += 1
            continue
        if c == "$" and in_tpl and text.startswith("${", i):
            stack.append("{")
            i += 2
            continue
        if not in_tpl:
            if c == "{":
                stack.append("{")
            elif c == "}":
                stack.pop()
                if not stack:
                    return i + 1
        i += 1
    return None


def title_attrs(text: str, spans: list | None = None):
    """Yield `(line, value)` for each `title=` attribute `text` builds.

    `value` is the expression **without** its outer delimiters, so `_spoken`
    is handed the same kind of thing for both spellings the codebase uses.

    `spans` is the reporting `rendered_dollars` takes as `skips`, widened to
    record what was *consumed* as well as what was stepped over — `("title",
    …)`, `("comment", …)`, `("string", …)`, `("regex", …)`. The parity
    assertion needs both halves: a `title=` this walker never saw, and a
    `title=` it correctly declined to read (one lives inside a `//` comment at
    `components.tsx:147`), are different answers, and a list of hits alone
    cannot tell them apart.
    """
    stack: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        in_tpl = bool(stack) and stack[-1] == _BQ
        if not in_tpl:
            if text.startswith("//", i):
                nxt = text.find(_NL, i)
                nxt = nxt if nxt >= 0 else n
                if spans is not None:
                    spans.append(("comment", i, nxt))
                i = nxt
                continue
            if text.startswith("/*", i):
                end = text.find("*/", i)
                end = (end + 2) if end > 0 else n
                if spans is not None:
                    spans.append(("comment", i, end))
                i = end
                continue
            if c == "/" and _opens_regex(text, i):
                j = _skip_delimited(text, i, "/", classes=True)
                if spans is not None and j is not None:
                    spans.append(("regex", i, j))
                i = j if j is not None else i + 1
                continue
            if c in "'\"":
                j = _skip_delimited(text, i, c, classes=False)
                if spans is not None and j is not None:
                    spans.append(("string", i, j))
                i = j if j is not None else i + 1
                continue
            if text.startswith("title=", i) and (
                    i == 0 or not (text[i - 1].isalnum()
                                   or text[i - 1] in "_$.")):
                k, end = i + 6, None
                if k < n and text[k] == "{":
                    end = _balanced(text, k)
                elif k < n and text[k] == '"':
                    # Not `_skip_delimited`: a JSX attribute value is not a JS
                    # string literal and may span lines, which is the one case
                    # that helper refuses. The shipped regex spanned lines too
                    # (`re.DOTALL`), so this preserves its reach exactly.
                    j = k + 1
                    while j < n and text[j] != '"':
                        j += 2 if text[j] == "\\" else 1
                    end = j + 1 if j < n else None
                if end is not None:
                    if spans is not None:
                        spans.append(("title", i, end))
                    yield _line_no(text, i), text[k + 1:end - 1]
                    i = end
                    continue
        if c == "\\":
            i += 2
            continue
        if c == _BQ:
            stack.pop() if in_tpl else stack.append(_BQ)
            i += 1
            continue
        if c == "$" and in_tpl and text.startswith("${", i):
            stack.append("{")
            i += 2
            continue
        if c == "{" and stack and stack[-1] == "{":
            stack.append("{")
        elif c == "}" and stack and stack[-1] == "{":
            stack.pop()
        i += 1


def _spoken(title_expr: str) -> str:
    """The sentence a browser would show, from the expression that builds it.

    **The dead end this replaces, recorded because the guard passed on the
    unfixed code and looked correct doing it.** The first version matched
    the phrase against the raw source. Every one of the three sites wrapped
    its string in a different place — `"…re-read a named " + "handful…"`,
    `"…re-read a " + "named handful…"`, twice with different tails — so no
    literal survives in any two of them, and the phrase survives in none.
    A search for the words a user reads found zero of three offenders and
    reported the file clean.

    That is the general shape rather than an accident of this sentence: a
    guard reading JSX source is reading an expression, and prose in this
    codebase is wrapped to 79 columns, so any phrase long enough to be
    specific is long enough to have been split. Join the pieces first, then
    match on what is spoken.

    **A template literal joins the same way**, which is the addition the
    brace-balanced lens made necessary: widening what is extracted buys
    nothing if the extra shapes render to nothing readable. An interpolation
    is *unwrapped* rather than dropped, so quoted prose inside one — a nested
    ternary choosing between two sentences, which is what `components.tsx:73`
    does — is still spoken here. Dropping it would have narrowed this guard in
    the same commit that widened its lens, and left the widening looking like
    a gain.
    """
    return " ".join(INTERP.sub("", CONCAT.sub("", title_expr))
                    .replace('"', " ").replace(_BQ, " ").split())


#: Shapes the lens must read correctly, with the spoken answer beside each,
#: on the precedent of `_SHAPES` below; `None` means nothing is extracted at
#: all. Written as data for that table's reason: the shipped matcher was
#: defeated by shapes nobody had listed, and a list is the only form in which
#: "which shapes did you check" has an answer.
_TITLE_SHAPES = [
    ('<span title="a plain quoted title">x</span>',
     "a plain quoted title", "the quoted spelling"),
    ('<span title={"one half " + "and the other"}>x</span>',
     "one half and the other", "two quoted pieces joined by +"),
    ('<span title={`a run of ${n} sites`}>x</span>',
     "a run of n sites", "a template literal carrying an interpolation"),
    ('<span title={`${w} — ${c === "good" ? "80 up" : "below"}`}>x</span>',
     "w — c === good ? 80 up : below",
     "an interpolation holding a nested ternary"),
    ('<span title={`Runs ${cmd} here. `\n + "Costs nothing — no model."}>x</span>',
     "Runs cmd here. Costs nothing — no model.",
     "a multi-line backtick-plus-quote concatenation"),
    ('<span title={ok ? "all }" : "none"}>x</span>',
     "ok ? all : none", "a closing brace inside a string in the value"),
    ("// the chip shipped with title={undefined} and no colour\n<span/>",
     None, "a // comment carrying a title="),
    ("/* the chip shipped with\n   title={undefined} */\n<span/>",
     None, "a block comment carrying a title="),
]


@pytest.mark.parametrize("src,expected,label",
                         _TITLE_SHAPES, ids=[s[2] for s in _TITLE_SHAPES])
def test_the_title_lens_reads_each_shape(src, expected, label):
    """One case per shape, because the count is the coverage claim.

    The shipped matcher read four of these eight, and it was not written
    carelessly — `title=(\\{[^{}]*\\}|"[^"]*")` reads every shape that existed
    when it was written. The others arrived afterwards, and nothing in the
    guard could say so, because it reported its hits and never reported what
    it had failed to reach.
    """
    got = [v for _, v in title_attrs(src)]
    if expected is None:
        assert got == [], label
    else:
        assert [_spoken(v) for v in got] == [expected], label


@pytest.mark.parametrize("path", _tsx_files(), ids=lambda p: p.name)
def test_the_title_lens_accounts_for_every_title_in_the_source(path: Path):
    """Parity: every `title=` in the file is one the lens read or declined.

    Rule 4 made checkable for this lens rather than asserted about it. A
    matcher can only report what it matched, so its own output can never show
    what it missed — which is how a depth-one regex sat at `:335` reporting 59
    hits with nothing to say that 26 live attributes across 10 files were
    invisible to it, `components.tsx:73` (UX-07) and `probes.tsx:145` (UX-47)
    among them.

    So the sites are enumerated by `_TITLE_SITE`, which knows nothing about
    values and so cannot be wrong about where one starts, and the lens must
    account for every one: read it, or record the comment, string or regex it
    sits inside. Run against the shipped matcher this named exactly 26
    offenders across 10 files — the figure that made the widening step 1
    rather than a later tidy.

    The `title=` inside a `//` comment at `components.tsx:147` is the case
    that makes "or declined" necessary. It is not a blind spot: it renders
    nothing, and the walker steps over it deliberately. The old matcher read
    it as a live attribute, which is the same defect pointing the other way.
    """
    text = path.read_text(encoding="utf-8")
    spans: list = []
    for _ in title_attrs(text, spans):
        pass
    blind = [f"{path.name}:{_line_no(text, m.start())}"
             for m in _TITLE_SITE.finditer(text)
             if not any(a <= m.start() < b for _, a, b in spans)]
    assert not blind, (
        "title attributes the lens cannot see — it reports what it matched, "
        "so these are invisible in its own output:\n  " + "\n  ".join(blind))


@pytest.mark.parametrize("path", _tsx_files(), ids=lambda p: p.name)
def test_that_a_money_total_understates_never_lives_only_in_a_title(path: Path):
    """UX-80's second half, on the same clause as the guard below it.

    "Entries written before their model had a configured price carry no cost,
    so this figure is a floor" is a limitation on a displayed value — the one
    sentence saying which *direction* the number is wrong in. On Home it sits
    in a `title` on a `Stat`, four lines under a comment in the same file
    saying a `title` is not a place an operator reads.

    Enumerated over every `.tsx` on the phrase rather than over the one known
    site, for the reason the narrow-run guard beside it records: this sentence
    already exists in three spellings across three screens, and a hard-coded
    list of one passes the moment a fourth screen copies it.
    """
    offenders = [f"{path.name}:{line}"
                 for line, expr in title_attrs(path.read_text(encoding="utf-8"))
                 if FLOOR_PHRASE.search(_spoken(expr))]
    assert not offenders, (
        "which way a money total is wrong, reachable only by hovering — put "
        "it in rendered text, from the component that owns the frame:\n  "
        + "\n  ".join(offenders))


def test_the_priced_entries_frame_states_which_way_the_total_is_wrong():
    """UX-80's first half. The owner asserts a direction it stopped rendering.

    Before UI-19, `tools.tsx` rendered `- a floor: {n} of {m} entries priced`.
    UI-19 collapsed three screens' sentences into `PricedFrame` — correctly,
    they had disagreed on weight — and the word `floor` did not survive the
    move. `PricedFrame`'s own docstring still states its purpose as "so the
    number reads as a floor rather than as a total", so the owner claims the
    property it no longer delivers, and all three screens now tell the
    operator which entries are priced and leave them to infer that the total
    beside it understates.

    Asserted on the owner rather than on the three call sites, because that
    is the whole of what UI-19 bought: one edit reaches all three. Read from
    the rendered body, not from the docstring — a docstring saying "floor" is
    what shipped this defect.
    """
    src = (SRC / "components.tsx").read_text(encoding="utf-8")
    assert "export function PricedFrame(" in src, (
        "components.tsx does not export an owner for the priced-entries frame")
    body = src.split("export function PricedFrame(", 1)[1].split("\n}", 1)[0]
    assert "floor" in _without_comments(body), (
        "the priced-entries frame says how many entries are priced and not "
        f"which way that leaves the total: {body!r}")


@pytest.mark.parametrize("path", _tsx_files(), ids=lambda p: p.name)
def test_what_a_narrow_run_is_never_lives_only_in_a_title(path: Path):
    """UX-42. A stated limitation must be in text, not in an attribute.

    The provenance invariant says so in its own words: "a stated limitation
    on a displayed value must appear in rendered text — not only in a
    `title` attribute, an `aria-label`, an `sr-only` element, or a string
    that reaches only the model." A narrow run's composite is a limitation
    on a displayed value if anything is: the number is real and is not the
    site's.

    Three tables across two screens each explained it in a `title` on a
    non-focusable `<span>`, so a keyboard reached the words "narrow run" and
    nothing else. They shipped in the round whose own report already carried
    `title`-only explanation as an open defect three times over — and the
    same commit got it right in `RunDetailView` with a rendered Card, so the
    correct pattern and the incorrect one landed together.

    Enumerated from every `.tsx` rather than from the three known sites, for
    the reason the header guard above records: the sites multiplied by
    copying, so a hard-coded list of three passes the moment a fourth table
    copies it. The phrase is what is enumerated on, not the file.
    """
    # No `COMMENT` blanking: the walker steps over both comment spellings
    # itself, which is why `COMMENT` did not have to be widened to reach
    # `//` and stays shared, unnarrowed, with the header guard above.
    offenders = [f"{path.name}:{line}"
                 for line, expr in title_attrs(
                     path.read_text(encoding="utf-8"))
                 if NARROW_RUN_PHRASE.search(_spoken(expr))]
    assert not offenders, (
        "what a narrow run is, reachable only by hovering — put the sentence "
        "in rendered text, from the one component that owns it:\n  "
        + "\n  ".join(offenders))


#: The one owner of what a finding's excluded states mean, read out of the
#: component that exports it. **Not a list in this file**, which is the whole
#: point: `NARROW_RUN_PHRASE` above is one enumerated sentence, and it is now
#: the last hand-kept population in this file — `UNBROKEN_TOKEN_CLASSES` was
#: the other, and round 068 replaced it with a derivation (CQ-110 remains,
#: CQ-27 is closed). A hand-kept population stops growing when the product
#: does. This one cannot: a fourth state added to `STATE_MEANING`
#: is a fourth sentence this guard defends, with nothing to remember.
STATE_MEANING = re.compile(r'^\s*"([a-z-]+)":\s*"((?:[^"\\]|\\.)*)"',
                           re.MULTILINE)


def _owned_sentences() -> dict[str, str]:
    text = (SRC / "fixloop.tsx").read_text(encoding="utf-8")
    start = text.index("export const STATE_MEANING")
    body = text[start:text.index("};", start)]
    owned = {m.group(1): m.group(2) for m in STATE_MEANING.finditer(body)}
    assert len(owned) >= 3, f"STATE_MEANING did not parse: {owned}"
    return owned


#: Words in a row before two sentences are the same sentence. Four, and the
#: number was measured rather than picked — see `_shingles`.
_SHINGLE = 4


def _shingles(sentence: str) -> set[tuple[str, ...]]:
    """Every run of `_SHINGLE` consecutive words, lowercased.

    Derived from the owned sentence rather than chosen by hand, because the
    same meaning is spelled three ways across the product — "It opens if a
    second run confirms it", "it opens if it appears again", "opens if it
    appears again" — and a guard matching the owner's exact string would see
    none of the copies it exists to find.

    **Three was tried first and was wrong, and the two it wrongly caught are
    the reason four is here.** At three words this flagged
    `reports.tsx`'s deliverable staleness note on "a later audit" and
    `VERDICT_CHIP`'s `still` chip on "the finding was" — neither of which is
    a state's meaning, and both of which would have been sent to a component
    that does not own their sentence. Four separates them cleanly: "a later
    audit **that**" against "a later audit **has**", "the finding was
    **never**" against "the finding was **still**".

    **What four costs, stated rather than discovered later.** One live
    paraphrase falls below it: `FixState`'s own `candidate` title, "Seen
    once. It opens if a second run confirms it", shares no four-word run
    with the owned sentence. That title is deleted in the commit that adds
    this guard, so nothing is being waved through today — but a *new*
    paraphrase that short would pass, and the browser assertion beside this
    one is what covers the rendered half. A guard that says where it stops
    is worth more than one that implies it stops nowhere.
    """
    w = [x for x in re.split(r"[^\w]+", sentence.lower()) if x]
    return {tuple(w[i:i + _SHINGLE]) for i in range(len(w) - _SHINGLE + 1)}


@pytest.mark.parametrize("path", _tsx_files(), ids=lambda p: p.name)
def test_no_title_carries_a_meaning_state_note_owns(path: Path):
    """UX-43. What `withdrawn` means was reachable only by hovering.

    The provenance invariant, extended clause: a stated limitation on a
    displayed value must appear in rendered text, not only in a `title`. A
    state that takes a finding *out* of the count in front of the operator is
    a limitation on every number above it, and the meaning of `withdrawn`
    existed in exactly two places, both of them `title` attributes on
    non-focusable spans, on two different screens.

    The counter-assertion this cannot be passed by: `StateNote` renders the
    sentence, and `test_the_record_says_what_withdrawn_means_without_a_mouse`
    drives a browser and reads it out of `inner_text`. Deleting the sentences
    to satisfy this guard turns that one red.
    """
    owned = {s for v in _owned_sentences().values() for s in _shingles(v)}
    offenders = []
    for line, expr in title_attrs(path.read_text(encoding="utf-8")):
        spoken = _spoken(expr)
        hit = _shingles(spoken) & owned
        if hit:
            offenders.append(f"{path.name}:{line} — {' '.join(sorted(hit)[0])}")
    assert not offenders, (
        "a state's meaning is in a `title`, so a keyboard reaches the chip "
        "and not the reason — render it with `StateNote`, which reads the "
        "same sentence from `STATE_MEANING`:\n  " + "\n  ".join(offenders))


#: `UNBROKEN_TOKEN_CLASSES` and `test_a_class_holding_an_unbroken_token_can_break_it`
#: stood here for eleven audit reports as CQ-27, and are gone rather than
#: moved. The tuple named `.fact-mono` because `.fact-mono` had already
#: caused a fault — a 140-character filename in the images cell widening the
#: Image column until Alt text left the screen — so its population was a
#: record of what had gone wrong, not a rule about what may.
#:
#: `tests/test_real_data_scale.py` now derives that population from `type
#: Facts` in `anatomy.tsx`, and covers the invariant's other clause as well.
#:
#: **This paragraph claimed a demonstration the committed code could not
#: produce, and it stood for a round.** It read that renaming the images
#: cell's class made the derived guard name `anatomy.tsx:974`. Line 974 is
#: `) : (`. The derived guard's population came from a window running
#: `function PageFactsBody` to `const Row = `, and the same commit moved
#: `ImagesTable` out of that window — so the images cell was in the
#: population of neither the deleted tuple nor its replacement. Report 069
#: found it as CQ-27 at its eleventh round.
#:
#: Re-run after the derivation was rebuilt on `_blocks()` and `_chains()`,
#: and recorded from what the run printed: the population goes from four
#: sites to ten, and renaming `.fact-mono` to `.fact-key` on the images cell
#: makes the guard fail with `anatomy.tsx:980 — .fact-key on
#: src.split("/").pop()`. That is the sentence this paragraph was supposed
#: to be able to say.
#:
#: Deleted and not kept beside it, because two guards for one rule is the
#: defect this repository keeps finding in its own product — the one the
#: provenance tag had nineteen of.

# ---- the stylesheet has a reader -------------------------------------------

#: A hook a test drives the DOM by. It paints nothing and is not meant to;
#: the value is the file and the **test function** that selects it, so a
#: rename that would break that test is visible from here rather than from a
#: red browser job.
#:
#: **Never a line number.** CQ-143, reports 067 to 071. A `file:line` value is
#: true when written and false the next time anything is inserted above it:
#: round 070 corrected two of these to `:733` and `:794`, and two commits
#: later in the same round `e4a8405` and `7a760c2` inserted two hundred lines
#: above them — `:733` became an unrelated assertion and `:794` a closing
#: docstring quote. Nothing failed, because nothing read the values. The same
#: commit wrote two rows on the durable form and left the ones it was
#: correcting on the fragile one. Both halves are now enforced by
#: `test_no_pointer_in_the_register_is_a_line_number` below: the form is
#: asserted, and the named function is asserted to exist.
#:
#: The values below were derived by searching `tests/` for each class rather
#: than by re-reading the old pointers — three of the ten did not resolve to
#: the test that selects the class, and `runs-table:640` was not inside a test
#: function at all.
SELECTED_NOT_PAINTED = {
    # The three answers to an analysis finding that waits (item 237): drawn
    # by the button factory, named so the guard can press each.
    "fix-confirm-open": "tests/test_a_brief_only_finding_waits_for_the_operator.py",
    "fix-confirm-accept": "tests/test_a_brief_only_finding_waits_for_the_operator.py",
    "fix-confirm-withdraw": "tests/test_a_brief_only_finding_waits_for_the_operator.py",
    # The Headings card with no outline to diff against (item 224): drawn
    # by `.muted`, named so the absence can be asserted.
    "fix-baseline-none": "tests/test_a_headings_card_diffs_against_the_page_at_site_scope.py",
    # The record narrowed to one audit (item 207): drawn by `.chip`, named
    # so the clause that presses it to widen the record can find it.
    "run-chip": "tests/test_every_count_on_the_landing_is_its_own_door.py",
    # The registry's disclosure and glossary route (item 166): hooks the
    # tests read the rendered text through, painting nothing of their own.
    "legend-short": "tests/test_every_tone_and_term_has_one_definition.py",
    "glossary": "tests/test_every_tone_and_term_has_one_definition.py",
    # The generator's control, named so a clause can press it without
    # matching every `pill-run` on the screen (brief v17 step AX). It
    # wears `pill-btn pill-run` and paints nothing of its own.
    "write-brief-btn": "tests/test_a_brief_can_be_written_for_a_page.py — "
                       "test_the_control_names_what_it_makes_and_not_what_it_checks",
    "add-forms": "tests/test_site_switch.py — "
                 "test_a_site_added_in_the_app_is_offered_by_the_picker",
    # CQ-197's and UX-98's hooks stood here - `confirm-run` and
    # `run-blocked` - and both left with item 188. They existed only so a
    # driven test could name one control on the Tools screen without matching
    # every other button wearing the same style class; neither carried a CSS
    # rule, and no component names either of them now. Re-pointing them at a
    # control they were not about would be the "exception that outlives its
    # reason" this file warns against two screens down, so they are gone
    # instead. The dialog the sweep still opens is `schedule.tsx`'s, which
    # names its own evidence in `DIALOG_EVIDENCE`.
    # The canonical chain block's page-scope hook (brief v16g). The block
    # renders one card instead of the site's grid when a page is in scope,
    # and the two states are otherwise identical markup — so a clause that
    # waits for the narrowed payload has nothing else to name. It paints
    # nothing on purpose, for the reason the three hooks above give: a hook
    # that also carried a rule could not be removed without changing the
    # screen.
    "cc-page": "tests/test_canonical_chains_are_walked.py — "
               "test_site_scope_draws_the_grid_and_page_scope_draws_one_card "
               "and test_pressing_a_node_opens_that_page_in_scope",
    "schedule-open": "tests/test_a11y_rendered.py — "
                     "test_every_dialog_the_app_renders_is_opened_by_the_sweep "
                     "and test_every_text_selector_captured_something"
                     "[.sched-block-client]",
    # The verify button's hook (item 140). After the tone migration both the
    # `verify` control and `clear these marks` carry `tone-action-free`, so
    # `.mark-bar .tone-action-free` no longer names one control; the hook lets
    # a driven test point at verify alone. Painted by `tone-action-free`,
    # which it already carries — a hook that also carried a rule could not be
    # removed without changing the screen.
    "mark-verify": "tests/test_fetch_state.py — "
                   "test_a_refresh_that_is_not_a_page_change_does_not_claim_one",
    # The link to the audit in flight on the suggested order's step 2. Painted
    # by `pill-btn`, which it already carries; the hook exists so the driven
    # test can tell "open the run" from the launcher link that stands in the
    # same slot when nothing is running, without matching on the caption.
    "seq-open-run": "tests/test_a_running_audit_is_a_state_of_its_own.py — "
                    "test_a_running_audit_is_said_and_not_offered_again",
    # The line the merged pane shows where the tree would be when the
    # position could not be read (plan §5c). Painted by `muted head-note`;
    # the hook lets the driven test find that sentence and not the header's.
    "anat-unread": "tests/test_the_strip_survives_the_position_failing.py — "
                   "test_a_failed_position_leaves_every_step_and_says_so",
    # The line under the chooser saying where its counts come from, with
    # the link to step 1's pane. Painted by `muted`; the hook lets the driven
    # test name this sentence apart from the grid's own `scan-foot`.
    "scan-from-precheck": "tests/test_the_analyses_pane_reads_one_audit.py — "
                          "test_step_two_s_pane_holds_the_chooser_and_the_launcher_still_does",
    # Speed's depth pills (brief v19 step BC). Painted by `pill-btn` and the
    # tone classes they already carry; each hook names ONE pill so a clause
    # can press the free one without matching the two that spend, which is
    # exactly the distinction F-10 exists to keep. `.sp-act-standard` and
    # `.sp-act-deep` are computed from the depth and so are out of this
    # check's reach (it reads `className="..."` literals only) - they are the
    # same shape and the same reason.
    "sp-act-prf": "tests/test_the_speed_depth_pills.py — "
                  "test_the_free_pill_and_the_two_that_spend_are_told_apart",
    # 150 BJ's three figure hooks, now spans in the state sentence (item 168;
    # the `.bj-figs` bar that once styled them was never mounted and is gone).
    # Each is a name and nothing else - which is what lets a clause
    # point at ONE of the header's figures rather than at "the third div",
    # the index that four reorderings of this bar have already moved. A hook
    # that also carried a rule could not be removed without changing the
    # screen. `.fig-gap` and `.fig-record` do carry rules, so they are not
    # here.
    "fig-size": "tests/test_the_header_states_three_numbers_with_denominators.py — "
                "test_the_header_states_the_site_size_and_never_the_declaration_alone",
    "fig-coverage": "tests/test_the_header_states_three_numbers_with_denominators.py — "
                    "test_coverage_is_crawled_over_site_size_and_says_the_percentage",
    "fig-assessed": "tests/test_the_header_states_three_numbers_with_denominators.py — "
                    "test_assessed_is_findings_been_through_and_never_reads_as_progress",
    # Item 155's four hooks. `.count` is the one count component's own class
    # and is deliberately unpainted — it wraps figures in a table cell, a
    # sidebar badge, a strip foot and a grid header, and a rule of its own
    # would fight each of those; what it carries instead is `data-population`,
    # which is what the guard reads. The other three name the one cell a
    # clause has to point at: a prevalence, which is the count this item is
    # about, told apart from the findings counts in the same row of `td.num`.
    # Painted by `num` (and by `count-of`, which IS declared), so a hook that
    # also carried a rule could not be removed without changing the screen.
    "count": "tests/test_every_count_carries_its_population.py — "
             "test_a_count_rendered_without_a_population_fails",
    "check-prev": "tests/test_every_count_carries_its_population.py — "
                  "test_prevalence_never_uses_the_record_as_its_denominator",
    "cause-prev": "tests/test_every_count_carries_its_population.py — "
                  "test_prevalence_never_uses_the_record_as_its_denominator and "
                  "test_a_site_scoped_count_is_not_rendered_as_a_page_ratio",
    "hl-pages": "tests/test_every_count_carries_its_population.py — "
                "test_a_count_rendered_without_a_population_fails",
    "out-count": "tests/test_real_data_scale.py — "
                 "test_the_outline_card_states_nothing_dropped_when_the_crawl_kept_all and "
                 "test_the_crawls_own_limit_is_stated_whatever_the_filter_shows",
    "runs-table": "tests/test_a11y_rendered.py — "
                  "test_the_runs_table_says_in_text_what_a_narrow_run_is and "
                  "test_one_comparison_is_offered_and_it_reaches_across_a_verification",
    # The second pointer was
    # `test_the_opener_carries_no_mark_and_the_button_that_spends_does`,
    # renamed by WF-59: the section refresh sends `analyst: false` now,
    # so neither of its two steps spends and there is no longer a "button
    # that spends" for the name to mean.
    "sec-refresh-open": "tests/test_section_refresh.py — "
                        "test_the_cost_is_readable_before_the_click_not_after, "
                        "test_neither_step_of_the_section_refresh_is_marked_as_spending "
                        "and "
                        "test_the_run_it_starts_is_scoped_to_the_dimension_that_covers_the_section",
    "sec-refresh-page": "tests/test_section_refresh.py — "
                        "test_with_a_page_selected_the_control_narrows_to_that_page "
                        "and test_the_page_refresh_asks_for_the_page_and_the_section",
    # This row was in PAINTED_BY_NOTHING with the reason "no clause selects
    # it yet"; two now do, one per picker, so it moves rather than staying
    # true-when-written. An exception that outlives its reason is CQ-145.
    # Back to one picker with item 188: the brief target picker was
    # `tools.tsx`'s and its clause retired with it. `_picker_narrows` stays,
    # and the surviving screen's clause still drives it.
    "page-count": "tests/test_real_data_scale.py — "
                  "test_the_page_dossier_picker_is_narrowed_by_its_url_filter, "
                  "through _picker_narrows",
    # UX-06's outage panel. `.error` beside it carries every pixel; this name
    # exists only so the guard can ask "is the outage on screen" without
    # matching the other `.error` paragraphs the app renders inside views.
    "server-down": "tests/test_server_outage_is_named.py — "
                   "test_the_outage_screen_says_the_server_did_not_answer",
    # UX-60's notice. `.muted` and `.fact-note` beside it carry the paint;
    # this name exists so the two clauses that read the crawl's limit have
    # one hook and the outline's other muted notes are not swept up with it.
    "not-kept": "tests/test_real_data_scale.py — "
                "test_the_crawls_own_limit_is_stated_whatever_the_filter_shows, "
                "both surfaces, and the counter-assertion in "
                "test_the_outline_card_states_nothing_dropped_when_the_crawl_kept_all "
                "that it is absent on a page the crawl did not truncate",
    "sec-refresh-page-confirm":
        "tests/test_section_refresh.py — "
        "test_with_a_page_selected_the_control_narrows_to_that_page and "
        "test_the_page_refresh_asks_for_the_page_and_the_section",
    "sec-refresh-page-done":
        "tests/test_section_refresh.py — "
        "test_the_page_refresh_asks_for_the_page_and_the_section",
    "sec-refresh-page-open":
        "tests/test_section_refresh.py — "
        "test_with_a_page_selected_the_control_narrows_to_that_page and "
        "test_the_page_refresh_asks_for_the_page_and_the_section",
    "stale-note": "tests/test_fetch_state.py — "
                  "test_a_page_change_marks_the_evidence_stale_and_keeps_the_picker, "
                  "test_a_refresh_that_is_not_a_page_change_does_not_claim_one "
                  "and test_clearing_the_page_filter_is_not_reported_as_choosing_a_page",
}

#: Reachable by neither a rule nor a selector — named for nobody. Each row is
#: a small open question rather than a settled decision, and the reason says
#: which. They are recorded rather than deleted because removing a class name
#: from a container changes a screen for no observable benefit, and recorded
#: rather than left out because the whole point of the guard is that the next
#: one fails instead of shipping.
PAINTED_BY_NOTHING = {
    "alist": "container in analyses.tsx:642; the rows inside it carry the paint",
    "alist-head": "sits beside .muted on analyses.tsx:647, which paints it",
    "phase-note": "sits beside .muted in admin.tsx's WorkbenchTab, which paints it",
    "phase-moved": "sits beside .muted in views.tsx's RunDetailView, which paints it",
    "report-view": "outermost wrapper in markdown.tsx:313; nothing inside needs it",
    "row-model": "analyses.tsx:222; styles.css:1622 names it in prose and the "
                 "rule beside that comment targets `input, select, textarea`",
    "to-confirm-runnable": "sits beside .to-confirm on probes.tsx:140, which paints it",
    "wb-toggle": "workbench.tsx:157; a disclosure caret taking its parent's ink",
    "intl-gate": "part identity on a .now-card in part_page.tsx's IntlNow; "
                 ".now-card paints it, the name is for the render tests",
    "intl-now": "part identity on a .now-card in IntlNow, which .now-card paints",
    "intl-clusters": "sits beside .findings on IntlNow's table, which paints it",
    "mobile-now": "part identity on a .now-card in MobileNow, which .now-card paints",
    "mobile-templates": "sits beside .findings on MobileNow's table, which paints it",
}

#: `className="a b"` only. A computed class cannot be read from source and is
#: out of reach here, the same way PAIRS cannot see what is composited over
#: what — say so rather than let the count read as complete.
CLASS_LITERAL = re.compile(r'className="([^"{}]+)"')


def _stylesheets() -> list[Path]:
    """Every stylesheet the app actually loads, read off its own imports.

    One hard-coded path until brief v16a step AT-b, when the Structured data
    picture took a sheet of its own and 40 classes that paint correctly were
    reported as painting nothing. The fix is not a second constant: it is to
    ask the source which sheets it imports, so a third sheet is covered the
    day it is added rather than the day someone remembers this file.

    Imports rather than a glob of `*.css`, because the property that matters
    is that a class the app *loads* declares it. A stylesheet sitting in the
    directory unimported paints nothing either, and counting it here would
    hide exactly the defect this guard is for.
    """
    named: list[Path] = []
    for src in sorted(SRC.glob("*.ts*")):
        for name in re.findall(r'^import\s+"\./([A-Za-z0-9_.-]+\.css)";',
                               src.read_text(encoding="utf-8"), re.M):
            sheet = SRC / name
            if sheet.is_file() and sheet not in named:
                named.append(sheet)
    assert CSS in named, (
        "the app no longer imports styles.css, so this guard is reading "
        f"something else entirely: {[p.name for p in named]}")
    return named


def _declared_classes() -> set[str]:
    """Every class the stylesheet mentions outside a comment.

    Comments are stripped first, and that is not tidiness: `.row-model` is
    discussed in the prose at `styles.css:1622` and declared nowhere, so a
    scan of the raw text reports it as painted. It was the seventeenth
    offender and the only one this step found by tightening rather than by
    looking.
    """
    text = "\n".join(sheet.read_text(encoding="utf-8")
                     for sheet in _stylesheets())
    css = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return set(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", css))


def test_every_class_a_component_names_is_declared_or_recorded():
    """A class named in a component and absent from the stylesheet paints
    nothing, and until this ran nothing in the repository could see one.

    UI-10 is the instance: `probes.tsx:122` carries `link-btn`, the only
    occurrence of that name anywhere, so the "measure again" button took
    user-agent chrome inside a tinted span — `.confirmed-again` supplies
    `margin-left` and `font-size` and no button shape at all.

    Enumerated from source rather than from the report's list, per the rule
    that a hard-coded list of three is how a partial fix passes: 322 classes
    are named in `className` literals and 17 had no rule. Sixteen were not in
    the finding. One of them, `err` on `deliverable.tsx:29`, is the same
    defect with a spelling one character from `.error` — six other error
    paragraphs in the app say `error` and paint red; that one did not.

    The check is deliberately permissive about what counts as declared: any
    `.foo` in the stylesheet outside a comment. A tighter selector parse
    would find more, and would also make this guard argue with the cascade,
    which is the job of the axe pass over rendered pages.
    """
    declared = _declared_classes()
    recorded = set(SELECTED_NOT_PAINTED) | set(PAINTED_BY_NOTHING)
    offenders = []
    for path in sorted(SRC.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        for m in CLASS_LITERAL.finditer(text):
            # `chr(10)`, not an escape, and the same at the join below.
            # The dead end, recorded because it cost two runs: writing the
            # literal here produced a real 0x0A in the source and aborted
            # collection — KI-21's family, in a test file rather than a
            # register. `_NL` at :596 and `chr(10)` at :803 are the two
            # places this file already worked around it.
            line = text.count(chr(10), 0, m.start()) + 1
            for cls in m.group(1).split():
                if cls not in declared and cls not in recorded:
                    offenders.append(f"{path.name}:{line} .{cls}")
    assert not offenders, (
        "a class named in a component that styles.css never declares paints "
        "nothing — add the rule, or record it in SELECTED_NOT_PAINTED with "
        "the test that selects it, or in PAINTED_BY_NOTHING with the reason:"
        + (chr(10) + "  ") + (chr(10) + "  ").join(sorted(set(offenders))))


def test_no_recorded_class_has_quietly_acquired_a_rule():
    """The other direction, because an exemption list is only honest while
    each row is still true.

    A class that gains a rule is no longer unpainted, and a row left behind
    turns the list into a place names go to stop being checked — which is the
    failure mode of every hand-kept list in this repository.
    """
    declared = _declared_classes()
    stale = sorted((set(SELECTED_NOT_PAINTED) | set(PAINTED_BY_NOTHING)) & declared)
    assert not stale, (
        "recorded as unpainted and now declared in styles.css — drop the row: "
        + ", ".join(stale))


def test_no_pointer_in_the_register_is_a_line_number():
    """CQ-143, reports 067 to 071 — the register cannot hold a line number
    true across one round, and until now nothing failed when it stopped.

    Two directions, because either alone just moves the staleness one hop:

    1. **The form.** A value ending in `:<digits>` is stale as soon as
       anything is inserted above that line. Round 070 corrected two of these
       and two later commits *in the same round* broke both again — `:733`
       became an unrelated assertion and `:794` a closing docstring quote.
       Three of the ten pointers had drifted off the test that selects the
       class entirely, and `runs-table:640` was not inside a test function.
    2. **The referent.** A test-function name is durable against insertion
       but not against renaming or deletion, so every `test_*` token in a
       value must name a function that exists somewhere in `tests/`. Without
       this the fix is a better spelling of the same defect.

    Both halves read the register and the test files; neither is a list kept
    by hand, which is what CQ-110 and CQ-144 are about one layer out.
    """
    fragile = sorted(f"{cls}: {where}"
                     for cls, where in SELECTED_NOT_PAINTED.items()
                     if re.search(r":\d+\s*$", where))
    assert not fragile, (
        "a pointer in SELECTED_NOT_PAINTED is a line number, which stops "
        "being true the next time a line is inserted above it — name the "
        "test function instead:"
        + (chr(10) + "  ") + (chr(10) + "  ").join(fragile))

    known = set()
    for path in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        known.update(re.findall(r"^def (test_\w+)", path.read_text(encoding="utf-8"),
                                re.MULTILINE))
    missing = sorted(
        f"{cls}: {name}"
        for cls, where in SELECTED_NOT_PAINTED.items()
        # The file part is stripped before scanning, because
        # `tests/test_site_switch.py` contains a `test_\w+` token that is a
        # *module* name; without this it is reported as a function that does
        # not exist, which is CQ-143 wearing the fix's clothes.
        for name in re.findall(r"test_\w+", re.sub(r"\S+\.py", "", where))
        if name not in known)
    assert not missing, (
        "a pointer names a test function that no longer exists — the class "
        "is recorded as driven by a clause nobody can find:"
        + (chr(10) + "  ") + (chr(10) + "  ").join(missing))


# ---- vocabulary and recovery-path guards -----------------------------------

def test_every_run_status_has_a_colour_rule():
    """`RunStatusChip`'s map is the one non-exhaustive pattern in the file
    that owns the status vocabulary.

    `isInFlight`, `hasScore`, `hasResults` and `isDeletable` all exhaust
    `RunStatus` through `assertNever`, so `tsc` catches a new member in four
    places out of five. The fifth compiles, renders `title={undefined}` and
    takes no colour — the chip goes out unexplained and unstyled.

    The union is read from source rather than restated here: a hard-coded
    list of six is how the next status slips past.
    """
    api_ts = (SRC / "api.ts").read_text(encoding="utf-8")
    union = re.search(r"export type RunStatus\s*=\s*([^;]+);", api_ts)
    assert union, "RunStatus union not found in api.ts"
    members = re.findall(r'"([a-z]+)"', union.group(1))
    assert len(members) >= 5, f"suspiciously few statuses parsed: {members}"

    css = CSS.read_text(encoding="utf-8")
    ruled = set(re.findall(r"\.run-status-([a-z]+)", css))
    missing = [m for m in members if m not in ruled]
    assert not missing, (
        f"RunStatus members with no .run-status-* rule: {missing}. "
        f"styles.css declares {sorted(ruled)}")


def test_a_missing_key_is_not_recovered_through_a_shell():
    """`setx` was offered as the only recovery path at seven sites.

    Provider keys have been settable in Admin since 0.14.0, and the launcher
    — where a missing key is actually noticed — still sent the operator to a
    shell. `admin.tsx` gets it right: Provider keys first, `setx` kept as the
    secondary scripted-install path. Carried open from round 001 to round 015.

    `setx` is not banned — it stays as the secondary, scripted-install path,
    which is what `admin.tsx` does. What is banned is offering it *alone*.
    So the rule is per file: any screen that names `setx` must also name
    Provider keys, and a new screen that reaches for a shell without one
    fails rather than moving a number.
    """
    offenders = {}
    for path in sorted(SRC.glob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        if "setx" not in text or "Provider keys" in text:
            continue
        offenders[path.name] = [i + 1 for i, line in
                                enumerate(text.splitlines()) if "setx" in line]
    assert not offenders, (
        "these screens offer a shell command as the only recovery path for a "
        f"missing key, with no mention of Admin -> Provider keys: {offenders}")


# ---- money: one owner, and the frame travels with the value -----------------


_CURRENCY_WORD = re.compile(r"\bUSD\b")


def rendered_currency_in_python(text: str):
    """Yield `(line, why)` for each f-string that renders a currency figure.

    CQ-43, carried from report 027 to report 079. The Python half of the money
    guard tested `"${" in line` — the shape TypeScript renders a dollar in.
    Python names its currency in words, so the four sites that actually
    rendered money here (`app.py` twice, `expert.py` twice) never matched it,
    and neither would any new one.

    Parsed rather than grepped, for a reason this repo has already paid for
    twice — `rendered_dollars` above records that no regex could read the
    TypeScript, and the same trap is here in a smaller form. `app.py:188`'s
    docstring reads "USD 2.18 — a number covering 14 rows" and `:219`'s comment
    reads "`USD n` rather than `$n`": both are prose *about* a money figure and
    a line-wise search calls them renderings. The AST separates them for free —
    a docstring is a `Constant` and a comment is not in the tree at all — so
    what is enumerated is f-strings that interpolate a value, which is the only
    shape that can render one.

    Two markers, because the two failure modes are different. A currency named
    in the literal text beside an interpolated value is the shape all four
    carried sites use. A `$` immediately before a replacement field is the
    shape TypeScript uses, kept so a Python file borrowing it still fails.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:            # a file this guard cannot read is
        yield (exc.lineno or 1, "unparseable")     # not a file it may pass
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        parts = node.values
        if not any(isinstance(p, ast.FormattedValue) for p in parts):
            continue
        literal = "".join(p.value for p in parts
                          if isinstance(p, ast.Constant)
                          and isinstance(p.value, str))
        if _CURRENCY_WORD.search(literal):
            yield node.lineno, "a currency named beside a rendered value"
            continue
        if any(isinstance(a, ast.Constant) and isinstance(a.value, str)
               and a.value.endswith("$") and isinstance(b, ast.FormattedValue)
               for a, b in zip(parts, parts[1:])):
            yield node.lineno, "literal $ before a value"


def rendered_dollars(text: str, skips: list | None = None):
    """Yield `(line, why)` for each literal `$` that reaches a rendered surface.

    **No regex can do this, and the previous guard's could not.** It tested
    `"$${" in line`, which describes money built inside a *template literal* —
    the shape `money()` itself uses, where `$$` is how one literal dollar is
    written. Every site it was meant to catch is the other shape: a single `$`
    in JSX text, where `${x}` renders a dollar followed by the value. The two
    are identical character sequences in different contexts, so the guard could
    match none of the four defects the round-026 audit named, and it scanned
    neither `*.ts` nor Python, where one of the four lives.

    So this walks characters and tracks context on a stack. Two dead ends are
    recorded here rather than left to be rediscovered:

    - **Per-line backtick parity does not work.** Template literals nest and
      span lines. Parity called five correct sites offenders, among them
      ``selection.tsx``'s ``#/sites/${id}${m[1] ?? ""}${tail ? `?${tail}` : ""}``.
    - **Regex literals must be skipped.** `markdown.tsx:74` is ``/[#*`]/g`` —
      one unescaped backtick inside a character class. Treated as source text
      it flips the stack for the rest of the file, and that single character
      produced thirteen false offenders on its own.
    """
    stack: list[str] = []              # "`" template text, "{" its expression
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        in_tpl = bool(stack) and stack[-1] == _BQ
        if not in_tpl:
            if text.startswith("//", i):
                nxt = text.find(_NL, i)
                if nxt < 0:
                    # Recorded before the early return, or a `$USD` in a
                    # trailing comment would be the one span nobody skipped.
                    if skips is not None:
                        skips.append(("comment", i, n))
                    return
                if skips is not None:
                    skips.append(("comment", i, nxt))
                i = nxt
                continue
            if text.startswith("/*", i):
                end = text.find("*/", i)
                j = (end + 2) if end > 0 else n
                if skips is not None:
                    skips.append(("comment", i, j))
                i = j
                continue
            if c == "/" and _opens_regex(text, i):
                j = _skip_delimited(text, i, "/", classes=True)
                if skips is not None and j is not None:
                    skips.append(("regex", i, j))
                i = j if j is not None else i + 1
                continue
            if c in "'\"":
                j = _skip_delimited(text, i, c, classes=False)
                if skips is not None and j is not None:
                    skips.append(("string", i, j))
                i = j if j is not None else i + 1
                continue
        if c == "\\":
            i += 2
            continue
        if c == _BQ:
            stack.pop() if in_tpl else stack.append(_BQ)
            i += 1
            continue
        if c == "$":
            if in_tpl and text.startswith("$${", i):
                yield _line_no(text, i), "money built inline"
                i += 3
                continue
            if text.startswith("${", i):
                if in_tpl:
                    stack.append("{")             # ordinary interpolation
                    i += 2
                else:
                    yield _line_no(text, i), "literal $ before a value"
                    i += 2
                continue
        if c == "{" and stack and stack[-1] == "{":
            stack.append("{")
        elif c == "}" and stack and stack[-1] == "{":
            stack.pop()
        i += 1


#: A literal `$` spelling a **currency** rather than printing before a value.
#: `rendered_dollars` above cannot see either shape, and that is not an
#: oversight in it — it walks to `$` and asks what follows, and it only yields
#: when what follows is `{`. So `$USD` (a dollar inside a word) and `$/M`
#: (a dollar inside a quoted attribute, which that scanner skips wholesale)
#: both pass it by construction.
#:
#: UI-20 is what that costs. Every figure the dashboard draws reads `USD 3.00`
#: through the owner, and the Admin card heading above those very cells read
#: `Model prices - $USD per million tokens` with `input $/M` and `output $/M`
#: beneath it: one card, one currency, two spellings. The confirming check
#: recorded in `OPERATOR_ACTIONS.md` for that round was a regex for `$`
#: followed by digits, which by construction could not see either.
#:
#: Regex end-anchors are the whole reason this needs the scanner's span
#: bookkeeping rather than a bare regex of its own: `/[#*`]/g`-style literals
#: put `$/` in `markdown.tsx` fourteen times, `selection.tsx` twice and
#: `home.tsx` once, and every one of them is correct code.
_CURRENCY_SPELLING = re.compile(r"\$(?=[A-Za-z/])")


def currency_words(text: str):
    """Yield `(line, why)` for each literal `$` naming a currency in a label.

    Strings are deliberately **in** scope here and out of scope in
    `rendered_dollars`: a placeholder is a quoted string that an operator
    reads, so the shape this looks for lives exactly where that one stops.
    Comments and regex literals are out — a `$` in either reaches nobody.
    """
    skips: list = []
    list(rendered_dollars(text, skips=skips))
    dead = [(a, b) for kind, a, b in skips if kind in ("regex", "comment")]
    for m in _CURRENCY_SPELLING.finditer(text):
        i = m.start()
        if any(a <= i < b for a, b in dead):
            continue
        word = text[i:i + 6].splitlines()[0]
        yield _line_no(text, i), f"literal $ spelling a currency: {word!r}"


def test_no_label_spells_the_currency_its_own_way():
    """The frame clause applied to the label, not only to the figure.

    `test_the_money_formatter_states_its_currency` asserts the owner names the
    currency on every value it formats. It says nothing about the headings and
    placeholders sitting beside those values, and UI-20 is the residue: a card
    whose cells read `USD 3.00` under a heading reading `$USD`.

    Enumerated from source rather than from the two sites the round knew
    about — the new guard's own docstring that round recorded that "the two
    sites spelling it the other way are both prose", which is a list of three
    and a hard-coded list of three is how a partial fix passes.
    """
    offenders: dict[str, list[str]] = {}
    for path in sorted(SRC.glob("*.tsx")) + sorted(SRC.glob("*.ts")):
        if path.name == "components.tsx":
            continue                              # the owner
        hits = [f"{ln} ({why})" for ln, why
                in currency_words(path.read_text(encoding="utf-8"))]
        if hits:
            offenders[path.name] = hits

    assert not offenders, (
        "these spell the currency at the call site instead of naming "
        f"MONEY_CURRENCY, so one card can spell it two ways: {offenders}")


#: One case per shape, on the same reasoning as `_SHAPES` below: two previous
#: versions of the sibling scanner shipped green while blind, and a list is the
#: only form in which "which shapes did you check" has an answer.
_CURRENCY_SHAPES = [
    ('<h4>Model prices - $USD per million tokens</h4>',
     True, "a currency word in JSX text"),
    ('<input placeholder="input $/M" />',
     True, "a currency abbreviation inside a quoted attribute"),
    ('<td className="num">${p.input_usd}</td>',
     False, "an interpolation — rendered_dollars owns this shape"),
    ("const re = /[#*`]/g;",
     False, "a backtick class in a regex, no dollar at all"),
    (r"const tail = s.replace(/\?.*$/, '');",
     False, "a regex end-anchor before the closing delimiter"),
    ("// prices are quoted $USD per million",
     False, "a line comment nobody renders"),
    ("/* $USD, historically */",
     False, "a block comment nobody renders"),
    ('<div>{`${MONEY_CURRENCY}/M`}</div>',
     False, "the currency named through the owner"),
]


@pytest.mark.parametrize("src,expected,label", _CURRENCY_SHAPES,
                         ids=[s[2] for s in _CURRENCY_SHAPES])
def test_the_currency_scanner_classifies_each_shape(src, expected, label):
    assert bool(list(currency_words(src))) is expected, label


#: Shapes the scanner must classify correctly, with the answer beside each.
#: Written as data because the previous two versions of this guard were each
#: defeated by one shape nobody had listed, and a list is the only form in
#: which "which shapes did you check" has an answer.
_SHAPES = [
    ('<td>{x}</td><td className="num">${p.input_usd}</td>',
     True, "a money cell after a JSX closing tag"),
    ("<span>you haven't spent ${cost.toFixed(2)}</span>",
     True, "a money figure after an apostrophe in JSX prose"),
    ('<td className="num">${p.input_usd}</td>',
     True, "a money cell with nothing before it"),
    ("<div>{`total ${n}`}</div>",
     False, "an ordinary interpolation in a template literal"),
    ("<div>{`$${money}`}</div>",
     True, "money built inline in a template literal"),
    ("const re = /[#*`]/g; const s = `${a}`;",
     False, "a backtick inside a regex character class"),
    ("// a comment mentioning ${x}",
     False, "a line comment"),
    ("/* a block comment\n   mentioning ${x} */",
     False, "a block comment spanning lines"),
    ('const u = `#/sites/${id}${m[1] ?? ""}${t ? `?${t}` : ""}`;',
     False, "nested template literals on one line"),
]


@pytest.mark.parametrize("src,expected,label",
                         _SHAPES, ids=[s[2] for s in _SHAPES])
def test_the_money_scanner_classifies_each_shape(src, expected, label):
    """One case per shape, because the count is the coverage claim.

    Two previous versions of this guard shipped green while blind. The first
    matched `"$${" in line`, which is the template-literal shape, and every
    defect it was written for was the JSX-text shape. The second treated `<`
    as able to precede a regex, so every closing tag `</…>` opened a scan that
    ran to end of line: measured by injection, 1,489 of 9,519 scanned lines
    were never examined past their first closing tag, and an apostrophe in
    prose did the same thing.

    Both failures are one failure — a guard whose matching is weaker than the
    thing it matches, and no list of what it had actually been tried against.
    """
    assert bool(list(rendered_dollars(src))) is expected, label


def test_no_string_or_regex_skip_ever_consumes_a_line_ending():
    """The scanner reports what it skipped, and the skips are checked.

    This is the coverage claim made checkable rather than asserted. Deciding
    what opens a string or a regex needs the grammar and this has a heuristic,
    so the question is not whether the heuristic is ever wrong — it is — but
    whether being wrong can silently eat content. A string or regex that runs
    past a line ending was never one: JavaScript has no multi-line string
    literal without a backtick, and no multi-line regex at all. So a skip that
    crosses a newline is a misread opener, and it is exactly how 1,489 lines
    went unexamined while the guard reported nothing wrong.

    `_skip_delimited` now returns None instead, and the caller rewinds and
    treats the character as ordinary text. This asserts that across every file
    the guard actually scans, in one pass rather than by injection — the
    injection probe that found the defect costs 36 seconds and this costs
    milliseconds.
    """
    offenders: list[str] = []
    for path in sorted(SRC.glob("*.tsx")) + sorted(SRC.glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        skips: list = []
        list(rendered_dollars(text, skips))
        for kind, start, end in skips:
            # A block comment is the one span that legitimately runs
            # past a newline, so the argument above does not reach it:
            # JavaScript has no multi-line string and no multi-line
            # regex, and it does have `/* ... */`. Excluded by what the
            # span opens with rather than by its kind, because a `//`
            # comment ends AT the newline and is held to the same bar
            # as a string — the kind alone cannot tell the two apart.
            #
            # The population under test is unchanged from before
            # comment spans were recorded at all. This keeps the
            # guard's scope constant while a kind is added beside it,
            # which is not the same as narrowing it to reach green.
            if kind == "comment" and text.startswith("/*", start):
                continue
            if "\n" in text[start:end]:
                offenders.append(
                    f"{path.name}:{text.count(chr(10), 0, start) + 1} "
                    f"({kind} skip spans {text.count(chr(10), start, end)} "
                    "line ending(s))")

    assert not offenders, (
        "a string or regex skip crossed a line ending, so its opener was "
        f"misread and everything after it went unexamined: {offenders[:8]}")


def test_every_money_figure_goes_through_one_formatter():
    """Fourteen — in fact fifteen — sites hard-coded a dollar sign.

    Two local helpers disagreed on sub-dollar precision (`schedule.tsx` showed
    `12c`, `expert.tsx` showed `12.3c`) and the inline sites disagreed on
    scale (`.toFixed(2)` on six screens, `.toFixed(4)` on the run-detail cost
    log), so the same cost read differently depending on which screen you were
    on. First named at audit 001 and carried eighteen rounds.

    Enumerated from source rather than from a list of known sites, so a new
    screen that reaches for `$` fails this rather than joining the count — and
    enumerated across all three languages that render one, because the version
    of this guard that scanned only `*.tsx` for only one of the two shapes was
    green while four sites rendered money it could not see.
    """
    offenders: dict[str, list[str]] = {}
    for path in sorted(SRC.glob("*.tsx")) + sorted(SRC.glob("*.ts")):
        if path.name == "components.tsx":
            continue                              # the owner
        hits = [f"{ln} ({why})" for ln, why
                in rendered_dollars(path.read_text(encoding="utf-8"))]
        if hits:
            offenders[path.name] = hits

    # Python renders money too: the budget warning reaches the operator through
    # `/api/admin`, and no amount of TypeScript scanning was ever going to see
    # it.
    #
    # CQ-43. The version of this loop looked only for `${` inside an f-string,
    # which is the absence of a dollar sign and not the presence of a
    # formatter. Python names its currency in words — `f"USD {cost:.2f}"` —
    # so four sites rendered money in front of this assertion for fifty-two
    # reports without ever reddening it. What the test is named for is that a
    # currency figure has one owner, so the enumeration is of currency figures
    # and not of one spelling of one of them.
    py_root = SRC.parents[1] / "clauditseo"
    for path in sorted(py_root.rglob("*.py")):
        if path.name == "money.py":
            continue                              # the owner
        hits = [f"{ln} ({why})" for ln, why
                in rendered_currency_in_python(path.read_text(encoding="utf-8"))]
        if hits:
            offenders[str(path.relative_to(py_root.parent))] = hits

    assert not offenders, (
        "these render money without going through the shared formatter, so "
        "the currency and the precision are decided at the call site: "
        f"{offenders}")


def test_the_money_formatter_states_its_currency():
    """The frame clause: a figure's currency travels with the value.

    Costs are recorded in USD and, as of the 16 August decision, are never
    converted — so the currency is not implied by a setting and has to be on
    the figure. An en-AU operator reading `$412.80` has nothing telling them
    which dollar it is.
    """
    src = (SRC / "components.tsx").read_text(encoding="utf-8")
    assert "export function money(" in src, (
        "components.tsx does not export a money formatter")
    assert 'MONEY_CURRENCY = "USD"' in src, (
        "the currency constant is missing or is not USD")
    # The currency has to be in what the formatter *returns*, not merely
    # somewhere in the file. Checked against the constant rather than the
    # literal, so naming the currency once stays the point.
    body = src.split("export function money(", 1)[1].split("\n}", 1)[0]
    assert "MONEY_CURRENCY" in body, (
        f"the money formatter does not put a currency on the value: {body!r}")


def test_the_python_money_formatter_states_its_currency():
    """The same frame clause, on the side that had no formatter at all.

    Asserted by calling it, not by reading it. The TypeScript sibling above
    has to read source because pytest cannot run TypeScript; this one can
    import the module, so what it checks is the string an operator gets rather
    than the presence of a constant in a file.
    """
    from clauditseo.money import MONEY_CURRENCY, money

    assert MONEY_CURRENCY == "USD"
    rendered = money(2.18)
    assert MONEY_CURRENCY in rendered, (
        f"the Python money formatter does not name its currency: {rendered!r}")
    assert "2.18" in rendered, rendered


def test_a_sub_cent_price_does_not_render_as_free():
    """CQ-43's measurable half: two decimal places called 0.0004 free.

    All four Python sites formatted at `:.2f`, and one of them — `app.py`'s
    `available_briefs[].price` — is the string the dispatcher model reads when
    it chooses which brief to spend on. A brief costing USD 0.0004 was offered
    to that model, and to the operator on the tools screen, as `USD 0.00`.

    The table is the measurement, not the rule restated: 0.0004 keeps four
    places, 0.12 keeps two, a genuine zero stays `0.00` rather than becoming
    `0.0000`, and a budget cap keeps its thousands separator.
    """
    from clauditseo.money import amount, money

    assert money(0.0004) == "USD 0.0004"
    assert money(0.12) == "USD 0.12"
    assert money(0.0) == "USD 0.00"
    assert money(2.185) == "USD 2.19"
    assert amount(1234.5) == "1,234.50"


NODE = shutil.which("node")

#: The values the two owners are compared over. Each row separates the two
#: implementations or pins a rule one of them decides: `0.0004` is the
#: sub-cent rule CQ-43 measured, `0.0` is the boundary that rule deliberately
#: excludes, `2.185` is a rounding tie the two already agreed on, and
#: `1234.5`, `1234567.891` and `-1234.5` are the thousands separator - the
#: disagreement `money.py`'s own docstring called deliberate.
MONEY_VALUES = (0.0004, 0.005, 0.12, 0.0, 2.185, 1234.5, 1234567.891, -1234.5)


def _typescript_money(values):
    """Run the TypeScript owner's own source and return what it produces.

    Executed rather than read, which is the whole point. CQ-168 was carried
    from report 081 to report 084 underneath two guards that read both owners
    and asserted each named a currency - and two implementations can both name
    USD while spelling the figure differently. Reading source can only check
    the property somebody thought to write down; running it compares the text.

    The block is lifted from `components.tsx` and stripped of its type
    annotations rather than re-implemented here. A re-implementation is the
    failure DISCIPLINE rule 5 names: it would be a third opinion about the
    rule, and it would agree with whichever side wrote it.

    `node` ships on the GitHub-hosted runner images without `setup-node`, so
    the skip is for an exotic environment rather than for CI.
    """
    src = (SRC / "components.tsx").read_text(encoding="utf-8")
    start = src.index("export const MONEY_CURRENCY")
    end = src.index("\n}", src.index("export function moneyPair")) + 2
    block = src[start:end].replace("export ", "")
    block = re.sub(r":\s*(?:number|string)", "", block)
    driver = block + (
        "\nconst vs = " + json.dumps(list(values)) + ";\n"
        "process.stdout.write(JSON.stringify({\n"
        "  money: vs.map(money),\n"
        "  pair: moneyPair(vs[5], vs[6]),\n"
        "  currency: MONEY_CURRENCY }));\n")
    out = subprocess.run([NODE, "-e", driver],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (
        "the money block lifted from components.tsx did not run, so this "
        "guard is measuring its own extraction rather than the formatter: "
        f"{out.stderr}")
    return json.loads(out.stdout)


@pytest.mark.skipif(NODE is None, reason="needs node to run the TypeScript owner")
def test_the_two_money_owners_spell_a_figure_the_same_way():
    """CQ-168: one card printed one month's spend in two spellings.

    `admin.tsx` paints the server's budget warning at `:899` and the same
    month through the TypeScript owner four lines below, so `USD 2.18` and
    `$2.18 USD` land within four lines of each other on the Spend card. Both
    owners passed every guard beside them, because those guards enumerate each
    language separately and `continue` past "the owner" - singular - twice.
    What they assert is that no *third* site formats money. That the two
    exempted owners agree was never asserted by anything.

    Measured before the fix, over the table above: three disagreements, not
    one. The currency word moved from prefix to suffix; TypeScript's `amount`
    put a `$` on the number half where Python's returns the digits alone; and
    Python grouped thousands where TypeScript did not. Rounding agreed - both
    give `2.19` for `2.185` - which is why that row stays in the table rather
    than being dropped as uninteresting.

    The separator was recorded at `money.py:47-51` as a deliberate divergence,
    justified by the two sides rendering different populations: "the figures
    here include a monthly budget cap, which an operator sets in hundreds or
    thousands." `admin.tsx:913` renders `cap_usd` through the *TypeScript*
    owner. The population split that justification rests on does not hold at
    the one screen that draws both, so it is closed rather than kept.

    Which spelling won is not a taste call and is recorded here so it is not
    re-argued. `test_the_money_formatter_states_its_currency` already holds
    the reason: "An en-AU operator reading `$412.80` has nothing telling them
    which dollar it is." `$` is the ambiguous token and `USD` the informative
    one, so `$2.18 USD` leads with the half that cannot be read. Cost pointed
    the same way: eight assertions in this tree pin the prefix spelling and
    the two sites spelling it the other way are both prose.
    """
    from clauditseo.money import MONEY_CURRENCY, money

    ts = _typescript_money(MONEY_VALUES)

    assert ts["currency"] == MONEY_CURRENCY, (
        "the two owners do not even name the same currency: "
        f"{ts['currency']!r} against {MONEY_CURRENCY!r}")

    disagree = {v: (py, js) for v, py, js
                in zip(MONEY_VALUES, (money(v) for v in MONEY_VALUES),
                       ts["money"]) if py != js}
    assert not disagree, (
        "the Python and TypeScript money owners spell the same value "
        "differently, so one figure reads two ways depending on which side "
        f"of the wire drew it: {disagree}")


@pytest.mark.skipif(NODE is None, reason="needs node to run the TypeScript owner")
def test_a_money_pair_carries_the_currency_in_the_same_place():
    """The pair shares the contract, or the contract has an exception.

    `moneyPair` renders one currency for two numbers - a per-million-token
    price - and it is the only money shape Python does not have a twin for.
    That makes it the place a re-divergence would be cheapest to miss: nothing
    on the Python side would fail if it drifted back to a suffix. Asserted
    against a pair composed from the Python owner's own `amount`, so the
    expectation moves with the owner rather than with a literal written here.
    """
    from clauditseo.money import MONEY_CURRENCY, amount

    ts = _typescript_money(MONEY_VALUES)
    low, high = MONEY_VALUES[5], MONEY_VALUES[6]
    assert ts["pair"] == f"{MONEY_CURRENCY} {amount(low)}/{amount(high)}", (
        "the pair spells its currency differently from the single figure "
        f"beside it: {ts['pair']!r}")


def _without_comments(source: str) -> str:
    """A `.tsx` file's rendered text, with its commentary removed.

    Block comments first, which covers JSX's `{/* … */}` as well, then any
    line that is nothing but a `//` or a continuation `*`. Deliberately not a
    parser: this is used to decide whether a screen *composes* a sentence, and
    a `//` inside a string literal - a URL - cannot be mistaken for the clause
    being looked for, so the cheap version has no failure mode here that the
    expensive one would fix.
    """
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return "\n".join(line for line in source.splitlines()
                      if not line.lstrip().startswith(("//", "*")))


def test_the_priced_entries_frame_has_one_owner():
    """UI-19: the same caveat was an alarm on one screen and a footnote on two.

    "n of m entries priced" is the frame clause on a dollar figure - the one
    sentence that says the number is a floor rather than a total. Three
    screens composed it themselves and each chose its own weight: Tools set
    it inside `<strong>` within `p.error`, as loud as the budget warning it
    qualifies; Home set it as a muted `Stat` note; Admin as a muted
    parenthetical. Nothing in `styles.css` carried a class for it, so there
    was no place the weight could be decided once.

    Enumerated from source rather than from the three screens report 084
    names, so a fourth screen reaching for the clause fails this rather than
    joining the count - the same reason
    `test_every_money_figure_goes_through_one_formatter` next door enumerates
    instead of listing. The literal is the whole clause and not a fragment of
    it, because a fragment matches prose about the clause as well as the
    clause itself.

    What this does NOT hold, said plainly rather than left to be assumed: it
    asserts one owner for the text, not one computed weight at render. The
    rendered half is
    `test_the_spending_screen_frames_its_money.py::test_the_frame_is_not_as_loud_as_the_warning_it_qualifies`,
    which reads the painted screen on the one of the three that was the
    outlier.

    **Comments are stripped first, and the dead end is worth recording.** The
    first version of this scanned the raw file and stayed red after all three
    screens had been converted, naming `tools.tsx` - whose remaining match is
    a comment at `:739` explaining where Admin draws the clause. A guard that
    cannot tell a screen composing a sentence from a comment describing one
    would be closed by rewording the comment, which teaches the next reader to
    write around the guard rather than to satisfy it. The population is what
    the screen renders, so that is what is scanned.
    """
    clause = "entries priced"
    offenders = {p.name for p in sorted(SRC.glob("*.tsx")) + sorted(SRC.glob("*.ts"))
                 if p.name != "components.tsx"
                 and clause in _without_comments(p.read_text(encoding="utf-8"))}
    assert not offenders, (
        "these screens compose the priced-entries frame themselves, so each "
        f"decides its own weight for one clause: {sorted(offenders)}")


def test_the_priced_entries_frame_has_a_class_that_styles_css_declares():
    """The weight has somewhere to be decided, and it is decided there.

    One owner for the text is only half of UI-19. If the owner renders a bare
    span the three call sites still inherit whatever surrounds them, which is
    exactly the alarm-on-one-screen defect with an extra function in front of
    it. So the owner has to name a class and the stylesheet has to declare it.

    Asserted against the class the owner actually uses rather than a literal
    written here, so renaming it moves both halves together or reddens this.
    """
    src = (SRC / "components.tsx").read_text(encoding="utf-8")
    assert "export function PricedFrame(" in src, (
        "components.tsx does not export an owner for the priced-entries frame")
    body = src.split("export function PricedFrame(", 1)[1].split("\n}", 1)[0]
    used = re.findall(r'className="([a-z0-9-]+)"', body)
    assert used, f"the priced-entries frame names no class: {body!r}"
    css = CSS.read_text(encoding="utf-8")
    undeclared = [c for c in used if f".{c}" not in css]
    assert not undeclared, (
        "the priced-entries frame names a class the stylesheet does not "
        f"declare, so its weight is still whatever surrounds it: {undeclared}")


def test_admin_does_not_promise_currency_conversion():
    """Conversion is closed won't-fix, and the screen still offered it.

    `audits/DISPOSITIONS.md` records the decision: client figures state the
    currency they were recorded in and are never converted. Admin still
    rendered a control labelled "Quote clients in" over a currency select,
    with copy reading "costs stay in USD until one is fetched" — a promise
    that a stored rate changes what the operator quotes. It does not, and now
    never will. Affordance invariant: a control that acts on nothing.
    """
    src = (SRC / "admin.tsx").read_text(encoding="utf-8")
    for promise in ("Quote clients in", "until one is fetched",
                    "No conversion needed"):
        assert promise not in src, (
            f"admin.tsx still promises conversion: {promise!r}")
