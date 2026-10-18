-- What a brief actually cost to run, and against how big a site.
--
-- Token use scales with the crawl: the same brief against a 12-page site and a
-- 100-page site are different jobs, so a flat per-tool average predicts badly
-- for both. Recording the page count alongside the tokens lets an estimate be
-- scaled to the site in front of the operator rather than to the average of
-- every site ever audited.
--
-- Elapsed time is recorded for the same reason: "about 40 minutes" is the
-- number that decides whether a full sweep is started now or later, and it is
-- not derivable from tokens.
ALTER TABLE expert_reports ADD COLUMN elapsed_ms INTEGER;
ALTER TABLE expert_reports ADD COLUMN pages_crawled INTEGER;
