"""
Live data from the US Department of Transportation open-data API.

Two questions we ask the API:
1. Traffic per airport per year (passengers, seats, departures).
2. Fare premium per airport (how much more expensive than usual).

The API speaks "SoQL" - a SQL-like language sent in the URL
($select, $where, $group), so the summing happens on their side
and we get back a small table.
"""

import pandas as pd
import requests

from backend.config import CODE_ALIASES, DATA_YEAR

# T-100 summary by origin airport (monthly, from 2014).
TRAFFIC_URL = "https://data.bts.gov/resource/r495-tyji.json"
# Consumer Airfare Report, Table 7: fare premium per airport (quarterly).
FARES_URL = "https://data.transportation.gov/resource/d6nc-s8v6.json"

FIRST_YEAR = 2014  # first year in the traffic dataset


def query(url, params):
    """Send one query to the API and return the result as a table."""
    params = {**params, "$limit": 50000}  # the API returns 1,000 rows unless told otherwise
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()  # stop with an error if the API failed
    return pd.DataFrame(response.json())


def get_yearly_traffic():
    """
    Passengers, seats and departures per airport per year,
    for every year from 2014 to DATA_YEAR.
    """
    data = query(TRAFFIC_URL, {
        "$select": (
            "origin_airport_code AS code, year, "
            "sum(total_passengers) AS passengers, "
            "sum(total_seats) AS seats, "
            "sum(total_departures) AS departures"
        ),
        "$where": f"year BETWEEN '{FIRST_YEAR}' AND '{DATA_YEAR}'",
        "$group": "origin_airport_code, year",
    })

    # The API returns everything as text - turn numbers into numbers.
    for column in ["year", "passengers", "seats", "departures"]:
        data[column] = pd.to_numeric(data[column]).astype(int)
    return data


def get_fare_premiums():
    """
    Average fare premium per airport in DATA_YEAR, in percent.
    +10 means fares are 10% higher than comparable markets.
    """
    data = query(FARES_URL, {
        "$select": "apt AS code, avg(totalperprem) AS fare_premium",
        "$where": f"year = {DATA_YEAR}",
        "$group": "apt",
    })

    # The API gives a fraction (0.10); we use percent (10.0).
    data["fare_premium_pct"] = (pd.to_numeric(data["fare_premium"]) * 100).round(1)
    data["code"] = data["code"].replace(CODE_ALIASES)  # the fares table still uses old codes
    return data[["code", "fare_premium_pct"]]
