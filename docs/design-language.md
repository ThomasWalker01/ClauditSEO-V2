# ClauditSEO design language: controls

The rules every screen's controls follow. The live reference is the product's own
`#/buttons` route, which draws every variant with the product's stylesheet, in
both themes, live and held. The meanings are the glossary registry's
(`clauditseo/glossary.json`, vocabulary `button variants`); this page does not
restate them.

## Five button variants (item 182)

| Variant | Component | Tone | For |
|---|---|---|---|
| primary | `PrimaryButton` | `action-primary` | the screen's one main action |
| secondary | `SecondaryButton` | `action-secondary` | every other action that spends nothing |
| spend | `SpendButton` | `action-paid` | spends money; price on the label, confirmed |
| danger | `DangerButton` | `action-danger` | removes or uncounts; confirmed |
| link | `LinkButton` | `nav` | navigates only |

All five live in `dashboard/src/buttons.tsx` (spend and danger in `spend.tsx`).

- **One box.** Radius 7, 4px 12px, UI type size, 24px minimum. A variant is
  told by its tone, never by its size.
- **Held** is not a sixth variant: any variant with a `why` is `aria-disabled`,
  dashed, still focusable, with the reason in text beside it. Never a native
  `disabled` with the reason in a `title`.
- **Spend** states its price in words: a figure, "no estimate yet", or
  "checking the price" while the price is being read, which also holds it. The
  confirmation names what runs, the site, the audit, the pages and the price.
- **Danger** names what goes and what depends on it, and sits at least one row
  height (24px, `act-gap`) from any save beside it.
- **Edges** are `--edge`, 3:1 or better on every ground, in both themes.
  `--border` is a divider, never a control's only boundary.
- **Dialogs** use `useDialog` (`confirm.tsx`): focus moves in, Tab stays in,
  Escape closes, focus returns to the control that opened it.

## Deprecated families

The idioms that drew the audit's 54 button looks are listed in
`tests/button_families.py`, each with the variant it becomes. A lint
(`tests/test_buttons_are_five_variants.py`) fails on a new use of any of them;
item 183 migrates the existing ones.

## States

- **Loading** says the registered word `Loading` until the data for the current
  selection has arrived (item 179). No empty answer is drawn from a request that
  has not answered.
- **Nothing here** is one of three registered states (item 180): clean, not
  measured, cannot have findings. The line always says which, and why.
- **A hold is drawn where the work is, not in the chrome.** The client report's
  hold appears on the landing's button, the strip's Deliver chapter and Generate
  — the three places that act on the report — and not on the nav link that
  points at it. It was on the nav too until 2026-09-18, and four surfaces at
  once cost the words their meaning (the operator's decision). A rule for any
  state word that repeats: state it where it changes what the press does.

## The chrome holds one row's worth

The bar is one row above 1119px (item 174, measured) and two below it. Text
gives way before a control does — the site field shrinks, then the gaps — and
`flex: 1 1 auto` on the context is what lets it; with `1 0 auto` it could not
give at all.

**Wrapping is not a milder shrink.** A `nowrap` flex line shrinks its items
until the line fits; a `wrap` line sizes them from their content and moves what
will not fit to a second row. Switching the bar to `wrap` therefore stopped the
search giving way and put the nav on its own row at 1280 — tried and reverted
on 2026-09-18.

So nothing in the CSS prevents a too-full bar; a measurement does.
`test_the_chrome_fits_the_width_it_is_drawn_at` fails on any page that widens at
1440, 1366, 1280, 1200, 1120 or 1000px. Add a word to the bar and that guard is
what tells you it no longer fits — which is how item 178's 187px hold mark gave
every client screen 83px of sideways scroll from 1120 to 1386px, with Admin and
Glossary off the screen, against a green suite that only ever measured 320.
