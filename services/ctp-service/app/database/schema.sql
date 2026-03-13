-- schema.sql — PostgreSQL schema for the CTP corpus.
--
-- Create or update by running:
--   psql $DATABASE_URL -f schema.sql
--
-- Design notes
-- ------------
-- * ``ctp_nodes`` is the primary table; each row is one (dataset, subnet,
--   window_index) triple — i.e. one node in the prefix tree at one time slice.
-- * Timeseries are stored as native FLOAT8 arrays for efficient range queries.
-- * Statistical descriptors are JSONB for schema flexibility and GIN indexing.
-- * B-tree indexes on extracted numeric fields support fast range queries
--   without scanning the full JSONB column.

-- ---------------------------------------------------------------------------
-- Extension
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Main CTP nodes table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ctp_nodes (
    -- Identity
    ctp_id          TEXT        NOT NULL,
    dataset_name    TEXT        NOT NULL,
    subnet          CIDR        NOT NULL,
    window_index    INTEGER     NOT NULL,

    -- Source metadata
    extracted_from  TEXT,
    start_time      TIMESTAMPTZ,
    duration_seconds INTEGER    NOT NULL DEFAULT 30,

    -- Raw timeseries (one value per burst-interval bin)
    upload_timeseries   FLOAT8[]  NOT NULL DEFAULT '{}',
    download_timeseries FLOAT8[]  NOT NULL DEFAULT '{}',

    -- Aggregated counts
    contributor_count INTEGER    NOT NULL DEFAULT 0,

    -- Statistical descriptors (JSONB for query flexibility)
    intensity            JSONB NOT NULL DEFAULT '{}',
    burstiness           JSONB NOT NULL DEFAULT '{}',
    temporal_correlation JSONB NOT NULL DEFAULT '{}',
    structure            JSONB NOT NULL DEFAULT '{}',

    -- Housekeeping
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (dataset_name, subnet, window_index)
);

COMMENT ON TABLE ctp_nodes IS
    'One row per (dataset, subnet, time-window) node in the CTP prefix hierarchy.';

COMMENT ON COLUMN ctp_nodes.subnet IS
    'IPv4 CIDR subnet this node represents, e.g. 169.231.0.0/16.';

COMMENT ON COLUMN ctp_nodes.window_index IS
    'Zero-based index of the time window within the dataset.';

COMMENT ON COLUMN ctp_nodes.upload_timeseries IS
    'Per-bin outbound byte counts (bin width = burst_interval_ms from config).';

COMMENT ON COLUMN ctp_nodes.download_timeseries IS
    'Per-bin inbound byte counts.';

COMMENT ON COLUMN ctp_nodes.intensity IS
    'JSON: {mean_pps, mean_bps, mean_mbps, peak_pps, peak_bps}';

COMMENT ON COLUMN ctp_nodes.burstiness IS
    'JSON: {peak_to_mean_ratio, coefficient_of_variation, percentile_95_to_mean, on_periods, off_periods}';

COMMENT ON COLUMN ctp_nodes.temporal_correlation IS
    'JSON: {lag_1, lag_5, lag_10, lag_60}';

COMMENT ON COLUMN ctp_nodes.structure IS
    'JSON: {contributor_count, unique_source_ips, unique_dest_ips, upload_download_ratio, prefix_diversity}';

-- ---------------------------------------------------------------------------
-- Indexes for multi-dimensional CTP selection queries
-- ---------------------------------------------------------------------------

-- Intensity (most commonly queried field)
CREATE INDEX IF NOT EXISTS idx_ctp_intensity_mbps
    ON ctp_nodes USING BTREE (((intensity->>'mean_mbps')::FLOAT8));

-- Burstiness PMR
CREATE INDEX IF NOT EXISTS idx_ctp_burstiness_pmr
    ON ctp_nodes USING BTREE (((burstiness->>'peak_to_mean_ratio')::FLOAT8));

-- Burstiness CoV
CREATE INDEX IF NOT EXISTS idx_ctp_burstiness_cov
    ON ctp_nodes USING BTREE (((burstiness->>'coefficient_of_variation')::FLOAT8));

-- Temporal correlation lag-1
CREATE INDEX IF NOT EXISTS idx_ctp_lag1
    ON ctp_nodes USING BTREE (((temporal_correlation->>'lag_1')::FLOAT8));

-- Contributor count
CREATE INDEX IF NOT EXISTS idx_ctp_contributors
    ON ctp_nodes USING BTREE (contributor_count);

-- Dataset + window (for time-range queries)
CREATE INDEX IF NOT EXISTS idx_ctp_dataset_window
    ON ctp_nodes (dataset_name, window_index);

-- GIN index for arbitrary JSONB queries
CREATE INDEX IF NOT EXISTS idx_ctp_structure_gin
    ON ctp_nodes USING GIN (structure);

CREATE INDEX IF NOT EXISTS idx_ctp_intensity_gin
    ON ctp_nodes USING GIN (intensity);

-- ---------------------------------------------------------------------------
-- Datasets table — lightweight metadata about each ingested capture
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS datasets (
    dataset_name    TEXT        PRIMARY KEY,
    pcap_source     TEXT,
    capture_start   TIMESTAMPTZ,
    capture_end     TIMESTAMPTZ,
    window_duration_sec  INTEGER NOT NULL DEFAULT 30,
    burst_interval_ms    INTEGER NOT NULL DEFAULT 100,
    gateway_subnet  CIDR,
    total_windows   INTEGER     NOT NULL DEFAULT 0,
    total_users     INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE datasets IS
    'One row per ingested capture dataset.  Stores capture-level metadata.';
