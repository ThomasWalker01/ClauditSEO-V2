-- Item 145 (brief v22 step BG; channel ruling 20260915-1430): the agents the
-- operator refuses at the edge on purpose, beside `ai_crawler_policy` (0061).
--
--   ai_edge_blocked_agents - a comma-separated list of robots tokens from
--       `crawler.ua_matrix.UA_MATRIX_AGENTS`, non-search agents with a UA only.
--       `ai_crawler_policy` declares intent for robots.txt and never softens an
--       edge row; this is the per-agent statement that does. An agent named
--       here that the edge refuses raises `AIS/edge-blocks-ai-ua` at LOW, as the
--       policy working; an agent not named raises it HIGH. NULL names none.
ALTER TABLE sites ADD COLUMN ai_edge_blocked_agents TEXT;
