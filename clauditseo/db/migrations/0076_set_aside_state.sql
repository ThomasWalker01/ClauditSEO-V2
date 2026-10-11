-- 'set-aside': the page a finding names now answers an error (channel ruling
-- 20261011-0745, screen audits round 3, Links AC-01).
--
-- An automatic page-level Links finding (`inlinks-low`, `orphan`,
-- `depth-deep`, `anchor-generic`, `nofollow-internal`) on a page that later
-- answers 404 could never clear: a page fetched with an error is not "read",
-- so `measured` called the finding unmeasured, and it sat in the open counts,
-- the Links AUTOMATIC column and the link suggestions for good, telling the
-- operator to add links to a 404.
--
-- None of the six states fits. `fixed` claims a repair nobody made, and the
-- page coming back under-linked would read as a false regression;
-- `accepted-risk` is "present and lived with"; `withdrawn` is "never true".
-- `set-aside` says the question no longer applies to that page.
--
-- Transitions: `open` or `regressed` go to `set-aside` when every page the
-- finding names answered an error on this run (`measured` says
-- `inapplicable`). From `set-aside` absence changes nothing; a later run that
-- reads the page and raises the check reopens it as `open`, never
-- `regressed`, because nothing was ever fixed. Operator states are untouched.
--
-- SQLite cannot widen a CHECK constraint in place, so the table is rebuilt -
-- same shape as 0023, and all seven columns carry over.
CREATE TABLE finding_states_new (
    site_id            TEXT NOT NULL REFERENCES sites(id),
    fingerprint        TEXT NOT NULL,
    state              TEXT NOT NULL
                       CHECK (state IN ('candidate','open','fixed','regressed',
                                        'accepted-risk','withdrawn','set-aside')),
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
