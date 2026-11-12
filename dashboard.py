"""VoltStream — real-time power-grid telemetry dashboard.

Renders live KPIs and charts from a Tiger Cloud hypertable, refreshing on
a timer. Run with: streamlit run dashboard.py
"""
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import plotly.express as px
import streamlit as st

from catalog import SUBSTATIONS
from db import (
    get_connection,
    init_schema,
    kpis,
    latest_readings,
    load_by_substation,
    load_per_minute,
    voltage_trend,
)

st.set_page_config(page_title="VoltStream", page_icon="◉", layout="wide")

st.sidebar.title("VoltStream")
refresh = st.sidebar.slider("Auto-refresh interval (seconds)", 3, 30, 5)
st.sidebar.caption(
    "Grid readings stream into the `grid_readings` hypertable on Tiger "
    "Cloud; a continuous aggregate rolls up per-substation load every "
    "5 minutes."
)
st.sidebar.markdown("---")
st.sidebar.caption("Python · psycopg 3 · Streamlit · Plotly")


def now_label() -> str:
    try:
        return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M:%S")
    except Exception:
        return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def styled(fig, height: int = 320):
    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=10, r=10, t=28, b=10),
        height=height,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


with get_connection() as conn:
    init_schema(conn)
    k = kpis(conn)
    per_min = load_per_minute(conn)
    by_station = load_by_substation(conn)
    voltages = voltage_trend(conn)
    latest = latest_readings(conn)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Avg load · last 15 min", f"{k['avg_load']:,.1f} MW")
c2.metric("Peak load · last hour", f"{k['peak']:,.1f} MW")
c3.metric("Readings · last 15 min", f"{k['readings']:,}")
c4.metric("Readings · last hour", f"{k['readings_hour']:,}")
c5.metric("Stations reporting", f"{k['stations']} of {len(SUBSTATIONS)}")

st.caption(f"Live view · updated {now_label()}")

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Grid load per minute · last hour")
    if per_min.empty:
        st.info("No readings yet — start the simulator: `python simulator.py`")
    else:
        fig = px.line(per_min, x="minute", y="load_mw", markers=True)
        fig.update_yaxes(title_text="MW")
        st.plotly_chart(styled(fig), width="stretch")

with col_b:
    st.subheader("Avg load per 5 min by substation · last 6 h")
    if by_station.empty:
        st.info("Aggregating — the first readings are being rolled up.")
    else:
        fig = px.area(by_station, x="bucket", y="avg_load_mw", color="substation")
        fig.update_yaxes(title_text="MW")
        st.plotly_chart(styled(fig), width="stretch")

col_c, col_d = st.columns(2)
with col_c:
    st.subheader("Voltage trend · last 15 min")
    if voltages.empty:
        st.info("No readings recorded yet.")
    else:
        fig = px.line(voltages, x="minute", y="voltage_kv", color="substation")
        fig.update_yaxes(title_text="kV")
        st.plotly_chart(styled(fig), width="stretch")

with col_d:
    st.subheader("Latest readings")
    st.dataframe(latest, hide_index=True)

time.sleep(refresh)
st.rerun()
