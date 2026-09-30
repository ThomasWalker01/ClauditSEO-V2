/** The Precheck pane: what the site publishes about itself, counted, and
 *  the control that counts it. Tile 1 on the rail.
 *
 *  Brief v4 Item 3b (`_plans/site-screen-brief-v4-2026-09-03.md`): its own
 *  file, like the other panes since brief step 8 (CQ-02). The pane held
 *  the panel alone; Item 2 adds the now-versus-prior table and the scan
 *  suggestion here, and nothing else belongs on it.
 */
import { Fragment } from "react";
import type React from "react";
import { AnatomyScreen } from "./anatomy";
import { Card } from "./components";
import { PrecheckPanel } from "./precheck";

export function PrecheckPane({ siteId, a }: { siteId: string; a: AnatomyScreen }) {
  const { precheck, setPreTick, compare } = a;
  return (
    <Card>
      <PublishedLine a={a} />
      <PrecheckPanel siteId={siteId} data={precheck} compare={compare}
                     onRan={() => setPreTick((t) => t + 1)} />
    </Card>
  );
}

/** What the site publishes, what moved since the last check, and why more
 *  may be audited than published: the sidebar's pages line, re-homed here
 *  when the sidebar was retired (brief v24 step BO; channel ruling
 *  2026-09-15). These are precheck counts, so they stand on the precheck
 *  block beside the sitemap read; how much of the site was audited is the
 *  landing's measured lane, and is said here only inside the UX-18 clause
 *  that explains a figure above the published one. */
function PublishedLine({ a }: { a: AnatomyScreen }) {
  const { precheck, compare, data } = a;
  if (!precheck) return null;
  const added = compare?.diff.full.known ? compare.diff.full.added.length : 0;
  const gone = compare?.diff.full.known ? compare.diff.full.removed.length : 0;
  const published = precheck.sitemap_urls ?? precheck.page_urls.length;
  const auditedN = data?.current?.last_audit ? data.pages.length : null;
  const navMissing = precheck.not_in_sitemap.length;
  // Joined with " · " so the line never opens on a separator.
  const pieces: React.ReactNode[] = [];
  if (compare?.prior.kind) {
    // Both directions when both moved (brief v12 step AN): `+2 · −2` says two
    // pages arrived and two went, which `±0 · 2 gone` did not.
    pieces.push(added && gone
      ? <><span className="pre-added">+{added}</span>{" · "}
          <span className="pre-removed">−{gone}</span>{" since last check"}</>
      : <>{added ? <span className="pre-added">+{added}</span> : "±0"} since last check
          {gone ? <> · <span className="pre-removed">{gone}</span> gone</> : ""}</>);
  }
  // More audited than published reads as an error until it is said why
  // (brief v5 step R, UX-18): the crawl reached the nav pages the sitemap
  // does not list.
  if (auditedN !== null && auditedN > published && navMissing > 0) {
    pieces.push(<>{auditedN} audited ({navMissing} nav page{navMissing === 1 ? "" : "s"} not in sitemap)</>);
  }
  return (
    <p className="pre-published">
      <b>{published}</b> <span className="muted">pages published</span>
      {pieces.length > 0 && <>{" · "}<span className="muted pre-pages-line">
        {pieces.map((x, i) => <Fragment key={i}>{i > 0 && " · "}{x}</Fragment>)}
      </span></>}
    </p>
  );
}
