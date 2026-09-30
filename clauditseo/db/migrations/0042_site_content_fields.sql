-- Brief v17 step AX: what the four Content prompts read from the site
-- record beside the crawl.
--
-- Two of these are floors the engine already applies, and they are on the
-- record because the defaults are placeholders. 300 words for a service
-- page and 600 for an article are numbers somebody chose; a client whose
-- service pages are deliberately two hundred words of specifics is not a
-- client with fifty findings, and the way to say so is to set the floor
-- rather than to accept the noise. `mandatory_formats` is the same shape
-- for a different question: which node types a page of each kind owes
-- (a table, an FAQ, a case study), which is what Coverage marks a node
-- Partial for the absence of.
--
-- `authors` and `proof_assets` are what a replacement may draw on.
-- Substance may only use facts the page, the site or these fields supply;
-- without them a row that would have named a credential returns
-- `kind: content-first` naming the fact the client must provide, which is
-- the difference between a brief that writes copy and a brief that
-- invents qualifications for somebody.
--
-- The last four are Benchmark's prerequisites, and they are registered
-- empty on purpose. Every Benchmark row is `not_assessable · needs:
-- competitor set` until they are filled, and the part page renders the
-- section disabled rather than hiding it: a section nobody can see is a
-- capability nobody knows they could have.
--
-- Scalars as text, lists and maps as JSON text. NULL means not set, and
-- each prompt states its own fallback.
ALTER TABLE sites ADD COLUMN word_floors TEXT;        -- JSON map: page type -> words
ALTER TABLE sites ADD COLUMN mandatory_formats TEXT;  -- JSON map: page type -> node types
ALTER TABLE sites ADD COLUMN authors TEXT;            -- JSON list: name/role/credentials/url
ALTER TABLE sites ADD COLUMN proof_assets TEXT;       -- JSON list: accreditations, awards, clients
ALTER TABLE sites ADD COLUMN competitors TEXT;        -- JSON list: the comparison set
ALTER TABLE sites ADD COLUMN keyword_data TEXT;       -- JSON: demand per term, where supplied
ALTER TABLE sites ADD COLUMN top10_corpus TEXT;       -- JSON: the SERP corpus to compare against
ALTER TABLE sites ADD COLUMN publish_history TEXT;    -- JSON: what was published when
