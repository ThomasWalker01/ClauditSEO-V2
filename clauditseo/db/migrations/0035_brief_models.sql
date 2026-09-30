-- Which model each brief runs on by default, chosen by the operator
-- (brief v4 Item 3g).
--
-- A brief declares a tier and the tier resolves to a model (0015). That is
-- the right default and the wrong place to correct one brief: pointing the
-- render-blocking brief at a deeper model meant re-pointing every deep
-- brief, and the catalogue offered a sixteen-option select on every row as
-- the way round it - a launch-time choice that bound nothing.
--
-- A row here is the brief's own default. No row means its tier decides, so
-- an install that never opens the screen behaves exactly as before. Both a
-- single run and a batch read from here.
CREATE TABLE IF NOT EXISTS brief_models (
    tool       TEXT PRIMARY KEY,
    model      TEXT NOT NULL,
    chosen_at  TEXT NOT NULL,
    chosen_by  TEXT
);
