/**
 * A small markdown renderer for expert briefs and client reports.
 *
 * These reports are markdown and were being shown inside <pre>, so a brief
 * like site-architecture arrived as 11,358 words containing 244 table rows
 * and 48 headings displayed as monospace text, separator rows and all. That
 * is unreadable for an operator and unusable in front of a client.
 *
 * Written by hand because the runtime dependency list is deliberately just
 * react and react-dom, and the input is narrow: the briefs emit headings,
 * pipe tables, lists, fenced code, blockquotes and inline emphasis. Anything
 * it does not recognise falls through as a paragraph rather than vanishing —
 * losing a line of a report is far worse than rendering it plainly.
 */
import { SecondaryButton } from "./buttons";
import React from "react";
import { ProbeProvider, ToConfirm } from "./probes";
import { Pill } from "./pill";

/** Inline: code, bold, italic, links, bare URLs, and `[TO CONFIRM: …]`.
 *
 *  Bare URLs matter — the affected pages a brief names are the actionable
 *  part of it, and they should be one click away rather than copied out by
 *  hand.
 *
 *  `[TO CONFIRM: …]` is here rather than in a panel because it is a sentence
 *  in the report, and F-05 turns it into a control without moving it: an
 *  item settled somewhere else while the paragraph still reads "[TO CONFIRM]"
 *  would be the product disagreeing with itself on one screen. Ahead of the
 *  link branch in the alternation, or `[TO CONFIRM: …]` never reaches it —
 *  the link pattern claims any `[…](…)`, and more to the point a marker
 *  containing a URL would be split across two tokens.
 */
export function inline(text: string, keyBase = "i"): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const pattern =
    /(\[TO CONFIRM:[^\]]*\])|(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s<>()[\]|,;"']+)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let n = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyBase}-${n++}`;
    if (token.startsWith("[TO CONFIRM:")) {
      /* Normalised exactly as `probes.normalise` normalises it — every run of
         whitespace to one space. The server keys the item list on that
         string, and the two sides see different whitespace for the same
         marker: these markers are long and wrap in the stored markdown, and
         a paragraph's lines are joined with a space before they reach here.
         Key on the raw text and every wrapped marker misses its entry, then
         renders as a plain `[TO CONFIRM: …]` offering nothing — which looks
         exactly like an item this product cannot measure. */
      out.push(<ToConfirm key={key}
                          text={token.slice("[TO CONFIRM:".length, -1)
                                     .trim().replace(/\s+/g, " ")} />);
    } else if (token.startsWith("`")) {
      out.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      out.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("[")) {
      const split = token.indexOf("](");
      const href = token.slice(split + 2, -1);
      out.push(
        <a key={key} href={href} target="_blank" rel="noreferrer noopener">
          {token.slice(1, split)}
        </a>,
      );
    } else if (token.startsWith("http")) {
      out.push(
        <a key={key} href={token} target="_blank" rel="noreferrer noopener">
          {token}
        </a>,
      );
    } else {
      out.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const isTableRule = (line: string) => /^\|?[\s:|-]*-[\s:|-]*\|?$/.test(line.trim());
const cells = (line: string) =>
  line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

export function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/** Headings in document order, for the contents list. */
export function outline(source: string): { level: number; text: string }[] {
  const found: { level: number; text: string }[] = [];
  let fenced = false;
  for (const line of source.split("\n")) {
    if (line.trimStart().startsWith("```")) fenced = !fenced;
    if (fenced) continue;
    const m = /^(#{1,4})\s+(.*)$/.exec(line);
    if (m) found.push({ level: m[1].length, text: m[2].replace(/[#*`]/g, "").trim() });
  }
  return found;
}

export function Markdown({ source }: { source: string }): React.ReactElement {
  const lines = source.split("\n");
  const blocks: React.ReactNode[] = [];
  let paragraph: string[] = [];
  let key = 0;

  const flush = () => {
    if (!paragraph.length) return;
    blocks.push(<p key={`p${key++}`}>{inline(paragraph.join(" "), `p${key}`)}</p>);
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {                       // fenced code
      flush();
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) body.push(lines[i++]);
      blocks.push(<pre key={`c${key++}`} className="md-code"><code>{body.join("\n")}</code></pre>);
      continue;
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(trimmed);
    if (heading) {
      flush();
      const text = heading[2].replace(/[#*`]/g, "").trim();
      const Tag = `h${Math.min(heading[1].length + 1, 6)}` as "h2";
      blocks.push(<Tag key={`h${key++}`} id={slug(text)}>{inline(text, `h${key}`)}</Tag>);
      continue;
    }

    if (/^(-{3,}|_{3,}|\*{3,})$/.test(trimmed)) {
      flush();
      blocks.push(<hr key={`r${key++}`} />);
      continue;
    }

    // Pipe table: a header row followed by a |---|---| rule.
    if (trimmed.startsWith("|") && isTableRule(lines[i + 1] ?? "")) {
      flush();
      const head = cells(line);
      const body: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) body.push(cells(lines[i++]));
      i--;
      blocks.push(
        <div key={`t${key++}`} className="md-table-wrap">
          <table className="md-table">
            <thead>
              <tr>{head.map((c, n) => <th key={n}>{inline(c, `th${n}`)}</th>)}</tr>
            </thead>
            <tbody>
              {body.map((row, r) => (
                <tr key={r}>{row.map((c, n) => <td key={n}>{inline(c, `td${r}-${n}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (trimmed.startsWith(">")) {
      flush();
      const quote: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quote.push(lines[i++].trim().replace(/^>\s?/, ""));
      }
      i--;
      blocks.push(
        <blockquote key={`q${key++}`}>{inline(quote.join(" "), `q${key}`)}</blockquote>,
      );
      continue;
    }

    const bullet = /^[-*+]\s+(.*)$/.exec(trimmed);
    const numbered = /^(\d+)[.)]\s+(.*)$/.exec(trimmed);
    if (bullet || numbered) {
      flush();
      const ordered = !!numbered;
      const items: string[] = [];
      while (i < lines.length) {
        const t = lines[i].trim();
        const b = /^[-*+]\s+(.*)$/.exec(t);
        const o = /^(\d+)[.)]\s+(.*)$/.exec(t);
        if (b && !ordered) items.push(b[1]);
        else if (o && ordered) items.push(o[2]);
        else if (t && items.length && lines[i].startsWith("  ")) {
          items[items.length - 1] += ` ${t}`;      // continuation line
        } else break;
        i++;
      }
      i--;
      const made = items.map((item, n) => <li key={n}>{inline(item, `li${n}`)}</li>);
      blocks.push(ordered ? <ol key={`l${key++}`}>{made}</ol> : <ul key={`l${key++}`}>{made}</ul>);
      continue;
    }

    if (!trimmed) flush();
    else paragraph.push(trimmed);
  }
  flush();
  return <div className="md">{blocks}</div>;
}

/** A bare capitalised line acting as a section label.
 *
 *  The briefs are operator-authored and do not agree on how to mark a
 *  section: one emits `## PARITY TABLE`, the next emits a naked line reading
 *  `RENDER PATH TIMELINE`. Handling only the markdown form left half the
 *  reports as a single unfoldable block, so both are recognised. Kept
 *  deliberately strict — short, fully capitalised, no trailing punctuation —
 *  because a shouted sentence inside the prose must not become a section. */
const BARE_LABEL = /^[A-Z][A-Z0-9 &/,'’()—–-]{2,58}$/;

const isLabel = (line: string) =>
  BARE_LABEL.test(line) && /[A-Z]{3}/.test(line) && !line.endsWith(".");

/** Split a report into its top-level sections, so each can be folded away.
 *  A brief runs to thousands of words with several long tables; as one block
 *  it can only be scrolled, not navigated. */
export function sections(source: string): { title: string; body: string }[] {
  const lines = source.split("\n");
  const out: { title: string; body: string }[] = [];
  let current = { title: "", body: [] as string[] };
  let fenced = false;

  const flush = () => {
    if (current.title || current.body.join("").trim()) {
      out.push({ title: current.title, body: current.body.join("\n") });
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) fenced = !fenced;
    if (fenced || trimmed.startsWith("|")) { current.body.push(line); continue; }

    const heading = /^#{1,2}\s+(.*)$/.exec(trimmed);
    // A bare label only counts when something follows it — otherwise a
    // capitalised table cell or a one-word answer would split the report.
    const bare = !heading && isLabel(trimmed)
      && (lines[i + 1] ?? "").trim() !== "|"
      && lines.slice(i + 1, i + 4).some((l) => l.trim());

    if (heading || bare) {
      flush();
      current = {
        title: (heading ? heading[1] : trimmed).replace(/[#*`]/g, "").trim(),
        body: [],
      };
    } else {
      current.body.push(line);
    }
  }
  flush();
  return out;
}

/**
 * A report as foldable sections.
 *
 * There was a contents list here as well, which was a duplicate of the
 * section headings: collapsed, the headings already are the contents; and
 * expanded, what a reader needs is not a list at the top but to know which
 * section they are currently inside. So the contents is gone and the heading
 * sticks to the top of the viewport while its section is open.
 *
 * (The contents also had a bug worth remembering: plain `#slug` anchors
 * collided with the app's hash router, so clicking one set the route to
 * `#assumptions`, matched nothing, and dropped the reader on the client list.
 * Any future in-report navigation must move the scroll position directly
 * rather than through the address bar.)
 */
export function ReportView({ source, runId }:
    { source: string; runId?: string }): React.ReactElement {
  const parts = React.useMemo(() => sections(source), [source]);
  const titled = parts.filter((p) => p.title);

  /* Open on the first section, collapsed on the rest. A brief runs to eight
     sections and seven thousand pixels; fully expanded, the reader lands at
     the top of a wall and scrolls blind looking for the part that matters.
     Collapsed-but-for-the-first gives an index and the summary at once,
     which is the shape the briefs are written in. Recomputed per report —
     keying on the source, not on mount, so switching tools re-folds. */
  const initial = React.useMemo(
    () => new Set(titled.slice(1).map((p) => p.title)), [source]);
  const [closed, setClosed] = React.useState<Set<string>>(initial);
  React.useEffect(() => { setClosed(initial); }, [initial]);

  const toggle = (title: string) => {
    const next = new Set(closed);
    if (next.has(title)) next.delete(title); else next.add(title);
    setClosed(next);
  };

  const allOpen = closed.size === 0;
  /* One owner for making a brief's `[TO CONFIRM: …]` items runnable (F-05).
     The wrap sat at the call site first, and there are four of them — the
     briefs panel, the run page's two report modals and the client screen's
     reading. Three of the four are the same brief opened from a different
     screen, and a probe offered on one of them and not the others is the
     drift rule 3 exists to stop. `runId` is optional because the fourth
     consumer is a client deliverable, which is read where nothing can be
     run and must keep rendering the marker as text. */
  const body = (
    <div className="report-view">
      {titled.length > 3 && (
        <div className="report-tools">
          <span className="muted">
            {titled.length} sections · {titled.length - closed.size} open
          </span>
          <SecondaryButton
                  onClick={() => setClosed(allOpen
                    ? new Set(titled.map((p) => p.title))
                    : new Set())}>
            {allOpen ? "collapse all" : "expand all"}
          </SecondaryButton>
        </div>
      )}

      {parts.map((part, n) => {
        if (!part.title) {
          return part.body.trim()
            ? <Markdown key={n} source={part.body} /> : null;
        }
        const shut = closed.has(part.title);
        return (
          <section key={n} className={`md-section${shut ? " md-shut" : ""}`}
                   data-section={slug(part.title)}>
            <button className="md-section-head" aria-expanded={!shut}
                    onClick={() => toggle(part.title)}>
              <span className="md-caret">{shut ? "▸" : "▾"}</span>
              <span>{part.title}</span>
            </button>
            {!shut && <Markdown source={part.body} />}
          </section>
        );
      })}
    </div>
  );
  return runId ? <ProbeProvider runId={runId}>{body}</ProbeProvider> : body;
}
