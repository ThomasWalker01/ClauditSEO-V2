"""The deprecated button families (item 182, commit 3), as source idioms.

The audit's 54 families were computed looks in a browser. What a lint can hold
is the source that draws them, so each family here is the idiom that produced
one or more of those looks, with a pattern that finds it. A family is retired
by item 183's migration; until then its count may fall and never rise.

`count_all()` is the census: per family, per file.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: family -> (what it drew, the variant it becomes, pattern)
FAMILIES: dict[str, tuple[str, str, str]] = {
    "pill-button-free": ("green outlined pill that acts (save, copy, re-check)",
                         "SecondaryButton", r'<Pill\b[^>]*?as="button"[^>]*?tone="action-free"|<Pill\b[^>]*?tone="action-free"[^>]*?as="button"'),
    "pill-button-nav": ("blue pill-text that acts rather than navigates (read, close, inputs)",
                        "SecondaryButton", r'<Pill\b[^>]*?as="button"[^>]*?tone="nav"|<Pill\b[^>]*?tone="nav"[^>]*?as="button"'),
    "pill-link-nav": ("blue pill-text anchor",
                      "LinkButton", r'<Pill\b[^>]*?as="a"[^>]*?tone="nav"|<Pill\b[^>]*?tone="nav"[^>]*?as="a"'),
    "pill-primary": ("filled primary pill, stretched or lowercase by screen",
                     "PrimaryButton", r'<Pill\b[^>]*?tone="action-primary"'),
    "pill-paid-raw": ("amber pill outside SpendButton",
                      "SpendButton", r'<Pill\b[^>]*?tone="action-paid"'),
    "pill-danger-raw": ("red pill outside DangerButton",
                        "DangerButton", r'<Pill\b[^>]*?tone="action-danger"'),
    "linklike": ("underlined 16px text button (Schedule… on Cadences, back to site)",
                 "LinkButton or SecondaryButton", r'className="linklike'),
    "bare-button": ("unstyled <button>, the browser's own box",
                    "SecondaryButton", r'<button(?![^>]*(?:className|role="tab"))[^>]*>'),
    "bl-secondary": ("r7 outlined head secondary, as a raw element",
                     "SecondaryButton or LinkButton", r'<(?:button|a)\b[^>]*bl-secondary'),
    "anat-rerun": ("grey 10.56px uppercase ↻ RE-RUN, as a raw button", "SecondaryButton", r'<button\b[^>]*anat-rerun'),
    "catalogue-fab": ("r8 floating catalogue tab, as a raw button", "SecondaryButton", r'<button\b[^>]*catalogue-fab'),
    "ctx-jump": ("r999 3.2/10.4 Open site →, as a raw anchor", "LinkButton", r'<a\b[^>]*ctx-jump'),
}

#: Where a family's pattern is the variant's own definition, not a use.
DEFINITIONS = {"buttons.tsx", "spend.tsx", "confirm.tsx", "pill.tsx"}


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("//"))


def count_all() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {f: {} for f in FAMILIES}
    for p in sorted(SRC.glob("*.tsx")):
        if p.name in DEFINITIONS:
            continue
        text = _strip_comments(p.read_text(encoding="utf-8"))
        for fam, (_, _, pat) in FAMILIES.items():
            n = len(re.findall(pat, text, flags=re.S))
            if n:
                out[fam][p.name] = n
    return out


def totals() -> dict[str, int]:
    return {f: sum(by.values()) for f, by in count_all().items()}


if __name__ == "__main__":
    for fam, by in count_all().items():
        print(f"{fam:20} {sum(by.values()):4}  {dict(sorted(by.items(), key=lambda kv: -kv[1]))}")
