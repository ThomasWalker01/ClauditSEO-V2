-- The name and mark that go on a client-facing document.
--
-- Reports carried the product's name and nothing else, so an agency handing
-- one to a client was handing over a document branded with its supplier's
-- tool. That is backwards: the client is buying the agency's judgement, and
-- the tool that produced it is the agency's business, not theirs.
--
-- Deliberately one row. This is who the operator IS, not a per-client
-- setting — an agency has one identity across every client, and making it
-- per-client would invite the mistake of sending one client's branding to
-- another.
--
-- The logo is a path, not a blob. A 200 kB image in every row of a SELECT is
-- a cost paid on every read for something displayed once, and a file on disk
-- can be replaced without a migration.
CREATE TABLE brand (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    display_name  TEXT,          -- NULL means "use the product name"
    logo_path     TEXT,
    logo_mime     TEXT,
    updated_at    TEXT
);
INSERT INTO brand (id) VALUES (1);
