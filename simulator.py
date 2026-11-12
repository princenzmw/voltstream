"""VoltStream — grid telemetry simulator.

Streams synthetic load and voltage readings from four substations into a
Tiger Cloud hypertable. On a fresh database it backfills six hours of
history so the dashboard starts populated. Runs until interrupted with
Ctrl+C.
"""
import math
import random
import time
from datetime import datetime, timedelta, timezone

from catalog import BASE_LOAD_MW, SUBSTATIONS
from db import get_connection, init_schema

INSERT_SQL = """
INSERT INTO grid_readings (ts, substation_id, load_mw, voltage_kv)
VALUES (%s, %s, %s, %s)
"""

BACKFILL_HOURS = 6
BACKFILL_BEAT_SECONDS = 10
LIVE_BEAT_SECONDS = 2
SUBSTATION_IDS = list(SUBSTATIONS)

# Deterministic phase offsets so each substation peaks at a different
# point of the demand cycle.
PHASES = {1: 0.0, 2: 1.6, 3: 3.1, 4: 4.9}


def make_readings(ts: datetime, step: int, walk: float):
    """One reading per substation: demand wave, grid-wide drift and noise.

    Voltage follows a droop model — the heavier the load relative to the
    substation's base demand, the lower the busbar voltage.
    """
    readings = []
    for sid in SUBSTATION_IDS:
        base = BASE_LOAD_MW[sid]
        wave = 0.72 + 0.28 * math.sin(step / 45 + PHASES[sid])
        load = base * wave + walk * base * 0.1 + random.uniform(-2.5, 2.5)
        load = max(base * 0.45, min(base * 1.25, load))
        droop = -0.45 * (load / base - 0.85)
        voltage = 11.15 + droop + random.uniform(-0.08, 0.08)
        voltage = max(10.3, min(11.65, voltage))
        readings.append((ts, sid, round(load, 2), round(voltage, 3)))
    return readings


def traffic_at(step: int, walk: float) -> float:
    """Bounded random walk for grid-wide demand drift."""
    return max(-0.5, min(0.5, walk + random.uniform(-0.15, 0.15)))


def backfill(conn) -> int:
    """Fill the last six hours with history at 10-second resolution."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=BACKFILL_HOURS)
    rows, walk, step = [], 0.0, 0
    ts = start
    while ts < now:
        walk = traffic_at(step, walk)
        rows.extend(make_readings(ts, step, walk))
        ts += timedelta(seconds=BACKFILL_BEAT_SECONDS)
        step += 1
    inserted = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, chunk)
        inserted += len(chunk)
        print(f"  backfilled {inserted:,} / {len(rows):,} readings", end="\r")
    print()
    return inserted


def main():
    with get_connection() as conn:
        init_schema(conn)
        sent = conn.execute("SELECT count(*) FROM grid_readings").fetchone()[0]
        if sent == 0:
            print(f"Fresh hypertable — backfilling {BACKFILL_HOURS} hours of history")
            backfill(conn)
        print("Streaming live grid readings into Tiger Cloud. Ctrl+C to stop.\n")
        walk, step = 0.0, 0
        try:
            while True:
                walk = traffic_at(step, walk)
                step += 1
                beat = make_readings(datetime.now(timezone.utc), step, walk)
                with conn.cursor() as cur:
                    cur.executemany(INSERT_SQL, beat)
                sent += len(beat)
                for ts, sid, load, voltage in beat:
                    print(f"  {ts:%H:%M:%S}  {SUBSTATIONS[sid]:<15}"
                          f"  load {load:>6.2f} MW   {voltage:>6.3f} kV")
                print(f"  [{sent:,} readings in hypertable]")
                time.sleep(LIVE_BEAT_SECONDS)
        except KeyboardInterrupt:
            print("\nStopped. The dashboard keeps serving what has been ingested.")


if __name__ == "__main__":
    main()
