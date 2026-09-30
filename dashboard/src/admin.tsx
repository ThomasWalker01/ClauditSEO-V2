import { SecondaryButton } from "./buttons";
import { Working } from "./working";
import { useEffect, useRef, useState } from "react";
import { goHandler } from "./nav";
import { AnalysisList, shortModel, useAnalyses } from "./analyses";
import { host, useSelection } from "./selection";
import { AuditScopeBar } from "./scope";
import { ApiError, api, useObjectUrl } from "./api";
import { DangerButton, SpendButton } from "./spend";
import { Pill } from "./pill";
import { applyBrandFavicon } from "./favicon";
import { CadenceGrid } from "./cadence";
import { SaveRule } from "./save_rule";
import { Card, ErrorNote, Loading, MONEY_CURRENCY, PricedFrame, money,
         moneyPair } from "./components";

type Provider = { configured: boolean; detail: string; env: string;
                  //: Whether "Provider keys" above can set this one. The
                  //: server decides; two screens guessing separately is how
                  //: they came to disagree.
                  managed: boolean;
                  //: "panel", "environment", or null when unconfigured.
                  source: "panel" | "environment" | null };
type BackupFile = { name: string; path: string; bytes: number; created_at: string };

type Admin = {
  version: string;
  engine_version: string;
  bundle: string | null;
  locale: string;
  auth_mode: string;
  providers: Record<string, Provider>;
  models: { fast: string; standard: string; deep: string };
  budgets: Record<string, number>;
  database: { path: string; bytes: number; wal_bytes: number;
              rows: Record<string, number> };
  backups: BackupFile[];
  restore_steps: string[];
  /** `priced` and `unpriced` split `entries` by whether the row carried a
   *  cost when it was written. `usd` is the sum over `priced` alone, so it
   *  is a floor whenever `unpriced` is non-zero. */
  spend: { month: string; client: string; tokens: number;
           usd: number | null; entries: number;
           priced: number; unpriced: number }[];
  /** Same frame, from the other aggregation of the same column. `month_usd`
   *  is null when the month has entries and none is priced. */
  budget: { month_tokens: number; month_usd: number | null;
            usd_entries: number; usd_unpriced: number;
            cap_tokens: number | null; cap_usd: number | null;
            warning: string | null };
  operators: { id: string; name: string; email: string | null; role: string;
               has_token: number }[];
};

function mb(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const TIER_PURPOSE: Record<string, string> = {
  fast: "applying a fixed checklist",
  standard: "analysis with judgement at the edges",
  deep: "where the judgement is the product",
};

type Rates = {
  display_currency: string;
  currencies: string[];
  rate: { rate: number; source: string; fetched_at: string | null;
          age_days: number | null; stale: boolean } | null;
  stored: { currency: string; rate: number; source: string;
            fetched_at: string }[];
  // `entered_by` was on the wire the whole time — the route selects `*` — and
  // this type dropped it, so the one screen that renders the ledger could not
  // show it. WF-33: the column had two writers and no reader, which is why
  // giving it a vocabulary at round 089 and fixing the second writer at CQ-200
  // both left the finding open. Nullable because sixteen rows on the live
  // install predate either write path and honestly have no answer.
  model_prices: { model: string; input_usd: number; output_usd: number;
                  entered_at: string; entered_by: string | null;
                  source: string; source_url: string | null }[];
  note: string;
  prices_url: string;
};

/** What a cost figure is built from, and how old each part is.
 *
 *  Two halves that behave differently on purpose. Exchange rates are fetched
 *  — the ECB publishes daily, free and without a key — so they carry an
 *  observation date and go stale. Model prices are not: no vendor publishes a
 *  machine-readable feed, and scraping a pricing page to produce a number that
 *  ends up in a client quote is how a quote goes wrong quietly. They are typed
 *  in, and dated so the operator can see when they last checked.
 *
 *  Until a price is entered every cost in the app is shown in tokens, which is
 *  the honest answer rather than a blank.
 */
function Money() {
  const [data, setData] = useState<Rates | null>(null);
  // UX-66. `busy` names the action rather than being a bare flag. Both
  // controls below share it, and each now carries its own live region — a
  // boolean would fill both regions on either press, announcing an action
  // nobody started. `busy === "cache"` at :1041 is this file's own idiom.
  const [busy, setBusy] = useState<"rates" | "prices" | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [model, setModel] = useState("");
  const [inUsd, setInUsd] = useState("");
  const [outUsd, setOutUsd] = useState("");

  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => api.get<Rates>("/api/rates").then((d) => { setData(d); setLoadError(null); })
    .catch((e: ApiError) => setLoadError(e.message));
  useEffect(() => { load(); }, []);

  const refresh = async () => {
    setBusy("rates"); setNote(null);
    try {
      const out = await api.post<{ ok: boolean; stored?: number;
                                   shown?: number;
                                   source?: string; error?: string }>(
        "/api/rates/refresh", {});
      // UX-70. This said `${out.stored} rates from ${out.source}.` and
      // `stored` is the write — every currency the feed sent — while the
      // list immediately below is `fx.reference_rates`, the display
      // currencies less the base. So the one sentence confirming what a
      // press did stated a count of rows the operator cannot see, directly
      // above the rows they can, and nothing said which was the answer. The
      // server now sends both; each is stated with the frame that makes it
      // readable, and neither is re-derived here.
      setNote(out.ok
        ? `Wrote ${out.stored} rates from ${out.source}.`
          + ` Listing ${out.shown} — the display currencies,`
          + ` less the ${MONEY_CURRENCY} base.`
        : `Not refreshed — ${out.error}. The stored rate is unchanged.`);
      load();
    } finally { setBusy(null); }
  };

  const fetchPrices = async () => {
    setBusy("prices"); setNote(null);
    try {
      const out = await api.post<{
        ok: boolean; stored?: number; kept?: string[]; error?: string;
        differs?: { model: string; yours: number[]; published: number[] }[];
      }>("/api/rates/fetch-prices", {});
      // A kept price that disagrees with the published one is said out loud.
      // Keeping it silently would rebuild the exact failure the lookup
      // exists to fix: a hand-typed number that is wrong and doesn't look it.
      const clash = (out.differs ?? []).map(
        (d) => `${d.model} — yours ${moneyPair(d.yours[0], d.yours[1])}, `
             + `published ${moneyPair(d.published[0], d.published[1])}`);
      setNote(out.ok
        ? `${out.stored} prices read from Anthropic's pricing page.`
          + (out.kept?.length
             ? ` Kept your own: ${out.kept.join(", ")}.` : "")
          + (clash.length
             ? ` These disagree with the published figure — ${clash.join("; ")}.`
               + " Remove yours to use the published one."
             : "")
        : `Not fetched — ${out.error}. Nothing changed.`);
      load();
    } finally { setBusy(null); }
  };

  const savePrice = async () => {
    if (!model.trim()) return;
    setNote(null);
    try {
      await api.put("/api/rates/model-price", {
        model: model.trim(), input_usd: Number(inUsd) || 0,
        output_usd: Number(outUsd) || 0 });
    } catch (err) {
      // The fields keep what was typed. Clearing them on a failed save threw
      // away the operator's work and left nothing on screen to explain why.
      setNote(`Not saved — ${err instanceof Error ? err.message : String(err)}.`);
      return;
    }
    setModel(""); setInUsd(""); setOutUsd("");
    await load();
  };

  if (!data) return loadError ? <ErrorNote error={loadError} onRetry={load} /> : <Loading />;
  // How much of the ledger cannot be attributed. A row at a time does not tell
  // an operator whether this is a stray or the whole table — on the install
  // this was found on it is sixteen of sixteen — and the count is what makes
  // removing them a decision rather than a discovery.
  const unattributed = data.model_prices.filter((p) => !p.entered_by).length;
  // `data.rate` is deliberately not read here any more. It answers for the
  // display currency, which is the recording currency, so its only value was
  // the identity WF-04 was about; the panel now renders `data.stored`, which
  // is what the button beside it actually writes. The field stays on the wire
  // because `rate_for` is the honest answer to "can we convert" and returns
  // null rather than 1.0 when it cannot — a distinction worth keeping at the
  // boundary even while no screen needs it.
  return (
    <Card>
      <h3>Money</h3>
      <p className="muted">{data.note}</p>

      <div className="money-row">
        {/* No currency selector. Costs are recorded in USD and stated in USD;
            they are never converted, decided 16 August 2026 and recorded in
            audits/DISPOSITIONS.md. The control here was labelled "Quote
            clients in" over a list of currencies and acted on nothing —
            `fx.convert` has no caller and no cost-bearing endpoint reads the
            stored preference — while the copy beside it promised costs would
            switch currency once a rate arrived — a conversion that was never
            coming. A control that acts on nothing is the affordance invariant;
            copy that promises behaviour the product has decided against is
            worse, because it is read as a plan.

            The reference rate stays. It is genuinely useful for an operator
            invoicing in their own currency by hand, and it is honest about
            being reference only. */}
        <span className="muted">
          Costs are recorded and shown in {MONEY_CURRENCY}, and are never
          converted — every figure carries its currency so it cannot be read
          as the wrong one.
        </span>
        {/* UX-66. The caption no longer swaps to a busy word. A button's
            label is its accessible name, so a name that changes mid-press is
            announced as a different control appearing — the convention
            `reports.tsx:270-289` set for UX-64 and `views.tsx`'s `ReportView` took for
            the report generate control. `aria-busy` carries the state the
            caption used to; the region below says it in words. */}
        <SecondaryButton disabled={!!busy}
                aria-busy={busy === "rates"} onClick={refresh}>
          refresh reference rates
        </SecondaryButton>
        {/* Mounted unconditionally: a live region inserted in the same render
            as its text gives assistive technology nothing to observe a change
            against, so it has to be here before there is anything to say. */}
        <span className="muted" role="status" aria-live="polite">
          {busy === "rates" && <Working>Fetching reference rates…</Working>}
        </span>
        {/* WF-04, and the reason this became a list of what was fetched
            rather than a sentence about one rate.

            `rate_for` answers for the *display* currency, and the display
            currency is the one costs are recorded in — CQ-16 records that no
            screen can change it, and the selector that once could was removed
            when conversion was closed won't-fix. So the only value this line
            could ever take was `Reference only: 1 USD = 1 USD · identity ·
            today`: a sentence whose grammar claims a conversion and whose
            content is that none happened. The server already says so in as
            many words — `rate_for` returns `source: "identity"` for the
            recording currency, and it was on the wire the whole time.

            What the button fetches was on the wire the whole time too, and
            rendered nowhere: `data.stored`, which is `refresh reference
            rates`' only output and which `grep -c data.stored` found zero
            readers for. Those rates are what the comment above says the
            reference rate is kept for, so they are what the panel shows. A
            control whose only output reaches no screen is the affordance
            invariant, and correcting the line without this would have left
            that comment stating something untrue.

            The date travels with each rate for the reason the old line
            already knew: a rate without its date is a number that silently
            becomes wrong. Formatted through `toLocaleDateString` rather than
            sliced off the ISO string, so it reads in the operator's locale
            — the en-AU contract UX-45 is open about elsewhere, not a fresh
            instance of it.

            Round 075: `data.stored` is no longer every row of `fx_rates`.
            The first press of the button beside this line brought the
            identity straight back — `fetch_rates` writes `rates["USD"] = 1.0`
            because the feed is USD-based, `store_rates` persists it, and this
            map rendered it as `1 USD = 1 USD` — and the row count was set by
            whichever of the two feeds answered. `fx.reference_rates` now
            drops the base row and bounds the rest by `CURRENCIES`, on the
            server, so no reader of the route has to remember either rule.
            Nothing is filtered here: a renderer that re-applies a server-side
            bound is how the two drift apart. */}
        <span className="muted">
          {data.stored.length
            ? "Reference only, for invoicing by hand: "
              + data.stored.map((x) =>
                  `1 ${MONEY_CURRENCY} = ${x.rate} ${x.currency}`
                  + ` (${x.source}, `
                  + `${new Date(x.fetched_at).toLocaleDateString()})`)
                .join(" · ")
            : "No reference rate stored yet."}
        </span>
      </div>
      {note && <p className="muted">{note}</p>}

      {/* One card, one spelling. Every cell below reads `USD 3.00`
          through the money owner; this heading and the two
          placeholders under it spelled the same currency `$USD` and
          `$/M` — UI-20, and CQ-168's own shape one layer out. The
          currency is named from `MONEY_CURRENCY` here for the same
          reason the figures are formatted there: so a card cannot
          disagree with itself, and so the next label added to it
          inherits the answer rather than deciding one. */}
      <h4 className="money-sub">
        Model prices · {MONEY_CURRENCY} per million tokens
      </h4>
      <div className="money-row">
        {/* UX-66, the same convention as the rates control above. */}
        {/* Item 178: this reads a public page and spends nothing, so it is not
            drawn as a spend - the paid tone is for controls that cost money. */}
        <SecondaryButton disabled={!!busy}
                aria-busy={busy === "prices"} onClick={fetchPrices}>
          read Claude prices
        </SecondaryButton>
        <span className="muted" role="status" aria-live="polite">
          {busy === "prices" && <Working>Reading Claude prices…</Working>}
        </span>
        <span className="muted">
          From the published pricing page. Your own entries are never
          overwritten.
        </span>
      </div>
      {data.model_prices.length === 0 ? (
        <p className="muted">
          None known yet, so every cost shows as tokens.
        </p>
      ) : (
        <table className="findings">
          {/* WF-33, and the reason this is a `<caption>` rather than a
              paragraph: `NarrowRunNote` is the standing precedent for a note
              that is about a table, and a table may have only one caption —
              this one had none, so nothing is displaced. Rendered text, not a
              `title` and not `sr-only`, per `BriefPriceFrame`'s docstring:
              the provenance invariant asks for a stated limit the operator
              reads, and "who put this number in my ledger" is unknown for
              every row that predates the column having a writer.

              Not a backfill. The obvious repair — writing `api:fetch-prices`
              into the empty rows — invents a provenance nobody observed, and
              a sentinel reads as an answer where NULL is honestly absent.
              Their `source` and `source_url` do record where the *figure*
              came from; what is missing is who caused the write. Both
              controls the note points at already exist directly above and
              beside it, so this states a limit the operator can act on rather
              than one they can only read. */}
          {unattributed > 0 && (
            <caption className="table-note">
              <strong>{unattributed} of {data.model_prices.length}</strong>{" "}
              {unattributed === 1 ? "price has" : "prices have"} no recorded
              author, so who stored {unattributed === 1 ? "it" : "them"} is not
              known. Read the published prices again to store them with one, or
              remove the row.
            </caption>
          )}
          {/* Source beside the figure: a price in a client quote has to be
              traceable, and "who said this" is the difference between a
              published rate and one somebody remembered. */}
          <thead><tr><th>Model</th><th className="num">Input</th>
                     <th className="num">Output</th><th>Source</th>
                     <th>Dated</th><th /></tr></thead>
          <tbody>
            {data.model_prices.map((p) => (
              <tr key={p.model}>
                <td><code>{p.model}</code></td>
                <td className="num">{money(p.input_usd)}</td>
                <td className="num">{money(p.output_usd)}</td>
                {/* Two facts, not one. `source` is where the figure came
                    from; `entered_by` is who caused the row to exist, and
                    they can disagree — a published price re-read through the
                    route reads `published · api:fetch-prices`. Painting only
                    the first is what made a row with no author read exactly
                    like one that has one. */}
                <td className="muted">
                  {p.source === "operator" ? "you" : "published"}
                  {" · "}
                  {p.entered_by ?? "no author recorded"}
                </td>
                <td className="muted">{p.entered_at.slice(0, 10)}</td>
                <td>
                  <DangerButton label={`remove the price for ${p.model}`}
                                confirm={{ title: `Remove the price for ${p.model}?`,
                                           body: <p>Every cost for {p.model} then shows as tokens,
                                             not money, on every site, until a price is set again.
                                             {p.source === "operator" ? " It was entered by you." : " It was read from the published page; reading prices again restores it."}</p>,
                                           action: "Remove the price" }}
                                onConfirm={async () => {
                                  await api.del(`/api/rates/model-price/${p.model}`);
                                  load();
                                }}>remove</DangerButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="money-row">
        <input className="input" placeholder="model id" value={model}
               aria-label="model id" onChange={(e) => setModel(e.target.value)} />
        <input className="input money-num" value={inUsd}
               placeholder={`input ${MONEY_CURRENCY}/M`}
               aria-label="input price per million tokens"
               onChange={(e) => setInUsd(e.target.value)} />
        <input className="input money-num" value={outUsd}
               placeholder={`output ${MONEY_CURRENCY}/M`}
               aria-label="output price per million tokens"
               onChange={(e) => setOutUsd(e.target.value)} />
        <SecondaryButton disabled={!model.trim()}
                onClick={savePrice}>save price</SecondaryButton>
      </div>
    </Card>
  );
}

type TierRow = {
  tier: "fast" | "standard" | "deep";
  purpose: string;
  model: string;
  chosen: boolean;
  recommended: string | null;
  price: [number, number] | null;
};
type TierData = {
  tiers: TierRow[];
  models: { model: string; price: [number, number] | null }[];
  recommended: Record<string, string>;
};

const per = (p: [number, number] | null) =>
  p ? `${moneyPair(p[0], p[1])} per Mtok` : "no price known";

/** Which model each tier runs on.
 *
 *  This was three environment variables, which put the most consequential
 *  decision in the product behind a deployment step: five times the price
 *  between the cheapest and the most capable, and on a judgement-heavy brief
 *  the difference between usable observations and a platitude.
 *
 *  Each option carries its price, because the choice is a cost decision as
 *  much as a quality one and the two were previously on different screens.
 */
type BriefRow = {
  tool: string; name: string; tier: string; scope: string | null; model: string;
  /** The part the brief writes to, from its header (brief v10 step AD). */
  part?: string | null; part_label?: string | null;
  chosen: boolean; why: string; used_by: number; price: [number, number] | null;
};
type BriefData = { briefs: BriefRow[]; models: { model: string; price: [number, number] | null }[] };

/** Admin > Brief defaults (brief v4 Item 3g): one row per brief - its
 *  tier, the model it runs on by default, why the tier suits it, and how
 *  many sites it has run on. Both a single run and run-all read from here;
 *  the catalogue shows the model as text and links to this table. The
 *  select is limited to models with a price on file, because a default is
 *  what a batch is totalled against. */
export function BriefDefaults() {
  const [data, setData] = useState<BriefData | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = () => api.get<BriefData>("/api/models/briefs").then(setData)
    .catch((e) => setNote((e as ApiError).message));
  useEffect(() => { load(); }, []);
  const pick = async (tool: string, model: string) => {
    setNote(null);
    try {
      if (model === "") await api.del(`/api/models/briefs/${tool}`);
      else await api.put(`/api/models/briefs/${tool}`, { model });
      load();
    } catch (e) {
      setNote((e as ApiError).message);
    }
  };
  if (!data) return note ? <ErrorNote error={note} /> : <Loading />;
  return (
    <Card>
      <h3>Analysis defaults</h3>
      <SaveRule kind="on-change" />
      <p className="muted">
        What run-all and every single run use unless a run overrides it. An
        analysis with no choice runs on its tier's model (Models and budgets);
        the choosable models are the ones with a price on file.
      </p>
      {note && <ErrorNote error={note} />}
      {data.models.length === 0 && (
        <p className="muted">No model has a price on file yet — read the published prices on the Money tab first.</p>
      )}
      <table className="findings brief-defaults">
        <thead><tr><th>Part</th><th>Analysis</th><th>Tier</th><th>Default model</th><th>Why</th><th>Used by</th></tr></thead>
        <tbody>
          {data.briefs.map((b) => (
            <tr key={b.tool} className="brief-row">
              <td className="muted">{b.part_label ?? (b.part === "none" ? "—" : b.part ?? "—")}</td>
              <td>{b.name} <code className="muted">{b.tool}</code></td>
              <td><span className={`tier-chip tier-${b.tier}`}>{b.tier}</span></td>
              <td>
                <select className="input brief-pick" value={b.chosen ? b.model : ""}
                        aria-label={`default model for ${b.name}`}
                        onChange={(e) => pick(b.tool, e.target.value)}>
                  <option value="">{`tier default · ${shortModel(b.model)}`}</option>
                  {data.models.map((m) => (
                    <option key={m.model} value={m.model}>
                      {shortModel(m.model)}{m.price ? ` · ${moneyPair(m.price[0], m.price[1])}` : ""}
                    </option>
                  ))}
                </select>
              </td>
              <td className="muted">{b.why}</td>
              <td className="muted">{b.used_by} site{b.used_by === 1 ? "" : "s"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function TierModels() {
  const [data, setData] = useState<TierData | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => api.get<TierData>("/api/models/tiers").then((d) => { setData(d); setLoadError(null); })
    .catch((e: ApiError) => setLoadError(e.message));
  useEffect(() => { load(); }, []);

  const pick = async (tier: string, model: string) => {
    setNote(null);
    try {
      await api.put(`/api/models/tiers/${tier}`, { model });
      load();
    } catch (e) {
      setNote((e as ApiError).message);
    }
  };

  const recommend = async () => {
    setBusy(true); setNote(null);
    try {
      const out = await api.post<{ applied: Record<string, string>;
                                   skipped: Record<string, string> }>(
        "/api/models/tiers/recommended", {});
      const skipped = Object.entries(out.skipped);
      setNote(`Set ${Object.keys(out.applied).length} tiers.`
        + (skipped.length
           // Named, not swallowed: a tier left alone because its recommended
           // model is unavailable is still running something else.
           ? ` Left alone — ${skipped.map(([t, m]) => `${t} (${m} `
               + "is not available here)").join(", ")}.`
           : ""));
      load();
    } finally { setBusy(false); }
  };

  const reset = async () => {
    await api.del("/api/models/tiers");
    setNote("Cleared — the deployment's configuration decides again.");
    load();
  };

  if (!data) return loadError ? <ErrorNote error={loadError} onRetry={load} /> : <Loading />;
  const anyChosen = data.tiers.some((t) => t.chosen);
  return (
    <>
      <table className="findings">
        <thead><tr><th>Tier</th><th>Model</th><th>Price</th>
                   <th>Used for</th></tr></thead>
        <tbody>
          {data.tiers.map((t) => (
            <tr key={t.tier}>
              <td><span className={`pill wb-status-${t.tier === "deep" ? "planned"
                : t.tier === "fast" ? "ready" : "needs_key"}`}>{t.tier}</span></td>
              <td>
                <select className="input tier-pick" value={t.model}
                        aria-label={`model for the ${t.tier} tier`}
                        onChange={(e) => pick(t.tier, e.target.value)}>
                  {data.models.map((m) => (
                    <option key={m.model} value={m.model}>{m.model}</option>
                  ))}
                </select>
              </td>
              <td className="muted">{per(t.price)}</td>
              <td>
                {t.purpose}
                {/* Whether this is the operator's decision or the
                    deployment's. Without it the screen cannot be read. */}
                {!t.chosen && <span className="muted"> · from config</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="money-row">
        {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
        {/* Item 178: a setting, not a spend - nothing is charged on the press. */}
        <SecondaryButton disabled={busy}
                aria-busy={busy} onClick={recommend}>
          use recommended
        </SecondaryButton>
        <span className="muted" role="status" aria-live="polite">
          {busy && <Working>Setting the recommended models…</Working>}
        </span>
        {anyChosen && (
          <SecondaryButton onClick={reset}>back to config</SecondaryButton>
        )}
        <span className="muted">
          Recommended: {Object.entries(data.recommended)
            .map(([t, m]) => `${t} → ${m}`).join(", ")}.
        </span>
      </div>
      {note && <p className="muted">{note}</p>}
    </>
  );
}

/** Whether a configured provider actually answers.
 *
 *  The list above reports `configured`, which only ever meant "a key string
 *  exists". OpenPageRank read green for weeks while every audit recorded no
 *  backlink data, because the key was being refused with a 403 — the one
 *  state the screen could not express.
 *
 *  On demand, never on load: it makes real calls, and a dashboard that
 *  probed every provider to render itself would spend the operator's quota
 *  on nothing.
 */
type KeyRow = {
  name: string; provider: string; detail: string; obtain: string;
  stored: boolean; masked: string | null; env_present: boolean;
  overriding_env: boolean; configured: boolean;
};

type KeyData = {
  keys: KeyRow[]; file: string;
  //: null until the first key is saved — there is no file to protect yet.
  protected: boolean | null;
  note: string;
};

/** Provider keys, entered here rather than in a shell.
 *
 *  Values are never sent back — a stored key shows as its last four
 *  characters, which is enough to tell one from another when deciding
 *  whether to replace it and useless for anything else. What is typed goes
 *  straight to the server and is not kept in component state after it lands.
 */
function ProviderKeys() {
  const [data, setData] = useState<KeyData | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => api.get<KeyData>("/api/keys").then((d) => { setData(d); setLoadError(null); })
    .catch((e: ApiError) => setLoadError(e.message));
  useEffect(() => { load(); }, []);

  const save = async (row: KeyRow) => {
    const value = (draft[row.name] ?? "").trim();
    if (!value) return;
    setBusy(row.name); setNote(null);
    try {
      await api.put(`/api/keys/${row.name}`, { value });
      // Dropped as soon as it is stored: there is no reason for a key to sit
      // in browser memory once the server has it, and leaving it in the box
      // invites a second save of a value the operator can no longer read.
      setDraft((d) => ({ ...d, [row.name]: "" }));
      setNote(`${row.provider} key saved.${row.env_present
        ? " It now takes precedence over the one in your environment." : ""}`);
      await load();
    } catch (err) {
      setNote(`Not saved — ${err instanceof Error ? err.message : String(err)}.`);
    } finally { setBusy(null); }
  };

  const clear = async (row: KeyRow) => {
    setBusy(row.name); setNote(null);
    try {
      const out = await api.del<{ falls_back_to_env: boolean }>(
        `/api/keys/${row.name}`);
      // Saying which of the two happened matters: "removed" reads as "this
      // provider is now off", and when an environment value takes over that
      // is not what happened at all.
      setNote(out.falls_back_to_env
        ? `${row.provider} key removed. The value in your environment takes over.`
        : `${row.provider} key removed. The provider is now unconfigured.`);
      await load();
    } catch (err) {
      setNote(`Not removed — ${err instanceof Error ? err.message : String(err)}.`);
    } finally { setBusy(null); }
  };

  if (!data) return loadError ? <ErrorNote error={loadError} onRetry={load} /> : <Loading />;
  return (
    <Card>
      <h3>Provider keys</h3>
      <SaveRule kind="explicit" />
      <p className="muted">{data.note}</p>
      <p className="muted">
        <code>{data.file}</code>{" · "}
        {data.protected === null
          ? "nothing stored here yet"
          : data.protected
            ? "readable only by your user account"
            : "could not restrict file permissions — check them yourself"}
      </p>
      {note && <p className="muted">{note}</p>}
      <table className="findings">
        <thead>
          <tr><th>Provider</th><th>Key</th><th>New value</th><th /></tr>
        </thead>
        <tbody>
          {data.keys.map((row) => (
            <tr key={row.name}>
              <td>
                {row.provider}
                <div className="muted">{row.detail}</div>
                {/* The scheme is dropped from the label but kept in the href:
                    a bare host reads as a place to go, and a link that opens
                    where it says it goes is the whole job. */}
                {row.obtain && (
                  <div className="muted">
                    <a href={row.obtain} target="_blank" rel="noopener noreferrer" className="key-obtain"
                       title={row.obtain}>
                      {row.obtain.replace(/^https:\/\//, "")}
                    </a>
                  </div>
                )}
              </td>
              <td className="muted">
                {row.stored
                  ? <code>{row.masked}</code>
                  : row.env_present
                    ? "from your environment"
                    : "not set"}
                {row.overriding_env && (
                  <div className="muted">overriding your environment</div>
                )}
              </td>
              <td>
                <input className="input" type="password" autoComplete="off"
                       aria-label={`${row.configured ? "Replacement" : "New"} ${row.provider} key`}
                       placeholder={row.configured ? "replace" : "paste key"}
                       value={draft[row.name] ?? ""}
                       onChange={(e) => setDraft(
                         (d) => ({ ...d, [row.name]: e.target.value }))} />
              </td>
              <td>
                {/* UX-66. Stable caption, state on `aria-busy`; the words
                    are said once for the whole table below it rather than
                    once per row, which would mount one live region per
                    provider and announce nine empty ones. */}
                {/* Item 178: save and remove a row-height apart (`act-gap`),
                    never stacked 0 px under each other. */}
                <span className="act-gap">
                <SecondaryButton className="save-btn"
                        aria-label={`save the ${row.provider} key`}
                        disabled={busy === row.name || !(draft[row.name] ?? "").trim()}
                        aria-busy={busy === row.name}
                        onClick={() => save(row)}>
                  save
                </SecondaryButton>
                {row.stored && (
                  <DangerButton busy={busy === row.name} label={`remove the ${row.provider} key`}
                                confirm={{ title: `Remove the ${row.provider} key?`,
                                           body: row.env_present
                                             ? <p>The key in your environment takes over, so {row.provider} stays
                                                 configured.</p>
                                             : <p>{row.provider} becomes unconfigured on every site: {row.detail}
                                                 {" "}stops until a key is set again.</p>,
                                           action: "Remove the key" }}
                                onConfirm={() => clear(row)}>remove</DangerButton>
                )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* UX-66. One region for the table above, mounted unconditionally and
          empty while idle. It names the provider because the control that
          filled it is one of several identical `save` buttons. */}
      <div className="muted" role="status" aria-live="polite">
        {busy && <Working>{`Saving the ${busy} key…`}</Working>}
      </div>
      <p className="muted">
        A saved key is used immediately — nothing needs restarting. Use{" "}
        <a href="#/admin?tab=providers"
           onClick={goHandler("#/admin?tab=providers")}>
          Providers
        </a> to confirm it is accepted, since a
        present key and an accepted one look identical until something asks.
      </p>
    </Card>
  );
}

type CheckRow = { provider: string; configured: boolean; state: string;
                  status?: number; detail?: string };

/** What each provider is for, whether it has a key, and whether it replies.
 *
 *  One card because it was two, describing the same ten providers and
 *  disagreeing: "Data sources" said `configured` while the check said
 *  `refusing 403`, and an operator had to hold both in their head to work
 *  out that a present key was being rejected. Presence and liveness are two
 *  columns of one row, not two screens.
 *
 *  Liveness is filled in on demand, never on load — it makes real calls, and
 *  a page that probed every provider to render itself would spend the
 *  operator's quota on nothing.
 */
function ProviderStatus({ providers }: { providers: Record<string, Provider> }) {
  const [rows, setRows] = useState<Record<string, CheckRow> | null>(null);
  const [busy, setBusy] = useState(false);

  const check = async () => {
    setBusy(true);
    try {
      const out = await api.post<{ providers: CheckRow[] }>(
        "/api/admin/providers/check", {});
      setRows(Object.fromEntries(out.providers.map((r) => [r.provider, r])));
    } finally { setBusy(false); }
  };

  const unconfigured = Object.entries(providers).filter(([, p]) => !p.configured);

  return (
    <Card>
      <h3>Providers</h3>
      <p className="muted">
        Every one is optional. A missing key lowers confidence and renders
        gaps as <code>[TO CONFIRM]</code> — it never invents a number or
        breaks a run. Set keys under{" "}
        <a href="#/admin?tab=keys" onClick={goHandler("#/admin?tab=keys")}>
          Provider keys
        </a>, or in the environment; either way they are never stored in the database, so
        a database backup carries no credentials.
      </p>
      <div className="money-row">
        {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
        {/* Item 178 (10-14): real calls, one of which bills, so it is priced
            in words and confirmed with the providers it will ask. */}
        <SpendButton price={null} busy={busy} onSpend={check}
                     confirm={{ title: "Ask every configured provider?",
                                body: <p>It makes a real call to each of{" "}
                                  {Object.entries(providers).filter(([, p]) => p.configured)
                                    .map(([n]) => n).join(", ") || "no configured provider"}.
                                  {" "}DataForSEO bills per request; any provider it cannot
                                  ask without spending or a side effect says so instead.</p>,
                                action: "Ask them" }}>
          ask every provider
        </SpendButton>
        <span className="muted" role="status" aria-live="polite">
          {busy && <Working>Asking every provider…</Working>}
        </span>
        <span className="muted">
          A key being present is not the same as it being accepted, and the
          two look identical until something asks. This makes real calls, and
          DataForSEO bills for them; any it cannot ask without spending your
          money or causing a side effect says so instead of being left out.
        </span>
      </div>
      <table className="findings">
        <thead><tr><th>Provider</th><th>Key</th><th>Answers</th>
                   <th>Enables</th></tr></thead>
        <tbody>
          {Object.entries(providers).map(([name, p]) => {
            const r = rows?.[name];
            return (
              <tr key={name}>
                <td>{name}</td>
                <td>
                  <Pill tone={p.configured ? "state-fixed" : "held"}>
                    {p.configured ? "configured" : "not configured"}
                  </Pill>
                  {/* Where from. "configured" was true of a key set here, one
                      in the environment, and one set here overriding one
                      there — three states an operator must tell apart. */}
                  {p.source && (
                    <div className="muted">
                      {p.source === "panel" ? "set here" : "from your environment"}
                    </div>
                  )}
                </td>
                <td>
                  {r ? (
                    <>
                      {/* "not checked" is its own state, not a middling one.
                          Colouring it like "not configured" would claim the
                          key is missing when it may be set and simply
                          unasked. */}
                      <Pill tone={r.state === "answering" ? "state-fixed"
                        : r.state === "refusing" ? "state-regressed"
                        : "state-candidate"}>
                        {r.state}{r.status ? ` ${r.status}` : ""}
                      </Pill>
                      {r.detail && <div className="muted">{r.detail}</div>}
                    </>
                  ) : <span className="muted">not asked yet</span>}
                </td>
                <td className="muted">{p.detail}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!!unconfigured.length && (
        <>
          <h4>To enable the rest</h4>
          <p className="muted">
            Most of these are keys — paste them in under{" "}
            <a href="#/admin?tab=keys" onClick={goHandler("#/admin?tab=keys")}>
              Provider keys
            </a>, which takes effect
            immediately and wins over the environment. The variable is the
            alternative, for a scripted or headless install.
          </p>
          <ul>
            {unconfigured.map(([name, p]) => (
              <li key={name}>
                <strong>{name}</strong>:{" "}
                {/* A `setx` line for the headless renderer could never work —
                    it is a pip install, not a key — and offering one sent
                    operators to set a variable nothing reads. */}
                {p.managed
                  ? <>set it in <strong>Provider keys</strong> above, or{" "}
                      <code>setx {p.env} "&lt;your value&gt;"</code>{" "}
                      <SecondaryButton onClick={() =>
                        navigator.clipboard.writeText(
                          `setx ${p.env} "<your value>"`).catch(() => {})}>
                        copy
                      </SecondaryButton></>
                  : <span className="muted">{p.detail}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

type BrandData = {
  name: string; name_is_set: boolean; product_name: string;
  logo_path: string | null; logo_mime: string | null;
  logo_missing: boolean; updated_at: string | null;
  /** Where the tab icon should point, or null to keep the built-in
   *  default. The server decides; see FEATURES.md F-08. */
  icon_href?: string | null;
};

/** The operator's own name and mark, for client-facing documents.
 *
 *  Two names kept apart on purpose. This screen says what it is actually
 *  running, because an admin panel that lied about that would be the one
 *  place an operator cannot debug from. The document says whoever the
 *  operator is — a client is buying their judgement, and which tool produced
 *  it is the operator's business.
 */
function Brand() {
  const [data, setData] = useState<BrandData | null>(null);
  const [name, setName] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  // Fetched with the token rather than left to the browser (UX-30). `tick`
  // still cache-busts, and still for its original reason: a replaced logo is
  // served from the same path, so the query is what makes this a new fetch.
  const logo = useObjectUrl(
    data?.logo_path ? `/api/brand/logo?v=${tick}` : null);

  const [loadError, setLoadError] = useState<string | null>(null);
  const logoInput = useRef<HTMLInputElement>(null);
  const load = () => api.get<BrandData>("/api/brand").then((d) => {
    setData(d);
    setLoadError(null);
    setName(d.name_is_set ? d.name : "");
  }).catch((e: ApiError) => setLoadError(e.message));
  useEffect(() => { load(); }, []);

  const saveName = async () => {
    setNote(null);
    try {
      await api.put("/api/brand/name", { name });
      load();
      setNote("Saved. New reports carry this name.");
    } catch (e) {
      setNote((e as ApiError).message);
    }
  };

  const pickLogo = async (file: File) => {
    setBusy(true); setNote(null);
    try {
      // Base64 in a JSON body rather than a multipart upload: multipart
      // would add a runtime dependency to the server for one 2 MB field.
      const buf = new Uint8Array(await file.arrayBuffer());
      let bin = "";
      for (const byte of buf) bin += String.fromCharCode(byte);
      await api.post("/api/brand/logo", { data_base64: btoa(bin) });
      setTick((t) => t + 1);
      load();
      // The tab too, not only this panel (F-08). Without this the new mark
      // appears here and the browser keeps showing the old one until a
      // reload, which is the stale-icon defect this feature exists to end.
      void applyBrandFavicon();
      setNote("Logo saved.");
    } catch (e) {
      setNote((e as ApiError).message);
    } finally { setBusy(false); }
  };

  if (!data) return loadError ? <ErrorNote error={loadError} onRetry={load} /> : <Loading />;
  return (
    <Card>
      <h3>Your name on client reports</h3>
      <SaveRule kind="explicit" />
      <p className="muted">
        What a client sees on a document produced here. This screen keeps
        saying {data.product_name}, because it is what you are running — the
        change is to the deliverable, not to the tool.
      </p>

      <div className="money-row">
        <label className="page-pick">
          <span className="sel-lbl">Reports are from</span>
          <input className="input brand-name" value={name}
                 aria-label="name on client reports"
                 placeholder={data.product_name}
                 onChange={(e) => setName(e.target.value)} />
        </label>
        <SecondaryButton onClick={saveName}>save</SecondaryButton>
        {!data.name_is_set && (
          <span className="muted">
            Unset — reports currently say {data.product_name}.
          </span>
        )}
      </div>

      <div className="money-row">
        {/* Item 181 (10-4): a real button - the label it was looked like one
            and was never a tab stop. It opens the hidden file input. */}
        <SecondaryButton aria-busy={busy}
              onClick={() => logoInput.current?.click()}>
          {data.logo_path ? "replace logo" : "add a logo"}
        </SecondaryButton>
        <input type="file" accept="image/*" hidden ref={logoInput}
               aria-label="logo image file"
               onChange={(e) => {
                 const f = e.target.files?.[0];
                 if (f) pickLogo(f);
                 e.target.value = "";
               }} />
        <span className="muted" role="status" aria-live="polite">{busy ? <Working>Reading the logo…</Working> : ""}</span>
        {data.logo_path && (
          <>
            {/* Rendered only once the bytes are here. An element pointed at
                the API path fetches without the token and paints a broken
                image instead of the operator's mark (UX-30); nothing is a
                truer answer than something wrong. */}
            {logo && <img className="brand-logo" alt="your logo" src={logo} />}
            <DangerButton label="remove the logo"
                          confirm={{ title: "Remove your logo?",
                                     body: <p>New client reports carry no logo, and the browser tab
                                       returns to the default icon. Reports already generated keep
                                       theirs.</p>,
                                     action: "Remove the logo" }}
                          onConfirm={async () => {
                            await api.del("/api/brand/logo"); load();
                            void applyBrandFavicon();
                          }}>remove</DangerButton>
          </>
        )}
        {data.logo_missing && (
          <Pill tone="state-regressed">
            file missing — re-upload it
          </Pill>
        )}
        <span className="muted">
          PNG, JPEG, GIF or WebP, up to 2 MB. Checked by content, not by file
          name.
        </span>
      </div>
      {note && <p className="muted">{note}</p>}
    </Card>
  );
}

/** The screen's sections, one per tab (operator, 2026-09-03: "make each
 *  section in the admin its own tab"). In the order the cards stood - by how
 *  often an operator needs it, so the one checked between runs is first and
 *  the ones set once during setup are last - with the parked Workbench at the
 *  end because it is a guest here. The key is the address: `#/admin?tab=<key>`.
 *
 *  Links through the door and `aria-current="page"`, the same shape as the
 *  client screen's reference row and for the same reason (`views.tsx`
 *  `Refs`): a row that changed the section without writing the address is
 *  the retired tab row's own defect, and the back button would do nothing. */
type AdminTab = "spend" | "providers" | "keys" | "models" | "briefs" | "prices" | "brand"
              | "sites" | "cadence" | "operators" | "database" | "workbench";
const ADMIN_TABS: { key: AdminTab; label: string }[] = [
  { key: "spend", label: "Spend" },
  { key: "providers", label: "Providers" },
  { key: "keys", label: "Provider keys" },
  { key: "models", label: "Models and budgets" },
  { key: "briefs", label: "Analysis defaults" },
  { key: "prices", label: "Money" },
  { key: "brand", label: "Brand" },
  { key: "sites", label: "Sites" },
  // Item 177: every site's cadence and its annual cost, one row per site - the
  // register of Analysis defaults, workspace configuration, which is why it is
  // here and not in Tools.
  { key: "cadence", label: "Cadences" },
  { key: "operators", label: "Operators" },
  { key: "database", label: "Database" },
  { key: "workbench", label: "Workbench" },
];
const DEFAULT_TAB: AdminTab = "spend";

/** Which section the address names. Read on mount and on every `hashchange`,
 *  since the links are pressed while this screen is mounted. An unknown name
 *  is never a silent fallthrough: the default section shows, and `unknown`
 *  carries the word so the screen can say which name was not one. */
function useAdminTab(): { tab: AdminTab; unknown: string | null } {
  const read = () => {
    const [, query] = (window.location.hash || "").split("?");
    const raw = new URLSearchParams(query || "").get("tab");
    if (!raw) return { tab: DEFAULT_TAB, unknown: null };
    const hit = ADMIN_TABS.find((t) => t.key === raw);
    return hit ? { tab: hit.key, unknown: null }
               : { tab: DEFAULT_TAB, unknown: raw };
  };
  const [state, setState] = useState(read);
  useEffect(() => {
    const on = () => setState(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return state;
}

function AdminTabs({ active }: { active: AdminTab }) {
  // Item 181 (11-14): one tab stop for the twelve sections, the current one;
  // arrow keys, Home and End move between them. Twelve stops stood between the
  // nav and every Admin tab's first control.
  const move = (e: React.KeyboardEvent<HTMLElement>) => {
    const links = [...e.currentTarget.querySelectorAll<HTMLAnchorElement>(".ref-link")];
    const at = links.indexOf(document.activeElement as HTMLAnchorElement);
    if (at < 0) return;
    const next = e.key === "ArrowRight" || e.key === "ArrowDown" ? Math.min(links.length - 1, at + 1)
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? Math.max(0, at - 1)
      : e.key === "Home" ? 0 : e.key === "End" ? links.length - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    links[next].focus();
  };
  return (
    <nav className="refs admin-tabs" aria-label="Admin sections, arrow keys move between them" onKeyDown={move}>
      {ADMIN_TABS.map((t) => {
        const href = `#/admin?tab=${t.key}`;
        return (
          <a key={t.key} className="ref-link" href={href}
             onClick={goHandler(href)} tabIndex={active === t.key ? 0 : -1}
             aria-current={active === t.key ? "page" : undefined}>
            {t.label}
          </a>
        );
      })}
    </nav>
  );
}

/** The briefs by phase, against one stored audit.
 *
 *  Parked here from the run screen (operator, 2026-09-03: "certain items are
 *  just in the wrong place ... move this workbench section into the admin
 *  section under its own tab for the moment"). There it ran against the run
 *  whose screen it stood on; here the audit is the selection's - the client
 *  from the header's picker, the audit from the control below - so the
 *  section keeps working while it waits for its proper home. The list itself
 *  is `AnalysisList`, unchanged, grouped by the payload's parts since brief v11 step AI. */
/** A site's local-SEO record (brief v11 step AI): what the Title &
 *  description and Headings briefs read beside the crawl. Lists and maps
 *  are typed one entry per line and stored as JSON; an empty field is not
 *  set, and each prompt states its own fallback for that. */
type SiteRecord = {
  id: string; domain: string; client?: string; client_id?: string;
  brand?: string | null; gbp_primary_category?: string | null;
  service_area_entity?: string | null; title_strategy?: string | null;
  neighbourhoods?: string[] | null; entity_variants?: Record<string, string[]> | null;
  sub_services?: { name: string; url?: string }[] | null;
  location_pages?: { url: string; location_entity: string }[] | null;
  page_types?: Record<string, string> | null;
  /** What the Images brief reads (brief v15 step AQ). Every one optional;
   *  the prompt states its own fallback and lists the inference under the
   *  run's assumptions. */
  platform?: string | null;
  cdn_or_image_pipeline?: string | null;
  breakpoints?: number[] | null;
  budget_lcp_kb?: string | null;
  budget_page_kb?: string | null;
  review_provenance?: string | null;
  priority_internal_targets?: string[] | null;
  /** What "too heavy" is for one image, and what the re-encode probe
   *  encodes at (brief v16 step AU7). */
  budget_image_kb?: string | null;
  bytes_per_pixel?: string | null;
  reencode_quality?: string | null;
  /** What the Structured data brief reads (brief v16 step AS). The two
   *  lists are separate because the distinction is the finding: a profile
   *  the entity controls belongs in `sameAs`, a directory that mentions it
   *  belongs in `subjectOf`, and putting the second in the first claims
   *  the entity *is* that page. */
  nap?: string | null;
  sameas_sources?: string[] | null;
  legal_name?: string | null;
  registered_ids?: string[] | null;
  external_profiles?: { url: string; claimed?: boolean | null }[] | null;
  citation_sources?: string[] | null;
  locations?: string | null;
  id_page_uri?: string | null;
  canonical_id?: string | null;
  /** What the Security brief reads (brief v20 step BD). The map is what
   *  script-inventory classifies a host against: named here, it is known. */
  stack?: string | null;
  cdn_or_waf?: string | null;
  active_probing_authorised?: string | null;
  /** Item 145 step BG: "allow" · "block" · empty (not stated). */
  ai_crawler_policy?: string | null;
  ai_field_data_source?: string | null;
  /** Item 145 BG: comma-separated agents refused at the edge on purpose. */
  ai_edge_blocked_agents?: string | null;
  /** The agents that list may name, from the server's agent table. */
  edge_agents?: { agent: string; class: string }[];
  reputation_source?: string | null;
  plugin_directory_feed?: string | null;
  third_party_map?: Record<string, string> | null;
  /** Item 167. The Google listing the operator confirmed, by Places id, and
   *  the latest lookup's candidates it was picked from. Written through
   *  `PUT /api/sites/{id}/gbp-listing`, never the site patch. */
  gbp_confirmed_place_id?: string | null;
  gbp_last_lookup?: GbpLookup | null;
};

type GbpCandidate = { place_id: string; name?: string | null; address?: string | null;
                      phone?: string | null; website?: string | null };
type GbpLookup = { looked_up_at: string; match?: string | null; place_id?: string | null;
                   candidates: GbpCandidate[];
                   confirmed_place_id_not_returned?: string | null };

/** Which Google listing is this site's (item 167). A Places lookup the
 *  website cannot confirm is withheld from every brief; the operator can
 *  tell the right business on sight, so they pick it here from the latest
 *  lookup's candidates and every later run uses it without asking again. */
function GbpListingControl({ site, onSaved }: { site: SiteRecord; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const lookup = site.gbp_last_lookup;
  const confirmed = site.gbp_confirmed_place_id ?? null;
  const put = async (placeId: string) => {
    setBusy(true); setNote(null);
    try {
      await api.put(`/api/sites/${site.id}/gbp-listing`, { place_id: placeId });
      onSaved();
    } catch (e) {
      setNote((e as ApiError).message);
    } finally { setBusy(false); }
  };
  return (
    <div className="gbp-listing">
      <span className="sel-lbl">Google listing</span>
      {!lookup ? (
        <p className="muted">
          {confirmed
            ? `Confirmed listing ${confirmed}. `
            : "No listing looked up yet. "}
          The Business Profile, Citations and Reviews analyses look it up; their
          candidates appear here to confirm.
        </p>
      ) : (
        <>
          <p className="muted">
            Latest lookup {lookup.looked_up_at.slice(0, 10)}: {lookup.candidates.length} candidate
            {lookup.candidates.length === 1 ? "" : "s"}.
            {lookup.confirmed_place_id_not_returned
              ? " The confirmed listing was not among them — it may have moved or closed."
              : ""}
            {" "}A listing that is not confirmed, by its website or here, is kept out of every analysis.
          </p>
          <ul className="gbp-candidates">
            {lookup.candidates.map((c) => {
              const mine = c.place_id === confirmed;
              return (
                <li key={c.place_id}>
                  <strong>{c.name ?? "unnamed listing"}</strong>
                  <span className="muted"> · {c.address ?? "no address"} · {c.phone ?? "no phone"}
                    {" · "}{c.website ?? "no website listed"}</span>
                  {" "}
                  {mine
                    ? <SecondaryButton disabled={busy}
                            onClick={() => put("")}
                            aria-label={`withdraw confirmation of ${c.name ?? c.place_id}`}>
                        confirmed · withdraw</SecondaryButton>
                    : <SecondaryButton disabled={busy}
                            onClick={() => put(c.place_id)}
                            aria-label={`confirm ${c.name ?? c.place_id} as the listing for ${site.domain}`}>
                        this is the listing</SecondaryButton>}
                </li>
              );
            })}
          </ul>
        </>
      )}
      {note && <span className="muted"> {note}</span>}
    </div>
  );
}

const linesOf = (v: string) => v.split("\n").map((l) => l.trim()).filter(Boolean);
const pairsOf = (v: string, a: string, b: string) => linesOf(v).map((l) => {
  const [x, ...rest] = l.split("|");
  return { [a]: x.trim(), [b]: rest.join("|").trim() };
});
/** `url | claimed` / `url | not claimed` / `url` — three states, because
 *  whether a profile is claimed is the operator's statement and an unanswered
 *  one is not a "no" (item 145 step BH). The engine reads `claimed: null` as
 *  not stated and says so in the analysis context. */
const profilesOf = (v: string) => linesOf(v).map((l) => {
  const [url, ...rest] = l.split("|");
  const said = rest.join("|").trim().toLowerCase();
  return {
    url: url.trim(),
    claimed: said === "" ? null : !/^(not|un|no\b)/.test(said),
  };
}).filter((p) => p.url);
const profileLines = (rows: { url: string; claimed?: boolean | null }[]) =>
  rows.map((r) => `${r.url}${r.claimed == null ? "" : r.claimed ? " | claimed" : " | not claimed"}`)
      .join("\n");
const mapOf = (v: string) => Object.fromEntries(linesOf(v).map((l) => {
  const [k, ...rest] = l.split(":");
  return [k.trim(), rest.join(":").split(",").map((s) => s.trim()).filter(Boolean)];
}));

type EntitySuggestions = {
  run_id: string | null; measured_at: string | null; home: string | null;
  entity_type: string | null; legal_name: string | null;
  registered_ids: string[]; external_profiles: { url: string; claimed: boolean | null }[];
};

/** What the site's own structured data says about the three entity fields
 *  (item 145 step BH). Offered, never applied: `entity-unresolvable` judges
 *  the markup's `sameAs` against the record's identifiers and
 *  `entity-footprint-unlinked` judges the record's profiles against what the
 *  pages pin, so a record filled from that markup makes both agree with
 *  themselves. Pressing `use` fills the box above and the operator still has
 *  to save, which is the point at which a value becomes the record's. */
function EntitySuggestionsPanel({ site, onUse }: {
  site: SiteRecord;
  onUse: (patch: { legal_name?: string; registered_ids?: string; external_profiles?: string }) => void;
}) {
  const [got, setGot] = useState<EntitySuggestions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open || got || error) return;
    // Latched, so a slow answer for the site the operator has moved off
    // cannot land in the panel of the one they are looking at now.
    let live = true;
    api.get<EntitySuggestions>(`/api/sites/${site.id}/entity-suggestions`)
      .then((s) => { if (live) setGot(s); })
      .catch((e) => { if (live) setError((e as ApiError).message); });
    return () => { live = false; };
  }, [open, got, error, site.id]);
  const nothing = got && !got.legal_name && !got.registered_ids.length
    && !got.external_profiles.length;
  return (
    <details className="entity-suggest" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>From the site&apos;s own schema</summary>
      {error && <p className="error" role="alert">{error}</p>}
      {!got && !error && <p className="muted">Reading the last crawl&apos;s home page…</p>}
      {got && !got.run_id && (
        <p className="muted">No crawl has been stored for this site yet.</p>
      )}
      {got && got.run_id && (
        <>
          <p className="muted">
            {got.entity_type ? `${got.entity_type} node on ` : "No business entity node on "}
            <code>{got.home}</code>, crawled {(got.measured_at ?? "").slice(0, 10)}.
            {" "}Nothing here is on the record until you use it and save: a field
            copied from the markup it is compared against can only agree with itself.
          </p>
          {nothing && <p className="muted">The node states none of these three.</p>}
          <ul className="entity-suggest-list">
            {got.legal_name && (
              <li>
                <span><code>legalName</code> {got.legal_name}</span>
                <SecondaryButton
                      onClick={() => onUse({ legal_name: got.legal_name! })}>use</SecondaryButton>
              </li>
            )}
            {got.registered_ids.length > 0 && (
              <li>
                <span>{got.registered_ids.length} identifier
                  {got.registered_ids.length === 1 ? "" : "s"}: {got.registered_ids.join("; ")}</span>
                <SecondaryButton
                      onClick={() => onUse({ registered_ids: got.registered_ids.join("\n") })}>use</SecondaryButton>
              </li>
            )}
            {got.external_profiles.length > 0 && (
              <li>
                <span>{got.external_profiles.length} profile
                  {got.external_profiles.length === 1 ? "" : "s"} pinned in <code>sameAs</code>:{" "}
                  {got.external_profiles.map((x) => x.url).join(", ")}</span>
                <SecondaryButton
                      onClick={() => onUse({
                        external_profiles: got.external_profiles.map((x) => x.url).join("\n"),
                      })}>use</SecondaryButton>
              </li>
            )}
          </ul>
        </>
      )}
    </details>
  );
}

function SiteRecordForm({ site, onSaved }: { site: SiteRecord; onSaved: () => void }) {
  const [f, setF] = useState({
    brand: site.brand ?? "", gbp_primary_category: site.gbp_primary_category ?? "",
    service_area_entity: site.service_area_entity ?? "", title_strategy: site.title_strategy ?? "",
    neighbourhoods: (site.neighbourhoods ?? []).join("\n"),
    entity_variants: Object.entries(site.entity_variants ?? {}).map(([k, v]) => `${k}: ${v.join(", ")}`).join("\n"),
    sub_services: (site.sub_services ?? []).map((s) => `${s.name} | ${s.url ?? ""}`).join("\n"),
    location_pages: (site.location_pages ?? []).map((l) => `${l.url} | ${l.location_entity}`).join("\n"),
    page_types: Object.entries(site.page_types ?? {}).map(([u, t]) => `${u} | ${t}`).join("\n"),
    platform: site.platform ?? "",
    cdn_or_image_pipeline: site.cdn_or_image_pipeline ?? "",
    breakpoints: (site.breakpoints ?? []).join(", "),
    budget_lcp_kb: site.budget_lcp_kb ?? "",
    budget_page_kb: site.budget_page_kb ?? "",
    review_provenance: site.review_provenance ?? "",
    priority_internal_targets: (site.priority_internal_targets ?? []).join("\n"),
    budget_image_kb: site.budget_image_kb ?? "",
    bytes_per_pixel: site.bytes_per_pixel ?? "",
    reencode_quality: site.reencode_quality ?? "",
    nap: site.nap ?? "",
    sameas_sources: (site.sameas_sources ?? []).join("\n"),
    legal_name: site.legal_name ?? "",
    registered_ids: (site.registered_ids ?? []).join("\n"),
    external_profiles: profileLines(site.external_profiles ?? []),
    citation_sources: (site.citation_sources ?? []).join("\n"),
    locations: site.locations ?? "",
    id_page_uri: site.id_page_uri ?? "",
    canonical_id: site.canonical_id ?? "",
    stack: site.stack ?? "",
    active_probing_authorised: site.active_probing_authorised ?? "",
    ai_crawler_policy: site.ai_crawler_policy ?? "",
    ai_field_data_source: site.ai_field_data_source ?? "",
    ai_edge_blocked_agents: site.ai_edge_blocked_agents ?? "",
    reputation_source: site.reputation_source ?? "",
    plugin_directory_feed: site.plugin_directory_feed ?? "",
    cdn_or_waf: site.cdn_or_waf ?? "",
    third_party_map: Object.entries(site.third_party_map ?? {}).map(([h, p]) => `${h} | ${p}`).join("\n"),
  });
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF((prev) => ({ ...prev, [k]: e.target.value }));
  const save = async () => {
    setBusy(true); setNote(null);
    try {
      await api.put(`/api/sites/${site.id}`, {
        brand: f.brand.trim(), gbp_primary_category: f.gbp_primary_category.trim(),
        service_area_entity: f.service_area_entity.trim(), title_strategy: f.title_strategy,
        neighbourhoods: linesOf(f.neighbourhoods),
        entity_variants: mapOf(f.entity_variants),
        sub_services: pairsOf(f.sub_services, "name", "url"),
        location_pages: pairsOf(f.location_pages, "url", "location_entity"),
        page_types: Object.fromEntries(pairsOf(f.page_types, "url", "type").map((p) => [p.url, p.type])),
        platform: f.platform.trim(),
        cdn_or_image_pipeline: f.cdn_or_image_pipeline.trim(),
        breakpoints: f.breakpoints.split(/[,\s]+/).map((n) => Number(n))
          .filter((n) => Number.isFinite(n) && n > 0),
        budget_lcp_kb: f.budget_lcp_kb.trim(),
        budget_page_kb: f.budget_page_kb.trim(),
        review_provenance: f.review_provenance,
        priority_internal_targets: linesOf(f.priority_internal_targets),
        budget_image_kb: f.budget_image_kb.trim(),
        bytes_per_pixel: f.bytes_per_pixel.trim(),
        reencode_quality: f.reencode_quality.trim(),
        nap: f.nap.trim(),
        sameas_sources: linesOf(f.sameas_sources),
        legal_name: f.legal_name.trim(),
        registered_ids: linesOf(f.registered_ids),
        external_profiles: profilesOf(f.external_profiles),
        citation_sources: linesOf(f.citation_sources),
        locations: f.locations,
        id_page_uri: f.id_page_uri.trim(),
        canonical_id: f.canonical_id.trim(),
        stack: f.stack.trim(),
        active_probing_authorised: f.active_probing_authorised,
        ai_crawler_policy: f.ai_crawler_policy,
        ai_field_data_source: f.ai_field_data_source.trim(),
        ai_edge_blocked_agents: f.ai_edge_blocked_agents,
        reputation_source: f.reputation_source.trim(),
        plugin_directory_feed: f.plugin_directory_feed.trim(),
        cdn_or_waf: f.cdn_or_waf.trim(),
        third_party_map: Object.fromEntries(pairsOf(f.third_party_map, "host", "purpose")
          .filter((p) => p.host).map((p) => [p.host.toLowerCase(), p.purpose])),
      });
      setNote("saved");
      onSaved();
    } catch (e) {
      setNote((e as ApiError).message);
    } finally { setBusy(false); }
  };
  const field = (label: string, k: keyof typeof f, hint: string, multiline = false) => (
    <label className="site-field">
      <span className="sel-lbl">{label}</span>
      {multiline
        ? <textarea className="input" rows={3} value={f[k]} onChange={set(k)} placeholder={hint}
                    aria-label={`${label} for ${site.domain}`} />
        : <input className="input" value={f[k]} onChange={set(k)} placeholder={hint}
                 aria-label={`${label} for ${site.domain}`} />}
    </label>
  );
  return (
    <Card>
      <h3>{host(site.domain)}{site.client ? <small className="muted"> · {site.client}</small> : null}</h3>
      <GbpListingControl site={site} onSaved={onSaved} />
      <EntitySuggestionsPanel site={site}
                              onUse={(patch) => setF((prev) => ({ ...prev, ...patch }))} />
      <div className="site-record">
        {field("Brand", "brand", "exactly as on the Google Business Profile")}
        {field("GBP primary category", "gbp_primary_category", "e.g. Pest Control Service")}
        {field("Service area entity", "service_area_entity", "e.g. Greater Melbourne")}
        <label className="site-field">
          <span className="sel-lbl">Title strategy</span>
          <select className="input" value={f.title_strategy} onChange={set("title_strategy")}
                  aria-label={`title strategy for ${site.domain}`}>
            <option value="">triple (default)</option>
            <option value="triple">triple</option>
            <option value="neighbourhood">neighbourhood</option>
          </select>
        </label>
        {field("Neighbourhoods", "neighbourhoods", "one suburb per line", true)}
        {field("Entity variants", "entity_variants", "entity: variant, variant — one per line", true)}
        {field("Sub-services", "sub_services", "name | url — one per line", true)}
        {field("Location pages", "location_pages", "url | location entity — one per line", true)}
        {field("Page types", "page_types", "url | location or service or blog or other — one per line", true)}
        {field("Platform", "platform", "CMS or builder, e.g. WordPress + Elementor")}
        {field("Image pipeline", "cdn_or_image_pipeline", "CDN or build step, e.g. Cloudflare Images")}
        {field("Breakpoints", "breakpoints", "widths in pixels, comma separated")}
        {field("LCP image budget (KB)", "budget_lcp_kb", "200 by default")}
        {field("Page image budget (KB)", "budget_page_kb", "1000 by default")}
        <label className="site-field">
          <span className="sel-lbl">Review provenance</span>
          {/* Review markup is only written where the reviews are confirmed
              to be the client's own; empty is read as unconfirmed, and the
              brief holds the check either way (brief v15 step AQ). */}
          <select className="input" value={f.review_provenance}
                  onChange={set("review_provenance")}
                  aria-label={`review provenance for ${site.domain}`}>
            <option value="">unconfirmed (default)</option>
            <option value="unconfirmed">unconfirmed</option>
            <option value="confirmed">confirmed</option>
          </select>
        </label>
        {field("Per-image budget (KB)", "budget_image_kb", "300 if unset")}
        {field("Bytes per rendered pixel", "bytes_per_pixel",
               "1.0 if unset; a well-encoded photograph is under 0.5")}
        {field("Re-encode quality", "reencode_quality", "60 if unset")}
        {field("NAP", "nap",
               "name, address and phone exactly as they should appear", true)}
        {/* Two boxes, not one, and the label says why: a directory in
            sameAs claims the entity *is* that page. */}
        {field("sameAs sources", "sameas_sources",
               "one per line - profiles the entity controls: GBP, Facebook, "
               + "LinkedIn, Wikidata", true)}
        {field("Legal name", "legal_name",
               "the registered entity, where it differs from the brand")}
        {field("Registered identifiers", "registered_ids",
               "one per line - ABN, ACN, VAT or company number, exactly as "
               + "registered", true)}
        {/* The footprint, not the pin list: `sameAs sources` above is what the
            markup should pin, and this is every branded profile with whether
            the operator has claimed it, which is a different fix. */}
        {field("External profiles", "external_profiles",
               "url | claimed - one per line; leave the second half off if you "
               + "do not know", true)}
        {field("Citation sources", "citation_sources",
               "one per line - places that mention it: directories, council "
               + "listings, review sites. These go to subjectOf, never sameAs.",
               true)}
        <label className="site-field">
          <span className="sel-lbl">Locations</span>
          <select className="input" value={f.locations} onChange={set("locations")}
                  aria-label={`locations for ${site.domain}`}>
            <option value="">not set</option>
            <option value="one">one</option>
            <option value="many">many</option>
          </select>
        </label>
        {field("ID page URI", "id_page_uri", "the page that describes the entity")}
        {field("Canonical @id", "canonical_id",
               "the @id in use or intended; empty proposes <site>/#organization")}
        {field("Priority internal targets", "priority_internal_targets",
               "one url per line — pages image links should reach", true)}
        {field("Stack", "stack", "origin, CDN and CMS, e.g. nginx · Cloudflare · WordPress")}
        {field("CDN / WAF", "cdn_or_waf", "what sits in front of the origin, e.g. Cloudflare")}
        <label className="site-field">
          <span className="sel-lbl">AI crawler policy</span>
          {/* Item 145 step BG. "block" makes a robots.txt block on an AI
              agent the policy working: the row stays, at LOW, and is not a
              blocker. Not stated keeps it HIGH. */}
          <select className="input" value={f.ai_crawler_policy}
                  onChange={set("ai_crawler_policy")}
                  aria-label={`AI crawler policy for ${site.domain}`}>
            <option value="">not stated (default)</option>
            <option value="allow">allow AI agents</option>
            <option value="block">block AI agents</option>
          </select>
        </label>
        <fieldset className="site-field edge-agents">
          <legend className="sel-lbl">Blocked at the firewall on purpose</legend>
          {/* Item 145 BG (channel 20260915-1430). The AI crawler policy
              speaks for robots.txt only; an agent ticked here that the edge
              refuses reads as the policy working, at LOW. Unticked, HIGH. */}
          {(site.edge_agents ?? []).map(({ agent, class: cls }) => {
            const on = f.ai_edge_blocked_agents.split(",").map((t) => t.trim()).includes(agent);
            const toggle = () => setF((prev) => {
              const now = prev.ai_edge_blocked_agents.split(",").map((t) => t.trim()).filter(Boolean);
              const next = on ? now.filter((t) => t !== agent) : [...now, agent];
              return { ...prev, ai_edge_blocked_agents: next.join(",") };
            });
            return (
              <label key={agent} className="edge-agent">
                <input type="checkbox" checked={on} onChange={toggle}
                       aria-label={`${agent} blocked at the firewall on purpose for ${site.domain}`} />
                {" "}{agent} <small className="muted">{cls}</small>
              </label>
            );
          })}
        </fieldset>
        {field("AI real-visitor data source", "ai_field_data_source",
               "where per-crawler server counts come from, e.g. cloudflare — recorded, not connected yet")}
        {field("Third-party map", "third_party_map",
               "host | what it is for — one per line; a host named here is not reported as unexplained",
               true)}
        <label className="site-field">
          <span className="sel-lbl">Active probing authorised</span>
          {/* Brief v20 step BD: recorded only. Saying so beside the control
              keeps a stored "true" from reading as a probe that ran. */}
          <select className="input" value={f.active_probing_authorised}
                  onChange={set("active_probing_authorised")}
                  aria-label={`active probing authorised for ${site.domain}`}>
            <option value="">not authorised (default)</option>
            <option value="true">authorised</option>
          </select>
          <small className="muted">Recorded only — nothing in this build probes a site, either way.</small>
        </label>
        {field("Reputation source", "reputation_source",
               "Safe Browsing key reference or search-console — recorded, not connected yet")}
        {field("Plugin directory feed", "plugin_directory_feed",
               "URL of a component version feed — recorded, not fetched yet")}
      </div>
      <p className="site-record-acts">
        <SecondaryButton disabled={busy} onClick={save}>save</SecondaryButton>
        {note && <span className="muted"> {note}</span>}
      </p>
    </Card>
  );
}

function SitesTab() {
  const [sites, setSites] = useState<SiteRecord[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    api.get<{ id: string; domain: string; client: string }[]>("/api/sites").then(async (list) => {
      const records = await Promise.all(list.map((s) => api.get<SiteRecord>(`/api/sites/${s.id}/record`)
        .then((r) => ({ ...r, client: s.client }))));
      if (live) setSites(records);
    }).catch((e) => { if (live) setErr((e as ApiError).message); });
    return () => { live = false; };
  }, [tick]);
  if (err) return <ErrorNote error={err} />;
  if (!sites) return <Loading />;
  return (
    <>
      <h3>Sites</h3>
      <SaveRule kind="explicit" />
      <p className="muted">
        The local-SEO facts the Title &amp; description and Headings analyses
        read beside the crawl. Every field is optional; an empty one follows
        the analysis's stated fallback, listed under the audit's assumptions.
      </p>
      {sites.map((s) => <SiteRecordForm key={`${s.id}-${tick}`} site={s} onSaved={() => setTick((t) => t + 1)} />)}
    </>
  );
}

function WorkbenchTab() {
  const { siteId, site, runId, runsReady } = useSelection();
  const [laneTick, setLaneTick] = useState(0);
  const { data: lanes, error } = useAnalyses(runId || null, laneTick);
  return (
    <>
      <AuditScopeBar note={"One stored audit for every analysis below: the client is "
                           + "the header's pick, the audit is this one."} />
      {error && <ErrorNote error={error} />}
      {site && !runsReady ? (
        <Loading what={`${host(site.domain)}'s audits`} />
      ) : !runId ? (
        <p className="muted">
          {site
            ? `${host(site.domain)} has no completed audit, so there is `
              + "nothing here for an analysis to read."
            : "No client is selected. Pick one in the header; the analyses run "
              + "against one of its stored audits."}
        </p>
      ) : (
        <>
          {/* The numbered phases are the workbench's order - fix what
              invalidates other work first - and they skip, because only some
              phases have analyses that read a whole site. */}
          <p className="muted phase-note">
            Grouped by the part each analysis writes to. Nothing here has run
            unless its row says so; a row that has run opens free, and only the
            priced ones spend.
          </p>
          {!lanes && !error && <Loading what="the analyses" />}
          {lanes && (lanes.parts ?? []).filter((p) => p.briefs.length).map((p) => (
            <Card key={p.key}>
              <h3>{p.label}</h3>
              <AnalysisList lanes={lanes} tools={p.briefs} runId={runId}
                            onChanged={() => setLaneTick((n) => n + 1)} />
            </Card>
          ))}
        </>
      )}
    </>
  );
}

/** When a measurement says it may be, or is, out of date (item 239 step 6).
 *  Two ages in days, the operator's; the defaults are item 239's. */
function AgeThresholdsPanel() {
  const [got, setGot] = useState<{ warn_days: number; stale_days: number;
                                   defaults: { warn_days: number; stale_days: number } } | null>(null);
  const [warn, setWarn] = useState("");
  const [stale, setStale] = useState("");
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.get<NonNullable<typeof got>>("/api/prefs/age").then((g) => {
      if (!live) return;
      setGot(g); setWarn(String(g.warn_days)); setStale(String(g.stale_days));
    }).catch((e: Error) => { if (live) setNote(e.message); });
    return () => { live = false; };
  }, []);
  const save = async () => {
    try {
      const g = await api.put<NonNullable<typeof got>>("/api/prefs/age",
        { warn_days: Number(warn), stale_days: Number(stale) });
      setGot(g); setNote("Saved.");
    } catch (e) { setNote((e as ApiError).message); }
  };
  return (
    <Card>
      <h3>When a measurement is out of date</h3>
      <SaveRule kind="explicit" />
      <p className="muted">
        Every date a part shows is judged by these two ages. From the first it
        is drawn in the warning tone, "may be out of date", with the part's
        re-check beside it; from the second it is "out of date" and the part is
        marked stale in the parts strip.
        {got ? ` The defaults are ${got.defaults.warn_days} and ${got.defaults.stale_days} days.` : ""}
      </p>
      <div className="money-row">
        <label className="page-pick">
          <span className="sel-lbl">May be out of date from (days)</span>
          <input className="input age-days" inputMode="numeric" value={warn}
                 aria-label="days before a measurement may be out of date"
                 onChange={(e) => setWarn(e.target.value)} />
        </label>
        <label className="page-pick">
          <span className="sel-lbl">Out of date from (days)</span>
          <input className="input age-days" inputMode="numeric" value={stale}
                 aria-label="days before a measurement is out of date"
                 onChange={(e) => setStale(e.target.value)} />
        </label>
        <SecondaryButton onClick={save}>save</SecondaryButton>
        <span className="muted" role="status" aria-live="polite">{note ?? ""}</span>
      </div>
    </Card>
  );
}

export function AdminView() {
  const [data, setData] = useState<Admin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const { tab, unknown } = useAdminTab();

  useEffect(() => {
    let live = true;
    api.get<Admin>("/api/admin")
      .then((d) => { if (live) setData(d); })
      .catch((e: ApiError) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [tick]);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;

  const backup = async () => {
    setBusy("backup");
    setNote(null);
    try {
      const result = await api.post<{ name: string; bytes: number;
                                      integrity: string }>("/api/admin/backup", {});
      setNote(`Snapshot ${result.name} written (${mb(result.bytes)}), `
        + `integrity check: ${result.integrity}.`);
      setTick((t) => t + 1);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  const clearCache = async () => {
    setBusy("cache");
    setNote(null);
    try {
      const result = await api.post<{ cleared: number }>(
        "/api/admin/clear-analyst-cache", {});
      setNote(`Cleared ${result.cleared} cached result${result.cleared === 1 ? "" : "s"}.`);
      setTick((t) => t + 1);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <h2>Admin</h2>
      <p className="muted">
        ClauditSEO {data.version} · engine {data.engine_version} · {data.locale} ·
        auth: {data.auth_mode} · UI{" "}
        {/* The bundle actually being served, not the server's version. They
            are different facts and were drawn as one: a dashboard fix that
            never reached the operator looked identical to one that had. */}
        {data.bundle ?? "not built — run npm run build in dashboard/"}
      </p>
      {/* One section at a time (operator, 2026-09-03). The row is the
          navigation, and the address is the state: `#/admin?tab=<key>`, so a
          section can be linked to and the back button works. The order is
          the one the cards stood in - by how often an operator needs it. */}
      <AdminTabs active={tab} />
      {unknown && (
        <p className="muted" role="status">
          No Admin section is called “{unknown}” — showing{" "}
          {ADMIN_TABS.find((t) => t.key === DEFAULT_TAB)?.label}.
        </p>
      )}
      {note && <div className="priority-plan">{note}</div>}

      {tab === "spend" && (<>
      {/* Checked between runs. */}
      <Card>
        <h3>Spend</h3>
        {data.budget?.warning && (
          <p className="error"><strong>{data.budget.warning}</strong></p>
        )}
        <p className="muted">
          This month: {data.budget?.month_tokens.toLocaleString()} tokens
          {data.budget?.month_usd != null
            ? ` · ${money(data.budget.month_usd)}`
            : data.budget?.usd_unpriced ? " · dollars not priced" : ""}
          {data.budget?.usd_unpriced
            ? <> (<PricedFrame entries={data.budget.usd_entries}
                               unpriced={data.budget.usd_unpriced} />)</>
            : ""}
          {data.budget?.cap_tokens || data.budget?.cap_usd
            ? ` — cap ${data.budget.cap_tokens
                ? `${data.budget.cap_tokens.toLocaleString()} tokens`
                : money(data.budget.cap_usd ?? 0)}`
            : " — no cap set (CLAUDITSEO_MONTHLY_BUDGET_TOKENS or _USD)"}.
          Dollar figures appear only where model prices are configured;
          a month with tokens but no dollars means no rates, not no spend.
        </p>
        {!!data.spend?.length && (
          <table className="findings">
            <thead><tr><th>Month</th><th>Client</th><th>Tokens</th><th>USD</th>
              {/* The column the em dash never had: a row drawing a real
                  number over a partly-priced month looked exactly like one
                  drawing it over a wholly-priced one. */}
              <th>Priced</th></tr></thead>
            <tbody>
              {data.spend.map((s, i) => (
                <tr key={i}>
                  <td>{s.month}</td>
                  <td>{s.client}</td>
                  <td>{Math.round(s.tokens).toLocaleString()}</td>
                  <td>{s.usd != null ? money(s.usd) : "—"}</td>
                  <td>{s.unpriced
                        ? `${s.priced} of ${s.priced + s.unpriced}`
                        : "all"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

      </Card>

      </>)}

      {/* Consulted when a report says a dimension went unmeasured. */}
      {tab === "providers" && <ProviderStatus providers={data.providers} />}

      {/* Changed when the answer on Providers is "refusing". */}
      {tab === "keys" && <ProviderKeys />}

      {tab === "briefs" && <BriefDefaults />}
      {tab === "models" && (<>
      {/* Tuned occasionally; it decides what a run costs. */}
      <Card>
        <h3>Models and budgets</h3>
        <p className="muted">
          Analyses are routed by what the work actually is, so applying a
          checklist does not cost the same as calling intent overlap.
        </p>
        <TierModels />
        <p className="muted">
          Token ceilings per audit — T2: {data.budgets.T2.toLocaleString()},
          T3: {data.budgets.T3.toLocaleString()},
          per page analysis: {data.budgets.page.toLocaleString()}.
        </p>
      </Card>

      </>)}

      {/* Rates and prices: set up once, refreshed now and then. */}
      {tab === "prices" && <Money />}

      {/* Set once. */}
      {tab === "brand" && <Brand />}
      {tab === "sites" && <SitesTab />}

      {tab === "cadence" && <><Card><CadenceGrid /></Card><AgeThresholdsPanel /></>}

      {tab === "operators" && (<>
      <Card>
        <h3>Operators</h3>
        {data.operators.length ? (
          <table className="findings">
            <thead><tr><th>Name</th><th>Role</th><th>Email</th><th>Token</th></tr></thead>
            <tbody>
              {data.operators.map((o) => (
                <tr key={o.id}>
                  <td>{o.name}</td>
                  <td>{o.role}</td>
                  <td>{o.email ?? "—"}</td>
                  <td>{o.has_token ? "set" : "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="muted">No operator accounts.</p>}
        <p className="muted">
          Add one with <code>clauditseo operator add --name "…" --role member</code>.
          The login token is shown once and stored only as a hash. Once any
          operator has a token, the API requires login.
        </p>
      </Card>
      </>)}

      {tab === "database" && (<>
      {/* Maintenance, and the most destructive controls on the page. Last
          on purpose: nothing here is part of a normal day. */}
      <Card>
        <h3>Database</h3>
        <p className="muted">
          <code>{data.database.path}</code> — {mb(data.database.bytes)}
          {data.database.wal_bytes > 0 &&
            ` (+${mb(data.database.wal_bytes)} awaiting checkpoint in the WAL)`}
        </p>
        <table className="findings">
          <thead><tr><th>Table</th><th>Rows</th></tr></thead>
          <tbody>
            {Object.entries(data.database.rows).map(([table, count]) => (
              <tr key={table}>
                <td><code>{table}</code></td>
                <td>{count < 0 ? "—" : count.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* Item 178 (10-14): with the other maintenance, not beside the tier
            models it re-prices. */}
        <h4>Maintenance</h4>
        <p>
          {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
          <DangerButton busy={busy === "cache"} why={busy !== null && busy !== "cache" ? "another task is running" : null}
                        confirm={{ title: "Clear every cached analyst and expert result?",
                                   body: <p>Nothing is lost that cannot be recomputed, but re-running
                                     those analyses spends tokens again, on every site.</p>,
                                   action: "Clear the cache" }}
                        onConfirm={clearCache}>
            Clear analyst cache
          </DangerButton>{" "}
          <span className="muted" role="status" aria-live="polite">
            {busy === "cache" && <Working>Clearing the analyst cache…</Working>}
          </span>{" "}
          <span className="muted">
            Forces every analysis to re-run rather than replay a cached report.
            Editing a prompt file already invalidates its own cache, so this is
            only needed to deliberately re-spend.
          </span>
        </p>
        <p>
          {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
          <SecondaryButton onClick={backup} disabled={busy !== null}
                  aria-busy={busy === "backup"}>
            Back up database now
          </SecondaryButton>{" "}
          <span className="muted" role="status" aria-live="polite">
            {busy === "backup" && <Working>Taking a snapshot…</Working>}
          </span>
        </p>
        <p className="muted">
          Safe to run while the server is serving: the snapshot is taken through
          a live connection rather than copied off disk, so it cannot miss
          writes still sitting in the write-ahead log. Every snapshot is
          integrity-checked and row-counted against the source, and discarded if
          it does not match.
        </p>

        <h4>Snapshots ({data.backups.length})</h4>
        {data.backups.length ? (
          <table className="findings">
            <thead><tr><th>File</th><th>Taken</th><th>Size</th></tr></thead>
            <tbody>
              {data.backups.map((b) => (
                <tr key={b.name}>
                  <td><code>{b.name}</code></td>
                  <td>{b.created_at.replace("T", " ")}</td>
                  <td>{mb(b.bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="muted">No snapshots yet.</p>}

        <h4>To restore one</h4>
        <ol className="advice-read">
          {data.restore_steps.map((step, i) => <li key={i}>{step}</li>)}
        </ol>
        <p className="muted">
          Deliberately a manual sequence rather than a button: restoring
          discards every audit recorded since the snapshot.
        </p>
      </Card>
      </>)}

      {/* A guest, parked (see `WorkbenchTab`). */}
      {tab === "workbench" && <WorkbenchTab />}
    </>
  );
}
