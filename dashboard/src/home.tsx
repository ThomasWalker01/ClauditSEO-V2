/**
 * Home: the workspace, in the client landing's language one floor up (item 176,
 * concept H1).
 *
 * Eyebrow, headline, one row of real actions, then the sites as cards, then
 * nothing else. Items 168 and 171 to 175 settled every piece on the client
 * landing, and the rules travel unchanged: the headline's 68ch measure and two
 * lines (175), the action row, the card rhythm, nothing between the actions and
 * the content. What changes is the scope - six sites, not one audit.
 *
 * Four things the earlier Home did stop. `delete site` and `edit domain` sat on
 * every row beside the name; editing and deleting are behind the card now, and a
 * delete still asks. The type select and brand input were live fields on the
 * row's face; they are facts on the card, edited deliberately behind it. The
 * score key and the "seen once" note are the shared legend's (item 166). And
 * "No site is scheduled" was a caution box, which is how a reader learns to stop
 * seeing it; it is the headline's last clause.
 *
 * A site no audit has completed on says so in words. Its score was an em-dash in
 * a column, which read as missing data; it is a state.
 */
import { LinkButton, SecondaryButton } from "./buttons";
import { useEffect, useState } from "react";
import { Meta, RunStatus, api, hasScore, useFetch } from "./api";
import {
  ErrorNote, Loading, PricedFrame, RunStatusChip, ScoreBadge, money,
} from "./components";
import { Legend } from "./glossary";
import { coverageNotes } from "./population";
import { host, useSelection } from "./selection";
import { Pill } from "./pill";
import { DangerButton } from "./spend";
import { goHandler } from "./nav";

type Row = {
  client: string; client_id: string; site_id: string; domain: string;
  business_type: string | null;
  /** The brand the site's copy carries (brief v11 step AI); null is not set. */
  brand?: string | null;
  schedule: string | null; score: number | null; delta: number | null;
  /** Coverage notes among the open rows, not counted in `open` (item 180). */
  notes?: number;
  /** The tier the delta compares within (item 180): "on the previous T2 audit". */
  delta_tier?: string | null;
  /** The newest scored reading when it was a page or navigation scan
   *  and no site-wide reading exists (brief v3 step I): shown as what it
   *  is, never as the site's score. */
  narrow_score?: number | null; narrow_scope?: string | null;
  /** When that narrow reading ran (item 180). */
  narrow_at?: string | null;
  last_run_at: string | null; last_run_id: string | null;
  /** The newest audit's status, which is not always the scored one.
   *  `/api/overview` has emitted this since `blocked` became a status,
   *  specifically so a blocked crawl is not reported as the previous run's
   *  healthy score. */
  last_run_status: RunStatus | null;
  open: number; regressed: number; candidate: number;
  watch: { change_count?: number }[] | number | null;
  schedule_state: "overdue" | "scheduled" | "manual" | "waiting";
  next_pass_at: string | null; why: string;
};

type Overview = {
  sites: Row[];
  /** `month_usd` is null when the month has cost entries and none of them
   *  carries a price - distinct from `0`, which is a measured zero on a
   *  month with no entries at all. `usd_entries` and `usd_unpriced` are the
   *  frame: without them the value cannot say whether it is a total or a
   *  floor. See `_budget_status` in `clauditseo/api/app.py`. */
  budget: { month_usd: number | null; usd_entries: number;
            usd_unpriced: number; warning: string | null };
  checks_every_minutes: number;
};

const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
               "Nine", "Ten", "Eleven", "Twelve"];
/** A count that opens a sentence, in words while it is small. */
const Count = (n: number) => WORDS[n] ?? String(n);

/** How long ago, in the words a card uses. */
function ago(iso: string | null): string {
  if (!iso) return "never";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

function watchCount(w: Row["watch"]): number {
  if (typeof w === "number") return w;
  if (Array.isArray(w)) return w.length;
  return 0;
}

/** The headline's last clause: what runs without anyone asking (item 177 says
 *  how it reads once cadences exist). */
function scheduleClause(sites: Row[], checksEvery: number): string {
  const on = sites.filter((s) => s.schedule_state !== "manual");
  if (!on.length) return "Nothing is scheduled, so nothing runs unless you start it.";
  const next = on.filter((s) => s.next_pass_at)
    .sort((a, b) => (a.next_pass_at! < b.next_pass_at! ? -1 : 1))[0];
  const when = next ? new Date(next.next_pass_at!).toLocaleDateString(undefined,
    { weekday: "short", day: "numeric", month: "short" }) : null;
  const lead = on.length === sites.length ? "Every site runs on a cadence"
    : `${Count(on.length)} of the ${sites.length} run on a cadence`;
  return `${lead}${when ? `; the next pass is ${when}` : ""}, checked every ${checksEvery} minutes.`;
}

export function HomeView() {
  const [tick, setTick] = useState(0);
  const [adding, setAdding] = useState(false);
  const { data, error, loading, retry } = useFetch<Overview>("/api/overview", tick);
  // Fetched once here rather than per card - `/api/meta` is the single source
  // for the business-type vocabulary.
  const { data: meta } = useFetch<Meta>("/api/meta");
  const { siteId } = useSelection();
  const businessTypes = meta?.business_types ?? [];
  if (error) return <ErrorNote error={error} onRetry={retry} retrying={loading} />;
  if (!data) return <Loading />;

  // Newest audit first; a site no audit has completed on goes last.
  const sites = [...data.sites].sort((a, b) =>
    // Newest reading of any scope (item 180, 01-2): a site read by a page scan
    // today does not sort below every site audited last week.
    (b.last_run_at ?? b.narrow_at ?? "").localeCompare(a.last_run_at ?? a.narrow_at ?? ""));
  const open = sites.reduce((n, s) => n + s.open, 0);
  const regressed = sites.reduce((n, s) => n + s.regressed, 0);
  const allScheduled = sites.length > 0 && sites.every((s) => s.schedule_state !== "manual");
  const cadenceAt = "#/admin?tab=cadence";
  const auditAt = siteId ? `#/sites/${siteId}?tab=history` : null;
  const refresh = () => setTick((t) => t + 1);

  return (
    <>
      {/* The route's heading, for the outline; the eyebrow is its drawn form. */}
      <h2 className="sr-only">Home</h2>
      <div className="run-head run-head-landing home-head">
        <p className="eyebrow" aria-hidden="true">Where the workspace stands</p>
        <p className="bl-sentence home-sentence">
          {sites.length ? <>
            {Count(sites.length)} site{sites.length === 1 ? " holds" : "s hold"}{" "}
            <span className="bl-found">{open} open finding{open === 1 ? "" : "s"}</span>
            {regressed > 0
              ? <>, and <span className="bl-tier">{regressed}</span> ha{regressed === 1 ? "s" : "ve"} come
                  back after a fix.</>
              : <>, and none has come back after a fix.</>}{" "}
            <span className="bl-s3">{scheduleClause(sites, data.checks_every_minutes)}</span>
          </> : <>No sites yet. Add a client, then a site.</>}
        </p>
        <p className="home-spend">
          {data.budget.month_usd != null
            ? <>{money(data.budget.month_usd)} spent this month</>
            : <>This month's spend is not priced</>}
          {/* The frame inline with the figure it qualifies, never a hover
              (UX-80): whether the sum is a total or a floor. */}
          {data.budget.usd_unpriced
            ? <>{" "}(<PricedFrame entries={data.budget.usd_entries}
                                   unpriced={data.budget.usd_unpriced} />)</>
            : null}.
        </p>
        {data.budget.warning && (
          <p className="error home-setup"><strong>{data.budget.warning}.</strong>{" "}
            Warnings only - nothing is blocked.</p>
        )}
        <div className="bl-actions">
          <div className="bl-buttons">
            {/* Primary while any site is manual (item 177): the finding stays
                visible without Home becoming a setup wizard. */}
            <LinkButton primary={!allScheduled}
                  className={allScheduled ? "bl-secondary" : "bl-primary"}
                  href={cadenceAt}>
              Set a cadence
            </LinkButton>
            {auditAt && (
              <LinkButton className="bl-secondary" href={auditAt}
                    onClick={goHandler(auditAt)}>
                Audit a site now
              </LinkButton>
            )}
            <SecondaryButton className="bl-secondary home-add-open"
                  aria-expanded={adding} onClick={() => setAdding(!adding)}>
              Add a client or site
            </SecondaryButton>
          </div>
        </div>
      </div>

      {adding && (
        <section className="home-add" aria-label="Add a client or site">
          <AddForms businessTypes={businessTypes} onAdded={refresh} />
          <ClientsDisclosure onChanged={refresh} version={tick} />
        </section>
      )}

      {sites.length > 0 && (
        <section className="home-sites" aria-labelledby="home-sites-head">
          <div className="home-row">
            <h3 id="home-sites-head" className="eyebrow home-sites-head">
              The {Count(sites.length).toLowerCase()} site{sites.length === 1 ? "" : "s"} · newest audit first
            </h3>
            <Legend ids={["score-good", "score-fair", "score-poor", "not-audited", "seen-once"]} />
          </div>
          <div className="home-cards">
            {sites.map((s) => (
              <SiteCard key={s.site_id} row={s} businessTypes={businessTypes} onChanged={refresh} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

/** One site: the score as its figure, the name, one sentence of consequence and
 *  its facts as tags. Editing and deleting are behind the card, in a closed
 *  disclosure, so no destructive control is one click from a resting state. */
function SiteCard({ row: s, businessTypes, onChanged }: {
  row: Row; businessTypes: string[]; onChanged: () => void;
}) {
  const changes = watchCount(s.watch);
  const audited = s.last_run_at != null;
  /** Read only by a page or nav scan (item 180, 01-2): not "never audited". */
  const narrowOnly = !audited && s.narrow_score != null;
  // Straight to the run they were last looking at.
  // The site's current view (item 239 step 5): no audit is picked.
  const href = `#/sites/${s.site_id}`;
  const name = `${s.client} › ${host(s.domain)}`;
  // Named against what it compares (item 180, 01-3): the previous audit of
  // the same tier, never whatever ran before.
  const against = s.delta_tier ? ` on the previous ${s.delta_tier} audit` : "";
  const moved = s.delta == null || s.delta === 0 ? ""
    : s.delta > 0 ? `, up ${s.delta}${against}` : `, down ${Math.abs(s.delta)}${against}`;
  return (
    <article className={`home-card${s.regressed > 0 ? " home-card-flag" : ""}`}
             data-site={s.site_id} aria-label={name}>
      <div className="home-card-top">
        <div>
          <h4 className="home-card-name"><a className="home-card-link" href={href}>{s.client}</a></h4>
          <div className="home-card-dom">{host(s.domain)}</div>
        </div>
        <div className="home-card-score">
          {narrowOnly ? <ScoreBadge score={s.narrow_score ?? null} />
            : !audited ? <span className="home-not-audited">not audited</span>
            : s.score == null && s.narrow_score != null ? <ScoreBadge score={s.narrow_score} />
            : <ScoreBadge score={s.score} />}
        </div>
      </div>
      <p className="home-card-line">
        {narrowOnly ? <>
          {s.open > 0 ? `${s.open} open from a ${s.narrow_scope} scan. ` : `Nothing open on a ${s.narrow_scope} scan. `}
          Scanned {ago(s.narrow_at ?? null)}; no site-wide audit yet, so the score is the scan's, not the site's.
        </> : !audited ? <>
          {s.open > 0 ? `${s.open} open. ` : "Nothing open. "}No audit has completed, so there is no score.
        </> : <>
          {s.regressed > 0 && <strong className="regressed">{s.regressed} back after a fix. </strong>}
          {s.open} open{s.notes ? ` · ${coverageNotes(s.notes)} not counted` : ""},
          {" "}{s.candidate} seen once. Audited {ago(s.last_run_at)}{moved}.
          {s.score == null && s.narrow_score != null && (
            <> The score is a {s.narrow_scope} scan, not a site score.</>
          )}
        </>}
        {changes > 0 && <> {Count(changes)} change{changes === 1 ? " is" : "s are"} being watched.</>}
      </p>
      <div className="home-card-foot">
        <span className={`home-tag${audited ? "" : " home-tag-warn"}`}>
          {audited ? `audited ${ago(s.last_run_at)}`
            : narrowOnly ? `${s.narrow_scope} scan only` : "never audited"}
        </span>
        {s.last_run_status && !hasScore(s.last_run_status) && <RunStatusChip status={s.last_run_status} />}
        <span className="home-tag">{s.business_type ?? "type not set"}</span>
        {s.brand && <span className="home-tag">brand {s.brand}</span>}
        <span className="home-tag">{s.schedule_state === "manual" ? "manual only"
          : s.schedule_state === "waiting" ? "needs a first audit" : s.schedule_state}</span>
      </div>
      <details className="home-card-manage">
        <summary>Edit this site<span className="sr-only">: {name}</span></summary>
        <div className="home-card-edit">
          <label className="home-edit-row">
            <span>Type</span>
            <BusinessType row={s} businessTypes={businessTypes} onSaved={onChanged} />
          </label>
          <label className="home-edit-row">
            <span>Brand</span>
            <BrandField row={s} onSaved={onChanged} />
          </label>
          <div className="home-edit-row">
            <span>Domain</span>
            {/* WF-81: the stored string, not the tidied one drawn above. */}
            <SiteDomain row={s} onSaved={onChanged} />
          </div>
          <div className="home-edit-row home-edit-danger">
            <SiteDelete row={s} onDeleted={onChanged} />
          </div>
        </div>
      </details>
    </article>
  );
}

/** Correct what a site is, from the list where every site is visible.
 *
 *  It could only be set when the site was added, which is before anyone has
 *  read the site — and it is an input the briefs trust completely. A lender
 *  filed as "ecommerce" produced a report reasoning about a product catalogue
 *  and branch locations that do not exist, stated as fact.
 *
 *  Changing it does not reach backwards, and the note says so rather than
 *  letting a corrected label imply corrected reports.
 */
/** The brand on the site record (brief v11 step AI): what replacement
 *  titles carry. Until it is set the Title & description brief takes it
 *  from the pages' own title tails and says so under assumptions. */
function BrandField({ row, onSaved }: { row: Row; onSaved: () => void }) {
  const [value, setValue] = useState(row.brand ?? "");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const next = value.trim();
    if (next === (row.brand ?? "")) return;
    setBusy(true);
    try {
      await api.put(`/api/sites/${row.site_id}`, { brand: next });
      setNote(null);
      onSaved();
    } catch (e) {
      setValue(row.brand ?? "");
      setNote((e as Error).message);
    } finally { setBusy(false); }
  };
  return (
    <span className="site-brand">
      <input className="input brand-field" value={value} disabled={busy}
             placeholder="brand"
             aria-label={`brand for ${row.domain}`}
             title="The brand the site's copy carries. Replacement titles and descriptions
                    use it; until it is set the analysis takes it from the pages' title tails
                    and lists that as an assumption."
             onClick={(e) => e.stopPropagation()}
             onChange={(e) => setValue(e.target.value)}
             onBlur={save}
             onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); (e.target as HTMLInputElement).blur(); } }} />
      {note && <span className="muted brand-note">{note}</span>}
    </span>
  );
}

function BusinessType({ row, businessTypes, onSaved }: {
  row: Row; businessTypes: string[]; onSaved: () => void;
}) {
  const [value, setValue] = useState(row.business_type ?? "");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async (next: string) => {
    setValue(next);
    setBusy(true);
    try {
      const out = await api.put<{ analyses_before: number; changed: string[] }>(
        `/api/sites/${row.site_id}`, { business_type: next });
      setNote(out.changed.length && out.analyses_before
        ? `${out.analyses_before} stored ${out.analyses_before === 1 ? "analysis was" : "analyses were"} written under the `
          + "old type — re-run them to benefit"
        : null);
      onSaved();
    } catch (e) {
      setValue(row.business_type ?? "");
      setNote((e as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <span className="biz-type">
      <select className="biz-select" value={value} disabled={busy}
              aria-label={`business type for ${row.domain}`}
              title="What the analyses assume this business is. They reason from
                     it, so a wrong value produces confident wrong advice."
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => { e.stopPropagation(); save(e.target.value); }}>
        <option value="">not set</option>
        {businessTypes.map((k) => <option key={k} value={k}>{k}</option>)}
      </select>
      {note && (
        <span className="muted biz-note" role="status">
          {note}{" "}
          <SecondaryButton onClick={() => setNote(null)}>ok</SecondaryButton>
        </span>
      )}
    </span>
  );
}

/** Correct a site's stored domain, where the domain is named -- WF-81.
 *
 *  High since report 063 and carried for nine reports: `sites.domain` was
 *  write-once, so the only route to a typo in the one field every run, crawl
 *  and deliverable filename hangs on was deleting the client and everything
 *  under it, or opening the database in SQL.
 *
 *  It shows the **stored** string, deliberately, where the row above shows a
 *  tidied one. `https://www.13acme.com.au/` is what the operator's database
 *  actually holds for one of three real sites, and the row has been drawing
 *  it as `www.13acme.com.au` for its whole life -- so a control prefilled
 *  from the drawn value would offer to correct a value that already looks
 *  correct, and the defect would stay invisible on the screen built to fix
 *  it.
 *
 *  Closed rather than open by default: this is a repair, not a field, and a
 *  text input beside every row on the product's densest table is noise on
 *  every row that is already right.
 */
function SiteDomain({ row, onSaved }: { row: Row; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(row.domain);
  /* CQ-222. A seed is not a subscription. `useState(row.domain)` runs once
     for the life of this component, and the server normalises through
     `crawl.site_host` on the way in — so `HTTP://Example.COM/` is stored as
     `example.com`, `onSaved` re-reads the table, the row arrives holding the
     normalised string, and the field went on offering back what was typed.
     The docstring above says this control shows what is *stored*; without
     this line it showed what was stored right up until the moment it was
     used, which is the one moment it is being read.

     Keyed on the stored string rather than on the row object, so a re-render
     that changes nothing about the domain does not reach in and clear a
     correction the operator is halfway through typing. A change to what is
     stored does clear it, and that is the intent: the stored value wins. */
  useEffect(() => { setValue(row.domain); }, [row.domain]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      /* The server normalises through `crawl.site_host` and answers with what
       * it stored, so nothing here strips a scheme: a copy of that rule in
       * the client is how the two would come to disagree, and the row above
       * is already one such copy. */
      await api.put(`/api/sites/${row.site_id}`, { domain: value });
      setOpen(false);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };

  if (!open) {
    return (
      <SecondaryButton disabled={busy}
              aria-label={`correct the stored domain for ${row.domain}`}
              title="What is stored for this site. Every audit, crawl and
                     deliverable is addressed by it."
              onClick={(e) => { e.stopPropagation(); setOpen(true); }}>
        edit domain
      </SecondaryButton>
    );
  }

  return (
    /* `stopPropagation` on each interactive child rather than once on this
       wrapper: `test_no_click_handlers_on_non_interactive_elements` refuses a
       handler on a `span`, and it is right to -- a span that swallows clicks
       is a control to a mouse and nothing at all to a keyboard. Found by that
       guard, which is the reason it exists, and the same shape `BusinessType`
       above already uses on its `select`. */
    <span className="site-domain">
      <input className="fact-mono" value={value} disabled={busy}
             aria-label={`stored domain for ${row.domain}`}
             onClick={(e) => e.stopPropagation()}
             onChange={(e) => setValue(e.target.value)} />
      <SecondaryButton disabled={busy}
              onClick={(e) => { e.stopPropagation(); save(); }}>save</SecondaryButton>
      <SecondaryButton disabled={busy}
              onClick={(e) => { e.stopPropagation(); setValue(row.domain);
                                setOpen(false); setError(null); }}>cancel</SecondaryButton>
      {error && <span className="muted" role="status">{error}</span>}
    </span>
  );
}

/** Delete one site and everything under it (item 169). A wrong site used to
 *  be removable only by deleting its whole client. Same shape as `edit domain`
 *  beside it, and `stopPropagation` on the button for the reason written in
 *  `SiteDomain`: the row around it is a link. */
function SiteDelete({ row, onDeleted }: { row: Row; onDeleted: () => void }) {
  const { refreshSites } = useSelection();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      {/* Item 178: the product's confirmation and the danger tone. */}
      <DangerButton busy={busy} label={`delete the site ${row.domain}`}
                    confirm={{ title: `Delete ${row.domain}?`,
                               body: <p>This permanently removes every audit, all findings and
                                 the full trend history for this site.</p>,
                               action: "Delete the site" }}
                    onConfirm={async () => {
              setBusy(true);
              setError(null);
              try {
                await api.del(`/api/sites/${row.site_id}`);
                refreshSites();
                onDeleted();
              } catch (err) {
                setError((err as Error).message);
              } finally { setBusy(false); }
            }}>
        delete site
      </DangerButton>
      {error && <span className="muted" role="status">{error}</span>}
    </>
  );
}

/** Every client, closed by default (item 169). Home is a table of sites, so a
 *  client with none appears nowhere else, and this is the one place it can be
 *  seen and removed. The confirm text is the retired client list's, verbatim. */
function ClientsDisclosure({ onChanged, version }: { onChanged: () => void; version: number }) {
  const [tick, setTick] = useState(0);
  const { data } = useFetch<{ id: string; name: string; site_count: number }[]>(
    "/api/clients", tick + version * 1000);
  const { refreshSites } = useSelection();
  const [error, setError] = useState<string | null>(null);
  return (
    <details className="home-clients">
      <summary>Clients</summary>
      {error && <p className="error" role="alert">{error}</p>}
      <ul className="home-client-list">
        {(data ?? []).map((c) => (
          <li key={c.id} className="card-deletable">
            <span>{c.name}</span>{" "}
            <span className="muted">{c.site_count} site{c.site_count === 1 ? "" : "s"}</span>
            <DangerButton className="card-delete" label={`delete client ${c.name}`}
                    confirm={{ title: `Delete client "${c.name}"?`,
                               body: <p>This permanently removes its {c.site_count} site
                                 {c.site_count === 1 ? "" : "s"}, every audit, all findings and the
                                 full trend history.</p>,
                               action: "Delete the client" }}
                    onConfirm={async () => {
                      setError(null);
                      try {
                        await api.del(`/api/clients/${c.id}`);
                        setTick((t) => t + 1);
                        refreshSites();
                        onChanged();
                      } catch (err) { setError((err as Error).message); }
                    }}>
              ✕
            </DangerButton>
          </li>
        ))}
      </ul>
      {data && !data.length && <p className="muted">No clients yet.</p>}
    </details>
  );
}

function AddForms({ businessTypes, onAdded }: {
  businessTypes: string[]; onAdded: () => void;
}) {
  const { data } = useFetch<{ id: string; name: string }[]>("/api/clients");
  // `onAdded` re-reads this screen's own table. The picker in the app chrome
  // is a different list with a different owner, and it has to be told too.
  const { refreshSites } = useSelection();
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [domain, setDomain] = useState("");
  const [kind, setKind] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (what: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try { await what(); onAdded(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="add-forms">
      {error && <p className="error" role="alert">{error}</p>}
      <form className="inline-form" onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim()) return;
        run(async () => { await api.post("/api/clients", { name: name.trim() });
                          setName(""); });
      }}>
        <input value={name} onChange={(e) => setName(e.target.value)}
               placeholder="New client name" aria-label="new client name" />
        <SecondaryButton submit disabled={busy || !name.trim()}>Add client</SecondaryButton>
      </form>

      <form className="inline-form" onSubmit={(e) => {
        e.preventDefault();
        if (!client || !domain.trim()) return;
        run(async () => {
          await api.post(`/api/clients/${client}/sites`,
                         { domain: domain.trim(), business_type: kind || null });
          setDomain("");
          refreshSites();
        });
      }}>
        <select value={client} onChange={(e) => setClient(e.target.value)}
                aria-label="client for the new site">
          <option value="">Client…</option>
          {(data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input value={domain} onChange={(e) => setDomain(e.target.value)}
               placeholder="example.com.au" aria-label="new site domain" />
        <select value={kind} onChange={(e) => setKind(e.target.value)}
                aria-label="business type">
          <option value="">business type…</option>
          {businessTypes.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <SecondaryButton submit disabled={busy || !client || !domain.trim()}>
          Add site
        </SecondaryButton>
      </form>
    </div>
  );
}
