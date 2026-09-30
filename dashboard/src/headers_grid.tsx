/** The response-headers grid (brief v16h, item 136i).
 *
 *  One component, two states, and **nothing changes between them except the
 *  column count and the presence of the divider and the sentence**. The
 *  cells are the same cells: a site serving the same headers everywhere is
 *  one column of eight rows, and a site that does not is fanned only on the
 *  rows where it does not.
 *
 *  That is the block's whole argument. A grid drawing one column per
 *  template group would make a uniform site look like a table of
 *  differences, and the reader would have to compare eight rows across
 *  three columns to learn that there is nothing to compare.
 *
 *  Every decision is the server's: `runs.security_headers_payload` groups
 *  the pages, decides each cell through the same function SEC's header
 *  checks call (item 143 step BD; `tec`'s `security-headers` until then), and
 *  says which rows disagree. This draws it.
 */

import { entry } from "./glossary";

/** A cell's state. `set` is good, `missing` is a gap the rest of the site
 *  does not have, `weak` is present and not doing its job, `absent` is a
 *  decision the site has not taken anywhere, `n/a` cannot apply. */
export type CellState = "set" | "missing" | "weak" | "absent" | "n/a";

export type HeaderRow = {
  key: string; label: string; agree: boolean; covered_by_check: boolean;
  cells: Record<string, CellState>; value: string;
};

export type HeadersGrid = {
  recorded: boolean; pages: number; redirects: number; fanned: boolean;
  groups: { key: string; label: string; pages: number }[];
  columns: string[];
  rows: HeaderRow[];
  odd: { group: string; lacks: string[]; pages: number; form: boolean } | null;
  in_place: number;
  absent_everywhere: string[];
};

/** One token per state (item 140's rule). `absent` is mute and not bad on
 *  purpose: a header nobody on the site has is a decision not yet taken,
 *  and colouring it like a gap would send an operator to chase two hundred
 *  identical cells. */
const TONE: Record<CellState, string> = {
  set: "ok", missing: "bad", weak: "warn", absent: "mute", "n/a": "mute",
};

/** The word in the cell, not only the fill. A state readable only as a
 *  colour fails WCAG 1.4.1, and this block is on the Security part where
 *  that would be its own joke.
 *
 *  `n/a` draws the registry's word rather than the engine's token (item 166;
 *  audit F14): `not-applicable` is "does not apply", and `N/A` was the engine
 *  key shown to a reader. Upper-cased here because every other cell in this
 *  grid is, and the grid is the one place the word is this short. */
const WORD: Record<CellState, string> = {
  set: "SET", missing: "MISSING", weak: "WEAK", absent: "ABSENT",
  "n/a": entry("not-applicable").word.toUpperCase(),
};

/** `Permissions-Policy` is the one row the brief lets this block say is not
 *  worth spending on, and only when nothing on the site uses a restricted
 *  feature. No other row generates the clause and none is invented here. */
const DO_NOT_SPEND = "Permissions-Policy";

export function HeadersGridBlock({ grid }: { grid: HeadersGrid | null | undefined }) {
  if (!grid) {
    return (
      <p className="muted hg-none">
        No crawl to read response headers from on this audit.
      </p>
    );
  }
  if (!grid.recorded) {
    return (
      <p className="muted hg-none">
        This audit stored no response headers, so what the site sends cannot be
        read back. A re-check records them.
      </p>
    );
  }
  const cols = grid.fanned ? grid.columns : [""];
  const fanned = grid.rows.filter((r) => !r.agree);
  const uniform = grid.rows.filter((r) => r.agree);
  const shown = grid.fanned ? fanned : grid.rows;
  return (
    <div className="hg">
      <table className="hg-table">
        <thead>
          <tr>
            <th scope="col">Header</th>
            {cols.map((c) => (
              <th key={c || "all"} scope="col">
                {grid.fanned
                  ? (grid.groups.find((g) => g.key === c)?.label ?? "everything else")
                  // A site-scoped claim, and it names the population it was
                  // read over (item 155): the grid is built from this run's
                  // crawl, so "every route" means every route THIS RUN
                  // FETCHED. Said rather than left to be assumed - on a
                  // partial crawl "every route" over 45 of 53 is a narrower
                  // claim than it reads.
                  : <span className="count" data-population="crawl"
                          data-value={String(grid.pages)}
                          title="Every route this audit fetched, not every route the site has.">
                      every route · {grid.pages} page
                      {grid.pages === 1 ? "" : "s"} crawled
                    </span>}
                {grid.fanned ? null : grid.groups.length > 1
                  ? ` · ${grid.groups.length} groups agree` : null}
              </th>
            ))}
            {!grid.fanned && <th scope="col">Observed</th>}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => <Row key={r.key} row={r} cols={cols} fanned={grid.fanned} />)}
          {grid.fanned && uniform.length > 0 && (
            <>
              <tr className="hg-divider">
                <th scope="rowgroup" colSpan={cols.length + 1}>
                  same on every route
                </th>
              </tr>
              {uniform.map((r) => (
                <tr key={r.key} className="hg-row">
                  <th scope="row">
                    {r.label}
                    {!r.covered_by_check && <NoCheck />}
                  </th>
                  {/* One full-width cell: the row agrees, so splitting it
                      across columns would draw a difference that is not
                      there. */}
                  <td colSpan={cols.length} className={`hg-cell tone-${TONE[first(r)]}`}>
                    <span className="hg-word">{WORD[first(r)]}</span>
                    {r.value && <span className="hg-value">{r.value}</span>}
                  </td>
                </tr>
              ))}
            </>
          )}
        </tbody>
      </table>
      {grid.fanned ? <OddRoute grid={grid} /> : <Summary grid={grid} />}
    </div>
  );
}

function first(r: HeaderRow): CellState {
  return Object.values(r.cells)[0] ?? "n/a";
}

/** A row whose state no check stands behind. Said once per row rather than
 *  left for the reader to assume the grid and the record agree everywhere:
 *  SEC raises a finding through the same decision for six of these eight, on
 *  the home page (`security_headers.COVERED_BY_CHECK`). */
function NoCheck() {
  return (
    <span className="muted hg-nocheck"
          title="The grid decides this cell on its own, looser reading of the stored response. SEC's own checks for this header ask more (a Report-Only CSP, Secure and HttpOnly on a cookie), so a SET cell here can sit beside a finding in the record.">
      {" "}· the grid's reading
    </span>
  );
}

function Row({ row, cols, fanned }: {
  row: HeaderRow; cols: string[]; fanned: boolean;
}) {
  return (
    <tr className="hg-row">
      <th scope="row">
        {row.label}
        {!row.covered_by_check && <NoCheck />}
      </th>
      {cols.map((c) => {
        const state = row.cells[c] ?? first(row);
        return (
          <td key={c || "all"} className={`hg-cell tone-${TONE[state]}`}>
            <span className="hg-word">{WORD[state]}</span>
          </td>
        );
      })}
      {!fanned && <td className="muted hg-value-col">{row.value || "—"}</td>}
    </tr>
  );
}

function Summary({ grid }: { grid: HeadersGrid }) {
  const absent = grid.absent_everywhere;
  const spend = absent.includes(DO_NOT_SPEND)
    ? "do not spend on Permissions-Policy — no restricted feature is used here"
    : "worth doing";
  return (
    <p className="muted hg-summary">
      {grid.in_place} of {grid.rows.length} in place on every route
      {absent.length > 0 && <> · {absent.length} absent everywhere</>}
      {" — "}{spend}.
    </p>
  );
}

function OddRoute({ grid }: { grid: HeadersGrid }) {
  if (!grid.odd) return null;
  const { group, lacks, form } = grid.odd;
  return (
    <p className="hg-odd">
      <b>{group}</b> is served without {lacks.length} header
      {lacks.length === 1 ? "" : "s"} the rest of the site has
      {lacks.length ? <> ({lacks.join(", ")})</> : null}.
      {form && (
        <> It is the one route that takes a customer&rsquo;s details, so it is
          the one to fix first.</>
      )}
    </p>
  );
}
