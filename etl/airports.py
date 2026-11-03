"""
Build the airports table from OurAirports.

Output: data/processed/airports.csv
One row per US airport: code, name, city, state, runways.

Run from the project root:
    python etl/airports.py
"""

import pandas as pd

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"
OUTPUT_PATH = "data/processed/airports.csv"

# Runways shorter than this are too short for commercial jets.
MIN_RUNWAY_LENGTH_FT = 5000


def load_us_airports():
    """US airports that have a 3-letter IATA code (like BOS, SFO)."""
    airports = pd.read_csv(AIRPORTS_URL, keep_default_na=False)

    # Only the 50 states. Territories (Puerto Rico, Guam...) have their own country code.
    airports = airports[airports["iso_country"] == "US"]
    airports = airports[airports["iata_code"] != ""]
    airports = airports[airports["type"].isin(["large_airport", "medium_airport", "small_airport"])]

    # "US-MA" -> "MA"
    airports["state"] = airports["iso_region"].str.replace("US-", "")

    return airports


def count_runways():
    """How many usable runways each airport has."""
    runways = pd.read_csv(RUNWAYS_URL, keep_default_na=False)

    runways["length_ft"] = pd.to_numeric(runways["length_ft"], errors="coerce")

    usable = runways[
        (runways["closed"] == 0)
        & (runways["length_ft"] >= MIN_RUNWAY_LENGTH_FT)
        & (~runways["surface"].str.upper().str.contains("WAT"))  # no water runways
    ]

    counts = usable.groupby("airport_ident").size()
    return counts.rename("runways").reset_index()


def main():
    airports = load_us_airports()
    runways = count_runways()

    # Add the runway count to each airport (matched by the airport's ident, like KBOS).
    result = airports.merge(runways, left_on="ident", right_on="airport_ident", how="left")
    result["runways"] = result["runways"].fillna(0).astype(int)

    result = result.rename(columns={"iata_code": "code", "municipality": "city"})
    result = result[["code", "name", "city", "state", "runways"]]
    result = result.sort_values("code")

    result.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved {len(result)} airports to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
