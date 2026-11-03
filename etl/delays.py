"""
Build the delay stats table from the BTS On-Time files.

Input:  12 monthly files (every US domestic flight of large airlines).
Output: data/processed/delay_stats.csv
One row per airport: taxi-out time, cancellation rate, NAS delay rate.

Run from the project root:
    python etl/delays.py
"""

import os
import urllib.request
import zipfile

import pandas as pd

YEAR = 2025
URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)
RAW_DIR = "data/raw/ontime"
OUTPUT_PATH = "data/processed/delay_stats.csv"

# We only need these columns out of 110.
COLUMNS = ["Origin", "Dest", "TaxiOut", "Cancelled", "Diverted", "NASDelay"]


def download_month(month):
    """Download one monthly file (skip if we already have it)."""
    path = f"{RAW_DIR}/{YEAR}_{month}.zip"
    if not os.path.exists(path):
        print(f"Downloading {YEAR}-{month:02d}...")
        # Download to a temporary name first, so a stopped download
        # never leaves a broken file that looks complete.
        urllib.request.urlretrieve(URL.format(year=YEAR, month=month), path + ".part")
        os.rename(path + ".part", path)
    return path


def read_month(path):
    """Read the flights table from inside the zip file."""
    with zipfile.ZipFile(path) as z:
        csv_name = [name for name in z.namelist() if name.endswith(".csv")][0]
        return pd.read_csv(z.open(csv_name), usecols=COLUMNS)


def summarize_month(flights):
    """
    Count things per airport for one month.
    We keep totals (not averages) so we can add months together later.
    """
    # Departures: measured at the airport the flight leaves from.
    departures = flights.groupby("Origin").agg(
        departures=("Origin", "size"),
        cancelled=("Cancelled", "sum"),
        taxi_out_total=("TaxiOut", "sum"),
        taxi_out_count=("TaxiOut", "count"),
    )

    # NAS delays: measured at the airport the flight arrives at (BTS convention).
    arrived = flights[(flights["Cancelled"] == 0) & (flights["Diverted"] == 0)].copy()
    arrived["nas_delayed"] = arrived["NASDelay"].fillna(0) > 0
    arrivals = arrived.groupby("Dest").agg(
        arrivals=("Dest", "size"),
        nas_delayed=("nas_delayed", "sum"),
    )

    return departures.join(arrivals, how="outer").fillna(0)


def main():
    os.makedirs(RAW_DIR, exist_ok=True)

    monthly = []
    for month in range(1, 13):
        path = download_month(month)
        flights = read_month(path)
        monthly.append(summarize_month(flights))
        print(f"Processed {YEAR}-{month:02d}: {len(flights):,} flights")

    # Add the 12 months together (per airport).
    totals = pd.concat(monthly).groupby(level=0).sum()

    # Turn totals into averages and percentages.
    result = pd.DataFrame({
        "code": totals.index,
        "year": YEAR,
        "departures": totals["departures"].astype(int),
        "avg_taxi_out_min": (totals["taxi_out_total"] / totals["taxi_out_count"]).round(1),
        "cancel_pct": (100 * totals["cancelled"] / totals["departures"]).round(2),
        "nas_delay_pct": (100 * totals["nas_delayed"] / totals["arrivals"]).round(2),
    })

    result.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved {len(result)} airports to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
