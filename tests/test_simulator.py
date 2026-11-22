"""Tests for VoltStream simulator physics, catalog invariants, and lazy DB config."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

import db
from catalog import BASE_LOAD_MW, SUBSTATIONS
from simulator import PHASES, SUBSTATION_IDS, make_readings, traffic_at


def test_catalog_and_phases_align() -> None:
    assert set(SUBSTATIONS) == set(BASE_LOAD_MW) == set(PHASES) == set(SUBSTATION_IDS)
    assert len(SUBSTATIONS) == 4
    assert all(mw > 0 for mw in BASE_LOAD_MW.values())


def test_make_readings_structure_and_bounds() -> None:
    random.seed(42)
    ts = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    walk = 0.0
    for step in range(200):
        walk = traffic_at(step, walk)
        readings = make_readings(ts, step, walk)
        assert len(readings) == len(SUBSTATIONS)
        for r_ts, sid, load_mw, voltage_kv in readings:
            base = BASE_LOAD_MW[sid]
            assert r_ts == ts
            assert sid in SUBSTATIONS
            assert round(base * 0.45, 2) <= load_mw <= round(base * 1.25, 2)
            assert 10.3 <= voltage_kv <= 11.65


def test_voltage_droop_inversely_tracks_load() -> None:
    ts = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)

    random.seed(7)
    low_load_rows = [make_readings(ts, step, walk=-0.5) for step in range(40)]
    random.seed(7)
    high_load_rows = [make_readings(ts, step, walk=0.5) for step in range(40)]

    mean_low_load = sum(r[2] for batch in low_load_rows for r in batch)
    mean_high_load = sum(r[2] for batch in high_load_rows for r in batch)
    mean_low_volt = sum(r[3] for batch in low_load_rows for r in batch)
    mean_high_volt = sum(r[3] for batch in high_load_rows for r in batch)

    assert mean_high_load > mean_low_load
    assert mean_high_volt < mean_low_volt


def test_traffic_at_stays_bounded() -> None:
    random.seed(99)
    walk = 0.0
    for step in range(500):
        walk = traffic_at(step, walk)
        assert -0.5 <= walk <= 0.5


def test_get_connection_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"), db.get_connection():
        pass


def test_init_sql_defines_hypertable_and_cagg() -> None:
    sql_path = Path(__file__).resolve().parent.parent / "sql" / "init.sql"
    sql = sql_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS grid_readings" in sql
    assert "create_hypertable" in sql
    assert "load_by_substation_5min" in sql
    assert "add_continuous_aggregate_policy" in sql
