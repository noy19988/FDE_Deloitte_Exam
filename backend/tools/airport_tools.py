"""
The 7 tools the agent can call.

Each tool is a normal Python function. The LLM reads the function name,
the arguments and the docstring to decide when to call it - so the
docstrings are written for the LLM.

All numbers come from code (deterministic). The LLM only explains them.
"""

import pandas as pd
import requests
from google.adk.tools import ToolContext

from backend.agent.verification import is_known
from backend.config import DATA_YEAR, LONG_HAUL_MIN_FLIGHTS, MIN_PASSENGERS, TARGET_LOAD_FACTOR_PCT, WEIGHTS
from backend.data_sources.dot_api import get_yearly_traffic
from backend.data_sources.faa_api import get_live_status
from backend.db.database import engine
from backend.scoring import special
from backend.tools.common import (
    API_ERROR,
    DATA_NOTES,
    airport_details,
    airport_summary,
    load_scored_airports,
    plain,
)


def not_found(code):
    """
    Why an airport is not in our scored data.
    If it is a real airport that is just too small, say so with its real number.
    """
    code = code.upper()
    try:
        traffic = get_yearly_traffic()
        this_year = traffic[(traffic["code"] == code) & (traffic["year"] == DATA_YEAR)]
    except requests.RequestException:
        this_year = pd.DataFrame()  # API is down - fall back to the general message

    if not this_year.empty and this_year["passengers"].iloc[0] < MIN_PASSENGERS:
        passengers = int(this_year["passengers"].iloc[0])
        return {
            "error": f"{code} had {passengers:,} departing passengers in {DATA_YEAR}, "
                     f"below our threshold of {MIN_PASSENGERS:,}, so it is not scored."
        }
    # Unknown code, or a big airport outside the 50 states (e.g. a US territory).
    return {
        "error": f"{code} is not in our data. Either the code is wrong, or it is not an airport "
                 f"in the 50 US states with at least {MIN_PASSENGERS:,} departing passengers in {DATA_YEAR}."
    }


def rank_airports(
    states: list[str] | None = None,
    top_n: int = 10,
    weight_capacity_pressure: int | None = None,
    weight_demand_growth: int | None = None,
    weight_congestion: int | None = None,
    weight_market_scale: int | None = None,
    weight_pricing_power: int | None = None,
) -> dict:
    """
    Rank US airports by their expansion opportunity score (0-100).

    Use this for questions like "which airports are the best candidates for expansion?".

    Args:
        states: Optional list of 2-letter US state codes to filter by.
            For a region, pass its states. Example - New England: ["CT", "ME", "MA", "NH", "RI", "VT"].
            Leave empty for the whole US.
        top_n: How many airports to return (default 10).
        weight_capacity_pressure, weight_demand_growth, weight_congestion,
        weight_market_scale, weight_pricing_power: Optional custom weights.
            Only set these if the user asks to change the weights.
            Defaults: capacity_pressure 30, demand_growth 25, congestion 20,
            market_scale 15, pricing_power 10.
    """
    custom = {
        "capacity_pressure": weight_capacity_pressure,
        "demand_growth": weight_demand_growth,
        "congestion": weight_congestion,
        "market_scale": weight_market_scale,
        "pricing_power": weight_pricing_power,
    }
    # Start from the default weights and replace only what the user changed.
    weights = {name: (custom[name] if custom[name] is not None else WEIGHTS[name]) for name in WEIGHTS}

    scored = load_scored_airports(weights)
    if scored is None:
        return API_ERROR

    if states:
        scored = scored[scored["state"].isin([state.upper() for state in states])]

    return {
        "weights_used": weights,
        "airports_in_selection": len(scored),
        "ranking": [airport_summary(row) for _, row in scored.head(top_n).iterrows()],
        "data_notes": DATA_NOTES,
    }


def compare_airports(codes: list[str]) -> dict:
    """
    Compare two or more airports side by side, metric by metric.

    Use this for questions like "compare LAX and SNA congestion".

    Args:
        codes: 3-letter airport codes, e.g. ["LAX", "SNA"].
            Use the main airport of a city: "LA" = LAX, "Santa Ana" = SNA.
    """
    scored = load_scored_airports()
    if scored is None:
        return API_ERROR

    airports = []
    for code in codes:
        match = scored[scored["code"] == code.upper()]
        airports.append(not_found(code) if match.empty else airport_details(match.iloc[0]))

    return {"airports": airports, "data_notes": DATA_NOTES}


def get_airport_profile(code: str) -> dict:
    """
    Everything we know about one airport: scores, every metric and its percentile.

    Use this for general questions about one airport, e.g. "tell me about BOS".
    For details on several airports, call compare_airports once instead (it is faster).

    Args:
        code: 3-letter airport code, e.g. "BOS".
    """
    scored = load_scored_airports()
    if scored is None:
        return API_ERROR

    match = scored[scored["code"] == code.upper()]
    if match.empty:
        return not_found(code)
    return {**airport_details(match.iloc[0]), "data_notes": DATA_NOTES}


def long_haul_share(code: str) -> dict:
    """
    Percentage of long-haul flights departing an airport.

    Returns passenger flights, cargo flights and all flights, each with two
    distance thresholds, because the answer depends a lot on the definition.
    Explain the difference to the user.

    Args:
        code: 3-letter airport code, e.g. "ANC".
    """
    routes = pd.read_sql_table("route_stats", engine)
    match = routes[routes["code"] == code.upper()]
    if match.empty:
        return not_found(code)
    route = match.iloc[0]

    # Confidence by a fixed rule, like the other tools (so the LLM does not guess it).
    flights = int(route["passenger_flights"] + route["cargo_flights"])
    if flights >= LONG_HAUL_MIN_FLIGHTS:
        confidence, reason = "High", f"full-year data from all US and foreign airlines ({flights:,} flights)"
    else:
        confidence, reason = "Medium", f"only {flights:,} flights in {DATA_YEAR}, so a few routes change the share a lot"

    return {
        "code": code.upper(),
        "year": DATA_YEAR,
        **special.long_haul_share(route),
        "confidence": confidence,
        "confidence_reason": reason,
        "data_notes": [
            f"Source: BTS T-100 Segment {DATA_YEAR}, all US and foreign airlines.",
            "Distance = non-stop flight distance in miles. Counted by number of flights.",
            "Passenger = scheduled + charter passenger service. Cargo = scheduled + charter cargo service.",
        ],
    }


def unmet_demand(code: str) -> dict:
    """
    Estimate unmet demand at one airport: people who wanted to fly but could not
    (no seats, or prices too high). It cannot be measured directly, so it uses signals.

    Returns:
    - unmet_demand_index (0-100): average percentile of 4 signals
      (load factor, fare premium, NAS delays, cancellations), strongest signal first = the "why".
      The index is an average of percentiles, not a percentile itself - do not say
      "higher than X% of airports" about the index.
    - capacity_gap_seats: seats per year needed to bring the load factor down to a healthy level.

    Args:
        code: 3-letter airport code, e.g. "SFO".
    """
    scored = load_scored_airports()
    if scored is None:
        return API_ERROR

    match = scored[scored["code"] == code.upper()]
    if match.empty:
        return not_found(code)
    airport = match.iloc[0]

    return {
        "code": airport["code"],
        "name": airport["name"],
        **special.unmet_demand(airport),
        "signal_values": {
            name: plain(airport[name]) for name in special.UNMET_DEMAND_SIGNALS
        },
        "capacity_gap_seats": special.capacity_gap(airport["passengers"], airport["seats"]),
        "target_load_factor_pct": TARGET_LOAD_FACTOR_PCT,
        "data_notes": DATA_NOTES + [
            "Capacity gap is a lower estimate: people who gave up on flying are not in the data.",
        ],
    }


def compare_numbers(value_a: float, value_b: float, tool_context: ToolContext) -> dict:
    """
    Difference, ratio and percent difference between two numbers from the other tools.

    You must not do arithmetic yourself, so call this when the user asks for one:
    "how many more", "how much bigger", "what percent higher" and so on.
    Example: "how many more passengers does LAX have than SFO?"
    -> compare_numbers(value_a=36778508, value_b=26488386).
    Do not call it to add differences the user did not ask for.

    Args:
        value_a: a number another tool returned (e.g. LAX passengers).
        value_b: a number another tool returned (e.g. SFO passengers).
    """
    # Only numbers that came from our data, so an invented number cannot sneak in this way.
    known = tool_context.state.get("known_numbers", [])
    invented = [value for value in (value_a, value_b) if not is_known(abs(value), known)]
    if invented:
        return {"error": f"{invented} did not come from a tool result. Get the numbers from a tool first."}

    return {
        "value_a": value_a,
        "value_b": value_b,
        "difference": round(value_a - value_b, 1),
        "ratio": round(value_a / value_b, 2) if value_b else None,
        "percent_difference": round(100 * (value_a - value_b) / value_b, 1) if value_b else None,
    }


def live_status(code: str) -> dict:
    """
    What is happening at an airport right now, from the FAA:
    ground stops, delay programs, delays and closures.

    Use this only for questions about the current situation.

    Args:
        code: 3-letter airport code, e.g. "SFO".
    """
    try:
        events = get_live_status(code.upper())
    except requests.RequestException:
        return {"error": "Could not reach the FAA status service right now."}

    return {
        "code": code.upper(),
        "events": events,
        "summary": "No current FAA delays or closures." if not events else f"{len(events)} active event(s).",
        "data_notes": ["Source: FAA National Airspace System status (live)."],
    }
