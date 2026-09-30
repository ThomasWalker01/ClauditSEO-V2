-- Which model each tier runs on, chosen by the operator.
--
-- The mapping existed only as three environment variables, so changing which
-- model a deep brief uses meant editing a service configuration and bouncing
-- the server. That put the most consequential cost-and-quality decision in
-- the product — Haiku at $1/$5 against Opus at $5/$25, and the difference
-- between a checklist and a judgement — behind a deployment step.
--
-- A row here overrides the environment variable for that tier. No row means
-- the environment still decides, so an install that never touches this screen
-- behaves exactly as before.
CREATE TABLE tier_models (
    tier       TEXT PRIMARY KEY CHECK (tier IN ('fast', 'standard', 'deep')),
    model      TEXT NOT NULL,
    chosen_at  TEXT NOT NULL,
    chosen_by  TEXT
);
