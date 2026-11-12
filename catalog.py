"""Shared catalog of substations used by the simulator and dashboard."""

SUBSTATIONS = {
    1: "Nairobi West",
    2: "Industrial Area",
    3: "Nakuru North",
    4: "Mombasa Island",
}

# Typical demand in megawatts, used as the centre point of each
# substation's load wave.
BASE_LOAD_MW = {
    1: 62.0,
    2: 78.0,
    3: 34.0,
    4: 51.0,
}
