/** Every count carries its population (item 155).
 *
 *  The defect this file closes is the denominator, not a missing label. The
 *  check table's `35 of 68` on Twenty22 T3 was already a ratio: 23 of those 68
 *  were never fetched, and a page nobody looked at cannot be evidence that the
 *  fault is absent. Naming the 68 does not repair the inference a reader draws
 *  from a fault rate computed over pages that were never assessed — so the
 *  denominator moves to the crawl, and the population travels with the count
 *  as data rather than as prose a component writes for itself.
 *
 *  Three populations are legal, and the server names each of them
 *  (`runs.POPULATION_BASIS`) so two components cannot word the same population
 *  two ways:
 *
 *    crawl    what this run fetched. The default for anything reporting what
 *             was found, and the ONLY legal denominator for fault prevalence.
 *    site     the site as one subject rather than a page set — `siteScope`
 *             parts (security, content) and BC's `cwv-not-assessed`. These sit
 *             inline with the part's other counts rather than outside the
 *             rule; a site-scoped count has a population like any other, it
 *             simply is not a page set, and is never dressed as a page ratio.
 *    record   everything stored for the site. Legal on the page, and the right
 *             population for what-we-know and what-changed statements. Never a
 *             prevalence denominator.
 *
 *  **Rendering follows from the population.** A count whose population matches
 *  the page's scope renders plain; one that differs renders `N of M` with its
 *  basis named. That is why this beats "every count states its scope" on that
 *  option's own cost: on a full-coverage T3 run the labels correctly
 *  disappear, because there is nothing to disambiguate, and on a T1 pulse
 *  every count reads `3 of 3 crawled` under a header reading `3 of 53 on the
 *  site`. The redundancy the option feared appears only where it is genuinely
 *  redundant.
 */

import { pathOf } from "./components";

export type Population = "crawl" | "site" | "record";

/** The noun, once: "4 coverage notes". A coverage note records something the
 *  audit could not measure, so it is not a finding and is never counted with
 *  them - and a count that quietly drops four of them is the same undisclosed
 *  population this file exists to end. Home said so and the landing did not;
 *  the landing's figure also still counted them, so it read "36 findings"
 *  beside its own lane reading 32 (measured on twenty22, 2026-09-18).
 *
 *  The claim is the caller's, because the three callers make different ones:
 *  Home and the landing say these were NOT counted, and the Record says how
 *  many its list holds. Only the noun is shared, and no screen spells it. */
export const coverageNotes = (n: number | null | undefined): string =>
  n ? `${n} coverage note${n === 1 ? "" : "s"}` : "";

/** A count as data. `of` is the denominator the value is a subset of, and is
 *  null wherever it is not one of a page set — a findings count, or a
 *  site-scoped count. The renderer then states the value plain rather than
 *  inventing a ratio: `12 findings of 68 pages` is not a ratio, it is two
 *  different things divided. */
export type Count = {
  value: number; population: Population; basis: string; of: number | null;
};

export type Populations = {
  crawl: { size: number | null; basis: string; paths: string[] };
  site: { size: number | null; basis: string; paths: string[] };
  record: { size: number | null; basis: string; paths: string[] };
  /** The page's own scope, whose extent is 150 BJ's site size — the part
   *  header states coverage once from BJ, and a count covering exactly that
   *  much has nothing left to disambiguate. `pages` is null when the size is
   *  unknown, and then nothing matches and every count names itself, which is
   *  the honest answer rather than a silent plain number. */
  scope: { pages: number | null; basis: string };
};

/** 150 BJ's three numbers, as the part header reads them. */
export type Headline = {
  run_id: string;
  site_size: {
    size: number | null; declared: number; discovered: number; gap: number;
    unknown: boolean; unknown_reason: string | null;
  };
  coverage: {
    crawled: number; size: number | null; pct: number | null;
    unknown: boolean; unknown_reason: string | null;
  };
  /** `notes` is the coverage notes this run wrote and this count does NOT
   *  include (item 180's ruling 20260918-0400). Optional only so a stored
   *  payload from before the server said so still parses. */
  assessed: { assessed: number; total: number; pct: number | null; notes?: number };
  /** Critical and High findings in the run still unassessed (brief v23 step
   *  BL). Above zero, a client report cannot be generated. */
  integrity?: { count: number; critical: number; high: number };
  audited: number;
};

/** The wording, mirroring `runs.POPULATION_BASIS`. Used only where the client
 *  mints a count of its own (the per-check prevalence, computed from the
 *  part's rows); a count that arrives from the server carries its own. */
export const BASIS: Record<Population, string> = {
  crawl: "crawled",
  site: "across the site",
  record: "in the record",
};

export function makeCount(value: number, population: Population,
                          of: number | null = null): Count {
  return { value, population, basis: BASIS[population], of };
}

/** A URL's population key: path only, trailing slash normalised.
 *
 *  Must agree with `runs._host_path`, which is what builds the crawl's path
 *  set on the server — `/how-it-works` and `/how-it-works/` are one page, and
 *  an intersection that treated them as two would drop a page from the
 *  numerator and understate the prevalence it exists to state. */
export function pathKey(url: string): string {
  const p = (pathOf(url).split("?")[0] || "/");
  return p === "/" ? p : p.replace(/\/+$/, "");
}

/** Whether a count's population covers exactly the page's scope, which is the
 *  one question the render rule turns on. Site-scoped counts never match: the
 *  site as one subject is not an extent a page ratio can be taken over. */
export function matchesScope(c: Count, pops: Populations | null): boolean {
  if (c.population === "site") return false;
  if (c.of === null) return true;              // not a page subset — plain
  const scope = pops?.scope.pages ?? null;
  return scope !== null && c.of === scope;
}

/** One count, rendered by its population.
 *
 *  `data-population` is on every count this component draws, and is what
 *  `test_a_count_rendered_without_a_population_fails` reads: the guard walks
 *  the numeric cells of a rendered part page and fails on one that carries no
 *  population, which is a test of the assembly rather than of a label's
 *  presence. "The label is present" passes forever and catches nothing, and is
 *  how 139a's ordering defect repeated across four blocks. */
export function Counted({ count, pops, className = "", title, unit }: {
  count: Count;
  pops: Populations | null;
  className?: string;
  /** Extra explanation, appended after the population's own sentence. */
  title?: string;
  /** The noun the ratio counts, where naming it helps: `35 of 45 pages
   *  crawled`. Omitted on a bare figure in a column whose header says it. */
  unit?: string;
}) {
  const plain = matchesScope(count, pops);
  const noun = unit ? `${unit} ` : "";
  /** Two different reasons a count renders plain, and they were one sentence.
   *
   *  `matchesScope` returns true for `of === null` - a count that is not a page
   *  subset at all, which a findings count legitimately is - and the plain
   *  branch then wrote "the same extent as this screen's scope" for it. On the
   *  twenty22 landing that sentence was the `title` of all eighteen part
   *  counts, on a screen whose scope is 53 pages and whose record is one, and
   *  it was false on every one of them (audit F6). "Not a page subset" and
   *  "the same extent as the screen's scope" are different statements. */
  const notASubset = count.of === null;
  const why = [
    count.population === "site"
      ? "A fact about the site as one subject, not a page ratio."
      : notASubset
        ? `${count.value} ${noun}${count.basis}. Not a share of this screen's scope.`
        : plain
          ? `${count.value} ${noun}${count.basis} — the same extent as this `
            + `screen's scope, so there is nothing to disambiguate.`
          : `${count.value} of ${count.of} ${noun}${count.basis}.`,
    title ?? "",
  ].filter(Boolean).join(" ");
  return (
    <span className={`count pop-${count.population}${className ? ` ${className}` : ""}`}
          data-population={count.population}
          data-of={count.of === null ? "" : String(count.of)}
          data-value={String(count.value)}
          title={why}>
      {plain || count.of === null
        ? count.value
        : <>{count.value}<span className="count-of muted">
              {" of "}{count.of} {noun}{count.basis}
            </span></>}
    </span>
  );
}

/** The part header's one coverage statement, from 150 BJ (item 155): `45 of 53
 *  on the site, 85%`.
 *
 *  Stated once per part page and nowhere else. Option three's insight survives
 *  and its rendering does not — uncrawled really is a different state from
 *  absent, and this line is where that now lives, so the length strips need
 *  neither 42 mute bars on a Twenty22 T1 nor a second absent tone.
 *
 *  Where the size is unknown the line says so rather than falling back to the
 *  record: a coverage figure over a denominator whose source failed is the
 *  defect, not a smaller version of the answer. */
export function CoverageLine({ headline, page }: {
  headline: Headline | null | undefined; page: string;
}) {
  if (page) {
    return (
      <p className="part-coverage muted" data-scope="page">
        Narrowed to one page. Every count below states the population it was
        counted over.
      </p>
    );
  }
  if (!headline) return null;
  const { coverage, assessed } = headline;
  return (
    <p className="part-coverage muted" data-scope="site"
       data-crawled={String(coverage.crawled)}
       data-size={coverage.size === null ? "" : String(coverage.size)}>
      {coverage.unknown || coverage.size === null || coverage.pct === null ? (
        <>
          <b>{coverage.crawled}</b> pages crawled · site size not known
          {coverage.unknown_reason ? ` (${coverage.unknown_reason})` : ""} — so
          no count below can be stated as a share of the site, and each names
          the population it was counted over.
        </>
      ) : (
        <>
          {/* Singular where it is one (audit F17): every T1 run read
              "1 pages audited of 53 known". */}
          <b>{coverage.crawled} page{coverage.crawled === 1 ? "" : "s"} audited
            {" "}of {coverage.size} known</b>,{" "}
          {coverage.pct}%
          {/* The declared-versus-discovered gap, stated rather than
              bracketed (150 BJ). It was `68 audited (4 nav pages not in
              sitemap)`: the difference between the site the owner believes
              they publish and the one that exists, in parentheses. Drawn
              only where there is one, and never against a declaration that
              failed - the branch above. */}
          {headline.site_size.gap > 0 && (
            <span className="part-gap" data-gap={String(headline.site_size.gap)}>
              {" · "}<b>{headline.site_size.gap}</b> found and not declared
            </span>
          )}
        </>
      )}
      {assessed.pct !== null && (
        <span className="part-assessed">
          {" · "}{assessed.assessed} of {assessed.total} findings have been through
        </span>
      )}
    </p>
  );
}

/** A prevalence cell: the fault rate over the assessed set, and beside it what
 *  the record holds outside that set.
 *
 *  **Both halves, because neither alone is the truth.** The denominator has to
 *  be the crawl — that is the whole ruling — and the numerator has to be
 *  intersected with it or the ratio can exceed 100%. But a record accumulated
 *  across runs can hold a fault on twenty-five pages this run did not fetch,
 *  and a cell reading `0 of 16 crawled` with those twenty-five silently
 *  dropped would trade one wrong impression for another. So the second span
 *  states them: `0 of 16 crawled · 25 more in the record`. The two numbers sum
 *  to what the cell used to show on its own, with a denominator that is now
 *  correct and a population on each half. */
export function Prevalence({ prev, pops, unit = "pages", title }: {
  prev: { count: Count; unfetched: number };
  pops: Populations | null;
  unit?: string;
  title?: string;
}) {
  return (
    <>
      <Counted count={prev.count} pops={pops} unit={unit} title={title} />
      {prev.unfetched > 0 && (
        <span className="prev-outside muted" data-outside={String(prev.unfetched)}
              title={"Pages the record holds this fault on that this audit did "
                     + "not fetch. Counted here rather than inside the rate, "
                     + "because a page nobody looked at is not evidence either "
                     + "way."}>
          {" · "}{prev.unfetched} more in the record
        </span>
      )}
    </>
  );
}

/** The per-check prevalence, as the rule requires it: affected OF ASSESSED.
 *
 *  `affected` is the part's own rows for the check, which come from the
 *  RECORD — `finding_states` is site-scoped and accumulates across runs. So
 *  the numerator is intersected with the crawl before it is divided by it, or
 *  a site audited twice can report more affected pages than the run fetched
 *  and the ratio reads above 100%. The pages the record knows about and this
 *  run did not fetch are not silently dropped: they are counted and named in
 *  the cell's own explanation, because "3 more the record knows and this run
 *  did not look at" is a different statement from a prevalence.
 *
 *  A check naming no page at all is site-scoped and takes the `site`
 *  population — it is a fact about the site as one subject and is never
 *  dressed as a page ratio. */
export function prevalence(urls: string[], pops: Populations | null,
                           siteScope = false):
    { count: Count; unfetched: number } {
  const named = urls.filter(Boolean).map(pathKey);
  const distinct = new Set(named);
  if (siteScope || distinct.size === 0) {
    return { count: makeCount(distinct.size, "site"), unfetched: 0 };
  }
  const crawl = pops?.crawl;
  if (!crawl || !crawl.size) {
    // No assessed set: either no run this screen can see, or a run that
    // stored no readable page. There is no prevalence to state — a rate over
    // nothing is not a smaller rate — so the cell states what the RECORD
    // holds, with `of: null` so it renders plain. Deliberately not
    // `of: record.size`: that would be a prevalence over the record, which is
    // the one thing the rule forbids, and it would arrive by the back door on
    // exactly the runs where nobody would check it.
    return { count: makeCount(distinct.size, "record"), unfetched: 0 };
  }
  const fetched = new Set(crawl.paths);
  const inside = [...distinct].filter((p) => fetched.has(p));
  return { count: makeCount(inside.length, "crawl", crawl.size),
           unfetched: distinct.size - inside.length };
}
