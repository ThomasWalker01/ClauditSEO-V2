import React, { useEffect, useState } from "react";

import { api, ApiError } from "./api";
import { Card } from "./components";
import { Markdown } from "./markdown";

type Deliverable = {
  id: string; template: string; audience: string; created_at: string;
  markdown: string | null; on_disk: boolean; path?: string;
  reason?: string;
  //: What this document replaced, and what replaced it. The Deliverables
  //: table states both and links here; a reader who opens a document directly
  //: reaches none of that, so it is stated here too rather than only there.
  supersedes?: string | null;
  superseded_by?: string | null;
};

/** One generated client report, read back from where it was written.
 *
 *  Read back rather than regenerated. Regenerating would produce today's
 *  document from today's findings, which is not the one the client received
 *  — and "what did we actually tell them" is the only question this screen
 *  exists to answer.
 */
export function DeliverableView({ reportId }: { reportId: string }) {
  const [doc, setDoc] = useState<Deliverable | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.get<Deliverable>(`/api/client-reports/${reportId}`)
      .then((d) => { if (live) setDoc(d); })
      .catch((e) => { if (live) setError((e as ApiError).message); });
    return () => { live = false; };
  }, [reportId]);

  /* `error`, not `err`: `.error` is declared at styles.css:154 and six other
     error paragraphs in the app use it. This one took no colour at all —
     found by the class-existence guard, not by the finding that prompted it. */
  if (error) return <Card><p className="error" role="alert">{error}</p></Card>;
  if (!doc) return null;
  return (
    <>
      <h2>Client report</h2>
      <p className="muted">
        {doc.template} · for the {doc.audience} · generated{" "}
        {doc.created_at.slice(0, 10)}
        {/* Not the absolute path. It reads
            C:\\Users\\owner\\...\\reports\\out — a home directory and an
            operator's name on a screen that gets screenshotted for a
            client. The filename is enough to find it; the rest is the
            operator's machine, not the client's business. */}
        {doc.path && (
          <> · <code>{doc.path.split(/[\\\/]/).pop()}</code></>
        )}
      </p>
      {/* Said above the document rather than below it. This screen exists to
          answer "what did we actually tell them", and whether the answer has
          since been replaced changes what the reader is looking at - so it
          belongs before the text, not after it. `QUESTIONS.md` Q-9. */}
      {doc.superseded_by && (
        <p className="muted">
          This document has been replaced by{" "}
          <a href={`#/client-reports/${doc.superseded_by}`}>a newer one</a>. It
          is kept because it is what was actually sent.
        </p>
      )}
      {doc.supersedes && (
        <p className="muted">
          Regenerated from{" "}
          <a href={`#/client-reports/${doc.supersedes}`}>an earlier document</a>,
          which is kept as the record of what was sent.
        </p>
      )}
      {doc.markdown
        ? <Card><Markdown source={doc.markdown} /></Card>
        : <Card><p className="muted">{doc.reason}</p></Card>}
    </>
  );
}
