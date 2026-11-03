"""
Load the processed aviation files into PostgreSQL.

Each CSV in data/processed becomes one table.
The tables are rebuilt from the files every time this runs,
so the database always matches the files.

Run from the project root:
    python -m backend.db.load_data
"""

import pandas as pd

from backend.db.database import engine

# table name -> file it comes from
TABLES = {
    "airports": "data/processed/airports.csv",
    "delay_stats": "data/processed/delay_stats.csv",
    "route_stats": "data/processed/route_stats.csv",
}


def load_aviation_data():
    for table, path in TABLES.items():
        data = pd.read_csv(path, dtype={"code": str})
        # if_exists="replace": drop the old table and create it again.
        data.to_sql(table, engine, if_exists="replace", index=False)
        print(f"Loaded {len(data)} rows into '{table}'")


if __name__ == "__main__":
    load_aviation_data()
