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
import { Markdown } from "./markdown";
import { Working } from "./working";
import { stamp } from "./client_lanes";
import { MeasuredAge, dayOf } from "./age";
import { SecondaryButton } from "./buttons";
import { sourceWord } from "./glossary";
import { Legend } from "./glossary";
import { Fragment, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Category, ContentBlock, EntityMatrix, Facts, ImageRecord, LinkIn, LinkOut, SchemaBlock } from "./anatomy";
import { BytesForPixels, ImageDot, ImageWall, PickedImage, fileOf, fileSrc, imageKey,
         dotKey } from "./images_budget";
import { OutlineLadder, SkipsByTemplate } from "./headings_outline";
import { BarrierOverlay, FixOrderWaterfall, ShotBoxes } from "./a11y_fixorder";
import { HeadersGridBlock } from "./headers_grid";
import { LengthStrips, SnippetCard } from "./title_snippet";
import { costOf } from "./cost";
import { Analysis, Lanes } from "./analyses";
import { FindingState, api, isCoverageNote } from "./api";
import { Card, ErrorNote, money } from "./components";
import { SpendButton, SpendTarget } from "./spend";
import { SECS_PER_PAGE, human } from "./scanmatrix";
import { SchemaGraphView } from "./schema_graph";
import { goHandler, goto, withPart } from "./nav";
import { Narrow, NarrowKind, narrowFromHash, pagePredicate, setNarrowInHash } from "./narrow";
import { CrawlDepthBlock, depthPicked } from "./crawl_depth";
import { CrawlNowBlock } from "./crawl_now";
import { AiLlmsFile, AiReachability, AiReachabilityPage, AiRegister, AiSurfaceFixBody } from "./ai_surface";
import { IndexabilityNowBlock } from "./indexability_now";
import { UrlsNowBlock } from "./urls_now";
import { SpeedActions, SpeedNowBlock } from "./speed_now";
import { CanonicalChainsBlock } from "./canonical_chains";
import { Pill, type Tone } from "./pill";
import { MEASURE_WORD, MeasureLine, measureOf } from "./measure";
import { Counted, Populations, Prevalence, coverageNotes, makeCount, pathKey,
         prevalence } from "./population";

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
  [/\b(lcp|cls|inp|ttfb|tbt|css|js|html|url|urls|nap|gbp|ssl|tls|dns|cdn|ai|og|jsonld|h1|h2)\b/g, "\u0000$1"],
];

export const plainName = (checkId: string) => {
  if (PLAIN[checkId]) return PLAIN[checkId];
  let words = checkId.replace(/^[A-Z0-9]+\//, "").replace(/^EXP:[^/]*\//, "").replace(/-/g, " ");
  for (const [pat, rep] of ID_WORDS) words = words.replace(pat, rep);
  words = words.replace(/\u0000(\w+)/g, (_, w: string) => (w === "jsonld" ? "JSON-LD" : w.toUpperCase()));
  return words.replace(/^[a-z]/, (c) => c.toUpperCase());
};

/** Where a held check's missing input is set. A `needs` naming a field of
 *  the site record links to the form that holds it; one naming the page's
 *  own content has nowhere to send anybody, and says so instead. */
const RECORD_WORDS = /gbp|categor|service area|location entit|neighbourhood|sub-service|page type|brand|strateg|provenance/i;

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
  current: string; replacement: string | null; note: string;
  needs?: string;
  /** The analysis read this before the automatic checks cleared it on
   *  every page it names: when (item 239 step 4). */
  supersededOn?: string | null;
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
  /** The finding states this card stands for (item 237): what Confirm,
   *  Accept and Withdraw write to. */
  fingerprints?: string[];
  /** The URL template the row is about, where it is a per-template row
   *  (items 217, 222): drawn as the card's subject. */
  template?: string | null;
  /** The page's outline as the crawl kept it, where the site view carries it
   *  (item 224) - the Headings diff's baseline with no page in hand. */
  baseline?: Pick<Facts, "outline" | "headings"> | null;
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
export const PER_SUBJECT_CHECKS = new Set(["edge-blocks-ai-ua", "ua-sensitive",
  "entity-unnamed", "ai-crawler-blocked"]);

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
      // The brief's row carries the copy; the sweep's carries the reading.
      if (word === "brief" && s.proposed) seen.replacement = s.proposed;
      if (word === "sweep") seen.current = s.summary;
      // And the brief's row carries what it is about (brief v15): the
      // image, the checks its one replacement closes, and whether the
      // change is a template's. A sweep row read first must not lose them.
      if (word === "brief") {
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
        seen.rollout = s.rollout ?? seen.rollout;
        seen.payload = s.payload ?? seen.payload;
      }
      if (RANK.indexOf(s.severity) < RANK.indexOf(seen.severity)) seen.severity = s.severity;
      seen.candidate = seen.candidate && s.state === "candidate";
      continue;
    }
    by.set(key, {
      key, check: `${s.dimension}/${s.check_id}`, checkId: s.check_id, page: url,
      pages: s.affected_urls.length, urls: [...s.affected_urls], coverageNote: isCoverageNote(s),
      block: s.block ?? null, where: s.where ?? null,
      severity: s.severity, sources: [word], candidate: s.state === "candidate",
      current: s.summary, replacement: s.proposed ?? null, note: "",
      image: s.image ?? null,
      images: [...new Set([...(s.images ?? []), ...(s.image ? [s.image] : [])])],
      alsoResolves: s.also_resolves ?? [],
      fingerprints: [s.fingerprint],
      supersededOn: s.superseded_on ?? null,
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
  const onPage = (u: string) => !page || u === "*" || !u || pathOf(u) === pathOf(page);
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
                    link?: string };

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
    const [text, ...rest] = m[2].split(" → ");
    const after = rest.join(" → ").trim();
    // A target path or the placeholder is a link; anything else after the
    // arrow is the words that follow the heading, which is context.
    const link = /^(\/|\[TO CONFIRM)/.test(after) ? after : undefined;
    out.push({ level: Number(m[1]), text: text.trim(), inMain: null,
               next: link ? "" : after, link });
  }
  return out;
}

const norm = (t: string) => t.trim().toLowerCase().replace(/\s+/g, " ");

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
export function WriteBrief({ runId, page }: { runId: string | null; page: string }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!page || !runId) return null;
  return (
    <span className="write-brief">
      {/* Item 178: priced in words and confirmed. The content brief has no
          estimate on this screen, so it says so rather than leaving no price. */}
      <SpendButton className="write-brief-btn" busy={busy} price={null}
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
                       await api.post(`/api/runs/${runId}/expert/content-brief`,
                                      { url: page });
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
    </span>
  );
}

/** Block 1 — the two things this page can do, and what produced what is
 *  on it. One free, one paid; no depth choice, because a sweep re-check
 *  is free at every depth and the choice was noise. */
function Actions({ part, page, sweep, brief, pages, estSeconds, estCost,
                   onRecheck, onRerun, busy, briefNote,
                   recheckConfirm = null }: {
  part: Category; page: string;
  sweep: SweepRun | null; brief: Category["brief_run"];
  pages: number | null; estSeconds: number | null; estCost: number | null;
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
  const briefScope = page ? "this page" : "this audit";
  const dim = part.refresh?.dimension ?? "ONP";
  // `stamp`, not a third spelling of the slice (audit F11): this one had the
  // replace and the slice the other way round, which is why a grep for the
  // other order missed it.
  const when = (iso: string | null | undefined) => stamp(iso);
  /** Item 232: the gate has settled that the analysis does not apply. The
   *  button offered "Run analysis" and the line under it said none "has run"
   *  - as if one were owed - over a card saying it was not applicable. */
  const gated = part.gate?.state === "na";
  const gatedWhy = "not applicable on this site: it presents one locale. It runs once a "
    + "target locale is stated for it, or a crawl reaches a second locale";
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
                why={busy === "brief" ? "the analysis is running" : null}
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
          {page && estSeconds !== null ? ` · ${human(estSeconds)}` : ""}
        </SecondaryButton>
        {/* Item 178: held with its reason in text, priced in words, and
            confirmed. "Run" until an analysis has run on this part: "Re-run"
            over "no analysis has run on this part" named a result that did not
            exist (05-2, 07-11). */}
        <SpendButton className="act-brief" price={estCost}
                     busy={busy === "brief"}
                     why={briefNote ?? (gated ? gatedWhy
                       : busy === "sweep" ? "the automatic checks are starting" : null)}
                     confirm={{ title: `${brief ? "Re-run" : "Run"} the ${part.label} analysis?`,
                                body: <><SpendTarget page={page ? pathOf(page) : null}
                                                     pages={page ? null : pages} />
                                  <p>{brief
                                    ? "It replaces the analysis stored for this part."
                                    : gated ? "The locale check found this analysis does not apply."
                                    : "Nothing has analysed this part on this audit yet."}</p></>,
                                action: `${brief ? "Re-run" : "Run"} the analysis` }}
                     onSpend={onRerun}>
          {`${brief ? "Re-run" : "Run"} analysis · ${briefScope}`}
        </SpendButton>
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
        {sweep && (
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
        {part.measured_range && (part.measured_range.from.slice(0, 10) !== part.measured_range.to.slice(0, 10)
                                 || part.measured_range.rechecked_pages > 0) && (
          <span className="prov-line prov-range muted">
            Measured {dayOf(part.measured_range.from)} to {dayOf(part.measured_range.to)}
            {part.measured_range.rechecked_pages > 0
              ? ` · ${part.measured_range.rechecked_pages === 1 ? "one page"
                  : `${part.measured_range.rechecked_pages} pages`} re-checked ${dayOf(part.measured_range.rechecked_at)}`
              : ""}
          </span>
        )}
        {brief ? (
          <span className="prov-line">
            <i className="prov-dot prov-brief" aria-hidden="true" />
            {" "}analysis {brief.tool} {when(brief.at)}
            {" · "}<MeasuredAge iso={brief.at} th={part.age_thresholds} />
            {brief.model ? ` · ${brief.model}` : ""}
            {/* Item 209: the accounting once, where the price is read. "10
                rows · USD 0.47" over a run that returned 29 hid that two
                thirds of what was paid for was refused. */}
            {brief.rows != null
              ? ((part.brief_dropped ?? 0) > 0
                  ? ` · ${brief.rows + (part.brief_dropped ?? 0)} rows returned · ${brief.rows} kept`
                    + ` · ${part.brief_dropped} dropped`
                  : ` · ${brief.rows} row${brief.rows === 1 ? "" : "s"}`)
              : ""}
            {brief.cost != null ? ` · ${money(brief.cost)}` : ""}
          </span>
        ) : (
          <span className="prov-line muted">
            {gated ? "analysis not applicable: this site presents one locale"
              : "no analysis has run on this part"}
          </span>
        )}
      </div>
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

/** Block 2, Title & description's renderer: the page's own strings, with
 *  a plain result preview so a 272-character description is visible
 *  rather than stated. */
function TitleDescNow({ facts, part, bounds }: {
  facts: Facts; part: Category; bounds: Bounds;
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
  const titleHeld = held("title-entity-alignment");
  const cut = desc.length > bounds.descMax ? desc.slice(0, bounds.descMax) + " …" : desc;
  return (
    <Card className="now-card">
      <h4>What the page has now</h4>
      <dl className="now-strings">
        <dt>Title</dt>
        <dd>
          {title ? <span className="now-str">{title}</span>
                 : <span className="muted">no title</span>}
          <div className="now-badges">
            {title && (
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
            {desc && (
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
  const current = now || fix.current;
  return (
    <>
      <p className="fix-now">
        <span className="fix-lbl">Now</span>
        {current ? <s>{current}</s> : <span className="muted">nothing on the page</span>}
      </p>
      {fix.replacement && (
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
  const byText = new Map(before.map((l, i) => [norm(l.text), { line: l, i }]));
  /** What happened to one line of the corrected outline, in a word. */
  const change = (line: Line): string | null => {
    const was = byText.get(norm(line.text));
    if (!was) return "[proposed]";
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
  // A heading the corrected outline does not carry is cut - unless it sits
  // outside the main region, which a brief rewriting the page's own
  // outline never claims to touch. Striking the site's navigation would
  // read as "delete this heading", which is not what was proposed.
  const cut = before.filter((l) => l.inMain !== false
                                   && !after.some((a) => norm(a.text) === norm(l.text)));
  const stub = fix.checkId === "h2-question-unanswered";
  return (
    <>
      <p className="fix-now">
        <span className="fix-lbl">Now</span>
      </p>
      <ol className="outline outline-was">
        {shown.map(({ line, mark, i }) => {
          const was = byText.get(norm(line.text));
          if (!was) return null;
          return (
            <li key={`was-${i}`} className={`out-line${mark ? " out-struck" : ""}`}
                style={{ marginLeft: `${(was.line.level - 1) * 1.1}rem` }}>
              <code className="out-lvl">H{was.line.level}</code>{" "}
              <span className="out-text">{was.line.text}</span>
            </li>
          );
        })}
        {cut.map((l, i) => (
          <li key={`cut-${i}`} className="out-line out-struck"
              style={{ marginLeft: `${(l.level - 1) * 1.1}rem` }}>
            <code className="out-lvl">H{l.level}</code>{" "}
            <span className="out-text">{l.text}</span>
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
                  onPage?: (url: string) => void }) => JSX.Element | null;
  /** What the copy button copies, in the words of the thing copied. */
  copyLabel?: string;
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
          <h5 className="muted">Now</h5>
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
        <div className="img-panel">
          <h5 className="muted">Replace with</h5>
          <pre className="img-markup out-new" tabIndex={0}>{fix.replacement ?? ""}</pre>
        </div>
      </div>
      {fix.where && <p className="muted fix-meta">Where: {fix.where}</p>}
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
  return (
    <div className="fix-links">
      {fix.current && <p className="fix-now"><s>{fix.current}</s></p>}
      {fix.replacement && <p className="fix-rep">{fix.replacement}</p>}
    </div>
  );
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
      </p>
      <div className="tp-bar" aria-hidden="true">
        {(["unique", "shared", "boilerplate"] as const).map((k) =>
          t[k] ? <span key={k} className={`tp-seg tone-${TP_TONE[k]}`}
                       style={{ width: `${(t[k] / all) * 100}%` }} /> : null)}
      </div>
      {shot ? (
        <div className="overlay tp-overlay">
          <ShotBoxes src={shot} docW={cb.doc!.w} selected={sel == null ? null : sel + 1}
                     onSelect={pick}
                     alt={`screenshot of the page, with ${placed.length} text region`
                          + `${placed.length === 1 ? "" : "s"} marked`}
                     boxes={placed.map(({ b, n }) => ({
                       n, rect: b.rect, tone: TP_TONE[cls(b)],
                       label: `region ${n}, ${cls(b)}, ${b.words} words` }))} />
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
        {CONTENT_BADGES.map(([check, label, good]) => (
          <span key={check}
                className={`str-badge ${raised.has(check) ? "sb-fail" : "sb-pass"}`}
                title={raised.has(check)
                         ? `${check} is open on this page`
                         : `${check} did not fire on this page`}>
            {label}: {raised.has(check) ? "no" : good}
          </span>
        ))}
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
  const rows = part.brief_map ?? [];
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
              {(part.brief_map ?? []).slice(0, MAP_SHOWN).map((row, i) => (
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
        <p className="muted">{rows.length - MAP_SHOWN} more not shown.</p>
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
      {fix.current && <p className="fix-now"><s>{fix.current}</s></p>}
      {fix.replacement && <p className="fix-rep">{fix.replacement}</p>}
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
        <FixOrderWaterfall order={part.fix_order} />
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
  return (
    <>
      <p className="fix-why">{fix.current || fix.note}</p>
      {fix.replacement && (
        <div className="img-panel">
          <h5 className="muted">Do this</h5>
          <pre className="img-markup out-new" tabIndex={0}>{fix.replacement}</pre>
        </div>
      )}
      {fix.where && <p className="muted fix-meta">Where: {fix.where}</p>}
    </>
  );
}

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
      <SecurityVerdict part={part} />
      <SecurityLayers part={part} narrow={narrow ?? null} onNarrow={onNarrow} />
      <h4>What the site has now</h4>
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
      <TransportFacts facts={facts} />
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
      <b>{head}</b>
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
      note = entry.missing ?? entry.summary ?? (found ? `${found} finding${found === 1 ? "" : "s"} open` : "assessed");
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
      <h4>The layers, and how far the {part.brief_security ? "analysis" : "automatic checks"} saw into each</h4>
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
function TransportFacts({ facts }: { facts: Facts }) {
  const t = facts?.site?.transport;
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
      ? `valid to ${String(t.cert_not_after).slice(0, 10)}` : "not recorded"],
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
          <h5 className="muted">Add this</h5>
          <pre className="img-markup out-new" tabIndex={0}>{fix.replacement}</pre>
        </div>
      )}
      {/* Brief v20 step BD: the change per layer, so the edge and the origin
          each get the block for their own stack, then the risk, the check
          that it worked, and the way back - in that order, because a change
          nobody can verify or undo should not be deployed. */}
      {(r?.config ?? []).map((c, i) => (
        <div key={i} className="img-panel sec-layer-cfg">
          <h5 className="muted">{c.layer ?? "config"}{c.stack ? ` · ${c.stack}` : ""}</h5>
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
      <h4>Every page&rsquo;s length</h4>
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
                  siteNow: TitleDescSiteNow },
  headings: { now: HeadingsNow, body: HeadingsFixBody, copyLabel: "copy outline",
              siteNow: HeadingsSiteNow,
              na: ["h3-sub-service", "h3-geo-map"] },
  images: { now: ImagesNow, body: ImagesFixBody, copyLabel: "copy markup",
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
  links: { now: LinksNow, body: LinksFixBody, copyLabel: "copy anchor" },
  // Brief v16e. Two blocks in one position, chosen by scope: the fix order
  // for the site, the page's own barriers when one page is in hand. They
  // answer different questions - "what first" and "where on this page" -
  // and neither is a smaller version of the other.
  // Item 226: the waterfall is the part's site picture. A11yNow drew it with
  // no page in hand, but with no `siteNow` the site branch never called it -
  // the same repair International and Mobile had (see `IntlSiteNow`).
  a11y: { now: A11yNow, siteNow: A11ySiteNow, body: A11yFixBody, copyLabel: "copy selector" },
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
                  copyLabel: "copy change" },
  crawl: { noPageBlock: true, now: NoPageNow, siteNow: CrawlSiteNow, body: SiteBriefFixBody,
           copyLabel: "copy change" },
  indexability: { now: IndexabilityPageNow, siteNow: IndexabilitySiteNow,
                  body: SiteBriefFixBody, copyLabel: "copy change" },
  urls: { noPageBlock: true, now: NoPageNow, siteNow: UrlsSiteNow, body: SiteBriefFixBody,
          copyLabel: "copy change" },
  speed: { noPageBlock: true, now: NoPageNow, siteNow: SpeedSiteNow, body: SiteBriefFixBody,
           copyLabel: "copy change" },
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
      <AiRegister brief={part.brief_ai_surface ?? null} />
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
function IntlNow({ part }: { facts: Facts; part: Category; bounds: Bounds;
                             fixes: Fix[]; page: string }) {
  const gate = part.gate ?? null;
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
        <pre className="intl-gate-reason" tabIndex={0}>{gate.reason}</pre>
      </Card>
    );
  }
  const loc = part.brief_locales ?? null;
  const clusters = (part.brief_clusters ?? []) as {
    cluster_id?: string; members?: string[]; locales?: string[];
    method?: string; closed?: boolean; x_default?: boolean;
    members_fetched?: number; verdict?: string }[];
  if (!loc && !clusters.length) return <></>;
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
    verdict?: string }[];
  if (!templates.length) return <></>;
  return (
    <Card className="now-card mobile-now">
      <h4>Templates at 412 px</h4>
      <VerdictTally verdicts={templates.map((t) => t.verdict ?? "")} />
      <div className="table-scroll">
        <table className="findings mobile-templates">
          <thead><tr><th>Template</th><th className="num">Pages</th>
            <th>Viewport (verbatim)</th><th className="num">Overflow</th>
            <th className="num">Small taps</th><th>Full-height</th>
            <th>Verdict</th></tr></thead>
          <tbody>
            {templates.map((t, i) => (
              <tr key={t.template ?? i}>
                <td>{t.template}</td>
                <td className="num">{t.pages ?? ""}</td>
                <td><code className="mobile-vp">{t.viewport_raw || "none"}</code>
                  {t.injected && <span className="tone tone-sev-high"> injected</span>}
                  {t.viewport_rendered && t.viewport_raw
                   && t.viewport_rendered !== t.viewport_raw
                   && <span className="muted"> → {t.viewport_rendered}</span>}</td>
                <td className="num">{t.overflow_px ? `${t.overflow_px} px` : "0"}</td>
                <td className="num">{t.tap_targets_small ?? 0}</td>
                <td>{(t.full_height_units ?? []).join(" · ") || "none"}</td>
                <td><span className={`tone tone-${VERDICT_TONE[(t.verdict || "").toLowerCase()] ?? "state-candidate"}`}>
                  {t.verdict}</span></td>
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
function IntlSiteNow({ part }: { part: Category; page: string; pages: number | null;
                                 pops?: Populations | null;
                                 onPage?: (url: string) => void }) {
  return <IntlNow part={part} facts={{} as Facts} bounds={{} as Bounds}
                  fixes={[]} page="" />;
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
  const groups = new Map<string, { rich: string; verdict: string; reason: string;
                                   pages: string[] }>();
  for (const e of part.brief_eligibility ?? []) {
    const rich = e.rich_result || "none";
    const reason = e.reason ?? "";
    const key = [rich, e.verdict.toLowerCase(), reason].join("\u0000");
    const g = groups.get(key) ?? { rich, verdict: e.verdict, reason, pages: [] };
    if (e.page && !g.pages.includes(e.page)) g.pages.push(e.page);
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
            <li key={`${g.rich}-${g.verdict}-${g.reason}`}>
              <code>{g.rich}</code>: <b>{g.verdict}</b>
              {g.reason ? ` — ${g.reason}` : ""}
              <details className="sd-elig-pages">
                <summary>{g.pages.length === 1 ? "1 page" : `${g.pages.length} pages`}</summary>
                <ul>
                  {g.pages.map((p) => (
                    <li key={p}>
                      <button type="button" className="btn-link" onClick={() => onPage?.(p)}>
                        {pathOf(p)}
                      </button>
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
function SiteBriefFixBody({ fix }: { fix: Fix; facts: Facts | null }) {
  return (
    <>
      <p className="fix-why">{fix.current || fix.note}</p>
      {fix.replacement && (
        <div className="img-panel">
          <h5 className="muted">Change</h5>
          <pre className="img-markup out-new" tabIndex={0}>{fix.replacement}</pre>
        </div>
      )}
      {fix.where && <p className="muted fix-meta">Where: {fix.where}</p>}
    </>
  );
}

/** How many cards of one check stand before `show all` (whole-site view). */
export const CARDS_PER_CHECK = 3;

/** Item 237: the operator's three answers to an analysis finding no sweep
 *  can raise. A second paid run of the same model is not confirmation, so
 *  the product asks once, here, rather than charging for a re-run. */
function ConfirmControls({ fix, siteId, onStateChanged }: {
  fix: Fix; siteId: string; onStateChanged?: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = async (state: string) => {
    setBusy(state); setErr(null);
    try {
      for (const fp of fix.fingerprints ?? []) {
        await api.post(`/api/sites/${siteId}/states/${fp}`, { state });
      }
      onStateChanged?.();
    } catch (e) {
      setErr(`could not set it: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };
  const held = (state: string) => (busy && busy !== state ? "another answer is being saved" : null);
  return (
    <div className="fix-confirm">
      <SecondaryButton className="fix-confirm-open" busy={busy === "open"} why={held("open")}
                       onClick={() => set("open")}>Confirm</SecondaryButton>
      <SecondaryButton className="fix-confirm-accept" busy={busy === "accepted-risk"}
                       why={held("accepted-risk")}
                       onClick={() => set("accepted-risk")}>Accept</SecondaryButton>
      <SecondaryButton className="fix-confirm-withdraw" busy={busy === "withdrawn"}
                       why={held("withdrawn")}
                       onClick={() => set("withdrawn")}>Withdraw</SecondaryButton>
      <span className="muted" role="status">{err ?? ""}</span>
    </div>
  );
}

function FixCard({ fix, facts, render, onCopy, copied, n, fixHeld = false,
                   awaiting = false, siteId, onStateChanged }: {
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
        <Pill tone={fix.needs ? "sev-info" : (`sev-${fix.severity}` as Tone)}>
          {fix.needs ? (fixHeld ? "fix held" : "Not assessable") : fix.severity}
        </Pill>
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
        <span className="muted fix-src">· {sourceWords(fix.sources, readingsDisagree(fix.current, fix.replacement))}</span>
        {/* Brief v20 (147 E4, 148 G5). Nothing renders where the brief stated
            none: a row the sweep measured carries no confidence, and drawing
            "low" there would grade the engine's own measurement as a guess. */}
        <ConfidenceChip value={fix.confidence} />
        {fix.candidate && (
          <Pill tone="state-candidate">{awaiting ? "analysis, not yet confirmed" : "candidate"}</Pill>
        )}
        {/* Item 239 step 4: the automatic checks cleared this on every page
            the analysis named, after the analysis read it. */}
        {fix.supersededOn && (
          <span className="muted fix-superseded">· superseded on {stamp(fix.supersededOn)}</span>
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
        ) : fix.page ? (
          <span className="muted fix-page"><code>{pathOf(fix.page)}</code></span>
        ) : null}
        {fix.replacement && (
          <SecondaryButton className="fix-copy"
                  onClick={() => onCopy(fix.key, fix.replacement as string)}>
            {copied === fix.key ? "copied" : (render.copyLabel ?? "copy replacement")}
          </SecondaryButton>
        )}
      </div>
      {awaiting && siteId && (
        <ConfirmControls fix={fix} siteId={siteId} onStateChanged={onStateChanged} />
      )}
      {fix.needs ? (
        <p className="fix-why">
          {/* Item 211: label and value apart in the TEXT, not only in the
              styling - the accessible name read "Why heldAUTHORS". And the
              table's sentence shape: "needs <input>". */}
          <span className="fix-lbl">Why held: </span>
          {fix.needs ? `needs ${fix.needs}` : "the brief gave no reason"}
          {link ? <> — <a href={link.href} onClick={goHandler(link.href)}>{link.label}</a>,
                     then re-run the analysis</> : "."}
        </p>
      ) : <render.body fix={fix} facts={facts} />}
      {/* Brief v20 (147 E3, 148 G4): inside the row and under the evidence,
          so a reader who has just read the evidence learns in the same breath
          that the verdict is a row up. Above the body it would read as a
          reason not to bother reading on. */}
      <SuppressedStrip checks={fix.suppressed} />
    </Card>
  );
}

/** Block 3 — one card per failing (check, page) on the current scope. On
 *  the whole site the cards group under their check, three deep, so a
 *  check on forty pages does not bury the check on two. */
/** The first path segment most of a group's pages share, where enough of
 *  them share one to call it a template (brief v14 step AP). One change
 *  there is the whole fix for that many of them, and the group says so
 *  once rather than repeating it per page. */
export function templateOf(pages: string[]): { prefix: string; n: number } | null {
  const seg = (u: string) => { const p = pathOf(u).split("/").filter(Boolean)[0];
                               return p ? `/${p}/` : "/"; };
  const by = new Map<string, number>();
  for (const u of pages) by.set(seg(u), (by.get(seg(u)) ?? 0) + 1);
  const best = [...by.entries()].filter(([prefix, n]) => prefix !== "/" && n >= 2)
                                .sort((a, b) => b[1] - a[1])[0];
  return best ? { prefix: best[0], n: best[1] } : null;
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

function Fixes({ fixes, facts, render, page, part, cost, onGlow, siteId, onStateChanged }: {
  siteId?: string; onStateChanged?: () => void;
  fixes: Fix[]; facts: Facts | null; render: Renderer; page: string; part: Category;
  cost: string;
  /** Which node the picture should light up, as the reader scrolls (brief
   *  v16a step AT-b). Absent on every part that draws no picture. */
  onGlow?: (key: string | null) => void;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const wrap = useRef<HTMLElement>(null);
  const graph = part.graph ?? null;
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
  const repeated = [...heldBy.entries()]
    .filter(([checkId, fs]) => fs.length >= 2 && new Set(fs.map((f) => f.needs)).size === 1
                               && !fs.some((f) => firing.has(`${checkId}|${pathOf(f.page)}`)))
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
  const closed = new Set(fixes.flatMap((f) => (f.alsoResolves ?? []).map(
    (c) => `${c.split("/").pop()}|${f.image ?? ""}|${f.page}`)));
  const shownFixes = fixes.filter(
    (f) => !na.includes(f) && !f.coverageNote
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
  const clean = (part.brief_checks ?? [])
    .map((c) => c.split("/").pop() as string)
    .filter((c) => !fixes.some((f) => f.checkId === c));
  const dropped = part.brief_dropped ?? 0;
  // Item 180 (05-4): on a page with no JSON-LD, a check that validates the
  // markup cannot have a finding - it has nothing to read - so it is neither
  // a pass nor unmeasured. Only the check for absence can pass there.
  const noMarkup = part.key === "schema" && Boolean(page)
    && (facts?.schema_inventory ?? []).length === 0;
  const cannot = noMarkup ? clean.filter((c) => c !== "schema-missing-for-type") : [];
  const cleanMeasured = clean.filter((c) => !unmeasured.has(c) && !cannot.includes(c));
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
    <section className="part-fixes" ref={wrap}>
      <h4>Fixes</h4>
      {/* Item 180 (05-3, 06-3): not "Nothing to fix" on a scope nothing
          measured. One of the three registered states, with its reason. */}
      {!shownFixes.length && !na.length && (
        <MeasureLine {...partMeasure(part, unmeasured)} />
      )}
      {/* What this list left out, said rather than dropped: the notes are in
          the check table above with the state `not measured`, and a reader who
          counts the cards is owed the difference (audit F3). */}
      {notes.length > 0 && (
        <p className="muted part-fix-notes">
          {coverageNotes(notes.length)} not counted here —{" "}
          {notes.map((f) => f.checkId).join(" · ")}: this audit did not collect
          what {notes.length === 1 ? "it needs" : "they need"}, so there is
          nothing to fix.
        </p>
      )}
      {SECTIONS.map(([section, title]) => {
        const mine = shownFixes.filter((f) => sectionOf(f) === section);
        const held = na.filter((f) => sectionOf(f) === section);
        if (!mine.length && !held.length) return null;
        const groups = new Map<string, Fix[]>();
        for (const f of mine) groups.set(f.checkId, [...(groups.get(f.checkId) ?? []), f]);
        return (
          <Fragment key={section}>
            <h5 className={`fixes-head fixes-head-${section}`}>
              {/* Item 208: checks with a finding, as the table heading says it,
                  and the cards said as cards rather than under the same word. */}
              {title}{" "}
              <span className="muted">
                · {new Set(mine.filter((f) => !f.needs && !f.coverageNote).map((f) => f.checkId)).size}
                {" · "}{mine.length + held.length} card{mine.length + held.length === 1 ? "" : "s"}
              </span>
              {folded(cost, section) && (
                <span className="muted fixes-folded">
                  {" · "}hidden by <code>free only</code>
                </span>
              )}
            </h5>
            {!folded(cost, section) && [...groups.entries()].map(([checkId, cards]) => {
              const all = page || cards.length <= CARDS_PER_CHECK || openAll.has(checkId);
              const shown = all ? cards : cards.slice(0, CARDS_PER_CHECK);
              return (
                <Fragment key={checkId}>
                  {!page && cards.length > 1 && (() => {
                    const tpl = templateOf(cards.map((f) => f.page));
                    return (
                      <p className="muted fix-group">
                        <code>{cards[0].check}</code> · {cards.length} page
                        {cards.length === 1 ? "" : "s"}
                        {tpl && <> · <span className="fix-template">
                          template <code>{tpl.prefix}*</code> — {tpl.n} of {cards.length}</span></>}
                      </p>
                    );
                  })()}
                  {shown.map((f) => (
                    <FixCard key={f.key} fix={f} facts={facts} render={render}
                             onCopy={copy} copied={copied} n={numberOf(f)}
                             fixHeld={Boolean(f.needs) && firing.has(`${f.checkId}|${pathOf(f.page)}`)}
                             awaiting={f.candidate && !f.needs && costOf(part, f.check) === "model"}
                             siteId={siteId} onStateChanged={onStateChanged} />
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

            {!folded(cost, section)
              && [...new Map(held.map((f) => [f.needs ?? "",
                                              held.filter((x) => x.needs === f.needs)]))
                   .entries()]
                   // Security splits what it could not assess in two (brief v20
                   // step BD): what waits on the owner's authorisation for an
                   // active probe, and what waits on an input no crawl can
                   // supply. Two different conversations with the client, so
                   // authorisation first, each under its own heading.
                   .sort(([a], [b]) => Number(!AUTH.test(a)) - Number(!AUTH.test(b)))
                   .map(([needs, group], i, all) => (
              <Fragment key={needs}>
              {part.key === "security" && (i === 0 || AUTH.test(all[i - 1][0]) !== AUTH.test(needs)) && (
                <p className="fix-na-head">
                  {AUTH.test(needs) ? "Pending authorisation" : "Missing input"}
                </p>
              )}
              <p className="muted fix-na">
                {[...new Set(group.map((f) => f.checkId))].join(" · ")} not assessable
                {(() => {
                  const n = new Set(group.map((f) => pathOf(f.page)).filter(Boolean)).size;
                  return n > 1 ? ` on ${n} pages` : "";
                })()} — needs {needs}
                {heldLink(needs)
                  ? <> — <a href="#/admin?tab=sites" onClick={goHandler("#/admin?tab=sites")}>
                      set it on Admin › Sites</a></>
                  : "."}
              </p>
              </Fragment>
            ))}
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
      {page && cleanMeasured.length > 0 && (
        <p className="cause-clean-line">
          {cleanMeasured.length} check{cleanMeasured.length === 1 ? "" : "s"}{" "}
          pass on this page: {cleanMeasured.join(" · ")}
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
          <ul className="rep-dropped-rows">
            {(part.brief_dropped_rows ?? []).map((d, i) => (
              <li key={i}>
                <code>{d.check || "no check named"}</code>
                {d.page ? <> · <code>{pathOf(d.page)}</code></> : null} · {d.reason}
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

/** Block 2 on the whole site — every check the part's briefs may emit,
 *  what each source counted, and where it stands. */
function ChecksTable({ part, fixes, cost, pops, siteScope = false }: {
  part: Category; fixes: Fix[]; cost: string;
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
    if (!tableChecks.some((c) => (c.split("/").pop() as string) === id)) tableChecks.push(filed);
  }
  const rows = tableChecks.map((full) => {
    const checkId = full.split("/").pop() as string;
    const mine = fixes.filter((f) => f.checkId === checkId);
    // Items 206 and 208: one classification, read by every count column. A
    // held row (`needs`) and a coverage note say something about the check
    // and nothing about the site, so they are in State and in no count: the
    // table read "ANALYSIS 2 · 2 of 45 pages crawled · not assessable" on
    // Schema, and a held Speed row put a 0 in PAGES where the rule is a dash.
    const counted = mine.filter((f) => !f.needs && !f.coverageNote);
    const sweep = counted.filter((f) => f.sources.includes("sweep")).length;
    const brief = counted.filter((f) => f.sources.includes("brief")).length;
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
    const pages = prevalence(counted.flatMap((f) => (f.urls?.length ? f.urls : [f.page])),
                             pops, siteScope);
    const images = new Set(counted.map((f) => f.image).filter(Boolean)).size;
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
    const state = counted.length
      ? (counted.every((f) => f.candidate)
          ? (costOf(part, full) === "model" ? "not yet confirmed" : "candidate") : "open")
      : resolvedBy.length ? `resolved by the ${resolvedBy[0].check} fix`
      : !mine.length ? "clean"
      : allNotes ? MEASURE_WORD["not-measured"]
      : heldN ? `not assessable · needs ${mine.find((f) => f.needs)?.needs}`
      : "open";
    return { full, checkId, sweep, brief, pages, images, blocks, severity, state,
             allNotes, n: mine.length + resolvedBy.length, counted: counted.length };
  });
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
        const open = mine.filter((r) => r.n > 0);
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
        const spotlessAll = mine.filter((r) => r.n === 0
                                               && !unmeasured.has(r.checkId));
        const spotless = spotlessAll.filter((r) => !traced.has(r.checkId));
        const spotlessTraced = spotlessAll.filter((r) => traced.has(r.checkId));
        const unread = mine.filter((r) => r.n === 0
                                          && unmeasured.has(r.checkId));
        const away = folded(cost, section);
        return (
          <Fragment key={section}>
            <h4 className={`checks-head checks-head-${section}`}>
              {/* Item 208: the checks with at least one finding - the same
                  number the Fixes heading carries under the same word. This
                  counted every check listed, clean ones too, and Fixes
                  counted cards: "Free checks · 10" here and "· 22" there. */}
              {title} <span className="muted">· {open.filter((r) => r.counted > 0).length}</span>
              {away && (
                <span className="muted checks-folded">
                  {" · "}hidden by <code>free only</code>
                </span>
              )}
              {section === "model" && part.brief_run && (
                <span className="muted checks-prov">
                  {" · "}analysis {part.brief_run.tool}
                  {/* The time alone read as "today" for an analysis written
                      against an audit two days old. Where audits have run
                      since, the date comes with it and the count says how
                      far back — the same number and the same words the
                      Reports screen uses. */}
                  {part.brief_run.at
                    ? ` · ${(part.brief_run.audits_since ?? 0) > 0
                        ? stamp(part.brief_run.at)
                        : part.brief_run.at.slice(11, 16)}`
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
                </span>
              )}
            </h4>
            {!away && open.length > 0 && (
              <table className="findings checks-table">
                <thead>
                  <tr><th>Severity</th><th>Check</th><th className="num">Automatic</th>
                      <th className="num">Analysis</th><th className="num">Pages</th>
                      {anyImages && <th className="num">Images</th>}
                      {anyBlocks && <th className="num">Blocks</th>}
                      <th>State</th></tr>
                </thead>
                <tbody>
                  {open.map((r) => (
                    <tr key={r.full}>
                      <td><Pill tone={`sev-${r.severity}` as Tone}>{r.severity}</Pill></td>
                      <td><code>{r.full}</code></td>
                      {/* Rows raised, not pages: a findings count over the
                          record, so it renders plain and carries its
                          population rather than borrowing the page one. */}
                      <td className="num">{r.sweep
                        ? <Counted pops={pops} count={makeCount(r.sweep, "record")} />
                        : "\u2014"}</td>
                      <td className="num">{r.brief
                        ? <Counted pops={pops} count={makeCount(r.brief, "record")} />
                        : "\u2014"}</td>
                      <td className="num check-prev">
                        {r.allNotes || !r.counted
                          ? "—"
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
            {!away && spotless.length > 0 && (
              <p className="cause-clean-line">
                {spotless.length} check{spotless.length === 1 ? "" : "s"} clean on
                every{" "}
                {siteScope
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
            {/* The trace-derived clean checks, on their own denominator. The
                population is still the crawl -- these are crawled pages -- so
                only the word and the number change, which is exactly what the
                basis override on a count exists for. */}
            {!away && spotlessTraced.length > 0 && (
              <p className="cause-clean-line">
                {spotlessTraced.length} check{spotlessTraced.length === 1 ? "" : "s"}{" "}
                clean on every page this audit traced{" "}
                <span className="muted clean-pop">
                  ({part.traced_pages ?? "?"} traced
                  {pops?.crawl.size != null ? ` of ${pops.crawl.size} ${pops.crawl.basis}` : ""})
                </span>
                : {spotlessTraced.map((r) => r.checkId).join(" \u00b7 ")}
              </p>
            )}
            {!away && byReason(unread.map((r) => r.checkId), unmeasured)
              .map(([reason, ids]) => (
                <p className="cause-dark-line" key={reason}>
                  {ids.length} check{ids.length === 1 ? "" : "s"}{" "}
          {part.gate?.state === "na" ? "not applicable" : "not assessed"}{" "}
                  — {reason}: {ids.join(" · ")}
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
        const brief = fixes.filter((f) => f.sources.includes("brief"));
        const merged = brief.filter((f) => f.sources.includes("sweep") && !f.needs).length;
        const own = brief.filter((f) => !f.sources.includes("sweep") && !f.needs).length;
        const held = brief.filter((f) => f.needs).length;
        const dropped = part.brief_dropped ?? 0;
        return (
          <p className="muted brief-accounting">
            What the analysis returned, as it stands on this page: {merged} merged onto
            automatic cards · {own} on their own · {held} held · {dropped} dropped
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
const PART_LEGEND = ["action-free", "action-paid", "sev-critical", "sev-high", "sev-medium",
                     "sev-low", "sev-info", "state-candidate", "not-assessed",
                     "population-crawl", "n-of-m"];
/** Parts whose pictures draw the measurement bands, measured on twenty22 by
 *  the 166 sweep: the snippet ruler, Speed's gauges and strip, the headers
 *  grid, and the accessibility fix order. */
const BAND_PARTS = new Set(["title-desc", "speed", "security", "a11y"]);
const BAND_LEGEND = ["band-ok", "band-warn", "band-bad", "band-mute", "band-info"];
/** Words one part's own pictures draw, which the shared lists cannot carry
 *  because no other part draws them (item 166, adoption). Speed labels every
 *  figure lab or field (`speed_now.tsx`), and Title & description names the
 *  viewport a cut is measured against (`title_snippet.tsx`, item 152). The
 *  166 sweep filed both as absent from the registry.
 */
const PART_LEGEND_EXTRA: Record<string, string[]> = {
  speed: ["basis-lab", "basis-field"],
  "title-desc": ["viewport-mobile", "viewport-desktop"],
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
  const mine: Analysis | undefined = [...(lanes?.ready ?? []), ...(lanes?.available ?? [])]
    .find((a) => a.part === part.key);
  const estCost = mine?.est_cost_default ?? mine?.est_cost ?? null;
  // The scan matrix's own figure, so this button and the launcher never
  // quote different times for the same crawl.
  const estSeconds = pages ? (page ? 1 : pages) * SECS_PER_PAGE.quick : null;
  return (
    <div className="part-page">
      {/* One disclosure for the shared layout, before its first chip (item
          166): the actions' cost, the checks table's severity and states,
          the counts' population, and the measurement bands where this part's
          pictures draw them. */}
      <Legend ids={[...PART_LEGEND, ...(BAND_PARTS.has(part.key) ? BAND_LEGEND : []),
                    ...(PART_LEGEND_EXTRA[part.key] ?? [])]} />
      {part.key === "speed" && onSpeedBrief ? (
        // A SLOT ONLY SPEED FILLS: its actions are a free re-check and the
        // brief at two depths, where every other part has one brief.
        <SpeedActions now={part.speed_now ?? null} cost={estCost}
                      busy={busyTool ?? (busy === "sweep" ? "sweep" : null)}
                      note={briefNote} onRecheck={onRecheck} onBrief={onSpeedBrief} />
      ) : (
        <Actions part={part} page={page} sweep={sweep} brief={part.brief_run ?? null}
                 pages={pages} estSeconds={estSeconds} estCost={estCost}
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
          <WriteBrief runId={runId} page={page} />
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
            ? <render.now facts={facts} part={part} bounds={bounds} fixes={allFixes}
                          page={page} glow={glow} onFix={onFix} onPage={onPage} />
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
                           siteScope />
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
                                              narrow={siteNarrow} onNarrow={setNarrowInHash} />}
            {scoped && (
              <p className="muted narrow-line" role="status">
                {scoped.said}{" "}
                <SecondaryButton className="narrow-clear"
                        onClick={() => setNarrowInHash(scoped.kind, null)}>Clear</SecondaryButton>
              </p>
            )}
            <ChecksTable part={part} fixes={pageFixes} cost={cost} pops={narrowedPops}
                         siteScope={Boolean(render.siteScope)} />
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
             siteId={siteId} onStateChanged={onStateChanged} />
    </div>
  );
}
