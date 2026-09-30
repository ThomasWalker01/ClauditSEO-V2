import { PrimaryButton, SecondaryButton } from "./buttons";
import { GlossaryView } from "./glossary";
import { FormEvent, Fragment, useCallback, useEffect, useState } from "react";
import { ApiError, api, classify, describe, getToken, setToken } from "./api";
import { applyBrandFavicon } from "./favicon";
import {
  ChatView, CompareView, LauncherView,
  PageDetailView, ReportView, RunDetailView, SiteDetailView, paneLabel,
} from "./views";
import { WorkbenchView } from "./workbench";
import { ReportsView } from "./reports";
import { DeliverableView } from "./deliverable";
import { AdminView } from "./admin";
import { goto } from "./nav";
import { PageDossierView } from "./dossier";
import { SelectionProvider, SiteSearch } from "./selection";
import { HomeView } from "./home";
import { ButtonsView } from "./buttons_ref";
import { host, useSelection } from "./selection";

/* The hold is NOT in the bar. Item 178 (UI audit 08-3) put it beside the nav's
 * Reports link, on the rule that every route to the report says the same thing.
 * Removed 2026-09-18 on the operator's decision, for two reasons they gave and
 * one this measured:
 *
 *   - Said in four places at once, the words stopped carrying: the landing's
 *     button, the strip's Deliver chapter, the step's own pill, and here.
 *   - The bar is global chrome. A hold belongs to one audit of one site, and
 *     the bar is the one place on the screen that is about neither.
 *   - 187px of words in a row that had been measured full: the band 1120-1386px
 *     scrolled the whole page sideways, with Glossary and Admin off the screen.
 *
 * What 08-3 was actually about survives, and is guarded: pressing Reports while
 * a report is held arrives at a Generate that is held and says why, with the way
 * to triage beside it. The journey is stopped at the thing it would have done,
 * not announced in the furniture.
 */
function useHash(): string {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

/* A screen's name comes from `views.tsx` (item 181, UI audit 11-11, 01-17;
 * item 184). There was a `PANE_NAMES` map here, keyed on the raw `?tab=` word:
 * it named the word asked for rather than the pane that answered, so `?tab=
 * triage` titled the tab "Triage" over a screen whose heading, landmark and
 * content were all "Audit" - and `?tab=nonsense` titled it "Client" over
 * Analyses. `paneLabel` resolves the alias the same way the pane does, which is
 * the only way the two can agree. */

export function screenName(hash: string): { screen: string; site: boolean; ownHeading: boolean } {
  const [path, query = ""] = hash.split("?");
  const parts = path.replace(/^#\//, "").split("/").filter(Boolean);
  const q = new URLSearchParams(query);
  if (!parts.length) return { screen: "Home", site: false, ownHeading: false };
  if (parts[0] === "sites" && parts[1]) {
    const sub = parts[2];
    if (sub === "reports") return { screen: "Reports", site: true, ownHeading: false };
    if (sub === "launch") return { screen: "Run an audit", site: true, ownHeading: false };
    if (sub === "workbench") return { screen: "Workbench", site: true, ownHeading: false };
    if (sub === "dossier") return { screen: "Page", site: true, ownHeading: false };
    if (sub === "chat") return { screen: "Chat", site: true, ownHeading: false };
    const tab = q.get("tab") ?? "landing";
    const part = q.get("part");
    // The client screen draws its own h1 (StandingHeader): the headline on the
    // landing, the pane's name elsewhere.
    const pane = paneLabel(tab);
    return { screen: part ? `${pane} · ${part}` : pane, site: true, ownHeading: true };
  }
  if (parts[0] === "runs") return { screen: parts[2] === "page" ? "Page in an audit" : "Audit run", site: true, ownHeading: false };
  if (parts[0] === "reports") return { screen: "Report", site: true, ownHeading: false };
  if (parts[0] === "client-reports") return { screen: "Delivered report", site: false, ownHeading: false };
  if (parts[0] === "compare") return { screen: "Compare audits", site: false, ownHeading: false };
  if (parts[0] === "admin") {
    const tab = q.get("tab");
    return { screen: tab ? `Admin · ${tab[0].toUpperCase()}${tab.slice(1)}` : "Admin", site: false, ownHeading: false };
  }
  if (parts[0] === "glossary") return { screen: "Glossary", site: false, ownHeading: false };
  if (parts[0] === "buttons") return { screen: "Buttons", site: false, ownHeading: false };
  if (parts[0] === "client") return { screen: "Client", site: true, ownHeading: false };
  return { screen: "ClauditSEO", site: false, ownHeading: false };
}

/** A route that is not a screen any more: it sends the reader where the
 *  capability went (item 188). Rendered for one paint, which is why it draws
 *  the sentence rather than nothing - a blank screen with a title is what a
 *  broken route looks like, and this one is not broken. */
function Redirect({ to }: { to: string }) {
  useEffect(() => { goto(to); }, [to]);
  return <p className="muted">Taking you to where this moved…</p>;
}

/** The document title and, where the screen has none of its own, its h1. */
function PageTitle() {
  const hash = useHash();
  const { site } = useSelection();
  const { screen, site: bySite, ownHeading } = screenName(hash);
  const where = bySite && site ? host(site.domain) : "";
  useEffect(() => {
    document.title = [screen, where, "ClauditSEO"].filter(Boolean).join(" · ");
  }, [screen, where]);
  if (ownHeading) return null;
  return <h1 className="sr-only page-h1">{screen}{where ? ` · ${where}` : ""}</h1>;
}

function Router() {
  const hash = useHash();
  // Split the query off before the path. `#/sites/abc?run=xyz` otherwise
  // parses as a site whose id ends in "?run=xyz", which renders nothing and
  // says nothing about why.
  const [path] = hash.split("?");
  const parts = path.replace(/^#\//, "").split("/").filter(Boolean);

  // The client list and client detail screens are retired: Home shows every
  // site with its schedule, the site screen shows one site's work, and the
  // only thing left on the old pair was five quick-audit preset buttons per
  // row from before the tool catalogue existed. Old links still resolve.
  // Deletion moved to Home (item 169).
  if (parts[0] === "clients") return <ToHome />;
  // The button reference (item 182): every variant, live and held.
  if (parts[0] === "buttons") return <ButtonsView />;
  if (parts[0] === "sites" && parts[1] && parts[2] === "launch")
    return <LauncherView siteId={parts[1]} />;
  if (parts[0] === "sites" && parts[1] && parts[2] === "chat")
    return <ChatView siteId={parts[1]} />;
  if (parts[0] === "sites" && parts[1] && parts[2] === "workbench")
    return <WorkbenchView siteId={parts[1]} />;
  // Site-scoped, so it cannot collide with `#/reports/<run>` — the single
  // client deliverable for one audit, which is a different thing entirely.
  if (parts[0] === "sites" && parts[1] && parts[2] === "reports")
    return <ReportsView siteId={parts[1]} />;
  if (parts[0] === "sites" && parts[1] && parts[2] === "dossier" && parts[3])
    return <PageDossierView siteId={parts[1]} url={decodeURIComponent(parts[3])} />;
  if (parts[0] === "sites" && parts[1]) return <SiteDetailView siteId={parts[1]} />;
  if (parts[0] === "runs" && parts[1] && parts[2] === "page" && parts[3])
    return <PageDetailView runId={parts[1]} url={decodeURIComponent(parts[3])} />;
  if (parts[0] === "runs" && parts[1]) return <RunDetailView runId={parts[1]} />;
  if (parts[0] === "compare" && parts[1] && parts[2])
    return <CompareView a={parts[1]} b={parts[2]} />;
  // A stored deliverable, distinct from `#/reports/<run>` which GENERATES
  // one. Reading what was delivered and producing something new are
  // different acts and must not share a route.
  if (parts[0] === "client-reports" && parts[1])
    return <DeliverableView reportId={parts[1]} />;
  if (parts[0] === "reports" && parts[1]) return <ReportView runId={parts[1]} />;
  // Item 188: Tools is retired. Its batch runner is superseded by the
  // per-site surfaces on the client page - the Analyses catalogue's own
  // "Run all", a part page's "Run analysis", the Audit pane and Triage - and
  // the screen is gone rather than kept as a second door to them.
  //
  // A redirect rather than a fall-through, because `#/tools/<site>/<tool>`
  // carried the site it was scoped to and that scope is the half worth
  // keeping: a stored link lands on the Analyses catalogue of the site it
  // named. Bare `#/tools` has no site to carry, so it lands on the list.
  if (parts[0] === "tools")
    return <Redirect to={parts[1] ? `#/sites/${parts[1]}?tab=findings` : "#/"} />;
  if (parts[0] === "admin") return <AdminView />;
  // Reference, not a destination (item 166): the registry, whole.
  if (parts[0] === "glossary")
    return <GlossaryView term={new URLSearchParams(hash.split("?")[1] ?? "").get("term") ?? undefined} />;
  // "Client" in the nav is a verb, not a URL: it means "the site I am
  // working on", which only the selection knows.
  if (parts[0] === "client") return <ToSelectedSite />;
  // Same trick as Client: "Reports" in the nav means "for the site I am
  // working on", which only the selection knows.
  if (parts[0] === "reports") return <ToSelectedSite tail="/reports" />;
  return <HomeView />;
}

function ToHome() {
  useEffect(() => { window.location.replace("#/"); }, []);
  return <p className="muted">Opening…</p>;
}

function ToSelectedSite({ tail = "" }: { tail?: string } = {}) {
  const { siteId, sites } = useSelection();
  useEffect(() => {
    if (siteId) window.location.replace(`#/sites/${siteId}${tail}`);
  }, [siteId, tail]);
  if (!sites.length)
    return <p className="muted">No sites yet — add one from Home.</p>;
  return <p className="muted">Opening…</p>;
}

function LoginGate({ onOk }: { onOk: () => void }) {
  const [token, setTokenInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setToken(token.trim());
    try {
      await api.get("/api/clients");
      onOk();
    } catch (err) {
      // Three answers, not two. `(err as ApiError).message` on a rejected
      // `fetch` is "Failed to fetch", which the operator reads as "my token
      // is wrong" on the one screen that is entirely about the token — so an
      // outage sent them looking for a credential that was never the problem.
      const kind = classify(err);
      setError(kind === "auth"
        ? "Token rejected — check CLAUDITSEO_TOKEN on the server."
        : kind === "unreachable"
        ? `The server did not answer, so the sign-in could not be checked — ${describe(err)}`
        : describe(err));
    }
  };

  return (
    <main className="shell">
      <header><h1>ClauditSEO</h1><p className="tagline">Operator login</p></header>
      <form onSubmit={submit} className="inline-form">
        <input type="password" value={token} placeholder="operator token"
               onChange={(e) => setTokenInput(e.target.value)} autoFocus />
        <PrimaryButton submit>Sign in</PrimaryButton>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </main>
  );
}

/** What a server that is not answering looks like: itself, and nothing else.
 *
 *  Deliberately not the shell. Rendering the topbar with empty panels behind
 *  it is the defect (UX-06) — a signed-in dashboard reporting no clients is
 *  pixel-identical to a working install nobody has used yet, and the operator
 *  has no way to tell which they are looking at. So the outage replaces the
 *  screen rather than decorating it.
 *
 *  `role="alert"` because the operator is not looking for this and has to be
 *  told rather than left to notice. The reason first written here — "this
 *  state arrives after paint, on a page that already looked like it was
 *  loading normally" — was never true of the code beside it (CQ-165). The
 *  boot probe renders nothing until it settles, so the only document this
 *  screen has ever replaced is an empty one. The retry no longer replaces it
 *  with another (UX-71); the mounting-with-its-first-content shape that
 *  leaves is UX-69, accepted as is at `audits/DISPOSITIONS.md:213`, and is
 *  not re-argued here.
 *
 *  `answered` is the difference between a process that is up and broken and
 *  nothing listening at all. `classify` calls both unreachable, correctly —
 *  neither is a fact about the operator's token — but they are not the same
 *  sentence, and printing "the server did not answer" one line above the 503
 *  it sent is this screen disproving itself on its own evidence line
 *  (UX-72). */
function Unreachable(
  { detail, answered, retrying, onRetry }: {
    detail: string;
    answered: boolean;
    retrying: boolean;
    onRetry: () => void;
  },
) {
  return (
    <main className="shell">
      <header><h1>ClauditSEO</h1><p className="tagline">Server unreachable</p></header>
      <p className="error server-down" role="alert">
        {answered
          ? "The server answered with an error."
          : "The server did not answer."}{" "}
        Nothing on this page is known to be empty — it is unknown, which is a
        different thing.
      </p>
      <p className="muted">{detail}</p>
      {/* Disabled while a probe is in flight, and a sentence beside it saying
          why. A control that greys out with nothing next to it reads as
          broken rather than as busy, which is the same misreading this whole
          screen exists to prevent. */}
      <SecondaryButton onClick={onRetry} disabled={retrying}>Try again</SecondaryButton>
      {retrying && (
        <p className="muted" role="status">Checking the server…</p>
      )}
    </main>
  );
}

export default function App() {
  const [authState, setAuthState] =
    useState<"checking" | "need-token" | "unreachable" | "ok">("checking");
  const [outage, setOutage] = useState("");
  const [answered, setAnswered] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const hash = useHash();          // the shell width follows the route

  //: The boot probe, named so the outage screen can run it again. Retrying is
  //: the whole affordance that screen offers, and a reload would throw away
  //: the route the operator was on to answer a question about the server.
  //:
  //: `again` is the whole of UX-71, and it separates two things that were one
  //: call. The same request is being made either way; what differs is what is
  //: already on the screen. At boot nothing has painted, so entering
  //: `checking` — which `App` renders as `null` — costs nothing. A retry is
  //: pressed *on* the outage screen, so entering that same state unmounts the
  //: screen the button is on and leaves an empty document for however long
  //: the request takes, which for a genuinely unreachable host is a TCP
  //: timeout rather than a moment. So the retry reports itself in place and
  //: never re-enters `checking`.
  const probe = useCallback((again = false) => {
    if (again) setRetrying(true);
    else setAuthState("checking");
    api.get("/api/clients")
      .then(() => setAuthState("ok"))
      .catch((err: unknown) => {
        const kind = classify(err);
        if (kind === "auth") {
          setToken("");
          setAuthState("need-token");
        } else if (kind === "unreachable") {
          setOutage(describe(err));
          // An `ApiError` only exists because a response came back to read a
          // status off. A rejected `fetch` never gets that far.
          setAnswered(err instanceof ApiError);
          setAuthState("unreachable");
        } else setAuthState("ok"); // a 4xx that a view can report in its terms
      })
      .finally(() => setRetrying(false));
  }, []);

  useEffect(() => { probe(); }, [probe]);

  // Once there is a session, ask what the tab icon should be. Not before:
  // /api/brand is guarded, and a 401 here would be noise on the way to the
  // login gate (FEATURES.md F-08).
  useEffect(() => {
    if (authState === "ok") void applyBrandFavicon();
  }, [authState]);

  if (authState === "checking") return null;
  if (authState === "need-token") return <LoginGate onOk={() => setAuthState("ok")} />;
  if (authState === "unreachable") {
    // An arrow, not `probe` itself: passed bare it would receive the
    // click event as `again`, which is truthy, and the boot path would
    // never be the one taken.
    return <Unreachable detail={outage} answered={answered}
                        retrying={retrying} onRetry={() => probe(true)} />;
  }

  // One width everywhere. Widening only the tools route made the whole page
  // jump when switching sections, which reads worse than the long line lengths
  // it was avoiding — those are handled by capping prose inside the report.
  return (
    <SelectionProvider>
    <main className="shell">
      {/* Bypass block (WCAG 2.4.1). The client screen carries twenty-six
          tab stops of standing position, strip and reference row before its
          pane, on every pane; without this a keyboard walked all of them on
          every move between panes (audit F-20). The target is the pane
          where a screen has one, else the routed content. An anchor, so it
          is a link to a screen reader's link list; the click is intercepted
          because `#pane` would otherwise be read as a route. */}
      <a className="skip" href="#pane"
         onClick={(e) => {
           e.preventDefault();
           const el = document.getElementById("pane")
             ?? document.getElementById("content");
           // `focus()` brings the target into view on its own; the one
           // scroll convention in the tree is for a message, not a landing.
           el?.focus();
         }}>
        Skip to the content
      </a>
      <header className="topbar">
        {/* Item 181 (11-11, 02-9): the brand is a link, not the page's heading.
            The h1 names the screen: `PageTitle` below, or the landing's headline. */}
        <p className="brand"><a href="#/" className="homelink">ClauditSEO</a></p>
        {/* Beside the logo, so switching client works from every screen
            rather than only from the one that happened to own a dropdown.
            The tagline gave up its space: it said the same thing on every
            visit, and this is used on most of them. */}
        <SiteSearch />
        {/* Item 173 (channel ruling 20260917-1125): a client screen's own
            context - the audit it reads, the mode, the page filter, its
            reference links - joins the bar here, after the site it narrows.
            Filled by `StandingHeader` through a portal; empty elsewhere. */}
        <div id="topbar-context" className="topbar-context" />
        {/* Item 174 (channel ruling 20260917-1430): a client screen's reference
            panes, Pages and Notes, beside the screens they sit with - pane
            navigation next to app navigation, a divider between, both always
            visible. Filled by `StandingHeader`; empty elsewhere. */}
        <div id="topbar-refs" className="topbar-refs" />
        <nav className="topnav" aria-label="Screens">
          {([["#/", "Home", (h: string) => h === "#/" || h === ""],
             // Not simply "any #/sites/ route": Reports lives under one too,
             // so both entries lit at once until this excluded it.
             ["#/client", "Client", (h: string) => (h.startsWith("#/sites/")
                                                    && !h.includes("/reports"))
                                                    || h.startsWith("#/client")],
             ["#/reports", "Reports", (h: string) => h.endsWith("/reports")
                                                     || h === "#/reports"],
             ["#/admin", "Admin", (h: string) => h.startsWith("#/admin")],
             // The one link in the bar to the glossary (item 166).
             ["#/glossary", "Glossary", (h: string) => h.startsWith("#/glossary")]] as const)
            .map(([href, label, active]) => (
              <Fragment key={href}>
                <a href={href}
                   className={`navbtn${active(hash) ? " navbtn-on" : ""}`}
                   aria-current={active(hash) ? "page" : undefined}>
                  {label}
                </a>
              </Fragment>
            ))}
        </nav>
        {getToken() && (
          <SecondaryButton onClick={() => { setToken(""); window.location.reload(); }}>
            Sign out
          </SecondaryButton>
        )}
      </header>
      {/* The skip link's target on screens with no pane of their own. */}
      <div id="content" tabIndex={-1}>
        <PageTitle />
        <Router />
      </div>
    </main>
    </SelectionProvider>
  );
}
