-- The page a brief read joins the key, so a second page stops overwriting the
-- first.
--
-- KI-56, and the half of it an operator reads. `store_expert_report` writes
-- `INSERT OR REPLACE` against a table keyed `(run_id, tool_id)` with
-- `page_url` sitting *outside* the key (0005, line 22), so a page-scoped
-- brief run against three pages of one audit kept the prose of the third and
-- silently discarded the first two. Both paid runs of 2026-08-24 were billed
-- for three `onpage-hygiene` calls and stored one report each; the catch
-- rates of 0.60 and 0.80 that came out of them were quoted as a tier
-- difference until `analyst_cache` was replayed and both models turned out to
-- have caught it.
--
-- `QUESTIONS.md` **Q-19**, answered by the operator on 2026-08-24: *page-scope
-- the persistence*. Fix the product and not only the harness -- an operator
-- who briefs a second page today loses the first with no message, which is
-- live client-facing data loss.
--
-- **`''` and not NULL, which is the detail that decides whether this works.**
-- SQLite treats NULLs in a primary key as distinct, so a NULL `page_url`
-- inside the key would make `INSERT OR REPLACE` never replace a site-scoped
-- row again -- trading a silent delete for a silent duplicate, the same class
-- of defect facing the other way. Existing rows carry NULL for exactly the
-- site-scoped case, so `COALESCE(page_url, '')` migrates them into the value
-- that already means "this brief read the site, not a page" and no historical
-- row changes meaning. The column is `NOT NULL DEFAULT ''` so nothing can
-- reintroduce one.
--
-- SQLite cannot widen a primary key in place, so the table is rebuilt -- same
-- shape as 0005 plus every column 0006, 0016, 0017 and 0027 added, and the
-- ALTER-added columns are written out in full here because a rebuilt table
-- is no longer the accumulation of its migrations.
--
-- The `findings` half of KI-56 is not a schema change and is not here:
-- `findings` carries no page column and its `EXP:` fingerprint is
-- deliberately site-grained, so `record_expert_findings` merges across pages
-- by code instead. That is `QUESTIONS.md` **Q-23**, answered *merge across
-- pages by code* on 2026-08-25. The two halves land together, because
-- `clauditseo/golden.py`'s caveat detects the loss as *more calls billed than
-- reports stored* -- repairing this half alone would make calls equal reports
-- and silence a true warning while the findings went on being deleted.
CREATE TABLE expert_reports_new (
    run_id      TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    tool_id     TEXT NOT NULL,
    model_id    TEXT,
    page_url    TEXT NOT NULL DEFAULT '',  -- '' means site-scoped, never NULL
    report      TEXT NOT NULL,
    findings    TEXT NOT NULL DEFAULT '[]',
    figures     TEXT NOT NULL DEFAULT '[]',
    tokens      INTEGER,
    cost        REAL,              -- null unless the operator supplied rates
    truncated   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    elapsed_ms  INTEGER,
    pages_crawled INTEGER,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    cache_write INTEGER,
    cache_read  INTEGER,
    figures_withheld INTEGER,
    PRIMARY KEY (run_id, tool_id, page_url)
);
INSERT INTO expert_reports_new (run_id, tool_id, model_id, page_url, report,
                                findings, figures, tokens, cost, truncated,
                                created_at, elapsed_ms, pages_crawled,
                                tokens_in, tokens_out, cache_write, cache_read,
                                figures_withheld)
    SELECT run_id, tool_id, model_id, COALESCE(page_url, ''), report,
           findings, figures, tokens, cost, truncated,
           created_at, elapsed_ms, pages_crawled,
           tokens_in, tokens_out, cache_write, cache_read,
           figures_withheld FROM expert_reports;
DROP TABLE expert_reports;
ALTER TABLE expert_reports_new RENAME TO expert_reports;
CREATE INDEX IF NOT EXISTS idx_expert_reports_run ON expert_reports(run_id);
