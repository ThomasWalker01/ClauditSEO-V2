-- Item 253: what a run's own evidence says the site has, and how its scope
-- label was arrived at.
--
-- `known_paths` is the page floor's denominator: the count the run's
-- sitemaps declared, or - where it read no sitemap - what its own crawl
-- discovered (fetched plus still queued). A run labelled site or full is a
-- reading of the site only if it read at least 50 pages or at least half of
-- this. On the row, not in the evidence blob, so the SQL that picks a site's
-- reference run asks the same question as `runs.meets_page_floor`. NULL where
-- nothing says (in flight, or no evidence): the run passes on its label.
--
-- `scope_source` is `posted` where the launcher named the scope and
-- `derived-from-tier` where it was read off the tier the run executed at.
-- NULL where nobody said (a row from before this column).
ALTER TABLE audit_runs ADD COLUMN known_paths INTEGER;
ALTER TABLE audit_runs ADD COLUMN scope_source TEXT;
