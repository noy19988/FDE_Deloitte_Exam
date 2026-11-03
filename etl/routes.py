"""
Build the route stats table from BTS T-100 Segment (All Carriers).

Input:  one row per route, per month, per aircraft type (US + foreign airlines).
Output: data/processed/route_stats.csv
One row per airport: passenger/cargo flights and long-haul flights.

Run from the project root:
    python etl/routes.py
"""

import os
import re
import zipfile

import pandas as pd
import requests

YEAR = 2025
# The BTS download page for "T-100 Segment (All Carriers)".
PAGE_URL = "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FMG&QO_fu146_anzr=Nv4%20Pn44vr45"
RAW_PATH = f"data/raw/t100_segment_{YEAR}.zip"
OUTPUT_PATH = "data/processed/route_stats.csv"

FIELDS = ["ORIGIN", "DEST", "DISTANCE", "CLASS", "DEPARTURES_PERFORMED"]

# A flight is "long haul" if it is at least this many miles.
LONG_HAUL_MILES = 3000
# A second threshold, to show how much the definition changes the answer.
ALT_LONG_HAUL_MILES = 2500

# Service classes in T-100:
#   F = scheduled passenger, L = non-scheduled passenger
#   G = scheduled cargo,     P = non-scheduled cargo
PASSENGER_CLASSES = ["F", "L"]
CARGO_CLASSES = ["G", "P"]


def download():
    """
    The BTS page is a form (no simple file link), so we fill it in from code:
    1. Open the page and copy its hidden security fields.
    2. Send the form back with the year and the fields we want.
    """
    if os.path.exists(RAW_PATH):
        return

    print(f"Downloading T-100 Segment {YEAR} (about 1 minute)...")
    session = requests.Session()

    page = session.get(PAGE_URL, timeout=60).text
    hidden_fields = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', page))

    form = {
        **hidden_fields,
        "cboGeography": "All",
        "cboYear": str(YEAR),
        "cboPeriod": "All",  # all 12 months
        "chkDownloadZip": "on",
        "btnDownload": "Download",
    }
    for field in FIELDS:
        form[field] = "on"  # tick the checkbox of each field we want

    response = session.post(PAGE_URL, data=form, timeout=600)
    response.raise_for_status()

    with open(RAW_PATH + ".part", "wb") as f:
        f.write(response.content)
    os.rename(RAW_PATH + ".part", RAW_PATH)


def read_segments():
    """Read the routes table from inside the zip file."""
    with zipfile.ZipFile(RAW_PATH) as z:
        csv_name = [name for name in z.namelist() if name.startswith("T_T100")][0]
        return pd.read_csv(z.open(csv_name), usecols=FIELDS)


def count_flights(segments, name):
    """Total flights flown per departure airport."""
    return segments.groupby("ORIGIN")["DEPARTURES_PERFORMED"].sum().rename(name)


def main():
    os.makedirs("data/raw", exist_ok=True)
    download()
    segments = read_segments()

    passenger = segments[segments["CLASS"].isin(PASSENGER_CLASSES)]
    cargo = segments[segments["CLASS"].isin(CARGO_CLASSES)]

    result = pd.concat([
        count_flights(passenger, "passenger_flights"),
        count_flights(passenger[passenger["DISTANCE"] >= LONG_HAUL_MILES], "passenger_long_haul"),
        count_flights(passenger[passenger["DISTANCE"] >= ALT_LONG_HAUL_MILES], "passenger_long_haul_alt"),
        count_flights(cargo, "cargo_flights"),
        count_flights(cargo[cargo["DISTANCE"] >= LONG_HAUL_MILES], "cargo_long_haul"),
        count_flights(cargo[cargo["DISTANCE"] >= ALT_LONG_HAUL_MILES], "cargo_long_haul_alt"),
    ], axis=1).fillna(0).astype(int)

    result.index.name = "code"
    result.insert(0, "year", YEAR)

    result.to_csv(OUTPUT_PATH)
    print(f"Saved {len(result)} airports to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
