-- Georgia Hospital Price & Quality Explorer — Database Schema
--
-- Normalized into three core tables (hospitals, services, prices), built
-- directly from the unified flat schema validated across all six
-- hospitals in data/processed/*_flat.csv.
--
-- UPDATE: added billing_class and modifiers to services. Real-world
-- discovery while investigating Grady's CPT 70450 data: the same CPT
-- code and same plain-English description can legitimately cover
-- multiple distinct billing entities -- e.g. "facility" fee vs.
-- "professional" fee with modifier 26 (interpretation only) vs.
-- modifier TC (technical component only). Without billing_class and
-- modifiers, these looked like unexplained duplicate/conflicting
-- prices for "the same service." They're now treated as PART of a
-- service's identity, not just descriptive metadata -- two rows with
-- the same CPT code but different billing_class ARE different services.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS hospitals (
    hospital_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_name   TEXT NOT NULL UNIQUE,
    city            TEXT,
    state           TEXT,
    source_format   TEXT,
    source_url      TEXT,
    last_retrieved  TEXT
);

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
    drug_unit_type  TEXT,
    billing_class   TEXT,       -- e.g. 'facility' or 'professional'
    modifiers       TEXT        -- e.g. '26' (interpretation only) or 'TC' (technical component)
);

CREATE TABLE IF NOT EXISTS prices (
    price_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id              INTEGER NOT NULL REFERENCES services(service_id),
    setting                 TEXT,
    gross_charge             REAL,
    discounted_cash          REAL,
    minimum_charge           REAL,
    maximum_charge           REAL,
    payer_name               TEXT,
    plan_name                TEXT,
    negotiated_price          REAL,
    negotiated_percentage     REAL,
    median_amount             REAL,
    price_type                TEXT,
    resolved_price             REAL,
    methodology                TEXT
);

CREATE INDEX IF NOT EXISTS idx_services_hospital ON services(hospital_id);
CREATE INDEX IF NOT EXISTS idx_services_description ON services(description);
CREATE INDEX IF NOT EXISTS idx_services_cpt ON services(cpt_code);
CREATE INDEX IF NOT EXISTS idx_services_billing_class ON services(billing_class);
CREATE INDEX IF NOT EXISTS idx_prices_service ON prices(service_id);
CREATE INDEX IF NOT EXISTS idx_prices_payer ON prices(payer_name);
CREATE INDEX IF NOT EXISTS idx_prices_price_type ON prices(price_type);

CREATE TABLE IF NOT EXISTS quality_measures (
    quality_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id     INTEGER NOT NULL REFERENCES hospitals(hospital_id),
    measure_name    TEXT NOT NULL,
    measure_value   REAL,
    measure_unit    TEXT,
    reporting_period TEXT
);

CREATE INDEX IF NOT EXISTS idx_quality_hospital ON quality_measures(hospital_id);

CREATE TABLE IF NOT EXISTS data_quality_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id     INTEGER NOT NULL REFERENCES hospitals(hospital_id),
    check_name      TEXT NOT NULL,
    check_result    TEXT,
    row_count_checked INTEGER,
    checked_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_quality_log_hospital ON data_quality_log(hospital_id);