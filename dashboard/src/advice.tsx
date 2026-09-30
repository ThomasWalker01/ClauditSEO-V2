import { SecondaryButton } from "./buttons";
import { Working } from "./working";
import { useEffect, useState } from "react";
import { ApiError, api } from "./api";
import { Pill, Tone } from "./pill";
import { Card, ErrorNote } from "./components";
import { SpendButton, SpendTarget } from "./spend";

type Advice = {
  assumptions: string[];
  triage: { commercial: boolean; multi_page: boolean; ymyl: boolean;
            search_facing: boolean; note: string };
  page_read: { page_type: string; primary_topic: string; audience: string;
               intent: string; alignment: string };
  site_role: { role: string; owns_cluster: string; sibling_clusters: string;
               cannibalisation: string } | null;
  keyword_intent: { head_term: string; demand: string; unverified_flags: string;
                    verdict: string } | null;
  // Optional because a scoped answer carries only its section's fields
  // (FEATURES.md F-03). The full remit still returns all of them; a request
  // narrowed to Headings genuinely has no title tag in it, and the type says
  // so rather than letting the render reach for one that is not there.
  recommended_h1?: { text: string; why: string };
  answer_line?: string | null;
  title_tag?: { text: string; why: string };
  meta_description?: { text: string; why: string };
  alternatives?: { h1: string; angle: string; tradeoff: string }[];
  schema_notes: string[] | null;
  compliance_notes: string[] | null;
  conflicts: string[];
};

type Envelope = {
  /** `none` comes only from the read-back (GET) path: nothing has been
   *  produced for this page of this run yet, so the panel offers to. It is
   *  distinct from an error — nothing failed. */
  status: "ok" | "unavailable" | "rejected" | "empty" | "none";
  reason?: string;
  problems?: string[];
  cached?: boolean;
  tokens?: number;
  model?: string;
  advice?: Advice;
  /** The finding this judgement answers, echoed back so the panel can say so
   *  rather than reading as advice about the page. */
  check_id?: string | null;
  /** Echoed back by the server: the category this answer was narrowed to,
   *  or null for the full remit. Rendered, because a narrowed answer and a
   *  thin one look identical otherwise. */
  scope?: string | null;
  security_notes?: string[];
  /** Set by the read-back: this advice came out of the page_advice table
   *  rather than off a provider just now (FEATURES.md F-04). */
  stored?: boolean;
  created_at?: string;
};

function Copyable({ label, text }: { label: string; text: string }) {
  const [done, setDone] = useState(false);
  return (
    <div className="advice-field">
      <div className="muted advice-label">{label}</div>
      <div className="advice-value">
        <code>{text}</code>
        <SecondaryButton onClick={async () => {
          await navigator.clipboard.writeText(text).catch(() => {});
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        }}>{done ? "copied ✓" : "copy"}</SecondaryButton>
      </div>
    </div>
  );
}

type SchemaAudit = {
  assumptions: string[];
  verdict: { rich_result: string; status: string; reason: string }[];
  current_state: string[];
  content_readiness: { supported: string[]; needs_new_content: string[];
                       hidden_markup_risk: string[] };
  validation: { property: string; status: string; requirement: string;
                finding: string }[];
  issues: { n: number; severity: string; issue: string }[];
  type_selection: string;
  corrected_jsonld: string;
  fix_map: { n: number; severity: string; fix: string; where: string }[];
  on_page_changes: string[];
  implementation: string[];
  revalidation: string[];
  fixes_unavailable?: string;
};

type SchemaEnvelope = {
  status: "ok" | "unavailable" | "rejected" | "empty";
  reason?: string; problems?: string[]; warnings?: string[];
  cached?: boolean; tokens?: number; model?: string; audit?: SchemaAudit;
};

const SEV_CLASS: Record<string, Tone> = {
  BLOCKER: "sev-critical", DEGRADES: "sev-medium",
  ADVISORY: "sev-info",
};
const STATUS_CLASS: Record<string, Tone> = {
  ERROR: "sev-high", MISSING: "sev-medium",
  WARNING: "sev-low", PASS: "sev-info",
};

export function SchemaAuditPanel({ runId, url, onBusy }: {
    runId: string; url: string;
    /** Reported upward so the section it was opened from can show
     *  it running. The panel owns its own run button, so nothing
     *  outside it can know otherwise — and the server cannot: this
     *  goes through its own endpoint, not the expert queue. */
    onBusy?: (busy: boolean) => void }) {
  const [result, setResult] = useState<SchemaEnvelope | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const request = async () => {
    setBusy(true); onBusy?.(true);
    setError(null);
    try {
      setResult(await api.post<SchemaEnvelope>(
        `/api/runs/${runId}/schema-audit`, { url }));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false); onBusy?.(false);
    }
  };

  if (!result) {
    return (
      <Card>
        <h3>Structured data audit</h3>
        <p className="muted">
          Diagnoses the page's existing JSON-LD against Google's current
          requirements — required properties, entity integrity, and rich
          results Google has deprecated or narrowed — then supplies corrected,
          paste-ready markup. Values the page doesn't show come back as
          <code> [TO CONFIRM: …]</code> rather than invented.
        </p>
        {error && <ErrorNote error={error} />}
        {/* UX-66. Stable caption, state on `aria-busy`, words in the
            unconditionally-mounted region below — the convention
            `views.tsx`'s `ReportView` states in full. */}
        {/* Item 178: priced in words and confirmed. */}
        <SpendButton price={null} busy={busy} onSpend={request}
                     confirm={{ title: "Audit this page's structured data?",
                              body: <><SpendTarget page={url} />
                                <p>A model reads the page's JSON-LD against Google's current
                                  requirements and writes corrected markup.</p></>,
                              action: "Audit the markup" }}>
          Audit structured data
        </SpendButton>
        <div className="muted" role="status" aria-live="polite">
          {busy && <Working>Auditing the markup…</Working>}
        </div>
      </Card>
    );
  }

  if (result.status !== "ok" || !result.audit) {
    return (
      <Card>
        <h3>Structured data audit</h3>
        <ErrorNote error={
          result.status === "rejected"
            ? `Audit rejected at ingest: ${(result.problems ?? []).join("; ")}`
            : result.reason ?? "No usable audit was produced."} />
        <SpendButton price={null} busy={busy} onSpend={request}
                     confirm={{ title: "Audit this page's structured data?",
                              body: <><SpendTarget page={url} />
                                <p>A model reads the page's JSON-LD against Google's current
                                  requirements and writes corrected markup.</p></>,
                              action: "Audit the markup" }}>
          Try again
        </SpendButton>
      </Card>
    );
  }

  const a = result.audit;
  return (
    <Card>
      <h3>
        Structured data audit{" "}
        <Pill tone="source-brief">
          model judgement — not scored{result.cached ? " · cached" : ""}
        </Pill>
      </h3>
      <p className="muted">
        {result.model}
        {result.tokens ? ` · ${result.tokens} tokens` : " · zero tokens (cached)"}
      </p>

      {!!result.warnings?.length && (
        <div className="banner-regression" role="alert">
          <strong>Verify before pasting:</strong>
          <ul>{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </div>
      )}

      <h4>Verdict</h4>
      <ul className="advice-read">
        {a.verdict.map((v, i) => (
          <li key={i}>
            <strong>{v.rich_result}:</strong> {v.status} — {v.reason}
          </li>
        ))}
      </ul>
      {a.fixes_unavailable && (
        <ErrorNote error={`Corrective markup not produced: ${a.fixes_unavailable}. `
          + "The diagnosis above still stands."} />
      )}

      {!!a.issues?.length && (
        <>
          <h4>Issues</h4>
          <table className="findings">
            <thead><tr><th>#</th><th>Severity</th><th>Issue</th></tr></thead>
            <tbody>
              {a.issues.map((it) => (
                <tr key={it.n}>
                  <td>{it.n}</td>
                  <td><Pill tone={SEV_CLASS[it.severity] ?? "sev-info"}>
                    {it.severity}</Pill></td>
                  <td>{it.issue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {!!a.validation?.length && (
        <>
          <h4>Property validation</h4>
          <table className="findings">
            <thead><tr><th>Property</th><th>Status</th><th>Level</th>
                       <th>Finding</th></tr></thead>
            <tbody>
              {a.validation.map((v, i) => (
                <tr key={i}>
                  <td><code>{v.property}</code></td>
                  <td><Pill tone={STATUS_CLASS[v.status] ?? "sev-info"}>
                    {v.status}</Pill></td>
                  <td>{v.requirement}</td>
                  <td>{v.finding}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {a.corrected_jsonld && (
        <>
          <h4>
            Corrected JSON-LD{" "}
            <SecondaryButton onClick={async () => {
              await navigator.clipboard.writeText(a.corrected_jsonld).catch(() => {});
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}>{copied ? "copied ✓" : "copy"}</SecondaryButton>
          </h4>
          <pre className="report">{a.corrected_jsonld}</pre>
        </>
      )}

      {!!a.fix_map?.length && (
        <>
          <h4>Fix map</h4>
          <table className="findings">
            <thead><tr><th>#</th><th>Fix</th><th>Where</th></tr></thead>
            <tbody>
              {a.fix_map.map((f, i) => (
                <tr key={i}><td>{f.n}</td><td>{f.fix}</td><td>{f.where}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {!!a.on_page_changes?.length && (
        <>
          <h4>On-page changes required</h4>
          <ul>{a.on_page_changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </>
      )}
      {!!a.content_readiness?.hidden_markup_risk?.length && (
        <ErrorNote error={"Hidden markup risk: "
          + a.content_readiness.hidden_markup_risk.join(" ")} />
      )}
      {!!a.implementation?.length && (
        <>
          <h4>Implementation</h4>
          <ul>{a.implementation.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </>
      )}
      {!!a.revalidation?.length && (
        <>
          <h4>Re-validation</h4>
          <ul>{a.revalidation.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </>
      )}
      {!!a.assumptions?.length && (
        <p className="muted rec">Assumptions: {a.assumptions.join(" · ")}</p>
      )}
    </Card>
  );
}

export function PageAdvice({ runId, url, scope, checkId, onBusy }: {
    runId: string; url: string;
    /** The category this panel was opened from, narrowing the answer to it
     *  (FEATURES.md F-03). Omitted where the panel is not opened from a
     *  section, which returns the full remit as it always did. The server
     *  refuses a category the advisor does not cover rather than quietly
     *  answering with everything. */
    scope?: string;
    /** The finding this was opened from (FEATURES.md F-02). It names its own
     *  scope, so it replaces `scope` rather than combining with it, and the
     *  server refuses it outright if the page advisor is not the specialist
     *  that judges that check. */
    checkId?: string;
    /** Reported upward so the section it was opened from can show
     *  it running. The panel owns its own run button, so nothing
     *  outside it can know otherwise — and the server cannot: this
     *  goes through its own endpoint, not the expert queue. */
    onBusy?: (busy: boolean) => void }) {
  const [result, setResult] = useState<Envelope | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(true);

  // Read back what was already produced for this page of this run, on mount
  // and whenever the panel changes what it is asking about (FEATURES.md
  // F-04). A GET: no fetch of the page, no provider, no cost entry. The
  // operator moved to another section and back and was offered "Advise on
  // this page" as though nothing had been made, because the result lived in
  // this component's state and unmounting discarded it.
  useEffect(() => {
    let live = true;
    setReading(true);
    setResult(null);
    setError(null);
    const query = new URLSearchParams({ url });
    // check_id names its own scope and replaces it, exactly as on the POST.
    if (checkId) query.set("check_id", checkId);
    else if (scope) query.set("scope", scope);
    api.get<Envelope>(`/api/runs/${runId}/advice?${query}`)
      .then((r) => { if (live) setResult(r); })
      // A read-back that fails leaves the panel exactly where it was before
      // this feature existed — offering to generate. It must not become a
      // wall between the operator and a control that used to work.
      .catch(() => { if (live) setResult(null); })
      .finally(() => { if (live) setReading(false); });
    // `live` guards the switch, not just the unmount: moving between sections
    // fires a second read while the first is in flight, and the loser landing
    // last would show one section's answer under another's heading.
    return () => { live = false; };
  }, [runId, url, scope, checkId]);

  const request = async () => {
    setBusy(true); onBusy?.(true);
    setError(null);
    try {
      setResult(await api.post<Envelope>(
        `/api/runs/${runId}/advise`,
        checkId ? { url, check_id: checkId }
                : scope ? { url, scope } : { url }));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false); onBusy?.(false);
    }
  };

  if (reading) {
    return (
      <Card>
        <h3>Page advisor</h3>
        <p className="muted">Checking for advice already produced for this page…</p>
      </Card>
    );
  }

  // `none` is the read-back saying nothing is stored, and is rendered
  // identically to never having asked: the offer to generate.
  if (!result || result.status === "none") {
    return (
      <Card>
        <h3>Page advisor</h3>
        <p className="muted">
          Recommends the H1, title tag, meta description and the answer line
          beneath the heading for this page, with ranked alternatives — judged
          from the page's live content, its siblings, and the findings already
          raised against it. One page, one call, budget-capped.
        </p>
        {error && <ErrorNote error={error} />}
        {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
        <SpendButton price={null} busy={busy} onSpend={request}
                     confirm={{ title: "Ask the page advisor about this page?",
                              body: <><SpendTarget page={url} />
                                <p>A model re-reads the live page and recommends its H1, title,
                                  description and answer line, replacing any advice stored for
                                  this page on this audit.</p></>,
                              action: "Ask the advisor" }}>
          Advise on this page
        </SpendButton>
        <div className="muted" role="status" aria-live="polite">
          {busy && <Working>Analysing the page…</Working>}
        </div>
      </Card>
    );
  }

  if (result.status !== "ok" || !result.advice) {
    return (
      <Card>
        <h3>Page advisor</h3>
        <ErrorNote error={
          result.status === "rejected"
            ? `Advice rejected at ingest: ${(result.problems ?? []).join("; ")}`
            : result.reason ?? "No usable recommendation was produced."} />
        <SpendButton price={null} busy={busy} onSpend={request}
                     confirm={{ title: "Ask the page advisor about this page?",
                              body: <><SpendTarget page={url} />
                                <p>A model re-reads the live page and recommends its H1, title,
                                  description and answer line, replacing any advice stored for
                                  this page on this audit.</p></>,
                              action: "Ask the advisor" }}>
          Try again
        </SpendButton>
      </Card>
    );
  }

  const a = result.advice;
  const fired = Object.entries(a.triage)
    .filter(([k, v]) => k !== "note" && v === true)
    .map(([k]) => k.replace("_", " "));

  return (
    <Card>
      <h3>
        Page advisor{" "}
        <Pill tone="source-brief">
          model judgement — not scored{result.cached ? " · cached" : ""}
        </Pill>
      </h3>
      <p className="muted">
        {result.model}
        {result.tokens ? ` · ${result.tokens} tokens` : " · zero tokens (cached)"}
        {fired.length ? ` · modules: ${fired.join(", ")}` : " · lean flow"}
      </p>
      {result.stored && (
        // Where this came from, said out loud. A judgement read back from
        // the run reads identically to one just produced, and the difference
        // — whether the operator was charged for what they are looking at —
        // is the whole of F-04.
        <p className="muted rec">
          Read back from this audit{result.created_at
            ? `, produced ${result.created_at}` : ""} — no model call, no
          tokens. Advising again re-reads the live page and replaces this.
        </p>
      )}
      {result.scope && (
        // Rendered text, not a title attribute: a narrowed answer and a thin
        // answer look the same, and the reader has to be told which this is.
        <p className="muted rec">
          Narrowed to this section. The advisor judged the whole page; the rest
          of its remit is on the other sections and cost nothing extra.
        </p>
      )}

      {a.recommended_h1 && (
        <div className="advice-h1">
          <div className="muted advice-label">Recommended H1</div>
          <h2 className="advice-headline">{a.recommended_h1.text}</h2>
          <p className="muted">{a.recommended_h1.why}</p>
          <SecondaryButton onClick={() =>
            navigator.clipboard.writeText(a.recommended_h1!.text).catch(() => {})}>
            copy H1
          </SecondaryButton>
        </div>
      )}

      {a.answer_line && (
        <div className="advice-field">
          <div className="muted advice-label">
            Answer line (the text directly beneath the H1 — what snippets quote)
          </div>
          <blockquote>{a.answer_line}</blockquote>
        </div>
      )}

      {a.title_tag && (
        <>
          <Copyable label="Title tag" text={a.title_tag.text} />
          <p className="muted rec">{a.title_tag.why}</p>
        </>
      )}
      {a.meta_description && (
        <>
          <Copyable label="Meta description" text={a.meta_description.text} />
          <p className="muted rec">{a.meta_description.why}</p>
        </>
      )}

      {!!a.alternatives?.length && (
        <>
          <h4>Alternatives</h4>
          <table className="findings">
            <thead><tr><th>Candidate H1</th><th>Angle</th><th>Trade-off</th></tr></thead>
            <tbody>
              {a.alternatives.map((alt, i) => (
                <tr key={i}><td>{alt.h1}</td><td>{alt.angle}</td><td>{alt.tradeoff}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h4>Page read</h4>
      <ul className="advice-read">
        <li><strong>Type:</strong> {a.page_read.page_type}</li>
        <li><strong>Topic:</strong> {a.page_read.primary_topic}</li>
        <li><strong>Audience:</strong> {a.page_read.audience}</li>
        <li><strong>Intent:</strong> {a.page_read.intent}</li>
        <li><strong>Alignment:</strong> {a.page_read.alignment}</li>
      </ul>

      {a.site_role && (
        <>
          <h4>Site role and cannibalisation</h4>
          <ul className="advice-read">
            <li><strong>Role:</strong> {a.site_role.role}</li>
            <li><strong>Should own:</strong> {a.site_role.owns_cluster}</li>
            <li><strong>Siblings own:</strong> {a.site_role.sibling_clusters}</li>
            <li><strong>Overlap:</strong> {a.site_role.cannibalisation}</li>
          </ul>
        </>
      )}

      {a.keyword_intent && (
        <>
          <h4>Keyword and intent</h4>
          <ul className="advice-read">
            <li><strong>Head term:</strong> {a.keyword_intent.head_term}</li>
            <li><strong>Demand:</strong> {a.keyword_intent.demand}</li>
            <li><strong>Unverified:</strong> {a.keyword_intent.unverified_flags}</li>
            <li><strong>Verdict:</strong> {a.keyword_intent.verdict}</li>
          </ul>
        </>
      )}

      {!!a.compliance_notes?.length && (
        <>
          <h4>Claim and compliance</h4>
          <ul>{a.compliance_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </>
      )}
      {!!a.schema_notes?.length && (
        <>
          <h4>Structured data</h4>
          <ul>{a.schema_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </>
      )}
      {!!a.conflicts?.length && (
        <>
          <h4>Conflicts and risks</h4>
          <ul>{a.conflicts.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </>
      )}
      {!!a.assumptions?.length && (
        <p className="muted rec">
          Assumptions: {a.assumptions.join(" · ")}
        </p>
      )}
      {!!result.security_notes?.length && (
        <ErrorNote error={`Security: ${result.security_notes.join(" ")}`} />
      )}
      {error && <ErrorNote error={error} />}
      {/* Kept, because F-04 would otherwise remove it. Once stored advice
          shows on mount there is no un-advised state to click through, and
          the operator who edits the page in response to the advice needs to
          ask again about what they just changed. Replaces the stored row for
          this page in this run rather than adding to it. */}
      {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
      <SpendButton price={null} busy={busy} onSpend={request}
                   confirm={{ title: "Ask the page advisor about this page?",
                              body: <><SpendTarget page={url} />
                                <p>A model re-reads the live page and recommends its H1, title,
                                  description and answer line, replacing any advice stored for
                                  this page on this audit.</p></>,
                              action: "Ask the advisor" }}>
        Advise again
      </SpendButton>
      <div className="muted" role="status" aria-live="polite">
        {busy && <Working>Analysing the page…</Working>}
      </div>
    </Card>
  );
}
