/** The operator's stated target locales, on the International part page
 *  (2026-10-03, after item 274).
 *
 *  The hreflang gate decides from the crawl alone whether a site has anything
 *  to declare, and on a one-locale crawl it says it does not apply - "two
 *  things would change this answer: a target locale you state under this
 *  analysis's inputs, or a second locale reached by a deeper crawl". The
 *  first of the two was an input no site-level screen collected: the inputs
 *  panel is mounted only in the page dossier. So the reason named a door that
 *  was not there.
 *
 *  It is stored on the site (`sites.target_locales`, migration 0074) rather
 *  than sent with one run, because the gate is re-derived on every read: a
 *  locale that rode along with one run would leave the gate saying "not
 *  applicable" over the analysis it had just let run. The analysis reads the
 *  same field as its `TARGET_LOCALES`.
 */
import { useId, useState } from "react";
import { api } from "./api";
import { SecondaryButton } from "./buttons";

export function TargetLocales({ siteId, stated, onSaved }: {
  siteId: string;
  /** What the record holds now, as the server normalised it. */
  stated: string | null;
  /** Re-reads the part, so the gate and the run control follow the save. */
  onSaved?: () => void;
}) {
  const [value, setValue] = useState(stated ?? "");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const id = useId();
  const dirty = value.trim() !== (stated ?? "");
  const save = async () => {
    setBusy(true);
    setNote(null);
    try {
      await api.put(`/api/sites/${siteId}`, { target_locales: value.trim() });
      setNote(value.trim() ? "Saved. The locale gate reads it from now on." : "Cleared.");
      onSaved?.();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="intl-target" onSubmit={(e) => { e.preventDefault(); if (dirty) void save(); }}>
      <label className="site-field" htmlFor={`${id}-in`}>
        <span className="sel-lbl">Target locales</span>
      </label>
      <div className="intl-target-row">
        <input id={`${id}-in`} className="input intl-target-input" value={value}
               placeholder="e.g. en-AU, en-GB, x-default" aria-describedby={`${id}-hint`}
               onChange={(e) => { setValue(e.target.value); setNote(null); }} />
        <SecondaryButton submit busy={busy} why={dirty ? null : "nothing to save"}>
          Save
        </SecondaryButton>
      </div>
      <p id={`${id}-hint`} className="muted intl-target-hint">
        The locales this site is meant to serve, as hreflang writes them. Stating any
        lifts the locale gate and the analysis runs for them; empty states none.
      </p>
      <span className="muted intl-target-note" role="status" aria-live="polite">{note ?? ""}</span>
    </form>
  );
}
