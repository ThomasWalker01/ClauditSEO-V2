/** How old a measurement is, said where it is shown (item 239 step 6).
 *
 *  One rule for every date on a screen: under the operator's warning age a
 *  date is muted, "measured 4 days ago"; from it, in the warning tone, "may
 *  be out of date", with the part's re-check beside it; from the out-of-date
 *  age, in the danger tone, "out of date". The two ages are the operator's,
 *  set in Admin and sent with each part (`age_thresholds`); the defaults are
 *  item 239's, 30 and 90 days.
 */
import { SecondaryButton } from "./buttons";
import { stamp } from "./client_lanes";

export type AgeThresholds = { warn_days: number; stale_days: number };
export type AgeTone = "fresh" | "warn" | "stale";

export const DEFAULT_AGES: AgeThresholds = { warn_days: 30, stale_days: 90 };

/** The registered tone classes (`glossary.json`): muted, near the limit,
 *  past the limit - the vocabulary every measured item already wears. */
const AGE_CLASS: Record<AgeTone, string> = {
  fresh: "muted", warn: "tone tone-warn", stale: "tone tone-bad",
};

const DAY = 86_400_000;

export function ageDays(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? Math.max(0, Math.floor((now - t) / DAY)) : null;
}

export function ageTone(days: number | null, th: AgeThresholds = DEFAULT_AGES): AgeTone {
  if (days === null) return "fresh";
  return days >= th.stale_days ? "stale" : days >= th.warn_days ? "warn" : "fresh";
}

/** "4 days", "7 weeks", "4 months", "2 years" - the unit a reader uses. */
export function ageWords(days: number): string {
  const n = (k: number, unit: string) => `${k} ${unit}${k === 1 ? "" : "s"}`;
  if (days < 14) return n(days, "day");
  if (days < 60) return n(Math.floor(days / 7), "week");
  if (days < 730) return n(Math.floor(days / 30), "month");
  return n(Math.floor(days / 365), "year");
}

/** "measured 4 days ago", "measured 7 weeks ago, may be out of date",
 *  "measured 4 months ago, out of date". */
export function measuredText(days: number, tone: AgeTone): string {
  const when = days === 0 ? "measured today" : `measured ${ageWords(days)} ago`;
  return tone === "stale" ? `${when}, out of date`
    : tone === "warn" ? `${when}, may be out of date` : when;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"];

/** A date as the range line says it: "18 Sept". */
export function dayOf(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? `${d.getDate()} ${MONTHS[d.getMonth()]}` : "—";
}

/** A measurement's age, in its tone, with the part's re-check beside it once
 *  it may be out of date. The exact stamp rides in the title. */
export function MeasuredAge({ iso, th, onRecheck }: {
  iso: string | null | undefined; th?: AgeThresholds | null; onRecheck?: () => void;
}) {
  const days = ageDays(iso);
  if (days === null) return null;
  const tone = ageTone(days, th ?? DEFAULT_AGES);
  return (
    <>
      <span className={`age age-${tone} ${AGE_CLASS[tone]}`} data-age={tone} title={stamp(iso)}>
        {measuredText(days, tone)}
      </span>
      {tone !== "fresh" && onRecheck && (
        <>{" "}<SecondaryButton className="age-recheck" onClick={onRecheck}>re-check</SecondaryButton></>
      )}
    </>
  );
}
