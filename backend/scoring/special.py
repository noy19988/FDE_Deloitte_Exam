"""
Calculations for the specific questions:
- Long-haul share (e.g. "percentage of long-haul flights out of Anchorage")
- Unmet demand index and capacity gap (e.g. "unmet demand at SFO")
"""

import pandas as pd

from backend.config import ALT_LONG_HAUL_MILES, LONG_HAUL_MILES, TARGET_LOAD_FACTOR_PCT

# The 4 signals of unmet demand (all already have percentiles from scores.py).
UNMET_DEMAND_SIGNALS = ["load_factor_pct", "fare_premium_pct", "nas_delay_pct", "cancel_pct"]


def percent(part, whole):
    """part / whole in percent, or None if there is nothing to divide by."""
    if not whole:
        return None
    return round(100 * part / whole, 1)


def long_haul_share(route):
    """
    Share of long-haul flights from one airport.
    `route` is the airport's row from the route_stats table.

    Returns three views (passenger / cargo / all), each with two thresholds,
    because the answer depends a lot on the definition.
    """
    all_flights = route["passenger_flights"] + route["cargo_flights"]
    all_long = route["passenger_long_haul"] + route["cargo_long_haul"]
    all_long_alt = route["passenger_long_haul_alt"] + route["cargo_long_haul_alt"]

    return {
        "threshold_miles": LONG_HAUL_MILES,
        "alt_threshold_miles": ALT_LONG_HAUL_MILES,
        "passenger_flights": {
            "flights": int(route["passenger_flights"]),
            "long_haul_pct": percent(route["passenger_long_haul"], route["passenger_flights"]),
            "long_haul_pct_alt": percent(route["passenger_long_haul_alt"], route["passenger_flights"]),
        },
        "cargo_flights": {
            "flights": int(route["cargo_flights"]),
            "long_haul_pct": percent(route["cargo_long_haul"], route["cargo_flights"]),
            "long_haul_pct_alt": percent(route["cargo_long_haul_alt"], route["cargo_flights"]),
        },
        "all_flights": {
            "flights": int(all_flights),
            "long_haul_pct": percent(all_long, all_flights),
            "long_haul_pct_alt": percent(all_long_alt, all_flights),
        },
    }


def unmet_demand(airport):
    """
    Unmet demand index (0-100) for one airport.
    `airport` is the airport's row from the scored table (score_airports).

    Index = average percentile of the 4 signals.
    Signals are returned from strongest to weakest - that is the "why".
    """
    # float(...) turns pandas number types into plain Python numbers.
    signals = {name: float(airport[f"{name}_pctl"]) for name in UNMET_DEMAND_SIGNALS}
    available = {name: value for name, value in signals.items() if pd.notna(value)}

    index = sum(available.values()) / len(available)
    strongest_first = dict(sorted(available.items(), key=lambda item: item[1], reverse=True))

    return {
        "unmet_demand_index": round(index, 1),
        "signals_percentile": strongest_first,
        "missing_signals": [name for name in signals if name not in available],
    }


def capacity_gap(passengers, seats, target_pct=TARGET_LOAD_FACTOR_PCT):
    """
    How many more seats are needed to bring the load factor down to the target.
    Example: 1,000 passengers, 1,100 seats, target 80%
             -> needs 1,000 / 0.8 = 1,250 seats -> 150 seats missing.
    0 if the airport is already below the target.

    This is a lower estimate: people who gave up on flying are not in the data.
    """
    seats_needed = passengers / (target_pct / 100)
    return max(0, round(seats_needed - seats))
