"""Database access for VoltStream: schema bootstrap and dashboard queries.

Everything runs against a Tiger Cloud service (managed TimescaleDB). The
schema bootstrap is fully idempotent, so it is safe to call on every start.
"""
import os
from contextlib import contextmanager

import pandas as pd
import psycopg
from dotenv import load_dotenv

from catalog import SUBSTATIONS

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and paste the "
        "connection string from your Tiger Cloud service config."
    )


@contextmanager
def get_connection():
    """Open a short-lived connection to the Tiger Cloud service."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        yield conn


def init_schema(conn) -> None:
    """Create the hypertable, a per-substation continuous aggregate and its
    auto-refresh policy. Every statement is safe to run repeatedly."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grid_readings (
            ts             TIMESTAMPTZ      NOT NULL,
            substation_id  INTEGER          NOT NULL,
            load_mw        DOUBLE PRECISION NOT NULL,
            voltage_kv     DOUBLE PRECISION NOT NULL
        )
    """)
    conn.execute("""
        SELECT create_hypertable('grid_readings', 'ts',
            chunk_time_interval => INTERVAL '1 hour',
            if_not_exists => TRUE,
            migrate_data => TRUE)
    """)
    conn.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS load_by_substation_5min
        WITH (timescaledb.continuous) AS
        SELECT time_bucket(INTERVAL '5 minutes', ts) AS bucket,
               substation_id,
               avg(load_mw) AS avg_load_mw,
               max(load_mw) AS peak_load_mw
        FROM grid_readings
        GROUP BY bucket, substation_id
        WITH NO DATA
    """)
    try:
        conn.execute("""
            SELECT add_continuous_aggregate_policy('load_by_substation_5min',
                start_offset      => INTERVAL '2 hours',
                end_offset        => INTERVAL '1 minute',
                schedule_interval => INTERVAL '1 minute',
                if_not_exists     => TRUE)
        """)
    except psycopg.Error as exc:
        print(f"note: refresh policy skipped ({exc})")


def kpis(conn) -> dict:
    """Headline grid numbers, computed in one pass with FILTER clauses."""
    avg15, peak60, readings15, readings60, stations = conn.execute("""
        SELECT avg(load_mw)   FILTER (WHERE ts > now() - INTERVAL '15 minutes'),
               max(load_mw)   FILTER (WHERE ts > now() - INTERVAL '1 hour'),
               count(*)       FILTER (WHERE ts > now() - INTERVAL '15 minutes'),
               count(*)       FILTER (WHERE ts > now() - INTERVAL '1 hour'),
               count(DISTINCT substation_id)
                              FILTER (WHERE ts > now() - INTERVAL '15 minutes')
        FROM grid_readings
    """).fetchone()
    return {
        "avg_load": float(avg15 or 0.0),
        "peak": float(peak60 or 0.0),
        "readings": readings15,
        "readings_hour": readings60,
        "stations": stations,
    }


def load_per_minute(conn, minutes: int = 60) -> pd.DataFrame:
    rows = conn.execute("""
        SELECT time_bucket(INTERVAL '1 minute', ts) AS minute,
               avg(load_mw) AS load_mw
        FROM grid_readings
        WHERE ts > now() - (%s * INTERVAL '1 minute')
        GROUP BY minute
        ORDER BY minute
    """, (minutes,)).fetchall()
    df = pd.DataFrame(rows, columns=["minute", "load_mw"])
    df["minute"] = pd.to_datetime(df["minute"]).dt.tz_convert("Africa/Nairobi")
    return df


def load_by_substation(conn, hours: int = 6) -> pd.DataFrame:
    """Per-substation average load from the continuous aggregate (realtime
    view, so the most recent un-materialized readings are included)."""
    rows = conn.execute("""
        SELECT bucket, substation_id, avg_load_mw
        FROM load_by_substation_5min
        WHERE bucket > now() - (%s * INTERVAL '1 hour')
        ORDER BY bucket
    """, (hours,)).fetchall()
    df = pd.DataFrame(rows, columns=["bucket", "substation_id", "avg_load_mw"])
    df["substation"] = df["substation_id"].map(SUBSTATIONS)
    df["bucket"] = pd.to_datetime(df["bucket"]).dt.tz_convert("Africa/Nairobi")
    return df[["bucket", "substation", "avg_load_mw"]]


def voltage_trend(conn, minutes: int = 15) -> pd.DataFrame:
    rows = conn.execute("""
        SELECT time_bucket(INTERVAL '1 minute', ts) AS minute,
               substation_id,
               avg(voltage_kv) AS voltage_kv
        FROM grid_readings
        WHERE ts > now() - (%s * INTERVAL '1 minute')
        GROUP BY minute, substation_id
        ORDER BY minute
    """, (minutes,)).fetchall()
    df = pd.DataFrame(rows, columns=["minute", "substation_id", "voltage_kv"])
    df["substation"] = df["substation_id"].map(SUBSTATIONS)
    df["minute"] = pd.to_datetime(df["minute"]).dt.tz_convert("Africa/Nairobi")
    return df[["minute", "substation", "voltage_kv"]]


def latest_readings(conn, limit: int = 10) -> pd.DataFrame:
    rows = conn.execute("""
        SELECT ts, substation_id, load_mw, voltage_kv
        FROM grid_readings
        ORDER BY ts DESC
        LIMIT %s
    """, (limit,)).fetchall()
    df = pd.DataFrame(rows, columns=["ts", "substation_id", "load_mw", "voltage_kv"])
    df["substation"] = df["substation_id"].map(SUBSTATIONS)
    df["ts"] = (pd.to_datetime(df["ts"])
                .dt.tz_convert("Africa/Nairobi")
                .dt.strftime("%H:%M:%S"))
    return df[["ts", "substation", "load_mw", "voltage_kv"]]
