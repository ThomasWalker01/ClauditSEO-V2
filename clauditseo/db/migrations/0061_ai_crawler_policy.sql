-- Item 145 (brief v22 step BG, and its addendum): two AI-surface inputs on the
-- site record.
--
--   ai_crawler_policy - 'allow', 'block' or NULL (not stated). What the client
--       has decided about AI agents reading the site. `TEC/ai-crawler-blocked`
--       reads it: with 'block' a robots.txt block is the policy working, so the
--       row drops to LOW and is not a blocker; NULL or 'allow' keep 137's HIGH
--       blocker, because a block the policy does not describe, or contradicts,
--       is the crawl-access defect 137 named.
--   ai_field_data_source - where the server's own per-agent counts come from
--       (e.g. 'cloudflare'), beside Speed's `field_data_source`. Empty today;
--       when set, the UA matrix gains the field columns (requests, refused).
ALTER TABLE sites ADD COLUMN ai_crawler_policy TEXT;
ALTER TABLE sites ADD COLUMN ai_field_data_source TEXT;
