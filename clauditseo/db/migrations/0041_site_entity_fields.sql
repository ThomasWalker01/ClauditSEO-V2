-- Brief v16 step AS: what the Structured data brief reads from the site
-- record beside the crawl.
--
-- The distinction the two list fields carry is the one the brief exists to
-- enforce: `sameas_sources` are profiles the entity *controls* - its GBP
-- listing, its own Facebook, LinkedIn, Wikidata - and belong in `sameAs`;
-- `citation_sources` are places that mention it - directories, council
-- listings, payment providers, review sites - and belong in `subjectOf`.
-- Putting a directory in `sameAs` claims the entity is that page, which is
-- `schema-sameas-misplaced` and is why the two are stored apart rather
-- than as one list somebody sorts later.
--
-- `nap` is exact, because a NAP that differs from the page by a comma is
-- what `schema-nap-mismatch` is about and an approximate copy could not
-- find it. `locations` is one | many, which decides whether the site is one
-- node or an Organization with a LocalBusiness per site. `canonical_id` is
-- the `@id` in use or intended, and where it is empty the brief proposes
-- `<site url>/#organization` and lists that as an assumption.
--
-- Scalars as text, lists and maps as JSON text. NULL means not set, and
-- the prompt states its own fallback for each.
ALTER TABLE sites ADD COLUMN nap TEXT;                   -- exact name/address/phone
ALTER TABLE sites ADD COLUMN sameas_sources TEXT;        -- JSON list: profiles it controls
ALTER TABLE sites ADD COLUMN citation_sources TEXT;      -- JSON list: places that mention it
ALTER TABLE sites ADD COLUMN locations TEXT;             -- one | many
ALTER TABLE sites ADD COLUMN id_page_uri TEXT;           -- the entity page's URI
ALTER TABLE sites ADD COLUMN canonical_id TEXT;          -- the @id in use or intended
ALTER TABLE sites ADD COLUMN target_rich_results TEXT;   -- JSON map: page type -> results
