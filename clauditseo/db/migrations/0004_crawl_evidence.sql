-- The derived record of what a crawl saw (no page bodies), so expert tools
-- can be run against a completed audit without re-crawling the site.
ALTER TABLE audit_runs ADD COLUMN crawl_evidence TEXT;
