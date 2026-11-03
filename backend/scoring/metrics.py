"""
Step 1 of scoring: collect the raw numbers for every airport.

Puts everything we know about each airport into one table:
- from PostgreSQL: state, runways, delays, cargo flights
- from the DOT API (live): passengers, seats, departures, fare premium

Then calculates the raw metrics (load factor, growth...).
No scores yet - just real numbers.
"""

import pandas as pd

from backend.config import BASELINE_YEAR, DATA_YEAR, MIN_PASSENGERS
from backend.data_sources.dot_api import get_fare_premiums, get_yearly_traffic
from backend.db.database import engine


def passengers_in(traffic, year):
    """Passengers per airport in one year (airport code -> passengers)."""
    one_year = traffic[traffic["year"] == year]
    return one_year.set_index("code")["passengers"]


def build_metrics():
    # --- 1. Get the data ---
    airports = pd.read_sql_table("airports", engine)
    delays = pd.read_sql_table("delay_stats", engine)
    routes = pd.read_sql_table("route_stats", engine)
    traffic = get_yearly_traffic()
    fares = get_fare_premiums()

    # --- 2. Start from this year's traffic, keep only airports big enough ---
    table = traffic[traffic["year"] == DATA_YEAR]
    table = table[table["passengers"] >= MIN_PASSENGERS]

    # Add airport details. "inner" = keep only airports found in both tables,
    # which also drops US territories (they are not in our airports table).
    table = table.merge(airports, on="code", how="inner")

    # --- 3. Capacity pressure metrics ---
    table["load_factor_pct"] = 100 * table["passengers"] / table["seats"]
    table["departures_per_runway"] = table["departures"] / table["runways"]

    # Highest yearly passengers before this year (2014 .. last year).
    earlier_years = traffic[traffic["year"] < DATA_YEAR]
    previous_peak = earlier_years.groupby("code")["passengers"].max()
    table["vs_peak_pct"] = 100 * table["passengers"] / table["code"].map(previous_peak)

    # --- 4. Demand growth metrics ---
    baseline = table["code"].map(passengers_in(traffic, BASELINE_YEAR))
    last_year = table["code"].map(passengers_in(traffic, DATA_YEAR - 1))
    table["baseline_passengers"] = baseline  # kept for a warning
    # A tiny baseline (new service) makes growth look huge (e.g. +1,400%),
    # so we only compare to the baseline year if it was big enough.
    baseline = baseline.where(baseline >= MIN_PASSENGERS)
    table["growth_vs_baseline_pct"] = 100 * (table["passengers"] / baseline - 1)
    table["growth_vs_last_year_pct"] = 100 * (table["passengers"] / last_year - 1)

    # --- 5. Congestion metrics (from the On-Time files) ---
    table = table.merge(
        delays[["code", "avg_taxi_out_min", "nas_delay_pct", "cancel_pct"]],
        on="code", how="left",  # "left" = keep the airport even if it has no delay data
    )

    # --- 6. Pricing power (from the fares API) ---
    table = table.merge(fares, on="code", how="left")

    # --- 7. Cargo share (used later for a warning, not for the score) ---
    routes["cargo_share_pct"] = 100 * routes["cargo_flights"] / (
        routes["cargo_flights"] + routes["passenger_flights"]
    )
    table = table.merge(routes[["code", "cargo_share_pct"]], on="code", how="left")

    return table.round(1)
