/**
 * The five button variants (item 182, UI audit pattern H, 11-7).
 *
 * The audit counted 1,860 controls in 76 looks and 54 shape families, with one
 * action drawn three or four ways: "Open the catalogue" as an outlined box, a
 * filled lane button and blue pill-text; Schedule as a primary box, a nav pill
 * and an underlined link. An operator cannot learn a shape-to-meaning rule when
 * every screen invents its own button. These are the rule:
 *
 *   primary    the screen's one main action - filled
 *   secondary  every other action that spends nothing - outlined at 3:1
 *   spend      costs money: the price on the label, confirmed first
 *   danger     cannot be undone, or takes something out of a count: confirmed
 *   link       goes somewhere and does nothing else
 *
 * One box for all five - radius, padding, type, a 24 px floor - so a variant is
 * told by its tone and never by its size. The tone for each is registered in
 * the glossary (`button-*`), and `#/buttons` draws every one of them.
 *
 * Held is not a sixth variant: any of the five with `why` is held - dashed,
 * `aria-disabled`, still focusable, the reason in text beside it. A native
 * `disabled` still passes through for the controls item 183 migrated as they
 * were; new code states a `why`.
 */
import {
  forwardRef, useId,
  type AnchorHTMLAttributes, type ButtonHTMLAttributes, type MouseEvent, type ReactNode,
} from "react";
import { goHandler } from "./nav";
import { Pill } from "./pill";
export { DangerButton, SpendButton } from "./spend";

type Common = {
  children?: ReactNode;
  /** Why it cannot be pressed now, drawn beside it; `null` when it can. */
  why?: string | null;
  busy?: boolean;
  className?: string;
  /** An accessible name where the visible label is shared by several rows. */
  label?: string;
};

type ButtonRest = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children" | "type"> & {
  /** Submits its form. */
  submit?: boolean;
};

function Held({ why, id }: { why: string | null | undefined; id: string }) {
  return why ? <span id={id} className="muted btn-why">{why}</span> : null;
}

function makeButton(variant: "primary" | "secondary", tone: "action-primary" | "action-secondary") {
  return forwardRef<HTMLButtonElement, Common & ButtonRest & { pressed?: boolean }>(
    function VariantButton({ children, why = null, busy = false, className = "", label, pressed,
                             onClick, submit = false, ...rest }, ref) {
      const id = useId();
      const held = busy || Boolean(why);
      return (
        <>
          <Pill as="button" type={submit ? "submit" : "button"} tone={tone} ref={ref as never}
                className={`btn btn-${variant}${className ? ` ${className}` : ""}`}
                aria-label={label ?? rest["aria-label"]} aria-busy={busy || rest["aria-busy"] || undefined}
                aria-pressed={pressed ?? rest["aria-pressed"]}
                aria-disabled={held || rest["aria-disabled"] || undefined}
                aria-describedby={why ? id : rest["aria-describedby"]}
                {...rest}
                onClick={(e: MouseEvent<HTMLButtonElement>) => {
                  if (held) { e.preventDefault(); return; }
                  onClick?.(e);
                }}>
            {children}
          </Pill>
          <Held why={why} id={id} />
        </>
      );
    });
}

export const PrimaryButton = makeButton("primary", "action-primary");
export const SecondaryButton = makeButton("secondary", "action-secondary");

/** Navigation only: an anchor, through `goHandler` unless the caller routes it
 *  itself, so a press on a link to the current place still lands. Never fires
 *  an action and never spends. */
export const LinkButton = forwardRef<HTMLAnchorElement, {
  children?: ReactNode; href: string; className?: string; label?: string;
  /** This is where the reader already is. */
  current?: boolean;
  /** The screen's main action is a place to go (the landing's next step): the
   *  primary variant, drawn as the link it is. */
  primary?: boolean;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "className" | "children" | "href">>(
  function LinkButton({ children, href, className = "", label, current = false, primary = false,
                       onClick, ...rest }, ref) {
    return (
      <Pill as="a" tone={primary ? "action-primary" : "nav"} href={href} ref={ref as never}
            className={`btn ${primary ? "btn-primary" : "btn-link"}${className ? ` ${className}` : ""}`}
            aria-label={label ?? rest["aria-label"]}
            aria-current={current ? "page" : rest["aria-current"]}
            {...rest}
            onClick={onClick ?? (href.startsWith("#") ? goHandler(href) : undefined)}>
        {children}
      </Pill>
    );
  });

/** The five, with the tone each is bound to (item 182, commit 2). The registry
 *  holds the meaning; this is the binding the reference page and the tests read. */
export const VARIANTS = [
  { variant: "primary", component: "PrimaryButton", tone: "action-primary", registry: "button-primary" },
  { variant: "secondary", component: "SecondaryButton", tone: "action-secondary", registry: "button-secondary" },
  { variant: "spend", component: "SpendButton", tone: "action-paid", registry: "button-spend" },
  { variant: "danger", component: "DangerButton", tone: "action-danger", registry: "button-danger" },
  { variant: "link", component: "LinkButton", tone: "nav", registry: "button-link" },
] as const;
