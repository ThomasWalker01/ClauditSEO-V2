-- Brief v15 step AQ: what the Images brief reads from the site record
-- beside the crawl. The platform and the pipeline decide what a corrected
-- markup can say; the breakpoints decide what a `sizes` value means; the
-- budgets decide what "too heavy" is on this site; the review provenance
-- decides whether review markup may be written at all.
--
-- Scalars as text, lists as JSON text. NULL means not set, and the prompt
-- states its own fallback for each: breakpoints default to
-- 480/768/1024/1440/1920, the budgets to 200 KB and 1000 KB, and an empty
-- review provenance is read as unconfirmed.
ALTER TABLE sites ADD COLUMN platform TEXT;                   -- CMS or builder
ALTER TABLE sites ADD COLUMN cdn_or_image_pipeline TEXT;      -- CDN or build step
ALTER TABLE sites ADD COLUMN breakpoints TEXT;                -- JSON list of widths
ALTER TABLE sites ADD COLUMN budget_lcp_kb TEXT;              -- number as text
ALTER TABLE sites ADD COLUMN budget_page_kb TEXT;             -- number as text
ALTER TABLE sites ADD COLUMN review_provenance TEXT;          -- confirmed | unconfirmed
ALTER TABLE sites ADD COLUMN priority_internal_targets TEXT;  -- JSON list of urls
