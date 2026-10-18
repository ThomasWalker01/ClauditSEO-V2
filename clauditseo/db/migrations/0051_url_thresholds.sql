-- Item 141 (brief v19 step BB): the four thresholds the URLs & parameters
-- brief reads. Numbers, but stored as TEXT holding the value, exactly like the
-- budget fields (`budget_lcp_kb`, `budget_page_kb` …) the record already keeps
-- — so an unset threshold is NULL and the sweep falls back to `urlshape`'s
-- default rather than to zero.
--
--   url_max_chars      — a path longer than this fires `url-length`. Default 75.
--   slug_max_words     — a slug with more hyphen-words than this fires
--                        `url-length` too. Default 6.
--   max_depth          — a content page deeper than this many path segments
--                        fires `url-depth`. Default 3.
--   rename_inlink_cap  — the brief only proposes a `url-rename` for a page with
--                        at most this many internal links (a rename is cheap
--                        below the cap, risky above it). Default 20.
ALTER TABLE sites ADD COLUMN url_max_chars TEXT;
ALTER TABLE sites ADD COLUMN slug_max_words TEXT;
ALTER TABLE sites ADD COLUMN max_depth TEXT;
ALTER TABLE sites ADD COLUMN rename_inlink_cap TEXT;
