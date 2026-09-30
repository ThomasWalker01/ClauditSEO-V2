/**
 * `[TO CONFIRM: …]`, where the operator reads it (`FEATURES.md` F-05).
 *
 * A brief's unresolved questions are prose inside the report, so this is
 * rendered inline by the markdown renderer rather than gathered into a panel
 * beside it. A panel would have produced the one state the register rules
 * out: the item settled in the sidebar and still saying `[TO CONFIRM: …]` in
 * the sentence it belongs to, three paragraphs down.
 *
 * Which items name a runnable probe is decided by the server and read from
 * `GET /api/runs/{id}/probes`. Deciding it again here would put two
 * implementations of one rule in the app, and the way they would fail is a
 * button offering a measurement the API then refuses.
 *
 * Outside a brief there is no provider, the context is empty, and every
 * marker renders as plain text — which is what a client report wants: a
 * deliverable is read where nothing can be run.
 */
import { Working } from "./working";
import { SecondaryButton } from "./buttons";
import React from "react";
import { api, ApiError } from "./api";
import { Pill } from "./pill";

export type ConfirmItem = {
  text: string;
  probe: string | null;
  command: string | null;
  label: string | null;
};

export type ProbeResult = {
  probe_id: string;
  target: string;
  status: "measured" | "failed";
  value: string;
  source: string;
  created_at: string;
};

type Ctx = {
  items: Record<string, ConfirmItem>;
  results: Record<string, ProbeResult>;
  running: string | null;
  errors: Record<string, string>;
  run: (probeId: string) => void;
};

const EMPTY: Ctx = {
  items: {}, results: {}, running: null, errors: {},
  run: () => undefined,
};

const ProbeContext = React.createContext<Ctx>(EMPTY);

export function ProbeProvider({ runId, children }:
    { runId: string; children: React.ReactNode }) {
  const [items, setItems] = React.useState<Record<string, ConfirmItem>>({});
  const [results, setResults] = React.useState<Record<string, ProbeResult>>({});
  const [running, setRunning] = React.useState<string | null>(null);
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  /* On mount, and free. The whole point of storing a measurement against the
     run is that re-opening the brief shows the answer rather than offering to
     go and get it again — so the read has to happen before the first paint
     the operator sees, not on a click. */
  const reload = React.useCallback(() => {
    api.get<{ items: ConfirmItem[]; results: ProbeResult[] }>(
      `/api/runs/${runId}/probes`)
      .then((body) => {
        setItems(Object.fromEntries(body.items.map((i) => [i.text, i])));
        setResults(Object.fromEntries(
          body.results.map((r) => [r.probe_id, r])));
      })
      .catch(() => {
        /* Silent, deliberately. A brief whose probe index could not be read
           still renders every one of its items as [TO CONFIRM: …] — the
           state they were in before this feature existed. Nothing is
           claimed, so there is nothing to warn about. */
      });
  }, [runId]);

  React.useEffect(() => { reload(); }, [reload]);

  const run = React.useCallback((probeId: string) => {
    setRunning(probeId);
    setErrors((e) => { const n = { ...e }; delete n[probeId]; return n; });
    api.post<ProbeResult>(`/api/runs/${runId}/probes/${probeId}`, {})
      .then((result) => setResults((r) => ({ ...r, [probeId]: result })))
      .catch((err) => setErrors((e) => ({
        ...e,
        [probeId]: err instanceof ApiError ? err.message : String(err),
      })))
      .finally(() => setRunning(null));
  }, [runId]);

  const value = React.useMemo(
    () => ({ items, results, running, errors, run }),
    [items, results, running, errors, run]);

  return <ProbeContext.Provider value={value}>{children}</ProbeContext.Provider>;
}

/** One `[TO CONFIRM: …]` from a brief, in the sentence it was written in. */
export function ToConfirm({ text }: { text: string }) {
  const { items, results, running, errors, run } = React.useContext(ProbeContext);
  const item = items[text];
  const probe = item?.probe ?? null;
  const result = probe ? results[probe] : undefined;
  const failed = errors[probe ?? ""];

  /* Settled: the marker is replaced by the answer and where it came from.
     Only a `measured` result does this. A probe that timed out has confirmed
     nothing, and a confident sentence produced by a timeout is precisely
     what the marker exists to prevent — so a failed run leaves the item
     exactly as it was and offers the attempt again. */
  if (result && result.status === "measured") {
    return (
      <span className="confirmed" data-probe={probe}>
        <span className="confirmed-mark" aria-hidden="true">✓</span>
        <span className="confirmed-value">{result.value}</span>
        <span className="confirmed-source">
          {" "}— {result.source}, {when(result.created_at)}
        </span>
        {/* UX-66. Stable caption, state on `aria-busy`, words in the
            unconditionally-mounted region beside it — the convention
            `views.tsx`'s `ReportView` states in full. */}
        <button className="link-btn confirmed-again"
                disabled={running === probe} aria-busy={running === probe}
                onClick={() => probe && run(probe)}
                title={item?.command ?? undefined}>
          measure again
        </button>
        <span className="muted" role="status" aria-live="polite">
          {running === probe && <Working>Measuring again…</Working>}
        </span>
      </span>
    );
  }

  const marker = <span className="to-confirm-text">[TO CONFIRM: {text}]</span>;

  /* Nothing this product can measure. The item says what it said before, and
     offers nothing — the register's words are that the honesty is the
     feature, not the thing being removed. */
  if (!probe) return <span className="to-confirm">{marker}</span>;

  return (
    <span className="to-confirm to-confirm-runnable">
      {marker}
      {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
      {/* Item 178: one connection, no model - free, so not the paid tone. */}
      <SecondaryButton className="to-confirm-run"
              disabled={running === probe} aria-busy={running === probe}
              onClick={() => run(probe)}
              title={`Runs ${item?.command} against this site. `
                     + "Costs nothing — one connection, no model."}>
        measure: {item?.label}
      </SecondaryButton>
      <span className="muted" role="status" aria-live="polite">
        {running === probe && <Working>{`Measuring ${item?.label}…`}</Working>}
      </span>
      {result && result.status === "failed" && (
        <span className="to-confirm-failed">
          {" "}last attempt measured nothing: {result.value}
        </span>
      )}
      {failed && <span className="to-confirm-failed"> {failed}</span>}
    </span>
  );
}

function when(stamp: string): string {
  const at = new Date(stamp);
  return Number.isNaN(at.getTime()) ? stamp : at.toLocaleString();
}
