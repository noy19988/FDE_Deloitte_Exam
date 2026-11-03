"""
Helpers shared by the agent tools.

The tools return plain dictionaries (JSON), because that is what
the LLM receives. These helpers build those dictionaries.
"""

import pandas as pd
import requests

from backend.config import BASELINE_YEAR, DATA_YEAR, MIN_PASSENGERS, WEIGHTS
from backend.scoring.metrics import build_metrics
from backend.scoring.scores import (
    AIRSIDE_METRICS,
    COMPONENTS,
    LANDSIDE_METRICS,
    confidence_reason,
    score_airports,
)

API_ERROR = {
    "error": "Could not get data from the US DOT API right now. Please try again in a minute."
}

# What each metric means (as calculated in scoring/metrics.py and etl/delays.py),
# so the LLM explains the metric we really computed instead of guessing from its name.
METRIC_DEFINITIONS = {
    "load_factor_pct": f"passengers / seats in {DATA_YEAR} (how full the planes are)",
    "departures_per_runway": f"{DATA_YEAR} departures / open runways of at least 5,000 ft",
    "vs_peak_pct": f"{DATA_YEAR} passengers / the busiest YEAR from 2014 to {DATA_YEAR - 1} "
                   "(above 100 = a new record year; it is not about months or departures)",
    "growth_vs_baseline_pct": f"change in passengers, {DATA_YEAR} vs {BASELINE_YEAR} (before COVID)",
    "growth_vs_last_year_pct": f"change in passengers, {DATA_YEAR} vs {DATA_YEAR - 1}",
    "avg_taxi_out_min": "average minutes from leaving the gate to take-off",
    "nas_delay_pct": "share of arriving flights delayed by the National Airspace System (weather, traffic volume)",
    "cancel_pct": "share of departing flights that were cancelled",
    "passengers": f"departing passengers in {DATA_YEAR}",
    "fare_premium_pct": "how much more expensive fares are than in comparable markets",
}

# Where every number comes from - the agent shows this to the user.
DATA_NOTES = [
    f"All {DATA_YEAR} numbers are actual reported data, not projections.",
    f"Passengers, seats, departures: US DOT T-100 (live API), year {DATA_YEAR}. "
    "Passengers = departing passengers.",
    f"Fare premium: DOT Consumer Airfare Report, Table 7 (live API), {DATA_YEAR}. "
    "Covers about 200 airports.",
    f"Delays, taxi-out, cancellations: BTS On-Time files, {DATA_YEAR}. "
    "Domestic flights of large US airlines only.",
    "Runways: OurAirports, counting open runways of at least 5,000 ft.",
    f"Metric percentiles compare an airport with the ~230 US airports with {MIN_PASSENGERS:,}+ passengers: "
    "relative, not absolute (90 = higher than ~90% of airports).",
    "Total, airside and landside scores (and components built from several metrics) "
    "are averages of those percentiles (0-100), "
    "so they are NOT a share of airports - higher just means stronger pressure.",
    # Which metrics make up which score - built from the code, so the explanation always matches it.
    "Each component is the average of its metrics' percentiles: "
    + "; ".join(f"{name} = {', '.join(metrics)}" for name, metrics in COMPONENTS.items()) + ".",
    f"Airside pressure (runways, airspace) = {', '.join(AIRSIDE_METRICS)}. "
    f"Landside pressure (terminal, passengers) = {', '.join(LANDSIDE_METRICS)}.",
    "Metric definitions: " + "; ".join(f"{name} = {meaning}" for name, meaning in METRIC_DEFINITIONS.items()) + ".",
]


def side_of(metric):
    """Which side of the airport a metric describes: airside, landside or neither."""
    if metric in AIRSIDE_METRICS:
        return "airside"
    if metric in LANDSIDE_METRICS:
        return "landside"
    return "neither"


def plain(value):
    """Turn a pandas value into a plain Python value the LLM can read (NaN -> None)."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):  # numpy numbers -> Python numbers
        value = value.item()
    if isinstance(value, float):
        value = round(value, 1)
    return value


def load_scored_airports(weights=None):
    """
    Build the scored table (calls the live API).
    Returns None if the API is not reachable.
    """
    try:
        return score_airports(build_metrics(), weights or WEIGHTS)
    except requests.RequestException:
        return None


def warnings_for(row):
    """Things the user should know before trusting this airport's score."""
    warnings = []
    missing = [name for name in COMPONENTS if pd.isna(row[name])]
    if missing:
        warnings.append(f"Missing data for: {', '.join(missing)} (its weight was shared by the other components).")
    if not row["baseline_passengers"] >= MIN_PASSENGERS:  # also true when there is no baseline data
        warnings.append(f"New or small service in {BASELINE_YEAR} (fewer than {MIN_PASSENGERS:,} passengers), "
                        f"so growth vs {BASELINE_YEAR} is not calculated; demand growth uses growth vs last year only.")
    if pd.notna(row["cargo_share_pct"]) and row["cargo_share_pct"] >= 50:
        warnings.append(f"Cargo airport: {plain(row['cargo_share_pct'])}% of flights are cargo, "
                        "so passenger metrics tell only part of the story.")
    return warnings


def airport_summary(row):
    """The short version of one airport - used in rankings."""
    return {
        "code": row["code"],
        "name": row["name"],
        "city": row["city"],
        "state": row["state"],
        "national_rank": plain(row["rank"]),
        "total_score": plain(row["total_score"]),
        "confidence": row["confidence"],
        "confidence_reason": confidence_reason(row),
        "components": {name: plain(row[name]) for name in COMPONENTS},
        "airside_pressure": plain(row["airside"]),
        "landside_pressure": plain(row["landside"]),
        "passengers": plain(row["passengers"]),
        "warnings": warnings_for(row),
    }


def airport_details(row):
    """
    The long version: summary + every raw metric with its percentile.
    Each metric also says which component and which side it belongs to,
    so the LLM explains a score only with the metrics that are really in it.
    """
    details = airport_summary(row)
    details["metrics"] = {
        metric: {
            "value": plain(row[metric]),
            "percentile": plain(row[f"{metric}_pctl"]),
            "component": component,
            "side": side_of(metric),
        }
        for component, metrics in COMPONENTS.items()
        for metric in metrics
    }
    return details
