-- The operator's stated target locales (2026-10-03, after item 274).
--
--   target_locales - comma-separated BCP 47 tags ("en-AU, en-GB"). The
--       hreflang gate decided from the crawl alone that a one-locale site has
--       nothing to declare, and the only thing its reason said would change
--       that - "a target locale you state under this analysis's inputs" - was
--       an input no site-level screen collected. Stored on the site so the
--       gate, re-derived on every read, reads it too; the International part
--       page edits it. NULL states none.
ALTER TABLE sites ADD COLUMN target_locales TEXT;
