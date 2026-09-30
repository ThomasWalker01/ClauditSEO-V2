-- 'withdrawn': the finding was never true — the audit that raised it could not
-- see the site.
--
-- The five states before this one all assume the finding was real and differ
-- only in what has happened to it since: open and regressed say it is present,
-- fixed says it was present and is gone, candidate says it was seen once,
-- accepted-risk says it is present and the operator has decided to live with
-- it. None of them can express "the condition was never there", so a false
-- finding could only be filed as one of two lies — `fixed`, which credits a
-- repair nobody made, or `accepted-risk`, which records an operator decision
-- nobody took.
--
-- *Case:* an audit of `www.acme.com.au` reached the site by a URL that could
-- not be served, and a crawl that fetched nothing raised `not-https` and
-- `robots-missing` against a site that is HTTPS and serves `robots.txt`
-- (`curl -sI -L http://www.acme.com.au/` -> 200 at https, `robots.txt` ->
-- 200, both 19 Aug 2026). `ef7a150` stopped future crawls doing it. The rows
-- already written needed a state that says what is actually true about them.
--
-- The transition rule, which is what keeps this from becoming a mute button:
-- a withdrawn finding raised again by a LATER RUN goes back to `open`. The
-- withdrawal retracts one audit's claim, not the question — new evidence
-- re-raises it as an ordinary open finding. It goes to `open` and not to
-- `regressed` because nothing was ever fixed, so nothing relapsed. What may
-- not reopen it is a replay of the stored history that produced it: that is
-- the same evidence being read twice, and it can only ever agree with itself.
--
-- SQLite cannot widen a CHECK constraint in place, so the table is rebuilt —
-- same shape as 0007, and all seven columns carry over.
CREATE TABLE finding_states_new (
    site_id            TEXT NOT NULL REFERENCES sites(id),
    fingerprint        TEXT NOT NULL,
    state              TEXT NOT NULL
                       CHECK (state IN ('candidate','open','fixed','regressed',
                                        'accepted-risk','withdrawn')),
    changed_by_run     TEXT REFERENCES audit_runs(id),
    updated_at         TEXT NOT NULL,
    attempted_at       TEXT,
    attempt_note       TEXT,
    PRIMARY KEY (site_id, fingerprint)
);
INSERT INTO finding_states_new (site_id, fingerprint, state, changed_by_run,
                                updated_at, attempted_at, attempt_note)
    SELECT site_id, fingerprint, state, changed_by_run,
           updated_at, attempted_at, attempt_note FROM finding_states;
DROP TABLE finding_states;
ALTER TABLE finding_states_new RENAME TO finding_states;
