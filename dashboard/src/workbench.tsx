import { LinkButton, SecondaryButton } from "./buttons";
import { Working } from "./working";
import { useEffect, useState } from "react";
import { goto } from "./nav";
import { ApiError, RunStatus, api, completedAudits } from "./api";
import { ErrorNote, Loading } from "./components";
import { SpendButton, SpendTarget } from "./spend";
import { AnalysisList, useAnalyses } from "./analyses";
import { Pill } from "./pill";

/** Brief metadata straight from the playbook API. Building the panel from
 *  this rather than from a second hardcoded list keeps the workbench and the
 *  run page describing the same tool the same way. */
type Brief = {
  scope: "site" | "page";
  tier?: "fast" | "standard" | "deep";
  inputs?: { key: string; label: string; hint?: string;
             multiline?: boolean; required?: boolean }[];
};

type Tool = {
  id: string;
  name: string;
  status: "ready" | "partial" | "needs_key" | "planned";
  kind: "sweep" | "page" | "site" | "report";
  dims: string[];
  does: string;
  spec?: string | null;
  checks?: string[];
  /** Which of `checks` can actually fire with the keys configured here.
   *  A tool used to read "ready" the moment any one of its accepted keys
   *  was present, even when that key supplied none of the data its checks
   *  read. */
  checks_live?: string[];
  checks_dark?: string[];
  dark_note?: string;
  endpoint?: string;
  needs?: string;
  /** A tool may carry its brief under another id (the mobile
   *  sweep's is `mobile-viewport`). */
  expert?: string;
};

type Phase = { phase: string; why: string; tools: Tool[] };

type Playbook = {
  phases: Phase[];
  experts?: Record<string, Brief>;
  summary: { total: number; ready: number; partial: number; needs_key: number;
             planned: number; with_spec: number };
};

const STATUS_LABEL: Record<Tool["status"], string> = {
  ready: "ready", partial: "part measured", needs_key: "needs key",
  planned: "to build",
};

const KIND_LABEL: Record<Tool["kind"], string> = {
  sweep: "runs in every audit of its dimension",
  page: "on demand, one page",
  site: "on demand, whole site",
  report: "produced after a run",
};

export function WorkbenchView({ siteId }: { siteId: string }) {
  const [data, setData] = useState<Playbook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<"all" | "ready" | "planned">("all");
  const [launching, setLaunching] = useState<string | null>(null);
  // Site-scoped briefs read a completed crawl, so the workbench needs one to
  // run them against. Without it the tools are listed but not offered.
  const [latestRun, setLatestRun] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const { data: lanes } = useAnalyses(latestRun, tick);

  useEffect(() => {
    let live = true;
    api.get<Playbook>("/api/playbook")
      .then((d) => {
        if (!live) return;
        setData(d);
        setOpen(new Set([d.phases[0]?.phase]));   // first phase open by default
      })
      .catch((e: ApiError) => { if (live) setError(e.message); });
    api.get<{ runs?: { id: string; status: RunStatus; kind: string }[] }>(
        `/api/sites/${siteId}`)
      .then((s) => { if (live) setLatestRun(completedAudits(s.runs)[0]?.id ?? null); })
      .catch(() => { if (live) setLatestRun(null); });
    return () => { live = false; };
  }, [siteId]);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;

  const toggle = (phase: string) => {
    const next = new Set(open);
    if (next.has(phase)) next.delete(phase); else next.add(phase);
    setOpen(next);
  };

  const runDims = async (tool: Tool) => {
    setLaunching(tool.id);
    try {
      const resp = await api.post<{ run_id: string }>(
        `/api/sites/${siteId}/audits`, { dims: tool.dims, tier: "T2" });
      goto(`#/runs/${resp.run_id}`);
    } finally {
      setLaunching(null);
    }
  };

  const visible = (t: Tool) =>
    filter === "all" ||
    (filter === "ready" && t.status !== "planned") ||
    (filter === "planned" && t.status === "planned");

  const s = data.summary;
  return (
    <>
      <h2>Workbench</h2>
      <p className="muted">
        Every tool in the order you would actually work a site: fix what
        invalidates other work first, and run the cheap automatic checks before the expensive judgement. <strong>{s.ready}</strong> ready ·{" "}
        {s.partial > 0 && (
          <><strong>{s.partial}</strong> running with some checks dark ·{" "}</>
        )}
        <strong>{s.needs_key}</strong> awaiting a provider key ·{" "}
        <strong>{s.planned}</strong> still to build.
      </p>
      {/* Which audit the briefs on this screen read, and a way to it. The
          panels below run against a specific completed audit and store their
          reports against it, so the run page is where those reports live —
          but nothing here named it or linked to it. */}
      <p className="muted wb-run">
        What the suite can do, and what each tool needs — not what has run
        here. For that, and to run one, use the{" "}
        <strong>Analyses</strong> tab.
      </p>
      <div className="filters">
        {(["all", "ready", "planned"] as const).map((f) => (
          <Pill as="button" key={f} tone={filter === f ? "current" : "nav"}
                  onClick={() => setFilter(f)}>
            {f === "all" ? "everything" : f === "ready" ? "built" : "to build"}
          </Pill>
        ))}
        <SecondaryButton onClick={() =>
          setOpen(open.size ? new Set() : new Set(data.phases.map((p) => p.phase)))}>
          {open.size ? "collapse all" : "expand all"}
        </SecondaryButton>
      </div>

      {data.phases.map((phase) => {
        const tools = phase.tools.filter(visible);
        if (!tools.length) return null;
        const ready = phase.tools.filter((t) => t.status === "ready").length;
        const isOpen = open.has(phase.phase);
        return (
          <section key={phase.phase} className="wb-phase">
            {/* A disclosure, so it is a real button — tab stop, Enter and
                Space, and its state announced. */}
            <button type="button" className="wb-head" aria-expanded={isOpen}
                    onClick={() => toggle(phase.phase)}>
              <span className="wb-toggle">{isOpen ? "▾" : "▸"}</span>
              <h3>{phase.phase}</h3>
              <span className="muted wb-count">
                {ready}/{phase.tools.length} ready
              </span>
            </button>
            {isOpen && (
              <>
                <p className="muted wb-why">{phase.why}</p>
                <ul className="wb-tools">
                  {tools.map((tool) => (
                    <li key={tool.id} className={`wb-tool wb-${tool.status}`}>
                      <div className="wb-tool-head">
                        <span className={`pill wb-status-${tool.status}`}>
                          {STATUS_LABEL[tool.status]}
                        </span>
                        <strong>{tool.name}</strong>
                        <span className="muted wb-kind">{KIND_LABEL[tool.kind]}</span>
                      </div>
                      <div className="wb-does">{tool.does}</div>
                      {tool.spec && (
                        <div className="muted wb-spec">Spec: {tool.spec}</div>
                      )}
                      {tool.needs && (
                        <div className="muted wb-spec">Needs: <code>{tool.needs}</code></div>
                      )}
                      {tool.dark_note && (
                        <div className="wb-dark-note">{tool.dark_note}</div>
                      )}
                      {!!tool.checks?.length && (
                        /* A check that cannot fire is struck through and
                           titled with what would free it, so the catalogue
                           reads as capability rather than as intent. */
                        <div className="wb-checks">
                          {tool.checks.map((c) => {
                            const dark = tool.checks_dark?.includes(c);
                            return (
                              <code key={c} className={dark ? "chk-dark" : ""}
                                    title={dark ? "No configured provider supplies "
                                                  + "the data this check reads"
                                                : undefined}>
                                {c}
                                {dark && <span className="sr-only"> — cannot run here</span>}
                              </code>
                            );
                          })}
                        </div>
                      )}
                      <div className="wb-actions">
                        {/* No run control for a tool whose key is absent:
                            external data is an optional enhancer, and a
                            button that runs degraded invites confusion. The
                            "needs" line already says what to configure. */}
                        {tool.status === "ready" && tool.kind === "sweep"
                          && tool.dims.length > 0 && (
                          /* UX-66. Stable caption, state on `aria-busy`, words
                             in the unconditionally-mounted region beside it —
                             the convention `views.tsx`'s `ReportView` states in full.
                             The region names the tool because these controls
                             repeat once per tool and only one can launch. */
                          <>
                            <SpendButton price={null} busy={launching === tool.id}
                                         why={launching !== null && launching !== tool.id
                                           ? "another audit is launching" : null}
                                         confirm={{ title: `Run a ${tool.dims.join("+")} audit?`,
                                                    body: <><SpendTarget />
                                                      <p>A Standard (T2) audit of {tool.dims.join(", ")},
                                                        up to 100 pages.</p></>,
                                                    action: "Run the audit" }}
                                         onSpend={() => runDims(tool)}>
                              run {tool.dims.join("+")} audit
                            </SpendButton>
                            <span className="muted" role="status" aria-live="polite">
                              {launching === tool.id
                                && <Working>{`Launching the ${tool.dims.join("+")} audit…`}</Working>}
                            </span>
                          </>
                        )}
                        {tool.status === "ready" && tool.kind === "page" && (
                          <LinkButton href="#/tools">
                            run on a page →
                          </LinkButton>
                        )}
                        {tool.status === "planned" && (
                          <span className="muted">
                            awaiting its expert specification
                          </span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
                {/* No analysis list here.
                    This phase used to render the same rows the Analyses tab
                    shows in its two lanes — the same component, reading the
                    same endpoint, one screen apart. Eleven phases of it made
                    the workbench 1798px of state that was already stated
                    better elsewhere.

                    The two have different jobs and now keep to them: this is
                    the catalogue — every tool, what it does, which of its
                    checks can fire with the keys configured — and Analyses is
                    what has run against this site. */}
              </>
            )}
          </section>
        );
      })}
    </>
  );
}
