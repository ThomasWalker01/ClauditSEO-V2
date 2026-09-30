-- Item 239 step 1 (the operator's ruling, 2026-09-24): The Latest View.
--
-- `state_events`: every operator judgement on a finding, in order. A state
-- the operator set - accept, withdraw, confirm (item 237) - and an attempt
-- mark are events, not states a replay can recompute: `set_state` overwrote
-- `finding_states` with no history, so a rebuild from the runs would have
-- erased every one. The replay applies these between the runs, in time
-- order. `kind` is `state` or `attempt`; for an attempt, `to_state` is
-- "marked" or "cleared" and `note` the operator's note.
CREATE TABLE IF NOT EXISTS state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    kind TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    note TEXT,
    by_operator TEXT,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_state_events_site ON state_events (site_id, at, id);

-- `latest_view`: the site's one current record. One row per item: a page's
-- measured fields (`page`, key = path), a crawl-relative block (`block`, key =
-- dimension: the dimension's reference crawl), the newest analysis per tool
-- (`analysis`, key = tool) and the reference composite (`composite`, key =
-- `current`). Each value carries the run that measured it and when. Derived,
-- never the only copy: `latest_view.rebuild` replays it from the runs.
CREATE TABLE IF NOT EXISTS latest_view (
    site_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    run_id TEXT,
    measured_at TEXT,
    PRIMARY KEY (site_id, kind, key)
);

-- One line per rebuild, in the site's history: why, and what it changed.
CREATE TABLE IF NOT EXISTS latest_view_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL,
    at TEXT NOT NULL,
    reason TEXT NOT NULL,
    counts TEXT
);
