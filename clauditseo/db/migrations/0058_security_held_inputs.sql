-- Item 143 (brief v20 step BD): the three site-record inputs the Security
-- brief's held domains name. 0057's comment said they were deliberately not
-- added; the brief asks for them, with the note that setting
-- `active_probing_authorised` enables nothing in this build, so they are.
--
--   active_probing_authorised - 'true' or NULL. Recorded and shown to the
--       brief; no sweep or probe reads it. A later brief with its own review
--       is what would act on it.
--   reputation_source - a Safe Browsing key reference or 'search-console';
--       recorded, not connected.
--   plugin_directory_feed - URL of a component version feed; recorded, not
--       fetched.
ALTER TABLE sites ADD COLUMN active_probing_authorised TEXT;
ALTER TABLE sites ADD COLUMN reputation_source TEXT;
ALTER TABLE sites ADD COLUMN plugin_directory_feed TEXT;
