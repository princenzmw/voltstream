-- VoltStream — schema bootstrap.
-- The Python apps run these same statements automatically on startup.
-- This file exists for running by hand in Tiger Console's SQL Editor.

CREATE TABLE IF NOT EXISTS grid_readings (
    ts             TIMESTAMPTZ      NOT NULL,
    substation_id  INTEGER          NOT NULL,
    load_mw        DOUBLE PRECISION NOT NULL,
    voltage_kv     DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('grid_readings', 'ts',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE,
    migrate_data => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS load_by_substation_5min
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '5 minutes', ts) AS bucket,
       substation_id,
       avg(load_mw) AS avg_load_mw,
       max(load_mw) AS peak_load_mw
FROM grid_readings
GROUP BY bucket, substation_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('load_by_substation_5min',
    start_offset      => INTERVAL '2 hours',
    end_offset        => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists     => TRUE);

-- Verification: partitioning and rollups
SELECT count(*) AS readings FROM grid_readings;
SELECT show_chunks('grid_readings') LIMIT 5;
SELECT bucket, substation_id, avg_load_mw, peak_load_mw
FROM load_by_substation_5min
ORDER BY bucket DESC
LIMIT 10;
