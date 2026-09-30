-- Operator notes: the human context that previously lived nowhere.
-- "Client says leave the pricing page alone" is the kind of fact that
-- decides what a finding means, and no crawl can supply it.
CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_site ON notes(site_id);
