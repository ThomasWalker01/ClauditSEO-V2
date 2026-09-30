/** One pill, one tone (item 140 — one tone per meaning).
 *
 *  A component takes a tone; it never owns a colour. Every pill, chip, badge,
 *  severity mark, state mark, provenance tag and small action in the dashboard
 *  is this component with a `tone` prop, and the colours live in the
 *  `--tone-*` block in styles.css. Before this, the same green meant free,
 *  enabled and a run button; the same amber meant Medium, open and a count.
 *  The tone names below are the meanings, and the stylesheet is the only place
 *  a meaning is bound to a colour.
 *
 *  Two axes, both fixed:
 *    fill  = a level or a count   (severity, count-*)
 *    outline = a state or an action (state-*, action-*, blocker, current, kind)
 *
 *  `as` picks the element: a span by default, `button` for a control, `a` for
 *  a link. The tone is the same whichever it is — an amber-outline `action-paid`
 *  reads the same as a button or as a link.
 */
import {
  forwardRef, Ref,
  ReactNode, HTMLAttributes, ButtonHTMLAttributes, AnchorHTMLAttributes,
} from "react";

export type Tone =
  // does something — outline, by cost (danger is by consequence, not cost)
  | "action-free" | "action-paid" | "action-primary" | "action-danger" | "nav"
  // every other action that spends nothing - neutral outline (item 182)
  | "action-secondary"
  // how bad — the only fills that may be red/amber/green severity hues
  | "sev-critical" | "sev-high" | "sev-medium" | "sev-low" | "sev-info"
  // where a finding is in its life — outline only
  | "state-open" | "state-regressed" | "state-fixed"
  | "state-candidate" | "state-withdrawn" | "state-accepted"
  // who found it — text, no fill
  | "source-brief" | "source-sweep"
  // needs an input to be judged — neutral grey fill
  | "held"
  // ranks above everything — red outline, once
  | "blocker"
  // how many — the only non-severity fills
  | "count-open" | "count-info" | "count-zero"
  // you are here — blue outline, wash
  | "current"
  // what kind of fix — green outline text chips
  | "template" | "pipeline" | "policy";

type Base = { tone: Tone; children?: ReactNode; className?: string };
type AsSpan = Base & { as?: "span" } & HTMLAttributes<HTMLSpanElement>;
type AsButton = Base & { as: "button" } & ButtonHTMLAttributes<HTMLButtonElement>;
type AsAnchor = Base & { as: "a" } & AnchorHTMLAttributes<HTMLAnchorElement>;
export type PillProps = AsSpan | AsButton | AsAnchor;

export const Pill = forwardRef<HTMLElement, PillProps>(function Pill(props, ref) {
  const { tone, as = "span", className, children, ...rest } = props;
  const cls = "tone tone-" + tone + (className ? " " + className : "");
  const Tag = as as "span" | "button" | "a";
  return (
    <Tag ref={ref as Ref<HTMLSpanElement & HTMLButtonElement & HTMLAnchorElement>}
         className={cls} {...(rest as HTMLAttributes<HTMLElement>)}>
      {children}
    </Tag>
  );
});
