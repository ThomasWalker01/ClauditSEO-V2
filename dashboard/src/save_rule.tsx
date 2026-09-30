/**
 * How a surface saves, said on the surface (item 183, UI audit 10-6).
 *
 * Admin saved some selects on change with no word, some forms on an explicit
 * save, and the Schedule dialog explicitly while the Cadences grid - the same
 * fields - saved on change. No tab said which. One rule per surface, from the
 * registry, drawn under the surface's heading.
 */
import { entry, short } from "./glossary";

export function SaveRule({ kind, also }: { kind: "on-change" | "explicit"; also?: "on-change" | "explicit" }) {
  const text = short(entry(`save-${kind}`));
  return (
    <p className="muted save-rule" data-save={kind}>
      {text}
      {also && also !== kind && (
        <> {kind === "explicit" ? "The Cadences grid holds the same fields and saves as you pick them."
                                : "Each site's Schedule holds the same fields and saves when you press save."}</>
      )}
    </p>
  );
}
