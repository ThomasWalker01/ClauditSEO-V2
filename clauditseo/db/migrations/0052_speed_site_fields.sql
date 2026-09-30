-- Item 141 (brief v19 step BC): the Speed brief's site-record fields that are
-- independent of the performance-trace capture — the vital budgets, the
-- framework, and the third-party map. Added during the BC foundation hold
-- because they are capture-independent (the emitters already read them where
-- set, defaulting to Google's own thresholds otherwise).
--
--   lcp_good/cls_good/inp_good/ttfb_good — the "Good" thresholds the free
--       checks judge against. Numbers, stored as TEXT holding the value like
--       the budget fields; NULL keeps Google's defaults (2500 ms / 0.10 /
--       200 ms / 800 ms). The page-weight budget is the existing budget_page_kb.
--   framework — the front-end framework (Next.js, Nuxt, WordPress …), so the
--       brief's fixes can name the mechanism; NULL means platform-generic.
--   third_party_map — host -> what it is -> business purpose, TEXT holding JSON
--       like the other map fields; read by third-party-policy. NULL means the
--       brief classifies each host itself.
ALTER TABLE sites ADD COLUMN lcp_good TEXT;
ALTER TABLE sites ADD COLUMN cls_good TEXT;
ALTER TABLE sites ADD COLUMN inp_good TEXT;
ALTER TABLE sites ADD COLUMN ttfb_good TEXT;
ALTER TABLE sites ADD COLUMN framework TEXT;
ALTER TABLE sites ADD COLUMN third_party_map TEXT;
