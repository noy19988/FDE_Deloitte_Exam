"""
Step 2 of scoring: turn raw metrics into scores (0-100).

1. Each metric -> percentile among all airports (0-100).
2. Each component -> average of its metrics' percentiles.
3. Total score -> weighted average of the components.
4. Airside / Landside sub-scores -> where the pressure is.
5. Confidence -> how much we can trust the score.

For every metric here, a higher value means a stronger case for expansion
(fuller planes, more growth, more delays, higher fares...).
"""

import pandas as pd

from backend.config import HIGH_CONFIDENCE_PASSENGERS, WEIGHTS

# Which metrics make up each component.
COMPONENTS = {
    "capacity_pressure": ["load_factor_pct", "departures_per_runway", "vs_peak_pct"],
    "demand_growth": ["growth_vs_baseline_pct", "growth_vs_last_year_pct"],
    "congestion": ["avg_taxi_out_min", "nas_delay_pct", "cancel_pct"],
    "market_scale": ["passengers"],
    "pricing_power": ["fare_premium_pct"],
}

# The same metrics, split by which side of the airport they describe.
AIRSIDE_METRICS = ["departures_per_runway", "avg_taxi_out_min", "nas_delay_pct", "cancel_pct"]
LANDSIDE_METRICS = ["load_factor_pct", "vs_peak_pct", "growth_vs_baseline_pct", "growth_vs_last_year_pct"]


def percentile(values):
    """
    Position of each airport among all airports, 0-100.
    90 = higher than about 90% of the airports.
    Missing values stay missing.
    """
    return values.rank(pct=True) * 100


def total_score(row, weights):
    """
    Weighted average of the components that have data.
    If a component is missing, its weight is shared by the others
    (we divide by the sum of the weights we actually used).
    """
    available = {name: weight for name, weight in weights.items() if pd.notna(row[name])}
    weighted_sum = sum(row[name] * weight for name, weight in available.items())
    return weighted_sum / sum(available.values())


def confidence(row):
    """High / Medium / Low, by fixed rules."""
    missing = sum(pd.isna(row[name]) for name in COMPONENTS)
    if missing >= 2:
        return "Low"
    if missing == 1 or row["passengers"] < HIGH_CONFIDENCE_PASSENGERS:
        return "Medium"
    return "High"


def confidence_reason(row):
    """Why the airport got its confidence level - in words, so the LLM does not guess."""
    reasons = []
    missing = [name for name in COMPONENTS if pd.isna(row[name])]
    if missing:
        reasons.append(f"missing data for {', '.join(missing)}")
    if row["passengers"] < HIGH_CONFIDENCE_PASSENGERS:
        reasons.append(f"fewer than {HIGH_CONFIDENCE_PASSENGERS:,} departing passengers")
    return "; ".join(reasons) or "all data available and a large airport"


def score_airports(metrics, weights=WEIGHTS):
    """
    Add all scores to the metrics table.
    Returns the airports sorted from highest to lowest total score.
    """
    table = metrics.copy()

    # 1. Percentile of every metric (saved as e.g. "load_factor_pct_pctl").
    all_metrics = [metric for names in COMPONENTS.values() for metric in names]
    for metric in all_metrics:
        table[f"{metric}_pctl"] = percentile(table[metric])

    # 2. Component scores = average percentile of their metrics.
    for component, metric_names in COMPONENTS.items():
        columns = [f"{metric}_pctl" for metric in metric_names]
        table[component] = table[columns].mean(axis=1)  # skips missing metrics

    # 3. Total score.
    table["total_score"] = table.apply(total_score, axis=1, weights=weights)

    # 4. Airside / Landside sub-scores (explain the score, don't change it).
    table["airside"] = table[[f"{m}_pctl" for m in AIRSIDE_METRICS]].mean(axis=1)
    table["landside"] = table[[f"{m}_pctl" for m in LANDSIDE_METRICS]].mean(axis=1)

    # 5. Confidence.
    table["confidence"] = table.apply(confidence, axis=1)

    table = table.sort_values("total_score", ascending=False)
    table["rank"] = range(1, len(table) + 1)
    return table.round(1)
