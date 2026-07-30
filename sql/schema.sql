-- Georgia Hospital Price & Quality Explorer — Database Schema
--
-- Normalized into three core tables (hospitals, services, prices), built
-- directly from the unified flat schema already validated across all six
-- hospitals in data/processed/*_flat.csv. Each row in a flattened CSV
-- maps to one row in `prices`, joined back to its hospital and service.
--
-- Design decision: payer_name and plan_name are kept as plain text
-- columns on the prices table rather than split into their own payers/
-- plans tables. Given this project's scope (6 hospitals, a handful of
-- procedures), the added join complexity of a separate payers table
-- isn't worth it -- but if the project grows to many more hospitals,
-- extracting a payers table (payer_id, payer_name, plan_name) would
-- reduce repeated text and make "compare prices by payer across all
-- hospitals" queries cleaner.

PRAGMA foreign_keys = ON;

-- One row per hospital in the project.
CREATE TABLE IF NOT EXISTS hospitals (
    hospital_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_name   TEXT NOT NULL UNIQUE,
    city            TEXT,
    state           TEXT,
    source_format   TEXT,       -- 'json', 'csv_flat', 'csv_wide', 'zip_csv'
    source_url      TEXT,
    last_retrieved  TEXT        -- ISO date the raw file was downloaded
);

-- One row per distinct service/item a hospital publishes a charge for.
-- A service can appear multiple times across different hospitals (same
-- description, different hospital_id) -- that's expected and useful for
-- cross-hospital comparison.
CREATE TABLE IF NOT EXISTS services (
    service_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id     INTEGER NOT NULL REFERENCES hospitals(hospital_id),
    description     TEXT NOT NULL,
    ndc_code        TEXT,
    revenue_code    TEXT,
    cdm_code        TEXT,
    hcpcs_code      TEXT,
    cpt_code        TEXT,
    drg_code        TEXT,
    drug_unit       TEXT,
    drug_unit_type  TEXT
);

-- One row per (service, setting, payer, plan) combination -- this is
-- the grain that matches a single row in the flattened CSVs.
CREATE TABLE IF NOT EXISTS prices (
    price_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id              INTEGER NOT NULL REFERENCES services(service_id),
    setting                 TEXT,       -- 'inpatient' or 'outpatient'
    gross_charge             REAL,
    discounted_cash          REAL,
    minimum_charge           REAL,
    maximum_charge           REAL,
    payer_name               TEXT,
    plan_name                TEXT,
    negotiated_price          REAL,      -- exact dollar amount, when published
    negotiated_percentage     REAL,      -- percent-of-billed rate, when published
    median_amount             REAL,      -- historical median claim amount, when published
    price_type                TEXT,      -- 'negotiated_dollar' | 'percent_of_billed'
                                          -- | 'median_estimate' | 'unavailable'
    resolved_price             REAL,      -- best usable price estimate, per price_type
    methodology                TEXT
);

-- Indexes to support the kinds of queries this project will run most:
-- comparing prices across hospitals for a given service/procedure, and
-- comparing prices across payers.
CREATE INDEX IF NOT EXISTS idx_services_hospital ON services(hospital_id);
CREATE INDEX IF NOT EXISTS idx_services_description ON services(description);
CREATE INDEX IF NOT EXISTS idx_prices_service ON prices(service_id);
CREATE INDEX IF NOT EXISTS idx_prices_payer ON prices(payer_name);
CREATE INDEX IF NOT EXISTS idx_prices_price_type ON prices(price_type);

-- Optional: CMS hospital quality measures, joined in later via facility
-- ID once src/fetch_cms_quality.py is built. Included now so the schema
-- is complete from the start.
CREATE TABLE IF NOT EXISTS quality_measures (
    quality_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id     INTEGER NOT NULL REFERENCES hospitals(hospital_id),
    measure_name    TEXT NOT NULL,
    measure_value   REAL,
    measure_unit    TEXT,
    reporting_period TEXT
);

CREATE INDEX IF NOT EXISTS idx_quality_hospital ON quality_measures(hospital_id);

-- Data-quality audit log: a structured place to record the kind of
-- findings already written up in data/README.md (e.g. "Emory: 96% of
-- sampled rows had price_type = unavailable"), so the audit results
-- live in the database itself, not just prose.
CREATE TABLE IF NOT EXISTS data_quality_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id     INTEGER NOT NULL REFERENCES hospitals(hospital_id),
    check_name      TEXT NOT NULL,      -- e.g. 'price_type_breakdown'
    check_result    TEXT,               -- e.g. 'negotiated_dollar: 2870, unavailable: 19'
    row_count_checked INTEGER,
    checked_at      TEXT                -- ISO date this check was run
);

CREATE INDEX IF NOT EXISTS idx_quality_log_hospital ON data_quality_log(hospital_id);