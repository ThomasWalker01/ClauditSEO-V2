/**
 * Open work, sorted the way a page is built.
 *
 * The dimensions the engine uses (TEC, ONP, CNT…) are how it is organised.
 * They are not how anyone repairs a site: you open a page in a CMS and you
 * fix its title, its headings, its images. This is the same findings, re-cut
 * along that grain — the server does the sorting so the totals cannot drift
 * from what the rest of the app reports.
 *
 * The co-occurrence marking is the part worth understanding. Selecting a
 * category highlights any other that affects substantially the same pages,
 * because that is almost always one template rather than several separate
 * problems. On the site this was built against, three categories holding 337
 * of 360 findings share the same 99 pages.
 */
import { heldRecordHref } from "./report_hold";
import { Working } from "./working";
import { LinkButton, PrimaryButton, SecondaryButton } from "./buttons";
import { sourceWord } from "./glossary";
import { CatalogueList, notRunCount } from "./catalogue";
import { LOADING_WORD, Legend } from "./glossary";
import { SpendButton, SpendTarget } from "./spend";
import { REPORT_HELD_WORD, heldWords } from "./report_hold";
import { MeasureLine } from "./measure";
import { partMeasure } from "./part_page";
import { Barrier, FixOrder } from "./a11y_fixorder";
import { HeadersGrid } from "./headers_grid";
import { SnippetField, TitleLengths } from "./title_snippet";
import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CANDIDATE_NOTE, FindingState, SOURCES_NOTE, WatchChange, api, completedAudits, hasScore,
         isInFlight, narrowPickNote, scopeOf, scopeWord, useFetch, useLoaded } from "./api";
import { costFromHash } from "./cost";
import { CrawlDepth, CrawlDepthBlock, depthFromHash, depthPicked, pagesAtDepth,
         setDepthInHash } from "./crawl_depth";
import { CrawlNow, CrawlNowBlock } from "./crawl_now";
import { IndexabilityNow, IndexabilityNowBlock } from "./indexability_now";
import { UrlsNow, UrlsNowBlock } from "./urls_now";
import { SpeedActions, SpeedNow, SpeedNowBlock } from "./speed_now";
import { ImageBudgetPayload } from "./images_budget";
import { CanonicalChains, CanonicalChainsBlock, Chain } from "./canonical_chains";
import { goHandler, goto, pageScopeFromHash, withPageScope } from "./nav";
import { Pill, type Tone } from "./pill";
import { Precheck, PrecheckCompare, usePrecheck, usePrecheckCompare } from "./precheck";
import { useSelection, host } from "./selection";
import type { AgeThresholds } from "./age";
import { DEPTH_TIER, DrawerFinding, ReauditDrawer } from "./reaudit";
import { DepthKey } from "./scanmatrix";
import { ReportView } from "./markdown";
import { Contract, ContractAccount } from "./expert";
import { PART_RENDERERS, PartPage, SweepRun, belongsTo } from "./part_page";
import { ClientLanes, IntegrityLine, ModeArith, PartSwitcher, PrimaryAction, stamp,
         StateSentence } from "./client_lanes";
import { Count, Counted, CoverageLine, Headline, Populations,
         Prevalence, makeCount, pathKey, prevalence } from "./population";
import { Alerts, Card, ErrorNote, Loading, ScoreBadge, ScoreBandKey, SpendMark, money,
         UrlLinks, pathOf } from "./components";
import { PageAdvice, SchemaAuditPanel } from "./advice";
import { Analysis, Lanes, useAnalyses } from "./analyses";
import { FixCol, FixState, FixTick, MarkBar, useFixLoop, useSeed,
} from "./fixloop";
import {
  Figures, LookDot, LookLegend, Pane, Panes, ReportHead,
} from "./panels";

type Finding = {
  fingerprint: string; check_id: string; dimension: string;
  severity: string; summary: string; state: string;
  /** "deterministic" (the sweep) or "model-judgement" (a brief). */
  source: string;
  recommendation: string; pages: number; urls: string[];
  /** A conforming brief's row (brief v10 step AF): the recommendation is
   *  the copy it proposed, and `brief_status` is what it gave the row. */
  contract?: boolean; brief_status?: string | null; brief?: string | null;
  /** How many URLs the check found before it capped its own list, or `null`
   *  where the row predates the column that stores it (migration 0030).
   *
   *  The third of three counts, and the one that was missing: `total` is what
   *  was found, `pages` is what the emitter kept, `urls.length` is what this
   *  payload carries. Without it the disclosure below stated the payload's
   *  cut against the emitter's and called the emitter's the total (UX-93,
   *  `QUESTIONS.md` Q-26). `null` is *unknown* and is never treated as
   *  "the list is whole" - that is the claim this field exists to stop being
   *  made without evidence. */
  total: number | null;
  /** Whether a crawl could look again at this one. Neither count beside it
   *  answers that: `pages` counts entries that need not be URLs and `urls` is
   *  truncated to ten. Decided by `runs.names_a_page`, the rule the verify
   *  route refuses on. */
  names_a_page: boolean;
  /** "I have fixed this — check it next time". Not a state: only a crawl
   *  that looks again may change the record. */
  attempted_at?: string | null;
  attempt_note?: string | null;
  /** The tool that judges this check, or null if nothing does (F-02).
   *  Decided on the server; a null means this row offers no specialist at
   *  all, rather than one that would run the wrong tool. */
  specialist?: string | null;
  /** Where in the page's outline this finding's fault sits, 0-based
   *  (F-07). Only `heading-skip` carries one, and only since the check
   *  began recording it — absent on every finding stored before that, and
   *  absent rather than defaulted, so the screen can tell "nobody measured
   *  this" from "the fault is at the top". */
  outline_index?: number;
};

/** The smallest run the engine can be asked for that refreshes a section,
 *  and the other sections that move with it.
 *
 *  The screen groups by section and the engine is asked in dimensions, so
 *  "refresh Headings" has no unit of its own — ONP is the smallest thing
 *  that covers it, and four other sections come along. `also` is what that
 *  costs, stated before the click rather than discovered after it.
 *
 *  Null means no sweep refreshes this section at all (Links on the page,
 *  URLs & parameters, International). A different answer from "not
 *  measured", and the reason the server sends the key either way.
 *
 *  `per_page` is whether naming a page narrows this offer at all (UX-39).
 *  Decided on the server from the engine's `measured_per_page` declarations
 *  — each module stating whether any of its findings can be measured against
 *  a single page — for the same reason `names_a_page` is: the answer is a
 *  property of the modules, which this screen cannot see. False for
 *  Backlinks alone, whose five OFP checks all read the domain's backlink
 *  profile — so a page refresh there re-reads a page, bills for it, and
 *  cannot move a single finding.
 *
 *  Not `group`: Speed, Mobile, Security, Indexability, AI surface and Local
 *  & citations all sit outside `on the page` as a heading and are every one
 *  of them measurable against a single page. `QUESTIONS.md` Q-17. */
type Refresh = { dimension: string; also: string[]; per_page: boolean };

export type Category = {
  key: string; label: string; group: string; blurb: string;
  /** The findings counts, each carrying the population it was gathered over
   *  (item 156, completing 155). These were plain integers, with a `counts`
   *  sibling beside them, and 155's report said what that left open: a
   *  component written next month could read `part.total` and render it bare,
   *  and no test would notice, because the rule lived in a convention about
   *  which field to read rather than in the type of the field. That is the
   *  exact shape of 139a.
   *
   *  `of` is null on all three — a findings count is not a subset of a page
   *  set, so `12 of 68` would divide two different things, and `Counted`
   *  renders it plain. Arithmetic reads `.value`, and the breakage of every
   *  consumer that did not is the audit of who was reading it bare. */
  open: Count; regressed: Count; total: Count;
  /** Pages carrying an open finding in this part — a count over the RECORD,
   *  and it says so (item 155). Not the pages this run fetched: open state is
   *  site-scoped, so a finding raised by an older run and never fixed still
   *  counts its page here. The screen had no way to know that until the count
   *  carried its population. */
  pages: Count;
  tools: string[]; findings: Finding[];
  /** Findings filed here and seen once, not yet confirmed (item 180, e2). */
  seen_once?: Count;
  /** Every check a brief writing to this part may emit (brief v11 step
   *  AH): the part page lists them all, `0` where the record holds none. */
  brief_checks?: string[];
  /** Every check id the engine filed under this part (brief v25 step BP). */
  filed_checks?: string[];
  /** Which of those this run could not measure, and why (item 157). THE
   *  RULE, stated in `playbook.py`: a check may be reported as passing only
   *  if the run measured it; absence of a finding is not a pass.
   *
   *  Keyed by the full `DIM/check` id, valued with the because-clause. One
   *  state carrying a reason rather than a state per cause - a status enum
   *  grows a member per cause and every call site switching on it has to
   *  learn each one (channel 20260912-0940).
   *
   *  Historical, not current: read from the run's own dimension list and
   *  stored evidence, never from the config. A renderer installed tomorrow
   *  must not rewrite what a June run claims to have measured. */
  not_assessed?: Record<string, string>;
  /** The part's checks no playbook tool names at all (item 157): 53 across
   *  the briefs, mostly the analysis checks a brief judges and no sweep
   *  emits. Declared rather than left to absence, because a check missing
   *  from the gating map must not read as "gated and live". Not a claim
   *  that the check failed or passed - only that nothing gates it. */
  unclaimed_checks?: string[];
  /** What each of those costs to answer (brief v17 step AV1): `free` where
   *  the sweep emits it, `model` where only a brief can. The part page
   *  splits on this, because "here is what we found for nothing" is the
   *  first half of every conversation about an audit. */
  check_cost?: Record<string, string>;
  /** The part's checks that can only ever be held, with what each is held
   *  for (brief v15 step AR). Present whether or not a brief has run. */
  brief_held_only?: { check: string; needs: string }[];
  /** Brief v20's block keys (items 147, 148). Each is a fact about a GROUP of
   *  pages -- a template, a locale set, a fix serving several templates -- so
   *  none could be carried by a row, which is why they ride beside them the
   *  way `brief_map` and `brief_clusters` already do.
   *
   *  `brief_fixes` is shared by both parts: the fix is stored once and each
   *  row points at it by `fix_id`, because one change repeated per row is how
   *  a single markup fix came to read as six on the Images part. */
  brief_templates?: Record<string, unknown>[];
  /** An OBJECT -- `{observed, stated, basis, conflict}` -- not a list. */
  brief_locales?: { observed?: string[]; stated?: string[]; basis?: string;
                    conflict?: string | null } | null;
  brief_fixes?: Record<string, unknown>[];
  /** The schema version the block declared (`mobile/2`, `intl/2`), so a
   *  screen can tell which shape it is drawing rather than inferring it from
   *  which keys happen to be present. */
  brief_schema?: string | null;
  /** Why a gated brief was NOT dispatched, derived on read from the run's own
   *  evidence (item 148 G6, brief 160 step 6). `na` is settled and a zero under
   *  the part is honest; `not_assessed` is not. Null where the brief would run.
   *  Nothing stores a refusal, and nothing needs to: the gate is a pure
   *  function of the evidence, so reading it again cannot go stale. */
  gate?: { state: "na" | "not_assessed"; reason: string } | null;
  /** Security's nine domains with their layer and checks (item 143 addendum). */
  sec_domains?: Record<string, { name: string; layer: string; checks: string[] }>;
  /** The Security brief's "now", newest brief (item 143 step BD). */
  /** The AI surface part's reachability, from the run's evidence (item 145 BH). */
  ai_now?: import("./ai_surface").AiNow | null;
  /** The AI surface brief's block beside its rows, newest run's (item 145 BH). */
  brief_ai_surface?: import("./ai_surface").AiBrief;
  brief_security?: {
    compromise?: { verdict?: string; basis?: string } | null;
    ledger?: { domain: string; status: string; missing?: string; summary?: string }[] | null;
    do_not_spend_on?: { control: string; why: string }[] | null;
  } | null;
  /** The part's checks that were measured on TRACED pages only, and how many
   *  pages that was, so a clean line can state the denominator each check was
   *  actually read over (item 155, brief 160). */
  trace_derived?: string[];
  traced_pages?: number | null;
  /** Rows the parser dropped from, and rows not assessable in, the latest
   *  run of each brief writing to this part (brief v12 step AL). */
  brief_dropped?: number;
  /** The analysis's assessment section as the model wrote it (item 210). */
  brief_prose?: string | null;
  /** The dropped rows with their reasons (item 209), capped at 200. */
  brief_dropped_rows?: { check: string; page: string | null; reason: string }[];
  brief_not_assessable?: number;
  /** The rows the brief could not assess, each naming the input it needs;
   *  the run that produced them; and the brief's own verdict sentence
   *  (brief v13 step AO). The part page states the run rather than
   *  marking it with a dot, and a held check gets a card, not a
   *  bracketed placeholder. */
  brief_held?: { check: string; page: string; needs: string; image?: string | null }[];
  /** The two verdicts that are not findings (brief v16 step AS): a page
   *  can be ineligible for a rich result with nothing wrong with its
   *  markup, and the site's entity shape is a fact about the site rather
   *  than about any page. Both render above the fixes. */
  brief_eligibility?: { page: string; rich_result: string; verdict: string;
                        reason?: string }[];
  brief_entity?: { verdict: string; reason?: string } | null;
  /** The Structured data picture, as a model the engine built (brief v16a
   *  step AT-b). Present on the `schema` part of a per-page payload and
   *  nowhere else: a graph of JSON-LD nodes is not a shape the other parts
   *  have anything to draw. Null on a run crawled before `jsonld_raw`
   *  existed, and the part page then draws the block cards it drew before
   *  - a smaller answer rather than a wrong one. */
  graph?: SchemaGraphModel | null;
  /** Coverage's topical map and Cannibalisation's clusters (brief v17
   *  step AX). Facts about groups of pages rather than about one, so they
   *  ride beside the rows the way the two verdicts above do: the whole-
   *  site view draws the map, and a cluster is about which of four pages
   *  wins, which no row about one page could carry. */
  /** Coverage's map, in the prompt's own key names — read off the first
   *  Birch run rather than assumed. `status` is Covered / Partial /
   *  Missing and `pages` is the list, which is more than one for a node
   *  two pages both answer; the renderer guessed `state` and `url` and
   *  drew twenty-two blank cells. */
  brief_map?: { service?: string; node?: string; status?: string;
                type?: string; pages?: string[]; priority?: number }[];
  brief_clusters?: { cluster?: string; survivor?: string; pages?: string[];
                     rule?: string; note?: string }[];
  brief_run?: { tool: string; model: string | null; at: string; run_id: string;
                rows: number; cost: number | null; status?: string | null;
                /** Readings of the site since the audit this analysis read
                 *  (the Reports screen's count, on the part page). */
                audits_since?: number | null;
                /** The crawl it read, and the newest automatic measurement of
                 *  the part's checks after it, or null (item 239 step 4). */
                crawl_at?: string | null; checked_since?: string | null } | null;
  brief_summary?: string | null;
  /** The smallest refresh this section can start, or null if nothing
   *  refreshes it. Derived on the server from the dimension table, so a
   *  module gaining a category changes what the control says it will
   *  touch without this screen knowing anything about it. */
  refresh?: Refresh | null;
  /** Whether the catalogue lists any analysis for this part (item 180, as
   *  narrowed by the channel on 2026-09-24). */
  catalogued?: boolean;
  /** The latest audit that measured this part's dimension (item 212). */
  sweep_run?: SweepRun | null;
  /** The dates the part's items were measured on, and the ages at which a
   *  date says it may be, or is, out of date (item 239 step 6). */
  measured_range?: { from: string; to: string; reference_at: string;
                     rechecked_pages: number; rechecked_at: string | null } | null;
  age_thresholds?: AgeThresholds | null;
  /** Item 243: the page in view has left the site, as this part's reference
   *  crawls saw it: the date they last fetched it. Absent or null otherwise. */
  gone_since?: string | null;
  /** What is left in this category's tool list once the read and run pills
   *  above have taken theirs. "page" runs on one page and has its own panel;
   *  "sweep" ran inside the audit and has nothing to start. */
  investigate?: { tool: string;
                  action: "page" | "sweep" | "planned" | "needs_key" }[];
  /** Check ids raised by both a sweep and a brief in this category. */
  contested?: string[];
  /** Which analyses have read this category, are reading it, and could. A
   *  count says how much is wrong; these say whether anyone has looked. */
  analysed_by?: string[];
  /** Coverage notes among the findings, not in `total` (brief v5 step S). */
  notes?: number;
  /** The newest run of each analysis that read this part (item 239 step 4),
   *  the rule the rows beneath read: each pill opens the report on its run. */
  analysed?: { tool: string; run_id: string; at: string | null;
               crawl_at: string | null; audits_since: number | null }[];
  analysing?: string[];
  can_run?: string[];
  /** Pages by clicks from the home page, for the audit the pane is reading
   *  (brief v16b). On the `crawl` part and nowhere else: a histogram of
   *  reachability is not a shape the other parts have anything to draw, and
   *  it is the one part whose subject it is. Null where there is no stored
   *  crawl to read at all — which is a different answer from a crawl that
   *  recorded no depth, and that one arrives with `recorded: false`. */
  depth?: CrawlDepth | null;
  /** The Crawl part's site-level "now" (brief v18 step AZ): the four counts
   *  (published · in sitemap · reached · render-only), the venn they
   *  decompose into, and the UA matrix. On the `crawl` part alone, for the
   *  reason `depth` gives. Null where there is no stored crawl to read;
   *  `ua_matrix` is null on a run that captured no matrix pass. */
  crawl_now?: CrawlNow | null;
  /** The Indexability part's site-level "now" (brief v18 step BA): the four
   *  headline counts and the canonical map. On the `indexability` part alone.
   *  Null where there is no stored crawl to read. */
  indexability_now?: IndexabilityNow | null;
  /** The URLs & parameters part's site-level "now" (brief v19 step BB): the
   *  four-count strip, the convention, and the pattern table and parameter
   *  inventory. On the `urls` part alone. Null where there is no stored crawl. */
  urls_now?: UrlsNow | null;
  /** The Speed part's site-level "now" (brief v19 step BC): the per-template
   *  vitals strip and the five pictures beneath it, read back off the
   *  performance traces the browser pass stored. On the `speed` part alone —
   *  a filmstrip of one page painting is not a shape another part could
   *  draw. */
  speed_now?: SpeedNow | null;
  /** The order the site's accessibility barriers are worth fixing in
   *  (brief v16e Block 1). On the `a11y` part alone, for the reason `depth`
   *  gives above. Null where no A11Y instance is open, or where the run
   *  predates the pass that records them — a re-check fills it. */
  fix_order?: FixOrder | null;
  /** What every fetched page's response headers say, by template group
   *  (brief v16h). On the `security` part alone. Null where there is no
   *  stored crawl; `recorded: false` where the crawl stored no headers,
   *  which is a different answer from a site that sets none. */
  headers_grid?: HeadersGrid | null;
  /** Every page's title and description width, in crawl order (brief v16i
   *  Part C). On the `title-desc` part, site scope. Null where there is no
   *  stored crawl. */
  title_lengths?: TitleLengths | null;
  /** The entity matrix (brief v16j Tab 4), site scope: the record's
   *  entities against where each is named, and each row's verdict. */
  entity_matrix?: EntityMatrix | null;
  /** Prefixes whose dynamically-named checks belong to this part (item
   *  136o) - `axe-` for Accessibility. A finding is this part's if its
   *  check is enumerated OR carries one of these, the same rule the engine
   *  files it under. */
  check_prefixes?: string[];
  /** Item 224, Headings at site scope: the outline the crawl kept for each
   *  page an analysis row names, by URL - the baseline a card diffs against. */
  page_outlines?: Record<string, Pick<Facts, "outline" | "headings">>;
  /** One page's barriers and the picture to draw them on (Block 2). Present
   *  only when a page is narrowed to AND that page has something to say;
   *  the rendered pass samples, so most pages have no screenshot and the
   *  block says which run and tier decided that. */
  barriers?: {
    screenshot: string | null; doc: { w: number; h: number };
    barriers: Barrier[]; rendered: number; crawled: number;
  } | null;
  /** Every image the crawl could weigh, against the budget the site record
   *  states (brief v16c). On the `images` part and nowhere else, for the
   *  reason `depth` gives above. Null where there is no stored crawl to
   *  read — which is a different answer from a crawl whose images nobody
   *  weighed, and that one arrives with `measured: false`. */
  images?: ImageBudgetPayload | null;
  /** Which heading fault each page of the audit carries (brief v16d). On
   *  the `headings` part and nowhere else, for the reason `depth` gives.
   *  The shape only: the template a page belongs to is decided by
   *  `templatesOf` above, once, and the block groups these URLs with it. */
  shapes?: HeadingShapes | null;
  /** The site's canonical chains that are not the healthy case (brief
   *  v16g). On the `indexability` part and nowhere else, for the reason
   *  `depth` gives. Null where there is no stored crawl to read — which is
   *  a different answer from a crawl that recorded no canonical, and that
   *  one arrives with `recorded: false`. */
  chains?: CanonicalChains | null;
};

/** The site-scope half of the Headings blocks (brief v16d), as the server
 *  assembled it. Codes rather than sentences, because a site with two
 *  hundred faulted pages would otherwise carry two hundred copies of the
 *  same one: `labels` holds one entry per distinct code. */
export type HeadingShapes = {
  run_id: string;
  /** False where the run stored no heading list on any page: absent, not
   *  clean, and the block says so rather than drawing an empty table. */
  recorded: boolean;
  scope: string | null;
  /** Pages the run stored, and the subset whose headings it recorded. */
  crawled: number; pages: number;
  /** URL -> the codes that page carries, in the order the table reads. */
  at: Record<string, string[]>;
  labels: Record<string, { label: string; tone: string; check: string }>;
  /** Pages this picture does not read, because their canonical points at
   *  another page and the checks judge that one instead (item 180, e3). */
  not_checked?: string[];
};

type Related = { jaccard: number; shared: number; of_selected: number };

/** One link out of this page, as the markup wrote it. */
export type LinkOut = { url: string; href?: string; anchor?: string;
                        rel?: string; region?: string };
/** One link into this page, from the crawl's own graph. */
export type LinkIn = { source: string; anchor: string; rel?: string;
                       region?: string };

export type ImageRecord = {
  src: string; tag?: string; alt?: string | null;
  /** The file a script lazy loader swaps in where `src` is a placeholder,
   *  and the file the browser fetched (item 241). `fileSrc` picks one. */
  lazy_src?: string | null; resolved?: string | null;
  width?: string | null; height?: string | null;
  loading?: string | null; fetchpriority?: string | null; decoding?: string | null;
  srcset?: string | null; sizes?: string | null; type?: string | null;
  role?: string | null; linked_to?: string | null; region?: string | null;
  /** Which of the page's three parts the image sits in, whether it is the
   *  site's furniture rather than this page's content, and - for the one
   *  header image that carries meaning - that it is the logo (brief v16
   *  step AU). `region_from` reads "position" where the page declared no
   *  landmark and the measurement decided, so a band a browser inferred is
   *  never read as one the markup stated. */
  region_class?: "header" | "body" | "footer" | null;
  template?: boolean | null; is_logo?: boolean | null;
  region_from?: string | null;
  in_main?: boolean; caption?: string | null; adjacent_text?: string | null;
  /** Measured in a browser where one ran (brief v15); absent otherwise,
   *  and absent never reads as a value. */
  rendered?: Record<string, [number, number]> | null;
  intrinsic_w?: number | null; intrinsic_h?: number | null;
  /** What the file weighs re-encoded, and at what (brief v16 step AU7).
   *  Measured by encoding it, never estimated - so a row without
   *  `measured_kb` states no saving at all, and one with
   *  `reencode_error` says the probe ran and could not. */
  measured_kb?: number | null; encoder?: string | null;
  reencode_error?: string | null;
  weight_kb?: number | null; above_fold?: boolean | null;
  lcp_candidate?: boolean | null; css_aspect_ratio?: string | null;
  /** What this image is against the site's budget, stamped onto the record
   *  by `persistence.runs.image_state` when the page is read (brief v16c).
   *  Never computed in the browser: the verdict inside it is the same
   *  `onp.image_weight_state` that raises `img-heavy`, and `alt_missing` is
   *  `img-alt-missing`'s own rule, so a tile's frame cannot come to
   *  disagree with the finding beside it. `drawn_w`/`drawn_h` are the
   *  widest box a browser measured, and `kb` is null where the weight was
   *  never measured — which a stored zero also means. */
  drawn_w?: number | null; drawn_h?: number | null; kb?: number | null;
  bytes_per_pixel?: number | null;
  alt_missing?: boolean; decorative?: boolean;
  weight_state?: "unmeasured" | "unscored" | "over" | "ok";
  state?: "ok" | "warn" | "bad" | "mute" | "unmeasured";
};

/** One structured-data node as the crawl parsed it (brief v16 step AS).
 *
 *  A node, not a script: a `@graph` is several of these in one tag, and the
 *  checks are about nodes - an orphan inside a graph is still an orphan.
 *  `parse_ok` false keeps its `error`, because a block that does not parse
 *  *is* the finding and dropping it would delete it. */
/** The Structured data picture (brief v16a step AT-b, RENDER_RULES).
 *
 *  Every field here is computed by `clauditseo/schema_graph.py` and only
 *  drawn by the dashboard. The reason is in that module's own docstring:
 *  the picture has to be reproducible from what a crawl stored, months
 *  later, without the page being fetched again, and a model built in the
 *  browser would be a drawing of whatever the browser could see.
 *
 *  So there is no derivation in this file. A count, a state, a caption or
 *  a verdict that appears on screen was decided by the engine; where the
 *  renderer needs one it reads it, and where it cannot read one it draws
 *  nothing rather than working it out a second way.
 */
export type SchemaGraphModel = {
  host: string; locale: string | null; page: string; page_type: string;
  tiers: string[]; entity: string | null;
  blocks: SchemaGraphBlock[];
  nodes: SchemaGraphNode[];
  ghosts: SchemaGraphNode[];
  collections: SchemaGraphCollection[];
  edges: SchemaGraphEdge[];
  /** The entity verdict and the numbers behind it. `why` names the
   *  condition that decided it, in RENDER_RULES section 6's order. */
  verdict: { entity: string; why?: string; dangling?: number; islands?: number;
             blocks?: number; nodes?: number; copies?: number };
  counts: Record<string, number>;
  eligibility: { target?: string; rich_result?: string; verdict: string;
                 reason?: string }[];
  findings: SchemaGraphFinding[];
};

export type SchemaGraphBlock = {
  kind: "block"; i: number; key: string; source: string;
  nodes: string[]; findings: number[]; state: string;
};

/** One card on the canvas. `kind` is the whole difference between a node,
 *  an inline copy and the two sorts of ghost - level 0 draws all four the
 *  same way and the drill opens all four the same way, which is why they
 *  are one type. */
export type SchemaGraphNode = {
  kind: "node" | "inline-copy" | "ghost-dangling" | "ghost-expected";
  key: string; role: string; type: string; types: string[];
  id: string | null; sid: string | null; name: string | null;
  block: number | null; island: boolean; state: string;
  flags: string[]; note: string | null;
  parent: string | null; via_prop: string | null;
  covers: string[]; count: number | null;
  props: SchemaGraphProp[];
  collections: string[];
  refs_in: { prop: string; from: string }[];
  refs_out: { prop: string; to: string; resolved: boolean;
              target?: string | null }[];
  findings: number[];
  raw: unknown;
  /** The stats line, computed by the engine so the card cannot count one
   *  thing and the drill another. */
  stats: { properties: number; lists: number; refs_out: number;
           dangling: number };
};

/** One row of a node's properties, flattened dot-style exactly as the
 *  crawler's inventory writes them. `mark` is section 7a's verdict on the
 *  row - `ok`, `bad`, `miss`, `held` - and `note` is the words beside it.
 *  `missing` marks a row the engine added because the property is absent
 *  and its absence is the finding. */
export type SchemaGraphProp = {
  k: string; v: string; raw?: unknown; mark?: string; note?: string;
  missing?: boolean; link?: string | null;
};

export type SchemaGraphMark = { mark?: string; note: string };

export type SchemaGraphCollection = {
  kind: "collection"; key: string; node: string; prop: string;
  count: number; item_kind: string; item_type: string;
  items: { i: number; label: string; detail?: string; raw?: unknown;
           marks: SchemaGraphMark[] }[];
  problems: number; container: string | null;
  findings: number[]; state: string;
  /** What is wrong with the items, with its count - never how many there
   *  are, because the pill is already that (RENDER_RULES 7b). */
  caption: string;
};

export type SchemaGraphEdge = {
  from: string; to: string; label: string;
  kind: "ok" | "dangling" | "expected";
};

export type SchemaGraphFinding = {
  n: number; sev: string; sev_class: string; name: string;
  checks: string[]; src: string;
  anchors: string[]; anchor_keys: string[];
};

export type SchemaBlock = {
  format: string; source: string; parse_ok: boolean;
  type?: string | null; id?: string | null; error?: string | null;
  in_graph?: boolean | null;
  /** The site's, rather than this page's: an Organization node on every
   *  page is one node and one card, and `pages` says how many. */
  template?: boolean | null; pages?: number | null;
  properties?: Record<string, string | number | boolean> | null;
};

/** A template is what one fix moves at once (brief v3 step M, UX-15):
 *  besides its page count it carries the fingerprints under it - every
 *  finding with a page there, those still open (the accept verb's), and
 *  those a crawl could look at again (the re-audit verb's). A finding
 *  whose pages fall across two templates stands under both, and a verb
 *  on either moves the whole finding: the record is per finding. */
export type Template = { prefix: string; pages: number; fps: string[];
                         accept: string[]; verify: string[] };
export type Templated = { fingerprint: string; urls: string[]; state: string;
                          names_a_page: boolean };

/** The path a template groups on. Not `components.pathOf`, which keeps the
 *  query string: two URLs differing only in a `?utm_` are one page for the
 *  purpose of "what one fix moves". Exported since brief v16d so the
 *  Headings site block buckets its rows by the same notion of a path this
 *  function does rather than by a second one. */
export const templatePathOf = (u: string) => {
  try { return new URL(u).pathname; } catch { return u; }
};

/** The template a path belongs to: its first segment, or `/` where it has
 *  none. Exported with `templatePathOf` and for its reason. */
export const templatePrefixOf = (p: string) => {
  const seg = p.split("/").filter(Boolean)[0];
  return seg ? `/${seg}/` : "/";
};

export const templatesOf = (items: Templated[]): Template[] => {
  const pathOf = templatePathOf;
  const prefixOf = templatePrefixOf;
  const paths = new Set(items.flatMap((i) => i.urls.map(pathOf)));
  if (paths.size < 10) return [];
  // Group the pages by first segment; a group of ten or more is a template.
  const by = new Map<string, number>();
  for (const p of paths) by.set(prefixOf(p), (by.get(prefixOf(p)) ?? 0) + 1);
  const heads = [...by.entries()].filter(([prefix, n]) => n >= 10 && prefix !== "/")
    .sort((x, y) => y[1] - x[1]).map(([prefix]) => prefix);
  const bucket = (prefix: string): Template => {
    const inside = (p: string) => prefix === "" ? !heads.includes(prefixOf(p))
                                                : prefixOf(p) === prefix;
    const mine = items.filter((i) => prefix === ""
      ? !i.urls.length || i.urls.some((u) => inside(pathOf(u)))
      : i.urls.some((u) => inside(pathOf(u))));
    const pages = new Set(mine.flatMap((i) => i.urls.map(pathOf).filter(inside)));
    return { prefix, pages: pages.size, fps: mine.map((i) => i.fingerprint),
             accept: mine.filter((i) => i.state === "open" || i.state === "regressed")
                         .map((i) => i.fingerprint),
             verify: mine.filter((i) => i.names_a_page).map((i) => i.fingerprint) };
  };
  const out = heads.map(bucket);
  const rest = bucket("");
  if (rest.fps.length) out.push(rest);
  return out;
};


/** One page's outline as the engine decided it (brief v16d).
 *
 *  `rungs` is what to draw and in what order, including the ones that are
 *  not headings: a `gap` stands at the level nothing on the page occupies,
 *  and a `no-h1` opens a page that has none. `state` is the token, decided
 *  on the server so the ladder cannot grade something the checks did not.
 *
 *  `fires` is what the checks raise. `heading-skip` is the **first** skip
 *  alone, because the check has always broken out of its loop after one -
 *  so a page skipping twice draws two gaps and carries one finding, and the
 *  second gap is a rung with nothing to open at. That is the outline being
 *  honest about the page rather than the ladder disagreeing with the
 *  record: the two are compared at the page level, where they are the same
 *  claim. */
export type HeadingOutline = {
  rungs: { kind: "heading" | "gap" | "no-h1"; level: number; text: string;
           state: "ink" | "warn" | "bad"; index: number | null;
           for_index?: number; in_main?: boolean | null }[];
  levels: number[];
  h1s: number; h1_texts: string[];
  skips: { from: number; to: number; index: number }[];
  fires: { "h1-missing": boolean; "h1-multiple": boolean;
           "heading-skip": { from: number; to: number; index: number } | null };
};

export type EntityVerdict = "owned" | "mentioned" | "absent";
export type EntityRow = {
  entity: string; kind: string;
  cells: Record<string, number>;
  verdict: EntityVerdict; owned_by: string | null;
};
export type EntityMatrix = {
  rows: EntityRow[];
  summary: { entities: number; owned: number; mentioned: number;
             absent: number; with_schema: number };
  reading: string; columns: string[]; matcher: string;
  body_basis?: string;
};

export type ContentBlockClass = "unique" | "shared" | "boilerplate";
export type ContentBlock = {
  tag: string; landmark: string; words: number; name: string; hash: string;
  rect: { x: number; y: number; w: number; h: number };
  klass: ContentBlockClass; other_pages: string[]; thin?: boolean;
  /** Item 245: the region's opening (40 words), which rule made it
   *  furniture, and how many rendered pages carry it. */
  excerpt?: string; boilerplate_why?: "landmark" | "repeated" | null; on_pages?: number;
};
export type ContentBlocks = {
  rendered: boolean; pages_rendered: number;
  /** The rendered pass's picture of the page, and the document size the
   *  regions' rects were measured in (item 245). */
  screenshot?: string | null; doc?: { w: number; h: number };
  blocks?: ContentBlock[];
  totals?: { words: number; unique: number; shared: number;
             boilerplate: number; unique_pct: number };
};

export type Facts = {
  from_run: string; captured_at: string; url: string;
  dated: Record<string, string>; observations: number;
  /** Item 243: dimension -> when its reference crawls last fetched this
   *  page, where it has since left the site. */
  gone?: Record<string, string>;
  title: string | null; meta_description: string | null; h1: string | null;
  /** The snippet as a result will cut it (brief v16i Part B): each of title
   *  and description measured in pixels against the registry width, with the
   *  words that fall off. Absent on a page crawled before it existed. */
  snippet?: { mobile: boolean; title: SnippetField; description: SnippetField };
  /** The Content overlay's weighed text (brief v16j Tab 1): each block's
   *  rect, class and note, and the page's totals. Present only where a page
   *  is in scope and the rendered pass visited it. */
  content_blocks?: ContentBlocks | null;
  /** What this page is about (brief v16j Tab 4, page scope), from the
   *  `CNT/entity-page-verdict` finding: the verdict and its counts. */
  entity_verdict?: { verdict: string; status: string; entities: string[];
                     about: number; owns: number; contested: string[] } | null;
  heading_counts: Record<string, number>;
  headings: [number, string][] | null; heading_total: number;
  /** The outline as the parser saw it (brief v11 step AJ): level, text,
   *  whether the heading sits in the main region, and the first words
   *  after it. Null on a run crawled before that, which is why the
   *  reader falls back to `headings` (brief v14 step AP). */
  outline: [number, string, boolean, string][] | null;
  main_region: string | null;
  /** The ladder the Headings "now" block draws (brief v16d): every rung in
   *  page order, the gaps where a level was skipped, and which of them the
   *  checks fire on. Decided by `onp.heading_outline_state` - the function
   *  the checks themselves call - so the drawing has no rule of its own.
   *  Absent on a payload from before it existed. */
  heading_outline?: HeadingOutline | null;
  /** One record per image-bearing surface (brief v15): what the markup
   *  says, and where a browser measured the page, what it saw. A page
   *  crawled before the inventory existed has `images` and no more. */
  image_inventory: ImageRecord[] | null;
  images: [string, string | null][] | null; image_total: number | null;
  word_count: number | null;
  /** The first sixty words, which is what a reader and a model both meet
   *  first (brief v17 step AX). Sixty rather than the body: the page
   *  shows the opening, and shipping the whole text to draw sixty words
   *  of it would be the largest field on the payload. */
  opening?: string;
  /** The dates the page states about itself, from its structured data —
   *  `dateModified` and `datePublished` where they exist. Typed since
   *  brief v17 step AX, because the Content page reads them: `unknown`
   *  meant every reader cast, and a cast is where a wrong key hides. */
  content_dates: Record<string, string> | null;
  schema_types: string[] | null; jsonld_blocks: number | null;
  /** Every block as parsed, and the page's links to profile hosts (brief
   *  v16 step AS). Null on a run crawled before the inventory existed,
   *  which had a list of type names and a count and nothing else. */
  schema_inventory: SchemaBlock[] | null;
  profile_links: string[] | null;
  lang: string | null;
  a11y: { form_controls: number; labels: number; links: number; buttons: number;
          iframes: number; tables: number; landmarks: string[] } | null;
  outlinks: number; link_sample: { url: string; text?: string; rel?: string }[];
  click_depth: number | null;
  /** The two directions the Links part page draws (brief v17 step AW):
   *  what this page links to, and what links to it. Body links first in
   *  both — a navigation repeats on every page, so a cut that kept it
   *  would drop the links that carry meaning. Absent on a page crawled
   *  before either existed, which is why the band says so rather than
   *  rendering an empty list. */
  link_inventory?: LinkOut[];
  inlinks?: LinkIn[];
  canonical: string | null; meta_robots: string | null;
  /** This page's own canonical chain, walked on the server (brief v16g).
   *  Absent on a run stored before the walk existed, and the block then
   *  says the audit stored no canonical rather than drawing an empty card. */
  canonical_chain?: Chain | null;
  x_robots_tag: string | null; link_header_canonical: string | null;
  indexability: string | null;
  status: number | null; redirect_chain: string[] | null;
  discovered_via: string | null;
  elapsed_ms: number | null; cache_control: string | null;
  security_headers: Record<string, string | null>; server: string | null;
  viewport_tags: string[] | null; hreflang: [string, string][] | null;
  nap_mentions: { text?: string }[] | null; local_schema_blocks: number;
  site: {
    robots_status: number | null; robots_txt_bytes: number;
    llms_txt_status: number | null;
    sitemaps: { url: string; status: number | null; entry_count: number | null }[] | null;
    sitemap_entry_total: number | null;
    duplicate_forms: unknown;
    transport: { tls_version?: string; cipher?: string; cert_not_after?: string;
                 tls_floor?: string | null; tls_floor_certain?: boolean;
                 tls_offered?: Record<string, string>;
                 http_redirects_to_https?: boolean; http_version?: string } | null;
  };
  missing: string[];
};

type Anatomy = {
  groups: string[];
  categories: Category[];
  /** Which scoring dimensions fed each category on this site. The screen
   *  speaks in categories and the score speaks in dimensions; this is the
   *  only thing joining the two vocabularies. */
  category_dimensions?: Record<string, string[]>;
  total: number;
  /** Findings the page filter set aside because they belong to no page (audit
   *  F15). Zero in site mode; optional only so a payload from before the field
   *  still parses. */
  site_only?: number;
  related: Record<string, Record<string, Related>>;
  pages: string[];
  page: string | null;
  facts: Facts | null;
  /** Length guidelines as the engine defines them, keyed by fact field. */
  guidelines?: Record<string, Guideline>;
  latest_run?: string | null;
  /** The current audit's composite, from the Latest View (item 239 step 5). */
  current_audit?: { run_id: string; score: number | null; tier: string; at: string;
                    dimensions: string[] } | null;
  /** 150 BJ's three numbers, each with its denominator. The part header states
   *  coverage once from this and nothing else on the page restates it. */
  headline?: Headline | null;
  /** The three populations a count may be counted over, and the page's own
   *  scope (item 155). The crawl's path set travels with its size because
   *  prevalence is affected OF ASSESSED — the numerator has to be intersected
   *  with what the run actually fetched. */
  populations?: Populations | null;
  /** The audit the counts were measured by (brief v13 step AO): the part
   *  page names the run rather than showing a dot for it. */
  sweep_run?: SweepRun | null;
  /** The most pages one verification will re-crawl, from
   *  `runs.VERIFY_PAGE_CAP`. Same field on `SiteDetail`, because the two
   *  screens holding a verify button read two different payloads. */
  verify_page_cap?: number;
  /** The standing position across every audit — never one run's output. */
  current?: {
    outstanding: number; open: number; regressed: number; candidate: number;
    accepted_risk: number; withdrawn: number; fixed: number;
    oldest_outstanding: string | null;
    last_audit: string | null;
    /** The run the standing position was last moved by, whatever kind it
     *  was, and never the same question as `last_audit` — UX-92. The counts
     *  in this payload are site-wide over every state; a two-page
     *  verification moves them and is not an audit. */
    last_move: { at: string; kind: string; run_id: string } | null;
    /** Ticked as fixed and still open — the fix loop's own backlog. */
    awaiting_a_look: number;
    /** Written analyses (briefs) and rendered client deliverables. Two
     *  different things the UI otherwise has one word for: the Reports page
     *  lists the first, `POST /api/reports` produces the second. */
    analyses: number;
    client_reports: number;
    /** The newest client report and what it was built over, as recorded at
     *  generation (item 170, migration 0064). `null` where there is none. */
    report_state?: ReportState | null;
    /** The client plan (brief v18 step AY): when the latest accepted one
     *  was written, and how many Record rows have moved since. Two facts
     *  rather than a verdict - a tile reading "predates 11 rows" says what
     *  has to be re-read, and a boolean would only say that something has.
     *  `null` and `0` mean no plan has been accepted for this site. */
    plan_generated_at?: string | null;
    plan_stale_rows?: number;
    moved: { opened: number; fixed: number; regressed: number };
  };
};

/** Google truncates on pixel width, not characters, and the two common
 *  character counts disagree anyway: JavaScript counts an emoji as two
 *  UTF-16 units where Python counts one code point. So a length is shown as
 *  a fact with a comfort range, never as a pass mark.
 *
 *  The range comes from the engine, not from a constant here. This file used
 *  to carry 30-60 for a title against the module's 10-65, so a 62-character
 *  title read "likely truncated" beside a check that had passed it. */
type Guideline = { min: number; max: number; check: string | null };

function Measure({ text, guide, label }:
    { text: string; guide?: Guideline; label: string }) {
  const n = [...text].length;              // code points, not UTF-16 units
  if (!guide) return <span className="measure">{n} characters</span>;
  const tone = n < guide.min ? "short" : n > guide.max ? "long" : "ok";
  // An in-range value said nothing at all, which read as unevaluated rather
  // than as checked-and-fine. Silence is the one thing a measurement should
  // not mean.
  const verdict = tone === "long" ? "likely truncated"
                : tone === "short" ? "room to say more"
                : "in range";
  return (
    <span className={`measure measure-${tone}`}
          title={`${label} sits comfortably between ${guide.min} and ${guide.max} `
                 + "characters. Google truncates by pixel width, so this is a "
                 + "guide, not a limit."
                 + (guide.check ? ` Scored by the ${guide.check} check.`
                                : " Advice only — no check scores this length.")}>
      {n} characters · {verdict}
      {/* An advisory range must not read like a graded one. */}
      {!guide.check && <span className="measure-advisory"> (not scored)</span>}
    </span>
  );
}

/** Fields each panel reads, so a value carried over from an older crawl can
 *  be labelled rather than silently blended into a newer snapshot. */
const FIELDS: Record<string, string[]> = {
  "title-desc": ["title", "meta_description", "canonical"],
  headings: ["heading_levels", "headings"],
  images: ["images"],
  content: ["word_count", "h1", "lang"],
  schema: ["schema_types"],
  a11y: ["a11y", "lang"],
  "links": ["outlinks", "links", "click_depth"],
  indexability: ["canonical", "meta_robots", "x_robots_tag"],
  crawl: ["status", "redirect_chain", "robots_status", "sitemaps"],
  speed: ["elapsed_ms", "headers"],
  security: ["headers", "transport"],
  mobile: ["viewport_tags"],
  intl: ["hreflang", "lang"],
  local: ["nap_mentions", "local_schema"],
  "ai-surface": ["llms_txt_status", "robots_status"],
  urls: ["click_depth"],
};

/** The largest cluster of categories that share their pages, stated before
 *  anything is selected.
 *
 *  This is the most useful sentence the screen can produce and it used to be
 *  three clicks deep — you had to guess a category, select it, and read what
 *  lit up beside it. On the site this was built against it reads "Images,
 *  Content and Headings affect the same 99 pages — 338 of 361 open findings",
 *  which is the difference between an unusable list and a quotable scope of
 *  work.
 *
 *  Suppressed under a page filter for the same reason the marking is: on one
 *  page every category trivially shares it. */
function SharedCause({ data, byKey, onPick }: {
  data: Anatomy;
  byKey: Record<string, Category>;
  onPick: (key: string) => void;
}) {
  const clusters = Object.entries(data.related)
    .filter(([, others]) => Object.keys(others).length > 0)
    .map(([seed, others]) => {
      const keys = [seed, ...Object.keys(others)];
      const findings = keys.reduce((n, k) => n + (byKey[k]?.total.value ?? 0), 0);
      // The widest part's page count, and it carries its population: these
      // are pages the RECORD holds an open finding on, which is what an
      // overlap statement is properly about (item 155). Never a prevalence,
      // so the record is a legal population here.
      const widest = keys
        .map((k) => byKey[k]?.pages)
        .filter((c): c is Count => Boolean(c))
        .sort((a, b) => b.value - a.value)[0];
      return { keys, findings, pages: widest ?? null };
    })
    // Widest first, then largest: the cluster worth naming is the one that
    // accounts for the most work, not the one that happens to sort first.
    .sort((a, b) => b.keys.length - a.keys.length || b.findings - a.findings);

  const top = clusters[0];
  if (!top || top.findings < 2) return null;
  const share = Math.round((top.findings / data.total) * 100);
  const names = top.keys.map((k) => byKey[k]?.label ?? k);

  return (
    <div className="anat-headline">
      <span className="hl-lede">
        <strong>
          {names.map((n, i) => (
            <span key={top.keys[i]}>
              {i > 0 && (i === names.length - 1 ? " and " : ", ")}
              <button type="button" className="hl-jump"
                      onClick={() => onPick(top.keys[i])}>{n}</button>
            </span>
          ))}{" "}
          affect the same{" "}
          {/* The noun and the basis in prose, because the count renders plain
              now that it carries no `of` (audit F7). It read "1 of 1 pages in
              the record pages": the noun twice - `unit` renders it and a
              literal followed it - around a ratio over the record, which
              `POPULATION_BASIS` forbids as a denominator. */}
          {top.pages
            ? <><Counted count={top.pages} pops={data.populations ?? null}
                         className="hl-pages" />{" "}
                {top.pages.value === 1 ? "page" : "pages"} {top.pages.basis}</>
            : "—"}
          {" "}— {top.findings} of {data.total} open findings ({share}%).
        </strong>
      </span>
      <span className="hl-note muted">
        That is usually one template rather than {names.length} separate
        problems. Fixing it should move all of them at once, and the next audit
        will say whether it did. Pick one to see what is actually wrong.
      </span>
    </div>
  );
}



/** Start the smallest run that refreshes the section being read.
 *
 *  `FEATURES.md` F-06's present-capability fallback, and deliberately not
 *  F-06 itself. The operator reading a finding here could not act on it from
 *  here: the only route to a re-run was the launcher on another screen, which
 *  asks in dimensions. F-06 makes the unit fine; this makes the coarse unit
 *  reachable and says plainly what it costs, which is worth having in the
 *  meantime and stays true afterwards.
 *
 *  **The cost is stated before the click, not after.** `also` names every
 *  other section this run refreshes, from the server's own dimension table.
 *  An operator who wanted only Headings can see that four more sections move
 *  with it without starting anything to find out.
 *
 *  **Nothing here is scoped to a page**, and the confirmation says so
 *  outright. The engine crawls; there is no per-page unit to ask for, and a
 *  control that implied one would be promising the thing F-06 exists to
 *  build. The page filter above narrows what is *shown*, never what is run.
 *
 *  **Two steps, per F-10.** The opener spends nothing and carries no mark;
 *  the button inside carries it, because that is the one that commits the
 *  call. That is the distinction `711557e` got wrong and `e979b1c` reverted.
 *
 *  Remounted by the caller on every section change (`key`), so a confirmation
 *  opened in one section cannot be committed in another.
 */
function SectionRefresh({ siteId, label, refresh,
                          startConfirming = false, ask = 0, tier = null }: {
  siteId: string; label: string; refresh: Refresh;
  /** Mount on the confirmation rather than the opener - the rail's re-run
   *  control (brief step 4) has already been the opener, and spent nothing
   *  doing it. The two steps of F-10 are kept: the button that commits is
   *  still the one inside, and it is still the only one that spends. */
  startConfirming?: boolean;
  /** Bumped by each press of a re-run control while this is mounted, so a
   *  second ask on an open section re-opens the confirmation. */
  ask?: number;
  /** A depth chosen in the re-audit drawer (brief step 5), as the launch
   *  route's manual tier; null is the engine's own choice, which is what
   *  this always sent and still sends by default. */
  tier?: string | null;
}) {
  const [confirming, setConfirming] = useState(startConfirming);
  useEffect(() => { if (startConfirming) setConfirming(true); }, [startConfirming, ask]);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      // `tier: "auto"` is the launcher's own default, so the BREADTH of a
      // refresh started here is the same question the launcher asks — not a
      // cheaper variant that quietly answers a different one. `analyst:
      // false` is the half that changed (WF-59, operator 2026-08-25): auto
      // used to turn the analyst layer on whatever the caller asked, so this
      // control spent model tokens while calling itself the smallest run
      // that refreshes the section. Sent explicitly rather than omitted —
      // the server reads an absent value as "let the tier decide", which is
      // the behaviour being declined here.
      const resp = await api.post<{ run_id: string }>(
        `/api/sites/${siteId}/audits`,
        // The drawer's chosen depth overrides the adaptive tier; nothing
        // else about the request changes, and the default is unchanged.
        { dims: [refresh.dimension], tier: "auto", analyst: false,
          ...(tier ? { tier } : {}) });
      setStarted(resp.run_id);
      setConfirming(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // Started, and the operator is still standing where they were. No
  // navigation: they came here to read this section, and a run takes minutes
  // — so this says where it is rather than taking them to watch it.
  if (started) {
    return (
      <p className="sec-refresh sec-refresh-done">
        <strong>{refresh.dimension} is running.</strong> This section shows the
        new findings once it finishes and this screen is reloaded.{" "}
        <LinkButton href={`#/runs/${started}`}>Watch it &rarr;</LinkButton>
      </p>
    );
  }

  // The opener is the re-audit drawer's primary button since brief v5 step
  // U; this renders its confirmation and its done state alone.
  if (!confirming) return null;

  return (
    <div className="sec-refresh sec-refresh-confirm">
      <p>
        <strong>Re-run {refresh.dimension}?</strong> The engine is asked in
        dimensions, not sections, so {refresh.dimension} is the smallest
        dimension that refreshes {label} — which is a claim about breadth and
        not about depth. How deep it goes is a separate question, and the
        answer is below.
      </p>
      {refresh.also.length ? (
        <p>
          {/* The cost, named rather than counted. "Four other sections" is
              not something an operator can weigh; the four names are. */}
          It refreshes <strong>{refresh.also.join(", ")}</strong> as well —
          that is not a side effect to be declined, it is what this unit
          covers.
        </p>
      ) : (
        <p>
          Nothing else moves with it: {refresh.dimension} covers {label} and no
          other section.
        </p>
      )}
      <p className="muted">
        {/* This read "the engine has no per-page unit to ask for", which was
            true when it was written and is not now: F-06 built that unit, and
            the same control narrows to it once a page is named. The sentence
            changed with the capability rather than outliving it.

            UX-39: and it is still not true of every section. Where the
            dimension reads the domain rather than its pages, pointing the
            operator at the page picker sends them to a control that will not
            appear — so the route out is only offered where it exists. */}
        {refresh.per_page
          ? <>It crawls the site, not one page. To re-read a single page
              instead, narrow to it above — this control then asks{" "}
              {refresh.dimension} for that page alone, and leaves every other
              page untouched.</>
          : <>It crawls the site, and there is no narrower version of it:{" "}
              {refresh.dimension} reads the domain rather than any page of it,
              so naming one page would not change what is measured. The page
              picker does not narrow this section.</>}
      </p>
      {/* WF-59. Everything above this was true and none of it was the whole
          truth: the control named the dimension, named the four sections
          that move with it and ruled out page scope, and then said nothing
          at all about DEPTH — which is the term that decides what a press
          costs. It sends `tier: "auto"`, and auto is the adaptive engine
          choosing its own tier up to T3.

          Three sentences, because there are three separate commitments and
          an operator cannot weigh them as one: how deep, what it records,
          and what it spends. The last is new — the same fix stopped the run
          asking for analysts (see `start` above), so "no model is invoked"
          is a claim about this request rather than a hope about how the
          instance is configured. */}
      <p className="muted sec-refresh-depth">
        {tier ? (
          <><strong>Depth: {tier}, as chosen in the drawer.</strong> It crawls
          at that tier and does not escalate; the engine's own choice would
          start at T1 and go to T2 or T3 where the evidence asked. </>
        ) : null}
        <strong>The depth is chosen by the engine, not by this button.</strong>{" "}
        It pulses the site at T1, bands what it finds, and escalates to T2 or
        T3 where the evidence asks for it — so a press may crawl the whole
        site, and how much of it is decided while it runs. It records a score
        for {refresh.dimension} on this site's history, computed over the one
        dimension it ran. <strong>No model is invoked</strong>: this audit asks
        for no analyst, so it spends no tokens.
      </p>
      {error && <ErrorNote error={error} />}
      <div className="run-choice">
        {/* Unmarked, and F-10 clause 2 is why — the same reason
            `PageRefresh` below carries no mark. The request now names
            `analyst: false` and the server starts none, so no model is
            invoked and `SpendMark`'s own words ("This spends model tokens")
            would be false on every press. Marked was right while the run
            enabled the analysts; it is what WF-59 was, and it went with it. */}
        {/* UX-66. Stable caption, state on `aria-busy`, words in the
            unconditionally-mounted region below — the convention
            `views.tsx`'s `ReportView` states in full. */}
        <PrimaryButton disabled={busy} aria-busy={busy}
                onClick={start}>
          Run {refresh.dimension}
        </PrimaryButton>
        <SecondaryButton disabled={busy}
                onClick={() => setConfirming(false)}>
          Cancel
        </SecondaryButton>
      </div>
      <div className="muted" role="status" aria-live="polite">
        {busy && <Working>{`Starting the ${refresh.dimension} run…`}</Working>}
      </div>
    </div>
  );
}

/** What a finished page refresh did. `scored: false` is sent rather than
 *  implied by a missing key, for the same reason the server states it: the
 *  absence of a composite is the feature, and a screen that had to infer it
 *  would be guessing at the one claim this run is careful not to make. */
type RefreshDone = {
  run_id: string; url: string; dimension: string; tier: string;
  also: string[]; pages: number; pages_attempted: number;
  recorded: number; cleared: number; regressed: number; opened: number;
  scored: boolean;
};

/** Re-measure the page being read, for the dimension covering the section
 *  being read — `FEATURES.md` F-06, the unit itself rather than the coarse
 *  fallback above.
 *
 *  **This is the same offer, narrowed.** `SectionRefresh` starts the smallest
 *  run the engine can be asked for *across the site*; with a page in front of
 *  the operator the engine can be asked for less than that, so the claim
 *  shrinks with it: the dimension is unchanged, the population is one page,
 *  and every other page keeps its findings and its timestamps.
 *
 *  **The other sections still move — for this page.** ONP emits for Title &
 *  description, Images, Structured data and Indexability as well as Headings,
 *  and all of it is recorded. Saying otherwise would be a nicer sentence and
 *  a false one, and filtering the output to match it would make a suppressed
 *  finding indistinguishable from one that stopped firing.
 *
 *  **Unmarked, and that is F-10 clause 2 rather than an oversight.** The
 *  request names no analyst and the server starts none: a refresh is a
 *  deterministic re-measure of one page, so no model is invoked and a spend
 *  mark would be the check that fires every time. `SectionRefresh` above
 *  was the counter-example — it sent `tier: "auto"`, which the launcher's
 *  own path turned into an analyst run — until WF-59 made it name
 *  `analyst: false` as well. Both are unmarked now and for the same reason,
 *  which leaves the tier deciding breadth alone. What still separates them
 *  is scope and score: this one reads a page and writes neither.
 *
 *  Synchronous, so the answer arrives where the question was asked. `onDone`
 *  re-reads the screen afterwards, which is what makes the new findings the
 *  ones on it.
 */
function PageRefresh({ siteId, label, sectionKey, refresh, page, onDone,
                       startConfirming = false, ask = 0 }: {
  siteId: string; label: string; sectionKey: string; refresh: Refresh;
  page: string; onDone: () => void;
  /** As `SectionRefresh`'s (brief v5 step U): the drawer's primary asks. */
  startConfirming?: boolean; ask?: number;
}) {
  const [confirming, setConfirming] = useState(Boolean(startConfirming));
  useEffect(() => { if (startConfirming) setConfirming(true); }, [startConfirming, ask]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<RefreshDone | null>(null);
  const [error, setError] = useState<string | null>(null);
  const path = pathOf(page);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      // The page and the section, not a dimension and not a page set. The
      // server derives the covering dimension from the same table this
      // control read its offer from, so there is one way to configure a
      // refresh and it is the one the section offered.
      const resp = await api.post<RefreshDone>(
        `/api/sites/${siteId}/refresh`, { url: page, section: sectionKey });
      setDone(resp);
      setConfirming(false);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <p className="sec-refresh sec-refresh-done sec-refresh-page-done">
        <strong>Re-read {path}.</strong>{" "}
        {done.pages
          ? <>{done.dimension} recorded {done.recorded} finding
              {done.recorded === 1 ? "" : "s"} for this page
              {done.cleared ? <>, and closed {done.cleared}</> : null}. No score
              was written: one page is not a measurement of the site, so the
              trend is where it was.</>
          : <>Nothing was read — the page did not answer, so nothing was
              closed and nothing was recorded.</>}{" "}
        <LinkButton href={`#/runs/${done.run_id}`}>See the audit &rarr;</LinkButton>
      </p>
    );
  }

  // As `SectionRefresh`: the drawer's primary is the opener (brief v5 U).
  if (!confirming) return null;

  return (
    <div className="sec-refresh sec-refresh-confirm sec-refresh-page-confirm">
      <p>
        <strong>Re-read {path}?</strong> The engine is asked for a page and a
        dimension, so this runs {refresh.dimension} — the smallest dimension
        covering {label} — against this page and no other.
      </p>
      {refresh.also.length ? (
        <p>
          {/* Named, and named as happening rather than as prevented. The
              coarse control's cost was other sections across the site; this
              one's is the same sections on this page, which is smaller but
              not nothing — and it is recorded in full, because a finding
              filtered out reads exactly like a finding that stopped firing. */}
          {refresh.dimension} also covers <strong>{refresh.also.join(", ")}</strong>,
          so those sections refresh <em>for this page</em> too. Everything it
          finds is recorded; nothing is filtered down to {label}.
        </p>
      ) : (
        <p>
          Nothing else moves with it: {refresh.dimension} covers {label} and no
          other section.
        </p>
      )}
      <p className="muted">
        It writes no score. One page over one dimension measures a different
        population from the audit it refreshes, so it contributes no point to
        the trend — and it closes only findings on this page.
      </p>
      {error && <ErrorNote error={error} />}
      <div className="run-choice">
        {/* UX-66, the convention `views.tsx`'s `ReportView` states in full. */}
        <PrimaryButton disabled={busy} aria-busy={busy}
                onClick={start}>
          Re-read {path}
        </PrimaryButton>
        <SecondaryButton disabled={busy}
                onClick={() => setConfirming(false)}>
          Cancel
        </SecondaryButton>
      </div>
      <div className="muted" role="status" aria-live="polite">
        {busy && <Working>{`Reading ${path}…`}</Working>}
      </div>
    </div>
  );
}

/** Where the outline should open, and why it should not.
 *
 *  `at` is a position in the page's outline; `unplaced` says a `heading-skip`
 *  finding is open on this page but none of them recorded one. The two
 *  silences are different — "nothing is wrong here" and "something is wrong
 *  and nobody wrote down where" — and the screen says which.
 */
type Fault = { at: number | null; unplaced: boolean };

const NO_FAULT: Fault = { at: null, unplaced: false };

/** The fault the outline should open at, from the findings on this page.
 *
 *  FEATURES.md F-07. The first `heading-skip` that carries a position wins;
 *  a brief's judgement of the same check never carries one, so it cannot
 *  suppress the sweep's. Where none carries one — every finding raised
 *  before the check began recording it — this returns `at: null`, and the
 *  outline is left unopened rather than marking a heading nobody measured.
 */
function headingFault(findings: Finding[]): Fault {
  const skips = findings.filter((f) => f.check_id === "heading-skip");
  const placed = skips.find((f) => typeof f.outline_index === "number");
  return { at: placed ? (placed.outline_index as number) : null,
           unplaced: !placed && skips.length > 0 };
}

/** What the crawl kept, said whatever the filters are doing.
 *
 *  UX-60, and the shape of the defect is worth keeping because it is easy to
 *  re-enter. Both call sites below used to gate this sentence on
 *  `shown.length === rows.length` — a fact about the *filter* — to decide
 *  whether to state a fact about the *crawl*. The reasoning at the time was
 *  sound as far as it went: filtering `www.acme.com.au/blog` to H3 rendered
 *  `0 of 60` above a list whose one remaining row said "…16 more not kept",
 *  and the two did read as opposite claims about the same list.
 *
 *  The wrong half was the remedy. Hiding a limitation to stop it being
 *  misread is the provenance invariant's own breach — "a stated limitation on
 *  a displayed value must appear in rendered text" — and it withheld the
 *  sentence exactly when the operator had narrowed and the tally above the
 *  list disagreed with the list below by the most. The fix is to say which
 *  list the number is about, not to stop saying it. So: named counts, no
 *  ellipsis, no dependence on filter state, and rendered beside the count
 *  bar rather than as a row of the list it is a caveat on.
 *
 *  `total` is the whole page: `heading_counts` in `runs.py:page_facts` is derived
 *  from `heading_levels`, which `evidence.py:214` stores uncapped, while
 *  `headings` is `facts.headings[:HEADING_CAP]`. The two disagree by design
 *  and this is the only place that says so.
 */
function NotKept({ kind, kept, total }:
    { kind: string; kept: number; total: number }) {
  if (total <= kept) return null;
  return (
    <p className="muted fact-note not-kept">
      This crawl kept {kept} of the {total} {kind} on this page. The other{" "}
      {total - kept} are not below, whatever the filters show.
    </p>
  );
}

/** The page's outline, opened at the heading that skipped a level.
 *
 *  FEATURES.md F-07. `heading-skip` reads "Heading level jumps H2→H4 on /",
 *  which is true and leaves the operator counting down a list of forty-eight
 *  headings to find the one it means.
 *
 *  A component rather than a branch of `PageFactsBody`, which is called as a
 *  plain function — hooks written there would belong to `PageFacts` and run
 *  conditionally on which category is open, which is the rule they exist
 *  under. Here they have their own scope.
 *
 *  Three states, and the last two are the feature as much as the first:
 *    - a position that names a heading in this outline, and that heading
 *      really does skip a level — marked, and scrolled to;
 *    - a finding with no position at all — the outline renders unopened,
 *      and says why. Nothing is guessed; the finding stays readable;
 *    - a position this outline cannot bear out — past the sixty headings a
 *      crawl keeps, or naming a heading that does not skip. The same
 *      unopened outline, said differently.
 *
 *  That third state is not hypothetical. The facts panel assembles each
 *  field from the most recent run that recorded it, and a finding comes from
 *  the run that last raised it — so the outline on screen and the outline
 *  the finding was measured against are not guaranteed to be the same
 *  reading of the page. Marking regardless would put "level skipped here"
 *  against a heading that does not, which is the guess the acceptance signal
 *  forbids. The check is made against the list about to be rendered rather
 *  than against anything else the server said.
 */
function Outline({ facts, fault, refresh }:
    { facts: Facts; fault: Fault; refresh?: Refresh | null }) {
  const rows = facts.headings || [];
  const inList = fault.at !== null && fault.at > 0 && fault.at < rows.length;
  // A skip is a level more than one deeper than the heading before it —
  // the same arithmetic the check does, re-done against what is on screen.
  // Position 0 can never be one, which is why `inList` starts at 1.
  const kept = inList && rows[fault.at as number][0]
                         > rows[(fault.at as number) - 1][0] + 1;
  const at = kept ? fault.at : null;
  const [fLvl, setFLvl] = useState("all");
  const [fText, setFText] = useState("");
  // Paired with its original index rather than filtered in place: `at` is a
  // position in the crawl's list, and the mark, the `ref` and the scroll all
  // key off it. Filtering a copy and re-indexing would move the mark to
  // whatever now sits at that position, which is the guess the acceptance
  // signal forbids — the same reason `kept` is computed against the list
  // about to be rendered rather than against anything else the server said.
  const shown = rows
    .map((r, i) => [r, i] as const)
    .filter(([[lvl, text]]) =>
      (fLvl === "all" || String(lvl) === fLvl) &&
      (!fText || (text || "").toLowerCase().includes(fText.toLowerCase())));
  const mark = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    // `center` rather than `nearest`: the point is to put the heading in
    // front of the operator, and `nearest` leaves it wherever it already sat
    // if it is technically on screen. No `behavior`, so it obeys the
    // browser's own motion setting rather than animating regardless.
    if (at !== null) mark.current?.scrollIntoView({ block: "center" });
  }, [at, facts.url]);
  return (
    <>
      {fault.unplaced && (
        <p className="muted fact-note out-unplaced">
          The heading-skip finding above was recorded before the audit noted
          which heading skipped, so nothing is marked below.{" "}
          {/* This used to read "The next audit of this page will point at
              it", which named an action the product cannot take: a page is
              not a unit the engine can be asked for (`anatomy.py`'s note on
              `DIMENSION_CATEGORIES`), so nothing an operator could do would
              produce "the next audit of this page". It now points at the
              control that exists, and names the run that control starts. */}
          {/* This panel only exists with a page selected, which is exactly
              when F-06's unit is available — so the note now names the run
              that reads *this* page rather than the site-wide sweep it named
              while that was the smallest thing available. */}
          {refresh
            ? <>Only a fresh measurement records the position, and the
                smallest one is <strong>{refresh.dimension}</strong> against
                this page — which the re-audit drawer beside this section starts.</>
            : <>No automatic check refreshes this section, so nothing here will record the position.</>}
        </p>
      )}
      {fault.at !== null && !kept && (
        <p className="muted fact-note out-unplaced">
          The finding puts the skipped heading at number {fault.at + 1} on
          the page, which the {rows.length} heading{rows.length === 1 ? "" : "s"}
          {" "}below cannot bear out — either it is past the ones this crawl
          kept, or the page has changed since the audit that raised it.
          Nothing is marked rather than the wrong thing.
        </p>
      )}
      {/* Bounded at the render site, per the real-data-scale invariant.
          Measured across the 557 stored crawl pages: median 21 headings,
          p95 47, max 60 — which is `HEADING_CAP` exactly, so the crawl's cap
          says how much is kept and nothing said how much is readable at
          once. An operator opens this to judge heading structure, so the two
          filters are the two questions they arrive with: which level, and
          where is the one that says X. */}
      <div className="filters fact-filters">
        <select value={fLvl} aria-label="heading level filter"
                onChange={(e) => setFLvl(e.target.value)}>
          <option value="all">All levels</option>
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <option key={n} value={String(n)}>H{n}</option>
          ))}
        </select>
        <input value={fText} placeholder="filter by heading text…"
               aria-label="heading text filter"
               onChange={(e) => setFText(e.target.value)} />
        <span className="muted out-count">
          {shown.length === rows.length
            ? `${rows.length} heading${rows.length === 1 ? "" : "s"}`
            : `${shown.length} of ${rows.length}`}
        </span>
      </div>
      {/* Directly under the count bar, and that placement is the fix. The
          `N of M` above is about the filter; `M` is what the crawl kept; the
          per-level tally above the whole panel counts the page. Three
          numbers about three different populations, and this is the line
          that says so — which it cannot do from inside the list, where it
          was a row of the thing it is a caveat on. */}
      <NotKept kind="headings" kept={rows.length}
               total={facts.heading_total} />
      {/* The marked heading can be filtered out, and then nothing is marked
          — the same rule the three states above already follow. Saying so
          matters because the mark is the reason this panel was opened from a
          finding, and a filter that silently hides it reads as "the finding
          is not in this outline". */}
      {at !== null && !shown.some(([, i]) => i === at) && (
        <p className="muted fact-note out-unplaced">
          The heading this finding marks is filtered out, so nothing below is
          marked. Clear the filters to see it.
        </p>
      )}
      <ol className="outline">
        {shown.map(([[lvl, text], i]) => (
          <li key={i} ref={i === at ? mark : undefined}
              className={`out-l${lvl}${i === at ? " out-fault" : ""}`}>
            <code>H{lvl}</code> <span>{text || <em>empty</em>}</span>
            {/* In words, not only in colour. A mark that exists as a
                background is not there at all for a screen reader, and this
                list is where the finding becomes something to act on. */}
            {i === at && (
              <strong className="out-fault-note"> — level skipped here</strong>
            )}
          </li>
        ))}
        {shown.length === 0 && (
          <li className="muted">
            No heading on this page matches those filters.
          </li>
        )}
      </ol>
    </>
  );
}

// `ImagesTable` stood here until brief v15 step AR gave the Images part its
// own grid, which states each image's alt beside the image itself and
// carries what a browser measured of it. Its two filters were the question
// "which images have no alt text" asked of a table of up to sixty rows; a
// grid that prints that answer on every card has nothing left to filter to.
// The bound the table carried moved with it, to `IMAGES_SHOWN` in
// `part_page.tsx`, and so did `IMAGE_CAP`'s notice.

/** What the crawler actually read, for the category being looked at. */
function PageFacts({ facts, category, guides, fault, refresh }:
    { facts: Facts; category: string; guides?: Record<string, Guideline>;
      fault?: Fault; refresh?: Refresh | null }) {
  const body = PageFactsBody({ facts, category, guides, fault, refresh });
  if (!body) return null;
  // Runs record different things — an imported crawl carries a fraction of a
  // native one — so each fact comes from the most recent run that captured
  // it. Where that is not the newest, say so: a mixed snapshot must not read
  // as one moment.
  // `?? {}` deliberately: a server that predates this field must degrade to
  // "no provenance shown", not blank the whole screen.
  const dated = facts.dated ?? {};
  const carried = [...new Set((FIELDS[category] || [])
    .map((f) => dated[f]).filter(Boolean))].sort();
  return (
    <>
      {body}
      {carried.length > 0 && (
        <p className="muted fact-note fact-provenance">
          Some of this was last recorded on {carried.join(" and ")}, not in
          the crawl of {(facts.captured_at || "").slice(0, 10)} — that audit did
          not capture it. Only a crawl refreshes these; an analysis reads its
          own fetch and stores nothing here.
        </p>
      )}
    </>
  );
}

function PageFactsBody({ facts, category, guides, fault, refresh }:
    { facts: Facts; category: string; guides?: Record<string, Guideline>;
      fault?: Fault; refresh?: Refresh | null }) {
  const when = (facts.captured_at || "").slice(0, 10);
  // Says "the stored crawl", not "this crawl". The panel is built from what
  // the crawler wrote down; a brief fetches its own copy of the page and
  // keeps nothing, so running one changes nothing here. Without that
  // sentence the note sat directly beneath a brief that had just fetched
  // this exact page and read as a flat contradiction of it.
  const absent = (what: string) => (
    <p className="muted">
      The stored crawl did not record {what}. It ran on {when}, before that
      was captured, and nothing back-fills a crawl that has already happened
      — an analysis fetches its own copy of the page and does not write it
      back here. <strong>Run an audit</strong> above, or verify a finding on
      this page, and the fresh crawl will include it.
    </p>
  );

  // The Title & description panel stood here until brief v13 step AO gave
  // that part its own "what the page has now" card. `PageFacts` is only
  // called from the old part body, so the branch became unreachable the
  // day the part stopped rendering one - and an unreachable panel is a
  // second answer to the same question, waiting to disagree with the
  // first. The card states the same three strings, and grades them
  // against the same registry bounds.

  if (category === "headings") {
    const c = facts.heading_counts || {};
    return (
      <div className="facts">
        <div className="hcounts">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className={`hcount${c[`h${i}`] ? "" : " hcount-zero"}`}>
              <b>H{i}</b><span>{c[`h${i}`] ?? 0}</span>
            </div>
          ))}
        </div>
        {facts.headings
          ? <Outline facts={facts} fault={fault ?? NO_FAULT}
                     refresh={refresh} />
          : absent("the heading text, only the level counts above")}
      </div>
    );
  }

  // The Images panel stood here until brief v15 step AR gave that part its
  // own grid, which carries the same list with what a browser measured
  // beside each row. `PageFacts` is only called from the old part body, so
  // this branch became unreachable the day the part stopped rendering one.
  // Its one row helper stays: every panel below is built from it.

  const Row = ({ k, v, mono }: { k: string; v: ReactNode; mono?: boolean }) => (
    <div className="fact-row">
      <span className="fact-key">{k}</span>
      <div className={`fact-val${mono ? " fact-mono" : ""}`}>
        {v === null || v === undefined || v === "" ? <em>none</em> : v}
      </div>
    </div>
  );

  if (category === "content") {
    return (
      <div className="facts">
        <Row k="Words" v={facts.word_count} />
        <Row k="H1" v={facts.h1} />
        <Row k="Language" v={facts.lang} mono />
      </div>
    );
  }

  if (category === "schema") {
    if (facts.schema_types === null)
      return <div className="facts">{absent("the schema types")}</div>;
    return (
      <div className="facts">
        <Row k="JSON-LD blocks" v={facts.jsonld_blocks} />
        <Row k="Declares" v={facts.schema_types.length
          ? <span className="chips">{facts.schema_types.map((t) => (
              <span key={t} className="type-tag">{t}</span>))}</span>
          : null} />
      </div>
    );
  }

  if (category === "a11y") {
    if (!facts.a11y) return <div className="facts">{absent("the accessibility tally")}</div>;
    const a = facts.a11y;
    return (
      <div className="facts">
        <Row k="Language" v={facts.lang} mono />
        <Row k="Form controls" v={`${a.form_controls} (${a.labels} labels declared)`} />
        <Row k="Links" v={a.links} />
        <Row k="Buttons" v={a.buttons} />
        <Row k="Frames" v={a.iframes} />
        <Row k="Tables" v={a.tables} />
        <Row k="Landmarks" v={a.landmarks.length
          ? <span className="chips">{a.landmarks.map((l) => (
              <span key={l} className="type-tag">{l}</span>))}</span> : null} />
      </div>
    );
  }

  if (category === "links") {
    return (
      <div className="facts">
        <Row k="Internal links" v={facts.outlinks} />
        <Row k="Click depth" v={facts.click_depth === null ? null
          : `${facts.click_depth} from the homepage`} />
        {facts.link_sample.length > 0 && (
          <details className="fact-more">
            <summary>Anchor text ({facts.link_sample.length} of {facts.outlinks})</summary>
            <ul className="anchor-list">
              {facts.link_sample.map((l, i) => (
                <li key={i}>
                  <span>{l.text?.trim() || <em>no text</em>}</span>
                  <code>{l.url}</code>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    );
  }

  if (category === "indexability") {
    return (
      <div className="facts">
        <Row k="Indexable" v={facts.indexability} />
        <Row k="Canonical" v={facts.canonical} mono />
        <Row k="Meta robots" v={facts.meta_robots} mono />
        <Row k="X-Robots-Tag" v={facts.x_robots_tag} mono />
        <Row k="Link header" v={facts.link_header_canonical} mono />
      </div>
    );
  }

  if (category === "crawl") {
    const s = facts.site;
    return (
      <div className="facts">
        <Row k="Status" v={facts.status} />
        <Row k="Found via" v={facts.discovered_via} />
        <Row k="Redirects" v={facts.redirect_chain?.length
          ? facts.redirect_chain.join(" → ") : null} mono />
        <Row k="robots.txt" v={s.robots_status
          ? `HTTP ${s.robots_status}, ${s.robots_txt_bytes} bytes` : null} />
        <Row k="Sitemaps" v={s.sitemaps?.length
          ? `${s.sitemaps.length}, ${s.sitemap_entry_total ?? 0} URLs listed` : null} />
      </div>
    );
  }

  if (category === "speed") {
    return (
      <div className="facts">
        <Row k="Response" v={facts.elapsed_ms === null ? null : `${facts.elapsed_ms} ms`} />
        <Row k="Cache-Control" v={facts.cache_control} mono />
        <Row k="Server" v={facts.server} mono />
        <p className="muted fact-note">
          One server-side timing from the crawl, not a measurement of real visitors.
          Core Web Vitals come from real visitors and need the CrUX provider.
        </p>
      </div>
    );
  }

  // The Security panel stood here until brief v16h gave that part its own
  // "what the site has now" card. Its header rows are what the headers grid
  // replaces; its four TRANSPORT rows are not headers and moved to the card
  // rather than being dropped - `Accepts down to` in particular, which is
  // the promoted provenance clause and the one figure on this panel a guard
  // names. Removed here for the reason stated above for Title & description:
  // an unreachable panel is a second answer to the same question, waiting to
  // disagree with the first.

  if (category === "mobile") {
    return (
      <div className="facts">
        <Row k="Viewport" v={facts.viewport_tags?.length
          ? <span className="chips">{facts.viewport_tags.map((v, i) => (
              <span key={i} className="type-tag">{v}</span>))}</span> : null} />
        {(facts.viewport_tags?.length ?? 0) > 1 && (
          <p className="muted fact-note">
            More than one viewport tag — the last one wins, which is rarely
            what was intended.
          </p>
        )}
      </div>
    );
  }

  if (category === "intl") {
    return (
      <div className="facts">
        <Row k="Page language" v={facts.lang} mono />
        <Row k="Alternates" v={facts.hreflang?.length
          ? <span className="chips">{facts.hreflang.map(([lang], i) => (
              <span key={i} className="type-tag">{lang}</span>))}</span> : null} />
      </div>
    );
  }

  if (category === "local") {
    return (
      <div className="facts">
        <Row k="Phone numbers" v={facts.nap_mentions?.length
          ? <span className="chips">{facts.nap_mentions.slice(0, 6).map((n, i) => (
              <span key={i} className="type-tag">{n.text ?? ""}</span>))}</span> : null} />
        <Row k="Local schema" v={facts.local_schema_blocks
          ? `${facts.local_schema_blocks} block(s)` : null} />
      </div>
    );
  }

  if (category === "ai-surface") {
    const s = facts.site;
    return (
      <div className="facts">
        <Row k="llms.txt" v={s.llms_txt_status === null ? null
          : s.llms_txt_status === 200 ? "present" : `HTTP ${s.llms_txt_status}`} />
        <Row k="robots.txt" v={s.robots_status
          ? `HTTP ${s.robots_status}, ${s.robots_txt_bytes} bytes` : null} />
        <Row k="Words on the page" v={facts.word_count} />
      </div>
    );
  }

  if (category === "urls") {
    return (
      <div className="facts">
        <Row k="URL" v={facts.url} mono />
        <Row k="Query" v={(() => {
          try { return new URL(facts.url).search || null; } catch { return null; }
        })()} mono />
        <Row k="Click depth" v={facts.click_depth} />
      </div>
    );
  }

  return null;
}

/** How a run's `kind` is said on screen — UX-92.
 *
 *  Two kinds exist in the schema (`audit`, `verify`) and the fallback prints
 *  the raw value rather than nothing, so a third one added server-side shows
 *  up as an unpolished word instead of silently reverting the stamp to a bare
 *  date. That is the failure this finding was: a date with nothing saying
 *  what put it there. */
const RUN_KIND: Record<string, string> = {
  audit: "audit",
  verify: "verification",
};

const SEV_RANK: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3, info: 4,
};

/** The order the work actually happens in, and where each step stands.
 *
 *  Numbered because it genuinely is a sequence: every step reads what the one
 *  before it produced. An audit crawls; triage ranks that audit's scoreboard;
 *  the briefs triage picks read the same evidence; the fix loop re-crawls the
 *  pages behind what was fixed; the report assembles what all of it produced.
 *  Numbering a list that is not ordered would be decoration, but this chain
 *  is real and getting it wrong wastes money — buying deep briefs before
 *  triage is the expensive mistake this exists to prevent.
 *
 *  It suggests, and never gates. Only step 2 disables itself, because triage
 *  genuinely cannot read an audit that does not exist; everything else stays
 *  reachable and simply reports that it is empty. The first incomplete step
 *  is marked as the suggestion.
 *
 *  Nothing here is a new control. Each step links to the screen that already
 *  owns it — the launcher, the Analyses lanes, the sections' own mark bar,
 *  the run's report page — because a second implementation of any of them is
 *  how this codebase previously ended up with two fix loops that disagreed.
 */
/** The steps and where they stand — computed once.
 *
 *  Two things render this: the strip, and the "what to do" pane above it that
 *  names the next one. Deriving "next" twice is how a screen ends up telling
 *  you to run triage in one place and read it in another; the pane is a
 *  headline over this list, never a second opinion about it.
 */
/** An audit in flight, as the strip needs it: enough to say so, say for how
 *  long, and open it. */
type RunningAudit = { id: string; started_at: string | null };

/** How long a run has been going, said the way a person would — `48s`,
 *  `3m20s`, `1h04m`. Re-rendered on every poll while the run is in flight,
 *  so it moves. */
function elapsed(startedAt: string | null): string {
  if (!startedAt) return "just started";
  const s = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}m`;
}

/** What a step is, in one of three words (brief step 2, WF-01). `done` is
 *  finished; `partial` is started and not finished - a ranking made against
 *  an older audit, briefs read with briefs still unrun, reports generated
 *  before the record was looked at; `idle` is not started. The strip used
 *  to tick a step on "anything at all", so step 4 wore a tick beside "23
 *  not run" and step 6 wore one while step 5 said "do this next". The next
 *  step is the first idle one: a partial step is not blocking, it is
 *  ongoing, and the thing to do is the first thing not begun. */
type StepStatus = "done" | "partial" | "idle";

type Step = {
  name: string;
  /** Where the step's pane is. The name is a link to it (plan §5f): the
   *  step is the navigation, and the action pill beside it is a sibling. */
  href: string;
  /** The name leads off this screen — to a route with no strip. Said on
   *  the card (audit F-09): two of six steps deleted the navigation and
   *  neither card warned, and below 700px step 1 was a bare link to a
   *  screen with no way back but the shell. */
  leaves?: boolean;
  status: StepStatus;
  /** `status === "done"`, kept as a field because every reader asks it. */
  done: boolean;
  /** Happening right now, so neither "do this next" nor its action applies.
   *  Only step 2 can be, today. */
  busy?: boolean;
  state: string;
  action: ReactNode;
};

function sequenceSteps({ siteId, current, latestRun, lanes,
                        prechecked, precheck = null, compare = null, running, payload,
                        selected = "", held = null }: {
  /** Unassessed Critical and High on the picked audit, `null` while unread
   *  (item 178): while any, the Client report step is held, never done. */
  held?: number | null;
  siteId: string;
  /** The audit the picker holds, for step 2's "open audit". */
  selected?: string;
  current?: Anatomy["current"];
  latestRun?: string | null;
  lanes: Lanes | null;
  prechecked: boolean;
  /** The newest precheck, for step 1's state: when it counted and how many
   *  pages (brief v4 Item 3b). "+N since last check" waits on Item 2. */
  precheck?: Precheck | null;
  compare?: PrecheckCompare | null;
  /** The audit in flight, if one is — read off the site's run list, which
   *  is the one payload on this screen that knows. */
  running?: RunningAudit | null;
  /** Whether the standing position has arrived (plan §5c). The strip is
   *  the navigation, so it renders whatever this says; what it may not do
   *  is state a position it has not read. While the payload is loading or
   *  has failed, every card that reads it says so instead, nothing is
   *  ticked on its account, and no step is recommended. The cards that
   *  read something else — the precheck, the lanes — keep what they know. */
  payload: "ok" | "loading" | "failed";
}) {
  const unknown = payload !== "ok";
  const unsaid = payload === "loading" ? "loading…" : "not loaded";
  const ready = lanes?.ready.length ?? 0;
  const notRun = lanes?.available.filter((a: Analysis) => a.type !== "triage").length ?? 0;
  /** What the audit answered without a model (brief v17 step AV5), from
   *  the server's own count of the registry. `?? 0` reads as "not said"
   *  and the line below falls back to the words it used before. */
  const freeChecks = lanes?.free_checks ?? 0;
  const audited = Boolean(current?.last_audit);
  // Ranked against THIS audit. A ranking carried from an older audit is
  // shown, and says so, but does not tick the step: the scoreboard it read
  // is superseded.
  const recordDone = !unknown && audited && (current?.awaiting_a_look ?? 0) === 0;
  const reports = current?.client_reports ?? 0;

  const steps: Step[] = ([
    {
      // Step zero, and before the audit rather than beside it: the audit is
      // the expensive thing, and this is what says how big it would be. A
      // sequence that opened with "run an audit" asked the operator to buy
      // before anyone had counted what they were buying.
      name: "Precheck",
      // Its own pane (plan §3 row 1): the full panel - stamp, counts with
      // their basis, the sitemap warning - lives once on this screen, here.
      // Until 2026-09-02 the name led to the launcher, a screen with no
      // strip, and the panel was mounted on the Audit pane as well (audit
      // F-10); the operator asked for the pane.
      href: `#/sites/${siteId}?tab=precheck`,
      status: prechecked ? "done" : "idle",
      state: precheck
        ? `counted ${precheck.checked_at.slice(11, 16)}`
          + (precheck.sitemap_urls !== null ? ` · ${precheck.sitemap_urls} pages` : "")
          + (compare?.diff.full.known && compare.diff.full.added.length
             ? ` · +${compare.diff.full.added.length}` : "")
        : prechecked ? "counted" : "not run",
      // The control lived in the retired What-to-do pane, beside the other two things this
      // screen can start: with the control and its counts in this card, step
      // 1 was the tallest of six and set the height of all of them.
      action: <LinkButton href={`#/sites/${siteId}?tab=precheck`}
                 onClick={goHandler(`#/sites/${siteId}?tab=precheck`)}>
                {prechecked ? "open precheck" : "run precheck"}
              </LinkButton>,
    },
    {
      name: "Audit",
      // History: the chooser, the audits, the trend and the crawl diff.
      href: `#/sites/${siteId}?tab=history`,
      status: !unknown && audited ? "done" : "idle",
      // A running audit is a state of its own (plan §5b). Without one this
      // read "never run" for the whole of a first audit, was the step marked
      // next, and its action opened the launcher — a second concurrent
      // audit one click from the sentence saying none had run. While one is
      // in flight the action is the run itself, and the launcher is not
      // offered from here at all: a control that starts what is already
      // running is not one to disable with a reason, it is one to withhold.
      busy: Boolean(running),
      state: unknown ? unsaid
        : running
        ? `running · ${elapsed(running.started_at)}`
        : current?.last_audit
          ? `last ran ${current.last_audit.slice(0, 10)}`
          : "never run",
      action: running
        ? <LinkButton className="seq-open-run" href={`#/runs/${running.id}`}>
            open the audit
          </LinkButton>
        // To the chooser on this step's own pane (§3), not to the launcher:
        // one way to start an audit, and the by-hand setup stays a link
        // under the grid for anyone who wants it.
        // `nav`, not an action tone: this control only opens the chooser
        // and spends nothing (F-05); the spending control is inside it.
        : <>
            <LinkButton href={`#/sites/${siteId}?tab=history`}
               onClick={goHandler(`#/sites/${siteId}?tab=history`)}>
              run an audit
            </LinkButton>
            {/* "Open audit" was the retired What-to-do pane's (brief v2 step A); the
                selected audit's own screen, from the step that made it. */}
            {selected && (
              <LinkButton href={`#/runs/${selected}`}>open audit</LinkButton>
            )}
          </>,
    },
    {
      name: "Analyses",
      href: `#/sites/${siteId}?tab=analyses`,
      // What the primary action counts when this is the next step (item 168):
      // the briefs not run, the same `notRun` the state line below states.
      count: unknown ? null : notRun,
      // Partial while any brief is unrun; done only when none remain.
      status: unknown || !audited ? "idle"
        : ready > 0 && notRun === 0 ? "done"
        : ready > 0 ? "partial" : "idle",
      // Brief v17 step AV5: what was free comes first. "13 not run" on
      // its own reads as thirteen things wrong; with the free half in
      // front of it, it reads as what is left after a pass that cost
      // nothing - which is the sentence this whole brief is about.
      state: unknown ? unsaid
        : !audited ? "needs an audit"
        // "N to read" is kept where there is one: AV5 asks the free half
        // to lead, not for the rail to stop saying a brief has landed and
        // nobody has opened it. Dropping it would trade one fact for
        // another rather than adding one.
        : freeChecks
          ? `${freeChecks} free · ${ready ? `${ready} to read · ` : ""}`
            + `${notRun} analysis not run`
        : ready ? `${ready} to read · ${notRun} not run`
        : `${notRun} available`,
      // `href` kept — this is a link and must behave as one — with the plain
      // left-click routed through `goHandler`, which is the only click the
      // browser would otherwise drop when the target is the current URL.
      action: <LinkButton href={`#/sites/${siteId}?tab=analyses`}
                 onClick={goHandler(`#/sites/${siteId}?tab=analyses`)}>
                open analyses
              </LinkButton>,
    },
    {
      // "Record", not "Fix and verify" (plan §4a): the pane is the record
      // as it stands, opened on what is outstanding, and the tick and the
      // verify are on it. A worklist of its own would be a third fix loop.
      name: "Record",
      // The record (§4a): one table, one vocabulary, and "what we fixed" is
      // one dropdown away. Not a worklist of its own, on purpose.
      href: `#/sites/${siteId}?tab=all`,
      // "Done" is the fix LOOP settled, not the site clean. It was
      // `outstanding === 0`, and on the operator's own install that is 1085
      // findings away: step 5 was never done, so `next` never moved past it
      // and step 6 could not be recommended for the product's entire life.
      // This step's own work is "tick what you fixed, then verify", and that
      // work is finished when nothing ticked is still waiting on a crawl —
      // `awaiting_a_look` is exactly that count. Being clean is what the
      // standing position above reports; it is not this step's job.
      //
      // The state line still names the outstanding count when it is ticked,
      // so a tick beside "1085 outstanding" reads as what it is rather than
      // as a claim the site is clean.
      status: recordDone ? "done" : "idle",
      state: unknown ? unsaid
        : !audited ? "needs an audit"
        : current?.awaiting_a_look
          ? `${current.awaiting_a_look} awaiting a look`
        : current?.outstanding
          ? `${current.outstanding} outstanding · none awaiting a look`
          : "nothing open",
      action: <span className="muted seq-inline">tick and verify on the record</span>,
    },
    {
      name: "Client report",
      href: `#/sites/${siteId}/reports`,
      leaves: true,
      // Generated before the record was looked at is partial: the
      // deliverable predates the work step 5 still holds. The brief also
      // asks for "predates the latest Record activity" by time, and the
      // position carries no report timestamp - only a count - so that
      // half waits on the server and is not faked here.
      status: held ? "partial" : unknown || !reports ? "idle" : recordDone ? "done" : "partial",
      // The plan is what this step now produces, so the tile reports the
      // plan and not only the document count (brief v18 step AY). Two
      // states, and the difference is what the operator does next: a plan
      // that is current needs nothing, and a plan the Record has moved
      // under has to be regenerated before it is sent. The count is the
      // server's - `plan_stale_rows` on the standing position - because
      // the screen has no way to compare a timestamp against every row.
      state: unknown ? unsaid
        // Item 178 (08-3): the hold before anything the report has done.
        : held ? heldWords(held)
        : current?.plan_generated_at
        ? (current.plan_stale_rows
            ? `plan predates ${current.plan_stale_rows} row`
              + (current.plan_stale_rows === 1 ? "" : "s")
            : `plan · generated ${(current.plan_generated_at || "").slice(0, 10)}`)
        : reports
        ? `${reports} generated${recordDone ? "" : " · before step 5"}`
        : "none yet",
      // The Reports screen's first control generates (brief v2 step G).
      // Held: the way to lift the hold, not a way past it (08-3) - and since
      // item 196 that is the record rather than triage. The hold is
      // "unassessed", which only `set_state` changes; triage wrote no state,
      // so the control that claimed to lift the hold could not.
      action: held
        // Item 202: the same rows the count is of - this audit's open
        // Critical and High - as the landing's figure opens.
        ? <LinkButton href={heldRecordHref(siteId)}
                onClick={goHandler(heldRecordHref(siteId))}>
            Open the record
          </LinkButton>
        : latestRun
        ? <LinkButton primary href={`#/sites/${siteId}/reports`}>
            Generate
          </LinkButton>
        : <span className="muted seq-inline">needs an audit</span>,
    },
  ] as Omit<Step, "done">[]).map((st) => ({ ...st, done: st.status === "done" }));
  // No recommendation from a position that has not been read: a badge
  // on "do this next" would be a claim about counts nobody has seen.
  // Otherwise the first step not begun. A partial step is ongoing, not
  // blocking, so "23 not run" on step 4 does not hold step 5 back; and
  // there is one next or none, never two.
  // Record is never the thing to do next (item 170): it is written after every
  // run with no decision and no action, so offering it as the next step - or
  // as the primary action - would ask the reader to do the system's filing.
  const next = unknown ? -1
    : steps.findIndex((st) => st.status === "idle" && st.name !== "Record");
  // The step being done right now, whichever step the work is at. It was
  // `steps[next].busy`, reachable only when every earlier step was done and
  // every later one not - so a fully worked site with a crawl in flight
  // recommended generating a deliverable from the audit being superseded
  // (audit F-08). A running audit is said whatever else is undone.
  const busyAt = steps.findIndex((st) => Boolean(st.busy));
  return { steps, next, busyAt, waiting: busyAt >= 0 };
}

/** Which step's pane a tab is. Read by the strip to mark where you are.
 *
 *  Four of six. `findings` is the merged pane — the issue browser and the
 *  catalogue under one run scope — and it is step 4's; step 3 lives on that
 *  pane's section rail (brief step 3) and is never "showing" on its own;
 *  `precheck` is step 1's; Pages and Notes are reference, not steps; and
 *  step 6 is another route, so this screen is never on it. */
const STEP_OF_TAB: Record<string, number> = {
  precheck: 0, history: 1, findings: 2, all: 3,
};

/** Which destination a pane is (brief v24 step BN): Audit holds the
 *  precheck and the chooser; Analyses the shop; Record the finding log and
 *  every audit; Client report is another route. The ranking was a fourth
 *  block on Audit until item 196 and is now the order of what is listed
 *  rather than a place to go. */
const DEST_OF_TAB: Record<string, number> = {
  precheck: 0, history: 0, findings: 1, all: 2,
};

/** The six steps drawn as four destinations (brief v24 step BN). The steps
 *  are KEPT - the primary action reads them, and where a site is in its
 *  loop is the engine's notion, not the screen's - and only what is drawn
 *  changes: Precheck, Audit and Triage fold into Audit.
 *
 *  A merged destination is done when every step in it is, idle when none
 *  has begun, and partial otherwise; it is next or running when any step in
 *  it is. Its panel keeps each step's own sentence and action, headed by the
 *  step's name, so nothing a tile said is lost in the fold. */
/** The number on the primary action: what pressing it will act on (item
 *  168, channel ruling 20260917-0045). For triage that is the findings not
 *  yet been through - "Open triage · 418" is a promise about the click, where
 *  the audit's 505 would be a promise about the audit. For the catalogue, the
 *  briefs not run. Anything else carries no count rather than an invented one. */
export function primaryCount(seq: ReturnType<typeof sequenceSteps>,
                             headline: { assessed: { assessed: number; total: number } } | null,
                             ): number | null {
  if (seq.next < 0 || seq.busyAt >= 0) return null;
  const step = seq.steps[seq.next];
  if (step.name === "Triage") {
    return headline ? headline.assessed.total - headline.assessed.assessed : null;
  }
  const counted = (step as { count?: number | null }).count;
  return counted ?? null;
}

export type ReportState = {
  id: string; created_at: string; run_ids: string[];
  predates_guard: boolean; recorded: boolean;
  unassessed_severe: number | null; unassessed_below: number | null;
  assessed_pct: number | null;
};

/** What the Deliver chapter says about the newest client report (item 170,
 *  channel ruling 20260917-0250). Built only from what was recorded when the
 *  report was generated, and it tells three cases apart rather than calling
 *  every report "out of date":
 *
 *  - made before 1efbe9a, when a client report could not yet be refused over
 *    an unassessed Critical or High: a legacy row, worded as a date and a
 *    fact, never as something the product would let happen now;
 *  - passed that guard and went out over Medium, Low or Info findings still
 *    open - the case the threshold deliberately leaves to the operator;
 *  - passed the guard before the counts were recorded, which says so rather
 *    than reading as clean.
 *
 *  `warn` is true where the reader should look again. */
export function deliverState(r: ReportState | null | undefined): {
  word: string; sentence: string | null; warn: boolean;
} {
  if (!r) return { word: "not started", sentence: null, warn: false };
  const day = r.created_at.slice(0, 10);
  if (r.predates_guard) {
    return {
      word: "built before the report guard",
      sentence: `The newest client report was built on ${day}, before a report could be `
        + "held for unassessed Critical or High findings. What it went out over was not "
        + "recorded.",
      warn: true,
    };
  }
  if (!r.recorded) {
    return {
      word: "passed the guard",
      sentence: `The newest client report (${day}) passed the Critical and High check. `
        + "How much else was unassessed was not recorded when it was built.",
      warn: false,
    };
  }
  const below = r.unassessed_below ?? 0;
  if (below > 0) {
    return {
      word: `${below} unassessed below the guard`,
      sentence: `The newest client report (${day}) passed the Critical and High check and `
        + `went out with ${below} Medium, Low or Info finding${below === 1 ? "" : "s"} `
        + `still unassessed${r.assessed_pct != null ? ` (${r.assessed_pct}% of the audit had been through)` : ""}.`,
      warn: true,
    };
  }
  return { word: "done", sentence: `The newest client report (${day}) went out with every `
    + "finding it describes assessed.", warn: false };
}

export function destinationsOf(seq: ReturnType<typeof sequenceSteps>) {
  /** Which sequence steps each destination folds in, BY NAME.
   *
   *  These were positions - `["Client report", [5], seq.steps[5].href]` -
   *  and item 196 removed the Triage step from the middle of the array. The
   *  indices then pointed one past the end, `seq.steps[5]` was undefined, and
   *  reading `.href` off it threw before the screen drew anything at all. A
   *  list of positions is only ever right for the array it was written
   *  against; a name survives its neighbours being removed.
   *
   *  The head of each group is the step whose href the destination carries:
   *  Audit folds Precheck in and links to Audit, which is why the group names
   *  and the step names are not simply the same list. */
  const at = (name: string) => seq.steps.findIndex((s) => s.name === name);
  const folded: [string, string[], string][] = [
    ["Audit", ["Precheck", "Audit"], "Audit"],
    ["Analyses", ["Analyses"], "Analyses"],
    ["Record", ["Record"], "Record"],
    ["Client report", ["Client report"], "Client report"],
  ];
  const groups: [string, number[], string][] = folded.map(
    ([name, members, head]) => {
      const i = at(head);
      if (i < 0) {
        throw new Error(
          `the sequence has no step named ${head}: the destination strip is `
          + `built from step names, and one has been renamed or removed `
          + `without this list being told`);
      }
      return [name, members.map(at).filter((n) => n >= 0), seq.steps[i].href];
    });
  const destOf = (i: number) => (i < 0 ? -1 : groups.findIndex(([, members]) => members.includes(i)));
  const steps = groups.map(([name, members, href]) => {
    const parts = members.map((i) => seq.steps[i]);
    if (parts.length === 1) return { ...parts[0], name, href };
    const status = parts.every((s) => s.status === "done") ? "done"
      : parts.every((s) => s.status === "idle") ? "idle" : "partial";
    return {
      ...parts[1], name, href, status, done: status === "done",
      busy: parts.find((s) => s.busy)?.busy,
      leaves: false,
      // One line per folded step, its name first, so each step's own
      // sentence is still read where the tile used to show it.
      state: parts.map((s) => `${s.name}: ${s.state}`).join(" · "),
      action: <>{parts.map((s) => (
        <span key={s.name} className="seq-sub-action">{s.action}</span>
      ))}</>,
    } as Step;
  });
  return { steps, next: destOf(seq.next), busyAt: destOf(seq.busyAt), waiting: seq.waiting };
}

/** The strip, as the navigation it claims to be (§5f).
 *
 *  The step name is the link, and the action pill is a sibling in the card,
 *  never nested inside the link — otherwise every step costs two tab stops
 *  and the nav costs twelve before content. `aria-current="step"` marks the
 *  step whose pane is on screen, and that is now a state that can coexist
 *  with "next": the pane you are on can also be the step to do, and each is
 *  a word as well as a treatment.
 *
 *  Every link goes through `goHandler`, because four of the six point at
 *  this screen and a left-click on an anchor to the current location is the
 *  no-op `nav.ts` exists for. The tab row is gone (§7 step 5): this and
 *  the reference row are the whole of the navigation, which is why the
 *  strip renders whatever the position payload does (§5c). */
function Sequence({ steps, next, busyAt, here, report = null, held = null, compact = false }:
    ReturnType<typeof sequenceSteps> & { here: number; report?: ReportState | null;
                                         held?: number | null;
                                         /** Item 200: off the landing, the pills
                                          *  alone - no chapter heads. */
                                         compact?: boolean }) {
  /** Which pill's panel is open (brief v7 step W). None on mount; hover,
   *  focus, Space on the pill or a press on its caret opens one, and Esc,
   *  leaving, or a second press closes it. The six tiles were ~140px on
   *  every pane and carried three things - state, a sentence, links - of
   *  which only the state needs to be on screen at all times; the strip
   *  keeps the state and moves the rest one hover away. The sentence and
   *  the links are the tiles' own strings, moved, not rewritten. */
  //
  // The panel remembers what opened it. A hover closes when the pointer
  // leaves and a focus when it moves on; a press (the caret, or Space on
  // the pill) pins the panel until a second press or Esc - and a press on
  // a panel the pointer has already opened pins it rather than closing
  // it, since the pointer is on the caret because the operator wants the
  // panel kept.
  type By = "hover" | "focus" | "pin";
  const [open, setOpen] = useState<{ i: number; by: By } | null>(null);
  const press = (i: number) => setOpen((o) =>
    o?.i === i && o.by !== "hover" ? null : { i, by: "pin" });
  const leave = (i: number, by: By) => setOpen((o) => (o?.i === i && o.by === by ? null : o));
  // Item 170 (concept 10, channel ruling 20260917-0250): two chapters, not four
  // numbered steps. Find is the work of getting and working the findings, with
  // the catalogue feeding in from the side; Deliver is the report, with the
  // Record the system files automatically. `ul`, not `ol`: an ordered list
  // announces the sequence this exists to stop asserting. Find's own stages
  // keep their order inside the Audit pill's panel, where it is true.
  //
  // ONE list, with the two chapter heads above it, rather than the two lists
  // the ruling named: nine files hold that the strip renders once as one `.seq`
  // inside one labelled `nav` - the guard against the strip being drawn twice -
  // and address its pills by position. Each pill names its chapter through
  // `aria-describedby`, so a screen reader hears the grouping the eye sees.
  const CHAPTERS: { name: string; cls: string; members: number[] }[] = [
    { name: "Find", cls: "seq-find", members: [0, 1] },
    { name: "Deliver", cls: "seq-deliver", members: [2, 3] },
  ];
  const chapterOf = (i: number) => CHAPTERS.find((c) => c.members.includes(i)) ?? CHAPTERS[0];
  const find = steps[0];
  const findWord = busyAt === 0 ? "running now"
    : find?.status === "done" ? "done"
    : find?.status === "partial" || next === 0 ? "in progress" : "not started";
  // Item 178 (08-3): a held report is the Deliver chapter's state, whatever
  // an earlier report did - "done" in green beside a held button was one
  // screen saying both.
  const deliver = held
    ? { word: heldWords(held), warn: true,
        sentence: `The client report is held: ${held} Critical or High finding`
          + `${held === 1 ? "" : "s"} on this audit not yet assessed.` }
    : deliverState(report);
  // Item 181 (11-14): a panel opened by focus or hover shows its actions but
  // does not put them in the tab order - that walked four pills into eight
  // stops of the same shared chrome on every tab. Space on the pill pins the
  // panel, and a pinned panel's actions are reachable by Tab.
  const stripRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    const root = stripRef.current;
    if (!root) return;
    root.querySelectorAll<HTMLElement>(".seq-panel").forEach((panel) => {
      const pinned = open?.by === "pin" && panel.id === `seq-panel-${open.i}`;
      panel.querySelectorAll<HTMLElement>("a[href], button").forEach((el) => {
        if (pinned) el.removeAttribute("tabindex"); else el.setAttribute("tabindex", "-1");
      });
    });
  });
  const renderStep = (i: number) => {
          const st = steps[i];
          if (!st) return null;
          const isOpen = open?.i === i;
          const panelId = `seq-panel-${i}`;
          const feeds = st.name === "Analyses";
          const auto = st.name === "Record";
          return (
            <li key={st.name}
                aria-describedby={compact ? undefined : `seq-chapter-${chapterOf(i).cls}`}
                className={`seq-step${st.done ? " seq-done" : ""}`
                           + (st.status === "partial" ? " seq-partial" : "")
                           + (i === next ? " seq-next" : "")
                           + (i === here ? " seq-here" : "")
                           + (feeds ? " seq-feeds" : "")
                           + (auto ? " seq-auto" : "")
                           + (i > 0 && chapterOf(i) !== chapterOf(i - 1) ? " seq-chapter-start" : "")}
                onMouseEnter={() => setOpen((o) => (o?.i === i ? o : { i, by: "hover" }))}
                onMouseLeave={() => leave(i, "hover")}
                onFocus={() => setOpen((o) => (o?.i === i ? o : { i, by: "focus" }))}
                onBlur={(e) => {
                  if (!e.currentTarget.contains(e.relatedTarget as Node | null)) leave(i, "focus");
                }}
                onKeyDown={(e) => {
                  if (e.key === "Escape") { setOpen(null); return; }
                  // Space on the pill presses; Enter on the pill is the
                  // link's own navigation and is left alone.
                  if (e.key === " " && (e.target as HTMLElement).classList.contains("seq-name")) {
                    e.preventDefault();
                    press(i);
                  }
                }}>
              <div className="seq-head">
                {/* The pill body is the link: click navigates, hover never
                    does. One tab stop per pill; the panel's links follow it
                    in the order only while it is open. */}
                <a className="seq-name" href={st.href} onClick={goHandler(st.href)}
                   aria-current={i === here ? "step" : undefined}
                   aria-expanded={isOpen} aria-controls={panelId}>
                  {st.name}
                </a>
                {feeds && <span className="seq-role">feeds in</span>}
                {auto && <span className="seq-role">automatic</span>}
                {/* One state word per pill, always visible, right-aligned in
                    its colour: done, partial, next, running now, or idle.
                    Never colour alone (1.4.1); the border agrees with it.
                    Location is the outline, and nothing else marks it. */}
                <span className="seq-words">
                  {/* Not while it runs: "done" beside "running now" was one
                      pill saying two things about one step, as the chapter
                      word above already knew (`findWord`). */}
                  {st.done && i !== busyAt && <span className="seq-tick">done</span>}
                  {/* One word per pill: a destination folding a begun step
                      and the next one (brief v24 step BN) says "next", not
                      "partial" beside it. */}
                  {/* Item 178 (08-3): a held client report says so on the pill
                      too. "Partial" beside a chapter reading held was the one
                      screen saying two things about one report. */}
                  {st.name === "Client report" && held ? (
                    <span className="seq-word seq-held">{REPORT_HELD_WORD}</span>
                  ) : st.status === "partial" && i !== next && i !== busyAt && (
                    <span className="seq-word">partial</span>
                  )}
                  {i === busyAt && <span className="seq-badge seq-badge-live">running now</span>}
                  {i === next && i !== busyAt && <span className="seq-badge">next</span>}
                  {st.status === "idle" && i !== next && i !== busyAt && (
                    <span className="seq-idle">idle</span>
                  )}
                </span>
                {/* Out of the tab order - the pill itself carries
                    `aria-expanded` and Space, one stop per step - and a
                    pointer target for a mouse that would rather press than
                    hover. Not a `button` element: the strip holds no
                    button, by the guard that keeps it from ever spending
                    (`test_the_standing_position_outlives_the_tab.py`). */}
                <span className="seq-caret" role="button" tabIndex={-1}
                      aria-label={`about ${st.name}`} aria-expanded={isOpen}
                      aria-controls={panelId}
                      onClick={(e) => { e.stopPropagation(); press(i); }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); press(i); }
                      }}>▾</span>
              </div>
              {/* In the tree whether open or not, so the strip's readers
                  (and the tests that read the tiles' sentences) find the
                  same strings; `hidden` is what "one hover away" means. */}
              <div id={panelId} className="seq-panel" hidden={!isOpen}>
                <div className="seq-state">{st.state}</div>
                {st.name === "Client report" && deliver.sentence && (
                  <div className="seq-deliver-note">{deliver.sentence}</div>
                )}
                {/* Moved from the reference row (item 173, ruling B): the
                    sentence telling a reader panes are not stages. */}
                {feeds && <div className="seq-feeds-note">Consulted from any step.</div>}
                <div className="seq-action">{st.action}</div>
              </div>
            </li>
          );
  };
  return (
    <nav aria-label="Where you are in the work"
         className={`seq-chapters${compact ? " seq-compact" : ""}`}>
      {!compact && CHAPTERS.map((ch) => {
        const word = ch.name === "Find" ? findWord : deliver.word;
        const warn = ch.name === "Deliver" && deliver.warn;
        return (
          <div key={ch.name} id={`seq-chapter-${ch.cls}`}
               className={`seq-chapter-head ${ch.cls}${warn ? " seq-chapter-warn" : ""}`}
               title={ch.name === "Deliver" && deliver.sentence ? deliver.sentence : undefined}>
            <span className="seq-chapter-name">{ch.name}</span>{" "}
            <span className="seq-chapter-state">{word}</span>
          </div>
        );
      })}
      <ul className="seq" ref={stripRef}>
        {steps.map((_, i) => renderStep(i))}
      </ul>
    </nav>
  );
}

/** The copy a conforming brief proposed, one row per page (brief v10 step
 *  AF): page, what is there now, what to put there, with the character
 *  count and a copy button per cell. The replacement is the brief's real
 *  value and it had no home in the UI; this is the home on the part page,
 *  and the client report carries the same table per part. */
/** The record's rows, not the pane's capped fifty (brief v11 step AH):
 *  every replacement the briefs of this part proposed, fifty at a time
 *  with the count said and a `show all` toggle. `findings` is the pane's
 *  own list, used only where the record has not been read yet. */
export const REPLACEMENTS_SHOWN = 50;

/** The record's states narrowed to one page, or all of them (brief v12
 *  step AM): one scope per pane, so the cause counts, the tags and the
 *  replacement table read the same states the narrowed findings do. A
 *  page is matched as the payload spells it, or by path where a stored
 *  state spells the host differently. */
export function narrowStates(states: FindingState[], page: string): FindingState[] {
  if (!page) return states;
  const pathOf = (u: string) => { try { return new URL(u).pathname || "/"; } catch { return u; } };
  const want = pathOf(page);
  return states.filter((s) => s.affected_urls.some((u) => u === page || pathOf(u) === want));
}

export function ReplacementTable({ states, belongs, findings, dropped = 0, notAssessable = 0 }: {
  states: FindingState[];
  /** Item 218: the part's own ownership rule (`belongsTo`), never "no
   *  checks, so everything". The set this took was the part's BRIEF checks,
   *  and an empty set passed every proposed row in the site record - so a
   *  part with no brief (Backlinks) listed 50 of 205 rows from Indexability,
   *  Crawl, Structured data and Links. Null when the part owns nothing. */
  belongs: ((checkId: string) => boolean) | null;
  findings: Finding[];
  /** Rows the parser dropped and rows the brief could not assess, from
   *  the latest run (brief v12 step AL): named here, listed in the report. */
  dropped?: number; notAssessable?: number;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  type Rep = { key: string; url: string; check_id: string; current: string; replacement: string;
               /** A brief-only row the sweep has not corroborated (brief v12
                *  step AM): shown, and tagged, as the cause table shows it. */
               candidate: boolean };
  const fromRecord: Rep[] = states
    .filter((s) => s.proposed && (s.state === "open" || s.state === "regressed" || s.state === "candidate")
                   && belongs !== null && belongs(s.check_id))
    .map((s) => ({ key: s.fingerprint, url: s.affected_urls[0] ?? "", check_id: s.check_id,
                   current: s.summary, replacement: s.proposed as string,
                   candidate: s.state === "candidate" }));
  const rows: Rep[] = fromRecord.length ? fromRecord
    : findings.filter((f) => f.contract && f.recommendation)
        .map((f) => ({ key: f.fingerprint, url: f.urls[0] ?? "", check_id: f.check_id,
                       current: f.summary, replacement: f.recommendation,
                       candidate: f.state === "candidate" }));
  const account = (dropped > 0 || notAssessable > 0) && (
    <p className="muted rep-dropped">
      {dropped > 0 ? `${dropped} row${dropped === 1 ? "" : "s"} dropped` : ""}
      {dropped > 0 && notAssessable > 0 ? " · " : ""}
      {notAssessable > 0 ? `${notAssessable} not assessable` : ""}
      {" — see report"}
    </p>
  );
  // Item 218: a part that owns no check has no replacement copy, and
  // says so once rather than borrowing another part's.
  if (belongs === null) return <p className="muted rep-none">No replacement copy for this part.</p>;
  if (!rows.length) return account || null;
  const shown = all ? rows : rows.slice(0, REPLACEMENTS_SHOWN);
  const pathOf = (u: string) => { try { return new URL(u).pathname || "/"; } catch { return u; } };
  const copy = async (key: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(key); } catch { setCopied(null); }
  };
  return (
    <div className="replacements">
      <h4>
        Replacement copy
        <span className="muted rep-count">
          {" "}· {shown.length} of {rows.length}
          {rows.length > shown.length ? " — all in the report" : ""}
        </span>
        {rows.length > REPLACEMENTS_SHOWN && (
          <SecondaryButton className="rep-all" aria-expanded={all}
                  onClick={() => setAll((v) => !v)}>
            {all ? `show ${REPLACEMENTS_SHOWN}` : `show all ${rows.length}`}
          </SecondaryButton>
        )}
      </h4>
      {account}
      <table className="findings replacements-table">
        <thead>
          <tr><th>Page</th><th>Check</th><th>Current</th><th>Replacement</th><th /></tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.key} className={r.candidate ? "rep-candidate" : undefined}>
              <td><code>{pathOf(r.url)}</code></td>
              <td>
                <code>{r.check_id}</code>
                {r.candidate && <Pill tone="state-candidate" title={CANDIDATE_NOTE}>candidate</Pill>}
              </td>
              <td className="muted">{r.current}</td>
              <td>
                {r.replacement}
                <span className="muted rep-chars"> ({r.replacement.length} chars)</span>
              </td>
              <td>
                <SecondaryButton className="copy-btn"
                        aria-label={`copy the replacement for ${pathOf(r.url)}`}
                        onClick={() => copy(r.key, r.replacement)}>
                  {copied === r.key ? "copied" : "copy"}
                </SecondaryButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// `worst()` moved to `severity.ts` at item 195: the parts strip needs it, and
// this file takes values from `client_lanes.tsx`, so importing it back would
// be a cycle. Re-exported so any reader that had it from here still does.
export { worst } from "./severity";

/** The Pages count, as a control where there is something behind it
 *  (FEATURES.md F-11).
 *
 *  The number is a summary of `affected_urls`, and until this it was the
 *  whole of the evidence: *"3 pages share the title …"*, `PAGES 3`, and no
 *  way to reach those three. The rule, stated wider than this one screen:
 *  wherever the product states a quantity of affected things, the operator
 *  can reach those things in one action from where the quantity is stated.
 *
 *  **No control where the list is empty**, rather than one that opens onto
 *  nothing. A site-scoped finding legitimately names no page — `hreflang`
 *  and `citations-nap` both raise findings with an empty `affected_urls`,
 *  measured in run `79a1fc02…` and recorded on `QUESTIONS.md` Q-20, and on
 *  this install twelve of `www.acme.com.au`'s 236 open findings are that
 *  shape. The branch is on `urls` rather than on `pages` because `urls` is
 *  what would be rendered: the two agree on the wire today
 *  (`runs.anatomy_view` derives `pages` from the same list) and a disclosure
 *  that trusts the count over its own contents is the empty-affordance
 *  defect one refactor away. */
function PagesCount({ f, open, onToggle }: {
  f: Finding; open: boolean; onToggle: () => void;
}) {
  if (!f.urls.length) return <>{f.pages}</>;
  return (
    <button type="button" className="pages-btn" aria-expanded={open}
            onClick={onToggle}>
      {f.pages}
      <span className="pages-caret" aria-hidden="true">{open ? "▴" : "▾"}</span>
      {/* UI-23. Pluralised at the render site, the way every other count in
          the product is (`fixloop.tsx`). The visible label is a bare digit,
          so this string is the whole of what a screen reader hears — and a
          fixed "pages" made a one-page finding announce "1 pages — show
          them". The one part of this control a sighted operator never reads
          was the one part that was ungrammatical. */}
      <span className="sr-only">
        {" "}{f.pages === 1
          ? (open ? "page — hide it" : "page — show it")
          : (open ? "pages — hide them" : "pages — show them")}
      </span>
    </button>
  );
}

/** The pages behind the count, and what the screen was not sent.
 *
 *  `UrlLinks` is handed `max` equal to the list it was given, because its own
 *  "+N more" counts the array in hand and the array in hand is already cut:
 *  the payload sends `affected_urls[:10]` while `pages` beside it is the
 *  whole of what was stored, so the component's default max of 3 would have
 *  read "+7 more" above a Pages column saying 38. The truncation is stated
 *  here instead, against the counts the server did send.
 *
 *  **`pages` is not the untruncated total, and this comment said it was for
 *  the feature's whole life.** Four checks cap their own list before it is
 *  stored, so on those findings `pages` is a cap too and the sentence built
 *  on it promised the operator that URLs which were never written down were
 *  retrievable (UX-93). `total` is the untruncated one, and it is `null` on
 *  every row written before migration 0030.
 *
 *  The sentence names no cap of its own. Ten is the server's number
 *  (`runs.anatomy_view`), and a client repeating it goes stale silently the
 *  day it changes; `f.urls.length`, `f.pages` and `f.total` are all on the
 *  wire and cannot disagree with what is on the screen. */
function PagesList({ f }: { f: Finding }) {
  /** The two cuts, stated apart because they are two.
   *
   *  `cutHere` is this payload's: the rest were stored and a different
   *  surface could reach them, which is B-30 and is a promise the sentence
   *  may only make when `f.total` confirms it. `cutBefore` is the check's
   *  own: those URLs were never written anywhere, so no surface can reach
   *  them and saying "the rest are stored" of them is false.
   *
   *  `f.total == null` is a row older than the frame. Neither clause fires
   *  on its size, because nothing here knows it. */
  const cutHere = f.pages > f.urls.length;
  const cutBefore = f.total != null && f.total > f.pages;
  return (
    <div className="pages-list">
      <UrlLinks urls={f.urls} max={f.urls.length} />
      {(cutHere || cutBefore) && (
        <p className="muted pages-cut">
          {cutHere
            /* UX-95: the sentence used to end "(BACKLOG.md B-30)". It was the
               only rendered register citation in the dashboard — every other
               mention of one in `dashboard/src` is inside a comment, as B-30
               is in the block above. The operator has no such file and
               nothing on the screen led anywhere; the fact the citation was
               carrying is already in the clause before it. */
            ? `Showing ${f.urls.length} of the ${f.pages} URLs stored. This
               screen's payload caps the URL list it carries per finding — the
               rest are stored and are not reachable from here.`
                .replace(/\s+/g, " ")
            : `Showing all ${f.pages} URLs stored.`}
          {cutBefore &&
            ` The check found ${f.total} and stored the first ${f.pages}, so
              the other ${f.total! - f.pages} were never recorded.`
              .replace(/\s+/g, " ")}
        </p>
      )}
    </div>
  );
}

/** The state the client screen's standing position and its findings pane
 *  share.
 *
 *  Owned by `SiteDetailView` and handed to both, so the position and the
 *  suggested order survive changing what is below them. Both rendered inside
 *  `AnatomyView`, which mounts only under the Current tab: a strip claiming
 *  to describe the whole of the work lived inside one view of it and
 *  vanished when you left that view (`_plans/site-screen-ia-plan-v2.md` §1,
 *  §7 step 1). The tabs are untouched; what moved is where the state lives.
 *
 *  What is here is exactly what both readers need: the anatomy payload, the
 *  page filter that scopes it, the tick that re-reads it and the fix loop
 *  whose verifications bump that tick. Everything only one of them reads —
 *  the precheck, triage and the lanes for the strip; the open category and
 *  its panels for the tree — stays with its reader.
 */
export function useAnatomy(siteId: string, onChanged?: () => void) {
  /** The page scope, and it lives in the address (brief v23 step BK).
   *
   *  It was `useState<{ site, url }>`, kept as one value so "a filter from
   *  another client" could not be represented; `pageScopeFromHash` keeps
   *  that guarantee by honouring `page=` only on the site it names. In the
   *  address, a page-scoped view is a link, survives a reload, and Back
   *  returns to site mode. Read on every `hashchange`, like `?cost=` below:
   *  the setter navigates, and a pasted link and a choice are one event. */
  const [page, setPageState] = useState(() => pageScopeFromHash(siteId));
  useEffect(() => {
    const read = () => setPageState(pageScopeFromHash(siteId));
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [siteId]);
  const setPage = (url: string) =>
    goto(withPageScope(window.location.hash || `#/sites/${siteId}`, url),
         { keepScope: false });
  // `useFetch` rather than a hand-rolled effect, because it already holds
  // the answer: a `live` flag cleared on cleanup, so a reply for a request
  // that has since been superseded is dropped instead of rendered. This was
  // the only keyed fetch that fetched its own way, and it rendered one
  // page's evidence under another page's name for exactly as long as the
  // slower reply took to arrive. The hook covers the other half of that too
  // now — a page change blanks what the previous page's reply produced, so
  // the facts panel says it is loading rather than showing the wrong page's
  // facts (UX-13).
  /** Bumped after a mark, a verification or a section run, so the tree and
   *  the counts follow what just happened. */
  const [tick, setTick] = useState(0);

  /** The cost filter (brief v17 step AV4), and the address is where it
   *  lives rather than where it is copied to.
   *
   *  Every other filter on this screen is React state that also writes
   *  itself into the hash, and each one has needed a rule for what to do
   *  when the two disagree. This one reads the hash and nothing else: the
   *  setter navigates, `hashchange` re-reads, and a pasted link and a
   *  press are the same event by construction. `goto` re-announces an
   *  unchanged hash, so pressing the chip it is already on still lands.
   *
   *  Not remembered per site, unlike `?state=` and `?group=`. Those are
   *  how an operator likes to read the record; this one is an argument
   *  being made about a particular audit, and a filter that silently
   *  hides paid findings on a site you have not opened for a month is a
   *  filter that will be forgotten and then trusted. */
  const [cost, setCostState] = useState(costFromHash);
  useEffect(() => {
    const read = () => setCostState(costFromHash());
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);
  const setCost = (next: string) => {
    const [path, query] = (window.location.hash || "").split("?");
    const q = new URLSearchParams(query || "");
    if (next) q.set("cost", next);
    else q.delete("cost");
    const tail = q.toString();
    goto(tail ? `${path}?${tail}` : path);
  };

  // Labelled by the site, not by the URL — the page filter is a control on
  // this screen rather than a different screen. Blanking on every path
  // change would unmount the picker between keystrokes, which is the
  // regression `2ed927a` fixed by removing the blanking outright; reports
  // 025 and 030 name the remedy for this screen and it is `stale` below.
  const { runsReady } = useSelection();
  // Item 239 step 5: the site screen is the current view. No audit is
  // picked and none travels with the request; a run's own record is the
  // Audits tab's history view.
  const anatQuery = [
    page ? `page=${encodeURIComponent(page)}` : "",
  ].filter(Boolean).join("&");
  const anatPath = `/api/sites/${siteId}/anatomy` + (anatQuery ? `?${anatQuery}` : "");
  // Not requested until the site's audit list has answered (item 179): a
  // request made before then is for whichever audit the server calls latest,
  // is superseded the moment the pick arrives, and left a stale-note naming a
  // page filter nobody had set (UI audit 02-1, 05-14).
  const { data, error, loading, retry, payloadPath } =
    useFetch<Anatomy>(runsReady ? anatPath : null, tick, siteId);

  /** UX-13's half of this screen: what is rendered is the previous page's
   *  until the reply for the chosen one lands, so it says so in rendered
   *  text rather than looking settled. `data &&` because before the first
   *  reply there is nothing to be stale — that state is `<Loading/>`.
   *
   *  **UX-56: compared, not inferred.** This was `loading && Boolean(data)`,
   *  and `loading` goes true for any re-run of the effect that keeps the
   *  payload — which is every bump of `tick`: a fix-loop verification
   *  (`:1421`), a paid triage purchase (`:1499`), a section run (`:1535`) and
   *  a page refresh (`:1870`). None of the four moves the subject, so all
   *  four printed and announced a sentence about a page nobody had chosen,
   *  immediately after the operator spent money. The hook could not have
   *  answered it: its `for` key is the SITE on this screen, deliberately, so
   *  it cannot distinguish two pages of one site. `payloadPath` is the
   *  addition — the path the payload actually came from — and the question
   *  becomes a comparison the screen can make for itself. */
  const stale = Boolean(data) && loading
    && payloadPath !== null && payloadPath !== anatPath;
  /** Item 179: the payload is the answer for the current site, page AND pick.
   *  Not ready while the pick is still being read either: a payload fetched
   *  before the site's audit list answered is for the latest audit, which is
   *  not always the operator's pick. Every figure and state sentence on the
   *  client screen draws from `ready`, and says "Loading…" until it is. */
  const ready = useLoaded({ data, payloadPath }, anatPath).ready && runsReady;
  /** What the payload on screen was read for, from the path it came from: its
   *  page and its audit. A stale payload is drawn against its OWN page, never
   *  the one just chosen - "Outstanding 16 · 1740 open" was a page's chip in a
   *  site's sentence (02-2) - and the head's figures, which follow the audit
   *  and not the page, are ready once the audit matches. */
  const payloadQuery = new URLSearchParams((payloadPath ?? "").split("?")[1] ?? "");
  const dataPage = payloadQuery.get("page") ?? "";
  const headReady = Boolean(data) && runsReady && payloadPath !== null;

  /** The fix loop, shared with The record — same tick, same words, same
   *  verify. It used to live here and only here, which is why the other
   *  screen grew its own vocabulary for the same mechanism. */
  /** One fix loop for the screen (plan §9; audit F-17). It was two - this
   *  one and the record pane's own, with two judges and two independent
   *  sets of marks - so a tick made on the Analyses pane reached the Record
   *  pane only when that pane's payload next re-read. Since the merge the
   *  two panes are sibling steps of one sequence, one click apart. The judge
   *  is the position's last audit; a verification re-reads the position and,
   *  through `onChanged`, whatever else the caller keeps. */
  const fix = useFixLoop(siteId, data?.current?.last_audit,
                         () => { setTick((t) => t + 1); onChanged?.(); });
  /** The audit this screen's run-scoped parts read: the newest reading of
   *  the site (item 239 step 5 retired the pick). One value for both
   *  readers. The strip's step cards read
   *  `latest_run` while the lanes under them read the pick, so the card
   *  could say "3 to read" a foot above lanes reading "Ready to read · 0"
   *  — the defect the merge was conditioned on not reproducing. What is
   *  OPEN is the site's standing position and does not follow this. */
  const run = data?.latest_run || null;
  /** The precheck, and a nonce to re-read it after one is run. Shared: the
   *  strip's compact control runs it, and the chooser on step 2's pane reads
   *  its counts (plan §3: the panel lives once, the counts travel). Its own state,
   *  not the audit's: it is measured before an audit exists and stays true
   *  across audits, so hanging it off `latest_run` would blank it every time
   *  a crawl finished. */
  const [preTick, setPreTick] = useState(0);
  const { data: precheck, loading: precheckLoading } = usePrecheck(siteId, preTick);
  /** Now beside prior (brief v4 Item 2), read once here for the pane, the
   *  sidebar's pages line, the strip's tile and the record's gone marker. */
  const { data: compare } = usePrecheckCompare(siteId, preTick);
  // A page change must not blank, or the picker unmounts under the caret
  // and cannot be typed into; a site change is handled by remounting from
  // the caller instead, which clears every piece of both readers' state at
  // once rather than one `setData(null)` at a time. A verification's
  // outcome is about the page it was run on, so it goes with the page.
  useEffect(() => { fix.setOutcome({}); }, [siteId, page]);

  /** A filter the site cannot honour is no filter.
   *
   *  Belt to the braces above: a deep link, a re-crawl that drops a URL, or
   *  any future path that sets `page` from outside would put the control
   *  back into the state where it disagrees with the request. Cleared as
   *  soon as the server's own page list says the value is not one of them. */
  useEffect(() => {
    if (page && data && !data.pages.includes(page)) setPage("");
  }, [data, page]);

  /** Ticks come back from the server, not from browser memory. Seeded from
   *  what is still outstanding, so a finding that was marked and has since
   *  been cleared is not in this list at all and nothing stale is re-ticked. */
  useSeed(fix.seed,
          data ? data.categories.flatMap((c) => c.findings) : [],
          data);

  /** The lanes for `run` — what has been analysed and what could be — and
   *  triage's own state. Shared, because three things read them: the strip's
   *  cards for steps 3 and 4, the Triage pane, and the header's compact
   *  triage control. Two fetches of one audit's lanes is how a card came to
   *  say "3 to read" above lanes reading "Ready to read · 0". */
  const [lanesTick, setLanesTick] = useState(0);
  const { data: lanes, error: lanesError } = useAnalyses(run, lanesTick);
  const bumpLanes = () => setLanesTick((t) => t + 1);
  /** Run-all (brief v4 Item 3f): the briefs queued, in order; each leaves
   *  the queue as it lands, the lanes and the tree re-read behind it. The
   *  sidebar reads this to turn a part's dot amber while its brief is in
   *  the queue and violet once the payload says it has been read. */
  const [queued, setQueued] = useState<string[]>([]);
  const [batchError, setBatchError] = useState<string | null>(null);
  const startBatch = (tools: string[]) => {
    if (!run || !tools.length) return;
    setBatchError(null);
    setQueued((q) => [...q, ...tools.filter((t) => !q.includes(t))]);
    for (const tool of tools) {
      api.post(`/api/runs/${run}/expert/${tool}`, {})
        .catch((e) => setBatchError(`${tool}: ${(e as Error).message}`))
        .finally(() => {
          setQueued((q) => q.filter((t) => t !== tool));
          setLanesTick((t) => t + 1);
          setTick((t) => t + 1);
        });
    }
  };
  return { data, error, loading, retry, stale, ready, headReady, dataPage,
           lanesSettled: !run || lanes != null || lanesError != null,
           page, setPage, setTick, fix,
           /** A state the operator set on this screen (item 237): this
            *  payload and whatever the caller keeps - the site's states,
            *  which the part page's cards read. */
           changed: () => { setTick((t) => t + 1); onChanged?.(); },
           cost, setCost,
           run, precheck: precheck ?? null, precheckLoading, setPreTick,
           compare: compare ?? null,
           lanes: lanes ?? null, bumpLanes,
           queued, batchError, startBatch };
}

export type AnatomyScreen = ReturnType<typeof useAnatomy>;

/** The standing position and the suggested order — the head of the client
 *  screen, above the tabs.
 *
 *  Keyed on the site by its caller, so the picker's text, the precheck nonce
 *  and the triage state are this site's alone and a site change starts them
 *  over, the way `AnatomyView`'s key already does for the tree.
 *
 *  The position payload cannot take the navigation down (§5c). On a failed
 *  or still-loading anatomy fetch the "Where it stands" pane holds the
 *  failure with its retry, or the wait, and the strip still renders every
 *  step with its link — the cards that read the position say "not loaded"
 *  or "loading…" rather than a state nobody has read, and nothing is
 *  recommended. Measured before this: one aborted GET left the record
 *  pane rendering twelve rows under zero steps, with no route to Audit,
 *  Analyses or Client report except the address bar.
 */
export function StandingHeader({ siteId, a, running = null, tab = "",
                                 alerts = null, context = null }: {
  siteId: string; a: AnatomyScreen;
  /** What the alert strip carried: regressions and the watch's changes. A
   *  chip in the scope bar now (brief v2 step A, UI-08), not a row of its
   *  own above everything. */
  alerts?: { regressions: FindingState[]; watch?: WatchChange[] } | null;
  /** The audit in flight, if one is. `SiteDetailView` reads the run list
   *  and polls it while this is set, so the elapsed time here moves. */
  running?: RunningAudit | null;
  /** The tab whose pane is on screen, so the strip can say which step that
   *  is. Empty from any caller that has no tabs. */
  tab?: string;
  /** More of the screen's own context for the shell's bar (item 173): the
   *  reference links, which are navigation and must stay operable. */
  context?: ReactNode;
}) {
  /** Item 200: the landing is the tab this board is for. "" is the landing
   *  before the address names a pane (`views.tsx` passes `landed ? tab : ""`). */
  const onLanding = !tab || tab === "landing";
  const { data, error, loading, retry, page, setPage, stale, setTick,
          run, precheck, setPreTick, lanes,
          headReady, dataPage, lanesSettled, precheckLoading } = a;
  const [typed, setTyped] = useState<string | null>(null);
  /** What is in the picker's box, which is not the same as which page is
   *  selected: a path being typed is not yet a choice. `null` means "show
   *  the selection", so a page chosen elsewhere still displays. */
  // The scope can change without this box (brief v23 step BK): Back, a
  // pasted link, the legend's clear. A draft left behind then displayed a
  // page the screen was no longer scoped to - `/many` in the box over site
  // mode - and re-typing that same path fired no change, so it could not be
  // chosen again. Whenever the scope moves, the box shows the scope.
  useEffect(() => { setTyped(null); }, [page]);
  // Item 181: pressing One page puts the bar in page mode before a page is
  // chosen, so a scope that returns to the whole site by any other route - Back,
  // a pasted link - puts the picker away, unless the operator cleared the box
  // to retype, which must not take it from under the caret.
  useEffect(() => {
    if (!page && !(typed !== null && !typed.trim())) setPicking(false);
  }, [page]);
  /** Whether a page is being picked (item 174, channel ruling 20260917-1430):
   *  the filter is page mode's control, so site mode does not draw it. "One
   *  page" reveals it and focuses it; it stays while it is in use - cleared to
   *  retype, it must not vanish under the caret - and "Whole site" puts it
   *  away. A page in scope always shows it, holding the chosen path. */
  const [picking, setPicking] = useState(false);
  const findRef = useRef<HTMLInputElement | null>(null);
  const [focusFind, setFocusFind] = useState(false);
  useEffect(() => {
    if (focusFind && findRef.current) { findRef.current.focus(); setFocusFind(false); }
  }, [focusFind, picking]);
  const { runs: selectedRuns, site } = useSelection();

  /** What the strip may say about the position: read, still coming, or
   *  not coming. No early return on either of the last two — see above. */
  const payload = error ? "failed" : headReady ? "ok" : "loading";
  /** Item 179: the next step is recommended only once every source it is
   *  chosen from has answered. Chosen early it named the precheck on an
   *  audited site whose precheck had not been read yet (02-1). */
  const settled = headReady && !precheckLoading && lanesSettled;


  /** Triage reads the audit's stored scoreboard, so it needs no crawl — but
   *  it does spend tokens, which is why the control states the estimate
   *  before it is pressed rather than after. */

  /** Computed once and handed to both the "what to do" pane and the strip. */
  const seq = sequenceSteps({
    siteId, current: data?.current, latestRun: run,
    lanes, running, payload, selected: run ?? "",
    held: headReady ? data?.headline?.integrity?.count ?? 0 : null,
    prechecked: Boolean(precheck), precheck, compare: a.compare,
  });

  return (
    <>
      {/* The one audit picker (brief step 1) and the one standing summary
          (brief step 2, CQ-03) in a bar above the card: the pick, and beside
          it the counts that do not follow the pick. The counts stood in a
          pane of their own, "Where it stands", opposite the controls; the
          Tools screen's pair of panes with the same titles counts a
          different thing (one audit's briefs) and keeps its own. The stamp
          names the run that last moved the counts (UX-92) and opens it
          (UX-94); it sat in the pane's aside and keeps its class. */}
      {/* Item 173 (channel ruling 20260917-1125, part B): the audit this
          screen reads, the regressions chip, the mode and the page filter, and
          the reference links, in the shell's bar after the site selector -
          where concept 05 puts them. The same place on every client tab: a
          control that moves between tabs is worse than one that is large on
          some. Inline where no bar slot exists (a caller outside the shell). */}
      <ContextBar>
        <div className={`client-context${page ? " client-context-page" : ""}`}
             data-mode={page ? "page" : "site"}>
          {/* Item 239 step 5: the picker is retired. The current audit, said
              and not chosen: its score, tier and date (amendment 8). A run's
              own record is the Audits tab's "View as this audit saw it". */}
          {/* `data-audit`: the current audit's id once the payload has
              answered ("" for a site with no scored audit), absent before. */}
          <div className="audit-now"
               data-audit={data ? data.current_audit?.run_id ?? "" : undefined}>
            <span className="sel-lbl">Current audit</span>
            <span className="audit-now-text">
              {data?.current_audit
                ? [data.current_audit.score, data.current_audit.tier, stamp(data.current_audit.at)]
                    .filter((x) => x !== null && x !== "").join(" · ")
                : data ? "no scored audit yet" : "…"}
            </span>
          </div>
          {data && (
            <div className="anat-narrow">
        <div className="mode-bar">
          <span className="mode-label">{page || picking ? "Page mode" : "Site mode"}</span>
          {/* Item 181 (11-14): one tab stop for the two segments - the one that
              is on - with arrows between them, as a segmented control is read. */}
          <div className="mode-switch" role="group" aria-label="Scope, arrow keys switch"
               onKeyDown={(e) => {
                 const segs = [...e.currentTarget.querySelectorAll<HTMLButtonElement>(".mode-seg")];
                 const at = segs.indexOf(document.activeElement as HTMLButtonElement);
                 if (at < 0 || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
                 e.preventDefault();
                 segs[at === 0 ? 1 : 0].focus();
               }}>
            <button type="button"
                    className={`mode-seg${page || picking ? "" : " mode-on"}`}
                    aria-pressed={!page && !picking} tabIndex={page || picking ? -1 : 0}
                    onClick={() => { setTyped(null); setPicking(false); if (page) setPage(""); }}>
              Whole site
            </button>
            <button type="button"
                    // Item 181 (02-11): pressed on the press, while a page is
                    // being picked - it did nothing observable until a whole path
                    // matched. Leaving the box empty puts it back.
                    className={`mode-seg${page || picking ? " mode-on" : ""}`}
                    aria-pressed={Boolean(page) || picking} tabIndex={page || picking ? 0 : -1}
                    onClick={() => { setPicking(true); setFocusFind(true); }}>
              One page
            </button>
          </div>
        </div>
        {(page || picking) && (
        <div className="anat-filter">
          {/* A native datalist rather than a select. On a 100-page
              site the select was a scroll to find one path, and typing
              in it only jumped to the first letter. This filters as you
              type and still opens as a list when you click it, with no
              dependency and no custom keyboard handling to get wrong.
              The value is the path; the URL is resolved on the way out,
              because a path is what an operator recognises. */}
          <label className="page-pick">
            {/* No "Narrow to" label row since brief v23 step BK: the mode
                bar above says what this field is for, and a second label
                row pushed the scope bar past its height guard. The name
                moves to `aria-label`, where a reader of the field needs it. */}
            {/* Two pieces of state, because they are two different
                things: what has been typed, and which page is selected.
                Bound to the selection alone, the field could only ever
                hold a *finished* choice — every partial path resolved to
                no page, `page` went empty, and the next render wrote the
                empty value back over what was being typed. Typing
                `/promo` left `/`: the first character matched the home
                page, so the field looked filled rather than broken,
                while the six keystrokes after it went nowhere. The
                placeholder said "type to filter" the whole time. */}
            <input className="input page-find" list="anat-pages" ref={findRef}
                   aria-label="Narrow to a page"
                   onFocus={() => setPicking(true)}
                   onBlur={(e) => { if (!page && !e.currentTarget.value.trim()) setPicking(false); }}
                   value={typed ?? (page ? pathOf(page) : "")}
                   placeholder={`All pages (${data.pages.length}) — type to filter`}
                   onChange={(e) => {
                     const text = e.target.value;
                     setTyped(text);
                     const hit = data.pages.find(
                       (u) => pathOf(u) === text.trim() || u === text.trim());
                     // Only a whole page commits. Clearing the box clears
                     // the selection; a half-typed path leaves the
                     // current one alone rather than dropping it on the
                     // way past.
                     if (hit) setPage(hit);
                     else if (!text.trim()) setPage("");
                   }} />
          </label>
        </div>
        )}
        {/* The page list, whether or not the filter is drawn (item 174): it
            paints nothing, and a reader of the site's pages should not have to
            enter page mode to find them. */}
        <datalist id="anat-pages">
          {data.pages.map((u) => (
            <option key={u} value={pathOf(u)} />
          ))}
        </datalist>
            </div>
          )}
        </div>
      </ContextBar>
      {/* Pages and Notes, beside the nav (item 174, ruling 20260917-1430):
          pane navigation never hides, so it is not in the context that gives
          way when the bar is tight. */}
      {context && <ContextBar slot="topbar-refs">{context}</ContextBar>}
      {/* The head (item 173, parts A, D and 5): the state sentence - a
          headline on the landing, where it is the subject, and one compact
          line on every other tab, where the subject is the pane below - then
          the integrity line on its own line, then the actions with the strip
          beside them. No card, no columns. */}
      <div className={`run-scope run-head${tab === "landing" ? " run-head-landing" : ""}`}
           data-mode={page ? "page" : "site"}>
        {/* Item 174: the reference's eyebrow over the headline. Hidden from
            assistive technology because the pane's own heading, "Where it
            stands", already names the landing; this is the same words for
            the eye. */}
        {tab === "landing" && site && (
          <p className="eyebrow" aria-hidden="true">Where {host(site.domain)} stands</p>
        )}
        {/* Item 181 (02-9, 11-11): one h1 per document, naming the page. On the
            landing the headline is the page; on another tab the pane is, and
            the headline is its context. */}
        {tab !== "landing" && (
          <h1 className="sr-only page-h1">
            {PANE_H1[tab] ?? "Client"}{site ? ` · ${host(site.domain)}` : ""}
          </h1>
        )}
        {/* Item 168: 05's three short sentences with BJ's three facts. */}
        <StateSentence heading={tab === "landing"}
                       headline={headReady ? data?.headline ?? null : null}
                       loading={!headReady && !error}
                       run={selectedRuns.find((x) => x.id === data?.headline?.run_id) ?? null}
                       nextStep={settled && seq.next >= 0 && seq.busyAt < 0 ? seq.steps[seq.next].name : null} />
        <IntegrityLine headline={headReady ? data?.headline ?? null : null}
                       checking={!headReady && !error} />
        {/* Item 174: the regressions chip is an alert about this run, not a
            navigation control, so it sits with the held line under the
            headline rather than in the shell's bar. */}
        {alerts && <Alerts regressions={alerts.regressions} watch={alerts.watch} />}
        {data && (<>
        {/* Rendered text and announced, not a `title` and not a spinner
            that says only "something is happening". The operator has
            just chosen a page and is looking at numbers; what they need
            to know is WHOSE numbers those still are. */}
        {/* Two transitions, two sentences — UX-56's fifth case. Widening
            back to All pages really does leave one page's counts on
            screen while the site-wide reply is in flight, so dropping the
            note there would be UX-13 again; but the operator chose no
            page, and telling them they did is the same false claim in a
            quieter place. The branch is `page`, which is the thing that
            was or was not chosen. */}
        {stale && (
          <p className="muted head-note stale-note"
             role="status" aria-live="polite">
            {dataPage === page
              // Item 179: the page did not move, the audit did.
              ? `${LOADING_WORD} the audit you picked — the counts and evidence `
                + `below are still the previous audit's.`
              : page
              ? `${LOADING_WORD} the page you chose — the counts and evidence `
                + `below are still the previous page's.`
              : `${LOADING_WORD} all pages — the counts and evidence below are `
                + `still the page you were filtered to.`}
          </p>
        )}
        </>)}
        <div className="bl-actions">
          {/* Item 200. The landing's actions are the landing's. On a part page
              they answered "what should I do next for this site" while the
              page asked "what is wrong with this part", and the reader passed
              them, the full board, the pane head and the legend strip before
              the part began. The part has its own controls. */}
          {onLanding && (<>
          <div className="bl-buttons">
            <PrimaryAction step={settled && seq.next >= 0 && seq.busyAt < 0 ? seq.steps[seq.next] : null}
                           count={primaryCount(seq, data?.headline ?? null)}
                           ofTotal={data?.headline?.assessed?.total ?? null} />
            {/* `briefs` is `notRunCount`, not a second filter of its own: this
                call excluded triage alone and so promised 24 where the
                catalogue it opens lists 23 (audit F4). */}
            <SecondaryActions siteId={siteId}
                              next={settled && seq.next >= 0 && seq.busyAt < 0 ? seq.steps[seq.next].name : null}
                              briefs={notRunCount(lanes)}
                              held={headReady ? data?.headline?.integrity?.count ?? 0
                                    : error ? 0 : null} />
          </div>
          </>)}
          {/* Outside the landing's gate (item 200): a site nothing has run on
              does not arrive on the landing - it lands on Audit (`views.tsx`,
              `young`) - and this sentence is its first instruction there. Its
              own condition, nothing having run, is what places it. */}
          {settled && !precheck && !data?.current?.last_audit && !running && (
            <p className="muted seq-fresh">
              Nothing has run here yet. Run the precheck - free, a few seconds - then
              start an audit.
            </p>
          )}
          {/* The strip stays on every tab - it is the only way between Audit,
              Analyses, Record and Client report - and on every tab but the
              landing it is the way and not the board: the same four pills in
              the same order, without the chapter heads and their captions. */}
          <Sequence {...destinationsOf(seq)} here={DEST_OF_TAB[tab] ?? -1}
                    compact={!onLanding}
                    report={data?.current?.report_state ?? null}
                    held={headReady ? data?.headline?.integrity?.count ?? 0 : null} />
        </div>
        {error && <ErrorNote error={error} onRetry={retry} retrying={loading} />}
      </div>
    </>
  );
}

/** Where a client screen's context controls render (item 173): the shell's bar
 *  slot, `#topbar-context`, through a portal - or in place, where the slot does
 *  not exist, so a caller outside the shell still gets its controls. */
function ContextBar({ children, slot: slotId = "topbar-context" }: {
  children: ReactNode;
  /** Which of the shell's bar slots: the context after the site selector, or
   *  `topbar-refs`, the reference panes beside the nav (item 174). */
  slot?: string;
}) {
  // Three states. `undefined` until the slot has been looked for, rendering
  // nothing: rendering in place first and portalling a frame later drew the
  // controls in the head for that frame, and a test reading the bar in that
  // window found nothing there. `null` once looked for and absent.
  const [slot, setSlot] = useState<HTMLElement | null | undefined>(undefined);
  useEffect(() => { setSlot(document.getElementById(slotId)); }, [slotId]);
  if (slot === undefined) return null;
  return slot ? createPortal(children, slot) : <>{children}</>;
}

/** The two secondaries beside the primary action (item 173, part D). The
 *  catalogue, counted by the briefs not run; and building the client report.
 *  Held by the Critical-and-High guard, the report button is `aria-disabled`
 *  - still focusable - and described by the integrity line, which states the
 *  reason in text: a `disabled` button cannot be focused and a `title` is not
 *  reliably announced, so the reason would have reached mouse users only.
 *  "Build", not concept 05's "Send": `generate.py` builds, nothing sends. A
 *  secondary that would repeat the primary is not drawn. */
const PANE_H1: Record<string, string> = {
  history: "Audit", triage: "Triage", findings: "Analyses", analyses: "Analyses",
  all: "Record", pages: "Pages", notes: "Notes", precheck: "Precheck",
};

function SecondaryActions({ siteId, next, briefs, held }: {
  siteId: string; next: string | null; briefs: number | null;
  /** Unassessed Critical and High, or `null` while that has not been read.
   *  Unread is held, not live (item 179): a live link during the load was the
   *  guard failing open for as long as the slowest request took (08-6). */
  held: number | null;
}) {
  const catalogue = `#/sites/${siteId}?tab=findings`;
  const reports = `#/sites/${siteId}/reports`;
  return (
    <>
      {next !== "Analyses" && (
        <LinkButton className="bl-secondary" href={catalogue}
              onClick={goHandler(catalogue)}>
          Open the catalogue{briefs != null ? ` · ${briefs}` : ""}
        </LinkButton>
      )}
      {next !== "Client report" && (held == null || held > 0
        ? <SecondaryButton className="bl-secondary bl-held"
                  aria-disabled="true" aria-describedby="integrity-line"
                  onClick={(e) => e.preventDefault()}>
            Build the client report
          </SecondaryButton>
        : <LinkButton className="bl-secondary" href={reports}
                onClick={goHandler(reports)}>
            Build the client report
          </LinkButton>)}
    </>
  );
}


/** Parts a rendered test draws on the layout of last resort (brief v25 step
 *  BP). That layout's real users are Accessibility, AI surface, Backlinks and
 *  Local & citations, and the test fixture holds no page-level finding in any
 *  of them, so the tests guarding its machinery name fixture parts that do
 *  (`tests/last_resort.py`). Read once from the window; nothing in the
 *  product sets it. */
const LAST_RESORT_PARTS: readonly string[] = (() => {
  try {
    const v = (window as unknown as { __CLAUDITSEO_LAST_RESORT__?: unknown }).__CLAUDITSEO_LAST_RESORT__;
    return Array.isArray(v) ? v.map(String) : [];
  } catch { return []; }
})();

/** The landing (brief v24 step BM): the three lanes as the body of the site
 *  route, at full height. They were the bar's three columns under BL; the bar
 *  keeps the sentence, the action, the integrity line, the mode switch, the
 *  picker and the band. */
export function SiteLanding({ siteId, a }: { siteId: string; a: AnatomyScreen }) {
  const { data, error, lanes, dataPage: page, ready } = a;
  const { runs: selectedRuns } = useSelection();
  if (!data) {
    return <p className="muted cl-landing-wait" role="status">
      {error ? "not loaded" : `${LOADING_WORD}…`}
    </p>;
  }
  // `page` is the payload's own (item 179): until the reply for a new scope
  // lands, the lanes stay whole for the scope they were read for, and the
  // head's stale-note says whose they are. Never one payload's counts under
  // the other scope's words (02-2).
  return (
    <div className="cl-landing" data-mode={page ? "page" : "site"} aria-busy={!ready}>
      {/* Before the first chip, where a reader starts (item 166, which names
          this landing as one of the two surfaces that adopt on arrival). */}
      <Legend ids={["lane-waiting", "lane-measured", "lane-settled", "count-open",
                    "count-zero", "population-crawl", "population-record", "not-assessed"]} />
      <ClientLanes siteId={siteId} page={page} current={data.current}
                   // The mode's arithmetic is a footnote to the parts it sums
                   // (item 174): nothing sits between the actions and the
                   // lanes but the legend, so it rides in the parts' head.
                   arith={<ModeArith page={page} standing={data.total}
                                     parts={data.categories.filter(isPart)
                                       .reduce((n, x) => n + x.total.value, 0)}
                                     siteOnly={data.site_only ?? 0} />}
                   categories={data.categories.filter(isPart)} headline={data.headline ?? null}
                   lanes={lanes} outstanding={data.total} record={data.pages.length}
                   pops={data.populations ?? null}
                   runState={{
                     running: selectedRuns.find((r) => r.kind === "audit" && isInFlight(r.status)) ?? null,
                     last: completedAudits(selectedRuns)[0] ?? null,
                     audits: completedAudits(selectedRuns).length,
                   }}
                   standingHead={data.current?.last_move && (() => {
                     // The run that last moved the standing counts (UX-92),
                     // not the picker's: they do not follow the pick. It
                     // opens the run (UX-94) and keeps its class.
                     const move = data.current.last_move;
                     const mover = selectedRuns.find((r) => r.id === move.run_id);
                     const word = mover ? scopeWord(scopeOf(mover)) : null;
                     const kind = RUN_KIND[move.kind] ?? move.kind;
                     return (
                       <a className="cur-when" href={`#/runs/${move.run_id}`}
                          data-run={move.run_id}
                          title="Open the audit these counts are computed from - the one that last moved them">
                         as of {move.at.slice(0, 10)} {move.at.slice(11, 16)}
                         {move.kind !== "audit" ? ` · ${kind}` : ""}
                         {word ? ` · ${word}` : ""}
                       </a>
                     );
                   })()} />
    </div>
  );
}


/** Which part a ranked check lands in (brief v2 step C, WF-07), for every
 *  reader of the ranking - the sidebar's rank column and the Analyse pane's
 *  own table (brief v4 Item 3a).
 *
 *  The server names a part only when the triage check is a check id it
 *  knows, and triage names its own: `heading-skip-multiple`,
 *  `img-alt-missing-fix-incomplete`, `sitemap-regression` - a sweep's
 *  check with a suffix, or its family with a different tail. The join is by
 *  check-id family: the longest run of leading hyphen-separated segments
 *  the triage check shares with a check open in a part, at least one
 *  segment, and the part must be the only one at that length - a tie
 *  places nothing rather than guessing. The server's own answer, when it
 *  has one, wins. */
/** Whether a category is a part of the page the operator can open (item
 *  238). "Prioritise & report" is not: it is the engine's catch-all, its
 *  run-notes and a slot for tools that write to no part, with no brief and
 *  no renderer. The Record's part filter and `rankParts` already left it
 *  out; the strip, the switcher and the part route now do too. The row stays
 *  in the payload, so `categorise()`'s fallback still has somewhere to file. */
export const isPart = (c: Pick<Category, "group">) => c.group !== "workflow";

export function rankParts(categories: Category[],
                          triage: { ranked: { check: string; category?: string | null }[] } | null) {
  const partForCheck = (check: string): string | null => {
    const segs = check.split("-");
    let best: { key: string; n: number } | null = null;
    let tie = false;
    for (const c of categories) {
      if (!isPart(c)) continue;
      for (const f of c.findings) {
        const other = f.check_id.split("-");
        let n = 0;
        while (n < segs.length && n < other.length && segs[n] === other[n]) n++;
        if (n === 0) continue;
        if (!best || n > best.n) { best = { key: c.key, n }; tie = false; }
        else if (n === best.n && best.key !== c.key) tie = true;
      }
    }
    return best && !tie ? best.key : null;
  };
  const rankOf = new Map<string, number>();
  const partOfRank = new Map<string, string | null>();
  triage?.ranked.forEach((r, i) => {
    const part = r.category ?? partForCheck(r.check);
    partOfRank.set(r.check, part);
    if (part && !rankOf.has(part)) rankOf.set(part, i + 1);
  });
  const placed = triage ? [...partOfRank.values()].filter(Boolean).length : 0;
  return { rankOf, partOfRank, placed };
}

/** A "read" pill per analysis (item 239 step 4): the newest run of that
 *  tool on this site, dated, opening the report on the run it is on. Never
 *  a pill that opens to a 404. */
function ReadAnalysis({ items, reading, onRead }: {
  items: NonNullable<Category["analysed"]>;
  reading: string | null;
  onRead: (tool: string, onRun: string) => void;
}) {
  return (
    <>
      {items.map((it) => (
        <SecondaryButton key={it.tool} className="read-analysis"
                data-run={it.run_id}
                title={it.crawl_at ? `Read the crawl of ${stamp(it.crawl_at)}` : undefined}
                onClick={() => onRead(it.tool, it.run_id)}>
          {reading === it.tool ? "hide" : "read"} {it.tool}
          <span className="muted"> · {it.at ? stamp(it.at) : "?"}</span>
        </SecondaryButton>
      ))}
    </>
  );
}

export function AnatomyView({ siteId, a, states, selected, onSelect, rerunAsk = null,
                              onRunAll, onRerun }: {
  siteId: string; a: AnatomyScreen;
  /** The shop header's re-run glyph (brief v24 step BO). */
  onRerun?: (key: string) => void;
  /** Run the part's briefs that are not run (brief v4 Item 3f): opens the
   *  catalogue drawer on its confirm panel, scoped to the part. */
  onRunAll?: (part: string) => void;
  /** The part in hand, owned by the screen (brief v4 Item 3a): the sidebar
   *  beside every pane selects it, and this pane opens it. */
  selected: string;
  onSelect: (key: string) => void;
  /** A re-run pressed on the sidebar: open the part on its refresh
   *  confirmation. A counter, so the same part can be asked twice. */
  rerunAsk?: { key: string; n: number } | null;
  /** The site's record, uncapped, for the causes' counts (brief v2 step E). */
  states?: FindingState[];
}) {
  const { data, error, page, setPage, setTick, fix, run, precheck, stale } = a;
  /** One scope per pane (brief v12 step AM): the record's states narrowed
   *  as the findings payload is, so every block below counts the same
   *  pages - the causes, their tags, the replacement table. */
  const scoped = narrowStates(states ?? [], page);

  /** The depth bar the operator pressed, from the address (brief v16b), for
   *  the reason `cost` gives at length in `useAnatomy`: one reader, one
   *  writer, so a pasted link and a press are the same event. Held as raw
   *  because the payload it is checked against arrives from the network and
   *  the address does not wait for it; `depthPicked` does the checking. */
  const [depthRaw, setDepthRaw] = useState(depthFromHash);
  useEffect(() => {
    const read = () => setDepthRaw(depthFromHash());
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);

  /** Whether the picker's run is one a brief may run against (brief v6
   *  step V3), and the sentence that says why not. */
  const { runs: pickedRuns } = useSelection();
  const narrowNote = narrowPickNote(pickedRuns.find((r) => r.id === run));
  /** What is in the page filter's box, which is not the same as which page
   *  is selected (brief v3 step J: the filter is this pane's, since this
   *  pane is what it narrows - it stood in the scope bar as a fourth row
   *  no other pane read). */
  /** Causes before instances (brief v2 step E, UX-07). A cause is a check
   *  from one source - the sweep's rows and a brief's are never merged,
   *  because their counts are not meant to agree - with every open finding
   *  it raised in this part counted from the site's record (`states`,
   *  uncapped), its worst severity, the pages those findings name, and the
   *  templates among them: the longest path prefix ten or more of its
   *  pages share. The part's own findings (the worst fifty) are the
   *  instances that open beneath. */
  /** `templatesOf` and what a `Template` is sit at module scope since brief
   *  v16d, because the Headings site block groups its own rows by the same
   *  rule and a second copy of "a first segment ten or more pages share" is
   *  how two tables on one screen come to disagree about a template. */
  const [openTemplates, setOpenTemplates] = useState<ReadonlySet<string>>(new Set());
  const [templateAsk, setTemplateAsk] =
    useState<{ key: string; prefix: string; fps: string[] } | null>(null);
  const [templateBusy, setTemplateBusy] = useState<string | null>(null);
  const [templateErr, setTemplateErr] = useState<string | null>(null);
  const acceptTemplate = async (ask: NonNullable<typeof templateAsk>) => {
    setTemplateBusy(`${ask.key}|${ask.prefix}`);
    setTemplateErr(null);
    try {
      for (const fp of ask.fps) {
        await api.post(`/api/sites/${siteId}/states/${fp}`, { state: "accepted-risk" });
      }
      setTemplateAsk(null);
      setTick((t) => t + 1);
    } catch (e) {
      setTemplateErr(`accept risk on ${ask.prefix || "the pages with no shared template"} `
                     + `failed part way: ${(e as Error).message}. The findings it reached `
                     + "are moved; the rest are not - reload to see which.");
    } finally {
      setTemplateBusy(null);
    }
  };
  type Cause = { key: string; check: string; dimension: string; source: string;
                 severity: string; summary: string; count: number; shown: number;
                 pages: number;
                 /** The same fault rate as `pages`, over the population the
                  *  rule permits (item 155): affected OF ASSESSED, so the
                  *  denominator is the crawl and never the record. `pages`
                  *  stays for the sort and for the verify bar, which ask how
                  *  many pages the record names rather than how prevalent the
                  *  fault is in what was looked at. */
                 prev: Count; unfetched: number;
                 templates: Template[]; rows: Finding[];
                 /** Per source (brief v10 step AF): `sweep 10 · brief 10` on
                  *  the one row rather than two rows for one check. */
                 sources: Record<string, number>;
                 /** Brief-only rows the sweep has not corroborated (brief v12
                  *  step AM): counted in `count` and `brief`, and tagged. */
                 candidates: number };
  const [openCauses, setOpenCauses] = useState<ReadonlySet<string>>(new Set());
  /** Narrow the record to one check: open its cause group and scroll to it
   *  (brief v16g). Opening without scrolling would move a row the reader
   *  cannot see, and scrolling without opening would land them on a
   *  collapsed row — the two halves are one action. */
  const openCause = (checkId: string) => {
    setOpenCauses((prev) => new Set(prev).add(checkId));
    // After the row has been told to open, so it is its expanded height
    // that is scrolled into view.
    requestAnimationFrame(() => document
      .querySelector(`tr.cause-row[data-cause="${CSS.escape(checkId)}"]`)
      // `{ block: "center" }` and no `behavior`, which is this tree's one
      // scroll convention — stated at the call `anatomy.tsx` already had
      // and held by
      // `test_every_scroll_into_view_uses_the_convention_already_in_the_tree`.
      ?.scrollIntoView({ block: "center" }));
  };
  const causesOf = (c: Category): Cause[] => {
    const order = ["critical", "high", "medium", "low", "info"];
    // A pressed depth bar narrows this list to the pages at that depth
    // (brief v16b) - the same thing the page filter does, over a set of
    // pages rather than one. Both halves are narrowed, the payload's
    // findings and the record's states, for the reason `narrowStates` gives:
    // one scope per pane, or the counts and the rows describe different
    // populations. Only the crawl part has bars to press.
    //
    // Each row's own URL list is narrowed with it, not just the set of rows:
    // the Pages column counts that list, and a row kept for one page at this
    // depth while still counting forty would be the count describing a
    // population the reader is not looking at.
    const pick = depthPicked(c.depth, depthRaw);
    const atDepth = pagesAtDepth(c.depth, pick);
    // The crawl population this list is read against. A pressed depth bar
    // narrows it to the pages crawled AT that depth, read off the depth
    // payload's own map (`at`: crawled URL -> depth), which is the same
    // source the row filter above uses - so the numerator and the
    // denominator cannot describe two different populations.
    const site = data?.populations ?? null;
    const depthPops: Populations | null = (atDepth && site)
      ? { ...site,
          crawl: { size: Object.values(c.depth?.at ?? {}).filter((d) => d === pick).length,
                   basis: "crawled at this depth",
                   paths: Object.entries(c.depth?.at ?? {})
                                .filter(([, d]) => d === pick)
                                .map(([u]) => pathKey(u)) } }
      : site;
    const findings = atDepth
      ? c.findings.map((f) => ({ ...f, urls: f.urls.filter(atDepth) }))
                  .filter((f) => f.urls.length)
      : c.findings;
    const states = atDepth
      ? scoped.map((st) => ({ ...st, affected_urls: st.affected_urls.filter(atDepth) }))
              .filter((st) => st.affected_urls.length)
      : scoped;
    const checkIds = new Set(findings.map((f) => f.check_id));
    const by = new Map<string, Cause>();
    const wordOf = (source: string | undefined) => (source === "deterministic" ? "sweep" : "brief");
    for (const f of findings) {
      // One cause per check (brief v10 step AF): a brief's row on the
      // sweep's check id joins the sweep's under one row, and the two are
      // counted apart on it - whatever dimension the brief's row was
      // stored under, since a legacy brief's still says `EXP:<brief>`.
      const key = f.check_id;
      let g = by.get(key);
      if (!g) {
        g = { key, check: f.check_id, dimension: f.dimension, source: f.source,
              severity: f.severity, summary: f.summary, count: 0, shown: 0,
              pages: 0, prev: makeCount(0, "site"), unfetched: 0,
              templates: [], rows: [], sources: {}, candidates: 0 };
        by.set(key, g);
      }
      if (f.source === "deterministic" && g.source !== "deterministic") {
        g.source = f.source; g.summary = f.summary; g.dimension = f.dimension;
      }
      g.rows.push(f);
      g.shown += 1;
      if (order.indexOf(f.severity) < order.indexOf(g.severity)) g.severity = f.severity;
    }
    // The part's other checks (brief v11 step AH): a part page that lists
    // only what is wrong cannot say what was measured and passed. Counted
    // below like the rest, since a brief-only check can hold candidates
    // the findings payload does not carry.
    for (const full of c.brief_checks ?? []) {
      const [dimension, check] = full.includes("/") ? full.split("/", 2) : ["", full];
      if (by.has(check)) continue;
      by.set(check, { key: check, check, dimension, source: "deterministic", severity: "info",
                      summary: "", count: 0, shown: 0, pages: 0,
                      prev: makeCount(0, "site"), unfetched: 0,
                      templates: [], rows: [], sources: {}, candidates: 0 });
    }
    // Counts and pages from the record, narrowed as the findings are
    // (brief v12 step AM) and not capped at fifty; a check the record
    // does not know counts what is here. Candidates count and are tagged:
    // the corroboration rule's output made visible, the same way the
    // replacement table shows them.
    for (const g of by.values()) {
      const mine = states.filter((st) =>
        st.check_id === g.check
        && (st.state === "open" || st.state === "regressed" || st.state === "candidate"));
      const counted = mine.length ? mine.map((st) => wordOf(st.source)) : g.rows.map((f) => wordOf(f.source));
      g.sources = counted.reduce<Record<string, number>>((m, w) => ({ ...m, [w]: (m[w] ?? 0) + 1 }), {});
      g.candidates = mine.filter((st) => st.state === "candidate").length;
      const urls = mine.length ? mine.flatMap((st) => st.affected_urls)
                               : g.rows.flatMap((f) => f.urls);
      g.count = mine.length || g.rows.length;
      g.pages = new Set(urls).size;
      // The same set, as a count that carries its population (item 155).
      // Under a depth narrow the population narrows with it: the crawl at
      // THAT depth, or a row kept for one page at this depth while counting
      // forty would be a count describing a population the reader is not
      // looking at - the same worry this function's own note above records,
      // now applied to the denominator as well as the numerator.
      const pv = prevalence(urls, depthPops);
      g.prev = pv.count;
      g.unfetched = pv.unfetched;
      if (g.count && g.severity === "info" && mine.length) {
        // A candidate-only cause has no finding to take a severity from.
        const worstOf = mine.map((st) => st.severity).sort((x, y) => order.indexOf(x) - order.indexOf(y))[0];
        if (worstOf) g.severity = worstOf;
      }
      g.templates = templatesOf(mine.length
        ? mine.map((st) => ({ fingerprint: st.fingerprint, urls: st.affected_urls,
                              state: st.state, names_a_page: st.names_a_page }))
        : g.rows.map((f) => ({ fingerprint: f.fingerprint, urls: f.urls,
                               state: f.state, names_a_page: f.names_a_page })));
    }
    return [...by.values()].sort((x, y) => Number(x.count === 0) - Number(y.count === 0)
                                           || order.indexOf(x.severity) - order.indexOf(y.severity)
                                           || y.pages - x.pages);
  };

  /** Which findings have their page list open (FEATURES.md F-11).
   *
   *  Held here rather than inside the row so a row is not remounted into a
   *  closed state by every re-render the fix loop causes — a tick re-reads
   *  the payload, and a disclosure that shuts when you tick the row beside
   *  it is the evidence going away as you work. Keyed by fingerprint, which
   *  survives a re-fetch; a finding that leaves the payload leaves a dead
   *  key, which costs nothing. */
  const [openPages, setOpenPages] = useState<ReadonlySet<string>>(new Set());
  const togglePages = (fp: string) => setOpenPages((prev) => {
    const next = new Set(prev);
    if (!next.delete(fp)) next.add(fp);
    return next;
  });
  const setSelected = onSelect;
  // A cause opened in one part is not open in the next.
  useEffect(() => { setOpenCauses(new Set()); }, [selected]);
  const [busyTool, setBusyTool] = useState<string | null>(null);
  /** Which page panel is open, if any, and whether it is mid-request — the
   *  panel owns its own run button, so it has to say. */
  const [panel, setPanel] = useState<string | null>(null);
  /** The finding a panel was opened from, if it was opened from one (F-02).
   *  Cleared whenever the panel is opened by the pill instead, so a section
   *  answer never carries a stale finding's name. */
  const [panelCheck, setPanelCheck] = useState<string | null>(null);
  const [panelBusy, setPanelBusy] = useState(false);
  /** The report being read inline. Reading is free — it is already stored —
   *  so it opens here rather than costing a navigation. */
  const [reading, setReading] = useState<{ tool: string;
                                           report: string | null;
                                           contract?: Contract | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  /** Which half of the actions row is in flight (brief v13 step AO).
   *  Declared with the pane's other state, above every early return: a
   *  hook after one is a hook the next render may not reach. */
  const [partBusy, setPartBusy] = useState<"sweep" | "brief" | null>(null);
  // Nine of seventeen categories can sit at zero, which is half a sidebar of
  // inert rows. Off by default: a category that found nothing is still worth
  // seeing once, because "we looked and it was clean" is a real answer.

  /** Triage, on the rail it ranks (brief step 3, WF-03 and UX-04).
   *
   *  The Triage pane's only consumers were this rail and the catalogue
   *  above it, so the pane is retired: the ranking is a number beside each
   *  part's name, the control that makes it stands at the head of the
   *  list, and the ranked list itself opens in the column beside the rail
   *  on request. The rank is the position of the first ranked check that
   *  lands in the part - the server names each check's part by the same
   *  registry this tree is built from - and a part triage did not rank
   *  shows a dash, which is a fact about triage and not about the part.
   *  `?tab=triage` still lands here (`views.tsx`'s alias table). */
  const { lanes, bumpLanes } = a;
  /** The section whose refresh the rail asked to open (brief step 4,
   *  WF-02): the row's re-run control selects the section and mounts its
   *  `SectionRefresh` on the confirmation, so a re-run is one press from
   *  the rail rather than a section opened first and a control found
   *  inside it. Cleared by any other selection, so a section opened by its
   *  name never starts on a confirmation it was not asked for. */
  const [refreshFor, setRefreshFor] = useState<string | null>(null);
  const [refreshAsk, setRefreshAsk] = useState(0);
  useEffect(() => {
    if (!rerunAsk) return;
    setReading(null);
    setSelected(rerunAsk.key);
    setRefreshFor(rerunAsk.key);
    setRefreshAsk((n) => n + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rerunAsk?.n]);
  /** The drawer (brief step 5): the finding it was opened from, if one,
   *  and the depth chosen in it. Both reset with the selection, so a
   *  drawer opened for one part never carries another part's finding. */
  const [drawerFinding, setDrawerFinding] = useState<DrawerFinding>(null);
  /** The chosen depth, or null for the engine's own choice - which the drawer
   *  shows as the Quick pill (brief v5 step U): the engine starts at Quick
   *  and escalates where the evidence asks, and the pill's title says so. */
  const [depth, setDepth] = useState<DepthKey | null>(null);
  useEffect(() => { setDrawerFinding(null); setDepth(null); }, [selected]);
  /** Which part a ranked check lands in (brief v2 step C, WF-07).
   *
   *  The server names a part only when the triage check is a check id it
   *  knows, and triage names its own: `heading-skip-multiple`,
   *  `img-alt-missing-fix-incomplete`, `sitemap-regression` - a sweep's
   *  check with a suffix, or its family with a different tail. So on the
   *  operator's site every part read "–" under "Ranked 5 checks". The join
   *  here is by check-id family: the longest run of leading hyphen-separated
   *  segments the triage check shares with a check open in a part, at
   *  least one segment, and the part must be the only one at that length -
   *  a tie places nothing rather than guessing. The server's own answer,
   *  when it has one, wins. */
  // `error` is the fix loop's own, and is not the `error` from this
  // screen's `useFetch` above — that one replaces the whole screen. A
  // refusal from the verify route must not, so it is named apart and
  // rendered beside the bar that provoked it.
  const { marked, outcome, verifying, judged, error: fixError } = fix;

  // The panel names a tool that belongs to the section it was opened
  // from; leaving that section must not leave its result behind. And a
  // page change closes it for the same reason: the panel is about one page.
  useEffect(() => { setPanel(null); }, [siteId, page]);
  useEffect(() => { setPanel(null); setPanelBusy(false); }, [selected]);

  /** Everything else on this screen that is about one client, dropped when
   *  the client changes.
   *
   *  None of it was, and switching sites carried all of it across. The open
   *  report kept the previous client's brief, so one company's entity graph
   *  sat under another company's name in the header. The selected section
   *  and its co-occurrence marking came too.
   *
   *  The page filter is not here — it is derived in `useAnatomy`, because it
   *  was the one that concealed itself: a <select> cannot display a value
   *  that is not among its options, so the control read "All pages" while
   *  the request still carried the old URL. The screen was filtered and said
   *  it was not, and every category on the new client read 0. The picker's
   *  own text is the header's now, cleared by the header's site key. */
  useEffect(() => {
    // The selected part is the screen's since brief v4 Item 3a, and the
    // screen clears it with the site; clearing it here too wiped a part
    // chosen on another pane the moment this one mounted.
    setReading(null);
    setPanel(null);
  }, [siteId]);

  // The failure and the wait are both rendered once, by the header above,
  // which reads the same fetch. A second `ErrorNote` here would announce the
  // same sentence twice to a screen reader — but the pane's head promises
  // "what is open" above this, so the absence is said, once, in text.
  if (error) {
    return (
      <p className="muted head-note anat-unread">
        What is open could not be read — the failure, and the control that
        tries again, are in “Where it stands” above.
      </p>
    );
  }
  if (!data) return null;

  // Item 238: `?part=workflow` resolves to no part, and so lands where any
  // unknown part does - on the Analyses shop.
  const byKey = Object.fromEntries(data.categories.filter(isPart).map((c) => [c.key, c]));
  const current = selected ? byKey[selected] : undefined;
  /** The parts that render as three blocks - actions, what the page has
   *  now, fixes (brief v13 step AO). A part with no renderer keeps the
   *  page it had, which is how Headings waits for brief v14. */
  const threeBlocks = Boolean(current && PART_RENDERERS[current.key]
                              && !LAST_RESORT_PARTS.includes(current.key));
  /** The bounds the "now" card grades against: the engine's own, so a
   *  badge never disagrees with the check that produced the finding. */
  const bounds = {
    titleMin: data?.guidelines?.title?.min ?? 10,
    titleMax: data?.guidelines?.title?.max ?? 65,
    descMin: data?.guidelines?.meta_description?.min ?? 120,
    descMax: data?.guidelines?.meta_description?.max ?? 160,
  };
  /** Which brief writes to this part, from the lanes payload rather than
   *  a list here (brief v11 step AI). */
  const briefOf = (c: Category): string | null =>
    [...(lanes?.ready ?? []), ...(lanes?.available ?? [])]
      .find((a) => a.part === c.key)?.tool ?? null;
  /** The free half of the actions row, and it now branches into two
   *  different KINDS of act rather than two spellings of one (item 189).
   *
   *  **Page mode commits.** `/refresh` is one page for one dimension: the
   *  page is named in the request, the run scores nothing and may not clear a
   *  site-scoped finding, and it answers in seconds. The caption already says
   *  what happens, so a confirmation would be a step between the operator and
   *  a thing they correctly expect.
   *
   *  **Site mode asks.** It used to post `/audits` with `tier: "auto"` from
   *  rest - a fresh adaptive crawl of the whole site, minutes of wall clock, a
   *  new run row, a new composite, and a new set of finding states that move
   *  the standing position. None of that is what "re-check this part"
   *  suggests, and none of it was confirmed, because the control spends no
   *  money and the confirmations here are for spends and deletes.
   *
   *  So the press opens the confirmation that already exists for this exact
   *  request - `SectionRefresh`, via the same `refreshFor`/`refreshAsk` pair
   *  the rail's re-run control uses - and that component makes the POST. The
   *  unconfirmed one is gone rather than guarded: two paths to one audit is
   *  the second launcher F-06 refuses.
   *
   *  Why it was unconfirmed on this layout only: `ReauditDrawer` renders when
   *  `!threeBlocks` and `PartPage` when `threeBlocks`, so the parts with no
   *  renderer have had the confirmation all along and the parts with one never
   *  could. An inconsistency that arrived with the layout, not a decision. */
  const recheckPart = async () => {
    if (!current?.refresh) return;
    if (!(page && current.refresh.per_page)) {
      setRefreshFor(current.key);
      setRefreshAsk((n) => n + 1);
      return;
    }
    setPartBusy("sweep");
    setActionError(null);
    try {
      await api.post(`/api/sites/${siteId}/refresh`, { url: page, section: current.key });
      setTick((t) => t + 1);
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setPartBusy(null);
    }
  };
  // Empty while a page filter is active — on one page every category shares
  // that page, so the signal would fire everywhere and mean nothing.
  const rel = (selected && data.related[selected]) || {};

  const readSection = async (tool: string, onRun?: string) => {
    if (reading?.tool === tool) { setReading(null); return; }
    const from = onRun ?? run;
    if (!from) return;
    setActionError(null);
    try {
      // The run the report is on (brief v6 step V4) - the picker's, or the
      // other run of this site the pill names - never a run that has none.
      const got = await api.get<{ report?: string; contract?: Contract | null }>(
        `/api/runs/${from}/expert/${tool}`);
      setReading({ tool, report: got.report ?? null, contract: got.contract ?? null });
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  /** `reopen` re-reads the report afterwards, which is what a re-run from
   *  inside an open report is for — closing it to show a spinner and leaving
   *  the operator to find it again would lose the thing they were reading. */
  /** `body` carries the Speed part's depth pill (brief v19 step BC). Every
   *  other caller sends nothing and gets what it always got. */
  const runSection = async (tool: string, reopen = false,
                            body?: Record<string, unknown>) => {
    // Item 239 step 5: against the part's reference crawl - the newest
    // reading of the site that measured its dimension - not a picked run.
    const target = current?.sweep_run?.run_id ?? run;
    if (!target) return;
    setBusyTool(tool);
    setActionError(null);
    try {
      await api.post(`/api/runs/${target}/expert/${tool}`, body ?? {});
      if (reopen) {
        const got = await api.get<{ report?: string; contract?: Contract | null }>(
          `/api/runs/${target}/expert/${tool}`);
        setReading({ tool, report: got.report ?? null, contract: got.contract ?? null });
      }
      setTick((t) => t + 1);
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusyTool(null);
    }
  };

  /** Is something running against this section *right now*?
   *
   *  The server's `analysing` list is the truth once it has been asked, but
   *  it is only re-read when the tree refreshes — which happens after the
   *  work finishes. So starting an analysis left the dot hollow for its whole
   *  duration and it turned purple at the end, which reads as nothing having
   *  happened until suddenly it had.
   *
   *  A page panel never appeared there at all: it runs through its own
   *  endpoint rather than the expert queue, so the server has nothing to
   *  report about it. This browser is the only thing that knows.
   */
  const liveHere = (c: Category) =>
    Boolean(c.analysing?.length
            || (busyTool && c.tools.includes(busyTool))
            || (panelBusy && panel && c.tools.includes(panel)));


  return (
    <>
      {/* The drawer's column only where a drawer stands: a part that
          renders as three blocks has no drawer, and its content takes the
          width the column was holding (brief v13 step AO). */}
      <div className={`anat-layout${current?.refresh && !threeBlocks ? " anat-with-drawer" : ""}`}>
        <section className="anat-pane">
          {!current ? (
            <Card>
              {/* The best sentence this screen produces: "which one first",
                  above the list it names. */}
              {!page && (
                <SharedCause data={data} byKey={byKey} onPick={setSelected} />
              )}
              {/* Analyses with no part open IS the shop (brief v24 steps BN
                  and BO; channel ruling 2026-09-15): every part, ranked, each
                  header opening its part. The same list as the drawer, but not
                  a drawer - `.catalogue-drawer` matches the aside only, and the
                  aside is not mounted while no part is open, so the list is
                  never on the screen twice. */}
              <section className="catalogue-shop" aria-label="Every part and its analyses">
                <CatalogueList siteId={siteId} a={a} onRerun={onRerun} />
              </section>
            </Card>
          ) : (
            <Card>
              {/* Item 181: a part's name is the pane's section heading, h2. */}
              <h2 className="part-h2">{current.label}</h2>
              {/* Triage's rank for this part, on the part itself (channel
                  ruling 2026-09-15, item 4): the sidebar's digit, which the
                  shop header also carries. */}
              {(() => {
                const r = lanes?.triage ? rankParts(data.categories, lanes.triage).rankOf.get(current.key) : undefined;
                return r != null ? (
                  <p className="part-rank muted">
                    {/* "by triage" and the staleness suffix went with item
                        196: the ranking is the audit's own, computed from
                        what is open, so there is no second author to name and
                        nothing that can be an older audit's. */}
                    ranked {r}
                  </p>
                ) : null;
              })()}
              {/* The part header states coverage once, from 150 BJ (item
                  155): `45 of 53 on the site, 85%`. Above the blocks and
                  outside the layout branch, because it is the scope every
                  count below is read against and both layouts count. Nothing
                  lower restates it - that is the redundancy the rule exists
                  to avoid, and it is why the length strips need neither 42
                  mute bars on a Twenty22 T1 nor a second absent tone. */}
              <CoverageLine headline={data.headline ?? null} page={page} />
              {/* Item 185: the way to the other parts, above the part DETAIL
                  and kept in view - which is where the item asked for it, and
                  not above the part's own name. The first build led the card
                  with this strip and pushed the h2 to second, so a section
                  heading no longer led its section and the reader was offered
                  every part before being told which one they were in. Outside
                  the layout branch for the same reason the coverage line is:
                  both layouts are a part, and choosing the next one happens in
                  both. */}
              <PartSwitcher siteId={siteId} categories={data.categories.filter(isPart)}
                            current={current.key} pops={data.populations ?? null} />
              {threeBlocks ? (
                <PartPage part={current} page={page} facts={data.facts}
                          states={scoped} sweep={current.sweep_run ?? data.sweep_run ?? null}
                          lanes={lanes} pages={data.pages.length}
                          pops={data.populations ?? null}
                          bounds={bounds} cost={a.cost} runId={run ?? null}
                          siteId={siteId} onStateChanged={a.changed}
                          onRecheck={recheckPart} onPage={setPage}
                          recheckConfirm={current.refresh && !(page && current.refresh.per_page) ? (
                            <SectionRefresh key={`part-${current.key}`} siteId={siteId}
                                            label={current.label}
                                            refresh={current.refresh}
                                            startConfirming={refreshFor === current.key}
                                            ask={refreshAsk} />
                          ) : null}
                          onRerun={async () => { const t = briefOf(current);
                                                 if (!t) return;
                                                 setPartBusy("brief");
                                                 await runSection(t);
                                                 setPartBusy(null); }}
                          busy={partBusy} error={actionError}
                          briefNote={!lanes ? `${LOADING_WORD} the analyses for this part…`
                            // Item 179 (05-2, 06-8, 07-11): no negative reason before the
                            // lanes have answered - a part that turns out runnable was
                            // drawn as having no analysis while they were in flight.
                            : briefOf(current) ? narrowNote : "no analysis writes to this part"}
                          busyTool={busyTool}
                          onSpeedBrief={current.key === "speed"
                            ? (depth) => runSection("speed", false, { depth }) : undefined} />
              ) : (<>
              {/* Item 166: the last-resort layout's own chips - severity,
                  cost, where a row came from - before the first of them.
                  AI surface draws its own disclosure, so it is not given two. */}
              {current.key !== "ai-surface" && (
                <Legend ids={["action-free", "action-paid", "sev-critical", "sev-high", "sev-medium",
                              "sev-low", "sev-info", "source-sweep", "source-brief",
                              "state-candidate", "current"]} />
              )}
              {/* THE LAYOUT OF LAST RESORT (brief v25 step BP). Since Crawl &
                  sitemaps, Indexability & canonicals, URLs & parameters and
                  Speed moved to the three-block layout with their narrows in
                  the address, this across-the-site layout serves only parts
                  with no renderer: Accessibility, AI surface, Backlinks and
                  Local & citations. (The brief named the last two; the first
                  two have no renderer either.) It is not a peer of
                  `PartPage`; a part that gains a renderer leaves it. */}
              <p className="muted anat-blurb">
                {current.blurb}
                {/* The join between the two vocabularies on this screen.
                    Everything here is grouped by how you fix it; the score
                    is grouped by dimension, and nothing said which fed
                    which — so a reader who improved Headings could not tell
                    which sub-score should move. */}
                {data.category_dimensions?.[current.key]?.length ? (
                  <span className="anat-dims">
                    {" "}Scores under{" "}
                    {data.category_dimensions[current.key].join(", ")}.
                  </span>
                ) : null}
              </p>

              {Object.keys(rel).length > 0 && (
                <div className="anat-shared">
                  <strong>
                    {Object.entries(rel)
                      .map(([k, v]) => `${byKey[k].label} (${v.shared} of ${v.of_selected} pages)`)
                      .join(" and ")}{" "}
                    affect the same pages.
                  </strong>{" "}
                  That is usually one template rather than separate problems —
                  fixing it should move all of them at once, and the next audit
                  will say whether it did.
                </div>
              )}

              {/* The smallest refresh this section can ask for
                  (`FEATURES.md` F-06's present-capability fallback). Above
                  the facts panel, not in the `cat-run` row below it: the
                  facts panel is the longest thing on this screen, and the
                  F-07 note inside it points at this control by name, so a
                  control it calls "above" has to be above it.

                  Keyed on the section, so a confirmation opened in one
                  cannot be committed in another. It used to be held back
                  until `/api/meta` arrived, because an unmarked spending
                  control is the one state F-10 exists to prevent; WF-59
                  removed the spend rather than the wait, so the control has
                  nothing left to learn from `meta` and renders straight
                  away. */}
              {/* With a page in front of the operator, the engine can be
                  asked for less than a dimension-wide sweep: F-06's unit is
                  `(url, dims)`, and the control narrows to it rather than
                  offering both. One control, one claim — a screen showing a
                  site-wide refresh beside a page-wide one would be asking
                  the operator to choose a scope in a place that exists to
                  state one. Without a page filter there is no page to name,
                  so the coarse offer stands and says so. */}
              {/* UX-39: a page filter narrows this offer only where a page
                  is a unit the dimension can be asked for. Where it is not —
                  Backlinks, whose OFP coverage is read from provider signals
                  and not from any page — the coarse control stands with the
                  page filter set, and says why rather than looking like the
                  filter was ignored. Withdrawing it silently would leave the
                  operator to work out why one section behaves unlike its
                  neighbours; the limit is rendered text, per the provenance
                  invariant, and not a title attribute. */}
              {/* The refresh controls stand in the re-audit drawer beside
                  this card (brief step 5), with the scope and depth they
                  commit to stated around them. */}

              {/* What the site has now, on the part whose subject is
                  reachability (brief v16b). The same position the parts with
                  a renderer give their "now" block: after the actions, above
                  the findings — and here, directly above the finding list a
                  pressed bar narrows, so the control and what it controls are
                  read together. Only Crawl & sitemaps carries a `depth`. */}
              {/* The v18 step AZ "now": the four counts, their venn and the UA
                  matrix, above the depth histogram. Site-level, so it draws in
                  the across-the-site layout beside the depth control it
                  summarises — not on the AO three-block layout, which has no
                  finding list for the depth bar to narrow (item 137, channel
                  20260910-0740, correcting the earlier keep-both-on-AO ruling).
                  Only Crawl carries `crawl_now`. */}
              {current.crawl_now && (
                <Card className="now-card"><CrawlNowBlock now={current.crawl_now} /></Card>
              )}
              <CrawlDepthBlock depth={current.depth}
                               picked={depthPicked(current.depth, depthRaw)}
                               onPick={setDepthInHash} />

              {/* And which URL owns a page, on the part whose subject that
                  is (brief v16g). The same position and for the same
                  reason as the depth block above it: this is the "now"
                  block the parts with a renderer put after the actions and
                  above the findings, and Indexability has no renderer of
                  its own. Only that part carries `chains`.

                  With a page in scope it draws that page's own chain, from
                  its facts, rather than the site's worst few — a reader who
                  has narrowed to one page is asking about that page. */}
              {/* The v18 step BA "now": the four counts and the canonical map,
                  above the canonical chains it summarises. Same reason as the
                  crawl block above — site-level, in the across-the-site layout.
                  Only Indexability carries `indexability_now`. */}
              {current.indexability_now && (
                <Card className="now-card"><IndexabilityNowBlock now={current.indexability_now} /></Card>
              )}
              {/* The v19 step BB "now": the four-count strip, the convention,
                  and the pattern table and parameter inventory. Same
                  across-the-site position as the crawl and indexability blocks
                  — site-level, no renderer of its own. Only the `urls` part
                  carries `urls_now`. */}
              {current.urls_now && (
                <Card className="now-card"><UrlsNowBlock now={current.urls_now} /></Card>
              )}
              {/* The v19 step BC "now": the per-template vitals strip and the
                  five pictures beneath it. Same across-the-site position as
                  the three blocks above, and for the same reason - Speed is a
                  site-level part with no renderer of its own. It carries its
                  own Card, because the block is six visuals rather than one
                  table and it states the device profile at its head. Only the
                  `speed` part carries `speed_now`.

                  `onPart` is the one link between two parts in the product:
                  the brief forbids this page from recounting image weight, so
                  it points at Images. The selection lives here, which is why
                  the block mounts here and not in a `siteNow` slot. */}
              {current.speed_now && (
                <SpeedNowBlock part={current} pops={data.populations ?? null}
                               onPart={setSelected} />
              )}
              <CanonicalChainsBlock chains={current.chains} page={page}
                                    chain={data.facts?.canonical_chain ?? null}
                                    onPage={setPage} onCheck={openCause}
                                    checks={new Set(causesOf(current)
                                      .filter((c) => c.count > 0)
                                      .map((c) => c.key))} />

              {/* What the crawler actually read, before what it concluded.
                  A finding says a heading level was skipped; this says which
                  heading, so the fix does not need the page opened — and,
                  since F-07, the outline opens at the heading the finding
                  means rather than leaving it to be counted out by hand. */}
              {data.facts && (
                <PageFacts facts={data.facts} category={current.key}
                           guides={data.guidelines}
                           fault={headingFault(current.findings)}
                           refresh={current.refresh} />
              )}

              {/* Two sources on one check id is the shape that put two
                  defensible numbers in front of an auditor with no basis to
                  choose: "19 of 42 images on / lack alt text" from the sweep,
                  "five informative images lack alt attributes" from the
                  brief, stacked, both open, both `img-alt-missing`. They are
                  not in conflict — they count different things — but nothing
                  said so. */}
              {actionError && <ErrorNote error={actionError} />}

              {reading && (
                <div className="sec-report">
                  <ReportHead
                    title={reading.tool}
                    rerunning={busyTool === reading.tool}
                    rerunTitle={`Runs ${reading.tool} again against the most `
                                + "recent audit and replaces this report. "
                                + "Spends model tokens."}
                    onRerun={() => runSection(reading.tool, true)}
                    onClose={() => setReading(null)} />
                  {/* What the parser dropped and what the brief could not
                      assess, ahead of the prose (brief v12 step AL). */}
                  <ContractAccount contract={reading.contract} />
                  {reading.report
                    ? <ReportView source={reading.report}
                                  runId={run ?? undefined} />
                    : <p className="muted">This report was not retained.</p>}
                </div>
              )}

              {/* Opened by the pill above, beside where a brief's report
                  opens. The panel states its own cost and owns its own run
                  button — the pill only reveals it. */}
              {panel === "page-advisor" && page && run && (
                <PageAdvice runId={run} url={page}
                            scope={current.key}
                            checkId={panelCheck ?? undefined}
                            onBusy={setPanelBusy} />
              )}
              {panel === "schema-auditor" && page && run && (
                <SchemaAuditPanel runId={run} url={page}
                                  onBusy={setPanelBusy} />
              )}

              {/* The fix loop's two halves, in one line. A tick is a claim;
                  a verification is a measurement. The bar never says
                  "fixed" — only the crawl gets to. */}
              {(() => {
                // Scoped to this category, because the bar sits inside this
                // category's pane. It counted every mark on the site, so
                // "4 marked fixed" appeared above a list holding two — the
                // number was true of somewhere else.
                const mine = current.findings
                  .filter((f) => marked.has(f.fingerprint));
                const here = mine.map((f) => f.fingerprint);
                // `urls` is truncated at ten on the wire; `pages` beside
                // it is the whole of what was stored. Counting the list
                // alone said 10 above a Pages column reading 12, while the
                // server re-crawled all twelve. Deliberately not `f.total`:
                // a verification re-crawls the URLs the row holds, and the
                // ones a check dropped before storing are not among them, so
                // the frame would overstate what this bar is about. The union is exact only while nothing is cut; past
                // that the largest single finding is the floor, and the bar
                // says so rather than inventing a total it cannot know.
                const known = new Set(mine.flatMap((f) => f.urls)).size;
                const pages = Math.max(known, ...mine.map((f) => f.pages), 0);
                const exact = mine.every((f) => f.urls.length >= f.pages);
                return (
                  <MarkBar here={here} pages={pages} pagesExact={exact}
                           pageCap={data.verify_page_cap}
                           elsewhere={marked.size - here.length}
                           outcome={outcome} verifying={verifying}
                           onVerify={() => fix.verify(here)}
                           onClear={() => fix.clear(here)} />
                );
              })()}

              {/* Where a refusal lands. `useFixLoop` stores every 422 and
                  every 502 the verify route returns and its own comment
                  calls the `ErrorNote` beside each call site the way they
                  reach the operator — and this call site had none, so four
                  refusals and one failure arrived here as nothing at all:
                  the button said "looking…", came back, and no sentence
                  appeared.

                  The case is not hypothetical and is only reachable here.
                  `MarkBar` withholds the button where it can already tell
                  the batch is over the cap, so a refusal needs a count the
                  screen reads low — and this payload truncates each
                  finding's URL list at ten, which two findings cannot be
                  deduped across. Two crawl findings naming fifteen pages
                  each read as twenty on this screen and thirty at the
                  route. */}
              {fixError && <ErrorNote error={fixError} />}

              {/* "Two sources, two questions" is inside the re-audit
                  drawer's details since brief v5 step U, not open here. */}
              {!causesOf(current).some((c) => c.count > 0) && !(current.brief_checks?.length) ? (
                // Item 180 (07-3): which of the three states "nothing open" is.
                <MeasureLine {...partMeasure(current, new Map(
                  Object.entries(current.not_assessed ?? {})
                    .map(([full, why]) => [full.split("/").pop() ?? full, why])))} />
              ) : (
                <table className="findings causes">
                  <thead>
                    <tr><FixCol />
                        <th>Severity</th><th>Cause</th>
                        <th className="num">Pages</th>
                        <th className="state-col">State</th></tr>
                  </thead>
                  <tbody>
                    {causesOf(current).filter((c) => c.count > 0).map((cause) => {
                      const open = openCauses.has(cause.key);
                      const instance = (f: Finding) => (
                      <Fragment key={f.fingerprint}>
                          <tr className={marked.has(f.fingerprint) ? "marked" : ""}>
                            {/* Only a crawl may say "fixed". This says "I have
                                fixed it, look again" — which is why ticking is
                                free of consequence and safe to do in bulk. A
                                finding raised by a brief is judged by re-running
                                the brief, so a crawl cannot verify it. */}
                            <td className="fix-col">
                              <FixTick f={f} marked={marked} onMark={fix.mark} />
                            </td>
                            <td><Pill tone={`sev-${f.severity}` as Tone}>{f.severity}</Pill></td>
                            <td>
                              <span className="f-sum">{f.summary}</span>
                              {f.recommendation &&
                                <div className="muted rec">{f.recommendation}</div>}
                              <div className="muted cites">
                                <code>{f.check_id}</code>
                                {/* Which kind of thing said this. Two findings
                                    sharing a check id but not a source are
                                    answering different questions, and without
                                    this they read as one number disagreeing with
                                    itself. */}
                                <Pill tone={f.source === "deterministic"
                                  ? "source-sweep" : "source-brief"}
                                      title={f.source === "deterministic"
                                        ? "Counted mechanically by the automatic checks — exhaustive, no judgement"
                                        : "Judged by an expert analysis — selective, and it can see things a parser cannot"}>
                                  {sourceWord(f.source === "deterministic" ? "sweep" : "brief")}

                                </Pill>
                                {/* FEATURES.md F-02. Offered only where a
                                    specialist actually judges this check — the
                                    server decides, and a null means no control
                                    at all rather than one that would run the
                                    wrong tool and return a fluent judgement
                                    about something else. Needs a page, because
                                    a page specialist has nothing to run against
                                    without one. */}
                                {/* Re-test this finding, from the finding
                                    (brief step 5, WF-02): opens the drawer on
                                    the confirmation, scoped to the part's
                                    dimension, naming the finding and its
                                    pages. The press spends nothing. */}
                                {current.refresh && (
                                  <SecondaryButton
                                          onClick={() => {
                                            setDrawerFinding({ check: f.check_id,
                                                               pages: f.pages,
                                                               fingerprint: f.fingerprint,
                                                               namesPage: f.names_a_page });
                                            setRefreshFor(current.key);
                                            setRefreshAsk((n) => n + 1);
                                          }}>
                                    re-audit
                                  </SecondaryButton>
                                )}
                                {f.specialist && page && (
                                  <SecondaryButton
                                          title={`Run ${f.specialist} against this `
                                                 + `finding on ${page}`}
                                          onClick={() => {
                                            setPanelCheck(f.check_id);
                                            setPanel(f.specialist!);
                                          }}>
                                    ask {f.specialist}
                                  </SecondaryButton>
                                )}
                              </div>
                            </td>
                            {/* FEATURES.md F-11. The count is the control: a
                                number that summarises a list the operator cannot
                                reach is a claim they have to take on trust. */}
                            <td className="num">
                              <PagesCount f={f} open={openPages.has(f.fingerprint)}
                                          onToggle={() => togglePages(f.fingerprint)} />
                            </td>
                            <td className="state-col">
                              <FixState f={f} marked={marked} outcome={outcome}
                                            judged={judged} />
                            </td>
                          </tr>
                          {openPages.has(f.fingerprint) && !!f.urls.length && (
                            <tr className="pages-row">
                              {/* Five columns above: tick, severity, finding,
                                  pages, state. Spanned rather than placed in the
                                  `num` cell, which is a right-aligned column
                                  sized for two digits. */}
                              <td colSpan={5}><PagesList f={f} /></td>
                            </tr>
                          )}
                          </Fragment>
    
                      );
                      return (
                      <Fragment key={cause.key}>
                      {/* The row's own check id as an attribute (brief
                          v16g): the canonical chain cards above narrow the
                          record by scrolling to this row and opening it,
                          and a class would not carry which check it is. */}
                      <tr className="cause-row" data-cause={cause.key}>
                        <td className="fix-col">
                          <SecondaryButton className="group-toggle"
                                  aria-expanded={open}
                                  aria-label={`${open ? "collapse" : "expand"} ${cause.check}`}
                                  onClick={() => setOpenCauses((prev) => {
                                    const next = new Set(prev);
                                    if (!next.delete(cause.key)) next.add(cause.key);
                                    return next;
                                  })}>
                            {open ? "−" : "+"}
                          </SecondaryButton>
                        </td>
                        <td><Pill tone={`sev-${cause.severity}` as Tone}>{cause.severity}</Pill></td>
                        <td>
                          <code>{cause.dimension}/{cause.check}</code>{" "}
                          {/* Both sources on the one row (brief v10 step
                              AF): the sweep's count and the brief's, each
                              tagged, and the sentence that used to be a
                              panel is the tag's tooltip. */}
                          {(["sweep", "brief"] as const).filter((w) => cause.sources[w]).map((w) => (
                            <Pill key={w} tone={`source-${w}`}
                                  title={Object.keys(cause.sources).length > 1 ? SOURCES_NOTE : undefined}>
                              {sourceWord(w)} {cause.sources[w]}
                            </Pill>
                          ))}
                          {cause.candidates > 0 && (
                            <Pill tone="state-candidate" title={CANDIDATE_NOTE}>
                              candidate {cause.candidates}
                            </Pill>
                          )}
                          {cause.count === 0 && (
                            <span className="muted cause-clean">0 — nothing open on this check</span>
                          )}
                          <div className="muted cause-sum">{cause.summary}</div>
                          {/* Templates: the longest path prefix ten or more of
                              the cause's pages share, else no shared template.
                              A template is what one fix moves at once. */}
                          {cause.templates.length > 0 && (
                            <div className="muted cause-templates">
                              {cause.templates.map((t) => (
                                <span key={t.prefix} className="cause-template">
                                  {t.prefix === "" ? "No shared template" : `Template ${t.prefix}*`}
                                  {" — "}{t.pages} page{t.pages === 1 ? "" : "s"}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        {/* Prevalence, over the only denominator the rule
                            permits (item 155): affected of ASSESSED. The
                            cell used to read the record's page count with
                            nothing saying so, and on a partial crawl that
                            invited a fault rate over pages nobody looked
                            at. */}
                        <td className="num cause-prev">
                          <Prevalence pops={data.populations ?? null}
                                      prev={{ count: cause.prev,
                                              unfetched: cause.unfetched }} />
                        </td>
                        <td className="state-col muted">
                          {/* `worst N here` only where the payload holds some
                              of them: a candidate-only cause (brief v12 step
                              AM) has its count and nothing beneath. */}
                          {cause.shown > 0 && cause.shown < cause.count
                            ? `${cause.count} finding${cause.count === 1 ? "" : "s"} · worst ${cause.shown} here`
                            : `${cause.count} finding${cause.count === 1 ? "" : "s"}`}
                        </td>
                      </tr>
                      {/* Brief v3 step M (UX-15): a cause with two or more
                          templates opens to them, one row each, with the
                          verbs that move what is under the template; its
                          instances open beneath the template. One template
                          is the cause itself, and opens to its instances. */}
                      {open && cause.templates.length < 2 && cause.rows.map(instance)}
                      {open && cause.templates.length >= 2 && cause.templates.map((t) => {
                        const tkey = `${cause.key}|${t.prefix}`;
                        const topen = openTemplates.has(tkey);
                        const members = new Set(t.fps);
                        const elsewhere = new Set(cause.templates.filter((o) => o !== t)
                                                                 .flatMap((o) => o.fps));
                        const under = cause.rows.filter((f) => members.has(f.fingerprint)
                          || (t.prefix === "" && !elsewhere.has(f.fingerprint)));
                        const name = t.prefix === "" ? "No shared template" : `Template ${t.prefix}*`;
                        return (
                          <Fragment key={tkey}>
                            <tr className="cause-template-row">
                              <td className="fix-col">
                                <SecondaryButton className="group-toggle"
                                        aria-expanded={topen}
                                        aria-label={`${topen ? "collapse" : "expand"} ${name} under ${cause.check}`}
                                        onClick={() => setOpenTemplates((prev) => {
                                          const next = new Set(prev);
                                          if (!next.delete(tkey)) next.add(tkey);
                                          return next;
                                        })}>
                                  {topen ? "−" : "+"}
                                </SecondaryButton>
                              </td>
                              <td />
                              <td>
                                <span className="tmpl-name">{name}</span>
                                <div className="muted tmpl-n">
                                  {t.fps.length} finding{t.fps.length === 1 ? "" : "s"}
                                  {" on "}{t.pages} page{t.pages === 1 ? "" : "s"}
                                </div>
                              </td>
                              <td className="num">{t.pages}</td>
                              <td className="state-col">
                                {/* The verbs behind the row's overflow, as the
                                    record's are (UI-04). "Re-audit these N" is
                                    the Record's verify path narrowed to the
                                    template's findings - there is no route that
                                    takes a page list, so it is the findings'
                                    pages the crawl looks at again, and the
                                    route's page cap answers through the note
                                    beside the fix loop. */}
                                {(t.accept.length > 0 || t.verify.length > 0) && (
                                  <details className="row-more">
                                    <summary aria-label={`actions for ${name} under ${cause.check}`}>⋯</summary>
                                    {t.accept.length > 0 && (
                                      <SecondaryButton
                                              disabled={templateBusy !== null}
                                              onClick={() => setTemplateAsk({ key: cause.key,
                                                                              prefix: t.prefix,
                                                                              fps: t.accept })}>
                                        accept ×{t.accept.length}
                                      </SecondaryButton>
                                    )}
                                    {t.verify.length > 0 && (
                                      // Item 178: a verification re-fetches pages and
                                      // spends no model tokens (`verify_findings`), so it
                                      // is drawn as the free action it is.
                                      <SecondaryButton
                                              disabled={fix.verifying}
                                              aria-busy={fix.verifying}
                                              onClick={() => fix.verify(t.verify)}>
                                        re-audit these {t.verify.length}
                                      </SecondaryButton>
                                    )}
                                  </details>
                                )}
                              </td>
                            </tr>
                            {templateAsk?.key === cause.key && templateAsk.prefix === t.prefix && (
                              <tr className="cause-confirm">
                                <td colSpan={5}>
                                  <strong>accept risk on {templateAsk.fps.length} finding
                                  {templateAsk.fps.length === 1 ? "" : "s"} under {name}?</strong>{" "}
                                  One request per finding, in order; a finding that also
                                  stands on another template moves with it.{" "}
                                  {/* UX-66's shape: a stable caption, the state on
                                      `aria-busy`, the busy words in the region beside. */}
                                  <SecondaryButton
                                          disabled={templateBusy !== null}
                                          aria-busy={templateBusy === tkey}
                                          onClick={() => acceptTemplate(templateAsk)}>
                                    yes, accept risk
                                  </SecondaryButton>{" "}
                                  <SecondaryButton
                                          disabled={templateBusy !== null}
                                          onClick={() => setTemplateAsk(null)}>
                                    no
                                  </SecondaryButton>
                                  {templateBusy === tkey && (
                                    <span className="muted" role="status" aria-live="polite">
                                      {" "}<Working>moving…</Working>
                                    </span>
                                  )}
                                </td>
                              </tr>
                            )}
                            {topen && under.map(instance)}
                          </Fragment>
                        );
                      })}
                      </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              )}
              {templateErr && <ErrorNote error={templateErr} />}
              {/* The part's checks with nothing open, on one line rather
                  than a row each (brief v12 step AN): what was measured and
                  passed is worth one sentence, not a screen of `0`. */}
              {(() => {
                /* Item 157. A check with no finding is only a PASS if this
                   run measured it; `not_assessed` names the ones it did not,
                   with the reason. Before this, Acme's Speed part read
                   "18 checks pass" on a run whose recorded dimensions did
                   not include PRF - `cwv-not-assessed`, the finding whose
                   whole job is to say a measurement did not happen, among
                   the eighteen. Links claimed 12 with LNK absent from the
                   run, and Crawl certified its LNK half.

                   Matched on the bare id because `causesOf` carries bare
                   check names while the payload keys by `DIM/check`. */
                const why = new Map(
                  Object.entries(current.not_assessed ?? {})
                    .map(([full, reason]) =>
                      [full.split("/").pop() ?? full, reason] as const));
                const zero = causesOf(current).filter((c) => c.count === 0);
                const clean = zero.filter((c) => !why.has(c.check));
                const dark = zero.filter((c) => why.has(c.check));
                /* Grouped by reason, so the line reads as one sentence per
                   cause rather than one per check. */
                const byReason = new Map<string, string[]>();
                for (const c of dark) {
                  const r = why.get(c.check)!;
                  byReason.set(r, [...(byReason.get(r) ?? []), c.check]);
                }
                if (!clean.length && !byReason.size) return null;
                return (
                  <>
                    {clean.length > 0 && (
                      <p className="cause-clean-line">
                        {clean.length} check{clean.length === 1 ? "" : "s"}
                        {page ? " pass on this page: " : " pass: "}
                        {clean.map((c) => c.check).join(" · ")}
                      </p>
                    )}
                    {[...byReason].map(([reason, checks]) => (
                      <p className="cause-dark-line" key={reason}>
                        {checks.length} check
                        {checks.length === 1 ? "" : "s"} not assessed —{" "}
                        {reason}: {checks.join(" · ")}
                      </p>
                    ))}
                  </>
                );
              })()}
              <ReplacementTable states={scoped}
                                belongs={(current.brief_checks?.length || current.filed_checks?.length
                                          || current.check_prefixes?.length) ? belongsTo(current) : null}
                                findings={current.findings}
                                dropped={current.brief_dropped ?? 0}
                                notAssessable={current.brief_not_assessable ?? 0} />
              {/* Briefs for this part, under the causes they would explain
                  (brief v2 step E). */}
              <h4 className="cause-briefs">
                Analyses for this part
                {/* Run the N not run (brief v4 Item 3f): opens the
                    drawer's confirm panel scoped to this part; the press
                    here spends nothing, the panel's commit carries the
                    mark (F-10). Page-scoped briefs are not in the count. */}
                {onRunAll && (() => {
                  const mine = (lanes?.available ?? []).filter(
                    (x) => current.tools.includes(x.tool) && x.type !== "page"
                           && x.state === "not_run");
                  if (!mine.length) return null;
                  const priced = mine.map((x) => x.est_cost_default)
                    .filter((c): c is number => c != null);
                  const est = priced.length
                    ? `${money(priced.reduce((s, c) => s + c, 0))}`
                      + (priced.length < mine.length ? ` + ${mine.length - priced.length} unpriced` : "")
                    : "unpriced";
                  return (
                    // Item 178 (07-10): the control that spends the most was drawn
                    // as a text link. It opens the batch confirmation rather than
                    // spending, and it is drawn as what it leads to: a spend.
                    <Pill tone="action-paid" as="button" type="button" className="run-part"
                            aria-disabled={Boolean(narrowNote) || undefined}
                            onClick={() => { if (!narrowNote) onRunAll(current.key); }}>
                      Run the {mine.length} not run · {est}
                    </Pill>
                  );
                })()}
              </h4>
              {/* Whether anyone has read this category, and what to do about
                  it. The count above says how much is wrong; this says
                  whether a specialist has looked. */}
              <div className="cat-run">
                {/* The Speed part's depth pills (brief v19 step BC, unheld
                    2026-09-11). A SLOT ONLY SPEED FILLS rather than a change
                    to this row's default: `.cat-run` is shared by every
                    across-the-site part, and BC's visuals and BJ's header
                    were written against it, so every other part's row is
                    unchanged. "Everywhere else the pills stay gone" is
                    enforced by nobody else mounting this. */}
                {current.key === "speed" && (
                  <SpeedActions
                    now={current.speed_now ?? null}
                    cost={(lanes?.available ?? []).concat(lanes?.ready ?? [])
                      .find((x) => x.tool === "speed")?.est_cost_default ?? null}
                    busy={busyTool}
                    note={narrowNote}
                    onRecheck={() => { setRefreshFor(current.key);
                                       setRefreshAsk((n) => n + 1); }}
                    onBrief={(depth) => runSection("speed", false, { depth })} />
                )}
                {liveHere(current) ? (
                  <span className="muted">
                    {(current.analysing?.length ? current.analysing.join(", ")
                      : busyTool && current.tools.includes(busyTool) ? busyTool
                      : panel)} is analysing this now…
                  </span>
                ) : current.analysed?.length ? (
                  <>
                    <span className="muted">Analysed —</span>
                    {/* Readable here, not merely stated. "Analysed by
                        onpage-hygiene" with no way to open it sent the
                        operator to another tab to read a report about the
                        list they were already looking at. */}
                    <ReadAnalysis items={current.analysed}
                                  reading={reading?.tool ?? null} onRead={readSection} />
                  </>
                ) : (
                  <span className="muted">
                    <strong>Nothing has analysed this.</strong> The automatic checks counted the problems; no specialist has read them.
                  </span>
                )}
                {/* Only what can actually start — a sweep runs inside every
                    audit and has no endpoint of its own. */}
                {/* UX-66. Stable caption, state on `aria-busy`; the words are
                    said once below rather than once per specialist, since
                    these are several identically-shaped controls and only one
                    can be running. */}
                {narrowNote && current.can_run?.length ? (
                  <p className="muted narrow-pick-note" role="note">{narrowNote}</p>
                ) : null}
                {current.can_run?.map((t) => {
                  // Item 178: priced from the lanes, held with the reason in text
                  // until they and the audit are read, confirmed before it runs.
                  const an = [...(lanes?.ready ?? []), ...(lanes?.available ?? [])]
                    .find((x) => x.tool === t);
                  return (
                    <SpendButton key={t}
                                 price={!lanes ? undefined : an ? an.est_cost ?? an.est_cost_default ?? null : null}
                                 busy={busyTool === t}
                                 why={!run ? "no completed audit for it to read"
                                   : narrowNote ? "this audit is too narrow for it"
                                   : busyTool !== null ? `${busyTool} is running` : null}
                                 confirm={{ title: `Run ${an?.name ?? t} on this part?`,
                                            body: <><SpendTarget pages={data.pages.length}
                                                                 runId={current.sweep_run?.run_id ?? run ?? undefined} />
                                              <p>It reads {current.sweep_run
                                                ? `the ${current.sweep_run.tier} crawl of ${stamp(current.sweep_run.at)}`
                                                : "the newest crawl"} for {current.label} and
                                                writes what it judges worth fixing.</p></>,
                                            action: `Run ${an?.name ?? t}` }}
                                 onSpend={() => runSection(t)}>
                      run {t}
                    </SpendButton>
                  );
                })}
                <span className="muted" role="status" aria-live="polite">
                  {busyTool && <Working key={busyTool}>{`Running ${busyTool}…`}</Working>}
                </span>
                {/* Whatever the category's tool list still holds once those
                    two have taken theirs. It used to sit under the findings
                    table as an "Investigate" row of links to the tools
                    screen — the same question as this row, asked twice, with
                    the section's own brief appearing in both. Most entries
                    have gone: they were already a read or a run pill here. */}
                {current.investigate?.map((it) => it.action !== "page" ? (
                  /* Said, not offered — and each says the true thing. A
                     first cut called all three a sweep, which put
                     "link-gap runs in every audit" on screen for a tool
                     that is not built. Removing them would read as nothing
                     covering the section at all; a button would be a lie. */
                  <span key={it.tool}
                        className={`tri-sweep${it.action === "planned"
                                               ? " tri-planned" : ""}`}
                        title={it.action === "planned"
                          ? "In the catalogue, not built yet — nothing to run"
                          : it.action === "needs_key"
                            ? "Built, but its provider key is not configured, "
                              + "so its checks are dark"
                            : "Measured by the audit itself — there is nothing "
                              + "separate to start"}>
                    {it.tool}{" "}
                    {it.action === "planned" ? "not built yet"
                      : it.action === "needs_key" ? "needs a key"
                      : "runs in every audit"}
                  </span>
                ) : (
                  /* One page at a time, so it needs the page filter set.
                     Purple because the pill only opens the panel; the
                     spending is the panel's own button, where the cost is
                     stated. */
                  // Item 178: this only opens the panel, whose own control spends and
                  // states the price, so it is navigation whether or not a page is set.
                  <SecondaryButton key={it.tool}
                          disabled={!page || !run}
                          title={!run
                            ? "No completed audit for it to read"
                            : page
                              ? `Analyse ${pathOf(page)} with ${it.tool}`
                              : "Pick a page above — this one looks at a "
                                + "single page, not the site"}
                          onClick={() => { setPanelCheck(null); setPanel(
                            panel === it.tool ? null : it.tool); }}>
                    {panel === it.tool ? "hide" : "open"} {it.tool}
                  </SecondaryButton>
                ))}
              </div>

              {/* A count drawn bare, and item 156's type change is what
                  found it: `{current.total}` in running text, with the
                  population it was counted over left for the reader to
                  assume. It is the record's - open state is site-scoped - and
                  it says so now. */}
              {current.findings.length < current.total.value && (
                <p className="muted anat-note">
                  Each cause counts every open finding; opening one shows the
                  worst {current.findings.length} of this part&rsquo;s{" "}
                  <Counted count={current.total} pops={data.populations ?? null} />,
                  the rest being on the Record.
                </p>
              )}
              </>)}
            </Card>
          )}
        </section>

        {/* The re-audit drawer (brief step 5, WF-02): the third column
            whenever a part with a sweep behind it is open. It wraps the
            same two commit paths the section card used to hold - the
            whole-site sweep and, once a page is narrowed to, that page -
            and states the sweep, the pages and the depth around them. */}
        {current?.refresh && !threeBlocks && (
          <ReauditDrawer label={current.label} refresh={current.refresh}
                         page={page} precheck={precheck} finding={drawerFinding}
                         depth={depth} onDepth={setDepth}
                         onClearPage={() => setPage("")}
                         onVerify={(fp) => fix.verify([fp])}
                         verifying={verifying}
                         verdict={drawerFinding ? outcome[drawerFinding.fingerprint] : null}
                         verifyError={fixError}
                         pageCap={data.verify_page_cap}
                         onPrimary={() => { setRefreshFor(current.key);
                                            setRefreshAsk((n) => n + 1); }}>
            {page && current.refresh.per_page ? (
              <PageRefresh key={`page-${current.key}`} siteId={siteId}
                           label={current.label} sectionKey={current.key}
                           refresh={current.refresh} page={page}
                           startConfirming={refreshFor === current.key}
                           ask={refreshAsk}
                           onDone={() => setTick((t) => t + 1)} />
            ) : (
              <SectionRefresh key={current.key} siteId={siteId}
                              label={current.label}
                              refresh={current.refresh}
                              startConfirming={refreshFor === current.key}
                              ask={refreshAsk}
                              tier={depth ? DEPTH_TIER[depth] : null}
                              />
            )}
          </ReauditDrawer>
        )}
      </div>
    </>
  );
}
