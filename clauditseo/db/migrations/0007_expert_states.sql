-- Expert findings join the open/fixed/regressed memory, with two additions
-- the deterministic side never needed.
--
-- 'candidate': a model-raised issue seen once. Model output varies a few
-- percent run to run, so a single appearance is not yet an open finding —
-- it opens when it appears in a second run, and a candidate that fails to
-- reappear is dropped rather than remembered.
--
-- attempted_at / attempt_note: the fix loop. An operator marks that a fix
-- was attempted; the next run either verifies it (state moves to fixed) or
-- shows the finding still present despite the attempt.
--
-- SQLite cannot widen a CHECK constraint in place, so the table is rebuilt.
CREATE TABLE finding_states_new (
    site_id            TEXT NOT NULL REFERENCES sites(id),
    fingerprint        TEXT NOT NULL,
    state              TEXT NOT NULL
                       CHECK (state IN ('candidate','open','fixed','regressed',
                                        'accepted-risk')),
    changed_by_run     TEXT REFERENCES audit_runs(id),
    updated_at         TEXT NOT NULL,
    attempted_at       TEXT,
    attempt_note       TEXT,
    PRIMARY KEY (site_id, fingerprint)
);
INSERT INTO finding_states_new (site_id, fingerprint, state, changed_by_run, updated_at)
    SELECT site_id, fingerprint, state, changed_by_run, updated_at FROM finding_states;
DROP TABLE finding_states;
ALTER TABLE finding_states_new RENAME TO finding_states;
