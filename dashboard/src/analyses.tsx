/**
 * One component for "an analysis you can run", used by every screen.
 *
 * The concept had four states and the dashboard had eight verbs for it —
 * `run`, `run all`, `run most`, `re-run`, `show`, `hide`, `open`,
 * `investigate` — across five screens, none of them sharing code. They
 * disagreed, and one disagreement cost money: a control that looked like it
 * opened a stored report re-ran it at full price instead.
 *
 * The server decides state, verb, type and price. This renders them.
 *
 * Two lanes rather than one list, because free and paid is the distinction an
 * operator most needs and the old layout hid it: reading something already
 * bought looked identical to buying something new. Making it the layout means
 * it cannot be misread.
 */
import { Working } from "./working";
import { SecondaryButton } from "./buttons";
import { ReactNode, useState } from "react";
import { api, useFetch } from "./api";
import { Card, ErrorNote, Loading, SpendMark, money, moneyPair } from "./components";
import { SpendButton, SpendTarget } from "./spend";
import { DerivedFigures, StoredBrief } from "./expert";
import { ReportView } from "./markdown";
import { useSelection } from "./selection";
import { Pill, Tone } from "./pill";

export type Analysis = {
  tool: string; name: string; phase: string; kind: string; does: string;
  /** triage | site | page | report | monitor — what kind of thing this is. */
  type: string;
  /** ready | running | needs_input | not_run — what is true of it now. */
  state: string;
  /** The single word this state gets. Chosen server-side so screens cannot
   *  invent their own. */
  verb: string;
  est_tokens?: number | null; est_cost?: number | null;
  /** The estimate at the model that would run it - the brief's default -
   *  and how long a run took (brief v4 Item 3f). */
  est_cost_default?: number | null; est_seconds?: number | null;
  /** Which model this brief would use, and the tier that decided it. The
   *  choice was invisible at launch, and it is the difference between 49
   *  usable observations and one platitude. */
  tier?: string; model?: string;
  /** The part this brief writes to and its label, and the catalogue's
   *  position - all from the prompt's own header (brief v10 step AD). */
  part?: string | null; part_label?: string | null; order?: number | null;
  inputs?: { key: string; label: string; required?: boolean }[];
  /** What a conforming brief asked instead of answering (brief v10 step
   *  AF): the run is `needs_input`, and these are shown. */
  questions?: string[];
  ran_at?: string; findings?: number; tokens?: number | null;
  cost?: number | null; worst?: string | null; truncated?: boolean;
};

/** One entry of Triage's own ranking (brief v17 step AX): a cluster, the
 *  four inputs its score is the sum of, and what moved since the last
 *  ranking. The inputs travel with the score because a rank an operator
 *  cannot argue with is a rank they have to take on trust. */
export type RankEntry = {
  rank: number; check: string; part?: string | null; node?: string | null;
  pages?: number; score?: number; why?: string;
  blocker?: boolean; quick_win?: boolean; moved?: string;
  inputs?: Record<string, number>;
};

export type Triage = {
  ran_at: string; from_run: string; stale: boolean; derivation: string;
  /** The brief's own order, where it gave one. A run made by the prompt
   *  this replaced has none and the derived `ranked` list below stands
   *  instead — a stored ranking does not become unreadable because the
   *  prompt that made it was retired. */
  ranking?: RankEntry[];
  /** The scoring model, verbatim from the brief, so the numbers beside
   *  each row can be checked against the rule that produced them. */
  model?: Record<string, string>;
  ranked: {
    check: string; severity: string; summary: string; category: string | null;
    /** Classified, because "run it" is wrong for two thirds of them: a sweep
     *  has no endpoint, and a tool that has already run should be read. */
    tools: { tool: string; name: string; type: string;
             action: "run" | "read" | "sweep" }[];
  }[];
};

/** A sidebar part with the briefs filed under it (brief v10 step AD). */
export type Part = { key: string; label: string; group: string; briefs: string[] };

export type Lanes = {
  ready: Analysis[]; available: Analysis[];
  /** The sidebar's parts in order, including those no brief writes to. */
  parts?: Part[];
  outstanding_cost: number | null; outstanding_tokens: number;
  /** How many checks the engine answers with no model at all (brief v17
   *  step AV5). The Analyse tile leads with it, because "13 not run" on
   *  its own reads as thirteen things wrong rather than as what is left
   *  after the free pass. */
  free_checks?: number;
  /** No measurement at all — never run here, so not even a token
   *  figure exists for it. */
  unestimated: number;
  /** Measured in tokens, but no dollar rate is configured. */
  no_dollar_rate: number;
  triage: Triage | null;
  /** What a single launch may be pointed at, with prices. */
  models?: { model: string; price: [number, number] | null }[];
  /** The batch total at the per-brief defaults, over what is not run and
   *  not page-scoped; and the input share the pricing assumes. */
  outstanding_cost_default?: number | null;
  /** The catalogue's batch, summed once on the server (item 180, e6).
   *
   *  `listed = count + need_page + needs_input + read`, and every reader draws
   *  the four separately rather than deriving one from the others. Before
   *  `needs_input` and `read` existed (audit F4, 2026-09-18) the head's three
   *  numbers summed to 22 under a total of 23, and `count` counted a row the
   *  Run-all button would not run. */
  batch?: {
    listed: number; count: number; cost: number | null; priced: number;
    need_page: number; needs_input: number; read: number;
    partless: { tool: string; name?: string | null; est_cost_default?: number | null }[];
  };
  input_share?: number;
};

const TYPE_TITLE: Record<string, string> = {
  triage: "Triage — reads the scoreboard and ranks what is worth buying. "
        + "Produces no findings about the site itself.",
  site: "Analyses the whole site from the stored crawl.",
  page: "Analyses one page — you choose which before it can run.",
  report: "Assembles what has already run into a client deliverable.",
  monitor: "Watches for change. Worth running repeatedly or not at all.",
};

const TYPE_LETTER: Record<string, string> = {
  triage: "T", site: "S", page: "P", report: "R", monitor: "M",
};

/** The circular type marker.
 *
 *  The letter carries the meaning and the ring makes it a marker rather than
 *  a coloured character — so both have to clear their thresholds. Measured:
 *  rings 3.28–4.60:1 against the surface (WCAG 1.4.11 wants 3:1), letters
 *  4.82–8.05:1 on their own tint. The first version failed all five rings at
 *  1.42–2.75:1, which would have left five differently-tinted blurs. */
export function TypeMark({ type }: { type: string }) {
  const letter = TYPE_LETTER[type] ?? "?";
  return (
    <span className={`ty ty-${type}`} title={TYPE_TITLE[type] ?? type}>
      <span aria-hidden="true">{letter}</span>
      <span className="sr-only">{TYPE_TITLE[type] ?? type}</span>
    </span>
  );
}

const tokens = (n?: number | null) =>
  n == null ? null : n >= 1000 ? `~${Math.round(n / 1000)}k` : `~${n}`;

export const price = (a: Analysis): string | null =>
  a.est_cost != null ? money(a.est_cost) : tokens(a.est_tokens);

/** "claude-sonnet-5" -> "sonnet-5". The family and version are what an
 *  operator is choosing between; the vendor prefix is the same on every
 *  option and only costs row width. The full id stays in the title. */
export const shortModel = (m: string) =>
  m.replace(/^claude-/, "").replace(/-\d{8}$/, "");

/** One row. The verb comes from the server; this never picks a word. */
export function AnalysisRow({ a, onAct, busy, extra, open,
                             models, picked, onPickModel }: {
  a: Analysis;
  onAct: (a: Analysis) => void;
  busy?: boolean;
  extra?: ReactNode;
  /** What this one launch may run on. Absent on screens that only read. */
  models?: { model: string; price: [number, number] | null }[];
  picked?: string;
  onPickModel?: (tool: string, model: string) => void;
  /** Its report is showing. The row that opened it is the natural way to
   *  shut it, so the verb flips rather than making the operator find the
   *  close button at the far end of a long report. */
  open?: boolean;
}) {
  const spends = a.state !== "ready";
  // not_run launches a model (paid); ready opens the stored report (nav).
  // The former third branch (neither) carried no tone; it now falls to nav
  // as the neutral default. FLAG: confirm the no-tone default is right.
  const actTone: Tone = a.state === "not_run" ? "action-paid"
    : a.state === "ready" ? "nav" : "nav";
  return (
    <div className={`arow arow-${a.state}`}>
      <TypeMark type={a.type} />
      <span className="arow-nm">
        {a.name}
        <small>
          {a.state === "ready" && a.ran_at
            ? `${a.ran_at.slice(0, 10)} · ${a.findings ?? 0} findings`
            : a.state === "running" ? "running now"
            : a.state === "needs_input" ? "needs context a crawl cannot supply"
            : a.tool}
        </small>
      </span>
      {a.truncated && (
        <Pill tone="state-regressed"
              title="The model hit its output cap; the report is incomplete">
          truncated
        </Pill>
      )}
      {/* A price appears only on a control that spends, so its presence is
          itself the signal that money is involved. */}
      {/* Stated where the money is committed, not discovered afterwards in
          the report header. `deep` and `fast` are the words the operator
          configures, so they are the words shown. */}
      {spends && a.tier && (
        <span className={`tier-chip tier-${a.tier}`}
              title={`The ${a.tier} tier. A fast model on a judgement-heavy `
                     + "analysis returns less for the same workflow."}>
          {a.tier}
        </span>
      )}
      {/* Chosen for this launch only. Pointing one brief at a bigger model
          to see whether it earns its price is a different decision from
          re-pointing every brief of that tier, which is Admin's. */}
      {spends && models?.length && onPickModel && a.model && (
        <select className="row-model" value={picked ?? a.model}
                aria-label={`model for ${a.name}`}
                title={"Runs this analysis on the chosen model, once. The tier "
                       + "default is set on Admin."}
                onChange={(e) => onPickModel(a.tool, e.target.value)}>
          {models.map((m) => (
            <option key={m.model} value={m.model}>
              {shortModel(m.model)}
              {m.price ? ` · ${moneyPair(m.price[0], m.price[1])}` : ""}
            </option>
          ))}
        </select>
      )}
      {/* Item 178: a row that spends is the spend control - its price on
          the button in words, held while it runs, confirmed before it fires.
          A row that opens a stored report stays the free nav control. */}
      {spends && !open ? (
        <SpendButton className="arow-act"
                     price={a.est_cost ?? a.est_cost_default ?? null}
                     busy={busy}
                     why={a.state === "running" ? "running now" : null}
                     confirm={{ title: `${a.verb[0].toUpperCase()}${a.verb.slice(1)} ${a.name}?`,
                                body: <><SpendTarget />
                                  <p>{a.does}</p>
                                  {picked && a.model && picked !== a.model && (
                                    <p>On {shortModel(picked)}, for this launch only.</p>
                                  )}</>,
                                action: `${a.verb[0].toUpperCase()}${a.verb.slice(1)}` }}
                     onSpend={() => onAct(a)}>
          {a.verb}
        </SpendButton>
      ) : (
      <Pill as="button" tone={actTone}
              disabled={busy} aria-busy={busy} onClick={() => onAct(a)}
              title={open ? "Close this report and bring the list back"
                : spends ? `${a.does}\n\nSpends ${price(a) ?? "tokens"}.`
                : `${a.does}\n\nOpens the stored report — costs nothing.`}>
        {/* `spends` is the same flag the price and tier chips gate on:
            state !== "ready". With the report open the verb is "close",
            which spends nothing. F-10 clause 2. */}
        {/* No mark: a row that spends is SpendButton above (item 178). */}
        {/* UX-66, and this was the worst of the class: the caption swapped to
            a bare ellipsis, so the control's accessible name became "…" —
            not merely a different name, but no name at all. The verb stays;
            the state is on `aria-busy` and said in the region below. Every
            caller passes `busy={busyTool === a.tool}`, so at most one row's
            region is ever non-empty. */}
        {open ? "close" : a.verb}
      </Pill>
      )}
      {/* Mounted unconditionally — a region inserted in the same render as
          its text gives assistive technology nothing to observe a change
          against. `views.tsx`'s `ReportView` is the house pattern. */}
      <span className="muted" role="status" aria-live="polite">
        {busy && <Working>{`${a.verb}…`}</Working>}
      </span>
      {extra}
    </div>
  );
}

/** The lanes payload for one audit, fetched once.
 *
 *  Exported so any screen can render the same rows from the same source.
 *  The lane layout suits the client screen, where free-vs-paid is the
 *  question; the workbench and the run page group by phase instead, and get
 *  the row, the state and the verb without the layout. */
export function useAnalyses(runId: string | null, tick = 0) {
  return useFetch<Lanes>(runId ? `/api/runs/${runId}/analyses` : null, tick);
}

/** A flat list of named analyses, in whatever grouping the caller already
 *  has. One component, so no screen invents its own verb again. */
export function AnalysisList({ lanes, tools, runId, onChanged }: {
  lanes: Lanes;
  /** Tool ids this group covers, in the caller's own order. */
  tools: string[];
  runId: string;
  onChanged?: () => void;
}) {
  /** A model chosen for one launch, keyed by tool. Not persisted: this is
   *  "run this brief on that model, once", which is a different decision
   *  from the tier default on Admin — trying Opus on a single brief should
   *  not silently re-point every future brief of that tier. */
  const [pickedModel, setPickedModel] = useState<Record<string, string>>({});
  const pick = (tool: string, model: string) =>
    setPickedModel((m) => ({ ...m, [tool]: model }));
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<{ tool: string; name: string } | null>(null);
  const [brief, setBrief] = useState<StoredBrief | null>(null);
  const [error, setError] = useState<string | null>(null);

  const byTool = new Map<string, Analysis>();
  for (const a of [...lanes.ready, ...lanes.available]) byTool.set(a.tool, a);
  const rows = tools.map((t) => byTool.get(t)).filter(Boolean) as Analysis[];
  if (!rows.length) return null;

  const read = async (a: Analysis) => {
    if (open?.tool === a.tool) { setOpen(null); setBrief(null); return; }
    setBusy(a.tool);
    try {
      // UX-03, the second of the two sites. Same shape, same owner — the
      // whole point of naming the type is that these two cannot now disagree
      // about which fields a stored brief has.
      const got = await api.get<StoredBrief>(
        `/api/runs/${runId}/expert/${a.tool}`);
      setBrief(got);
      setOpen({ tool: a.tool, name: a.name });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  const run = async (a: Analysis) => {
    setBusy(a.tool);
    try {
      await api.post(`/api/runs/${runId}/expert/${a.tool}`, {});
      onChanged?.();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  const ready = rows.filter((a) => a.state === "ready");
  return (
    <div className="alist">
      {error && <ErrorNote error={error} />}
      {/* Free first, in every grouping. The ordering is the same signal the
          lanes carry: what is already bought precedes what would spend. */}
      {ready.length > 0 && (
        <p className="muted alist-head">
          {ready.length} of {rows.length} already run — free to open
        </p>
      )}
      {rows.map((a) => (
        <AnalysisRow key={a.tool} a={a} busy={busy === a.tool}
                     models={lanes.models} picked={pickedModel[a.tool]}
                     onPickModel={pick}
                     onAct={(x) => (x.state === "ready" ? read(x) : run(x))} />
      ))}
      {open && (
        <Card>
          <div className="modal-head">
            <h4>{open.name}</h4>
            <SecondaryButton
                    onClick={() => { setOpen(null); setBrief(null); }}>close</SecondaryButton>
          </div>
          {brief?.report
            ? <>
                <DerivedFigures figures={brief.figures_to_verify}
                                flagged={brief.figures_flagged} />
                <ReportView source={brief.report} runId={runId ?? undefined} />
              </>
            : <p className="muted">This report was not retained.</p>}
        </Card>
      )}
    </div>
  );
}

