/** One clock (item 248): every date and time the dashboard prints goes
 *  through these three, and all three convert to the reader's local time.
 *
 *  The store holds instants with different offsets - a run's `started_at` is
 *  UTC, a precheck's `checked_at` carries the machine's own - and screens
 *  printed them by slicing the string: `iso.slice(0, 10)` is the UTC day of a
 *  run and the local day of a precheck. So one audit read "2026-09-29 06:09"
 *  on the Record and "2026-09-28" on Reports, one click apart, and a delete
 *  confirm named "the audit of 2026-09-28" from a button that said the 29th.
 *
 *  `tests/test_every_date_is_local_time.py` fails on a date sliced out of a
 *  string anywhere in `dashboard/src`. */

const pad = (n: number) => String(n).padStart(2, "0");

function instant(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? d : null;
}

/** `2026-09-29 06:09`, local. An em dash where there is no instant. */
export function stamp(iso: string | null | undefined): string {
  const d = instant(iso);
  return d ? `${day(iso)} ${clock(iso)}`.trim() : "—";
}

/** A value that is a day and not an instant: it has no time to convert, and
 *  parsing it as one (UTC midnight) would move it a day west of Greenwich. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/** `2026-09-29`, the local day. A date-only value is that day. */
export function day(iso: string | null | undefined): string {
  if (iso && DATE_ONLY.test(iso)) return iso;
  const d = instant(iso);
  return d ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` : "—";
}

/** `06:09`, the local time of day. Empty for a date-only value, which has
 *  none. */
export function clock(iso: string | null | undefined): string {
  if (iso && DATE_ONLY.test(iso)) return "";
  const d = instant(iso);
  return d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : "—";
}
