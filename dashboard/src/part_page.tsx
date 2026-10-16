/** The part page in three blocks — actions, what the page has now, fixes
 *  (brief v13 step AO).
 *
 *  The page it replaces told the operator a brief had run by colouring a
 *  dot; offered three depth choices for a sweep that is free at every
 *  depth; opened on three paragraphs of explanation; listed a row per
 *  check with nothing open; and put the briefs that write to the part at
 *  the bottom. A client could not relate any of it to their own page.
 *
 *  Read top to bottom it is now: what you can do and what produced what
 *  you are reading; what this page has on it right now; and the fixes,
 *  one card per problem with the current string struck through above the
 *  replacement.
 *
 *  **Rendered, never called.** Both renderers are used as elements -
 *  `<render.now ... />` - and not as `render.now({...})`. The renderers do
 *  not hold the same number of hooks, so a plain call puts a varying hook
 *  count inside `PartPage` and React tears the tree down the moment the
 *  operator switches part. Guarded at
 *  `tests/test_the_part_page_is_three_blocks.py`.
 *
 *  **A renderer per block.** `PART_RENDERERS` keys the "now" block and the
 *  fix-card body by part, so Headings can supply an outline where Title &
 *  description supplies strings (brief v14) without forking the layout.
 *  A part with no renderer keeps the old page.
 */
import { Envelope, Report } from "./expert";
import { Markdown } from "./markdown";
import { Working } from "./working";
import { stamp } from "./client_lanes";
import { MeasuredAge, dayOf } from "./age";
import { SecondaryButton } from "./buttons";
import { sourceWord } from "./glossary";
import { Legend, entry } from "./glossary";
import { Fragment, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Category, ContentBlock, EntityMatrix, Facts, ImageRecord, LinkIn, LinkOut, SchemaBlock,
         templatesOf } from "./anatomy";
import { BytesForPixels, ImageDot, ImageWall, PickedImage, fileOf, fileSrc, imageKey,
         dotKey } from "./images_budget";
import { OutlineLadder, SkipsByTemplate } from "./headings_outline";
import { BarrierOverlay, FixOrderWaterfall, kindShort, ShotBoxes } from "./a11y_fixorder";
import { HeadersGridBlock } from "./headers_grid";
import { LengthStrips, SnippetCard, SnippetField, fired } from "./title_snippet";
import { costOf } from "./cost";
import { Analysis, Lanes } from "./analyses";
import { FindingState, api, isCoverageNote } from "./api";
import { Card, ErrorNote, money } from "./components";
import { SpendButton, SpendTarget } from "./spend";
import { estimate, humanEst, usePace, type Estimate } from "./scanmatrix";
import { SchemaGraphView } from "./schema_graph";
import { goHandler, goto, withPart } from "./nav";
import { Narrow, NarrowKind, narrowFromHash, pagePredicate, setNarrowInHash } from "./narrow";
import { CrawlDepthBlock, depthPicked } from "./crawl_depth";
import { CrawlNowBlock } from "./crawl_now";
import { AiLlmsFile, AiReachability, AiReachabilityPage, AiRegister, AiSurfaceFixBody, aiSurfaceCopy } from "./ai_surface";
import { IndexabilityNowBlock } from "./indexability_now";
import { UrlsNowBlock } from "./urls_now";
import { SpeedActions, SpeedNowBlock } from "./speed_now";
import { CanonicalChainsBlock } from "./canonical_chains";
import { TargetLocales } from "./intl_target";
import { Pill, type Tone } from "./pill";
import { MEASURE_WORD, MeasureLine, measureOf } from "./measure";
import { Counted, Populations, Prevalence, coverageNotes, makeCount, pathKey,
         prevalence } from "./population";
import { clock, day } from "./dates";
import { CONFIRM_SAYS, ConfirmControls, TO_CONFIRM_LEGEND, candidateWord } from "./to_confirm";
import { FixTick, type Markable, useFixLoop, useSeed } from "./fixloop";

/** What a check means in the words a client uses. The check id stays on
 *  the card in code — this is the sentence above it, not a replacement
 *  for it. */
const PLAIN: Record<string, string> = {
  "title-missing": "No title",
  "title-length": "Title length outside the window",
  "title-duplicate": "Title shared with other pages",
  "title-entity-alignment": "Title may not state the triple",
  "meta-desc-missing": "No description",
  "meta-desc-length": "Description length outside the window",
  "meta-desc-duplicate": "Description shared with other pages",
  // Headings (brief v14 step AP), fixed by the brief.
  "h1-missing": "No h1",
  "h1-multiple": "More than one h1",
  "h1-triple-restated": "H1 may not restate the triple",
  "h1-title-verbatim": "H1 copies the title",
  "h1-brand-repeated": "Brand in the h1",
  "h1-hook": "H1 has no angle",
  "h2-support": "H2 off the page's subject",
  "h2-location-service": "No h2 for the services here",
  "h2-overstuffed": "Redundant h2s",
  "h2-question-unanswered": "Question heading with no answer",
  "h3-sub-service": "Sub-services not broken out",
  "h3-geo-map": "Locations not mapped",
  "heading-skip": "Level skipped",
  // Images (brief v15 step AR), fixed by the brief.
  "img-alt-missing": "No alt text",
  "img-alt-decorative-nonempty": "Decorative image with alt text",
  "img-link-alt-not-destination": "Linked image alt doesn't say where it goes",
  "img-filename-generic": "Filename says nothing",
  "img-alt-filename": "Alt repeats the filename",
  "img-lcp-lazy": "Main image loads late",
  "img-dimensions-missing": "No width and height",
  "img-oversized": "Larger than shown",
  "img-no-srcset": "One size for every screen",
  "img-sizes-wrong": "sizes doesn't match the layout",
  "img-legacy-format": "Old format",
  "img-weight-budget": "Over the weight budget",
  "img-text-in-image": "Text only in pixels",
  "img-duplicate-links": "Several links to one place",

  "img-sitemap-missing": "Not in the image sitemap",
  // The Structured data brief's own set (brief v16 step AT). Fixed words,
  // because a check id is the engine's name for a thing and this is the
  // operator's - and an operator who has to translate one into the other
  // is reading a register rather than a page.
  "schema-invalid-json": "Markup doesn't parse",
  "schema-missing-for-type": "No markup for this kind of page",
  "schema-required-missing": "Required property missing",
  "schema-deprecated-rich-result": "Markup for a result Google no longer shows",
  "schema-subtype-shallow": "Type could be more specific",
  "schema-id-inconsistent": "Entity has more than one @id",
  "schema-orphan-instance": "Block doesn't point at the entity",
  "schema-island": "Block connected to nothing else on the page",
  "schema-redundant-block": "Duplicate block",
  "schema-nap-mismatch": "Name, address or phone differs",
  "schema-sameas-missing": "Profiles not linked",
  "schema-sameas-misplaced": "Listing in the wrong place",
  "schema-hidden-markup": "Markup says what the page doesn't",
  "schema-entity-model": "Wrong shape for this business",
  "schema-graph-wiring": "Blocks don't point at each other",
  "schema-entity-thin": "Entity could say more",
  "schema-catalog-mismatch": "Service list doesn't match the site",
  "schema-review-unsupported": "Rating with no visible reviews",
  "schema-author-missing": "Article without an author",
  "schema-datemodified-missing": "Article without a modified date",
  "schema-breadcrumb-missing": "No breadcrumbs",
  "schema-id-page": "Entity page missing or disagrees",
  "schema-triple-mismatch": "Type or address may not state the business",
  // The one header image that is not decorative (brief v16 step AU6),
  // and one image too heavy for what it shows (step AU7).
  "img-logo": "The logo", "img-heavy": "Heavier than it needs to be",
  // Security & transport (item 143 step BD): the ids are abbreviations a
  // client does not read.
  "hsts": "Strict-Transport-Security (HSTS)", "http-redirect": "HTTP to HTTPS redirect",
  "tls-legacy": "Old TLS versions accepted", "cert-chain": "Certificate expiry or chain",
  "cert-san": "Certificate does not cover every host name", "mixed-content": "Insecure content on a secure page",
  "csp-absent": "No Content-Security-Policy", "csp-weak": "Content-Security-Policy is weak",
  "xcto": "X-Content-Type-Options", "referrer-policy": "Referrer-Policy",
  "permissions-policy": "Permissions-Policy", "frame-ancestors": "Framing protection",
  "cookie-flags": "Cookie flags", "cache-authenticated": "Cacheable response that sets a cookie",
  "deprecated-header": "Deprecated security headers still sent", "version-banner": "Software version disclosed",
  "cms-fingerprint": "Platform fingerprintable", "exposed-file": "File that should not be public",
  "directory-listing": "Directory listing", "error-leak": "Error page says too much",
  "html-comment-leak": "Leaky HTML comment", "cms-xmlrpc": "xmlrpc.php reachable",
  "cms-user-enumeration": "User names can be listed", "cms-login-exposed": "Login page exposed",
  "cms-registration-open": "Open registration", "spf": "SPF (mail sender policy)",
  "dmarc": "DMARC (mail authentication policy)", "dkim": "DKIM (mail signing)",
  "caa": "CAA (who may issue certificates)", "dnssec": "DNSSEC",
  "dangling-cname": "CNAME pointing at nothing", "sri-missing": "Third-party code without integrity",
  "cross-origin-form": "Form posts to another site", "security-txt": "security.txt",
  "csp-policy": "The CSP this site can run", "hsts-rollout": "HSTS rollout",
  "header-deploy-risk": "Header deploy risk", "compromise-triage": "Compromise triage",
};

/** Words an id spells that a reader spells differently (item 183, UI audit
 *  04-10, 06-9): "Llms txt missing", "Unused css js", "Ttfb slow" and "Eeat"
 *  were ids said as words. Industry terms keep their industry spelling. */
const ID_WORDS: [RegExp, string][] = [
  [/\bllms txt\b/g, "llms.txt"], [/\brobots txt\b/g, "robots.txt"], [/\bsecurity txt\b/g, "security.txt"],
  [/\bcss js\b/g, "CSS/JS"], [/\beeat\b/g, "E-E-A-T"], [/\bcwv\b/g, "Core Web Vitals"],
  // Item 267 (row 19): and `ua` and `id` ("ai crawler ua", "id page absent").
  [/\b(lcp|cls|inp|ttfb|tbt|css|js|html|url|urls|nap|gbp|ssl|tls|dns|cdn|ai|og|jsonld|h1|h2|ua|id)\b/g, "\u0000$1"],
];

export const plainName = (checkId: string) => {
  if (PLAIN[checkId]) return PLAIN[checkId];
  let words = checkId.replace(/^[A-Z0-9]+\//, "").replace(/^EXP:[^/]*\//, "").replace(/-/g, " ");
  for (const [pat, rep] of ID_WORDS) words = words.replace(pat, rep);
  words = words.replace(/\u0000(\w+)/g, (_, w: string) => (w === "jsonld" ? "JSON-LD" : w.toUpperCase()));
  // A file name keeps its case: "llms.txt missing", not "Llms.txt missing".
  if (/^\S*\.\S/.test(words)) return words;
  return words.replace(/^[a-z]/, (c) => c.toUpperCase());
};

/** Where a held check's missing input is set. A `needs` naming a field of
 *  the site record links to the form that holds it; one naming the page's
 *  own content has nowhere to send anybody, and says so instead. */
// Item 267 (row 14): and the record's own field names, which a held reason
// quotes as written ("sub_services, locations and authors on the site
// record are empty"), so the card links to the form for four more fields.
// Items 270 (row 11) and 271 (row 12): and the schema fields the record
// supplies (geo, priceRange, openingHours, areaServed, the ID page) and a
// page's triple, so each such hold links to the form too.
const RECORD_WORDS = /gbp|categor|service area|location entit|neighbourhood|sub-service|sub_services|\blocations\b|\bauthors\b|sameas|page type|brand|strateg|provenance|\bgeo\b|pricerange|openinghours|areaserved|id page|\btriple\b|primary entity|intended[_ -]noindex|noindex list|migration[_ ]map|parameter[_ ]rules/i;

/** A held reason as the table and the card say it (item 267, row 14): a
 *  reason that is already a sentence ("no /llms.txt existed at sweep
 *  time") reads as given; a noun phrase ("a reputation source") reads as
 *  what is needed. "needs no /llms.txt existed" was neither. */
export function heldSays(needs: string): string {
  return /\b(is|are|was|were|has|have|had|existed|ran|returned|raised|did|does)\b/i.test(needs)
    ? needs : `needs ${needs}`;
}

export function heldLink(needs: string): { href: string; label: string } | null {
  if (!RECORD_WORDS.test(needs)) return null;
  return { href: "#/admin?tab=sites", label: "set it on Admin › Sites" };
}

const pathOf = (u: string) => { try { return new URL(u).pathname || "/"; } catch { return u; } };

/** The two sections every part page is read in (brief v17 step AV3),
 *  free first. The order is the argument: what the audit found for
 *  nothing, and then what a model was asked to read on top of it. */
export const SECTIONS: [string, string][] = [["free", "Free checks"],
                                             ["model", "Analysis"]];

/** Item 266 (row 3): the sections in the order Fixes reads them - the one
 *  holding the most severe fix first, so the worst thing on the page is the
 *  first thing read. On URLs every free card was `low` and the one `medium`
 *  sat under Analysis, below all of them. On a tie the usual order stands,
 *  free first, so the order moves only when there is a reason, and the
 *  section that moved says it (answer 20261004-0011-266-fix-order-across-
 *  sections). Holds, coverage notes and verdicts are not fixes and do not
 *  rank a section. */
export function sectionsByWorst<F extends { severity: string; needs?: string | null;
                                            coverageNote?: boolean; override?: boolean;
                                            sources: string[] }>(
  fixes: F[], sectionOf: (f: F) => string,
): [string, string][] {
  const worst = (section: string) => Math.min(RANK.length, ...fixes
    .filter((f) => !f.needs && !f.coverageNote && !closedByAnalysis(f)
                   && sectionOf(f) === section)
    .map((f) => RANK.indexOf(f.severity)).filter((n) => n >= 0));
  return [...SECTIONS].sort(([a], [b]) => worst(a) - worst(b));
}

/** Whether the cost filter has folded a section away (brief v17 step
 *  AV4). Never its heading and never its count: the fold is an offer to
 *  spend, and an offer nobody can see is a section that was deleted. */
export const folded = (cost: string, section: string) =>
  Boolean(cost) && cost !== section;

/** One problem on one page: what the record holds, and where it came
 *  from. A held check is the same card with nothing to copy. */
type Fix = {
  key: string; check: string; checkId: string; page: string;
  severity: string; sources: string[]; candidate: boolean;
  /** Item 250: the candidate waits for the operator (the server's rule). */
  toConfirm?: boolean;
  current: string; replacement: string | null; note: string;
  /** What a length row measured on the page, and how far past the cut
   *  (item 273, rows 4 and 5). */
  said?: string | null; overPx?: number | null;
  needs?: string;
  /** The analysis read this before the automatic checks cleared it on
   *  every page it names: when (item 239 step 4). */
  supersededOn?: string | null;
  /** Item 271: the targets the automatic checks raised for this check that
   *  this analysis card names - the same fault, filed on the other end. */
  corroboratedBy?: string[];
  /** Item 269: the analysis's row is a PASS-OVERRIDE - a verdict that the
   *  flag is not a fault ("No consolidation"), not a fault of its own. */
  override?: boolean;
  /** Item 251: when the automatic checks measured this, at which tier, and
   *  when the analysis that wrote it ran. */
  measuredAt?: string | null; measuredTier?: string | null; analysedAt?: string | null;
  /** Item 249: the automatic checks can raise this check, have read the
   *  page since the analysis, and have not raised it. */
  unseenSince?: string | null;
  /** How many pages this one row covers. A template image's finding is
   *  folded by the engine into one row over every page it appears on
   *  (brief v16 step AU4), and this is that number - the record's own,
   *  never a second count of it. */
  pages?: number;
  /** Every page the row's findings name (item 206), merged across the sweep's
   *  row and the brief's. `page` is the card's anchor - the first - and the
   *  checks table counted that alone, so a site-wide fault the engine files
   *  as ONE finding over 31 pages read "1 of 45 pages crawled". */
  urls?: string[];
  /** The automatic row behind the card, for the fix loop (item 279, row 6):
   *  its fingerprint, whether a re-check can read it (the server's
   *  `names_a_page`), and when a fix was marked. */
  sweepFp?: string | null;
  namesAPage?: boolean;
  /** The analyses whose rows are on this card (item 275, row 5): Crawl's
   *  part draws `LNK/depth-deep` rows the Links analysis wrote, and its
   *  accounting counted them as its own. */
  briefs?: string[];
  attemptedAt?: string | null;
  /** The automatic check's own advice, and the elements it names - axe's
   *  selectors or the links' hrefs - from its evidence (item 279, row 5). */
  recommendation?: string | null;
  targets?: string[];
  /** The pages the check found, where it kept fewer in `urls` (item 276). */
  affectedTotal?: number | null;
  /** The record says this came back after a fix (screen audits round 3,
   *  Security IP-01: the table read "open" on four regressed rows). */
  regressed?: boolean;
  /** Not a finding: a coverage note, carried so the check table can keep its
   *  row while the Fixes block drops it (`isCoverageNote`, item 180). */
  coverageNote?: boolean;
  /** The structured-data block this row is about, as the inventory numbers
   *  it (brief v16 step AS), and where the change goes in the operator's
   *  own words (step AT). */
  block?: string | null;
  where?: string | null;
  /** The image this row is about, where the part has one, and the other
   *  checks its one replacement closes (brief v15 step AR). */
  image?: string | null;
  /** Every image the card's findings name (item 244): a card is one check
   *  on one page, so two heavy images on a page are one card, and a filter
   *  to either has to find it. */
  images?: string[];
  alsoResolves?: string[];
  /** The analysis wrote a replacement and the reader did not keep it, and
   *  why (screen audits round 3, Title & description AC-05). */
  copyNotKept?: string | null;
  /** The finding states this card stands for (item 237): what Confirm,
   *  Accept and Withdraw write to. */
  fingerprints?: string[];
  /** The URL template the row is about, where it is a per-template row
   *  (items 217, 222): drawn as the card's subject. */
  template?: string | null;
  /** The page's outline as the crawl kept it, where the site view carries it
   *  (item 224) - the Headings diff's baseline with no page in hand. */
  baseline?: (Pick<Facts, "outline" | "headings"> & { captured_at?: string | null }) | null;
  kind?: string | null;
  group?: string | null;
  /** The sources a link-suggestion row proposes, each with the anchor and
   *  the heading it belongs after (brief v17 step AW). A row's own fields
   *  travel on the contract already; this is the shape this part's do. */
  suggestions?: { source: string; anchor: string; after?: string;
                  overlap?: string[] }[];
  /** Which entry of the part's `brief_fixes` serves this row (brief v20,
   *  items 147 and 148). The fix is stored once and pointed at, because one
   *  change repeated per row is how a single markup fix came to read as six
   *  on the Images part. */
  fixId?: string | null;
  /** The checks THIS row sets aside, on the row that survives (brief v20,
   *  items 147 E3 and 148 G4). A set-aside check emits no row of its own,
   *  so the row that answers for it names it -- which is why a reader
   *  looking for that check finds the answer here rather than being told to
   *  run deeper, and why it is still not `not_assessed`. */
  suppressed?: string[];
  /** How sure the brief is, where it says. Absent on a row the sweep
   *  measured: a measurement's confidence is not the model's to state. */
  confidence?: string | null;
  /** A Security brief row's rollout (brief v20 step BD). */
  rollout?: import("./api").Rollout | null;
  /** The AI surface brief's row payload (item 145 BH). */
  payload?: Record<string, unknown>;
};

/** One entry of a part's `brief_fixes` (brief v20, items 147 E2 and 148 G3):
 *  the fix itself, stored once, naming what it serves. */
export type BriefFix = {
  /** The installed schemas' own field names (mobile/2, intl/2). The first
   *  version of this type used `where`, `serves` and `pages`, none of which
   *  either brief emits: every card on the first real run would have read
   *  "where it goes is not stated" with no page count. Found by reading the
   *  schema after a real Acme run, not by any test, because the test built
   *  its JSON from these same wrong names. */
  fix_id?: string;
  edit_point?: string;
  change?: string;
  /** What it serves: templates on Mobile, clusters on International. */
  templates?: string[];
  clusters?: string[];
  /** Mobile only: the directives the change strips out. */
  removes?: string[];
  closes?: string[];
  pages_affected?: number;
  confidence?: string | null;
  note?: string;
};

/** How sure a brief is about a row or a fix (brief v20, items 147 E4 and
 *  148 G5). Rendered for both parts from one component.
 *
 *  Absent means "not stated", which is NOT low: a row the sweep measured
 *  carries no confidence because a measurement's confidence is not the
 *  model's to state, and drawing "low" there would grade the engine's own
 *  work as a guess. So nothing renders rather than a neutral chip.
 *
 *  Item 140's tones: `high` reads as a level, `low` as a warning, anything
 *  else stays muted rather than being mapped to a level it did not claim.
 */
export function ConfidenceChip({ value }: { value?: string | null }) {
  if (!value) return null;
  const word = value.trim().toLowerCase();
  // Confidence is not a severity, so it takes no severity fill (item 140).
  // LOW is drawn as a candidate -- outline, because a low-confidence row is a
  // candidate in all but name -- and the rest as plain brief text. The first
  // version used `tone-level-*` classes that exist nowhere in the stylesheet,
  // so the chip rendered unstyled and no type check could see it: they were
  // raw class strings, not `Tone`s.
  const tone: Tone = word === "low" ? "state-candidate" : "source-brief";
  return (
    <span className={`tone tone-${tone} conf-chip`}
          title={"How sure the analysis is about this row. A row the automatic checks "
                 + "measured carries none: a measurement's confidence is not "
                 + "the model's to state."}>
      confidence {word}
    </span>
  );
}

/** Why a row has no verdict of its own, inside the row and under its
 *  evidence (brief v20, items 147 E3 and 148 G4).
 *
 *  **Two producers, one state**, which is the trap brief 160 names. Sweep
 *  precedence writes it (3b, and BA's one-verdict-per-page) and a brief
 *  writes it in its own row field; the clause names which, and the screen
 *  shows one thing. Letting the two make two states is how a reader ends up
 *  with "suppressed" and "set aside" meaning the same thing differently.
 *
 *  Neither pass nor fail, so item 140's mute and an outline rather than a
 *  level tone. A check set aside is not good news.
 */
export function SuppressedStrip({ checks }: { checks?: string[] }) {
  // Empty is the common, correct answer -- nothing set aside -- and it must
  // render nothing. The first real run wrote `[]` on every row and the reader
  // had turned it into the string '[]', which would have put this strip on
  // every card.
  if (!checks?.length) return null;
  return (
    <p className="sup-strip">
      <span className="sup-lbl">Also answers for</span>
      {checks.map((c) => <code key={c}>{c}</code>)}
    </p>
  );
}

/** The part's fixes as their own list, sorted by the pages each affects,
 *  each naming what it serves (brief v20, items 147 E2 and 148 G3).
 *
 *  **A low-confidence fix is a different card, not a dimmed one.** It has no
 *  corrected-tag block at all -- 147 E2 in terms -- because a replacement
 *  rendered in a copyable block IS an instruction, and an instruction the
 *  brief is not sure of should not be offered as one. It says what it
 *  suspects and what would settle it instead.
 *
 *  Sorted by pages because that is the order the work is worth doing in, and
 *  the count is the fix's own rather than a second count of the rows: a fix
 *  serving three templates is one change.
 */
export function BriefFixes({ fixes }: { fixes: BriefFix[] }) {
  if (!fixes.length) return null;
  const ordered = [...fixes].sort(
    (a, b) => (b.pages_affected ?? 0) - (a.pages_affected ?? 0));
  return (
    <section className="brief-fixes">
      <h4>Fixes</h4>
      {ordered.map((f, i) => {
        const low = (f.confidence || "").trim().toLowerCase() === "low";
        const change = f.change;
        const serves = f.templates ?? f.clusters ?? [];
        return (
          <div className={`brief-fix${low ? " brief-fix-low" : ""}`}
               key={f.fix_id || i}>
            <div className="bf-head">
              {f.fix_id && <span className="bf-id">{f.fix_id}</span>}
              <span className="bf-where">
                {f.edit_point || "where it goes is not stated"}
              </span>
              <span className="bf-pages">
                {f.pages_affected != null
                  && `${f.pages_affected} page${f.pages_affected === 1 ? "" : "s"}`}
                {serves.length ? ` · ${serves.join(" · ")}` : ""}
              </span>
            </div>
            {/* The corrected thing, in a block to copy — and ONLY where the
                brief is sure of it. A low-confidence card gets the sentence
                below instead, which is the whole difference between a fix and
                a candidate. */}
            {change && !low && <div className="bf-change">{change}</div>}
            {low && (
              <p className="bf-candidate">
                Candidate, not a fix: the analysis is not sure enough of this to
                offer a change to paste.
              </p>
            )}
            {!!f.removes?.length && !low && (
              <p className="muted bf-closes">Removes {f.removes.join(" · ")}</p>
            )}
            {f.note && <p className="muted bf-note">{f.note}</p>}
            {!!f.closes?.length && (
              <p className="muted bf-closes">
                Closes {f.closes.join(" · ")}
              </p>
            )}
            <ConfidenceChip value={f.confidence} />
          </div>
        );
      })}
    </section>
  );
}

function sourceWords(sources: string[], disagree = false): string {
  const has = (w: string) => sources.includes(w);
  // Item 215: "agree" only when they do. Both raising the check is not
  // agreement - on twenty22 43 cards read "agree" over a Now naming
  // #local_business and a Replace-with naming #organization.
  if (has("sweep") && has("brief")) {
    return disagree ? "automatic checks and analysis disagree" : "automatic checks and analysis agree";
  }
  return sourceWord(has("brief") ? "brief" : "sweep");
}

/** The structured-data @ids a sentence names (item 215): an absolute URL
 *  with a fragment, the form every @id in this product's evidence takes. */
export function idsNamed(text: string | null | undefined): Set<string> {
  return new Set((text ?? "").match(/https?:\/\/[^\s"'<>,)]+#[\w-]+/g) ?? []);
}

/** A merged card whose two readings name @ids and share none: the sweep's
 *  Now points at one node and the brief's Replace-with at another. */
export function readingsDisagree(current: string | null | undefined,
                                 replacement: string | null | undefined): boolean {
  const a = idsNamed(current), b = idsNamed(replacement);
  return a.size > 0 && b.size > 0 && ![...a].some((x) => b.has(x));
}

/** The fixes on the current scope: the record's open, regressed and
 *  candidate rows for this part's checks, then the rows the brief could
 *  not assess. Ordered by severity, then by check, so the same page reads
 *  the same way twice running. */
const RANK = ["critical", "high", "medium", "low", "info"];

/** Checks whose rows are one per agent or entity, all on the start URL (item
 *  145): keyed by page alone, fifteen agents' edge blocks read as one card at
 *  the worst severity, and a declared LOW sat inside an undeclared HIGH. */
/** What a brief writes for "the whole site" in a row's page: `*`, nothing,
 *  or `all`. The same set as `runs.SITE_WIDE_PAGES`. */
export const SITE_WIDE_PAGES = new Set(["*", "", "all"]);

export const PER_SUBJECT_CHECKS = new Set(["edge-blocks-ai-ua", "ua-sensitive",
  "entity-unnamed", "ai-crawler-blocked"]);

/** Item 271 (row 4): analysis checks owed a row on every page an automatic
 *  check raised - `contract.REQUIRED_BY`, by bare id. */
export const REQUIRED_BY: Record<string, string[]> = {
  "link-suggestion": ["inlinks-low", "orphan"],
};

/** The pages a check is owed a row on, from the open automatic rows of its
 *  triggers; null where it is owed none. */
export function owedPages(checkId: string, fixes: { checkId: string; page: string;
                                                    urls?: string[]; sources: string[] }[]) {
  const triggers = REQUIRED_BY[checkId];
  if (!triggers) return null;
  const on = fixes.filter((f) => triggers.includes(f.checkId) && f.sources.includes("sweep"));
  const pages = new Set(on.flatMap((f) => (f.urls?.length ? f.urls : [f.page])).map(pathOf)).size;
  return pages ? { triggers: [...new Set(on.map((f) => f.checkId))], pages } : null;
}

/** Item 251: whether the automatic checks' reading outranks an analysis's
 *  hold on a check - a free check they measured after the analysis wrote it.
 *  The table then reads the check clean, and the hold stays under Fixes with
 *  its date. One rule, read by both (item 276 row 4 found a line pointing at
 *  a "not assessable" row the table did not draw). */
export function sweepOutranks(part: Category, full: string, checkId: string,
                              sweepAt: string | null | undefined,
                              unmeasured: Map<string, unknown>): boolean {
  const briefAt = part.brief_run?.at ?? null;
  return Boolean(sweepAt && briefAt
                 && new Date(sweepAt).getTime() > new Date(briefAt).getTime())
    && costOf(part, full) === "free" && !unmeasured.has(checkId)
    // Nor where the sweep tests the check only in part (screen audits round
    // 3, Security AC-01): its silence on cert-chain is an expiry date, not a
    // chain, and the analysis's hold on the rest stands.
    && !part.partly_measured?.[checkId];
}

/** The checks table's row for a check, by its full id, as an element id. */
export const checkRowId = (full: string) => `check-row-${full.replace(/[^A-Za-z0-9-]/g, "-")}`;

/** One card's "fixed?" control and its re-check (item 279, row 6). The tick
 *  is the fix loop's own, with its three readable refusals; the re-check
 *  asks the verify route about this card's row alone. */
function CardDone({ m, loop }: { m: Markable; loop: ReturnType<typeof useFixLoop> }) {
  const said = loop.outcome[m.fingerprint];
  return (
    <div className="fix-done">
      <span className="fix-lbl">Fixed? </span>
      <FixTick f={m} marked={loop.marked} onMark={loop.mark} />
      {loop.marked.has(m.fingerprint) && m.names_a_page && (
        <SecondaryButton busy={loop.verifying} onClick={() => loop.verify([m.fingerprint])}>
          re-check this page
        </SecondaryButton>
      )}
      {said && <span className="muted" role="status"> · {DONE_WORD[said]}</span>}
      {loop.error && <span className="muted" role="alert"> · {loop.error}</span>}
    </div>
  );
}

/** A re-check's verdict, in the card's words. */
const DONE_WORD: Record<string, string> = {
  cleared: "cleared on the re-check",
  still: "still there on the re-check",
  undecided: "not checked: the re-check could not read it",
  unchanged: "unchanged",
};

/** The event a control outside Fixes sends to open one check's group. */
const FIX_OPEN = "clauditseo:fix-open";

/** Open a check's group under Fixes and bring its first card into view. */
export function openFixGroup(check: string) {
  if (check) window.dispatchEvent(new CustomEvent(FIX_OPEN, { detail: check }));
}

/** Item 267 (row 4): a Fixes group's label, counted as the table counts.
 *  It counted cards and called them pages: four crawlers' edge blocks on
 *  the one page "/" read "4 pages" beside a table reading 3 of 3 probed.
 *  Pages are the distinct paths every card names; a per-subject check says
 *  its subjects first ("4 crawlers · 3 pages"). A group naming no page says
 *  how many cards it holds, not "0 pages". */
export function groupCount(checkId: string, cards: { page: string; urls?: string[] }[]): string {
  const plural = (n: number, w: string, ws = `${w}s`) => `${n} ${n === 1 ? w : ws}`;
  const paths = new Set(cards.flatMap((f) => (f.urls?.length ? f.urls : [f.page]))
                             .filter(Boolean).map(pathOf));
  const pages = paths.size ? plural(paths.size, "page") : "";
  if (PER_SUBJECT_CHECKS.has(checkId)) {
    const subj = checkId === "entity-unnamed" ? plural(cards.length, "entity", "entities")
                                              : plural(cards.length, "crawler");
    return pages ? `${subj} · ${pages}` : subj;
  }
  // Item 275 (row 8): where one page carries more than one card (the
  // automatic checks' and an analysis's on `/`), the cards are said too,
  // so "2 pages" is never two cards on one page.
  if (pages && cards.length > paths.size) return `${pages} · ${plural(cards.length, "card")}`;
  return pages || plural(cards.length, "card");
}

/** Whether a check is this part's, by the SAME rule the engine files it
 *  under (item 136o): its check is one the part enumerates, OR its id
 *  carries a prefix the part owns. `axe-<rule>` ids are minted from
 *  axe-core's rule set at run time and cannot be enumerated, so the overlay
 *  boxed barriers the Fixes block had no card for until this read the prefix
 *  too. One definition of "belongs to this part", so the next
 *  dynamically-named family does not reopen the gap - exported since item
 *  218, when the replacement table turned out to hold a second one. */
export function belongsTo(part: Pick<Category, "brief_checks" | "check_prefixes" | "filed_checks">) {
  return (checkId: string) =>
    (part.brief_checks ?? []).some((c) => c.split("/").pop() === checkId)
    || (part.check_prefixes ?? []).some((pre) => checkId.startsWith(pre))
    // And every check the engine filed here (brief v25 step BP): a sweep row
    // no brief enumerates is still this part's finding.
    || (part.filed_checks ?? []).includes(checkId);
}

/** Item 269. A card the analysis closed and nothing else raised: its row is
 *  a PASS-OVERRIDE ("No consolidation on present evidence"), which the
 *  cannibalisation prompt emits to say a flag is not a fault. On twenty22's
 *  Content three such rows were drawn as Medium faults with a copy button
 *  and counted in ANALYSIS, PAGES and the strip. Where the automatic checks
 *  raised the check on the same page the card still counts - as theirs. */
export const closedByAnalysis = (f: Pick<Fix, "override" | "sources">): boolean =>
  Boolean(f.override) && !f.sources.includes("sweep");

/** Item 270. An analysis row the automatic checks have since cleared on every
 *  page it names, and that they do not raise themselves. It said so on its
 *  card ("superseded on ...") and was still a card and a count: on twenty22's
 *  Structured data 43 `schema-orphan-instance` rows read as 66 free-check
 *  cards behind a "show all 43" button, over a check the sweep raised once. */
export const overtaken = (f: Pick<Fix, "supersededOn" | "sources">): boolean =>
  Boolean(f.supersededOn) && !f.sources.includes("sweep");

export function fixesOf(part: Category, states: FindingState[], page: string): Fix[] {
  const belongs = belongsTo(part);
  const mine = states.filter(
    (s) => (s.state === "open" || s.state === "regressed" || s.state === "candidate")
           && belongs(s.check_id));
  const by = new Map<string, Fix>();
  for (const s of mine) {
    const url = s.affected_urls[0] ?? "";
    const key = `${s.check_id}|${pathOf(url)}`
      + (PER_SUBJECT_CHECKS.has(s.check_id) && s.source === "deterministic" ? `|${s.fingerprint}` : "");
    const word = s.source === "deterministic" ? "sweep" : "brief";
    const seen = by.get(key);
    if (seen) {
      if (!seen.sources.includes(word)) seen.sources.push(word);
      seen.urls = [...new Set([...(seen.urls ?? []), ...s.affected_urls])];
      seen.affectedTotal = Math.max(seen.affectedTotal ?? 0, s.affected_total ?? 0) || null;
      // The brief's row carries the copy; the sweep's carries the reading.
      if (word === "brief" && s.proposed) seen.replacement = s.proposed;
      if (word === "sweep") {
        seen.sweepFp = s.fingerprint;
        seen.namesAPage = s.names_a_page;
        seen.attemptedAt = s.attempted_at ?? null;
        seen.current = s.summary;
        seen.recommendation = s.recommendation ?? seen.recommendation;
        seen.targets = s.targets?.length ? s.targets : seen.targets;
        // The page's string and its overage are the measurement's, whichever
        // row was read first (screen audits round 3, title-desc AC-04: 17 of
        // 30 merged cards lost both and sorted last).
        seen.said = s.said ?? seen.said;
        seen.overPx = s.over_px ?? seen.overPx;
      }
      // Each source's own date (item 251).
      if (word === "sweep") {
        seen.measuredAt = s.measured_at ?? seen.measuredAt;
        seen.measuredTier = s.measured_tier ?? seen.measuredTier;
      } else {
        seen.analysedAt = s.analysed_at ?? s.measured_at ?? seen.analysedAt;
      }
      // And the brief's row carries what it is about (brief v15): the
      // image, the checks its one replacement closes, and whether the
      // change is a template's. A sweep row read first must not lose them.
      if (word === "brief") {
        if (s.brief && !(seen.briefs ?? []).includes(s.brief)) seen.briefs = [...(seen.briefs ?? []), s.brief];
        seen.image = s.image ?? seen.image;
        seen.alsoResolves = s.also_resolves?.length ? s.also_resolves : seen.alsoResolves;
        seen.kind = s.kind ?? seen.kind;
        seen.group = s.group ?? seen.group;
        seen.template = s.template ?? seen.template;
        seen.fingerprints = [...(seen.fingerprints ?? []), s.fingerprint];
        for (const im of [...(s.images ?? []), ...(s.image ? [s.image] : [])]) {
          if (!(seen.images ?? []).includes(im)) seen.images = [...(seen.images ?? []), im];
        }
        seen.supersededOn = s.superseded_on ?? seen.supersededOn;
        seen.override = s.brief_status === "PASS-OVERRIDE";
        seen.unseenSince = s.unseen_since ?? seen.unseenSince;
        seen.copyNotKept = s.copy_not_kept ?? seen.copyNotKept;
        seen.rollout = s.rollout ?? seen.rollout;
        seen.payload = s.payload ?? seen.payload;
      }
      if (RANK.indexOf(s.severity) < RANK.indexOf(seen.severity)) seen.severity = s.severity;
      seen.candidate = seen.candidate && s.state === "candidate";
      seen.toConfirm = seen.candidate && Boolean(seen.toConfirm || s.to_confirm);
      seen.regressed = seen.regressed || s.state === "regressed";
      continue;
    }
    by.set(key, {
      key, check: `${s.dimension}/${s.check_id}`, checkId: s.check_id, page: url,
      pages: s.affected_urls.length, urls: [...s.affected_urls], coverageNote: isCoverageNote(s),
      affectedTotal: s.affected_total ?? null,
      recommendation: word === "sweep" ? s.recommendation ?? null : null,
      sweepFp: word === "sweep" ? s.fingerprint : null,
      namesAPage: word === "sweep" ? s.names_a_page : false,
      briefs: word === "brief" && s.brief ? [s.brief] : [],
      attemptedAt: word === "sweep" ? s.attempted_at ?? null : null,
      targets: word === "sweep" ? s.targets ?? [] : [],
      block: s.block ?? null, where: s.where ?? null,
      severity: s.severity, sources: [word], candidate: s.state === "candidate",
      toConfirm: s.state === "candidate" && Boolean(s.to_confirm),
      regressed: s.state === "regressed",
      current: s.summary, replacement: s.proposed ?? null, note: "",
      said: s.said ?? null, overPx: s.over_px ?? null,
      image: s.image ?? null,
      images: [...new Set([...(s.images ?? []), ...(s.image ? [s.image] : [])])],
      alsoResolves: s.also_resolves ?? [],
      fingerprints: [s.fingerprint],
      supersededOn: s.superseded_on ?? null,
      override: word === "brief" && s.brief_status === "PASS-OVERRIDE",
      measuredAt: word === "sweep" ? s.measured_at ?? null : null,
      measuredTier: word === "sweep" ? s.measured_tier ?? null : null,
      analysedAt: word === "brief" ? s.analysed_at ?? s.measured_at ?? null : null,
      unseenSince: s.unseen_since ?? null,
      copyNotKept: word === "brief" ? s.copy_not_kept ?? null : null,
      kind: s.kind ?? null, group: s.group ?? null, template: s.template ?? null,
      baseline: part.page_outlines?.[url] ?? null,
      suggestions: s.suggestions ?? [],
      // Brief v20's three row fields (items 147, 148).
      fixId: s.fix_id ?? null, suppressed: s.suppressed ?? [],
      confidence: s.confidence ?? null,
      rollout: s.rollout ?? null,
      payload: s.payload,
    });
  }
  // A check that can only ever be held is held on every page, including
  // the ones no brief has read - so the page states it rather than waiting
  // for a run to say so. Read from the part rather than listed here: which
  // checks these are is the engine's registry, not the screen's (step AI).
  const heldOnly: Fix[] = (part.brief_held_only ?? [])
    // Where the brief wrote its own held row for the check, that row is
    // this card - it says the same thing and says more. Birch rendered
    // both: the brief writes `page: "*"` and the standing card carries
    // whichever page is open, so a check-and-page test could not see they
    // were one answer. Matched on the check alone, and only the standing
    // card is dropped - a brief holding one check on three pages still
    // gets three cards, which is what those pages differ about.
    .filter((h) => !(part.brief_held ?? []).some((b) => b.check === h.check))
    .map((h) => ({
    key: `held-only|${h.check}|${pathOf(page)}`, check: h.check,
    checkId: h.check.split("/").pop() ?? h.check, page,
    severity: "info", sources: [], candidate: false,
    current: "", replacement: null, note: "", needs: h.needs,
    image: null, alsoResolves: [],
  }));
  // `*` is the page a brief writes when it could not assess a check
  // anywhere on the site, and a site-wide answer is an answer about this
  // page too. Narrowing used to drop those rows, and the check then fell
  // into "N checks pass on this page" - `img-sitemap-missing` read as
  // passing on Birch's home page while the brief was saying site-wide
  // that it could not judge it.
  // Item 269 (row 3): and `all`, which the Content analysis wrote for the same
  // thing. Its `cannibalisation` hold on page `all` dropped on narrowing, so
  // `/` counted the check among the 12 that pass there.
  const onPage = (u: string) => !page || !u || SITE_WIDE_PAGES.has(u) || pathOf(u) === pathOf(page);
  const held: Fix[] = [...heldOnly, ...(part.brief_held ?? [])]
    .filter((h) => onPage(h.page))
    .map((h) => ({
      key: `held|${h.check}|${h.page}|${h.image ?? ""}`, check: h.check,
      checkId: h.check.split("/").pop() ?? h.check, page: h.page,
      severity: "info", sources: ["brief"], candidate: false,
      current: "", replacement: null, note: "", needs: h.needs,
      image: h.image ?? null, alsoResolves: [],
    }))
    // A check the record already holds a row for is not also held.
    .filter((h) => ![...by.values()].some((f) => f.checkId === h.checkId
                                                 && pathOf(f.page) === pathOf(h.page)));
  const order = (f: Fix) => `${RANK.indexOf(f.severity)}|${f.checkId}|${pathOf(f.page)}`;
  // Item 271: the automatic checks file `broken-internal` on the broken
  // TARGET and the analysis on the SOURCE page that links to it, so the two
  // never share a card and the analysis's read "candidate" over a 404 the
  // free checks had measured. A source card naming a target the automatic
  // checks raised for the same check is said to be corroborated by them.
  const sweepOnly = [...by.values()].filter((f) => f.sources.length === 1 && f.sources[0] === "sweep");
  for (const f of by.values()) {
    if (f.sources.length !== 1 || f.sources[0] !== "brief") continue;
    const said = `${f.current ?? ""} ${f.replacement ?? ""}`;
    const hits = sweepOnly.filter((s) => s.checkId === f.checkId && s.page !== f.page
      && pathOf(s.page) !== "/" && said.includes(pathOf(s.page)));
    if (hits.length) f.corroboratedBy = [...new Set(hits.map((s) => pathOf(s.page)))];
  }
  return [...by.values(), ...held].sort((a, b) => order(a).localeCompare(order(b)));
}

/** The unmeasured members of a check list, grouped by the reason this run
 *  could not measure them (item 157).
 *
 *  One helper for both clean lines on this page, because two spellings of
 *  "which of these did we not measure" is how the defect this item fixes came
 *  to exist in the first place: three surfaces each deciding for themselves
 *  what counts as a pass.
 *
 *  A check absent from `why` is not returned - it was measured, and whether it
 *  passed is the caller's question, not this one's.
 */
export function byReason(ids: string[],
                         why: Map<string, string>): [string, string[]][] {
  const out = new Map<string, string[]>();
  for (const id of ids) {
    const reason = why.get(id);
    if (reason) out.set(reason, [...(out.get(reason) ?? []), id]);
  }
  return [...out];
}

/** One heading as the parser recorded it. `inMain` is null on a run
 *  crawled before the outline was recorded (brief v11 step AJ): unknown,
 *  which is not the same as "outside", and the line says neither. */
export type Line = { level: number; text: string; inMain: boolean | null; next: string;
                    /** Where a sub-service heading points, on a row that
                     *  names one (brief v14 step AP): a path, or the one
                     *  placeholder permitted anywhere on this page. */
                    link?: string;
                    /** The model wrote `[proposed]` on it (item 268): its
                     *  own word for a new heading, now a flag, not text. */
                    proposed?: boolean };

export function outlineOf(facts: Facts, cap: number = OUTLINE_SHOWN): Line[] {
  // The cap sits between the field and the map on purpose: it is the bound
  // the real-data-scale invariant looks for, and putting it after the map
  // would bound the list without saying so where the list is read.
  if (facts.outline?.length) {
    return facts.outline.slice(0, cap).map(([level, text, inMain, next]) => ({ level, text, inMain, next }));
  }
  return (facts.headings ?? []).slice(0, cap).map(([level, text]) => ({ level, text, inMain: null, next: "" }));
}

/** How many headings one page can hold at all: the crawl's own
 *  `HEADING_CAP` (`clauditseo/crawler/evidence.py`). A card that needs the
 *  whole outline - a fix's before-and-after - asks for that rather than
 *  for no bound at all. */
export const OUTLINE_KEPT = 60;

/** How much of an outline stands before a control reveals the rest.
 *  Measured across the 557 stored crawl pages: median 21 headings, p95 47,
 *  max 60 - which is `OUTLINE_KEPT`, a number that says how much was kept
 *  rather than how much is readable at once. */
export const OUTLINE_SHOWN = 25;

/** How many structured-data blocks stand before the rest are folded. A
 *  page carries one to four; a page carrying more is carrying duplicates,
 *  which is  and a finding rather than a reason to
 *  render twenty cards. */
export const SCHEMA_BLOCKS_SHOWN = 12;

/** How many images stand before a control reveals the rest. Measured
 *  across the 557 stored crawl pages: median 25 images, p95 60, max 60 -
 *  the crawl's own `IMAGE_CAP`, which says how many were kept rather than
 *  how many are readable at once. */
export const IMAGES_SHOWN = 24;
export const IMAGES_KEPT = 60;

/** A brief's corrected outline, as it writes one: `h1 Some heading / h2
 *  Another → the words that follow it`. The arrow introduces context, not
 *  heading text, so it is cut. */
export function parseOutline(replacement: string | null): Line[] {
  if (!replacement) return [];
  const out: Line[] = [];
  for (const part of replacement.split(" / ")) {
    const m = /^h([1-6])\s+([\s\S]*)$/.exec(part.trim());
    if (!m) continue;
    const [raw, ...rest] = m[2].split(" → ");
    const after = rest.join(" → ").trim();
    // Item 268: the model's tokens are fields, not heading text. `[proposed]`
    // was drawn beside the card's own "[proposed]" chip, and an `[answer
    // stub: ...]` was part of the heading the diff then failed to match.
    const stub = /\[answer stub:\s*([^\]]*)\]/i.exec(raw);
    const proposed = /\[proposed\]/i.test(raw);
    const text = raw.replace(/\[proposed\]/gi, "").replace(/\[answer stub:[^\]]*\]/gi, "")
      .replace(/\s+/g, " ").trim();
    // A target path or the placeholder is a link; anything else after the
    // arrow is the words that follow the heading, which is context.
    const link = /^(\/|\[TO CONFIRM)/.test(after) ? after : undefined;
    out.push({ level: Number(m[1]), text, inMain: null,
               next: link ? "" : (after || stub?.[1]?.trim() || ""), link, proposed });
  }
  return out;
}

/** Item 268: the key two spellings of one heading share. Case, spacing,
 *  apostrophes ("Lets" and "Let's", curly and straight) and a trailing `?`
 *  are how a heading is written, not which heading it is: matched on exact
 *  text, "Lets find the right steps together" read as removed and "Let's
 *  find ..." as proposed, and seven FAQ questions the same. */
export const outlineKey = (t: string) => t.normalize("NFKC").toLowerCase()
  .replace(/['‘’ʼ`´]/g, "").replace(/\s+/g, " ").trim().replace(/\?+$/, "").trim();
const norm = outlineKey;

/** What `copy outline` copies (item 268): the parsed lines, one `Hn text`
 *  each, with the model's tokens and stubs left out. */
export const outlineCopy = (replacement: string | null) =>
  parseOutline(replacement).map((l) => `H${l.level} ${l.text}`).join("\n");
const outlineLines = (replacement: string | null) => parseOutline(replacement).length;

/** Write a brief for the page in hand (brief v17 step AX).
 *
 *  A **generator**: it emits no findings and adds no Record rows. What it
 *  produces is a document a writer works from, so the control says what
 *  it makes rather than what it checks, and the result is a line naming
 *  the stored document rather than a count of anything.
 *
 *  Only where a page is in hand. "Write a brief" with no page is a
 *  question about which page, and a control that has to ask is a control
 *  that should not have been offered.
 */
export function WriteBrief({ runId, page, price = null }:
                           { runId: string | null; page: string; price?: number | null }) {
  // `price`: the lanes payload's, for the content brief (item 269, row 11).
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  // The brief as written, to read where it was asked for (item 269, row 11):
  // "brief written for /" named a document nothing on screen opened.
  const [written, setWritten] = useState<Envelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!page || !runId) return null;
  return (
    <span className="write-brief">
      {/* Item 178: priced in words and confirmed. Item 269 (row 11): the
          price is the lanes payload's, where it has one; where it has none
          the button says so rather than leaving no price. */}
      <SpendButton className="write-brief-btn" busy={busy} price={price}
                   title={`Writes a content brief for ${pathOf(page)} from what this `
                          + "audit found. Spends tokens; adds no findings."}
                   confirm={{ title: `Write a content brief for ${pathOf(page)}?`,
                              body: <><SpendTarget page={pathOf(page)} />
                                <p>It writes a brief a writer works from, from what this
                                  audit found. It adds no findings.</p></>,
                              action: "Write the brief" }}
                   onSpend={async () => {
                     setBusy(true);
                     setError(null);
                     try {
                       const got = await api.post<Envelope>(
                         `/api/runs/${runId}/expert/content-brief`, { url: page });
                       setWritten(got && typeof got === "object" ? got : null);
                       setDone(pathOf(page));
                     } catch (e) {
                       setError((e as Error).message);
                     } finally {
                       setBusy(false);
                     }
                   }}>
        Write a brief for this page
      </SpendButton>
      {/* Mounted ahead of its content, and the caption above never
          changes: a button's label is its accessible name (UX-66). */}
      <span className="muted write-brief-state" role="status" aria-live="polite">
        {busy ? <Working>writing…</Working> : done ? `brief written for ${done}` : ""}
      </span>
      {error && <span className="muted write-brief-error">{error}</span>}
      {written && (
        <details className="write-brief-read">
          <summary>read the brief</summary>
          <Report title={`Content brief for ${done ?? pathOf(page)}`} result={written}
                  runId={runId} />
        </details>
      )}
    </span>
  );
}

/** Block 1 — the two things this page can do, and what produced what is
 *  on it. One free, one paid; no depth choice, because a sweep re-check
 *  is free at every depth and the choice was noise. */
function Actions({ part, page, sweep, brief, pages, estSeconds, estCost,
                   onRecheck, onRerun, busy, briefNote,
                   recheckConfirm = null, cardDates = [], tool = null, others = [],
                   estRuns = null, rereads = null, lastCost = null, othersHref = null }: {
  /** Where the other analyses are run (screen audits round 3, Content
   *  UX-01): "run from the Analyses list" was plain text naming a screen. */
  othersHref?: string | null;
  /** The last recorded cost here, where it is the price shown (item 276,
   *  row 11): above the median, so the median is not what is quoted. */
  lastCost?: number | null;
  /** Item 271 (row 10): what the price is the median of, and what a re-run
   *  would re-read - the analysis's rows, and how many sit on pages the
   *  automatic checks still raise. */
  estRuns?: number | null; rereads?: { rows: number; raised: number } | null;
  /** The analysis the paid button runs, and the others that write to this
   *  part (item 269, row 5). The price is the named one's. */
  tool?: string | null; others?: string[];
  /** When each card's own row was measured (item 274, row 5). */
  cardDates?: string[];
  part: Category; page: string;
  sweep: SweepRun | null; brief: Category["brief_run"];
  pages: number | null; estSeconds: Estimate | null; estCost: number | null;
  onRecheck: () => void; onRerun: () => void;
  busy: "sweep" | "brief" | null; briefNote: string | null;
  /** The confirmation the re-check opens in site mode, where the press
   *  starts a whole-site audit (item 189).
   *
   *  A slot rather than a control built here, and the reason is F-06 — "do
   *  not add a second launcher or a second way to configure a run". What
   *  arrives is `SectionRefresh`, the same component the re-audit drawer
   *  opens for the same request: it names the dimension, names every other
   *  part that moves with it, rules out page scope, and states the depth and
   *  that no model is invoked. A confirmation written here instead would be a
   *  second description of one act, free to drift from the first.
   *
   *  Null in page mode, where `/refresh` is one page that is known at press
   *  time and the caption above is already true. */
  recheckConfirm?: ReactNode;
}) {
  /** What the press covers, and in site mode that is not a page set at all
   *  (audit F17, channel ruling 20260918-1431).
   *
   *  It read "the N pages in the record" - item 180 e5's wording - and the
   *  record is not what either control reads. `recheckPart` branches: with a
   *  page in hand and a per-page part it posts `/refresh`, which is "one page,
   *  always"; otherwise it posts `/audits` with `tier: "auto"`, which is a NEW
   *  adaptive audit whose page set the crawl decides as it runs. There is no
   *  number to name at press time, so naming one invents a figure - the fault
   *  this round exists to end. On Acme the button offered "the 227 pages in
   *  the record" for a request that had chosen no pages.
   *
   *  Page mode stays specific, because there the set is exactly one and known.
   *  The measured population still belongs to the block's coverage line, which
   *  is where a measurement's population belongs rather than on a button. */
  const scope = page ? "this page" : "this part's checks";
  /** And the analysis's own, which is a different request: it is posted
   *  against the part's reference crawl (`/api/runs/<id>/expert/...`, item
   *  239 step 5), so its scope is that audit - not the record, not the site,
   *  and not the part's checks. The confirmation states the crawl and its date. */
  // Item 269 (row 5): the run is posted against the part's reference crawl
  // with no page in it, so in page mode it is still the whole audit; "this
  // page" named a scope the request did not carry.
  const briefScope = page ? "this audit, all pages" : "this audit";
  // Item 274: no fallback. A part no automatic check covers (International)
  // has no dimension, and "ONP" here dated it by the On-page sweep.
  const dim = part.refresh?.dimension ?? null;
  /** Item 274, finishing item 232: with nothing to re-check, the re-check is
   *  held and says why. It was enabled, left-most, and did nothing. */
  const noRecheck = part.refresh ? null : "no automatic check covers this part";
  // `stamp`, not a third spelling of the slice (audit F11): this one had the
  // replace and the slice the other way round, which is why a grep for the
  // other order missed it.
  const when = (iso: string | null | undefined) => stamp(iso);
  /** Item 232: the gate has settled that the analysis does not apply. The
   *  button offered "Run analysis" and the line under it said none "has run"
   *  - as if one were owed - over a card saying it was not applicable. */
  const gated = part.gate?.state === "na";
  // Item 274: the gate's own first sentence, not a second wording of it.
  const gatedWhy = part.gate?.why
    || (part.gate?.reason ?? "").split(/(?<=\.)\s/)[0].replace(/\.$/, "")
    || "not applicable on this site";
  return (
    <div className="part-actions">
      <div className="part-acts">
        {/* The label never changes under the press. A button's label is its
            accessible name, so a caption that swaps to a busy word is
            announced as a different control appearing - UX-66, and the
            house pattern (`components.tsx`, `reports.tsx`) says the state
            beside it in a region that is mounted before it has anything to
            say. */}
        {/* Item 204: held through the factory like the SpendButton beside
            it. A real `disabled` drew this one solid on white and that one
            dashed on clear - the same row, two held looks, by accident. */}
        <SecondaryButton className="act-sweep"
                busy={busy === "sweep"}
                why={noRecheck ?? (busy === "brief" ? "the analysis is running" : null)}
                onClick={onRecheck}>
          {/* Item 183: the part's name, and how many other parts the same checks
              re-check - "Re-check TEC" on Crawl, Indexability and URLs re-checked
              all three and said none of them. The engine code is gone. */}
          {`Re-check ${part.label}${(part.refresh?.also ?? []).length
            ? ` + ${(part.refresh?.also ?? []).length} other part${(part.refresh?.also ?? []).length === 1 ? "" : "s"}` : ""} · ${scope} · free`}
          {/* The time only where the press has a page set to spend it on
              (audit F17's second half). `estSeconds` is the record's page
              count times the per-page rate, and in site mode this button
              starts a fresh adaptive audit that has not chosen its pages: on
              twenty22's one-page T1 "~2s" is true by accident, and on Acme
              it would promise a fraction of what the press costs. "free" is
              true either way - no model runs - so it stays. */}
          {page && estSeconds !== null ? ` · ${humanEst(estSeconds)}` : ""}
        </SecondaryButton>
        {/* Item 178: held with its reason in text, priced in words, and
            confirmed. "Run" until an analysis has run on this part: "Re-run"
            over "no analysis has run on this part" named a result that did not
            exist (05-2, 07-11). */}
        {part.catalogued === false && !brief ? (
          // Item 279 (row 8): no analysis is catalogued for this part, so a
          // disabled paid button offered a spend that cannot exist.
          <span className="muted">{briefNote ?? "no analysis writes to this part"}</span>
        ) : (
        <SpendButton className="act-brief" price={estCost}
                     busy={busy === "brief"}
                     // Item 274 (row 6): the brief has changed since the analysis
                     // shown was written; the heading says so, and so does the
                     // control that would apply the change.
                     title={brief?.brief_changed
                       ? "The brief has changed since this analysis was written: a re-run applies it"
                       : undefined}
                     why={briefNote ?? (gated ? gatedWhy
                       : busy === "sweep" ? "the automatic checks are starting" : null)}
                     confirm={{ title: `${brief ? "Re-run" : "Run"} the ${tool ?? part.label} analysis?`,
                                body: <><SpendTarget page={page ? pathOf(page) : null}
                                                     pages={page ? null : pages} />
                                  <p>{brief
                                    ? "It replaces the analysis stored for this part."
                                      + (brief.brief_changed
                                        ? " The brief has changed since that analysis was written, and this run applies it."
                                        : "")
                                    : gated ? "The locale check found this analysis does not apply."
                                    : "Nothing has analysed this part on this audit yet."}</p></>,
                                action: `${brief ? "Re-run" : "Run"} the analysis` }}
                     onSpend={onRerun}>
          {`${brief ? "Re-run" : "Run"} ${tool ? `${tool} analysis` : "analysis"} · ${briefScope}`}
        </SpendButton>
        )}
        {(estRuns || rereads || lastCost != null) && (
          <span className="muted">
            {estRuns ? ` median of ${estRuns} run${estRuns === 1 ? "" : "s"}` : ""}
            {lastCost != null ? " what the last run here cost" : ""}
            {rereads ? `${estRuns || lastCost != null ? " ·" : ""} re-reads ${rereads.rows} row${rereads.rows === 1 ? "" : "s"}`
              + ` · ${rereads.raised} on pages the automatic checks still raise` : ""}
          </span>
        )}
        {others.length > 0 && (
          <span className="muted">
            {" "}Also writing here: {others.join(", ")} - run from{" "}
            {othersHref
              ? <a href={othersHref} onClick={goHandler(othersHref)}>the Analyses list</a>
              : "the Analyses list"}.
          </span>
        )}
        <span className="muted act-busy" role="status" aria-live="polite">
          {/* Keyed, so going from one wait straight to the other starts
              the clock again rather than carrying the first one's. */}
          {busy === "sweep" ? <Working key="sweep">Starting the automatic checks…</Working>
            : busy === "brief" ? <Working key="brief">Running the analysis — this spends model tokens…</Working>
            : ""}
        </span>
      </div>
      {/* Under the buttons and inside the actions block, which is where item
          178 put a control's reason: beside the control it belongs to, not in
          a second region the reader has to connect to it. */}
      {recheckConfirm}
      <div className="part-prov">
        {sweep && dim && (
          <span className="prov-line">
            <i className="prov-dot prov-sweep" aria-hidden="true" />
            {" "}automatic checks {when(sweep.at)} · {sweep.tier} · {dim}
            {/* Item 239 step 6: its age, in its tone, and the re-check beside
                it once it may be out of date. */}
            {/* Item 243: a page that has left the site keeps its last reading
                and says when it was last seen, not how old the crawl is - a
                re-check would not fetch it, so none is offered. */}
            {part.gone_since
              ? <>{" · "}<span className="age age-gone" data-age="gone">
                  not seen since {dayOf(part.gone_since)}</span></>
              : <>{" · "}<MeasuredAge iso={sweep.at} th={part.age_thresholds} onRecheck={onRecheck} /></>}
          </span>
        )}
        {part.gone_since && (
          <span className="prov-line prov-gone muted">
            This page has left the site: the crawl of {dayOf(sweep?.at ?? "")} did not
            fetch it and the sitemap no longer lists it. What is shown is its last
            reading, from {dayOf(part.gone_since)}. Its findings keep their states.
          </span>
        )}
        {/* Rule 3: a part whose items were measured on different days says
            its range, and how many pages were re-checked since its crawl. */}
        {/* Item 274 (row 5): and where any card was measured on a day
            other than the automatic checks' own, which the range read from
            the record's items did not see (13 cards, 12 counted). */}
        {(() => {
          const differ = sweep?.at ? cardDates.some((d) => day(d) !== day(sweep.at)) : false;
          return part.measured_range && (day(part.measured_range.from) !== day(part.measured_range.to)
                                         || part.measured_range.rechecked_pages > 0) || differ;
        })() && (
          <span className="prov-line prov-range muted">
            Measured {dayOf([part.measured_range?.from, sweep?.at, ...cardDates]
                              .filter((d): d is string => Boolean(d)).sort()[0] ?? "")} to{" "}
            {dayOf([part.measured_range?.to, sweep?.at, ...cardDates]
                     .filter((d): d is string => Boolean(d)).sort().slice(-1)[0] ?? "")}
            {part.measured_range && part.measured_range.rechecked_pages > 0
              ? ` · ${part.measured_range.rechecked_pages === 1 ? "one page"
                  : `${part.measured_range.rechecked_pages} pages`} re-checked ${dayOf(part.measured_range.rechecked_at)}`
              : ""}
          </span>
        )}
        {brief ? (
          <span className="prov-line">
            <i className="prov-dot prov-brief" aria-hidden="true" />
            {" "}analysis {brief.tool} {when(brief.at)}
            {/* Item 267 (row 15): what it read is the crawl, so the age is the
                crawl's - "read the crawl of 18 Sept, measured 13 days ago" -
                where the analysis says which crawl that was. */}
            {brief.crawl_at
              ? <>{" · "}read the crawl of {dayOf(brief.crawl_at)},{" "}
                  <MeasuredAge iso={brief.crawl_at} th={part.age_thresholds} /></>
              : <>{" · "}<MeasuredAge iso={brief.at} th={part.age_thresholds} /></>}
            {brief.model ? ` · ${brief.model}` : ""}
            {/* Item 209: the accounting once, where the price is read. "10
                rows · USD 0.47" over a run that returned 29 hid that two
                thirds of what was paid for was refused. */}
            {(part.brief_runs?.length ?? 0) > 1 ? (
              // Item 269 (row 4): several analyses write to this part. Each
              // is its own line below, and this one names them and sums
              // what they cost; a count across tools is no run's count.
              <>
                {" · "}{part.brief_runs!.length} analyses: {part.brief_runs!.map((b) => b.tool).join(", ")}
                {part.brief_runs!.some((b) => b.cost != null)
                  ? ` · ${money(part.brief_runs!.reduce((s, b) => s + (b.cost ?? 0), 0))} in all` : ""}
              </>
            ) : (
              <>
                {brief.rows != null
                  ? ((part.brief_dropped ?? 0) > 0
                      ? ` · ${brief.rows + (part.brief_dropped ?? 0)} rows returned · ${brief.rows} kept`
                        + ` · ${part.brief_dropped} dropped`
                      : ` · ${brief.rows} row${brief.rows === 1 ? "" : "s"}`)
                  : ""}
                {/* Items 277 (row 9), 273 (row 8): the holds, so the
                    provenance and the accounting under the cards are one
                    arithmetic. */}
                {(() => {
                  // In checks, as the accounting says them (item 276, row 3).
                  const n = new Set((part.brief_held ?? []).map((h) => h.check.split("/").pop())).size;
                  return n > 0 ? ` · ${n} check${n === 1 ? "" : "s"} held` : "";
                })()}
                {brief.cost != null ? ` · ${money(brief.cost)}` : ""}
              </>
            )}
          </span>
        ) : (
          <span className="prov-line muted">
            {gated ? "analysis not applicable: this site presents one locale"
              : "no analysis has run on this part"}
          </span>
        )}
      </div>
      {(part.brief_runs?.length ?? 0) > 1 && (
        <ul className="prov-runs muted">
          {part.brief_runs!.map((b) => (
            <li key={b.tool}>
              analysis {b.tool} · {stamp(b.at)}
              {(b.audits_since ?? 0) > 0
                ? ` · ${b.audits_since} audit${b.audits_since === 1 ? "" : "s"} since` : ""}
              {b.crawl_at ? ` · read the crawl of ${stamp(b.crawl_at)}` : ""}
              {b.model ? ` · ${b.model}` : ""}
              {` · ${b.rows + b.dropped} rows returned · ${b.rows} kept · ${b.dropped} dropped`}
              {b.cost != null ? ` · ${money(b.cost)}` : ""}
            </li>
          ))}
        </ul>
      )}
      {/* The reason is beside the control it holds (item 178), not a second
          copy under the provenance. */}
    </div>
  );
}

/** A reading of one string: what it is, and whether it passes. A held
 *  check is neutral — never a failure, because nothing was measured. */
function Badge({ kind, children }: { kind: "pass" | "fail" | "held"; children: ReactNode }) {
  return <span className={`str-badge str-${kind}`}>{children}</span>;
}

/** A length badge graded as the check grades it (item 273, row 3): pixels
 *  against the cut at the viewport the check fires at, characters against
 *  the minimum. A character range said "in range" over a 561 px title the
 *  check had raised. */
export function lengthGrade(f: SnippetField): { pass: boolean; says: string } {
  const v = fired(f);
  const chars = f.chars ?? (f.text ?? "").length;
  if (f.min_chars && chars < f.min_chars) {
    return { pass: false, says: `${chars} chars · under ${f.min_chars}` };
  }
  const where = f.fires === "mobile" ? "mobile" : "desktop";
  return v.state === "ok" || v.state === "mute"
    ? { pass: true, says: `${Math.round(f.px)} px · fits the ${v.limit_px} px cut on ${where}` }
    : { pass: false, says: `${Math.round(f.px)} px · cut at ${v.limit_px} px on ${where}` };
}

/** Block 2, Title & description's renderer: the page's own strings, with
 *  a plain result preview so a 272-character description is visible
 *  rather than stated. */
function TitleDescNow({ facts, part, bounds, fixes = [] }: {
  facts: Facts; part: Category; bounds: Bounds; fixes?: Fix[];
}) {
  // Part B's desktop/mobile toggle. Pure display: the string's pixel width
  // is fixed and the payload carries both cut lines, so a press switches
  // which limit applies without a re-fetch. Default desktop, per the item.
  // null until the operator toggles: the card then opens on the viewport the
  // title check fires at (item 152), so the first view is the finding's.
  const [snippetToggle, setSnippetMobile] = useState<boolean | null>(null);
  const held = (checkId: string) =>
    (part.brief_held ?? []).find((h) => h.check.split("/").pop() === checkId);
  const title = facts.title ?? "";
  const desc = facts.meta_description ?? "";
  const canonical = facts.canonical ?? "";
  const inRange = (n: number, lo: number, hi: number) => n >= lo && n <= hi;
  // Item 273 (row 13): said once. Where the hold has its own card below,
  // the badge here repeated it 55 lines apart.
  const titleHeld = fixes.some((f) => f.checkId === "title-entity-alignment" && f.needs)
    ? undefined : held("title-entity-alignment");
  const cut = desc.length > bounds.descMax ? desc.slice(0, bounds.descMax) + " …" : desc;
  return (
    <Card className="now-card">
      <h3>What the page has now</h3>
      <dl className="now-strings">
        <dt>Title</dt>
        <dd>
          {title ? <span className="now-str">{title}</span>
                 : <span className="muted">no title</span>}
          <div className="now-badges">
            {title && facts.snippet?.title && (() => {
              const g = lengthGrade(facts.snippet.title);
              return <Badge kind={g.pass ? "pass" : "fail"}>{g.says}</Badge>;
            })()}
            {title && !facts.snippet?.title && (
              <Badge kind={inRange(title.length, bounds.titleMin, bounds.titleMax) ? "pass" : "fail"}>
                {title.length} chars ·{" "}
                {inRange(title.length, bounds.titleMin, bounds.titleMax)
                  ? "in range" : `outside ${bounds.titleMin}–${bounds.titleMax}`}
              </Badge>
            )}
            {titleHeld && (
              <Badge kind="held">
                {titleHeld.check.split("/").pop()} not checked — {titleHeld.needs}
              </Badge>
            )}
          </div>
        </dd>
        <dt>Description</dt>
        <dd>
          {desc ? <span className="now-str">{desc}</span>
                : <span className="muted">no description</span>}
          <div className="now-badges">
            {desc && facts.snippet?.description && (() => {
              const g = lengthGrade(facts.snippet.description);
              return <Badge kind={g.pass ? "pass" : "fail"}>{g.says}</Badge>;
            })()}
            {desc && !facts.snippet?.description && (
              <Badge kind={inRange(desc.length, bounds.descMin, bounds.descMax) ? "pass" : "fail"}>
                {desc.length} chars ·{" "}
                {inRange(desc.length, bounds.descMin, bounds.descMax)
                  ? "in range" : `outside ${bounds.descMin}–${bounds.descMax}`}
              </Badge>
            )}
          </div>
        </dd>
        <dt>Canonical</dt>
        <dd>
          {canonical ? <span className="now-str now-mono">{canonical}</span>
                     : <span className="muted">none</span>}
          <div className="now-badges">
            {canonical && (
              <Badge kind={pathOf(canonical) === pathOf(facts.url) ? "pass" : "fail"}>
                {pathOf(canonical) === pathOf(facts.url) ? "self" : "points elsewhere"}
              </Badge>
            )}
          </div>
        </dd>
      </dl>
      {facts.snippet
        ? <SnippetCard snippet={facts.snippet}
                       mobile={snippetToggle ?? facts.snippet.title.fires === "mobile"}
                       byRule={snippetToggle === null
                               && facts.snippet.title.fires === "mobile"}
                       host={(() => { try { return new URL(facts.url).host; }
                                      catch { return facts.url; } })()}
                       onToggle={setSnippetMobile} />
        : <p className="muted now-note">
            This audit measured lengths in characters. A re-check measures the
            snippet in pixels, as a result will cut it.
          </p>}
    </Card>
  );
}

/** Block 3, Title & description's fix body: the string as it stands,
 *  struck, and the copy that replaces it. */
function TitleDescFixBody({ fix, facts }: { fix: Fix; facts: Facts | null }) {
  const now = fix.checkId.startsWith("meta-desc") ? facts?.meta_description
            : fix.checkId.startsWith("title") ? facts?.title : null;
  // Item 273 (row 4): on the site view the page's own string comes from the
  // finding; the engine's sentence goes under it, and the string is struck
  // only where a replacement stands under it.
  const current = now || fix.said || null;
  const sentence = fix.current && fix.current !== current ? fix.current : null;
  const keep = isKeep(fix);
  return (
    <>
      <p className="fix-now">
        <span className="fix-lbl">Now</span>
        {current
          ? (fix.replacement && !keep ? <s>{current}</s> : <span>{current}</span>)
          : <span className="muted">{sentence ? "" : "nothing on the page"}</span>}
        {/* Item 273 (row 5): the overage and the length on each card. */}
        {fix.overPx != null && current
          ? <span className="muted fix-meta"> {Math.round(fix.overPx)} px over · {current.length} chars</span>
          : null}
      </p>
      {sentence && <p className="muted fix-meta">{sentence}</p>}
      {fix.replacement && keep && (
        <p className="fix-new muted">The analysis keeps the text as it is: no change.</p>
      )}
      {fix.replacement && !keep && (
        <p className="fix-new">
          <span className="fix-lbl">Replace with</span>
          <span className="fix-rep">{fix.replacement}</span>
          <span className="muted fix-meta">
            {" "}{fix.replacement.length} chars · analysis
          </span>
        </p>
      )}
    </>
  );
}

/** Block 2, Headings' renderer: the outline as the parser saw it, one
 *  line per heading, indented by level, with each problem tagged on its
 *  own line.
 *
 *  The structural tags are read off the outline itself - a level that
 *  jumps, a second h1 - because those are properties of the document and
 *  the block's promise is to show what the parser saw. The judgement tags
 *  are gated on a row for that check being open on this page, so the
 *  screen never grades something the engine did not. */
function HeadingsNow({ facts, fixes }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[];
}) {
  const model = facts.heading_outline ?? null;
  const kept = facts.outline?.length ?? facts.headings?.length ?? 0;
  /** Open the record's card for a check, from a rung of the ladder. By check
   *  and not by number: this part has no graph and no `fix-N` anchors, so
   *  `data-fix-check` on every card's head is the join. The scroll follows the
   *  tree's one convention — `{ block: "center" }`, no `behavior`. */
  const openCheck = (checkId: string) => {
    document.querySelector(`[data-fix-check="${checkId}"]`)
      ?.scrollIntoView({ block: "center" });
  };
  const carded = new Set(fixes.map((f) => f.checkId));
  return (
    <Card className="now-card ho-now">
      <h4>What the page has now</h4>
      {/* The outline as a drawn ladder, gaps where the skipped levels should
          have been (brief v16d Block 1). Every rung's state is the engine's —
          `onp.heading_outline_state`, the function the checks call — so the
          drawing and the record cannot grade this page differently.

          The tagged list that stood beneath it (brief v14 step AP) is retired
          (Q-51, operator 2026-09-07): it was a second outline of the same page
          on the same card, the thing 136e said not to do. The skips and the
          second H1 it tagged are on the ladder itself; the per-heading
          judgements it carried (a question with no answer, a title-copying
          H1, an unchecked triple) are on the Free-checks table and their fix
          cards. And the ladder reads the outline function directly, so it
          never needed the recorded position F-07 took from the finding — which
          is why F-07's rule is moot here rather than merely dropped. */}
      <OutlineLadder outline={model} path={pathOf(facts.url)}
                     onCheck={openCheck} checks={carded} />
      {/* UX-60, re-pointed from the retired list to the ladder: the crawl's
          own storage limit is a stated limitation, and it reads the same
          however much of the outline stands. The ladder shows only the
          headings the crawl kept, so the fact holds for it too. */}
      {(facts.heading_total ?? 0) > kept && (
        <p className="muted not-kept">
          This crawl kept {kept} of the {facts.heading_total} headings on this
          page. The other {(facts.heading_total ?? 0) - kept} are not on the
          outline above, whatever it shows.
        </p>
      )}
      <p className="muted now-note">
        Document order and level as the parser saw them; main region{" "}
        {facts.main_region ? <code>{facts.main_region}</code> : "not recorded on this crawl"}.
        Styling is not evidence.
      </p>
    </Card>
  );
}

/** Block 3, Headings' fix body: the affected lines before and after.
 *
 *  A brief answers a heading row with the whole corrected outline, so the
 *  card diffs it against what the parser saw and shows only what moves,
 *  with one line of context above. `copy outline` copies the brief's
 *  answer whole - the card is a reading of it, not a substitute. */
function HeadingsFixBody({ fix, facts }: { fix: Fix; facts: Facts | null }) {
  // The whole outline the crawl kept, because a diff that cannot see a
  // line reports it as removed.
  // Item 224: at site scope the baseline is the outline the site view carried
  // for this card's page. With none, there is nothing to diff against, so the
  // card draws no "Now" and marks nothing - every line read `[proposed]`,
  // headings the page already has included.
  const base = facts ?? (fix.baseline as Facts | null | undefined) ?? null;
  const before = base ? outlineOf(base, OUTLINE_KEPT) : [];
  const after = parseOutline(fix.replacement);
  if (!base && after.length) {
    return (
      <>
        {fix.current && <p className="fix-why">{fix.current}</p>}
        <p className="muted fix-baseline-none">
          The page's current outline is not loaded here, so what changes is not
          marked. Open the page to see the difference.
        </p>
        <p className="fix-new"><span className="fix-lbl">Replace with</span></p>
        <ol className="outline outline-now">
          {after.map((line, i) => (
            <li key={`now-${i}`} className="out-line"
                style={{ marginLeft: `${(line.level - 1) * 1.1}rem` }}>
              <code className="out-lvl">H{line.level}</code>{" "}
              <span className="out-text">{line.text}</span>
            </li>
          ))}
        </ol>
      </>
    );
  }
  if (!after.length) {
    return (
      <p className="fix-now">
        <span className="fix-lbl">Now</span>
        <span className="muted">{fix.current || "the outline as it stands"}</span>
      </p>
    );
  }
  // The first line of each spelling (screen audits round 3, headings AC-03):
  // last-wins matched a typo fix to a later duplicate.
  const byText = new Map<string, { line: Line; i: number }>();
  before.forEach((l, i) => { if (!byText.has(norm(l.text))) byText.set(norm(l.text), { line: l, i }); });
  /** What happened to one line of the corrected outline, in a word.
   *  Screen audits round 3 (headings AC-03): a line the key matches differs
   *  at most in case, spacing or an apostrophe, which is how a heading is
   *  written and not a change - 263 "reworded" marks on one page were letter
   *  case. `[proposed]` is the model's own flag, for a heading where none
   *  stands; any other line without a match is a rewording. */
  const change = (line: Line): string | null => {
    const was = byText.get(norm(line.text));
    if (!was) return line.proposed ? "[proposed]" : "reworded";
    if (was.line.level === line.level) return null;
    if (was.line.level === 1 && fix.checkId === "h1-multiple") {
      return "demoted; the subject stays as h1";
    }
    if (fix.checkId === "h1-title-verbatim") return "restates the entity; not the title string";
    return `relevelled h${was.line.level} → h${line.level}`;
  };
  const marks = after.map(change);
  /** The lines that move, each with one line of context above. */
  const keep = new Set<number>();
  marks.forEach((m, i) => { if (m) { keep.add(i); if (i > 0) keep.add(i - 1); } });
  const shown = after.map((line, i) => ({ line, mark: marks[i], i }))
                     .filter(({ i }) => keep.has(i));
  // Item 268. "Now" is the page as it stands, so it is drawn from `before`
  // in document order. It was the corrected outline's matched lines in the
  // corrected outline's order, then the cut lines after them, so on
  // /contact-us/ an H1 read below the H2 and H3 it heads and the H3 that
  // skipped a level was not marked at all.
  //
  // A line is struck where the corrected outline does not carry it at its
  // level - unless it sits outside the main region, which a brief rewriting
  // the page's own outline never claims to touch: striking the site's
  // navigation would read as "delete this heading". On a level-skip card
  // the heading that skipped is marked, by the engine's rule (a level more
  // than one below the heading before it, `onp.heading_outline_state`).
  const carried = new Map(after.map((l) => [norm(l.text), l]));
  const skipCard = fix.checkId === "heading-skip";
  const was = before.map((l, i) => {
    const now = carried.get(norm(l.text));
    return {
      line: l, i,
      struck: now ? now.level !== l.level : l.inMain !== false,
      skipped: skipCard && i > 0 && l.level > before[i - 1].level + 1,
    };
  });
  // The lines that change, one line of context above each, and the line a
  // proposed heading would follow - still in the page's order.
  const keepWas = new Set<number>();
  was.forEach(({ struck, skipped }, i) => {
    if (struck || skipped) { keepWas.add(i); if (i > 0) keepWas.add(i - 1); }
  });
  marks.forEach((m, i) => {
    if (m !== "[proposed]" || i === 0) return;
    const above = byText.get(norm(after[i - 1].text));
    if (above) keepWas.add(above.i);
  });
  const stub = fix.checkId === "h2-question-unanswered";
  // Item 268 (row 4): which crawl "Now" is. The analysis may have read an
  // older one, and a diff against a page that has since changed reads as a
  // change nobody asked for.
  const readAt = facts ? (facts.dated?.outline ?? facts.captured_at)
                       : (fix.baseline as { captured_at?: string | null } | null)?.captured_at;
  return (
    <>
      {/* Item 268 (row 3): the analysis's evidence above the diff, as the
          no-outline branches draw it. Ten of twelve cards carried an outline
          and so showed none: "Redundant h2s" struck three H3s and never named
          an h2. */}
      {fix.current && <p className="fix-why">{fix.current}</p>}
      <p className="fix-now">
        <span className="fix-lbl">Now</span>
        {readAt && <span className="muted fix-meta"> · crawl of {day(readAt)}</span>}
      </p>
      <ol className="outline outline-was">
        {was.filter(({ i }) => keepWas.has(i)).map(({ line, i, struck, skipped }) => (
          <li key={`was-${i}`}
              className={`out-line${struck ? " out-struck" : ""}${skipped ? " out-skip" : ""}`}
              style={{ marginLeft: `${(line.level - 1) * 1.1}rem` }}>
            <code className="out-lvl">H{line.level}</code>{" "}
            <span className="out-text">{line.text}</span>
            {skipped && <span className="out-tag out-skipped">skipped a level</span>}
          </li>
        ))}
      </ol>
      <p className="fix-new">
        <span className="fix-lbl">Replace with</span>
      </p>
      <ol className="outline outline-now">
        {shown.map(({ line, mark, i }) => (
          <li key={`now-${i}`} className={`out-line${mark ? " out-new" : ""}`}
              style={{ marginLeft: `${(line.level - 1) * 1.1}rem` }}>
            <code className="out-lvl">H{line.level}</code>{" "}
            <span className="out-text">{line.text}</span>
            {line.link && (
              <span className={`out-link${line.link.startsWith("[") ? " out-bad" : ""}`}>
                {" → "}{line.link}
              </span>
            )}
            {mark && <span className="out-tag out-mark">{mark}</span>}
            {stub && line.text.trim().endsWith("?") && line.next && (
              <div className="out-stub"><i>[answer stub] {line.next}</i></div>
            )}
          </li>
        ))}
      </ol>
      <p className="muted fix-meta">
        {after.length} line{after.length === 1 ? "" : "s"} in the corrected outline · analysis
      </p>
    </>
  );
}

/** One band of the grid: the cards, and nothing about which band it is.
 *
 *  Split out at brief v16 step AU3, when the header and the footer became
 *  collapsed rows around the body's grid. They render the same card the
 *  body does - a card that looked different inside a `<details>` would be a
 *  second answer to what an image is, and the reason the furniture is
 *  folded away is that there is a lot of it, not that it is different.
 */
function ImageBand({ facts, band, cap, problems }: {
  facts: Facts; band: "header" | "body" | "footer"; cap: number;
  problems: (src: string) => { key: string; checkId: string; needs?: string }[];
}) {
  // The one place cards are made is the one place the inventory is read,
  // and the cap sits between the field and the map on both branches - the
  // bound the real-data-scale invariant looks for, and the place a reader
  // of this line would look for it. The second branch is the fallback a
  // run crawled before brief v15 needs, which recorded `[src, alt]` and
  // nothing else; every measured field is absent on it, which is what each
  // line below already says when a browser did not measure.
  //
  // Both branches settle `alt` to `string | null`, so a card never has to
  // tell an absent field from a null one to know which of the three things
  // an alt attribute can be it is looking at.
  const inventory: ImageRecord[] = facts.image_inventory?.length
    ? facts.image_inventory.slice(0, cap).map((r) => ({ ...r, alt: r.alt ?? null }))
    : (facts.images ?? []).slice(0, cap).map(([src, alt]) => ({ src, alt }));
  // The logo first inside its band (AU6): it is the one image in the
  // header an operator is looking for, and the icons around it are the
  // reason the band is folded away at all.
  const images = inventory.filter((i) => (i.region_class ?? "body") === band)
    .sort((a, b) => Number(Boolean(b.is_logo)) - Number(Boolean(a.is_logo)));
  const altOf = (i: ImageRecord) =>
    i.alt === null ? "alt missing" : i.alt === "" ? 'alt=""' : `alt="${i.alt}"`;
  return (
    <div className={`img-grid img-grid-${band}`}>
      {images.map((i, n) => {
        const rendered = Object.entries(i.rendered ?? {})
          .sort((a, b) => Number(a[0]) - Number(b[0]));
        const widest = rendered.length ? rendered[rendered.length - 1][1][0] : null;
        return (
          <div key={`${fileSrc(i)}-${n}`} className="img-card">
            {/* The picture, not a name for it. Constrained rather than
                sized: an image that renders at 1920 must not lay this
                grid out at 1920. */}
            <img className="img-thumb" src={fileSrc(i)} alt="" loading="lazy" />
            <div className="img-facts">
              <code className="img-name">{fileOf(fileSrc(i))}</code>
              {/* What this image is to the site, before what it is as a
                  file (AU3, AU6). `template` is why one fix card can say
                  "fixes 12 pages"; `logo` is the one header image that
                  carries meaning rather than decoration. */}
              {(i.is_logo || i.template) && (
                <div className="img-chips">
                  {i.is_logo && <span className="chip img-chip-logo">logo</span>}
                  {i.template && <span className="chip img-chip-template">template</span>}
                </div>
              )}
              <div className="muted img-line">
                {formatOf(fileSrc(i)) || "no extension"}
                {i.weight_kb != null ? ` · ${i.weight_kb} KB` : " · weight not measured"}
                {/* The saving, and only where it was taken (AU7). A ratio
                    would be an estimate wearing a measurement's clothes,
                    and this number is the one an operator acts on.
                    Two things read as savings and are not, both seen on
                    Birch's home page: a re-encode with no measured weight
                    beside it has nothing to be a saving *from*, and a
                    re-encode that comes out larger is a measurement that
                    the file is already right. Neither gets an arrow. */}
                {i.measured_kb != null && i.weight_kb != null
                  ? (i.measured_kb < i.weight_kb
                     ? ` → ${i.measured_kb} KB · ${i.encoder} (measured)`
                     : ` · re-encoding saves nothing here (${i.encoder}, measured)`)
                  : i.reencode_error ? ` · saving not measured: ${i.reencode_error}` : ""}
              </div>
              <div className="muted img-line">
                {i.intrinsic_w ? `${i.intrinsic_w}×${i.intrinsic_h} intrinsic`
                               : "intrinsic not measured"}
                {widest ? ` · renders at ${widest}px` : " · rendered width not measured"}
              </div>
              <div className="muted img-line">
                {i.region || "body"}
                {/* Where the page declared no landmark and the measurement
                    decided, the line says so rather than reading as
                    something the markup stated. */}
                {i.region_from === "position" ? " (by position)" : ""}
                {i.above_fold == null ? " · fold not measured"
                  : i.above_fold ? " · above the fold" : " · below the fold"}
                {i.lcp_candidate == null ? " · paint not measured"
                  : i.lcp_candidate ? " · largest paint" : ""}
              </div>
              {i.linked_to && (
                <div className="muted img-line">links to <code>{i.linked_to}</code></div>
              )}
              <div className={`img-alt${i.alt ? "" : " img-alt-none"}`}>{altOf(i)}</div>
              <div className="img-tags">
                {problems(i.src).map((f) => (
                  <span key={f.key}
                        className={`out-tag ${f.needs ? "out-held" : "out-bad"}`}>
                    {f.needs ? `${plainName(f.checkId)} — held` : plainName(f.checkId)}
                  </span>
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** How many pages a band's template images are the same on, as the record
 *  says rather than as the grid guesses.
 *
 *  Read off the fix rows, because they are what the engine folded: a
 *  template image's finding carries every page it appears on, and this is
 *  that number rather than a second count of it. Zero where no fix on the
 *  band names a page count, and the row then says nothing about pages -
 *  which is the honest answer when nothing has been raised on the
 *  furniture at all.
 */
function bandPages(fixes: Fix[], images: ImageRecord[]): number {
  const mine = images.map((i) => i.src);
  return Math.max(0, ...fixes
    .filter((f) => f.image && mine.some((s) => sameImage(f.image, s)))
    .map((f) => f.pages ?? 0));
}

/** Block 2, Images' renderer: one card per image-bearing surface, with
 *  what the crawl read and what the browser measured.
 *
 *  The thumbnail is the image itself, constrained: a filename is not a
 *  picture, and the operator is being asked which picture to change. Every
 *  measured field says so where a number exists and says nothing where
 *  none was taken - the two never read alike, which is the whole reason
 *  the browser pass was worth adding.
 */
function ImagesNow({ facts, fixes }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[];
}) {
  const [allImages, setAllImages] = useState(false);
  // The cap sits between the field and the map, which is the bound the
  // real-data-scale invariant looks for and the place a reader of this
  // line would look for it.
  const cap = allImages ? IMAGES_KEPT : IMAGES_SHOWN;
  // Two branches, written here rather than behind a helper, because both
  // scale invariants read the line the field is named on: the cap between
  // the field and the map is the bound clause one looks for, and the local
  // this binds is how clause two follows a filename cell three lines below
  // back to the crawl it came from.
  //
  // The second branch is the fallback `outlineOf` makes for headings and
  // for the same reason: a run crawled before brief v15 recorded `[src,
  // alt]` and nothing else, and a grid that read only the new field would
  // show those pages an empty card and call it "no images". Every measured
  // field is absent on that path, which is what each line of the card
  // already says when a browser did not measure. Both branches settle `alt`
  // to `string | null`, so a card never has to tell an absent field from a
  // null one to know which of the three things an alt attribute can be it
  // is looking at.
  const inventory: ImageRecord[] = facts.image_inventory?.length
    ? facts.image_inventory.slice(0, cap).map((r) => ({ ...r, alt: r.alt ?? null }))
    : (facts.images ?? []).slice(0, cap).map(([src, alt]) => ({ src, alt }));
  const kept = facts.image_inventory?.length || facts.images?.length || 0;
  /** Every problem on one image, including the ones a single
   *  replacement closes alongside its own check: the image has them, and
   *  a grid that named only the surviving row would under-report it. */
  const problems = (src: string) => {
    const mine = fixes.filter((f) => f.image && sameImage(f.image, src));
    const named = new Set(mine.map((f) => f.checkId));
    const also = mine.flatMap((f) => (f.alsoResolves ?? []).map((c) => c.split("/").pop() as string))
      .filter((c) => !named.has(c));
    return [...mine.map((f) => ({ key: f.key, checkId: f.checkId, needs: f.needs })),
            ...[...new Set(also)].map((c) => ({ key: `also-${src}-${c}`, checkId: c,
                                                needs: undefined as string | undefined }))];
  };
  const measured = inventory.some((i) => i.rendered);
  // What this page could give back, added up from the rows that were
  // actually re-encoded (AU7). Rows nobody measured are not in it and are
  // not guessed at, so the number understates rather than flatters - and
  // the sentence says as much where any row is missing its measurement.
  const weighed = inventory.filter(
    (i) => i.measured_kb != null && i.weight_kb != null && i.measured_kb < i.weight_kb);
  const recoverable = weighed.reduce((n, i) => n + (i.weight_kb! - i.measured_kb!), 0);
  const unweighed = inventory.filter(
    (i) => i.weight_kb != null && i.measured_kb == null).length;
  const widths = [...new Set(inventory.flatMap((i) => Object.keys(i.rendered ?? {})))]
    .map(Number).sort((a, b) => a - b);
  const inBand = (name: "header" | "body" | "footer") =>
    inventory.filter((i) => (i.region_class ?? "body") === name);
  const furniture = (name: "header" | "footer") => {
    const mine = inBand(name);
    // Omitted, not shown empty (AU3). A `Footer · 0 images` row is a
    // sentence about nothing, and a page carrying three of them looks like
    // one that failed to load.
    if (!mine.length) return null;
    const faults = mine.reduce((n, i) => n + problems(i.src).length, 0);
    const pages = bandPages(fixes, mine);
    return (
      <details className={`img-band img-band-${name}`}>
        <summary>
          <b>{name === "header" ? "Header" : "Footer"}</b>
          {` · ${mine.length} image${mine.length === 1 ? "" : "s"}`}
          {` · ${faults} problem${faults === 1 ? "" : "s"}`}
          {pages > 1 ? ` · same on all ${pages} pages` : ""}
        </summary>
        <ImageBand facts={facts} band={name} cap={cap} problems={problems} />
      </details>
    );
  };
  return (
    <Card className="now-card">
      <h4>What the page has now</h4>
      {!inventory.length && (
        <p className="muted">
          This crawl recorded no images on the page. Re-check the part
          above to read it again.
        </p>
      )}
      {recoverable > 0 && (
        <p className="muted img-recoverable">
          <b>{(recoverable / 1024).toFixed(1)} MB recoverable</b> across {weighed.length}
          {" "}image{weighed.length === 1 ? "" : "s"}, measured by re-encoding each one.
          {unweighed > 0
            ? ` ${unweighed} more carry a weight nobody re-encoded, so they are not in this total.`
            : ""}
        </p>
      )}
      {/* The page's furniture folded above and below its content (AU3).
          One missing alt on a footer icon is one change, and it used to
          fill this grid ahead of the images the page is actually about. */}
      {furniture("header")}
      <ImageBand facts={facts} band="body" cap={cap} problems={problems} />
      {furniture("footer")}
      {kept > inventory.length && (
        <p className="out-more">
          <SecondaryButton onClick={() => setAllImages(true)}>
            show all {kept} images
          </SecondaryButton>
        </p>
      )}
      {/* The crawl's own limit, which is not a fact about what is shown
          (UX-60). It reads the same however much of the grid stands. */}
      {(facts.image_total ?? 0) > kept && (
        <p className="muted not-kept">
          This crawl kept {kept} of the {facts.image_total} images on this page.
          The other {(facts.image_total ?? 0) - kept} are not below, whatever
          this card shows.
        </p>
      )}
      <p className="muted now-note">
        Every <code>&lt;img&gt;</code> the crawl read on this page
        {measured
          ? `, measured in a browser at ${widths.join(", ")} pixels wide.`
          : ". No browser measured this page, so rendered width, weight, the "
            + "fold and the largest paint are not stated."}
        {" "}CSS background images and video posters are not inspected.
      </p>
    </Card>
  );
}

/** Whether two names point at the same file.
 *
 *  A brief writes the filename it was shown - `hero-banner.jpg` - and the
 *  inventory holds the URL the page served, which on a CDN carries a
 *  resize path and a query. Comparing the whole strings would match
 *  nothing on any site with an image pipeline, so the file at the end is
 *  what is compared, and an exact match still wins. */
export function sameImage(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  return a === b || fileOf(a).toLowerCase() === fileOf(b).toLowerCase();
}

/** The inventory record a row is about, matched as above. */
export function imageIn(inventory: ImageRecord[], name: string | null | undefined) {
  return inventory.find((i) => i.src === name)
      ?? inventory.find((i) => sameImage(i.src, name));
}

const formatOf = (src: string) => {
  const name = fileOf(src);
  return name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "";
};

/** One attribute of an image's markup, for the before-and-after panels. */
type Attr = { name: string; value: string };

/** The markup the crawl recorded, as attributes. Rebuilt from what was
 *  stored rather than kept as a string: the crawl keeps the attributes it
 *  read, and a panel showing a raw tag would be showing a thing the engine
 *  never held. */
export function attrsOf(record: ImageRecord | undefined): Attr[] {
  if (!record) return [];
  const pairs: [string, unknown][] = [
    ["src", record.src], ["alt", record.alt], ["width", record.width],
    ["height", record.height], ["loading", record.loading],
    ["fetchpriority", record.fetchpriority], ["decoding", record.decoding],
    ["srcset", record.srcset], ["sizes", record.sizes],
  ];
  return pairs.filter(([, v]) => v !== null && v !== undefined && v !== "")
              .map(([name, value]) => ({ name: String(name), value: String(value) }));
}

/** The attributes of a proposed `<img>`, out of the markup a brief wrote.
 *  Tolerant on purpose: a replacement may carry a `<picture>` or a preload
 *  line beside the tag, and what this needs is the one tag's attributes to
 *  line up against what is there now. */
export function attrsIn(markup: string | null): Attr[] {
  if (!markup) return [];
  const tag = /<img\b[^>]*>/i.exec(markup);
  if (!tag) return [];
  const out: Attr[] = [];
  const attr = /([a-zA-Z-]+)\s*=\s*"([^"]*)"/g;
  let hit = attr.exec(tag[0]);
  while (hit) {
    out.push({ name: hit[1].toLowerCase(), value: hit[2] });
    hit = attr.exec(tag[0]);
  }
  return out;
}

/** Block 3, Images' fix body: the markup as it stands and as proposed,
 *  attribute by attribute, so what changed is visible rather than stated. */
function ImagesFixBody({ fix, facts }: { fix: Fix; facts: Facts | null }) {
  const record = imageIn(facts?.image_inventory ?? [], fix.image);
  const before = attrsOf(record);
  const after = attrsIn(fix.replacement);
  const beforeBy = new Map(before.map((a) => [a.name, a.value]));
  const afterBy = new Map(after.map((a) => [a.name, a.value]));
  const rest = (fix.replacement || "").replace(/<img\b[^>]*>/i, "").trim();
  if (!after.length) {
    return (
      <p className="fix-now">
        <span className="fix-lbl">Now</span>
        <span className="muted">{fix.current || "the image as it stands"}</span>
      </p>
    );
  }
  return (
    <div className="img-diff">
      <div className="img-panel">
        <span className="fix-lbl">Now</span>
        {/* Item 272 (row 5): at site scope there is no page in hand, so no
            stored record of the image; the card says what the finding says
            rather than drawing an empty `<img>`. */}
        {!before.length ? (
          <p className="muted">{fix.current || fix.image || "the image as it stands"}</p>
        ) : (
        <pre className="md-code img-markup" tabIndex={0}><code>
          {"<img"}
          {before.map((a) => (
            <span key={a.name}
                  className={afterBy.get(a.name) === a.value ? undefined : "out-struck"}>
              {"\n  " + a.name + '="' + a.value + '"'}
            </span>
          ))}
          {"\n>"}
        </code></pre>
        )}
      </div>
      <div className="img-panel">
        <span className="fix-lbl">Replace with</span>
        <pre className="md-code img-markup" tabIndex={0}><code>
          {"<img"}
          {after.map((a) => (
            <span key={a.name}
                  className={beforeBy.get(a.name) === a.value ? undefined : "out-new"}>
              {"\n  " + a.name + '="' + a.value + '"'}
            </span>
          ))}
          {"\n>"}
          {rest ? "\n" + rest : ""}
        </code></pre>
      </div>
      {fix.note && <p className="muted img-note">{fix.note}</p>}
    </div>
  );
}

export type Bounds = { titleMin: number; titleMax: number; descMin: number; descMax: number };
export type SweepRun = { run_id: string; at: string; tier: string; dimensions: string[] };

type Renderer = {
  //: `page` since brief v16 step AT: the Structured data card names the
  //: page's own expected blocks, and which those are depends on which page
  //: it is. The renderers that do not need it ignore it.
  //: `glow` and `onFix` are the scroll-link's two halves (brief v16a step
  //: AT-b, taken from the designer's layout 2): the fixes block says which
  //: card is nearest the top, and the "now" block lights the node it is
  //: about. Only Structured data draws a graph, so every other renderer
  //: ignores both - they are optional rather than a second `now` signature
  //: because a part with no picture has nothing to light up.
  now: (p: { facts: Facts; part: Category; bounds: Bounds; fixes: Fix[];
             page: string; glow?: string | null;
             onFix?: (n: number) => void;
             /** A key the "now" block narrows the fix cards to, and the way
              *  to set it (item 143 step BD: a Security layer card). Parts
              *  that draw no narrowing control ignore both. */
             narrow?: string | null;
             onNarrow?: (key: string | null) => void;
             /** Open a page in scope, for a page block that names other
              *  pages (Indexability's chain, brief v25 step BP). */
             onPage?: (url: string) => void }) => JSX.Element;
  body: (p: { fix: Fix; facts: Facts | null }) => JSX.Element;
  /** Whether the "now" block answers a question about the SITE rather than
   *  about the page in scope.
   *
   *  The block below draws `now` only when a page is chosen, because most
   *  of these blocks read `facts` - one page's parse - and have nothing to
   *  say without one. A site-wide block is the other case and needs saying
   *  out loud: the response-headers grid is a claim about every route, and
   *  registering it without this flag put it behind a page filter it then
   *  correctly refused to draw under. It rendered nowhere at all on the
   *  running product, which is how this was found (item 136m step 1).
   */
  siteScope?: boolean;
  /** The part has no page-mode block (brief v23 step BK), so in page mode
   *  its "now" slot draws nothing.
   *
   *  BK's discipline: page mode is never site mode with rows hidden, and a
   *  part with nothing to draw in a mode draws nothing rather than a
   *  degraded version of the other. Mobile's and International's `now`
   *  blocks are site pictures - every template at 412 px, the locale gate
   *  and clusters - and were drawn unchanged under a chosen page. Their
   *  checks table and fixes still narrow to the page; only the picture is
   *  withheld until a page block is designed for them. */
  noPageBlock?: boolean;
  /** The checks table at page scope too (item 265): Speed's checks are read
   *  per traced page, so a page in hand has its own table under its trace. */
  pageChecks?: boolean;
  /** The part's site-wide picture, drawn inside the site-scope else-branch,
   *  immediately before the free-checks table (item 139a). Site-scope-only by
   *  construction: a page in scope takes the `now` path above, and this slot is
   *  never reached with a page in hand. Declaring it here makes the order -
   *  picture, then Free checks, then Fixes - structural rather than a
   *  `part.key === "..."` conditional each new part page has to re-add; 147
   *  (Mobile) and 148 (International) inherit it by declaring their own.
   *  Images is the deliberate exception and does NOT use this slot: it renders
   *  at both scopes and above `now` at page scope (see the images block), which
   *  a site-scope-only slot cannot express. */
  siteNow?: (p: { part: Category; page: string; pages: number | null;
                  /** The narrow in hand and its setter (brief v25 step BP):
                   *  a part whose picture carries a narrowing control writes
                   *  it here, and the layout narrows the checks and fixes
                   *  beneath once. */
                  narrow?: Narrow;
                  onNarrow?: (kind: NarrowKind, value: string | null) => void;
                  /** The populations a count may be counted over (item 155):
                   *  every block in this slot draws counts, and each renders
                   *  by the population rather than deciding for itself what
                   *  its number is a share of. */
                  pops?: Populations | null;
                  onPage?: (url: string) => void;
                  /** The site, and the re-read after a block edits its record
                   *  (International's target locales). */
                  siteId?: string; onChanged?: () => void }) => JSX.Element | null;
  /** What the part draws below Fixes at site scope (item 267, row 10: the
   *  AI surface Register, which is read after the fixes, not before). */
  siteFoot?: (p: { part: Category }) => JSX.Element | null;
  /** What the copy button copies, in the words of the thing copied. */
  copyLabel?: string;
  /** What a card offers to copy where it has no replacement (item 279,
   *  row 5: Accessibility's first selector); null for nothing. */
  copyFrom?: (fix: Fix) => string | null;
  /** Whether the card's replacement is one the body drew (item 272, row 5):
   *  Images drew "copy markup" on cards whose replacement held no `<img>`,
   *  so the operator copied text the card never showed. */
  copyWhen?: (fix: Fix) => boolean;
  /** What the copy button copies, where it is not the replacement verbatim
   *  (Headings: the parsed outline, item 268; AI surface: the payload the
   *  card shows, item 267). */
  copyText?: (replacement: string, fix: Fix) => string;
  /** Checks that cannot be judged without a list on the site record. One
   *  muted line naming the input, not a held card per page (brief v14
   *  step AP): the answer is the same on every page, and saying it twelve
   *  times says no more than saying it once. */
  na?: string[];
  /** Whether one replacement closing several checks is one card naming
   *  them all (brief v15 step AR). */
  collapse?: boolean;
};

/** The parts that render as three blocks. Everything else keeps the page
 *  it had; brief v14 adds `headings` with its own two renderers. */
/** What each page type is expected to carry, from the brief's own map. The
 *  engine holds the same table; this one exists to draw the dashed card for
 *  a type that is absent, which is a shape rather than a finding - the
 *  finding is `schema-missing-for-type` and it has its own row. */
const EXPECTED_BLOCKS: Record<string, string[]> = {
  home: ["Organization", "WebSite", "WebPage"],
  location: ["LocalBusiness", "BreadcrumbList"],
  service: ["Service", "WebPage", "BreadcrumbList"],
  blog: ["Article", "WebPage", "BreadcrumbList"],
  article: ["Article", "WebPage", "BreadcrumbList"],
  product: ["Product", "WebPage", "BreadcrumbList"],
  event: ["Event", "WebPage", "BreadcrumbList"],
};

/** What Google marks Required per type, so the property tree can mark an
 *  absent one in amber where the reader is looking rather than in a row
 *  they have to go and find. The engine's own table is the authority and
 *  raises the finding; this is the same list for the same reason the
 *  registry bounds are repeated on the Title & description card. */
const REQUIRED_PROPS: Record<string, string[]> = {
  Article: ["headline", "author", "datePublished", "image"],
  BlogPosting: ["headline", "author", "datePublished", "image"],
  NewsArticle: ["headline", "author", "datePublished", "image"],
  Product: ["name", "offers", "image"],
  Event: ["name", "startDate", "location"],
  Organization: ["name", "url", "logo"],
  LocalBusiness: ["name", "address", "telephone"],
  BreadcrumbList: ["itemListElement"],
};

/** How many properties of one block stand before the rest are folded. A
 *  node with forty properties is a node an operator scrolls past; the ones
 *  that matter are the required ones, and those are pulled to the top. */
const PROPS_SHOWN = 12;

/** Block 2, Structured data's renderer: one card per block as parsed, with
 *  the verdicts above them (brief v16 step AT).
 *
 *  The property tree shows values as stored, and marks in amber the
 *  properties this page's type requires and does not have. That is the
 *  same fact as a `schema-required-missing` row, and it is here as well
 *  because the row says which property is missing and the tree says where
 *  it would go - a reader deciding whether to act needs the second.
 */
function SchemaNow({ facts, part, page, fixes, glow, onFix }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
  glow?: string | null; onFix?: (n: number) => void;
}) {
  const [allProps, setAllProps] = useState<ReadonlySet<string>>(new Set());
  // Brief v16a step AT-b: where the engine built a graph, the picture *is*
  // the "now" block and the block cards below are what it replaces. They
  // stay reachable as the raw-JSON toggle inside the drill's properties
  // column, which is where a reader who wants the markup goes.
  //
  // Kept as a fallback rather than deleted, because the model is `null` on
  // every run crawled before `jsonld_raw` existed (ENGINE_VERSION 0.16.0).
  // A reader opening a September run would otherwise meet an empty panel
  // saying nothing, which reads as "this page has no markup" - a different
  // claim from "this run did not store it".
  const graph = part.graph ?? null;
  const blocks = (facts.schema_inventory ?? []).slice(0, SCHEMA_BLOCKS_SHOWN);
  const kept = (facts.schema_inventory ?? []).length;
  // The record keys page types by path and the reader does not carry the
  // map, so the home page is the one this card can name for itself - a
  // fact about the URL rather than an inference about content, and the
  // same reading the sweep makes.
  const pageType = pathOf(page) === "/" ? "home" : "";
  const present = new Set(blocks.map((b) => (b.type ?? "").split(",")[0].trim()));
  const absent = (EXPECTED_BLOCKS[pageType] ?? []).filter((t) => !present.has(t));
  const canonical = blocks.find((b) => b.id && /#(organization|org|business)\b/i.test(b.id))?.id
    ?? blocks.find((b) => b.id)?.id ?? null;
  const eligibility = (part.brief_eligibility ?? [])
    .filter((e) => !page || pathOf(e.page) === pathOf(page));
  const problems = (block: SchemaBlock, n: number) => {
    const ref = `${(block.type ?? "block").split(",")[0].trim()}#${n + 1}`;
    return fixes.filter((f) => f.block && f.block === ref);
  };
  if (graph) {
    return (
      <Card className="now-card sg-now">
        <h4>What the page has now</h4>
        <SchemaGraphView part={part} glow={glow ?? null}
                         onFix={onFix ?? (() => undefined)} />
      </Card>
    );
  }
  return (
    <Card className="now-card">
      <h4>What the page has now</h4>
      {/* A run crawled before the graph existed. The blocks as parsed, which
          is what this card drew before brief v16a step AT-b. */}
      <p className="muted sg-nograph">
        This audit stored the blocks as a flattened inventory and not as
        markup, so the picture cannot be drawn for it. Re-check the part to
        crawl the page again.
      </p>
      {/* The two verdicts, above the blocks: neither is a finding about a
          page, and putting them among the cards would make them read as
          one. */}
      {part.brief_entity && (
        <p className="sd-entity">
          <b>Entity: {part.brief_entity.verdict}</b>
          {" "}<span className="muted">(site-wide)</span>
          {part.brief_entity.reason ? ` — ${part.brief_entity.reason}` : ""}
        </p>
      )}
      {eligibility.length > 0 && (
        <ul className="sd-eligibility">
          {eligibility.map((e, i) => (
            <li key={`${e.rich_result}-${i}`}>
              <code>{e.rich_result}</code>: <b>{e.verdict}</b>
              {e.reason ? ` — ${e.reason}` : ""}
            </li>
          ))}
        </ul>
      )}
      {!blocks.length && (
        <p className="muted">
          This crawl found no JSON-LD on the page. Microdata and RDFa are not
          read, so markup in either is not evidence of none.
        </p>
      )}
      <div className="sd-blocks">
        {blocks.map((b, n) => {
          const type = (b.type ?? "").split(",")[0].trim();
          const props = Object.entries(b.properties ?? {})
            .filter(([k]) => !k.startsWith("@"));
          const required = REQUIRED_PROPS[type] ?? [];
          const missing = required.filter(
            (r) => !props.some(([k]) => k === r || k.startsWith(r + ".")));
          const open = allProps.has(`${type}-${n}`);
          const shown = open ? props : props.slice(0, PROPS_SHOWN);
          return (
            <div key={`${type}-${n}`} className="sd-card">
              <div className="sd-head">
                <code className="sd-type">{type || "untyped"}#{n + 1}</code>
                <span className="chip sd-source">{b.source}</span>
                {b.template && (
                  <span className="chip sd-template">
                    template{b.pages && b.pages > 1 ? ` · ${b.pages} pages` : ""}
                  </span>
                )}
                {b.parse_ok
                  ? <span className="pill sd-ok">valid JSON-LD</span>
                  : <span className="pill sd-bad">does not parse</span>}
                {b.parse_ok && !b.id && <span className="pill sd-bad">no @id</span>}
                {b.parse_ok && b.id && canonical && b.id !== canonical
                  && /Organization|LocalBusiness/.test(type)
                  && <span className="pill sd-bad">@id differs from canonical</span>}
              </div>
              {!b.parse_ok && <p className="muted sd-error">{b.error}</p>}
              {b.parse_ok && (
                <dl className="sd-props">
                  {shown.map(([k, v]) => (
                    <Fragment key={k}>
                      <dt><code>{k}</code></dt>
                      <dd>{String(v)}</dd>
                    </Fragment>
                  ))}
                  {/* Required and absent, in the tree rather than only in a
                      row: the row says which property is missing, and this
                      says where it would go. */}
                  {missing.map((r) => (
                    <Fragment key={`missing-${r}`}>
                      <dt className="sd-missing"><code>{r}</code></dt>
                      <dd className="sd-missing">required, and not here</dd>
                    </Fragment>
                  ))}
                </dl>
              )}
              {props.length > shown.length && (
                <p className="out-more">
                  <SecondaryButton
                          onClick={() => setAllProps(new Set([...allProps, `${type}-${n}`]))}>
                    show all {props.length} properties
                  </SecondaryButton>
                </p>
              )}
              <div className="img-tags">
                {problems(b, n).map((f) => (
                  <span key={f.key} className={`out-tag ${f.needs ? "out-held" : "out-bad"}`}>
                    {f.needs ? `${plainName(f.checkId)} — held` : plainName(f.checkId)}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
        {/* A type the page is expected to carry and does not: a shape
            rather than a finding, because the finding is
            `schema-missing-for-type` and it has its own row. */}
        {absent.map((t) => (
          <div key={`absent-${t}`} className="sd-card sd-absent">
            <div className="sd-head">
              <code className="sd-type">{t}</code>
              <span className="pill sd-bad">not on this page</span>
            </div>
            <p className="muted">
              A {pageType} page is expected to carry one.
            </p>
          </div>
        ))}
      </div>
      {kept > blocks.length && (
        <p className="muted not-kept">
          This crawl kept {blocks.length} of the {kept} blocks on this page.
        </p>
      )}
      <p className="muted now-note">
        Every JSON-LD node the crawl parsed on this page, as it parsed it.
        Microdata and RDFa are not read, so a page marked up in either shows
        no blocks here and that is not evidence it has none.
      </p>
    </Card>
  );
}

/** Block 3's body for Structured data: the JSON-LD before and after.
 *
 *  Two panels rather than a diff, exactly as the Images part does with
 *  markup: a corrected `@graph` is not a line-edit of the old one and
 *  pretending otherwise would show an operator a diff they cannot apply.
 *  A `content-first` row shows no code at all, because there is nothing to
 *  paste until the content exists. */
/** The analysis a part's Re-run runs (screen audits round 3, Content UX-01).
 *
 *  It was the first lane whose part matched, which on Content was
 *  content-benchmark: 0 rows for USD 0.12, while content-substance's 18 kept
 *  rows filled the page and its brief had changed since. Now: the analysis
 *  whose rows the page draws - the most rows kept, the newer on a tie - and
 *  the catalogue's order only where none has run. Exported so the screen's
 *  run handler and the button's label and price name the same tool. */
export function partAnalysis(part: Category,
                             lanes: { ready?: Analysis[]; available?: Analysis[] } | null | undefined,
                             ): Analysis | undefined {
  const offered = [...(lanes?.ready ?? []), ...(lanes?.available ?? [])]
    .filter((a) => a.part === part.key);
  const ran = [...(part.brief_runs ?? [])]
    .filter((r) => offered.some((a) => a.tool === r.tool))
    .sort((a, b) => (b.rows - a.rows) || b.at.localeCompare(a.at));
  return (ran.length ? offered.find((a) => a.tool === ran[0].tool) : undefined) ?? offered[0];
}

/** A one-line replacement over 80 characters, laid out (item 270, row 17):
 *  a JSON-LD block the model wrote on one line read as a 400-character
 *  scroll beside a laid-out Now. Anything that is not JSON stays as written. */
export function laidOut(text: string): string {
  const t = text.trim();
  if (t.length <= 80 || t.includes("\n") || !/^[[{]/.test(t)) return text;
  try { return JSON.stringify(JSON.parse(t), null, 2); } catch { return text; }
}

function SchemaFixBody({ fix, facts }: { fix: Fix; facts: Facts | null }) {
  const before = (facts?.schema_inventory ?? []).find(
    (b, n) => fix.block === `${(b.type ?? "block").split(",")[0].trim()}#${n + 1}`);
  if (fix.kind === "content-first") {
    return (
      <>
        <p className="fix-why">
          <b>What the page needs first.</b> {fix.current || fix.note}
        </p>
        <p className="muted fix-meta">
          Nothing to paste yet: the markup states what the page says, so the
          page has to say it first{fix.where ? ` · ${fix.where}` : ""}.
        </p>
      </>
    );
  }
  return (
    <>
      <div className="img-diff">
        <div className="img-panel">
          <p className="fix-lbl muted">Now</p>
          {/* Focusable because it scrolls: a region a mouse can scroll
              and a keyboard cannot is unreachable for anyone not using
              one (axe: scrollable-region-focusable). */}
          <pre className="img-markup out-struck" tabIndex={0}>
            {before
              ? JSON.stringify({ "@type": before.type, "@id": before.id,
                                 ...(before.properties ?? {}) }, null, 2)
              : fix.current || "(no block on this page)"}
          </pre>
        </div>
        {fix.replacement?.trim() ? (
          <div className="img-panel">
            <p className="fix-lbl muted">Replace with</p>
            <pre className="img-markup out-new" tabIndex={0}>{laidOut(fix.replacement)}</pre>
          </div>
        ) : (
          // Screen audits round 3 (Structured data US-01): a card with no
          // markup to paste drew an empty "Replace with" - on twenty22's
          // duplicate Organization, both cards - and the automatic checks'
          // advice, the change itself, was never shown.
          <div className="img-panel">
            <p className="fix-lbl muted">Do this</p>
            <p className="fix-why schema-advice">
              {fix.recommendation || "No markup to paste: the change is to the page's blocks, as Now shows."}
            </p>
          </div>
        )}
      </div>
      {/* Item 270 (row 17): "Where: markup" on a card that is the markup
          says nothing the two panels above it do not. */}
      {fix.where && !["markup", (fix.kind ?? "").toLowerCase()].includes(fix.where.trim().toLowerCase())
        && <p className="muted fix-meta">Where: {fix.where}</p>}
    </>
  );
}

/** How many links of each direction stand before the list says it cut
 *  itself. The server sends forty of each; twelve is what fits beside the
 *  other one without either becoming a scroll. */
export const LINKS_SHOWN = 12;

/** One row of a link list, in whichever direction. */
type LinkRow = { where: string; anchor: string; rel: string };

/** One band: its heading, its rows, its empty sentence and the site's
 *  furniture counted beneath it. Presentational — the reach into `facts`
 *  and the cut stay at the call site, where the real-data-scale invariant
 *  can see them. */
function LinkBand({ side, title, rows, total, folded: fold, empty }: {
  side: string; title: string; rows: LinkRow[]; total: number;
  folded: Record<string, number>; empty: string;
}) {
  return (
    <section className={`links-band links-band-${side}`}>
      <h5>{title} <span className="muted">· {total}</span></h5>
      {total === 0 && <p className="muted">{empty}</p>}
      {rows.length > 0 && (
        <table className="findings links-table">
          <thead>
            <tr><th>{side === "in" ? "Source" : "Target"}</th>
                <th>Anchor</th><th>rel</th></tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td><code>{pathOf(row.where)}</code></td>
                <td>{row.anchor.trim() || "[no anchor text]"}</td>
                <td className="muted">{row.rel || "\u2014"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {total > rows.length && (
        <p className="muted">{total - rows.length} more not shown.</p>
      )}
      {/* The furniture, counted rather than listed (the rule AU3 set for
          images). A navigation link is the same link on every page of the
          site: listed one by one it is most of this list and none of the
          answer, and `inlinks-low` does not count it either. */}
      {Object.entries(fold).map(([region, n]) => (
        <p key={region} className="muted links-template">
          {region} · {n} link{n === 1 ? "" : "s"} — the same on every page,
          counted once for the site
        </p>
      ))}
    </section>
  );
}

const isBody = (link: { region?: string }) => (link.region || "body") === "body";

/** How many of the site's furniture links there are, per region. */
function foldedCounts(links: { region?: string }[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const link of links) {
    const region = link.region || "body";
    if (region !== "body") out[region] = (out[region] ?? 0) + 1;
  }
  return out;
}

/** Block 2, narrowed to one page: what links out, and what links in.
 *
 *  Two lists rather than one table, because they answer two questions and
 *  only one of them is about this page's own markup. The heading line
 *  carries the two numbers every check of this part turns on — how many
 *  pages link here, and how far this page is from home — so a reader who
 *  reads nothing else has the finding.
 *
 *  **The incoming list is the first "now" block about somebody else's
 *  page.** `orphan`, `inlinks-low` and `anchor-generic` are all
 *  statements about other pages' markup, so a page's own record could
 *  never carry the answer; the server derives it from the same crawl this
 *  page was read from, which is what stops this heading's count and the
 *  check's count disagreeing.
 */
function LinksNow({ facts, fixes }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
}) {
  const problems = new Set(fixes.map((f) => f.checkId));
  if (facts.link_inventory === undefined) {
    return (
      <div className="now-card links-now">
        <p className="muted now-note">
          This page was crawled before the link graph was recorded. Re-check
          the part to read it.
        </p>
      </div>
    );
  }
  const inBody = (facts.inlinks ?? []).filter(isBody).length;
  return (
    <div className="now-card links-now">
      <p className="links-head">
        <b>{inBody}</b>{" "}
        <span className="muted">
          page{inBody === 1 ? "" : "s"} link here from body copy
        </span>
        {" · "}
        <b>{facts.click_depth === null ? "\u2014" : facts.click_depth}</b>{" "}
        <span className="muted">
          {facts.click_depth === null
            ? "not reached from the home page by any internal link"
            : `click${facts.click_depth === 1 ? "" : "s"} from the home page`}
        </span>
        {problems.size > 0 && (
          <span className="muted links-problems">
            {" \u00b7 "}{[...problems].join(" \u00b7 ")}
          </span>
        )}
      </p>
      <div className="links-bands">
        <LinkBand side="in" title="Links into this page" total={inBody}
                  folded={foldedCounts(facts.inlinks ?? [])}
                  empty="Nothing on this site links here from body copy."
                  rows={(facts.inlinks ?? []).filter(isBody).slice(0, LINKS_SHOWN).map((l) => ({ where: l.source, anchor: l.anchor, rel: l.rel ?? "" }))} />
        <LinkBand side="out" title="Links out of this page"
                  total={(facts.link_inventory ?? []).filter(isBody).length}
                  folded={foldedCounts(facts.link_inventory ?? [])}
                  empty="This page links nowhere from its body copy."
                  rows={(facts.link_inventory ?? []).filter(isBody).slice(0, LINKS_SHOWN).map((l) => ({ where: l.url, anchor: l.anchor ?? "", rel: l.rel ?? "" }))} />
      </div>
    </div>
  );
}

/** A fix card's body: a link to add, or an anchor to change.
 *
 *  `kind` is the brief's own word for which. A suggestion is a sentence an
 *  operator carries to a CMS — from this page, with this anchor, after
 *  that heading — so the anchor is what the copy button copies; an anchor
 *  fix is the old words struck through above the new ones, the shape the
 *  Title & description card set. */
function LinksFixBody({ fix }: { fix: Fix; facts: Facts | null }) {
  const suggestions = (fix.suggestions ?? []);
  if (suggestions.length) {
    return (
      <div className="fix-links">
        {suggestions.map((s, i) => (
          <p key={i} className="fix-suggestion">
            <code className="fix-src-page">{pathOf(s.source)}</code>
            {" → "}
            <span className="fix-anchor">{s.anchor.trim() || "[no anchor text]"}</span>
            {s.after && (
              <span className="muted fix-after"> · place after: {s.after}</span>
            )}
          </p>
        ))}
      </div>
    );
  }
  // Item 271 (row 7): the finding's sentence is why, not text to strike.
  // An anchor card strikes the old anchor alone and sets the new beside it,
  // read from the replacement's own `'old' → 'new' (→ /target)` entries.
  const swaps = fix.kind === "anchor" ? anchorSwaps(fix.replacement ?? "") : [];
  return (
    <div className="fix-links">
      {fix.current && <p className="fix-why">{fix.current}</p>}
      {swaps.length ? swaps.map((s, i) => (
        <p key={i} className="fix-rep">
          <s>{s.from}</s>{" → "}<span className="fix-anchor">{s.to}</span>
          {s.target && <span className="muted"> (→ {s.target})</span>}
        </p>
      )) : fix.replacement && <p className="fix-rep">{fix.replacement}</p>}
    </div>
  );
}

/** One anchor change per entry of an anchor card's replacement, as the
 *  Links prompt writes it: `'Learn more' → 'what Birch Events does' (→
 *  /birch-events-what-we-do)`, entries separated by `;`. An entry that does
 *  not read that way yields nothing, and the card falls back to the text. */
export function anchorSwaps(replacement: string): { from: string; to: string; target: string | null }[] {
  const out: { from: string; to: string; target: string | null }[] = [];
  for (const part of replacement.split(";")) {
    const m = part.trim().match(/^['‘"“](.+?)['’"”]\s*→\s*['‘"“](.+?)['’"”]\s*(?:\(→\s*([^)]+)\))?$/);
    if (!m) return [];
    out.push({ from: m[1], to: m[2], target: m[3]?.trim() ?? null });
  }
  return out;
}

/** The five things the Content part page says about one page, and where
 *  each answer comes from.
 *
 *  Four of the five are the sweep's own rows rather than a second
 *  measurement: whether the page names an author, whether it carries
 *  enough facts, whether its questions are answered and whether the
 *  answer leads are all checks with findings behind them. A badge that
 *  recomputed any of them could disagree with the finding two blocks
 *  below it, and the screen would be the one nobody could correct. Word
 *  count and the date are read straight from the crawl, because no check
 *  asserts them.
 */
const CONTENT_BADGES: [string, string, string][] = [
  ["no-author", "Author", "named"],
  ["fact-density", "Facts", "enough"],
  ["question-unanswered", "Questions", "answered"],
  ["answer-first", "Answer first", "leads"],
  ["stale", "Updated", "current"],
];

/** How many rows of the map and of the clusters stand before the table
 *  says it cut itself. */
export const MAP_SHOWN = 40;

type CTab = "page" | "map" | "words" | "entities";

function ctabFromHash(): CTab | null {
  const q = new URLSearchParams((window.location.hash.split("?")[1]) || "");
  const t = q.get("ctab");
  return t === "page" || t === "map" || t === "words" || t === "entities" ? t : null;
}
/** Narrow the part to another page, through the address the part screen
 *  reads its page from (item 245: a shared region's other pages). */
function navigatePage(url: string): void {
  const [path, query] = (window.location.hash || "").split("?");
  const q = new URLSearchParams(query || "");
  q.set("page", url);
  goto(`${path}?${q.toString()}`);
}
function setCtabInHash(t: CTab): void {
  const [path, query] = (window.location.hash || "").split("?");
  const q = new URLSearchParams(query || "");
  q.set("ctab", t);
  goto(`${path}?${q.toString()}`);
}

/** The Content part's "now" block, in four tabs (brief v16j Part B; the tab
 *  rule is 136m Step 2b). The tabs are inside the "now" block only - the
 *  actions row and the fix list are never tabbed. The default follows scope:
 *  a page in hand opens This page, the whole site opens The map. The chosen
 *  tab rides in the hash. A view whose data is absent still gets a tab, and
 *  its label carries the absent-data state so the panel is never empty. */
function ContentTabs({ facts, part, bounds, fixes, page }: {
  facts: Facts | null; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
}) {
  const map = part.brief_map ?? [];
  const ents = part.entity_matrix ?? null;
  const runCost = "~USD 0.05";
  const tabs: { key: CTab; label: string; absent?: string }[] = [
    { key: "page", label: "This page" },
    { key: "map", label: "The map",
      absent: map.length ? undefined
        : `The map \u00b7 needs the Coverage analysis \u00b7 run it ${runCost}` },
    { key: "words", label: "The words" },
    { key: "entities", label: "Entities",
      absent: ents ? undefined
        : "Entities \u00b7 set the site record's sub-services and authors on Admin \u203a Sites" },
  ];
  const dflt: CTab = page ? "page" : "map";
  const [active, setActive] = useState<CTab>(ctabFromHash() ?? dflt);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  useEffect(() => { if (!ctabFromHash()) setActive(page ? "page" : "map"); }, [page]);
  const choose = (t: CTab) => { setActive(t); setCtabInHash(t); };
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const nx = tabs[(i + d + tabs.length) % tabs.length];
    choose(nx.key);
    const el = refs.current[nx.key];
    if (el) el.focus();
  };
  return (
    <Card className="now-card content-tabs">
      <div className="ctab-strip" role="tablist" aria-label="what this page has now">
        {tabs.map((t, i) => (
          <button key={t.key} type="button" role="tab"
                  ref={(el) => { refs.current[t.key] = el; }}
                  id={`ctab-${t.key}`} aria-selected={t.key === active}
                  aria-controls={`ctab-panel-${t.key}`}
                  tabIndex={t.key === active ? 0 : -1}
                  className={`ctab${t.key === active ? " on" : ""}${t.absent ? " ctab-absent" : ""}`}
                  onClick={() => choose(t.key)} onKeyDown={(e) => onKey(e, i)}>
            {t.absent ?? t.label}
          </button>
        ))}
      </div>
      {/* Item 269 (row 8): in page mode the screenshot and regions run long
          above the cards; the way to them is beside the tabs, with their
          count. Outside the tablist, which holds only tabs. */}
      {page && fixes.length > 0 && (
        <SecondaryButton className="ctab-jump"
                         onClick={() => document.getElementById("part-fixes")
                           ?.scrollIntoView({ block: "center" })}>
          Fixes ({fixes.length})
        </SecondaryButton>
      )}
      <div role="tabpanel" id={`ctab-panel-${active}`}
           aria-labelledby={`ctab-${active}`} className="ctab-panel">
        {active === "page" && <ThisPageTab facts={facts} part={part}
                                           bounds={bounds} fixes={fixes} page={page} />}
        {active === "map" && (map.length
          ? <ContentMap part={part} />
          : <p className="muted">The Coverage analysis has not run for this audit,
              so there is no map yet.</p>)}
        {active === "words" && <TheWordsTab fixes={fixes} page={page} />}
        {active === "entities" && <EntitiesTab matrix={ents} page={page}
                                                verdict={facts?.entity_verdict ?? null} />}
      </div>
    </Card>
  );
}

const TP_TONE: Record<string, string> = {
  unique: "ok", shared: "warn", boilerplate: "mute", thin: "bad",
};

/** Tab 1: the page's text weighed. A totals line and stacked bar over one
 *  row per region, each coloured by class. Reads the server's
 *  classification - nothing here measures. */
function ThisPageTab({ facts, part, bounds, fixes, page }: {
  facts: Facts | null; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
}) {
  const [sel, setSel] = useState<number | null>(null);
  // No page in scope: this view is one page at a time, so it asks for one
  // rather than rendering a default page's content (which read as "the whole
  // site" and, when `facts` is null at site scope, crashed the tab).
  if (!page || !facts) {
    return <p className="muted">Choose a page above to weigh its text —
      this view reads one page at a time. The map and Entities tabs are the
      whole-site views.</p>;
  }
  const cb = facts.content_blocks;
  // The page's content always shows - word count, dates, the opening, the
  // check badges. The weighed-text overlay is ADDED when the rendered pass
  // visited this page; it does not replace the content, so a page that was
  // crawled but not rendered still reads here (only 5 of N pages are
  // rendered at a tier, and the other pages are not blank).
  const base = <ContentNow facts={facts} part={part} bounds={bounds}
                           fixes={fixes} page={page} />;
  if (!cb || !cb.rendered) {
    return (
      <>
        {base}
        <p className="muted overlay-none tp-unrendered">
          The rendered pass did not weigh this page in this audit
          {cb ? ` (${cb.pages_rendered} page${cb.pages_rendered === 1 ? "" : "s"} rendered)` : ""}.
          Re-check the part to draw where its words come from.
        </p>
      </>
    );
  }
  const t = cb.totals!;
  const list = cb.blocks ?? [];
  const all = t.unique + t.shared + t.boilerplate || 1;
  const cls = (b: ContentBlock) => (b.thin ? "thin" : b.klass);
  // Item 245: the rows select a region only where there is a picture to
  // select it on. Without one a press changed nothing a reader could see,
  // so the rows are a plain list and a line says why.
  const shot = cb.screenshot && cb.doc?.w ? cb.screenshot : null;
  const placed = list.map((b, i) => ({ b, n: i + 1 }))
    .filter(({ b }) => b.rect && (b.rect.w || b.rect.h));
  const pick = (n: number | null) => setSel(n == null ? null : n - 1);
  const row = (b: ContentBlock, i: number) => (
    <>
      <i className={`tp-badge tone-${TP_TONE[cls(b)]}`}>{i + 1}</i>
      <span className="tp-name">{b.name || `(${b.tag})`}</span>
      <span className="muted tp-w">{b.words} words</span>
      <span className="tp-note">{tpNote(b, t.boilerplate ? cb.pages_rendered : 0)}</span>
    </>
  );
  return (
    <div className="tp">
      {base}
      <p className="tp-totals">
        <b>{t.words}</b> words of its own, as rendered {" · "}
        <span className="tp-u">{t.unique} unique to it</span> {" · "}
        <span className="tp-s">{t.shared} shared with another page</span>
        {t.boilerplate ? <>{" · "}<span className="tp-b">plus {t.boilerplate} words of site
          furniture</span></> : null}
        {" · "}<b>{t.unique_pct}%</b> of its own words are on no other page
        {/* Item 269 (row 8): the thin regions counted on the summary, so the
            line says what the list below will show. */}
        {list.some((b) => b.thin)
          ? <>{" · "}{list.filter((b) => b.thin).length} thin region
              {list.filter((b) => b.thin).length === 1 ? "" : "s"}</> : null}
      </p>
      <div className="tp-bar" aria-hidden="true">
        {(["unique", "shared", "boilerplate"] as const).map((k) =>
          t[k] ? <span key={k} className={`tp-seg tone-${TP_TONE[k]}`}
                       style={{ width: `${(t[k] / all) * 100}%` }} /> : null)}
      </div>
      {shot ? (
        // Item 269 (row 8): the screenshot in a 900 px box that scrolls, so
        // the regions and the cards are not a page's height below the
        // summary. Focusable, because a region that scrolls must be
        // reachable without a mouse.
        <div className="tp-overlay-cap" tabIndex={0} role="region"
             aria-label="the page's screenshot with its text regions; scrolls">
        <div className="overlay tp-overlay">
          <ShotBoxes src={shot} docW={cb.doc!.w} selected={sel == null ? null : sel + 1}
                     onSelect={pick}
                     alt={`screenshot of the page, with ${placed.length} text region`
                          + `${placed.length === 1 ? "" : "s"} marked`}
                     boxes={placed.map(({ b, n }) => ({
                       n, rect: b.rect, tone: TP_TONE[cls(b)],
                       label: `region ${n}, ${cls(b)}, ${b.words} words` }))} />
        </div>
        </div>
      ) : (
        <p className="muted tp-noshot">The rendered pass took no screenshot of this page,
          so its regions are listed without a picture to find them on.</p>
      )}
      <ol className="tp-rows">
        {list.map((b, i) => (
          <li key={i} className={`tp-row${sel === i ? " is-sel" : ""}`}>
            {shot ? (
              <button type="button" className="tp-rowbtn"
                      aria-expanded={sel === i}
                      aria-label={`region ${i + 1}, ${cls(b)}, ${b.words} words`}
                      onClick={() => setSel(sel === i ? null : i)}>
                {row(b, i)}
              </button>
            ) : <div className="tp-rowplain">{row(b, i)}</div>}
            {shot && sel === i && (
              <div className="tp-detail">
                {b.excerpt && <p className="tp-excerpt">{b.excerpt}</p>}
                {b.klass === "shared" && b.other_pages.length > 0 && (
                  <p className="muted">Also on:{" "}
                    {b.other_pages.map((u, k) => (
                      <Fragment key={u}>{k ? ", " : ""}
                        <button type="button" className="btn-link"
                                onClick={() => navigatePage(u)}>{pathOf(u)}</button>
                      </Fragment>
                    ))}
                  </p>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function tpNote(b: ContentBlock, rendered = 0): string {
  if (b.thin) return "a heading that promises a section, with under 50 words under it.";
  // Item 245: which rule made it furniture, so a block of the page's own
  // copy is not mistaken for one - or a template's repeated block is seen
  // for what it is.
  if (b.klass === "boilerplate") {
    if (b.boilerplate_why === "repeated" && b.on_pages)
      return `Site furniture: repeated on ${b.on_pages} of ${rendered || b.on_pages} rendered pages. `
        + "Not counted toward this page.";
    if (b.boilerplate_why === "landmark")
      return "Site furniture: in the page's header, navigation or footer. Not counted toward this page.";
    return "Site furniture. Not counted toward this page.";
  }
  if (b.klass === "shared")
    return `Also on ${b.other_pages.map(pathOf).join(", ")}, word for word.`;
  return "";
}

/** Tab 3: the Substance rows for this page, from the fixes already on the
 *  part - the check and its reading. */
function TheWordsTab({ fixes, page }: { fixes: Fix[]; page: string }) {
  const SUBST = ["eeat", "substance", "answer-surface", "retrieval-cost",
                 "fact-density", "answer-first", "no-author", "stale"];
  if (!page) return <p className="muted">Choose a page to read its words.</p>;
  const rows = fixes.filter((f) => SUBST.includes(f.checkId));
  if (!rows.length) return <p className="muted">Nothing open on this
    page&rsquo;s content checks, or the Substance analysis has not run.</p>;
  return (
    <table className="words-table">
      <thead><tr><th>Check</th><th>Reading</th></tr></thead>
      <tbody>
        {rows.map((f) => (
          <tr key={f.key}>
            <td><code>{f.check}</code></td>
            <td className="muted">{f.current}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Tab 4: the site's entities against where each is named. Rows are the
 *  record's own entities (and every Coverage gap), columns are page counts,
 *  each row carries an engine verdict. The matcher and the reading line are
 *  the server's - the screen draws, it does not judge. */
function EntitiesTab({ matrix, page, verdict }: {
  matrix: EntityMatrix | null; page: string;
  verdict?: { verdict: string; status: string; contested: string[] } | null;
}) {
  const banner = page && verdict ? (
    <p className={`em-verdict-banner tone-${verdict.status === "PASS" ? "ok" : "bad"}`}>
      <b>{verdict.verdict}</b>
      {verdict.contested?.length
        ? <span className="muted"> — contested: {verdict.contested.join(", ")}</span>
        : null}
    </p>
  ) : null;
  if (!matrix) {
    return <>{banner}<p className="muted">Set the site record&rsquo;s
      sub-services and authors on Admin &rsaquo; Sites, and this matrix draws
      what each is named by.</p></>;
  }
  const COLS: [string, string][] = [
    ["url", "URL"], ["title", "Title"], ["h1", "H1"], ["body", "Body"],
    ["anchors", "Anchors"], ["schema", "Schema"], ["map", "Map"],
  ];
  const groups: [string, (k: string) => boolean][] = [
    ["Services", (k) => k === "sub_services" || k === "service" || k === "sub-service"],
    ["Places", (k) => k === "locations" || k === "location" || k === "service_area"],
    ["People", (k) => k === "authors" || k === "author"],
    ["Other", (k) => k === "brand" || k.startsWith("from Coverage")],
  ];
  const s = matrix.summary;
  const tone = (v: string) => v === "owned" ? "ok" : v === "mentioned" ? "warn" : "bad";
  return (
    <div className="em">
      {banner}
      <p className="em-summary muted">
        {s.entities} entities &middot; <b>{s.owned}</b> owned &middot;{" "}
        {s.mentioned} only mentioned &middot; {s.absent} absent &middot;{" "}
        {s.with_schema} with a schema node
      </p>
      <div className="em-scroll">
        <table className="em-table">
          <thead>
            <tr>
              <th scope="col">Entity</th>
              {COLS.map(([, label]) => <th key={label} scope="col">{label}</th>)}
              <th scope="col">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(([name, pick]) => {
              const rows = matrix.rows.filter((r) => pick(r.kind));
              if (!rows.length) return null;
              return (
                <Fragment key={name}>
                  <tr className="em-group"><th scope="rowgroup"
                      colSpan={COLS.length + 2}>{name}</th></tr>
                  {rows.map((r) => (
                    <tr key={r.entity}>
                      <th scope="row">{r.entity}
                        <span className="muted em-kind"> {kindLabel(r.kind)}</span>
                      </th>
                      {COLS.map(([k]) => {
                        const n = r.cells[k] ?? 0;
                        const warn = n > 0 && (k === "anchors" || k === "body")
                          && r.cells.url === 0 && r.cells.title === 0 && r.cells.h1 === 0;
                        return (
                          <td key={k} className={`em-cell tone-${n ? (warn ? "warn" : "ok") : "mute"}`}>
                            {n || "\u2014"}
                          </td>
                        );
                      })}
                      <td className={`em-verdict tone-${tone(r.verdict)}`}>{r.verdict}</td>
                    </tr>
                  ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="em-reading">{matrix.reading}</p>
      <p className="em-matcher muted">Matched {matrix.matcher}.
        {matrix.body_basis ? ` Body ${matrix.body_basis}.` : ""}</p>
    </div>
  );
}

function kindLabel(kind: string): string {
  const m: Record<string, string> = {
    sub_services: "sub-service", service: "service", locations: "location",
    service_area: "service area", authors: "author", brand: "brand",
  };
  return m[kind] ?? kind;
}

function ContentNow({ facts, part, fixes, page }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
}) {
  const raised = new Set(fixes.map((f) => f.checkId));
  const updated = (facts.content_dates || {})["dateModified"]
    || (facts.content_dates || {})["datePublished"] || null;
  return (
    <div className="now-card content-now">
      <p className="content-head">
        <b>{facts.word_count ?? "\u2014"}</b>{" "}
        {/* Item 245: two counts on one tab, so each says whose it is. */}
        <span className="muted">words in the page&rsquo;s HTML</span>
        {" \u00b7 "}
        <b>{updated ? updated.slice(0, 10) : "\u2014"}</b>{" "}
        <span className="muted">
          {updated ? "last updated, by the page's own date" : "no date on the page"}
        </span>
      </p>
      <p className="content-badges">
        {CONTENT_BADGES.map(([check, label, good]) => {
          // Item 269: a check that does not read this kind of page is not a
          // pass on it - "Author: named" on a home page no author check reads.
          const unread = (facts.content_not_run ?? []).includes(check) && !raised.has(check);
          return (
            <span key={check}
                  className={`str-badge ${unread ? "str-held" : raised.has(check) ? "sb-fail" : "sb-pass"}`}
                  title={unread
                           ? `${check} does not read ${facts.page_type ? `a ${facts.page_type} page` : "a page with no type on the site record"}`
                           : raised.has(check)
                           ? `${check} is open on this page`
                           : `${check} did not fire on this page`}>
              {label}: {unread ? MEASURE_WORD["not-measured"] : raised.has(check) ? "no" : good}
            </span>
          );
        })}
      </p>
      {/* What a reader and a model both meet first. Quoted rather than
          summarised: the checks above are about whether the answer is
          here, and a paraphrase would be the screen answering its own
          question. */}
      {facts.opening
        ? <p className="content-opening">{facts.opening}{"\u2026"}</p>
        : <p className="muted">The crawl recorded no body text for this page.</p>}
    </div>
  );
}

/** Block 2 on the whole site: Coverage's map.
 *
 *  Drawn rather than described, because the map is the one output of this
 *  part that is a shape - services down, node types across, and the holes
 *  are the finding. A run that has not happened says so; a map with no
 *  rows after a run that did happen is a different sentence and gets one.
 */
function ContentMap({ part }: { part: Category }) {
  // Item 269 (row 12): the missing nodes first - the map's work - and every
  // row reachable, as Fixes opens its groups. "38 more not shown" hid most
  // of them behind nothing.
  const rows = [...(part.brief_map ?? [])].sort((a, b) =>
    Number((b.status || "").toLowerCase() === "missing") - Number((a.status || "").toLowerCase() === "missing"));
  const [all, setAll] = useState(false);
  const clusters = part.brief_clusters ?? [];
  return (
    <section className="content-map">
      <h4>Topical map <span className="muted">· {rows.length}</span></h4>
      {rows.length === 0 && (
        <p className="muted">
          Coverage has not run against this site, so there is no map. It is
          the analysis that draws one — nothing here is derived from the
          crawl alone.
        </p>
      )}
      {rows.length > 0 && (
        <div className="table-scroll">
          <table className="findings map-table">
            <thead>
              <tr><th>Service</th><th>Node</th><th>State</th><th>Pages</th><th>Type</th></tr>
            </thead>
            <tbody>
              {(all ? rows : rows.slice(0, MAP_SHOWN)).map((row, i) => (
                <tr key={i}>
                  <td>{row.service || "\u2014"}</td>
                  <td>{row.node || "\u2014"}</td>
                  <td><span className={`map-state map-${(row.status || "").toLowerCase()}`}>
                    {row.status || "—"}</span></td>
                  <td>{(row.pages ?? []).length
                        ? (row.pages ?? []).map((u) => <code key={u}>{pathOf(u)}</code>)
                        : <span className="muted">none</span>}</td>
                  <td className="muted">{row.type || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > MAP_SHOWN && (
        <SecondaryButton className="fix-more" onClick={() => setAll(!all)}>
          {all ? "show fewer" : `show all ${rows.length}`}
        </SecondaryButton>
      )}
      {clusters.length > 0 && (<>
        <h4>Overlapping pages <span className="muted">· {clusters.length}</span></h4>
        <div className="table-scroll">
          <table className="findings cluster-table">
            <thead>
              <tr><th>Cluster</th><th>Survivor</th><th>Pages</th><th>Rule</th></tr>
            </thead>
            <tbody>
              {(part.brief_clusters ?? []).slice(0, MAP_SHOWN).map((row, i) => (
                <tr key={i}>
                  <td>{row.cluster || "\u2014"}</td>
                  <td>{row.survivor ? <code>{pathOf(row.survivor)}</code> : "\u2014"}</td>
                  {/* The cluster's own size, over the pages the brief read -
                      a what-we-know statement, so the record is its legal
                      population and it renders plain (item 155). */}
                  <td className="num">
                    <Counted pops={null}
                             count={makeCount((row.pages ?? []).length, "record")} />
                  </td>
                  <td className="muted">{row.rule || row.note || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>)}
    </section>
  );
}

function ContentFixBody({ fix }: { fix: Fix; facts: Facts | null }) {
  return (
    <div className="fix-content">
      {/* Item 269 (row 10): the finding's sentence is struck only where a
          replacement stands under it; otherwise it is the reason, and a free
          card carries the automatic checks' own advice beneath it. */}
      {fix.current && (fix.replacement
        ? <p className="fix-now"><s>{fix.current}</s></p>
        : <p className="fix-why">{fix.current}</p>)}
      {fix.replacement && <p className="fix-rep">{fix.replacement}</p>}
      {!fix.replacement && fix.recommendation && (
        <p className="fix-rep"><span className="fix-lbl">Do this: </span>{fix.recommendation}</p>
      )}
      {/* A replacement that could not be written because the client has
          to supply a fact is not a failure of the brief: `content-first`
          is what the prompt returns instead of inventing the fact. */}
      {fix.kind === "content-first" && (
        <p className="muted fix-content-first">
          The client must supply this before the copy can be written.
        </p>
      )}
    </div>
  );
}

/** Block 2's selection lives in the hash, so a barrier can be linked to.
 *  `&barrier=<n>` beside the part page's other hash state. */
function barrierFromHash(): number | null {
  const q = new URLSearchParams((window.location.hash || "").split("?")[1] || "");
  const n = Number(q.get("barrier"));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Through `goto`, never by assigning `window.location.hash`. A hash
 *  assigned directly does nothing when it names the current location and
 *  the call site cannot tell — the same door `setDepthInHash` uses. */
function setBarrierInHash(n: number | null): void {
  const [path, query] = (window.location.hash || "").split("?");
  const q = new URLSearchParams(query || "");
  if (n == null) q.delete("barrier");
  else q.set("barrier", String(n));
  const tail = q.toString();
  goto(tail ? `${path}?${tail}` : path);
}

/** Block 2, Accessibility's renderer: the fix order at site scope, the
 *  page's own barriers when one page is narrowed to (brief v16e).
 *
 *  One position, two blocks, chosen by scope rather than stacked. They
 *  answer different questions - "what should I do first" and "where on this
 *  page is it" - and showing both at once would put a site-wide bar chart
 *  above a single page's screenshot, which reads as though the chart were
 *  about the page.
 */
function A11yNow({ part, page }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
}) {
  const [sel, setSel] = useState<number | null>(barrierFromHash());
  const [step, setStep] = useState<number | null>(null);
  const barriers = part.barriers;
  const pick = (n: number | null) => { setSel(n); setBarrierInHash(n); };
  return (
    <Card className="now-card">
      <h4>{page ? "What the page has now" : "What the site has now"}</h4>
      {page ? (
        barriers ? (
          <BarrierOverlay src={barriers.screenshot} docW={barriers.doc.w}
                          docH={barriers.doc.h} barriers={barriers.barriers}
                          rendered={barriers.rendered} crawled={barriers.crawled}
                          selected={sel} onSelect={pick} />
        ) : (
          <p className="muted overlay-none">
            Nothing is recorded for this page in the audit being read.
          </p>
        )
      ) : (
        <FixOrderWaterfall order={part.fix_order} selected={step}
                           onStep={(s, i) => { setStep(i); openFixGroup(s.check); }} />
      )}
      <p className="muted now-note">
        {page
          ? "Boxes come from the rendered pass, which samples the crawl. A "
            + "barrier listed without a box was found by a check that reads "
            + "the markup, which records no position."
          : "Each step is one piece of work, and its height is the instances "
            + "it removes rather than the rows it closes."}
      </p>
    </Card>
  );
}

/** Block 3's body for Accessibility: the element, and where it sits. There
 *  is no before/after here - an accessible name is content the page does not
 *  have, so there is nothing to strike through. */
function A11yFixBody({ fix }: { fix: Fix; facts: Facts | null }) {
  // Item 279 (row 5): each card was one sentence ("4 link(s) on /about/ have
  // no accessible name") while the row carried the elements and the
  // module's advice. Both are drawn now.
  const targets = fix.targets ?? [];
  return (
    <>
      <p className="fix-why">{fix.current || fix.note}</p>
      {targets.length > 0 && (
        <div className="fix-where">
          <span className="fix-lbl">Where: </span>
          {targets.slice(0, A11Y_TARGETS_SHOWN).map((t, i) => (
            <Fragment key={t}>{i > 0 && " · "}<code>{t}</code></Fragment>
          ))}
          {targets.length > A11Y_TARGETS_SHOWN
            && <span className="muted"> and {targets.length - A11Y_TARGETS_SHOWN} more</span>}
        </div>
      )}
      {fix.replacement ? (
        <div className="img-panel">
          <p className="fix-lbl muted">Do this</p>
          <pre className="img-markup out-new" tabIndex={0}>{fix.replacement}</pre>
        </div>
      ) : fix.recommendation && (
        <p className="fix-new"><span className="fix-lbl">Do this: </span>{fix.recommendation}</p>
      )}
      {fix.where && <p className="muted fix-meta">Where: {fix.where}</p>}
    </>
  );
}

/** How many of a card's elements are named before "and N more". */
const A11Y_TARGETS_SHOWN = 5;

/** Block 2, Security & transport's renderer: what every response actually
 *  carried (brief v16h). Site scope only - a header is a property of a
 *  response and the grid's subject is whether they agree across the site,
 *  which one page cannot answer. */
function SecurityNow({ facts, part, page, narrow, onNarrow }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
  narrow?: string | null; onNarrow?: (key: string | null) => void;
}) {
  return (
    <Card className="now-card">
      {/* The 143 addendum's order: the verdict, then the layers, then the
          headers. A compromised site makes every hygiene row irrelevant, so
          the one line that says whether it is comes first. */}
      <SecurityLayers part={part} narrow={narrow ?? null} onNarrow={onNarrow} />
      <h3>What the site has now</h3>
      {page ? (
        <p className="muted hg-none">
          Response headers are a property of the whole site&rsquo;s
          configuration, so this grid is drawn without a page filter. Clear
          the filter above to read it.
        </p>
      ) : (
        <HeadersGridBlock grid={part.headers_grid} />
      )}
      {/* Outside the filter branch on purpose. The grid is a claim about
          routes and a page filter makes it unreadable; what the connection
          negotiated is one fact about the origin and is the same fact
          whichever page is chosen, so hiding it behind the filter would
          withhold the floor from a reader who had narrowed for an unrelated
          reason. */}
      <TransportFacts transport={part.transport ?? facts?.site?.transport ?? null} />
      <p className="muted now-note">
        Read from the response every fetched page returned. A row marked
        &ldquo;the grid&rsquo;s reading&rdquo; is decided here more loosely than
        SEC&rsquo;s own check for that header, which is what the record shows.
      </p>
    </Card>
  );
}

/** The compromise verdict (143 addendum, block 1). One of three: no sign of
 *  compromise, indicators found (with the indicator named), not assessable
 *  (with the input missing). It never says "secure". Triage is the Security
 *  brief's, so before one has run the line says that rather than inventing a
 *  verdict from the sweep. */
function SecurityVerdict({ part }: { part: Category }) {
  const c = part.brief_security?.compromise ?? null;
  const verdict = (c?.verdict ?? "").toLowerCase();
  const kind = !c ? "none"
    : verdict.includes("none") ? "clear"
    : verdict.includes("indicator") ? "found" : "none";
  const head = kind === "clear" ? "No sign of compromise"
    : kind === "found" ? "Indicators of compromise found"
    : "Compromise not assessable";
  const basis = c?.basis
    ?? (c ? c.verdict : "No Security analysis has run on this site, and compromise triage is the "
        + "analysis's judgement over the page sources, script inventory and cloaking diff. "
        + "Nothing below says the site is secure.");
  return (
    <div className={`secv secv-${kind}`} role="note">
      <h3>{head}</h3>
      <span className="muted">{basis}</span>
    </div>
  );
}

const SEC_LAYERS: [string, string][] = [
  ["dns", "DNS & mail"], ["edge", "Firewall / CDN"], ["origin", "Origin"], ["page", "Page"]];

/** The layers, and how far the sweep saw into each (143 addendum, block 2).
 *
 *  One card per domain at the layer it lives at. The state reads the brief's
 *  own ledger where a brief has run; before that, it reads what THIS run
 *  measured - a domain whose checks are all held is hollow, one with any
 *  check not assessed is partial and names the first reason, the rest are
 *  assessed, amber where a finding is open. Every state is also a word on the
 *  card, never only a fill (WCAG 1.4.1). */
function SecurityLayers({ part, narrow, onNarrow }: {
  part: Category; narrow: string | null; onNarrow?: (key: string | null) => void;
}) {
  const domains = part.sec_domains;
  if (!domains) return null;
  const ledger = new Map((part.brief_security?.ledger ?? []).map((e) => [e.domain, e]));
  const open = new Set(part.findings.filter((f) => f.state !== "fixed").map((f) => f.check_id));
  const unmeasured = new Map(Object.entries(part.not_assessed ?? {})
    .map(([full, why]) => [full.split("/").pop() ?? full, why]));
  const cards = Object.entries(domains).map(([letter, d]) => {
    const found = d.checks.filter((c) => open.has(c)).length;
    const missing = d.checks.filter((c) => unmeasured.has(c));
    const held = missing.filter((c) => (unmeasured.get(c) ?? "").startsWith("held"));
    const entry = ledger.get(letter);
    let state: "ok" | "warn" | "partial" | "held";
    let note: string;
    if (entry) {
      const s = entry.status.toLowerCase();
      state = s.startsWith("not") ? "held" : s.startsWith("partial") ? "partial"
        : found ? "warn" : "ok";
      // Item 276 (row 9, round-1 #4 and #8): the found count first, as the
      // partial branch says it; a ledger gap naming the probing switch in
      // the engine's held words (it read as if the switch were on), and any
      // other gap of an unassessed domain as what it needs.
      const why = entry.missing && /active[_ ]probing/i.test(entry.missing) && held.length
        ? (unmeasured.get(held[0]) ?? "").replace(/^held: /, "")
        : entry.missing && s.startsWith("not") && !/^needs\b/i.test(entry.missing)
          ? `needs ${entry.missing}` : entry.missing;
      note = [found ? `${found} finding${found === 1 ? "" : "s"} open` : null,
              why ?? entry.summary ?? (found ? null : "assessed")].filter(Boolean).join(" · ");
    } else if (held.length === d.checks.length) {
      state = "held";
      note = (unmeasured.get(held[0]) ?? "held").replace(/^held: /, "");
    } else if (missing.length === d.checks.length) {
      // Item 180 (06-3): none of its checks measured is not "partial", which
      // read as "some was checked".
      state = "held";
      note = `${MEASURE_WORD["not-measured"]}: `
        + (unmeasured.get(missing[0]) ?? "").replace(/^(not collected yet|not assessed|held): /, "");
    } else if (missing.length) {
      state = "partial";
      // Both halves: what was found among the measured checks, and what was
      // not measured. A partly measured domain with open findings read only
      // "not assessed", which hid the findings behind the gap.
      note = (found ? `${found} finding${found === 1 ? "" : "s"} open · ` : "")
        + `${missing.length} of ${d.checks.length} not assessed: `
        + (unmeasured.get(missing[0]) ?? "").replace(/^(not collected yet|not assessed|held): /, "");
    } else {
      state = found ? "warn" : "ok";
      note = found ? `${found} finding${found === 1 ? "" : "s"} open` : "assessed, nothing found";
    }
    const word = { ok: "assessed", warn: "assessed, findings", partial: "partly measured",
                   held: missing.length === d.checks.length && !entry ? MEASURE_WORD["not-measured"] : "held" }[state];
    return { letter, ...d, state, note, word };
  });
  return (
    <section className="seclayers" aria-label="The layers, and how far the checks saw into each">
      <h3>The layers, and how far the {part.brief_security ? "analysis" : "automatic checks"} saw into each</h3>
      <div className="seclayers-rail">
        {SEC_LAYERS.map(([key, label]) => (
          <div key={key} className="seclayer">
            <div className="seclayer-name">{label}</div>
            <div className="seclayer-cards">
              {cards.filter((c) => c.layer === key).map((c) => (
                // A button (item 143 step BD): pressing a domain narrows the
                // fix cards below to its checks, and pressing it again clears
                // the narrow. Spans, not divs, inside: a button holds phrasing
                // content only.
                <button type="button" key={c.letter} className={`seccard seccard-${c.state}`}
                        data-domain={c.letter} data-state={c.state}
                        aria-pressed={narrow === c.letter}
                        aria-label={`narrow fixes to ${c.letter} ${c.name}: ${c.word}, ${c.note}`}
                        disabled={!onNarrow}
                        onClick={() => onNarrow?.(narrow === c.letter ? null : c.letter)}>
                  <span className="seccard-head">
                    <span className="seccard-letter">{c.letter}</span> {c.name}
                    <span className="seccard-word"> · {c.word}</span>
                  </span>
                  <span className="seccard-note muted">{c.note}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {onNarrow && <p className="muted seclayers-caption">Press a layer to narrow the fixes below.</p>}
    </section>
  );
}

/** What the connection itself did, which is not a header and so is not in
 *  the grid above. It sat on the old page's facts panel until brief v16h
 *  gave this part a card; the grid replaces the header rows that panel drew
 *  and these four came with it rather than being dropped.
 *
 *  `Accepts down to` is the one that matters and the reason this is here at
 *  all: a bare `TLS 1.3` reads as the site's floor when it is only the
 *  ceiling one handshake reached, and the limitation belongs beside it in
 *  text.
 */
/** The certificate's expiry as a date. The probe stores OpenSSL's text form
 *  ("Dec 14 13:05:09 2026 GMT"), and cutting it at ten characters drew
 *  "Dec 14 13:" once site scope showed it (item 276, row 9). An ISO string
 *  passes through as its date. */
export function certDay(raw: string): string {
  const d = new Date(raw.replace(/ GMT$/, " UTC"));
  return Number.isNaN(d.getTime()) ? raw : day(d.toISOString());
}

function TransportFacts({ transport }: { transport: Facts["site"]["transport"] | null }) {
  const t = transport;
  if (!t) return null;
  const rows: [string, string][] = [
    ["TLS", t.tls_version
      ? `${t.tls_version} negotiated · ${t.cipher ?? "cipher not recorded"}`
      : "not probed — the site was not reached over HTTPS"],
    ["Accepts down to", t.tls_floor
      ? `${String(t.tls_floor).replace("_", ".")}${t.tls_floor_certain ? ""
         : " at lowest — older versions could not be offered from this "
           + "machine, so the floor is not settled"}`
      : MEASURE_WORD["not-measured"]],
    ["Certificate", t.cert_not_after
      ? `valid to ${certDay(String(t.cert_not_after))}` : "not recorded"],
    ["HTTP → HTTPS", t.http_redirects_to_https ? "redirects" : "does not redirect"],
  ];
  return (
    <div className="facts hg-transport">
      {rows.map(([k, v]) => (
        <div key={k} className="fact-row">
          <span className="fact-key">{k}</span>
          <span className="fact-val">{v}</span>
        </div>
      ))}
    </div>
  );
}

/** Block 3's body: the header to add, as a line to paste. */
/** The address's narrow, applied to one part's fixes and populations (brief
 *  v25 step BP), or null where nothing narrows this part. A narrow names a
 *  population only a part that draws its control has, so a `?depth=` left in
 *  the address while another part is open narrows nothing there. */
export function siteScopedNarrow(part: Category, narrow: Narrow, fixes: Fix[], pops: Populations | null):
    { kind: NarrowKind; fixes: Fix[]; pops: Populations | null; said: string } | null {
  if (!narrow) return null;
  const crawlSize = pops?.crawl.size ?? null;
  const onPages = (urls: string[], words: string) => {
    const has = pagePredicate(urls);
    const keys = [...new Set(urls.map(pathKey))];
    const inCrawl = pops ? pops.crawl.paths.filter((p) => has(p)) : keys;
    return {
      kind: narrow.kind,
      fixes: fixes.filter((f) => f.page && has(f.page)),
      pops: pops ? { ...pops, crawl: { size: inCrawl.length, basis: words, paths: inCrawl } } : null,
      said: `Showing ${words}: ${inCrawl.length}${crawlSize != null ? ` of ${crawlSize}` : ""} crawled pages.`,
    };
  };
  if (narrow.kind === "depth" && part.depth) {
    const n = depthPicked(part.depth, narrow.value);
    if (n === null) return null;
    const urls = Object.entries(part.depth.at).filter(([, d]) => d === n).map(([u]) => u);
    return onPages(urls, `depth ${n}`);
  }
  if (narrow.kind === "template") {
    const map = part.urls_now?.pattern_of ?? part.speed_now?.pattern_of ?? null;
    if (!map || !Object.values(map).includes(narrow.value)) return null;
    const urls = Object.entries(map).filter(([, t]) => t === narrow.value).map(([u]) => u);
    return onPages(urls, `pages under ${narrow.value}`);
  }
  if (narrow.kind === "check" && part.key === "indexability") {
    const bare = narrow.value.split("/").pop() ?? narrow.value;
    const kept = fixes.filter((f) => f.check === narrow.value || f.checkId === bare);
    return { kind: "check", fixes: kept, pops,
             said: `Showing ${narrow.value}: ${kept.length} of ${fixes.length} fix cards.` };
  }
  return null;
}

/** An HSTS max-age ramp named in a fix's `staged` text ("300 → 86400 →
 *  31536000"), as the values it steps through. Null unless at least two
 *  strictly increasing values are joined by an arrow, comma or "then", and
 *  the text is then shown as written. */
export function rampOf(staged: string): number[] | null {
  const m = staged.match(/\d+(?:\s*(?:→|->|=>|,|then)\s*\d+)+/);
  if (!m) return null;
  const steps = m[0].split(/\s*(?:→|->|=>|,|then)\s*/).map(Number);
  return steps.length >= 2 && steps.every((v, i) => i === 0 || v > steps[i - 1]) ? steps : null;
}

const SPANS: [number, string][] = [[31536000, "year"], [604800, "week"], [86400, "day"],
                                   [3600, "hour"], [60, "minute"]];

/** A max-age in the unit it divides into exactly: 86400 is "1 day". */
export function spanOf(seconds: number): string {
  for (const [n, unit] of SPANS) {
    if (seconds >= n && seconds % n === 0) {
      const k = seconds / n;
      return `${k} ${unit}${k === 1 ? "" : "s"}`;
    }
  }
  return `${seconds} seconds`;
}

function SecurityFixBody({ fix }: { fix: Fix; facts: Facts | null }) {
  const r = fix.rollout;
  // The ramp is HSTS's: a max-age raised in steps, each held until nothing
  // breaks (brief v20 step BD). Other staged text - a Report-Only window -
  // reads as written.
  const ramp = r?.staged && fix.checkId.startsWith("hsts") ? rampOf(r.staged) : null;
  return (
    <>
      <p className="fix-why">{fix.current || fix.note}</p>
      {r?.impact && <p className="fix-meta"><b>Impact:</b> {r.impact}</p>}
      {fix.replacement && (
        <div className="img-panel">
          <p className="fix-lbl muted">Add this</p>
          <pre className="img-markup out-new" tabIndex={0}>{fix.replacement}</pre>
        </div>
      )}
      {/* Brief v20 step BD: the change per layer, so the edge and the origin
          each get the block for their own stack, then the risk, the check
          that it worked, and the way back - in that order, because a change
          nobody can verify or undo should not be deployed. */}
      {(r?.config ?? []).map((c, i) => (
        <div key={i} className="img-panel sec-layer-cfg">
          <p className="fix-lbl muted">{c.layer ?? "config"}{c.stack ? ` · ${c.stack}` : ""}</p>
          <pre className="img-markup out-new" tabIndex={0}>{c.block}</pre>
        </div>
      ))}
      {r && (r.deploy_risk || r.verify || r.rollback || r.staged) && (
        <dl className="sec-rollout">
          {r.order != null && <><dt>Order</dt><dd>{r.order}</dd></>}
          {r.staged && <><dt>Staged</dt><dd>
            {ramp && (
              <ol className="sec-ramp" aria-label="max-age ramp">
                {ramp.map((v) => (
                  <li key={v}><code>max-age={v}</code> <span className="muted">{spanOf(v)}</span></li>
                ))}
              </ol>
            )}
            <span className={ramp ? "muted" : undefined}>{r.staged}</span>
          </dd></>}
          {r.deploy_risk && <><dt>Deploy risk</dt><dd>{r.deploy_risk}</dd></>}
          {r.verify && <><dt>Verify</dt><dd><code>{r.verify}</code></dd></>}
          {r.rollback && <><dt>Roll back</dt><dd>{r.rollback}</dd></>}
        </dl>
      )}
      {fix.where && <p className="muted fix-meta">Where: {fix.where}</p>}
    </>
  );
}

/** Headings' site picture: which skip shape sits on which template, over the
 *  audit the pane is reading (brief v16d). The `siteNow` slot for `headings`. */
function HeadingsSiteNow({ part }: { part: Category }) {
  return (
    <Card className="now-card ho-blocks">
      <SkipsByTemplate shapes={part.shapes} />
    </Card>
  );
}

/** Title & description's site picture: every page's title and description width
 *  on one line (brief v16i). A bar opens its page in scope, which draws Part B's
 *  snippet card for it. The `siteNow` slot for `title-desc`; nothing to draw
 *  when the run recorded no lengths. */
function TitleDescSiteNow({ part, pages, pops = null, onPage }:
    { part: Category; pages: number | null; pops?: Populations | null;
      onPage?: (url: string) => void }) {
  if (!part.title_lengths) return null;
  return (
    <Card className="now-card">
      {/* Item 273 (row 13): a block under the part's h2 is an h3. */}
      <h3>Every page&rsquo;s length</h3>
      {/* `total` is the record count (PartPage's `pages`), so the foot can say
          how many of the record this audit's crawl drew (item 146z) - and it
          now names that denominator, because the part header above states a
          ratio over the SITE and two ratios over the same numerator must not
          read as a contradiction (item 155). */}
      <LengthStrips lengths={part.title_lengths} total={pages} pops={pops}
                    onPick={(url) => onPage && onPage(url)} />
    </Card>
  );
}

export const PART_RENDERERS: Record<string, Renderer> = {
  "title-desc": { now: TitleDescNow, body: TitleDescFixBody, copyLabel: "copy replacement",
                  copyWhen: (fix) => !isKeep(fix), siteNow: TitleDescSiteNow },
  headings: { now: HeadingsNow, body: HeadingsFixBody, copyLabel: "copy outline", copyText: outlineCopy,
              siteNow: HeadingsSiteNow,
              na: ["h3-sub-service", "h3-geo-map"] },
  images: { now: ImagesNow, body: ImagesFixBody, copyLabel: "copy markup",
            copyWhen: (fix) => attrsIn(fix.replacement).length > 0,
            // One card per replacement, not per check: a brief answers six
            // checks on one image with one piece of markup, and repeating
            // it six times would read as six changes (brief v15 step AR).
            collapse: true,
            na: ["img-sitemap-missing"] },
  // Brief v16 step AT. One card per replacement here too: a corrected
  // `@graph` closes several checks at once and repeating it per check
  // would read as several edits.
  schema: { now: SchemaNow, siteNow: SchemaSiteNow, body: SchemaFixBody, copyLabel: "copy JSON-LD",
            collapse: true },
  // Brief v17 step AW. What is copied is the anchor: a suggestion's
  // sentence is read, and the words that go in the markup are the one
  // thing an operator retypes.
  // Item 271 (row 8): "copy anchor" copies an anchor - the first
  // suggestion's, or an anchor card's new anchors - not the prose; and a
  // removal or a hand-off has none to copy.
  links: { now: LinksNow, siteNow: LinksSiteNow, body: LinksFixBody, copyLabel: "copy anchor",
           copyWhen: (fix) => !["remove", "handoff"].includes(fix.kind ?? ""),
           copyText: (rep, fix) => fix.suggestions?.length ? fix.suggestions[0].anchor
             : fix.kind === "anchor" && anchorSwaps(rep).length
               ? anchorSwaps(rep).map((s) => s.to).join("\n") : rep },
  // Brief v16e. Two blocks in one position, chosen by scope: the fix order
  // for the site, the page's own barriers when one page is in hand. They
  // answer different questions - "what first" and "where on this page" -
  // and neither is a smaller version of the other.
  // Item 226: the waterfall is the part's site picture. A11yNow drew it with
  // no page in hand, but with no `siteNow` the site branch never called it -
  // the same repair International and Mobile had (see `IntlSiteNow`).
  a11y: { now: A11yNow, siteNow: A11ySiteNow, body: A11yFixBody, copyLabel: "copy selector",
          copyFrom: (fix) => fix.replacement ? null
            : (fix.targets ?? []).find((t) => !t.startsWith("http") && !t.startsWith("/")) ?? null },
  // Brief v16h. One block, two states, and the column count is the number
  // of template groups that disagree - so a site serving the same headers
  // everywhere draws one column rather than a table of differences.
  // `siteScope`: the headers grid is a claim about every route, so it is
  // drawn with no page chosen. Without it the block sat behind a page
  // filter and drew nothing anywhere (item 136m step 1).
  security: { now: SecurityNow, body: SecurityFixBody, copyLabel: "copy header",
              siteScope: true },
  // Brief v17 step AX. Four analysis prompts write here and each carries
  // its own provenance on the checks table's Analysis heading, so
  // Coverage can be run without paying for Substance on every page.
  content: { now: ContentTabs, body: ContentFixBody, copyLabel: "copy replacement", siteScope: true },
  // Items 147 and 148 (brief v20). On the three-block layout so the brief's
  // fixes list, the set-aside strip and the confidence chip actually render
  // here -- they were built into this file and, until these two lines, never
  // reached either part: both fell through to the across-the-site layout, and
  // a screen check found zero fix cards on International beside a payload
  // holding a real fix. Site-wide, like Security: the strip is a claim about
  // the whole site. Neither part's "now" carries a narrowing control, which is
  // the reason crawl, indexability, urls and speed stay off this layout.
  //
  // `siteNow`, NOT `siteScope`, and that was got wrong first. As `siteScope`
  // parts they took the branch that skips `ChecksTable` entirely, so the
  // "N checks pass" and "not assessed" lines item 157 exists to keep honest
  // vanished from both parts: a screen check found six real fix cards on
  // Mobile and no checks table at all. `siteNow` is the slot that draws the
  // picture, THEN the checks table, THEN the fixes -- the order the slot's own
  // docstring calls structural. `now` draws the same block when a page is in
  // hand, since both blocks describe the site rather than one page.
  intl: { noPageBlock: true, now: IntlNow, siteNow: IntlSiteNow, body: SiteBriefFixBody,
          copyLabel: "copy change" },
  mobile: { noPageBlock: true, now: MobileNow, siteNow: MobileSiteNow, body: SiteBriefFixBody,
            copyLabel: "copy tag" },
  // Brief v25 step BP: the four parts whose "now" carries a narrowing control
  // come off the across-the-site layout. `siteNow`, not `siteScope`, for the
  // reason the note above gives: picture, then checks, then fixes.
  // Item 145 BH: reachability per agent, then the checks, then the brief's
  // fixes, and the register at the foot of the site picture.
  "ai-surface": { now: AiSurfacePageNow, siteNow: AiSurfaceSiteNow, body: AiSurfaceFixBody,
                  siteFoot: ({ part }) => <AiRegister brief={part.brief_ai_surface ?? null} />,
                  copyLabel: "copy change", copyText: aiSurfaceCopy },
  crawl: { noPageBlock: true, now: NoPageNow, siteNow: CrawlSiteNow, body: SiteBriefFixBody,
           copyLabel: "copy change" },
  indexability: { now: IndexabilityPageNow, siteNow: IndexabilitySiteNow,
                  // Item 277 (row 6): the same test as URLs - no copy over a
                  // hold or over a change to what the page already has.
                  body: SiteBriefFixBody, copyLabel: "copy change", copyWhen: isChange },
  urls: { noPageBlock: true, now: NoPageNow, siteNow: UrlsSiteNow, body: SiteBriefFixBody,
          copyLabel: "copy change", copyWhen: isChange },
  // Item 265: Speed's trace is per page, so page mode draws that page's own
  // gauges, sub-parts, filmstrip and waterfall (or says it was not traced),
  // and the checks table at page scope. `noPageBlock` suits Mobile and
  // International, whose pictures describe the site; it never suited Speed.
  // Screen audits round 3 (Speed UX-02): gated as URLs and Indexability
  // are, and not over advice that points elsewhere - "same TTFB fix as
  // above" (no row above), "verify LiteSpeed cache-hit".
  speed: { now: SpeedPageNow, siteNow: SpeedSiteNow, body: SiteBriefFixBody,
           copyLabel: "copy change", pageChecks: true,
           copyWhen: (f) => isChange(f) && !isPointerAdvice(f.replacement) },
  // Crawl & sitemaps and Indexability & canonicals are deliberately NOT here:
  // they are across-the-site parts whose "now" carries controls — the depth
  // histogram narrows the finding list, a canonical chain's check narrows the
  // record — and the AO three-block layout has no finding list for those to
  // act on. They keep the across-the-site layout (`anatomy.tsx`), where those
  // narrows work, and the v18 "now" content (counts, venn, matrix, canonical
  // map) is surfaced there (item 137, brief v18 steps AZ/BA, channel
  // 20260910-0740). AO for them waits on a site-scope slot that renders a
  // narrowable list — the same gap 147/148 inherit.
};

/** A page-mode `now` for a part with no page block (brief v25 step BP): the
 *  slot is required by the renderer type and `noPageBlock` keeps it undrawn. */
function NoPageNow() { return <></>; }

/** Links' site picture (item 271, row 6): the analysis's hub map - one row
 *  per hub with its spokes, how many link up, how many it links down to and
 *  its body inlinks - then how body inlinks and click depth fall across the
 *  live pages. The prompt says "the UI draws it"; nothing did. */
function LinksSiteNow({ part }: { part: Category; page: string; pages: number | null }) {
  const hubs = part.brief_hubs ?? [];
  const site = part.links_site ?? null;
  if (!hubs.length && !site) return null;
  // Screen audits round 3 (Links AC-02): the hub map is the analysis's, and
  // it sat undated under "What is drawn below was measured 3 Oct" - a model
  // reading of the 18 Sept crawl presented as that day's measurement. Its
  // own line says whose it is and which crawl it read.
  const by = [...(part.brief_runs ?? [])].sort((a, b) => b.at.localeCompare(a.at))[0];
  return (
    <Card className="now-card">
      <h4>Hubs</h4>
      {hubs.length > 0 && by && (
        <p className="muted links-hubs-source">
          From the analysis of {dayOf(by.at)}
          {by.crawl_at ? `, reading the crawl of ${dayOf(by.crawl_at)}` : ""}: not
          the automatic checks, and not re-measured since.
        </p>
      )}
      {hubs.length ? (
        <div className="table-scroll">
          <table className="findings">
            <thead><tr><th>Hub</th><th className="num">Spokes</th>
              <th className="num">Spokes linking up</th><th className="num">Hub linking down</th>
              <th className="num">Body inlinks</th></tr></thead>
            <tbody>
              {hubs.map((h, i) => (
                <tr key={h.hub ?? i}>
                  <td><code className="links-hub">{h.hub}</code></td>
                  <td className="num" title={(h.spokes ?? []).join("\n")}>{(h.spokes ?? []).length}</td>
                  <td className="num">{h.spokes_linking_up ?? "—"}</td>
                  <td className="num">{h.hub_linking_down ?? "—"}</td>
                  <td className="num">{h.inlinks_body ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No analysis has mapped this site's hubs yet; the Links analysis draws them.</p>
      )}
      {site && (
        <>
          <h4>Body inlinks per page</h4>
          <p className="muted links-dist">
            Over {site.counted} live pages, the start page aside; fewer than {site.minimum} is
            under-linked:{" "}
            {site.inlinks.map((b) => `${b.band}: ${b.pages}`).join(" · ")}
          </p>
          {(site.capped ?? 0) > 0 && (
            <p className="muted links-dist">
              Body links are counted from the first {site.cap} links stored per page, menus
              included; {site.capped} page{site.capped === 1 ? "" : "s"} reached that, so
              the pages they link to may be counted lower than they are.
            </p>
          )}
          <h4>Click depth</h4>
          <p className="muted links-dist">
            Over {site.pages} live pages:{" "}
            {site.depth.map((d) => `${d.depth}: ${d.pages}`).join(" · ")}
          </p>
        </>
      )}
    </Card>
  );
}

/** Crawl & sitemaps' site picture (brief v25 step BP): the v18 counts, venn
 *  and UA matrix, then the depth histogram as the narrowing control. */
function AiSurfaceSiteNow({ part }: { part: Category; page: string; pages: number | null }) {
  if (!part.ai_now) {
    return <Card className="now-card"><p className="muted">No audit of this site has stored a crawl to read reachability from.</p></Card>;
  }
  return (
    <>
      <AiReachability now={part.ai_now} brief={part.brief_ai_surface ?? null} />
      <AiLlmsFile brief={part.brief_ai_surface ?? null} />
    </>
  );
}

function AiSurfacePageNow({ part, page }: { part: Category; page: string; facts: Facts; bounds: Bounds;
                                           fixes: Fix[] }) {
  return part.ai_now
    ? <AiReachabilityPage now={part.ai_now} page={page} brief={part.brief_ai_surface ?? null} />
    : <></>;
}

function CrawlSiteNow({ part, narrow, onNarrow }: {
  part: Category; page: string; pages: number | null;
  narrow?: Narrow; onNarrow?: (kind: NarrowKind, value: string | null) => void;
}) {
  return (
    <>
      {part.crawl_now && <Card className="now-card"><CrawlNowBlock now={part.crawl_now} /></Card>}
      <CrawlDepthBlock depth={part.depth}
                       picked={depthPicked(part.depth, narrow?.kind === "depth" ? narrow.value : "")}
                       onPick={(n) => onNarrow?.("depth", n === null ? null : String(n))} />
    </>
  );
}

/** Indexability & canonicals' site picture: the counts and canonical map,
 *  then the chains, whose check ids narrow to that check and whose pages
 *  still open page scope. */
function IndexabilitySiteNow({ part, narrow, onNarrow, onPage }: {
  part: Category; page: string; pages: number | null;
  narrow?: Narrow; onNarrow?: (kind: NarrowKind, value: string | null) => void;
  onPage?: (url: string) => void;
}) {
  // Both spellings: a chain names its check bare (`canonical-mismatch`).
  const open = new Set(part.findings.flatMap((f) => [f.check_id, `${f.dimension}/${f.check_id}`]));
  return (
    <>
      {part.indexability_now && (
        <Card className="now-card"><IndexabilityNowBlock now={part.indexability_now} /></Card>
      )}
      <CanonicalChainsBlock chains={part.chains} page="" chain={null}
                            onPage={onPage ?? (() => undefined)}
                            onCheck={(c) => onNarrow?.("check",
                              narrow?.kind === "check" && narrow.value === c ? null : c)}
                            checks={open} />
    </>
  );
}

/** Indexability's page block: the chain of the page in scope, from its own
 *  facts. A node still opens its page in scope; the check id is not a narrow
 *  here, because one page has no population to narrow. */
function IndexabilityPageNow({ facts, part, page, onPage }: {
  facts: Facts; part: Category; bounds: Bounds; fixes: Fix[]; page: string;
  onPage?: (url: string) => void;
}) {
  return (
    <Card className="now-card">
      <CanonicalChainsBlock chains={part.chains} page={page}
                            chain={facts?.canonical_chain ?? null}
                            onPage={onPage ?? (() => undefined)}
                            // A check id on one page's chain leaves page scope
                            // for the site narrowed to that check: one page
                            // has no population of its own to narrow.
                            onCheck={(c) => {
                              const [path, query] = (window.location.hash || "").split("?");
                              const q = new URLSearchParams(query || "");
                              q.delete("page");
                              for (const k of ["depth", "template"]) q.delete(k);
                              q.set("check", c);
                              goto(`${path}?${q.toString()}`, { keepScope: false });
                            }}
                            checks={new Set(part.findings.flatMap((f) => [f.check_id, `${f.dimension}/${f.check_id}`]))} />
    </Card>
  );
}

/** URLs & parameters' site picture: the pattern table's rows narrow to a
 *  template. */
function UrlsSiteNow({ part, narrow, onNarrow }: {
  part: Category; page: string; pages: number | null;
  narrow?: Narrow; onNarrow?: (kind: NarrowKind, value: string | null) => void;
}) {
  if (!part.urls_now) return null;
  return (
    <Card className="now-card">
      <UrlsNowBlock now={part.urls_now}
                    picked={narrow?.kind === "template" ? narrow.value : null}
                    onTemplate={(t) => onNarrow?.("template", t)} />
    </Card>
  );
}

/** Speed's site picture: the vitals strip's templates narrow the fixes, and
 *  the pictures follow the template in hand. Images is the one other part it
 *  links to. */
/** Speed in page mode (item 265): the page's own trace. */
function SpeedPageNow({ part, page }: { part: Category; page: string }) {
  return (
    <SpeedNowBlock part={part} page={page}
                   onPart={(key) => goto(withPart(window.location.hash || "", key), { keepScope: false })} />
  );
}

function SpeedSiteNow({ part, pops, narrow, onNarrow }: {
  part: Category; page: string; pages: number | null; pops?: Populations | null;
  narrow?: Narrow; onNarrow?: (kind: NarrowKind, value: string | null) => void;
}) {
  return (
    <SpeedNowBlock part={part} pops={pops ?? null}
                   picked={narrow?.kind === "template" ? narrow.value : null}
                   onTemplate={(t) => onNarrow?.("template", t)}
                   onPart={(key) => goto(withPart(window.location.hash || "", key), { keepScope: false })} />
  );
}

/** The three verdicts a Mobile template or an International cluster takes
 *  (both installed schemas: "clean", "defective", or "partial"). */
//: Mapped onto `pill.tsx`'s own vocabulary, where the coloured fills are
//: reserved for `sev-*` ("how bad"). A verdict IS how bad, so defective and
//: partial take severity fills; clean is not a severity and takes the
//: non-severity `count-zero`. An invented `level-*` tone would have rendered
//: with no rule behind it at all.
const VERDICT_TONE: Record<string, Tone> = {
  clean: "count-zero", partial: "sev-medium", defective: "sev-high",
};

/** "3 clean, 1 partial" rather than a row of pills (items 147 E5, 148 G2).
 *
 *  A PARTIAL verdict links to Not assessable, because partial is the brief
 *  saying it could judge some of the group and not the rest -- and a reader
 *  who sees "partial" needs to reach what was not assessed, not guess at it.
 *  Counted from the brief's own verdicts; nothing here re-derives one.
 */
function VerdictTally({ verdicts }: { verdicts: string[] }) {
  const counts = new Map<string, number>();
  for (const v of verdicts) {
    const w = (v || "").trim().toLowerCase();
    if (w) counts.set(w, (counts.get(w) ?? 0) + 1);
  }
  if (!counts.size) return null;
  const order = ["defective", "partial", "clean"];
  const parts = [...counts].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  return (
    <p className="verdict-tally">
      {parts.map(([word, n], i) => (
        <Fragment key={word}>
          {i > 0 && ", "}
          {word === "partial"
            ? <a href="#not-assessable" className={`tone tone-${VERDICT_TONE.partial}`}>
                {n} partial
              </a>
            : <span className={`tone tone-${VERDICT_TONE[word] ?? "state-candidate"}`}>
                {n} {word}
              </span>}
        </Fragment>
      ))}
    </p>
  );
}

/** International's "now" (item 148 G1, G2, G6): the locales, the clusters,
 *  and -- where the brief was not dispatched -- why.
 *
 *  G6 comes FIRST and alone when it applies. A part whose brief the gate
 *  refused has no locales and no clusters to show, and a blank block under it
 *  would read as "checked, nothing found". The two refusals are drawn as the
 *  two different things they are (brief 160 step 6): `na` is settled and a
 *  zero under it is honest; `not_assessed` is not, and says so.
 */
function IntlNow({ part, siteId, onChanged }: { facts: Facts; part: Category; bounds: Bounds;
                             fixes: Fix[]; page: string;
                             siteId?: string; onChanged?: () => void }) {
  const gate = part.gate ?? null;
  // The door the gate's reason names (after item 274): stating a target
  // locale is the first of the two things that would change its answer.
  const target = siteId
    ? <TargetLocales siteId={siteId} stated={part.target_locales ?? null} onSaved={onChanged} />
    : null;
  if (gate) {
    const settled = gate.state === "na";
    return (
      <Card className="now-card intl-gate">
        <h4>{settled ? "Not applicable" : "Not assessed"}</h4>
        <p className={settled ? "muted" : "intl-gate-open"}>
          {settled
            ? "The analysis was not dispatched: this site presents one locale."
            : "Whether hreflang applies could not be determined, so the analysis was "
              + "not dispatched. This is not a finding that the site is "
              + "single-locale."}
        </p>
        {/* Item 274 (row 12): the evidence as Observed, in the layout the
            clusters below use, and the brief's prose rendered rather than
            dumped as source - backticks and all - in a <pre>. */}
        {gate.evidence ? (
          <div className="intl-locales">
            <p><span className="fix-lbl">Pages inspected</span> {gate.evidence.pages_inspected}</p>
            <p><span className="fix-lbl">Observed lang</span>{" "}
              {gate.evidence.lang_values.join(" · ") || "none"}
              {gate.evidence.lang_undeclared
                ? ` (${gate.evidence.lang_undeclared} page${gate.evidence.lang_undeclared === 1 ? "" : "s"} declare none)`
                : ""}</p>
            <p><span className="fix-lbl">Locale folders</span>{" "}
              {gate.evidence.locale_folders.map((f) => `/${f}/`).join(" · ") || "none"}</p>
            <p><span className="fix-lbl">Alternates</span>{" "}
              on {gate.evidence.alternates_on} of {gate.evidence.pages_inspected} pages</p>
          </div>
        ) : null}
        <details className="intl-gate-reason">
          <summary>the reason as the gate wrote it</summary>
          <Markdown source={gate.reason} />
        </details>
        {target}
      </Card>
    );
  }
  const loc = part.brief_locales ?? null;
  const clusters = (part.brief_clusters ?? []) as {
    cluster_id?: string; members?: string[]; locales?: string[];
    method?: string; closed?: boolean; x_default?: boolean;
    members_fetched?: number; verdict?: string }[];
  if (!loc && !clusters.length) {
    return target ? <Card className="now-card intl-now"><h4>Target locales</h4>{target}</Card> : <></>;
  }
  return (
    <Card className="now-card intl-now">
      <h4>Locales and clusters</h4>
      {loc && (
        <div className="intl-locales">
          <p><span className="fix-lbl">Observed</span>
             {(loc.observed ?? []).join(" · ") || "none"}</p>
          <p><span className="fix-lbl">Stated</span>
             {(loc.stated ?? []).join(" · ") || "none"}</p>
          {/* The conflict is the one line a reader acts on, so it is said in
              words and only where there is one. */}
          {loc.conflict && <p className="intl-conflict">{loc.conflict}</p>}
          {loc.basis && <p className="muted intl-basis">{loc.basis}</p>}
        </div>
      )}
      {clusters.length > 0 && (
        <>
          <VerdictTally verdicts={clusters.map((c) => c.verdict ?? "")} />
          <div className="table-scroll">
            <table className="findings intl-clusters">
              <thead><tr><th>Cluster</th><th>Locales</th><th>Method</th>
                <th>Closed</th><th>x-default</th><th className="num">Fetched</th>
                <th>Verdict</th></tr></thead>
              <tbody>
                {clusters.map((c, i) => (
                  <tr key={c.cluster_id ?? i}>
                    <td><code>{c.cluster_id}</code>{" "}
                      <span className="muted">{(c.members ?? []).length} member(s)</span></td>
                    <td>{(c.locales ?? []).join(" · ")}</td>
                    <td>{c.method}</td>
                    <td>{c.closed ? "yes" : "no"}</td>
                    <td>{c.x_default ? "yes" : "no"}</td>
                    {/* Fetched of members: a cluster whose alternates the crawl
                        never reached cannot have its reciprocity judged, and
                        this is the number that says so. */}
                    <td className="num">{c.members_fetched ?? 0} of {(c.members ?? []).length}</td>
                    <td><span className={`tone tone-${VERDICT_TONE[(c.verdict || "").toLowerCase()] ?? "state-candidate"}`}>
                      {c.verdict}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {target}
    </Card>
  );
}

/** Mobile's "now" (item 147 E1, E5): one row per template, the viewport
 *  string verbatim, the three render measurements, and the verdict.
 *
 *  **No 360 px thumbnail**, which E1 asks for, and that is a stated departure:
 *  the trace measures at 412 x 823 (perf's existing Pixel 5 emulation, brief
 *  160 step 1), and a 360 thumbnail would picture a width nothing on this row
 *  was measured at. The width is stated in the heading instead.
 *
 *  The viewport string is quoted exactly -- the prompt forbids normalising
 *  it, and all six parse checks read it character by character.
 */
function MobileNow({ part }: { facts: Facts; part: Category; bounds: Bounds;
                               fixes: Fix[]; page: string }) {
  const templates = (part.brief_templates ?? []) as {
    template?: string; pages?: number; viewport_raw?: string;
    viewport_rendered?: string; injected?: boolean; overflow_px?: number;
    tap_targets_small?: number; full_height_units?: string[];
    verdict?: string; verdict_model?: string | null; verdict_by?: string;
    verdict_faults?: string[]; verdict_holds?: string[] }[];
  if (!templates.length) return <></>;
  // Same verbatim tag, nothing injected, nothing rewritten on render.
  const sameViewport = templates.length > 1 && templates.every((t) =>
    t.viewport_raw === templates[0].viewport_raw && !t.injected
    && (!t.viewport_rendered || t.viewport_rendered === t.viewport_raw));
  return (
    <Card className="now-card mobile-now">
      <h4>Templates at 412 px</h4>
      {/* Item 274 (row 5): the rows are the analysis's, read from an older
          crawl than the automatic checks above them; said, so a count from
          18 Sept does not read as the site on the 29th. */}
      {part.brief_run?.at && (
        <p className="muted now-measured">
          From the analysis of {dayOf(part.brief_run.at)}
          {part.brief_run.crawl_at ? `, which read the crawl of ${dayOf(part.brief_run.crawl_at)}` : ""}.
        </p>
      )}
      <VerdictTally verdicts={templates.map((t) => t.verdict ?? "")} />
      {/* Item 274 (row 14): one viewport on every template is said once above
          the table, not repeated twelve times in a column. */}
      {sameViewport && (
        <p className="muted">
          Viewport on every template: <code className="mobile-vp">{templates[0].viewport_raw || "none"}</code>
        </p>
      )}
      <div className="table-scroll">
        <table className="findings mobile-templates">
          <thead><tr><th>Template</th><th className="num">Pages</th>
            {!sameViewport && <th>Viewport (verbatim)</th>}<th className="num">Overflow</th>
            <th className="num">Small taps</th><th>Full-height</th>
            <th>Verdict</th></tr></thead>
          <tbody>
            {templates.map((t, i) => (
              <tr key={t.template ?? i}>
                <td>{t.template}</td>
                <td className="num">{t.pages ?? ""}</td>
                {!sameViewport && (
                <td><code className="mobile-vp">{t.viewport_raw || "none"}</code>
                  {t.injected && <span className="tone tone-sev-high"> injected</span>}
                  {t.viewport_rendered && t.viewport_raw
                   && t.viewport_rendered !== t.viewport_raw
                   && <span className="muted"> → {t.viewport_rendered}</span>}</td>
                )}
                <td className="num">{`${t.overflow_px ?? 0} px`}</td>
                <td className="num">{t.tap_targets_small ?? 0}</td>
                {/* Item 274 (row 11): null is "not stated" (the reader kept no
                    unit), an empty list is none. */}
                <td>{t.full_height_units == null ? "not stated"
                     : t.full_height_units.join(" · ") || "none"}</td>
                <td><span className={`tone tone-${VERDICT_TONE[(t.verdict || "").toLowerCase()] ?? "state-candidate"}`}
                          title={t.verdict_faults?.length
                            ? `open on its pages: ${t.verdict_faults.join(", ")}`
                            : t.verdict_holds?.length
                              ? `held: ${t.verdict_holds.join(", ")}` : undefined}>
                  {t.verdict}</span>
                  {/* Item 274 (row 4): the verdict is the automatic checks'
                      reading of the template's pages; the analysis's own
                      word stays beside it where it differs. */}
                  {t.verdict_by === "analysis"
                    ? <span className="muted"> · analysis</span>
                    : t.verdict_model && t.verdict_model.toLowerCase() !== (t.verdict ?? "")
                      && <span className="muted"> · analysis said {t.verdict_model.toLowerCase()}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/** The two blocks in the `siteNow` slot's signature. Both read only `part`,
 *  so the same component serves the page-in-hand `now` and the whole-site
 *  `siteNow`; these adapt the props rather than duplicating the markup. */
function IntlSiteNow({ part, siteId, onChanged }: { part: Category; page: string; pages: number | null;
                                 pops?: Populations | null;
                                 onPage?: (url: string) => void;
                                 siteId?: string; onChanged?: () => void }) {
  return <IntlNow part={part} facts={{} as Facts} bounds={{} as Bounds}
                  fixes={[]} page="" siteId={siteId} onChanged={onChanged} />;
}

function A11ySiteNow({ part }: { part: Category; page: string; pages: number | null;
                                 pops?: Populations | null;
                                 onPage?: (url: string) => void }) {
  return <A11yNow part={part} facts={{} as Facts} bounds={{} as Bounds}
                  fixes={[]} page="" />;
}

function MobileSiteNow({ part }: { part: Category; page: string; pages: number | null;
                                   pops?: Populations | null;
                                   onPage?: (url: string) => void }) {
  return <MobileNow part={part} facts={{} as Facts} bounds={{} as Bounds}
                    fixes={[]} page="" />;
}

/** Worst first: what a reader can act on before what is already fine. */
const eligRank = (verdict: string) =>
  /not eligible/i.test(verdict) ? 0 : /degraded/i.test(verdict) ? 1
    : /none/i.test(verdict) ? 2 : 3;

/** Structured data across the site (item 242): the analysis's entity
 *  verdict, and its eligibility rows grouped. Ungrouped, the rows for 55
 *  pages named no page and read as one line said 55 times; grouped by
 *  (rich result, verdict, reason), each line says how many pages it is and
 *  opens to name them. */
function SchemaSiteNow({ part, onPage }: { part: Category; page: string; pages: number | null;
                                           pops?: Populations | null;
                                           onPage?: (url: string) => void }) {
  // Item 270 (row 9): grouped by (rich result, verdict), the count in the
  // line and each page's own reason under the disclosure. Keyed on the
  // reason too, the model's wording split one verdict into a line per page:
  // 24 lines over 45 pages, and the three totals nowhere.
  const groups = new Map<string, { rich: string; verdict: string;
                                   pages: string[]; reasons: Map<string, string> }>();
  for (const e of part.brief_eligibility ?? []) {
    const rich = e.rich_result || "none";
    const key = [rich, e.verdict.toLowerCase()].join("\u0000");
    const g = groups.get(key) ?? { rich, verdict: e.verdict, pages: [] as string[],
                                  reasons: new Map<string, string>() };
    if (e.page && !g.pages.includes(e.page)) {
      g.pages.push(e.page);
      if (e.reason) g.reasons.set(e.page, e.reason);
    }
    groups.set(key, g);
  }
  const rows = [...groups.values()].sort((a, b) =>
    eligRank(a.verdict) - eligRank(b.verdict) || b.pages.length - a.pages.length);
  if (!rows.length && !part.brief_entity) return null;
  return (
    <Card className="now-card sd-site">
      <h4>Across the site</h4>
      {part.brief_entity && (
        <p className="sd-entity">
          <b>Entity: {part.brief_entity.verdict}</b>
          {" "}<span className="muted">(site-wide)</span>
          {part.brief_entity.reason ? ` — ${part.brief_entity.reason}` : ""}
        </p>
      )}
      {rows.length > 0 && (
        <ul className="sd-eligibility">
          {rows.map((g) => (
            <li key={`${g.rich}-${g.verdict}`}>
              <code>{g.rich}</code>: <b>{g.verdict}</b>
              {" · "}{g.pages.length === 1 ? "1 page" : `${g.pages.length} pages`}
              <details className="sd-elig-pages">
                <summary>which, and why</summary>
                <ul>
                  {g.pages.map((p) => (
                    <li key={p}>
                      <button type="button" className="btn-link" onClick={() => onPage?.(p)}>
                        {pathOf(p)}
                      </button>
                      {g.reasons.get(p) ? <span className="muted"> — {g.reasons.get(p)}</span> : null}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The fix card body for the two site-wide brief-v20 parts. The change is
 *  what a reader pastes, so it is in a block to copy, with where it goes. */
/** Whether a card's replacement is a change to paste (item 266, row 6): a
 *  `rename`, `policy` or `markup`, or with no kind, anything that is not a
 *  "keep ..." or a "class: convention ..." note. Those say what not to do,
 *  and a copy button over them copied a sentence to paste into nothing. */
/** Title and description's own "no change" (screen audits round 3,
 *  title-desc AC-02): the bare word "keep", the brief's "leave it", whose copy
 *  button pasted "keep" into a meta description. Not `isChange`, whose "keep
 *  ..." rule would also take a title that begins "Keep your ...". */
export const isKeep = (fix: { replacement?: string | null }) =>
  /^keep[.!]?$/i.test((fix.replacement ?? "").trim());

export function isChange(fix: { kind?: string | null; replacement?: string | null;
                                current?: string | null }): boolean {
  // Item 277 (row 6): a hold written where the change goes ("held: needs
  // ..."), or a change to what the page already has (a canonical to itself),
  // is nothing to paste.
  const rep = (fix.replacement ?? "").trim();
  // And "no markup change here - resolve via ..." says there is none.
  if (/^(held|no (\w+ )?change)\b/i.test(rep)) return false;
  const norm = (s: string) => s.trim().toLowerCase().replace(/\/+$/, "");
  if (rep && fix.current && norm(rep) === norm(fix.current)) return false;
  if (fix.kind) return ["rename", "policy", "markup"].includes(fix.kind);
  return !/^\s*(keep\b|class:\s*convention)/i.test(fix.replacement ?? "");
}

/** A change that is an instruction to go and look, or a reference to
 *  another row, rather than text to paste (screen audits round 3, Speed
 *  UX-02). */
export function isPointerAdvice(rep: string | null | undefined): boolean {
  const r = (rep ?? "").trim();
  return /^(same\b|see\b|verify\b|investigate\b|check\b|confirm\b|as (above|below)\b)/i.test(r)
    || /\b(as above|as below|as the [\w/*-]+ template)\b/i.test(r);
}

function SiteBriefFixBody({ fix }: { fix: Fix; facts: Facts | null }) {
  return (
    <>
      <p className="fix-why">{fix.current || fix.note}</p>
      {/* Item 277 (row 5): a merged card the analysis wrote no change for
          carries the automatic checks' advice as its change. */}
      {!fix.replacement && fix.recommendation && (
        <p className="fix-new"><span className="fix-lbl">Do this: </span>{fix.recommendation}</p>
      )}
      {fix.checkId === "http-status-error" && (fix.targets?.length ?? 0) > 0 && (
        // Item 275 (row 10): where the link to it is, to update.
        <p className="muted fix-meta">
          Linked from {fix.targets!.map((t) => pathOf(t)).join(", ")}
        </p>
      )}
      {/* Item 275 (row 10): a finding about several URLs names them - "8
          sitemap URLs not reached" said eight and showed none. Behind a
          disclosure, with the total where the check kept fewer than it found. */}
      {fix.urls && fix.urls.length > 1 && (
        <details className="fix-urls">
          <summary>
            {fix.urls.length} URL{fix.urls.length === 1 ? "" : "s"}
            {fix.affectedTotal != null && fix.affectedTotal > fix.urls.length
              ? ` of ${fix.affectedTotal} found` : ""}
          </summary>
          <ul>
            {fix.urls.map((u) => <li key={u}><code>{pathOf(u)}</code></li>)}
          </ul>
        </details>
      )}
      {fix.replacement && (
        <div className="img-panel">
          <p className="fix-lbl muted">Change</p>
          {isChange(fix)
            ? <pre className="img-markup out-new" tabIndex={0}>{fix.replacement}</pre>
            : <p className="fix-rep">{fix.replacement}</p>}
        </div>
      )}
      {fix.where && <p className="muted fix-meta">Where: {fix.where}</p>}
      {/* Item 274 (row 8): the elements the row names, where it names them. */}
      {!fix.where && (fix.targets ?? []).length > 0 && (
        <div className="fix-meta">
          <span className="fix-lbl">Where</span>
          <ul className="muted">
            {(fix.targets ?? []).slice(0, TARGETS_SHOWN).map((t) => <li key={t}><code>{t}</code></li>)}
          </ul>
        </div>
      )}
    </>
  );
}

/** How many elements a card's finding names, from its own sentence ("3
 *  interactive element(s) under 24 x 24 CSS px"), or its listed targets
 *  (item 274, row 9). */
export function elementCount(f: { current?: string | null; targets?: string[] }): number {
  const m = /(\d+)\s+(?:interactive\s+)?element/.exec(f.current ?? "");
  return m ? Number(m[1]) : (f.targets ?? []).length;
}

/** How many of a card's named elements it lists (item 274, row 8). */
const TARGETS_SHOWN = 10;

/** How many cards of one check stand before `show all` (whole-site view). */
export const CARDS_PER_CHECK = 3;


function NowMeasured({ part, sweep, facts }: {
  part: Category; sweep: SweepRun | null; facts: Facts | null;
}) {
  const at = facts?.captured_at ?? sweep?.at;
  if (!at) return null;
  const range = !facts ? part.measured_range : null;
  const mixed = range && dayOf(range.from) !== dayOf(range.to);
  return (
    <p className="muted now-measured" data-measured={at}>
      {mixed ? `What is drawn below was measured ${dayOf(range.from)} to ${dayOf(range.to)}`
             : `What is drawn below was measured ${dayOf(at)}`}
      {!facts && sweep?.tier ? ` · ${sweep.tier}` : ""}
    </p>
  );
}

/** Item 251: the date and run of the measurement a card draws, in the
 *  provenance line's form ("measured 29 Sept · T2"). A card with a row in
 *  the record says its own; one without (a hold, a note) says the part's -
 *  the analysis that wrote it, or the automatic checks that read the part. */
function FixMeasured({ fix, sweep, briefAt }: {
  fix: Fix; sweep?: SweepRun | null; briefAt?: string | null;
}) {
  const ofBrief = fix.sources.includes("brief");
  const measured = fix.measuredAt ?? (!ofBrief || fix.sources.includes("sweep") ? sweep?.at : null) ?? null;
  const tier = fix.measuredAt ? fix.measuredTier : measured ? sweep?.tier : null;
  const analysed = fix.analysedAt ?? (ofBrief ? briefAt : null) ?? null;
  if (!measured && !analysed) return null;
  return (
    <span className="muted fix-measured" data-measured={measured ?? analysed ?? ""}>
      {measured ? `· measured ${dayOf(measured)}${tier ? ` · ${tier}` : ""}` : ""}
      {analysed ? `${measured ? " " : ""}· analysed ${dayOf(analysed)}` : ""}
    </span>
  );
}

function FixCard({ fix, facts, render, onCopy, copied, n, fixHeld = false,
                   awaiting = false, siteId, onStateChanged, earlierBrief = false,
                   sweep = null, briefAt = null, done = null, rivals = [] }: {
  /** The card's own "fixed?" control, where the part offers one (item 279,
   *  row 6). */
  done?: ReactNode;
  /** Other cards on this page proposing a different whole outline (screen
   *  audits round 3, Headings AC-04): each is a full replacement, so pasting
   *  two is pasting the duplicates one of them removes. */
  rivals?: { check: string; lines: number }[];
  /** The part's reference readings, for a card with no row of its own
   *  (item 251). */
  sweep?: SweepRun | null; briefAt?: string | null;
  /** The part's analysis was written under a brief that has since changed
   *  (item 249). */
  earlierBrief?: boolean;
  fix: Fix; facts: Facts | null; render: Renderer;
  /** Item 213: the hold is on the FIX, not the check - the check ran and
   *  fired on this page, and what waits on an input is the change. "Old
   *  format, not checked" sat directly under an "Old format" finding that
   *  fired on `/`. */
  fixHeld?: boolean;
  onCopy: (key: string, text: string) => void; copied: string | null;
  /** This card's number in the picture, where the part draws one (brief
   *  v16a step AT-b, RENDER_RULES section 12). The id is `fix-{n}` so a
   *  checklist row and a drill dock can scroll to it, and the badge is the
   *  same number the graph draws on the node - section 7 calls that the
   *  only agreement mechanism between the two. Null where the part has no
   *  picture, and the card is then exactly what it was. */
  n?: number | null;
  /** Item 237: a candidate on a check no sweep can raise - it waits for
   *  the operator, and the card says so and offers the three answers. */
  awaiting?: boolean; siteId?: string; onStateChanged?: () => void;
}) {
  const link = fix.needs ? heldLink(fix.needs) : null;
  return (
    <Card className={`fix-card${fix.needs ? " fix-held" : ""}`}>
      {/* The anchor sits on the card's head rather than on the card, so
          `Card` itself stays exactly as every other screen uses it.
          Widening a component every screen renders, for one caller, would
          put this step's diff on the render path of every browser guard in
          the suite - which is the difference between a red that is
          obviously not ours and one that needs an argument.

          A departure from RENDER_RULES section 12, which says the card
          carries the id. The head is the top of the card, so scrolling to
          it and scrolling to the card land in the same place, and the
          observer below tracks a box at the card's top rather than a
          230px one whose middle is what it would otherwise measure. */}
      {/* `data-fix-check` beside `data-fix-n` (brief v16d): the Headings
          ladder joins on the check id, because this part has no graph and
          so no numbers to join on. One card per check per page, which is
          what `fixesOf` keys on, so the selector names one card. */}
      <div className="fix-head" id={n ? `fix-${n}` : undefined}
           data-fix-n={n ?? undefined} data-fix-check={fix.checkId}>
        {n ? <i className={`sg-bd sg-bd-${fix.needs ? "held" : fix.severity}`}>{n}</i> : null}
        {/* Item 269: a verdict carries no severity - it is not a fault. */}
        {!closedByAnalysis(fix) && (
          <Pill tone={fix.needs ? "sev-info" : (`sev-${fix.severity}` as Tone)}>
            {fix.needs ? (fixHeld ? "fix held" : "Not assessable") : fix.severity}
          </Pill>
        )}
        {/* Item 211: the check's plain name, always. "<name> — not checked"
            put a fourth word for one state on the page ("not measured",
            "Not assessable", "held" were the other three), and on Content
            titled three cards with an empty name. The pill says the state. */}
        <b className="fix-name">{plainName(fix.checkId)}</b>
        <code className="fix-check">{fix.check}</code>
        {(fix.alsoResolves ?? []).map((c) => (
          <code key={c} className="fix-check fix-also">{c}</code>
        ))}
        {fix.kind && fix.kind !== "image" && (
          <Pill tone={fix.kind === "pipeline" || fix.kind === "policy" ? fix.kind : "template"}
                className="fix-kind">
            {fix.kind === "template" && fix.group
              ? `template: ${fix.group.replace(/^template:/, "")}`
              : fix.kind}
          </Pill>
        )}
        <span className="muted fix-src">· {fix.override && fix.sources.includes("sweep")
          ? "automatic checks flagged, analysis overrides"
          : fix.corroboratedBy?.length
          ? `analysis · the automatic checks raised the same target: ${fix.corroboratedBy.join(", ")}`
          : sourceWords(fix.sources, readingsDisagree(fix.current, fix.replacement))}</span>
        <FixMeasured fix={fix} sweep={sweep} briefAt={briefAt} />
        {/* Item 249: on each card the analysis wrote, not only on the
            provenance line above them. */}
        {earlierBrief && fix.sources.includes("brief") && (
          <span className="muted fix-earlier-brief">· analysed under an earlier brief</span>
        )}
        {/* Brief v20 (147 E4, 148 G5). Nothing renders where the brief stated
            none: a row the sweep measured carries no confidence, and drawing
            "low" there would grade the engine's own measurement as a guess. */}
        <ConfidenceChip value={fix.confidence} />
        {/* Item 269: a verdict waits for nobody - it is not a candidate fault. */}
        {fix.candidate && !closedByAnalysis(fix) && (
          <Pill tone="state-candidate">{candidateWord(awaiting)}</Pill>
        )}
        {/* Item 239 step 4: the automatic checks cleared this on every page
            the analysis named, after the analysis read it. */}
        {fix.supersededOn && (
          <span className="muted fix-superseded">· superseded on {stamp(fix.supersededOn)}</span>
        )}
        {/* Item 249: a model row on a check the automatic checks can raise,
            which they have not raised on this page since. It is not retired
            for the operator; it says so, and Withdraw is offered below. */}
        {fix.unseenSince && !fix.sources.includes("sweep") && (
          <span className="fix-unseen">· not seen by the automatic checks since {day(fix.unseenSince)}</span>
        )}
        {/* Only where there is a page. A site-scoped finding legitimately
            names none, and `pathOf("")` returns "" - so this rendered an
            empty <code> beside every one of them, which is the affordance
            that opens onto nothing the Record's own page control was
            already forbidden from being. Found while teaching
            `test_a_finding_that_names_no_page_offers_no_control` this
            layout (relay 136f), because a11y took a part page and that
            clause had nowhere left to stand. */}
        {/* Item 222: a per-template row is about its template. Item 217 filed
            it on the template's traced page instead of "/", but the card
            still named that one page as its subject - a template-wide 1.8 s
            TTFB read as one page's. The page stays, as where it was traced. */}
        {fix.template ? (
          <span className="muted fix-page">
            template <code>{fix.template}</code>
            {fix.page ? <> · traced on <code>{pathOf(fix.page)}</code></> : null}
          </span>
        ) : fix.kind === "policy" ? (
          // Item 277 (row 10): a policy is the site's, not its filing page's.
          <span className="muted fix-page">site-wide</span>
        ) : fix.page ? (
          // Item 275 (row 9): the page is a way into the page, as everywhere
          // else a page is named - its dossier, with every part's reading.
          <span className="muted fix-page">
            {siteId && /^https?:\/\//.test(fix.page)
              ? <a href={`#/sites/${siteId}/dossier/${encodeURIComponent(fix.page)}`}>
                  <code>{pathOf(fix.page)}</code></a>
              : <code>{pathOf(fix.page)}</code>}
          </span>
        ) : null}
        {/* Item 273 (row 7): the card's own row on the Record, every state,
            filtered to this check and page. Beside the page, not inside it:
            the page's span says the page and nothing else. */}
        {siteId && fix.page && !fix.template && fix.kind !== "policy" && (
          <span className="muted fix-record-at">
            <a className="fix-record"
               href={`#/sites/${siteId}?tab=all&state=all&find=${
                 encodeURIComponent(`${fix.check} ${pathOf(fix.page)}`)}`}>
              on the Record</a>
          </span>
        )}
        {((fix.replacement && (render.copyWhen?.(fix) ?? true)) || render.copyFrom?.(fix))
         && !fix.override && (
          <SecondaryButton className="fix-copy"
                  // Item 271 (row 8): every card's button read "copy anchor";
                  // each now names the page it is for.
                  aria-label={copied === fix.key ? undefined
                    : `${render.copyLabel ?? "copy replacement"} for ${fix.page ? pathOf(fix.page) : fix.check}`}
                  onClick={() => onCopy(fix.key, !fix.replacement ? render.copyFrom?.(fix) ?? ""
                    : render.copyText ? render.copyText(fix.replacement, fix) : fix.replacement)}>
            {copied === fix.key ? "copied" : (render.copyLabel ?? "copy replacement")}
          </SecondaryButton>
        )}
      </div>
      {fix.needs ? (
        <p className="fix-why">
          {/* Item 211: label and value apart in the TEXT, not only in the
              styling - the accessible name read "Why heldAUTHORS". And the
              table's sentence shape: "needs <input>". */}
          <span className="fix-lbl">Why held: </span>
          {fix.needs ? heldSays(fix.needs) : "the brief gave no reason"}
          {/* Item 267 (row 14): every held card says the next step, with the
              form where the reason names a record field. */}
          {link ? <> — <a href={link.href} onClick={goHandler(link.href)}>{link.label}</a>,
                     then re-run the analysis</> : "; then re-run the analysis."}
        </p>
      ) : fix.override ? (
        // Item 269: the analysis's verdict, as one sentence. Not the part's
        // body, which draws the row's text as a change to make and, on
        // Content, a footer telling the writer to put it first.
        <>
          {fix.sources.includes("sweep") && fix.current && <p className="fix-why">{fix.current}</p>}
          <p className="fix-why fix-override">
            <span className="fix-lbl">Analysis closes this: </span>
            {fix.replacement || (!fix.sources.includes("sweep") && fix.current)
              || fix.note || "the analysis found no fault here"}
          </p>
        </>
      ) : <render.body fix={fix} facts={facts} />}
      {fix.copyNotKept && !fix.replacement && !fix.needs && (
        <p className="muted fix-copy-not-kept">
          The analysis wrote a replacement and it was not kept ({fix.copyNotKept}),
          so this one is written by hand.
        </p>
      )}
      {rivals.length > 0 && !fix.needs && !fix.override && (
        <p className="muted fix-rivals" role="note">
          {/* Screen audits round 3, Headings AC-04: /web-design1/ carried a
              28-line outline on two cards and a 24-line one on a third. */}
          This page has {rivals.length === 1 ? "another card" : `${rivals.length} other cards`} with
          a different corrected outline ({rivals.map((r) =>
            `${plainName(r.check)}, ${r.lines} line${r.lines === 1 ? "" : "s"}`).join("; ")}
          , against {outlineLines(fix.replacement)} here). Each is a whole outline and they are
          not merged: paste one, and carry the other cards' changes into it.
        </p>
      )}
      {/* Item 270 (row 10): the answers after what they answer - under Now
          and Replace with, not above them. */}
      {awaiting && siteId && !closedByAnalysis(fix) && (
        <ConfirmControls fingerprints={fix.fingerprints ?? []} siteId={siteId} explain={false}
                         subject={`${plainName(fix.checkId)}, ${pathOf(fix.page)}`}
                         onStateChanged={onStateChanged} />
      )}
      {!awaiting && siteId && fix.unseenSince && !fix.sources.includes("sweep") && (
        <ConfirmControls fingerprints={fix.fingerprints ?? []} siteId={siteId} explain={false}
                         subject={`${plainName(fix.checkId)}, ${pathOf(fix.page)}`}
                         onStateChanged={onStateChanged} withdrawOnly />
      )}
      {/* Brief v20 (147 E3, 148 G4): inside the row and under the evidence,
          so a reader who has just read the evidence learns in the same breath
          that the verdict is a row up. Above the body it would read as a
          reason not to bother reading on. */}
      <SuppressedStrip checks={fix.suppressed} />
      {done}
    </Card>
  );
}

/** Block 3 — one card per failing (check, page) on the current scope. On
 *  the whole site the cards group under their check, three deep, so a
 *  check on forty pages does not bury the check on two. */
/** The template most of a group's pages share, where they share one
 *  (brief v14 step AP). One change there is the whole fix for that many of
 *  them, and the group says so once rather than repeating it per page.
 *
 *  Item 268 (row 6): by `templatesOf`'s rule - the one the skip table and
 *  the cause table use - not a looser one of its own. Two pages under one
 *  first segment were a "template" here and ten were needed there, so the
 *  skip table said "no shared template" above a group line naming one. */
export function templateOf(pages: string[]): { prefix: string; n: number } | null {
  const best = templatesOf(pages.map((u) => ({ fingerprint: u, urls: [u], state: "open",
                                               names_a_page: true })))
    .find((t) => t.prefix !== "");
  return best ? { prefix: best.prefix, n: best.pages } : null;
}

/** A held reason that waits on the owner's say-so for an active probe, rather
 *  than on an input (brief v20 step BD). */
// "authorisation" only: a reason saying a probe's BODIES were not captured
// (cloaking on twenty22) is a missing input, not a wait for the owner's say-so.
const AUTH = /authoris|authoriz/i;

/** Which of the three measurement states a part with nothing open is in
 *  (item 180). Accessibility is measured by the rendered pass, not by a check
 *  list, so its population is the pages that pass visited. */
export function partMeasure(part: Category, unmeasured: Map<string, string>) {
  if (part.key === "a11y") {
    const rendered = part.fix_order?.rendered ?? 0;
    return rendered > 0
      ? { state: "clean" as const, why: `the rendered pass read ${rendered} page${rendered === 1 ? "" : "s"} and found nothing` }
      : { state: "not-measured" as const, why: "the rendered pass visited no page in this audit, and accessibility is read only from rendered pages" };
  }
  const checks = (part.brief_checks?.length ? part.brief_checks : part.filed_checks ?? [])
    .map((c) => c.split("/").pop() as string);
  const keyless = (part.investigate ?? []).filter((t) => t.action === "needs_key").map((t) => t.tool);
  return measureOf({
    checks, unmeasured, gate: part.gate ?? null,
    noCheckWhy: keyless.length
      ? `no automatic check covers this part, and ${keyless.join(", ")} needs a provider key (Admin › Keys)`
      : undefined,
  });
}

function Fixes({ fixes, facts, render, page, part, cost, onGlow, siteId, onStateChanged,
                 sweep = null }: {
  siteId?: string; onStateChanged?: () => void;
  /** The part's reference sweep, for the cards' dates (item 251). */
  sweep?: SweepRun | null;
  fixes: Fix[]; facts: Facts | null; render: Renderer; page: string; part: Category;
  cost: string;
  /** Which node the picture should light up, as the reader scrolls (brief
   *  v16a step AT-b). Absent on every part that draws no picture. */
  onGlow?: (key: string | null) => void;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const wrap = useRef<HTMLElement>(null);
  const graph = part.graph ?? null;
  // Item 279 (row 6): Accessibility's cards can be marked fixed and re-checked
  // where they stand, through the one fix loop the Record uses - the same
  // route, the same page cap, the same four verdicts. A verified fix leaves
  // the open count, so the strip and the waterfall read it on the reload.
  const loop = useFixLoop(siteId ?? "", null, onStateChanged);
  const markable = (f: Fix): Markable | null => f.sweepFp ? {
    fingerprint: f.sweepFp, state: f.candidate ? "candidate" : "open", summary: f.current,
    source: "deterministic", names_a_page: Boolean(f.namesAPage), attempted_at: f.attemptedAt,
  } : null;
  useSeed(loop.seed, fixes.map(markable).filter((m): m is Markable => m !== null),
          fixes.map((f) => f.sweepFp).join(","));
  /** A card's number in the picture. Joined on the check id, which is the
   *  one field both sides carry: the engine numbered its findings from the
   *  same rows this list is built from, so the join is between two views of
   *  one list rather than between two lists.
   *
   *  A row the graph never saw gets no number and no badge - it is not
   *  renumbered to fit, because the numbers are the agreement and a
   *  locally-invented one would agree with nothing. */
  const numberOf = (f: Fix): number | null => {
    if (!graph) return null;
    const hit = graph.findings.find((g) => g.checks.includes(f.check));
    return hit ? hit.n : null;
  };
  // The scroll-link (the item's addition from layout 2): the card nearest
  // the top of the viewport makes its anchored nodes glow. One observer
  // over the block rather than a scroll handler, so it costs nothing while
  // the reader is still.
  useEffect(() => {
    if (!graph || !onGlow || !wrap.current) return;
    const cards = Array.from(wrap.current.querySelectorAll("[data-fix-n]"));
    if (!cards.length) return;
    const visible = new Set<Element>();
    const pick = () => {
      // Nearest the top of the viewport, which is the card the reader is
      // working on - not the largest intersection, which picks a long card
      // whose head has already gone past.
      //
      // Positions are read here rather than taken from the entry, because
      // an `IntersectionObserverEntry` carries the rect as it was when the
      // threshold was crossed. Scrolling within the visible set fires
      // nothing, so a stored rect goes stale and the glow sticks on
      // whichever card happened to enter first.
      let best: Element | null = null;
      let bestTop = Infinity;
      for (const el of visible) {
        const top = el.getBoundingClientRect().top;
        if (Math.abs(top) < Math.abs(bestTop)) { best = el; bestTop = top; }
      }
      if (!best) { onGlow(null); return; }
      const n = Number((best as HTMLElement).dataset.fixN);
      const f = graph.findings.find((g) => g.n === n);
      onGlow(f && f.anchor_keys.length ? f.anchor_keys[0] : null);
    };
    // The whole viewport, with no inset band. An inset was the first try and
    // was measured wrong twice: a short part page cannot scroll its last fix
    // card up to the middle - `scrollIntoView` ran out of document at
    // `scrollY 715` with the card's top still at 798 of a 1080 viewport - so
    // any band ending above that never intersected and the scroll-link
    // silently did not exist. Captured as `hasGlowClass: false` on all three
    // pages before this changed.
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) visible.add(e.target);
        else visible.delete(e.target);
      }
      pick();
    }, { threshold: 0 });
    cards.forEach((c) => io.observe(c));
    const onScroll = () => pick();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
    };
  }, [graph, onGlow, fixes, page]);
  const [openAll, setOpenAll] = useState<ReadonlySet<string>>(new Set());
  // Item 279 (row 3): a control elsewhere on the part (the waterfall's bars)
  // asks for a check's group: every card shown, then the first in view.
  useEffect(() => {
    const open = (e: Event) => {
      const check = (e as CustomEvent<string>).detail;
      setOpenAll((prev) => new Set(prev).add(check));
      requestAnimationFrame(() => document.querySelector(`[data-fix-check="${check}"]`)
        ?.scrollIntoView({ block: "center" }));
    };
    window.addEventListener(FIX_OPEN, open);
    return () => window.removeEventListener(FIX_OPEN, open);
  }, []);
  const copy = async (key: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(key); }
    catch { setCopied(null); }
  };
  // A check held for want of a list on the site record is the same answer
  // on every page, so it is one line rather than a card each (brief v14
  // step AP). It is not clean either way: it was not judged.
  // Security's held checks are lines too, not a card each (brief v20 step BD):
  // the brief returned 23 on twenty22, and a card per check buried the ten
  // real fixes. Read from the part's own domain map, so no second list.
  // Item 213: which (check, page) pairs FIRED, so a hold on one of them is a
  // hold on the fix. And a check held page by page for one and the same
  // reason is one line with its page count, the rule stated just above - it
  // arrived per page on Indexability (four identical "Noindex intent" cards)
  // and URLs (six), so the fold was never taken.
  const firing = new Set(fixes.filter((f) => !f.needs && !f.coverageNote)
                              .map((f) => `${f.checkId}|${pathOf(f.page)}`));
  const heldBy = new Map<string, Fix[]>();
  for (const f of fixes) {
    if (f.needs && !f.coverageNote) heldBy.set(f.checkId, [...(heldBy.get(f.checkId) ?? []), f]);
  }
  // Item 272: every hold, not only one repeated with one reason. A held card
  // was drawn among the faults, counted in its group's "N pages" and sliced
  // behind "show all", so Images' accounting line said "held" of fewer cards
  // than it drew. A hold on a fix whose check FIRED on that page stays a card
  // (item 213): there the finding is real and only the change waits.
  const repeated = [...heldBy.entries()]
    .filter(([checkId, fs]) => !fs.some((f) => firing.has(`${checkId}|${pathOf(f.page)}`)))
    .map(([checkId]) => checkId);
  const naChecks = new Set([...(render.na ?? []), ...repeated,
    ...(part.key === "security"
      ? Object.values(part.sec_domains ?? {}).flatMap((d) => d.checks) : [])]);
  const na = fixes.filter((f) => f.needs && naChecks.has(f.checkId)
                                 && !f.coverageNote);
  // A coverage note is not a fix (item 180's ruling; audit F3, 2026-09-18).
  // `PRF/cwv-not-assessed` was Speed's sixth "Free check" where the part's own
  // count - the strip, the catalogue chip and the Record filter - is five, and
  // it drew a card under the heading Fixes saying there was something to fix
  // where the audit had not measured. It keeps its row in the check table
  // below, because a check that could not measure belongs in a table of
  // checks; what it does not belong in is a list of work.
  const notes = fixes.filter((f) => f.coverageNote);
  // One card per replacement rather than per check (brief v15 step AR): a
  // row that says it also resolves five others is one change, and the
  // card names all six. The checks it closes are dropped from the list so
  // they are not counted twice - here or in the clean line.
  // Except a removal (screen audits round 3, Structured data US-01): the
  // analysis's sameAs card said it also resolved twenty22's duplicate
  // Organization block, and its change added `subjectOf` - so the one
  // certain free fault on the home page had no card that removes it. A
  // second block is closed only by a change that removes one, so its card
  // stays unless the closer says so.
  const removes = (f: Fix) => /\b(remove|delete|drop|merge)\b/i.test(f.replacement ?? "");
  const closed = new Set(fixes.flatMap((f) => (f.alsoResolves ?? [])
    .filter((c) => !REMOVAL_CHECKS.has(c.split("/").pop() ?? c) || removes(f))
    .map((c) => `${c.split("/").pop()}|${f.image ?? ""}|${f.page}`)));
  // Screen audits round 3 (Headings AC-04): the cards on one page whose
  // corrected outlines differ, each named on the others.
  const rivalsOf = (f: Fix) => {
    if (part.key !== "headings" || !f.replacement || f.needs) return [];
    const mine = outlineCopy(f.replacement);
    if (!mine) return [];
    const seen = new Set<string>([mine]);
    return shownFixes
      .filter((o) => o !== f && o.page === f.page && o.replacement && !o.needs && !o.override)
      .filter((o) => {
        const theirs = outlineCopy(o.replacement);
        if (!theirs || seen.has(theirs)) return false;
        seen.add(theirs);
        return true;
      })
      .map((o) => ({ check: o.checkId, lines: outlineLines(o.replacement) }));
  };
  // Item 270: overtaken rows leave the cards for one folded line per check.
  const passed = new Map<string, Fix[]>();
  for (const f of fixes.filter(overtaken)) passed.set(f.check, [...(passed.get(f.check) ?? []), f]);
  const shownFixes = fixes.filter(
    (f) => !na.includes(f) && !f.coverageNote && !overtaken(f)
           && !(render.collapse
                && closed.has(`${f.checkId}|${f.image ?? ""}|${f.page}`)));
  // A held-only check is never clean, and it is `fixesOf` that keeps it
  // out: every one of them is a held fix on every page, so no second test
  // is needed here and a second one would be a place for the two to
  // disagree. Observed on Birch before that card existed, reading `6 checks
  // pass on this page: ... img-review-schema ...` about a check no engine
  // can run - which is the one sentence on this page a reader acts on
  // without opening anything.
  // Item 157. A check with no card is only a PASS if this run MEASURED it.
  // `part.not_assessed` names the ones it did not, keyed by the full
  // `DIM/check` id and valued with the reason, and BOTH clean lines on this
  // page read it. Before this, a run whose dimension list did not name the
  // part's dimension certified every check of that part: Acme's Links part
  // read "12 checks clean on every page this run fetched" on a run with no
  // LNK in it at all, and this file is where that sentence is written.
  //
  // THE RULE is stated in `clauditseo/playbook.py`; this is one of its
  // readers, beside `anatomy.tsx`'s own clean line and the payload's
  // `runs.not_assessed_payload`, which is where the reasons come from.
  const unmeasured = new Map(
    Object.entries(part.not_assessed ?? {})
      .map(([full, reason]) => [full.split("/").pop() ?? full, reason] as const));
  // Item 270 (row 6): a check a card says it also resolves is not a pass
  // on this page - the table's `resolvedBy` reading (item 220), which this
  // line did not apply: `schema-orphan-instance` read "passes on this page"
  // beside the card resolving it. A hold on `all` or `*` reaches the page
  // through `SITE_WIDE_PAGES` (item 269, row 3) and is a card here too.
  const clean = (part.brief_checks ?? [])
    .map((c) => c.split("/").pop() as string)
    .filter((c) => !fixes.some((f) => f.checkId === c
      || (f.alsoResolves ?? []).some((r) => (r.split("/").pop() ?? r) === c)))
    // Screen audits round 3 (Speed AC-01): a check filed for the site as a
    // whole names no page, so it can never have a card here and is no pass.
    .filter((c) => !(page && (part.site_level_checks ?? []).includes(c)));
  const dropped = part.brief_dropped ?? 0;
  // Item 180 (05-4): on a page with no JSON-LD, a check that validates the
  // markup cannot have a finding - it has nothing to read - so it is neither
  // a pass nor unmeasured. Only the check for absence can pass there.
  const noMarkup = part.key === "schema" && Boolean(page)
    && (facts?.schema_inventory ?? []).length === 0;
  const cannot = noMarkup ? clean.filter((c) => c !== "schema-missing-for-type") : [];
  // Item 269: on Content, the checks that do not read a page of this type are
  // not passes on it either; the line below says which and why.
  const notRead = part.key === "content" && page
    ? clean.filter((c) => (facts?.content_not_run ?? []).includes(c)) : [];
  const cleanMeasured = clean.filter((c) => !unmeasured.has(c) && !cannot.includes(c)
                                            && !notRead.includes(c));
  const fullOf = (c: string) => (part.brief_checks ?? []).find((f) => f.split("/").pop() === c) ?? c;
  const cleanModel = cleanMeasured.filter((c) => costOf(part, fullOf(c)) === "model");
  const cleanFree = cleanMeasured.filter((c) => !cleanModel.includes(c));
  /** Which of the two sections a card belongs to (brief v17 step AV3).
   *
   *  A replacement that closes checks from both groups is analysis - the
   *  model wrote the copy - and the free ids it also closes are named on
   *  the card, which is where they were already named. Filing it under
   *  "free" because one of the six checks it closes is free would credit
   *  the sweep with work it did not do, and would put a paid card in
   *  front of an operator who asked to see only the free ones. */
  const sectionOf = (f: Fix) =>
    [f.check, ...(f.alsoResolves ?? [])].some((c) => costOf(part, c) === "model")
      ? "model" : "free";
  return (
    <section className="part-fixes" id="part-fixes" ref={wrap}>
      <h3>Fixes</h3>
      {/* Item 266 (row 5): what the three answers do, once above the cards
          that offer them, not under each one. */}
      {shownFixes.some((f) => f.candidate && !f.needs && f.toConfirm) && (
        <p className="muted fix-meta">{CONFIRM_SAYS}</p>
      )}
      {/* Item 180 (05-3, 06-3): not "Nothing to fix" on a scope nothing
          measured. One of the three registered states, with its reason. */}
      {!shownFixes.length && !na.length && (
        <MeasureLine {...partMeasure(part, unmeasured)} />
      )}
      {/* What this list left out, said rather than dropped: the notes are in
          the check table above with the state `not measured`, and a reader who
          counts the cards is owed the difference (audit F3). */}
      {notes.length > 0 && (
        <div className="muted part-fix-notes">
          {/* Item 279: each note in its own words. "This audit did not
              collect what it needs" was said of `axe-sampled`, which is the
              rendered pass's sample - collected, and saying so. */}
          <p>{coverageNotes(notes.length)} not counted here: a statement of
             what the audit read, not something to fix.</p>
          <ul className="part-fix-notes-list">
            {notes.map((f) => (
              <li key={f.key}><code>{f.checkId}</code> {f.current}</li>
            ))}
          </ul>
        </div>
      )}
      {[...passed.entries()].map(([check, fs]) => {
        const latest = fs.map((f) => f.supersededOn as string).sort().slice(-1)[0];
        return (
          <details key={check} className="muted part-fix-overtaken">
            <summary>
              {fs.length} analysis row{fs.length === 1 ? "" : "s"} on <code>{check}</code>{" "}
              overtaken by the audit of {day(latest)}: the automatic checks have
              since read {fs.length === 1 ? "its page" : "their pages"} and did not raise it.
            </summary>
            <p className="part-fix-overtaken-pages">
              {fs.map((f) => pathOf(f.page)).join(" · ")}
            </p>
          </details>
        );
      })}
      {sectionsByWorst(shownFixes, sectionOf).map(([section, title], _i, order) => {
        const mine = shownFixes.filter((f) => sectionOf(f) === section);
        const held = na.filter((f) => sectionOf(f) === section);
        if (!mine.length && !held.length) return null;
        // Whether the checks table states this hold on the check's own row.
        const onTable = (f: Fix) => !page
          && !shownFixes.some((x) => x.checkId === f.checkId && !x.needs && !x.coverageNote)
          && !sweepOutranks(part, f.check, f.checkId, sweep?.at, unmeasured);
        // Item 266 (row 3): moved ahead of its usual place, it says why.
        const led = section === order[0][0] && section !== SECTIONS[0][0];
        const groups = new Map<string, Fix[]>();
        for (const f of mine) groups.set(f.checkId, [...(groups.get(f.checkId) ?? []), f]);
        // Item 279 (row 4): Accessibility's groups in the waterfall's order,
        // the step that removes the most instances first, so a bar pressed
        // lands on a group that stands where the bar does. A check with no
        // step keeps its place after them.
        const steps = part.key === "a11y" ? part.fix_order?.steps ?? [] : [];
        const stepOf = (checkId: string) => steps.find((s) => s.check === checkId) ?? null;
        // Item 276 (row 8): the analysis's own rollout order. Sorted by
        // severity, the order the operator paid for read 2, 11, 12, 4, 1, 6
        // ... down the page. The cards it placed come first, in its order; a
        // card it gave no place (twenty22's `dnssec`, an automatic Info row)
        // follows them in severity order rather than voiding the order for
        // the twelve it did place.
        const placed = mine.filter((f) => !f.needs && !f.coverageNote && !closedByAnalysis(f));
        const byRollout = placed.some((f) => typeof f.rollout?.order === "number");
        const firstOrder = (cards: Fix[]) =>
          Math.min(...cards.map((f) => f.rollout?.order ?? Number.MAX_SAFE_INTEGER));
        const ordered = steps.length
          ? [...groups.entries()].sort(([a], [b]) => {
              const ia = steps.findIndex((s) => s.check === a);
              const ib = steps.findIndex((s) => s.check === b);
              return (ia < 0 ? steps.length : ia) - (ib < 0 ? steps.length : ib);
            })
          : byRollout
            ? [...groups.entries()]
                .map(([k, cards]) => [k, [...cards].sort((x, y) =>
                  (x.rollout?.order ?? 0) - (y.rollout?.order ?? 0))] as [string, Fix[]])
                .sort(([, a], [, b]) => firstOrder(a) - firstOrder(b))
            : [...groups.entries()];
        return (
          <Fragment key={section}>
            <h4 className={`fixes-head fixes-head-${section}`}>
              {/* Item 208: checks with a finding, as the table heading says it,
                  and the cards said as cards rather than under the same word. */}
              {title}{" "}
              <span className="muted">
                {/* Item 270 (row 7): cards only. A count of checks here
                    could not be the table's: a card is placed by `sectionOf`
                    and one replacement folds several checks into a card under
                    another check's id (`schema-redundant-block` on twenty22),
                    so it read 10 under the table's 11 even by the table's
                    cost rule. The table counts checks; this counts cards. */}
                · {mine.length + held.length} card{mine.length + held.length === 1 ? "" : "s"}
                {led && " · holds the most severe fix"}
              </span>
              {folded(cost, section) && (
                <span className="muted fixes-folded">
                  {" · "}hidden by <code>free only</code>
                </span>
              )}
            </h4>
            {!folded(cost, section) && ordered.map(([checkId, unsorted]) => {
              // Item 274 (row 9): on Mobile, the page with the most elements
              // first within a check - the one a fix moves most.
              // Item 273 (row 5): on Title & description, the furthest past
              // the cut first.
              const ranked = part.key === "mobile"
                ? [...unsorted].sort((a, b) => elementCount(b) - elementCount(a))
                : part.key === "title-desc" && unsorted.some((f) => f.overPx != null)
                ? [...unsorted].sort((a, b) => (b.overPx ?? -1) - (a.overPx ?? -1)) : unsorted;
              // Item 270 (row 17): where the group line names a template, the
              // cards shown first are its members. "template /seo/*: 28 of 43"
              // stood over /about/, /privacy-policy/ and /seo-category/seo-local/.
              const sample = !page && ranked.length > CARDS_PER_CHECK
                && !stepOf(checkId) && !ranked.every((f) => f.needs)
                ? templateOf(ranked.map((f) => f.page)) : null;
              const cards = sample
                ? [...ranked.filter((f) => pathOf(f.page).startsWith(sample.prefix)),
                   ...ranked.filter((f) => !pathOf(f.page).startsWith(sample.prefix))]
                : ranked;
              const all = page || cards.length <= CARDS_PER_CHECK || openAll.has(checkId);
              const shown = all ? cards : cards.slice(0, CARDS_PER_CHECK);
              return (
                <Fragment key={checkId}>
                  {!page && cards.length > 1 && (() => {
                    // Item 279 (row 4): on Accessibility, the step's own kind and
                    // share - what the waterfall says of it - in place of a path
                    // prefix, which named a "template" for site chrome.
                    const step = stepOf(checkId);
                    // Item 268 (row 6): a group of holds has nothing to fix, so
                    // a template on it read as "fix this template" over none.
                    const tpl = step || cards.every((f) => f.needs) ? null
                      : templateOf(cards.map((f) => f.page));
                    return (
                      <p className="muted fix-group">
                        <code>{cards[0].check}</code> · {groupCount(checkId, cards)}
                        {step && <> · <span className="fix-template">
                          {kindShort(step.kind)} · on {step.pages} of {step.assessed} page
                          {step.assessed === 1 ? "" : "s"} this check assessed</span></>}
                        {tpl && <> · <span className="fix-template">
                          template <code>{tpl.prefix}*</code> — {tpl.n} of {cards.length}</span></>}
                        {part.key === "mobile" && checkId === "tap-target" && (() => {
                          // Item 274 (row 9): the shape across the site, said once
                          // above the cards: one control on every template is one fix.
                          const templates = (part.brief_templates ?? []) as { tap_targets_small?: number }[];
                          const withSmall = templates.filter((t) => (t.tap_targets_small ?? 0) > 0).length;
                          const traced = part.traced_pages ?? null;
                          const pages = new Set(cards.map((f) => pathOf(f.page))).size;
                          return traced ? <> · <span className="fix-template">
                            small targets on {pages} of {traced} traced page{traced === 1 ? "" : "s"}
                            {templates.length ? `, ${withSmall} of ${templates.length} templates` : ""}
                            {templates.length && withSmall / templates.length >= 0.75
                              ? ": likely one shared control" : ""}</span></> : null;
                        })()}
                      </p>
                    );
                  })()}
                  {shown.map((f) => (
                    <FixCard key={f.key} fix={f} facts={facts} render={render}
                             onCopy={copy} copied={copied} n={numberOf(f)}
                             rivals={rivalsOf(f)}
                             fixHeld={Boolean(f.needs) && firing.has(`${f.checkId}|${pathOf(f.page)}`)}
                             awaiting={f.candidate && !f.needs && Boolean(f.toConfirm)}
                             earlierBrief={!!part.brief_run?.brief_changed}
                             sweep={sweep} briefAt={part.brief_run?.at ?? null}
                             siteId={siteId} onStateChanged={onStateChanged}
                             done={part.key === "a11y" && siteId && markable(f)
                               ? <CardDone m={markable(f) as Markable} loop={loop} /> : null} />
                  ))}
                  {!all && (
                    <p className="fix-more">
                      <SecondaryButton
                              onClick={() => setOpenAll((prev) => new Set(prev).add(checkId))}>
                        show all {cards.length}
                      </SecondaryButton>
                    </p>
                  )}
                </Fragment>
              );
            })}

            {!folded(cost, section) && (() => {
              // Item 276 (row 4): on the whole part the checks table says each
              // of these "not assessable · needs ..." on its own row, so the
              // reason was on screen twice. Those are named on one line, each
              // a way to its row. A hold the table does not state keeps its
              // reason on a line of its own: a check that also fired (its row
              // reads open), or one the newer automatic reading outranks (its
              // row reads clean).
              const stated = page ? [] : [...new Set(held.filter((f) => onTable(f))
                                                       .map((f) => f.checkId))];
              const needsOf = (id: string) => held.find((f) => f.checkId === id)?.needs ?? "";
              const rest = [...new Map(held.filter((f) => !onTable(f)).map((f) => [f.needs ?? "",
                              held.filter((x) => !onTable(x) && x.needs === f.needs)])).entries()];
              // Security splits what it could not assess in two (brief v20
              // step BD): what waits on the owner's authorisation for an
              // active probe, and what waits on an input no crawl can supply.
              // Two different conversations with the client, so authorisation
              // first, each under one heading - the table-stated ids and the
              // reasons together under it.
              const security = part.key === "security";
              type Line = { auth: boolean; key: string; ids?: string[];
                            needs?: string; group?: Fix[] };
              const lines: Line[] = [
                ...(security
                  ? [{ auth: true, key: "ref-auth", ids: stated.filter((id) => AUTH.test(needsOf(id))) },
                     { auth: false, key: "ref-input", ids: stated.filter((id) => !AUTH.test(needsOf(id))) }]
                  : [{ auth: false, key: "ref", ids: stated }]).filter((l) => l.ids.length > 0),
                ...rest.map(([needs, group]) => ({ auth: security && AUTH.test(needs), key: needs,
                                                   needs, group })),
              ].sort((a, b) => Number(!a.auth) - Number(!b.auth));
              return lines.map((l, i) => (
                <Fragment key={l.key}>
                  {security && (i === 0 || lines[i - 1].auth !== l.auth) && (
                    <p className="fix-na-head">{l.auth ? "Pending authorisation" : "Missing input"}</p>
                  )}
                  {l.ids ? (
                    <p className="muted fix-na fix-na-ref">
                      {l.ids.map((id, k) => {
                        const mine = held.filter((f) => f.checkId === id);
                        const n = new Set(mine.map((f) => pathOf(f.page)).filter(Boolean)).size;
                        return (
                          <Fragment key={id}>
                            {k > 0 && " · "}
                            <button type="button" className="btn-link"
                                    onClick={() => document.getElementById(checkRowId(mine[0].check))
                                      ?.scrollIntoView({ block: "center" })}>
                              {id}
                            </button>
                            {n > 1 ? ` on ${n} pages` : ""}
                          </Fragment>
                        );
                      })}{" "}
                      not assessable — the reason is on {l.ids.length === 1 ? "its row" : "their rows"} in
                      the checks table
                    </p>
                  ) : (
                    <p className="muted fix-na">
                      {[...new Set((l.group ?? []).map((f) => f.checkId))].join(" · ")} not assessable
                      {(() => {
                        // Item 266 (row 10): the pages, named - the first three
                        // and how many more - so the line says where.
                        const paths = [...new Set((l.group ?? []).map((f) => pathOf(f.page))
                                                 .filter((p) => p && !SITE_WIDE_PAGES.has(p)))];
                        // Narrowed to one page, the page is the scope: not said again.
                        if (!paths.length || page) return "";
                        const shown = paths.slice(0, 3).join(", ");
                        return ` on ${paths.length === 1 ? shown : `${paths.length} pages (${shown}`
                          + (paths.length > 3 ? ` and ${paths.length - 3} more)` : ")")}`;
                      })()} — {heldSays(l.needs ?? "")}
                      {heldLink(l.needs ?? "")
                        ? <> — <a href="#/admin?tab=sites" onClick={goHandler("#/admin?tab=sites")}>
                            set it on Admin › Sites</a></>
                        : "."}
                    </p>
                  )}
                </Fragment>
              ));
            })()}
          </Fragment>
        );
      })}
      {/* The controls the brief declined for this site, with why (brief v20
          step BD): muted and under the fixes, because it is the list of
          things NOT to do, and an operator should read it after the list of
          things to do rather than instead of it. */}
      {(part.brief_security?.do_not_spend_on ?? []).length > 0 && (
        <p className="muted fix-dnso">
          Do not spend on:{" "}
          {(part.brief_security?.do_not_spend_on ?? [])
            .map((d) => `${d.control} — ${d.why}`).join(" · ")}
        </p>
      )}
      {/* On the whole site the checks table carries this line; here it
          is the one-page answer to "what was measured and passed". */}
      {/* Items 274, 276: an analysis check with no row on this page is not
          a pass on it - the briefs omit passes - so it is said apart. */}
      {page && cleanFree.length > 0 && (
        <p className="cause-clean-line">
          {cleanFree.length} check{cleanFree.length === 1 ? "" : "s"}{" "}
          pass on this page: {cleanFree.join(" · ")}
        </p>
      )}
      {page && cleanModel.length > 0 && (
        <p className="cause-unreturned-line muted">
          {cleanModel.length} check{cleanModel.length === 1 ? "" : "s"} the analysis
          returned no row for on this page, which is not a pass: {cleanModel.join(" · ")}
        </p>
      )}
      {notRead.length > 0 && (
        <p className="muted cause-cannot-line" data-measure="not-measured">
          {notRead.length} check{notRead.length === 1 ? "" : "s"} {MEASURE_WORD["not-measured"]} on
          this page: {notRead.join(" · ")} {notRead.length === 1 ? "does" : "do"} not read{" "}
          {facts?.page_type ? `a ${facts.page_type} page` : "a page the site record gives no type"}
        </p>
      )}
      {page && cannot.length > 0 && (
        <p className="muted cause-cannot-line" data-measure="cannot">
          {cannot.length} check{cannot.length === 1 ? "" : "s"} {MEASURE_WORD.cannot} on
          this page, which carries no JSON-LD: {cannot.join(" · ")}
        </p>
      )}
      {/* Item 157: what this run could not measure, grouped by reason so the
          line reads as one sentence per cause rather than one per check.
          Said rather than omitted - a check that silently vanished from the
          page is the same absence-as-answer this item forbids. */}
      {page && byReason(clean, unmeasured).map(([reason, ids]) => (
        <p className="cause-dark-line" key={reason}>
          {ids.length} check{ids.length === 1 ? "" : "s"}{" "}
          {part.gate?.state === "na" ? "not applicable" : "not assessed"}{" "}
          — {reason}: {ids.join(" · ")}
        </p>
      ))}
      {/* Item 209: the rows, not a pointer at a report the page does not
          link. A disclosure, because a list of what the contract refused is
          for the reader who asks, and the count is for everyone. */}
      {dropped > 0 && (
        <details className="muted rep-dropped">
          <summary>{dropped} row{dropped === 1 ? "" : "s"} dropped</summary>
          {/* Item 277 (row 14): grouped by reason, each reason said once with
              the checks it dropped, rather than the same sentence eleven times. */}
          <ul className="rep-dropped-rows">
            {droppedByReason(part.brief_dropped_rows ?? []).map((g) => (
              <li key={g.key}>
                {g.rows.length} row{g.rows.length === 1 ? "" : "s"}: {g.reason}
                {" "}({g.checks.map(([c, n]) => (n > 1 ? `${c} ×${n}` : c)).join(", ")})
                {g.rows.some((d) => d.page) && (
                  <details className="rep-dropped-pages">
                    <summary>which pages</summary>
                    {g.rows.map((d, i) => (
                      <div key={i}><code>{d.check || "no check named"}</code>
                        {d.page ? <> · <code>{pathOf(d.page)}</code></> : null}
                        {g.rows.length > 1 && d.reason ? <> · {d.reason}</> : null}</div>
                    ))}
                  </details>
                )}
              </li>
            ))}
          </ul>
          {(part.brief_dropped_rows ?? []).length < dropped && (
            <p>{dropped - (part.brief_dropped_rows ?? []).length} more are in the report.</p>
          )}
        </details>
      )}
    </section>
  );
}

/** Dropped rows by reason (item 277, row 14). Two reasons that differ only
 *  in a count or a path ("on 4 pages", "on /about/") are one reason; the
 *  first row's wording names the group. */
export function droppedByReason(rows: { check: string; page: string | null; reason: string }[]) {
  const groups = new Map<string, { key: string; reason: string; rows: typeof rows;
                                   checks: [string, number][] }>();
  for (const d of rows) {
    const key = (d.reason || "").replace(/\/\S*/g, "/").replace(/\d+/g, "#").trim().toLowerCase();
    const g = groups.get(key) ?? { key, reason: d.reason || "no reason given", rows: [], checks: [] };
    g.rows.push(d);
    const c = d.check || "no check named";
    const at = g.checks.find(([name]) => name === c);
    if (at) at[1] += 1; else g.checks.push([c, 1]);
    groups.set(key, g);
  }
  // The group's wording states a figure only where every row agrees on it,
  // and a range where they differ (screen audits round 3, title-desc AC-01:
  // "replacement 578 px" was said of ten rows measuring 431 to 578 px).
  for (const g of groups.values()) {
    const parts = g.reason.split(/(\d+)/);
    const each = g.rows.map((d) => (d.reason || "").split(/(\d+)/))
      .filter((s) => s.length === parts.length);
    g.reason = parts.map((piece, i) => {
      if (i % 2 === 0) return piece;
      const ns = each.map((s) => Number(s[i]));
      const lo = Math.min(...ns), hi = Math.max(...ns);
      return lo === hi ? piece : `${lo}–${hi}`;
    }).join("");
  }
  return [...groups.values()].sort((a, b) => b.rows.length - a.rows.length);
}

/** Block 2 on the whole site — every check the part's briefs may emit,
 *  what each source counted, and where it stands. */
function ChecksTable({ part, fixes, cost, pops, siteScope = false, sweepAt = null,
                       whole = false, onePage = false }: {
  part: Category; fixes: Fix[]; cost: string;
  /** Page mode: a clean line is about this page, not every page the audit
   *  read, and a check filed for the site as a whole is neither (screen
   *  audits round 3, Speed AC-01). */
  onePage?: boolean;
  /** The whole part, neither one page nor a narrow: only then can the
   *  analysis's accounting be held to the run's kept-row count. */
  whole?: boolean;
  /** When the automatic checks last read this part (item 251): a row's state
   *  is the newer measurement's, so an analysis that held a free check before
   *  that reading does not outrank it. */
  sweepAt?: string | null;
  /** The populations a count may be counted over (item 155). */
  pops: Populations | null;
  /** The part's renderer is site-scoped (security, content), so every count
   *  in it is a fact about the site as one subject and none of them is
   *  dressed as a page ratio. */
  siteScope?: boolean;
}) {
  // Item 157, the same map `Fixes` builds and for the same reason: a row with
  // no findings is only clean if this run measured its check. Built here rather
  // than passed in, because both components already take `part` and a prop
  // would be a second place for the two to disagree about what a pass is.
  const unmeasured = new Map(
    Object.entries(part.not_assessed ?? {})
      .map(([full, reason]) => [full.split("/").pop() ?? full, reason] as const));
  // Item 180 (ruling 20260918-0402): the table and the Fixes list read one
  // set. A check the engine filed under this part that no brief enumerates -
  // `ONP/title-entity-incomplete`, 30 findings in Fixes and no row, so the
  // table summed 185 under "Free checks · 215" - is a row like any other.
  const tableChecks = [...(part.brief_checks ?? [])];
  for (const filed of part.filed_checks ?? []) {
    const id = filed.split("/").pop() as string;
    // Item 277 (row 16): with its dimension, as the brief's rows carry it -
    // `canonical-missing` stood bare among `TEC/...` rows.
    const dim = filed.includes("/") ? null
      : part.findings.find((f) => f.check_id === id)?.dimension ?? null;
    if (!tableChecks.some((c) => (c.split("/").pop() as string) === id)) {
      tableChecks.push(dim ? `${dim}/${filed}` : filed);
    }
  }
  // Item 279 (row 7): Accessibility's registered checks too, so the nine
  // that ran and filed nothing are said clean rather than left unsaid.
  // `axe-render-failed` says the rendered pass failed, which is no reading
  // of a page, so it is not listed as clean.
  if (part.key === "a11y") {
    for (const id of part.registered_checks ?? []) {
      if (id === "axe-render-failed") continue;
      if (!tableChecks.some((c) => (c.split("/").pop() as string) === id)) tableChecks.push(id);
    }
  }
  const tracedChecks = new Set((part.trace_derived ?? []).map((c) => c.split("/").pop() ?? c));
  const rows = tableChecks.map((full) => {
    const checkId = full.split("/").pop() as string;
    // Item 270: an overtaken analysis row is the automatic checks' to answer,
    // and they cleared it; the row reads their state.
    const mine = fixes.filter((f) => f.checkId === checkId && !overtaken(f));
    // Items 206 and 208: one classification, read by every count column. A
    // held row (`needs`) and a coverage note say something about the check
    // and nothing about the site, so they are in State and in no count: the
    // table read "ANALYSIS 2 · 2 of 45 pages crawled · not assessable" on
    // Schema, and a held Speed row put a 0 in PAGES where the rule is a dash.
    // Item 269: a verdict is not a finding. An analysis row that closes its
    // check counts nowhere; on a page the automatic checks also raised, the
    // card counts as theirs and not as the analysis's.
    const counted = mine.filter((f) => !f.needs && !f.coverageNote && !closedByAnalysis(f));
    const sweep = counted.filter((f) => f.sources.includes("sweep")).length;
    const brief = counted.filter((f) => f.sources.includes("brief") && !f.override).length;
    const heldN = mine.filter((f) => f.needs).length;
    // Item 220 (AC-07): a card that says it also resolves this check. On
    // twenty22 `schema-catalog-mismatch` read "clean on every page" while the
    // /website-seo/ card listed it as resolved, and `schema-entity-thin` read
    // "not assessable" on the page a wiring card fixed it on. Not counted -
    // the finding is the card's own check's - but never clean or held.
    const resolvedBy = fixes.filter(
      (f) => !f.needs && !f.coverageNote && f.checkId !== checkId
             && (f.alsoResolves ?? []).some((c) => c.split("/").pop() === checkId));
    // **The one count this item is actually about.** Prevalence is affected
    // OF ASSESSED: the denominator is the crawl and never the record, because
    // 23 of Twenty22's 68 stored pages were never fetched and a page nobody
    // looked at cannot be evidence that the fault is absent. `35 of 68` was
    // already a ratio - it had the wrong bottom half.
    //
    // And over EVERY page each finding names (item 206), not its first: the
    // engine files a site-wide fault as one finding over all its pages, so
    // `img-logo` - the logo on 31 pages - read "1 of 45" while a check that
    // files one finding per page read 31. `prevalence` counts a page once, so
    // findings that overlap do not add up past the pages they share.
    const named = counted.flatMap((f) => (f.urls?.length ? f.urls : [f.page]));
    // Item 279: an axe rule is read on the pages the rendered pass visited,
    // not on the crawl. `axe-color-contrast` on all 5 rendered pages read
    // "5 of 45 pages crawled" - an 11% problem - beside a waterfall whose
    // axis said every rendered page had it.
    // Item 274: and a trace-derived check on the pages the browser traced -
    // Mobile's six read "of 45 pages crawled" for a reading taken on 12.
    const rendered = part.fix_order?.rendered ?? 0;
    const tracedN = part.traced_pages ?? 0;
    const own = part.samples?.[checkId];
    const sample = siteScope ? null
      : own?.n ? { n: own.n, basis: own.basis }
      : checkId.startsWith("axe-") && rendered > 0 ? { n: rendered, basis: "rendered" }
      : tracedChecks.has(checkId) && tracedN > 0 ? { n: tracedN, basis: "traced" }
      : null;
    const counted0 = sample
      ? { count: { value: Math.min(new Set(named.filter(Boolean).map(pathKey)).size, sample.n),
                   population: "crawl" as const, basis: sample.basis, of: sample.n },
          unfetched: 0 }
      : prevalence(named, pops, siteScope);
    // Item 276 (row 6): an emitter that capped its URL list (`sri-missing`
    // keeps 20 of 45) stores what it found; PAGES reads that, not the cap.
    // Never past the population it is a share of. On a site-scoped part too:
    // Security is one, and `sri-missing` is the row that read 20 there.
    // And only where every page the row names is in the crawl (screen audits
    // round 3, Crawl AC-01): `unreachable` read "8 of 45 pages crawled" for
    // eight pages never reached, and `http-status-error` "1 of 45" for none.
    const found = Math.max(0, ...counted.map((f) => f.affectedTotal ?? 0));
    const allInCrawl = counted0.count.value > 0 && counted0.unfetched === 0
      && !(counted0.errored ?? 0);
    const pages = allInCrawl && found > counted0.count.value
      ? { ...counted0, count: { ...counted0.count,
                                value: counted0.count.of != null ? Math.min(found, counted0.count.of)
                                                                 : found } }
      : counted0;
    // Item 272: every image a card names, not its first. A sweep row names
    // all the images it found on its page (`images`) and one `image` at
    // most, so `img-no-srcset` - 7 images on / and 5 on /about/ - read 2. A
    // page-total check (`img-weight-budget`) names none and draws a dash.
    const images = new Set(counted.flatMap(
      (f) => f.images?.length ? f.images : f.image ? [f.image] : [])).size;
    // Blocks, counted once for a block the site repeats (brief v16 step
    // AT). The row already carries every page it covers, so counting the
    // rows would count an Organization node twelve times for one edit.
    const blocks = new Set(counted.map((f) => f.block).filter(Boolean)).size;
    const severity = mine.length
      ? mine.map((f) => f.severity).sort((a, b) => RANK.indexOf(a) - RANK.indexOf(b))[0]
      : "info";
    // A row whose only rows are coverage notes was not measured, and `open` is
    // registered as "a fault the latest audit still found" (audit F3). The
    // registry's own word for this is `not-assessed` - "not measured" - and
    // the prevalence cell reads an em dash rather than `0`, because a 0 in a
    // PAGES column reads as clean: "a zero where nothing looked is not a zero
    // where nothing is wrong", as the registry says of `lane-measured`.
    const allNotes = Boolean(mine.length) && mine.every((f) => f.coverageNote);
    // From the counted rows only (item 220, AC-06): a held row is not a
    // candidate, so one candidate beside one hold fell through to "open" -
    // the confirmed state - on `schema-sameas-missing`, a model-only row.
    // Item 237: a candidate on a check no sweep can raise waits for the
    // operator, not for a second audit - "candidate" says the latter.
    // Item 251: ranked by the measurement's date. On Crawl a 23 Sept analysis
    // held three free checks ("not assessable · needs ...") over the 29 Sept
    // sweep that had measured each and raised nothing. The automatic checks
    // read the check after the analysis wrote its hold, so their reading is
    // the row's state; the hold stays visible as a card under Fixes.
    const sweepOutranksHold = heldN > 0 && sweepOutranks(part, full, checkId, sweepAt, unmeasured);
    const state = counted.length
      ? (counted.every((f) => f.candidate)
          ? candidateWord(counted.every((f) => f.toConfirm))
          : counted.some((f) => f.regressed) ? entry("state-regressed").word : "open")
      : resolvedBy.length ? `resolved by the ${resolvedBy[0].check} fix`
      : !mine.length ? "clean"
      : allNotes ? MEASURE_WORD["not-measured"]
      : mine.some(closedByAnalysis) && mine.every((f) => closedByAnalysis(f) || f.coverageNote)
        ? "analysis closes this"
      : sweepOutranksHold ? "clean"
      : heldN ? `not assessable · ${heldSays(mine.find((f) => f.needs)?.needs ?? "")}`
      : "open";
    // Item 275: a hold the newer automatic reading outranks is that reading's
    // pass - the check joins the clean line beside the others the sweep
    // measured, and the hold stays a card under Fixes with its date.
    const outranked = sweepOutranksHold && !counted.length && !resolvedBy.length;
    // Item 267: a row about the site as one subject has no page count.
    // Item 277 (row 10): a check whose every card is a policy is about the
    // site too - PAGES is a dash, not the one page the model named.
    const mineCards = fixes.filter((f) => f.checkId === checkId);
    const siteRow = part.samples?.[checkId]?.basis === "site"
      || (mineCards.length > 0 && mineCards.every((f) => f.kind === "policy"));
    // Row 4: a raised row naming no page draws a dash, not the 0 that reads
    // as clean beside it.
    const noPage = !named.some(Boolean);
    return { full, checkId, sweep, brief, pages, images, blocks, severity, state,
             allNotes, n: mine.length + resolvedBy.length, counted: counted.length, outranked,
             siteRow, noPage,
             // Items 277 (row 13), 273 (row 13): a row whose only rows are
             // holds has no severity of its own - the model's hold carries
             // "info", which is not the check's.
             held: state.startsWith("not assessable") };
  });
  // Item 279 (row 8): whether the table carries an Analysis column at all.
  const analysisCol = part.catalogued !== false || rows.some((r) => r.brief > 0);
  const raised = rows.filter((r) => r.n > 0);
  // The column only where a row is about an image (brief v15 step AR):
  // an empty column on every other part is furniture.
  const anyImages = rows.some((r) => r.images > 0);
  const anyBlocks = rows.some((r) => r.blocks > 0);
  return (
    <section className="part-checks">
      {/* Two sections, free first (brief v17 step AV3). The order is the
          argument: what the audit found for nothing, then what a model was
          asked to read on top of it. Each heading carries its own count,
          and Analysis carries the brief that produced it and what it cost
          - a heading that says "Analysis" without saying who ran it and
          for how much is asking an operator to take the price on trust. */}
      {SECTIONS.map(([section, title]) => {
        const mine = rows.filter((r) => costOf(part, r.full) === section);
        if (!mine.length) return null;
        const open = mine.filter((r) => r.n > 0 && !r.outranked);
        // Item 157: clean means measured and found nothing. A row this run
        // could not measure is neither clean nor open, and it gets the line
        // below instead of being counted as a pass.
        // Split by what each check was MEASURED over (item 155, brief 160).
        // A trace-derived check was read on the traced pages only, so it may
        // not share a line that says "every page this run fetched": on
        // twenty22 four of Mobile's ten clean checks had been read on 12 pages
        // of 45 and the line claimed 45.
        const traced = new Set((part.trace_derived ?? [])
                                 .map((c) => c.split("/").pop() ?? c));
        const spotlessAll = mine.filter((r) => (r.n === 0 || r.outranked)
                                               && !unmeasured.has(r.checkId));
        // Item 267: a check read on its own sample says so on its own line.
        const ownSample = (r: { checkId: string }) => part.samples?.[r.checkId]?.n ?? null;
        // Item 272 (row 4): two checks the line could not certify. An
        // analysis check whose rows were all dropped returned rows, so "no
        // row" was false of it; and `img-lcp-lazy` with no largest paint
        // measured was judged on document order, not on the paint it names.
        const droppedIds = new Set((part.brief_dropped_rows ?? [])
          .map((d) => d.check.split("/").pop() ?? d.check));
        const byOrder = (r: { checkId: string }) => part.key === "images"
          && part.images?.lcp_found === false && r.checkId === "img-lcp-lazy";
        const spotlessDropped = section === "model"
          ? spotlessAll.filter((r) => droppedIds.has(r.checkId)) : [];
        const spotlessByOrder = spotlessAll.filter(byOrder);
        const partly = (r: { checkId: string }) => Boolean(part.partly_measured?.[r.checkId]);
        const siteLevel = (r: { checkId: string }) => onePage
          && (part.site_level_checks ?? []).includes(r.checkId);
        const spotlessSiteLevel = spotlessAll.filter(siteLevel);
        const spotlessPartly = section === "model" ? [] : spotlessAll.filter((r) => partly(r) && !siteLevel(r));
        const spotless = spotlessAll.filter((r) => !traced.has(r.checkId) && !ownSample(r)
          && !byOrder(r) && !spotlessDropped.includes(r) && !partly(r) && !siteLevel(r));
        const spotlessSampled = spotlessAll.filter((r) => !traced.has(r.checkId) && ownSample(r)
          && !siteLevel(r));
        const spotlessTraced = spotlessAll.filter((r) => traced.has(r.checkId) && !siteLevel(r));
        const unread = mine.filter((r) => r.n === 0
                                          && unmeasured.has(r.checkId));
        const away = folded(cost, section);
        return (
          <Fragment key={section}>
            <h3 className={`checks-head checks-head-${section}`}>
              {/* Item 208: the checks with at least one finding - the same
                  number the Fixes heading carries under the same word. This
                  counted every check listed, clean ones too, and Fixes
                  counted cards: "Free checks · 10" here and "· 22" there. */}
              {title} <span className="muted">· {open.filter((r) => r.counted > 0).length}
                {/* Item 275 (row 15): where the section holds checks, the
                    heading says so - "Analysis · 0" over two held rows read
                    as nothing there. */}
                {(() => {
                  const heldN = mine.filter((r) => r.counted === 0 && /not assessable/.test(r.state)).length;
                  // "in this table": the part's own count is every held check;
                  // a held check the automatic checks raised is listed open.
                  return heldN ? ` open · ${heldN} held in this table` : "";
                })()}</span>
              {away && (
                <span className="muted checks-folded">
                  {" · "}hidden by <code>free only</code>
                </span>
              )}
            </h3>
              {/* Items 267 (row 16) and 268 (row 8): the provenance under the
                  heading, not in it - the heading reads "Analysis · 5". */}
              {section === "model" && part.brief_run && (
                <p className="muted checks-prov">
                  analysis {part.brief_run.tool}
                  {/* The time alone read as "today" for an analysis written
                      against an audit two days old. Where audits have run
                      since, the date comes with it and the count says how
                      far back — the same number and the same words the
                      Reports screen uses. */}
                  {part.brief_run.at
                    ? ` · ${(part.brief_run.audits_since ?? 0) > 0
                        ? stamp(part.brief_run.at)
                        : clock(part.brief_run.at)}`
                    : ""}
                  {(part.brief_run.audits_since ?? 0) > 0
                    ? ` · ${part.brief_run.audits_since} `
                      + (part.brief_run.audits_since === 1 ? "audit since" : "audits since")
                    : ""}
                  {/* Item 239 step 4: the crawl it read, where the part's
                      checks have been measured since. */}
                  {part.brief_run.checked_since && part.brief_run.crawl_at
                    ? ` · read the crawl of ${stamp(part.brief_run.crawl_at)}; automatic checks since`
                    : ""}
                  {part.brief_run.model ? ` · ${part.brief_run.model}` : ""}
                  {part.brief_run.cost != null
                    ? ` · USD ${part.brief_run.cost.toFixed(2)}` : ""}
                  {/* Item 249: the rows below were read again under the rules
                      as they now stand, and - where the brief itself has
                      changed - written under an earlier one. */}
                  {part.brief_run.reread
                    ? ` · re-read under current rules${part.brief_run.reread_at
                        ? " " + stamp(part.brief_run.reread_at) : ""}`
                    : ""}
                  {part.brief_run.brief_changed && (
                    <span className="prov-earlier-brief">
                      {" · "}analysed under an earlier brief · re-run to apply
                    </span>
                  )}
                </p>
              )}
            {!away && open.length > 0 && (
              <table className="findings checks-table">
                <thead>
                  <tr><th>Severity</th><th>Check</th><th className="num">Automatic</th>
                      {/* Item 279 (row 8): no Analysis column on a part no
                          analysis writes to and no row came from - a column of
                          dashes for a source that does not exist. */}
                      {analysisCol && <th className="num">Analysis</th>}
                      <th className="num">Pages</th>
                      {anyImages && <th className="num">Images</th>}
                      {anyBlocks && <th className="num">Blocks</th>}
                      <th>State</th></tr>
                </thead>
                <tbody>
                  {open.map((r) => (
                    <tr key={r.full} id={checkRowId(r.full)}>
                      <td>{r.held
                        ? <span className="muted">—</span>
                        : <Pill tone={`sev-${r.severity}` as Tone}>{r.severity}</Pill>}</td>
                      <td><code>{r.full}</code></td>
                      {/* Rows raised, not pages: a findings count over the
                          record, so it renders plain and carries its
                          population rather than borrowing the page one. */}
                      <td className="num">{r.sweep
                        ? <Counted pops={pops} count={makeCount(r.sweep, "record")} />
                        : "\u2014"}</td>
                      {analysisCol && <td className="num">{r.brief
                        ? <Counted pops={pops} count={makeCount(r.brief, "record")} />
                        : "\u2014"}</td>}
                      <td className="num check-prev">
                        {r.allNotes || !r.counted
                          ? "—"
                          : r.siteRow ? <span className="muted">site</span>
                          : r.noPage ? <span title="the finding names no page">—</span>
                          : <Prevalence prev={r.pages} pops={pops} />}
                      </td>
                      {anyImages && <td className="num">{r.images
                        ? <Counted pops={pops} count={makeCount(r.images, "record")} />
                        : "\u2014"}</td>}
                      {anyBlocks && <td className="num">{r.blocks
                        ? <Counted pops={pops} count={makeCount(r.blocks, "record")} />
                        : "\u2014"}</td>}
                      <td className="muted">{r.state}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {/* One clean line per section, not one for the part: a reader
                asking "what did the free pass find" is owed its own
                answer. */}
            {/* "Clean on every page" is an absence claim, and an absence
                claim carries a population too (item 155): clean on every page
                THIS RUN FETCHED. Over the record it asserted a pass for pages
                nobody looked at, which is the same bad inference the
                prevalence column was making from the other direction. */}
            {/* Items 274, 276 and 265: an analysis check with no row is not
                a pass. The briefs report faults and omit passes, so "clean"
                certified what the model never said - Security's csp-policy,
                which rides on the csp-weak card, and platform-limits, which
                returned nothing. Said as what it is. */}
            {!away && section === "model" && spotless.length > 0 && (
              <p className="cause-unreturned-line muted">
                {spotless.length} check{spotless.length === 1 ? "" : "s"} the analysis
                returned no row for
                {part.brief_run?.crawl_at ? ` on the crawl of ${stamp(part.brief_run.crawl_at)}` : ""}.
                It reports faults, not passes, so this is not a
                clean result: {spotless.map((r) => r.checkId).join(" · ")}
              </p>
            )}
            {!away && spotlessDropped.length > 0 && (
              <p className="cause-unreturned-line muted">
                {spotlessDropped.length} check{spotlessDropped.length === 1 ? "" : "s"} the
                analysis returned rows for, every one dropped by the reader, so neither
                clean nor open: {spotlessDropped.map((r) => r.checkId).join(" · ")}. The
                dropped rows below say why.
              </p>
            )}
            {/* Screen audits round 3 (Security AC-01): a check the sweep
                tests only in part is clean on that part, said with what it
                left untested, and never on the "clean on every reading" line. */}
            {!away && spotlessSiteLevel.length > 0 && (
              <p className="cause-dark-line">
                {spotlessSiteLevel.length} check{spotlessSiteLevel.length === 1 ? " is" : "s are"} filed
                for the site as a whole, not per page, so this page is neither clean nor
                open on {spotlessSiteLevel.length === 1 ? "it" : "them"}:{" "}
                {spotlessSiteLevel.map((r) => r.checkId).join(" · ")}
              </p>
            )}
            {!away && spotlessPartly.length > 0 && (
              <p className="cause-clean-line">
                {spotlessPartly.length} check{spotlessPartly.length === 1 ? "" : "s"} clean
                only as far as the automatic checks test them:{" "}
                {spotlessPartly.map((r) => `${r.checkId} (${part.partly_measured?.[r.checkId]})`)
                  .join(" · ")}
              </p>
            )}
            {!away && spotlessByOrder.length > 0 && (
              <p className="cause-clean-line">
                {spotlessByOrder.map((r) => r.checkId).join(" · ")} clean on document
                order: no largest paint was measured, so the first image in each page's
                main region was read in its place.
              </p>
            )}
            {/* Item 271 (row 4): a check the brief owes a row for on every page
                an automatic check raised, returned for none of them, is a gap
                in the analysis, said with the pages that are owed one. */}
            {!away && section === "model" && spotless.map((r) => {
              const owed = owedPages(r.checkId, fixes);
              return owed && (
                <p className="cause-dark-line" key={`owed-${r.checkId}`}>
                  {r.checkId} not returned by the analysis, though{" "}
                  {owed.triggers.join(" or ")} is open on {owed.pages} page
                  {owed.pages === 1 ? "" : "s"}: the brief writes one for each
                </p>
              );
            })}
            {!away && section !== "model" && spotless.length > 0 && (
              <p className="cause-clean-line">
                {spotless.length} check{spotless.length === 1 ? "" : "s"} clean on
                {onePage ? " this page" : " every "}
                {onePage ? "" : siteScope
                  ? "reading across the site"
                  : pops?.crawl.size != null
                    ? <>page this audit fetched{" "}
                        <span className="muted clean-pop">
                          ({pops.crawl.size} {pops.crawl.basis})
                        </span></>
                    : "page in the record"}
                : {spotless.map((r) => r.checkId).join(" \u00b7 ")}
              </p>
            )}
            {!away && section !== "model" && [...new Set(spotlessSampled.map(
              (r) => part.samples?.[r.checkId]?.basis ?? ""))].map((basis) => {
              const these = spotlessSampled.filter((r) => part.samples?.[r.checkId]?.basis === basis);
              const n = part.samples?.[these[0].checkId]?.n;
              return (
                <p className="cause-clean-line" key={`sampled-${basis}`}>
                  {these.length} check{these.length === 1 ? "" : "s"} clean on every{" "}
                  {basis === "probed" ? "URL the crawler access test probed" : "page the rendered pass read"}{" "}
                  <span className="muted clean-pop">({n} {basis})</span>
                  : {these.map((r) => r.checkId).join(" \u00b7 ")}
                </p>
              );
            })}
            {/* The trace-derived clean checks, on their own denominator. The
                population is still the crawl -- these are crawled pages -- so
                only the word and the number change, which is exactly what the
                basis override on a count exists for. */}
            {!away && spotlessTraced.length > 0 && (
              <p className="cause-clean-line">
                {spotlessTraced.length} check{spotlessTraced.length === 1 ? "" : "s"}{" "}
                {onePage ? "clean on this page's trace" : <>clean on every page this audit traced{" "}
                <span className="muted clean-pop">
                  ({part.traced_pages ?? "?"} traced
                  {pops?.crawl.size != null ? ` of ${pops.crawl.size} ${pops.crawl.basis}` : ""})
                </span></>}
                : {spotlessTraced.map((r) => r.checkId).join(" \u00b7 ")}
              </p>
            )}
            {!away && byReason(unread.map((r) => r.checkId), unmeasured)
              .map(([reason, ids]) => part.gate?.state === "na" ? (
                // Item 274 (row 13): a gated part's checks cannot have findings
                // here; said as that, once, with the ids behind a disclosure
                // rather than a bare list of eleven.
                <details className="cause-dark-line" key={reason}>
                  <summary>
                    {ids.length} check{ids.length === 1 ? "" : "s"} {MEASURE_WORD.cannot} on
                    this site — {reason}
                  </summary>
                  {ids.join(" · ")}
                </details>
              ) : (
                <p className="cause-dark-line" key={reason}>
                  {ids.length} check{ids.length === 1 ? "" : "s"} not assessed — {reason}:{" "}
                  {ids.join(" · ")}
                </p>
              ))}
          </Fragment>
        );
      })}
      {/* Item 210: the engine's accounting of what the analysis returned,
          every figure a count of things drawn on this page - in place of the
          model's summary, which was printed here at data weight and
          contradicted the table above it on ten parts of eighteen. */}
      {part.brief_run && (() => {
        // Item 275 (row 5): this analysis's own cards. A card another
        // analysis wrote (Links' `depth-deep` on Crawl, 17 on twenty22) is
        // said apart, not counted into what this run returned.
        const tool = part.brief_run?.tool;
        const mine = (f: Fix) => !tool || !(f.briefs ?? []).length || (f.briefs ?? []).includes(tool);
        const brief = fixes.filter((f) => f.sources.includes("brief") && mine(f));
        const others = fixes.filter((f) => f.sources.includes("brief") && !mine(f));
        const otherNames = [...new Set(others.flatMap((f) => f.briefs ?? []))];
        // Item 276 (row 3): the rows first, summing to what the run returned,
        // and the holds after them as what they are. A hold is the ledger's
        // `not_assessable` entry, not a row, so "12 held" made the line sum to
        // 25 beside a provenance line reading 13 returned. A verdict closing
        // an automatic finding (item 269) is a kept row counted nowhere, so it
        // is its own term here (answer 20261004-0010-270-pass-override-drop-
        // superseded), and a kept row no card draws is said, so the terms
        // still sum on the whole part.
        const rows = brief.filter((f) => !f.needs);
        const verdicts = rows.filter((f) => f.override).length;
        const merged = rows.filter((f) => !f.override && f.sources.includes("sweep")).length;
        const own = rows.filter((f) => !f.override && !f.sources.includes("sweep")).length;
        const heldChecks = new Set(brief.filter((f) => f.needs).map((f) => f.checkId));
        // Item 274 (row 10): counted as the checks table counts them. A check
        // the analysis held where the automatic checks raised it is an open
        // row in the table, not a held one: Mobile read "3 checks could not be
        // assessed" over a table with two held rows (`tap-target` was the
        // third). Said apart, so the two lines agree.
        const raisedIds = new Set(fixes.filter((f) => !f.needs && f.sources.includes("sweep"))
                                       .map((f) => f.checkId));
        const heldOnRaised = [...heldChecks].filter((c) => raisedIds.has(c)).length;
        const held = heldChecks.size - heldOnRaised;
        // Item 275 (row 5): a check the model returned as NOT_ASSESSABLE is
        // dropped as a row and drawn as a hold; it is counted once, as the
        // hold it is.
        const alsoHeld = (part.brief_dropped_rows ?? []).filter(
          (d) => heldChecks.has(d.check.split("/").pop() ?? d.check)).length;
        const dropped = Math.max(0, (part.brief_dropped ?? 0) - alsoHeld);
        const kept = whole ? part.brief_run?.rows ?? null : null;
        const undrawn = kept != null ? Math.max(0, kept - rows.length) : 0;
        return (
          <p className="muted brief-accounting">
            What the analysis returned, as it stands on this page:{" "}
            {kept != null && <>{kept} kept: </>}{merged} merged onto
            automatic cards · {own} on their own
            {verdicts > 0 && <> · {verdicts} verdict{verdicts === 1 ? "" : "s"} closing an
              automatic finding</>}
            {undrawn > 0 && <> · {undrawn} kept but on no card here</>}
            {" · "}{dropped} dropped
            {held > 0 && <>; {held} check{held === 1 ? "" : "s"} could not be assessed</>}
            {heldOnRaised > 0 && <>; {heldOnRaised} more held where the automatic checks
              raised {heldOnRaised === 1 ? "it" : "them"}</>}
            {others.length > 0 && (
              <>. Also on this page: {others.length} card{others.length === 1 ? "" : "s"} from the{" "}
                {otherNames.join(" and ")} analys{otherNames.length === 1 ? "is" : "es"}, counted there</>
            )}
          </p>
        );
      })()}
      {part.brief_prose && (
        <details className="brief-prose">
          <summary>What the analysis wrote</summary>
          <p className="muted brief-prose-note">
            The model&apos;s own words about the rows it returned, written before the
            contract kept, merged, held or dropped any of them. Where they disagree
            with the table above, the table is the measurement.
          </p>
          <Markdown source={part.brief_prose} />
        </details>
      )}
    </section>
  );
}

/** Registry ids every three-block part page draws (item 166). */
const PART_LEGEND = ["action-free", "action-paid", "population-crawl", "n-of-m"];
/** Ids a part draws only where its rows carry them (items 268 row 8, 270
 *  row 16): each severity, the candidate state and "not measured". The
 *  legend defines the ones on screen, not the whole vocabulary. */
const PART_LEGEND_IF_DRAWN = ["sev-critical", "sev-high", "sev-medium", "sev-low", "sev-info",
                              "state-candidate", "not-assessed"];
/** Parts whose pictures draw the measurement bands, measured on twenty22 by
 *  the 166 sweep: the snippet ruler and Speed's gauges and strip. Not
 *  Security (item 276, row 9): its grid draws SET / ABSENT / DOES NOT APPLY,
 *  never "within range" or "past the limit". Not Accessibility (item 279,
 *  row 9): its fix-order bars are three kinds of work, not three bands, and
 *  its legend says those (`PART_LEGEND_EXTRA`). */
const BAND_PARTS = new Set(["title-desc", "speed"]);
/** The checks whose fix is taking a block out (screen audits round 3,
 *  Structured data US-01): another card closes one only if its change
 *  removes or merges a block. */
const REMOVAL_CHECKS = new Set(["schema-redundant-block", "schema-duplicate-id"]);
const BAND_LEGEND = ["band-ok", "band-warn", "band-bad", "band-mute", "band-info"];
/** Words one part's own pictures draw, which the shared lists cannot carry
 *  because no other part draws them (item 166, adoption). Speed labels every
 *  figure lab or field (`speed_now.tsx`), and Title & description names the
 *  viewport a cut is measured against (`title_snippet.tsx`, item 152). The
 *  166 sweep filed both as absent from the registry.
 */
const PART_LEGEND_EXTRA: Record<string, string[]> = {
  speed: ["basis-lab", "basis-field"],
  // Item 273 (row 10): the strip's four counts, in its own words.
  "title-desc": ["viewport-mobile", "viewport-desktop",
                 "length-over", "length-fit", "length-short", "length-missing"],
  a11y: ["fix-kind-chrome", "fix-kind-template", "fix-kind-page"],
};

export function PartPage({ part, page, facts, states, sweep, lanes, pages, bounds,
                           cost, runId, onRecheck, onRerun, onPage, busy, briefNote,
                           error, pops = null, onSpeedBrief, busyTool = null,
                           recheckConfirm = null, siteId, onStateChanged }: {
  /** The site, and what to call when the operator sets a state from a card
   *  (item 237). Absent, the cards offer no answers. */
  siteId?: string; onStateChanged?: () => void;
  part: Category; page: string; facts: Facts | null; states: FindingState[];
  sweep: SweepRun | null; lanes: Lanes | null;
  /** The record count. Still an integer, and still the record's: what it now
   *  has beside it is a population, so the strip foot can name its own
   *  denominator (`45 of 68 in the record`) on a page whose header says
   *  `45 of 53 on the site` without the two reading as a contradiction
   *  (item 155, superseding part of 146z). */
  pages: number | null;
  /** The three populations a count may be counted over, and this page's own
   *  scope — what decides whether each count renders plain or as a ratio
   *  (item 155). */
  pops?: Populations | null;
  bounds: Bounds;
  /** The cost filter, from the address (brief v17 step AV4). */
  cost: string;
  /** The audit the generator would write from (brief v17 step AX). */
  runId: string | null;
  onRecheck: () => void; onRerun: () => void;
  /** Narrow the whole screen to one page - the pane's own page filter, so a
   *  dot pressed on the scatter and a page typed into the bar reach the
   *  same state rather than two (brief v16c). */
  onPage?: (url: string) => void;
  busy: "sweep" | "brief" | null; briefNote: string | null; error: string | null;
  /** Speed's depth pills (brief v19 step BC, item 4's slot, Speed-only): the
   *  brief at a depth, and the tool running now. Only the Speed part is
   *  handed them (brief v25 step BP moved Speed onto this layout). */
  onSpeedBrief?: (depth: "standard" | "deep") => void;
  busyTool?: string | null;
  /** Passed straight to `Actions`, which documents what it is: the
   *  confirmation the re-check opens in site mode (item 189). Threaded rather
   *  than built here because the request belongs to the screen that owns the
   *  site id and the opener state. */
  recheckConfirm?: ReactNode;
}) {
  const render = PART_RENDERERS[part.key];
  // Held above the early return, because hooks may not be conditional -
  // the file's own opening note records what a varying hook count costs
  // here. `glow` is the scroll-link's shared half: the fixes block sets it
  // and the "now" block reads it, and no other part sets it at all.
  const [glow, setGlow] = useState<string | null>(null);
  // Item 255: the re-check's time is this site's stored re-checks', not a
  // constant.
  const pace = usePace(siteId);
  // The layer card a reader pressed (item 143 step BD), cleared when the part
  // changes so a narrow never follows the reader to a part with no such card.
  const [narrow, setNarrow] = useState<string | null>(null);
  useEffect(() => { setNarrow(null); }, [part.key]);
  /** The image a dot on Bytes for pixels selected (item 244): what the wall
   *  and the Fixes cards follow. Not in the address - it is a view of one
   *  block, like a drawer - and cleared when the part changes. */
  const [picked, setPicked] = useState<ImageDot | null>(null);
  useEffect(() => { setPicked(null); }, [part.key]);
  /** The address's narrow (brief v25 step BP): depth, check or template. */
  const [siteNarrow, setSiteNarrow] = useState<Narrow>(narrowFromHash);
  useEffect(() => {
    const read = () => setSiteNarrow(narrowFromHash());
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);
  // `{ block: "center" }` with no `behavior`, which is the convention
  // `anatomy.tsx` already states and
  // `test_every_scroll_into_view_uses_the_convention_already_in_the_tree`
  // enforces. A second scroll convention is worse than either one of them.
  const onFix = useCallback((n: number) => {
    document.getElementById(`fix-${n}`)?.scrollIntoView({ block: "center" });
  }, []);
  if (!render) return null;
  const allFixes = fixesOf(part, states, page);
  const narrowed = narrow ? part.sec_domains?.[narrow] ?? null : null;
  // Brief v25 step BP: the address's narrow applied ONCE, above the checks
  // table and the fixes, in site mode only. A depth or template narrow keeps
  // the fixes on its pages and narrows `pops.crawl` to that page set, so every
  // count below reads the smaller population by 155's rule; a check narrow
  // keeps that check's fixes and leaves the population as it was.
  const scoped = siteScopedNarrow(part, page ? null : siteNarrow, allFixes, pops ?? null);
  const pageFixes = scoped ? scoped.fixes : allFixes;
  const narrowedPops = scoped ? scoped.pops : (pops ?? null);
  // Only the fix CARDS narrow. The checks table and the "now" block keep the
  // whole part: they are the picture the card was pressed on.
  const cardFixes = narrowed ? pageFixes.filter((f) => narrowed.checks.includes(f.checkId)) : pageFixes;
  // A picked image narrows the cards to the ones about it (item 244).
  const pickedKey = picked && part.key === "images" ? dotKey(picked) : null;
  const fixes = pickedKey
    ? cardFixes.filter((f) => [...(f.images ?? []), f.image].some(
        (im) => im && imageKey(im, f.page || picked!.page) === pickedKey))
    : cardFixes;
  const chip = picked && part.key === "images"
    ? <PickedImage dot={picked} onClear={() => setPicked(null)} onPage={onPage} /> : null;
  const mine: Analysis | undefined = partAnalysis(part, lanes);
  // Items 276 (row 11), 268 (row 10), 270 (row 17), 275 (row 15): the last
  // recorded cost of this analysis on this site is the estimate's floor. A
  // median over every site quoted USD 0.21 for a re-run whose last run here
  // cost 0.38.
  const median = mine?.est_cost_default ?? mine?.est_cost ?? null;
  const lastCost = (part.brief_runs ?? []).find((r) => r.tool === mine?.tool)?.cost
    ?? (part.brief_run && part.brief_run.tool === mine?.tool ? part.brief_run.cost : null) ?? null;
  const floored = lastCost != null && (median == null || lastCost > median);
  const estCost = floored ? lastCost : median;
  // The scan matrix's own figure, so this button and the launcher never
  // quote different times for the same crawl.
  const estSeconds = pages ? estimate(pace, "recheck", "quick", page ? 1 : pages) : null;
  return (
    <div className="part-page">
      {/* One disclosure for the shared layout, before its first chip (item
          166): the actions' cost, the checks table's severity and states,
          the counts' population, and the measurement bands where this part's
          pictures draw them. */}
      {/* Item 250: where a row waits for the operator, the legend defines
          that state and its three answers. */}
      {/* Item 276 (row 9, round-1 #14): Security's verdict stands above the
          legend and the actions. A compromised site makes everything below
          it beside the point. */}
      {part.key === "security" && <SecurityVerdict part={part} />}
      <Legend ids={[...PART_LEGEND,
                    ...(PART_LEGEND_EXTRA[part.key] ?? []),
                    ...(states.some((s) => s.to_confirm && belongsTo(part)(s.check_id))
                        ? TO_CONFIRM_LEGEND : [])]}
              // Item 273 (row 10): the bands too, defined where a band is
              // drawn - "for information" stood in Title & description's
              // legend with no band of that tone on the part.
              ifDrawn={[...PART_LEGEND_IF_DRAWN, ...(BAND_PARTS.has(part.key) ? BAND_LEGEND : [])]} />
      {part.key === "speed" && onSpeedBrief ? (
        // A SLOT ONLY SPEED FILLS: its actions are a free re-check and the
        // brief at two depths, where every other part has one brief.
        <SpeedActions now={part.speed_now ?? null} cost={estCost}
                      busy={busyTool ?? (busy === "sweep" ? "sweep" : null)}
                      note={briefNote} onRecheck={onRecheck} onBrief={onSpeedBrief} />
      ) : (
        <Actions part={part} page={page} sweep={sweep} brief={part.brief_run ?? null}
                 cardDates={pageFixes.map((f) => f.measuredAt).filter((d): d is string => Boolean(d))}
                 pages={pages} estSeconds={estSeconds} estCost={estCost}
                 tool={mine?.tool ?? null}
                 estRuns={floored ? null : mine?.est_samples ?? null}
                 lastCost={floored ? lastCost : null}
                 rereads={part.brief_run ? {
                   rows: part.brief_run.rows,
                   raised: pageFixes.filter((f) => f.sources.includes("brief")
                                                   && f.sources.includes("sweep")).length,
                 } : null}
                 others={[...new Set([...(lanes?.ready ?? []), ...(lanes?.available ?? [])]
                   .filter((a) => a.part === part.key && a.tool !== mine?.tool).map((a) => a.tool))]}
                 othersHref={siteId ? `#/sites/${siteId}?tab=analyses` : null}
                 onRecheck={onRecheck} onRerun={onRerun} busy={busy} briefNote={briefNote}
                 recheckConfirm={recheckConfirm} />
      )}
      {/* The generator's door, beside the two actions and not among them:
          it produces a document rather than findings, so it is a third
          thing this page can do rather than a third way to check it
          (brief v17 step AX). Only on Content, and only with a page in
          hand. */}
      {part.key === "content" && (
        <p className="part-acts part-generate">
          <WriteBrief runId={runId} page={page}
                      price={[...(lanes?.ready ?? []), ...(lanes?.available ?? [])]
                        .find((a) => a.tool === "content-brief")?.est_cost ?? null} />
        </p>
      )}
      {error && <ErrorNote error={error} />}
      {/* Narrowed, the page's own reading - and where the crawl recorded
          nothing about it, that, rather than the site-wide table, which
          would be the wrong scope on a screen that says it is one page. */}
      {/* What the site has now, on Images (brief v16c). Above the scope
          branch and not inside it, because the scatter is a site-wide
          picture that narrows to the page rather than a different block at
          each scope - and the wall says "pick a page" at site scope rather
          than disappearing, so the part reads the same shape either way.
          Only Images carries an `images` payload.
          Deliberately NOT a `siteNow` slot (item 139a): that slot is inside
          the site-scope branch and draws only there, but this card must draw
          at page scope too, and above `now`. Folding it into `siteNow` would
          drop the scatter and the wall from the page view. Leave it here. */}
      {/* Item 251: the Now blocks say when what they draw was measured. One
          line above them, on every part: the page's own reading in page
          mode, the part's reference crawl on the whole site, and the range
          where the part's items were measured on different days. */}
      <NowMeasured part={part} sweep={sweep} facts={page ? facts : null} />
      {part.key === "images" && (
        <Card className="now-card ib-blocks">
          {chip}
          <BytesForPixels payload={part.images} page={page} picked={picked} onPick={setPicked} />
          <ImageWall inventory={facts?.image_inventory} page={page}
                     budget={part.images?.budget ?? null} picked={picked} onPage={onPage} />
        </Card>
      )}
      {page && render.noPageBlock
        ? null
        : page
        ? (facts
            ? <>
                <render.now facts={facts} part={part} bounds={bounds} fixes={allFixes}
                            page={page} glow={glow} onFix={onFix} onPage={onPage} />
                {render.pageChecks && (
                  <ChecksTable part={part} fixes={pageFixes} cost={cost} pops={narrowedPops}
                         onePage={Boolean(page)}
                         whole={!page && !scoped}
                               siteScope={false} sweepAt={sweep?.at ?? null} />
                )}
              </>
            : <p className="muted">The crawl recorded nothing about this page, so there is
                nothing to read back. Re-check the part to fetch it.</p>)
        : render.siteScope
          ? <>
              <render.now facts={facts as Facts} part={part} bounds={bounds}
                          fixes={allFixes} page="" glow={glow} onFix={onFix}
                          narrow={narrow} onNarrow={part.sec_domains ? setNarrow : undefined} />
              {/* Item 230: the picture AND the table, not one or the other.
                  Security and Content drew no checks table, so no clean line,
                  no "not measured" line and no Free/Analysis split - and no
                  row on which `csp-weak`'s gap could even be seen. */}
              <ChecksTable part={part} fixes={pageFixes} cost={cost} pops={narrowedPops}
                         onePage={Boolean(page)}
                         whole={!page && !scoped}
                           siteScope sweepAt={sweep?.at ?? null} />
            </>
        : <>
            {/* The part's site-wide picture, then the free-checks table, then
                Fixes (item 139a). Each part declares its picture as `siteNow`
                (see the Renderer type), so this one order is structural rather
                than a `part.key === "..."` per part, and 147/148 inherit it.
                Images is the exception: it renders at both scopes and above
                `now`, so it stays at the top of this component, not in this
                slot. `content` and `security` are `siteScope` and take the
                branch above - they never reach here. */}
            {render.siteNow && <render.siteNow part={part} page="" pages={pages}
                                              pops={pops} onPage={onPage}
                                              siteId={siteId} onChanged={onStateChanged}
                                              narrow={siteNarrow} onNarrow={setNarrowInHash} />}
            {scoped && (
              <p className="muted narrow-line" role="status">
                {scoped.said}{" "}
                <SecondaryButton className="narrow-clear"
                        onClick={() => setNarrowInHash(scoped.kind, null)}>Clear</SecondaryButton>
              </p>
            )}
            <ChecksTable part={part} fixes={pageFixes} cost={cost} pops={narrowedPops}
                         onePage={Boolean(page)}
                         whole={!page && !scoped}
                         siteScope={Boolean(render.siteScope)} sweepAt={sweep?.at ?? null} />
          </>}
      {/* The brief's own fixes, once each, above the per-row cards (brief v20,
          items 147 E2 and 148 G3). DATA-GATED rather than part-gated: only a
          brief that emits `fixes[]` fills it, so this renders nothing for
          every other part without the actions row growing a conditional each
          of them has to opt out of. That is the same argument item 4's slot
          settled, from the other side -- there the part chose, here the
          payload does. */}
      <BriefFixes fixes={(part.brief_fixes ?? []) as BriefFix[]} />
      {narrowed && narrow && (
        <p className="muted fix-narrow" role="status">
          Fix cards narrowed to {narrow} · {narrowed.name}: {fixes.length} of {allFixes.length}.{" "}
          <SecondaryButton onClick={() => setNarrow(null)}>Show all</SecondaryButton>
        </p>
      )}
      {pickedKey && (
        <div className="fix-narrow ib-picked-fixes">
          {chip}
          <p className="muted" role="status">
            Fix cards for this image: {fixes.length} of {cardFixes.length}.
          </p>
        </div>
      )}
      <Fixes fixes={fixes} facts={facts} render={render} page={page} part={part}
             cost={cost} onGlow={part.graph ? setGlow : undefined}
             siteId={siteId} onStateChanged={onStateChanged} sweep={sweep} />
      {!page && render.siteFoot && <render.siteFoot part={part} />}
    </div>
  );
}
