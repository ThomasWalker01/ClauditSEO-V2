-- Currency conversion for the cost log.
--
-- Two different problems, and only one of them can be looked up.
--
-- MODEL PRICES cannot. No vendor publishes a machine-readable price feed, and
-- scraping a pricing page to put a number in a client-facing cost estimate is
-- how a quote goes wrong quietly. They stay operator-entered — the existing
-- rule that no price is ever invented — but they move out of an environment
-- variable and into a row an operator can edit, with the date they were
-- entered so staleness is visible.
--
-- EXCHANGE RATES can. The ECB publishes daily reference rates, free and
-- without a key, so USD to the operator's currency is a real lookup with a
-- real observation date. Each row keeps when it was fetched: a rate presented
-- without its age is a number that silently becomes wrong.
CREATE TABLE fx_rates (
    currency    TEXT PRIMARY KEY,       -- ISO 4217, e.g. AUD
    rate        REAL NOT NULL,          -- units of `currency` per 1 USD
    source      TEXT NOT NULL,          -- who said so
    fetched_at  TEXT NOT NULL
);

-- Operator-entered prices, in $USD per MILLION tokens, superseding the env
-- var when present.
CREATE TABLE model_prices (
    model        TEXT PRIMARY KEY,
    input_usd    REAL NOT NULL,
    output_usd   REAL NOT NULL,
    entered_at   TEXT NOT NULL,
    entered_by   TEXT
);

-- Single-row app preferences. `display_currency` is the one the operator
-- quotes clients in; USD needs no rate and is the default.
CREATE TABLE app_prefs (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    display_currency  TEXT NOT NULL DEFAULT 'USD',
    updated_at        TEXT
);
INSERT INTO app_prefs (id, display_currency) VALUES (1, 'USD');
