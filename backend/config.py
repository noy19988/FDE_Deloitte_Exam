"""
All backend settings in one place.

Values come from the .env file in the project root.
"""

import os

from dotenv import load_dotenv

# Read the .env file and put its values into environment variables.
load_dotenv()


# --- LLM (Gemini) ---

# The API key itself (GOOGLE_API_KEY) is read by ADK directly from the environment.
# "or" = use the default also when the variable is there but empty.
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"


# --- Data years ---

# The main year we analyze (the last full year of data).
DATA_YEAR = 2025

# The year before COVID - used to measure real growth.
BASELINE_YEAR = 2019


# --- Scoring ---

# Airports with fewer departing passengers per year are left out
# (tiny airports give misleading numbers, e.g. "+100% growth" from 10 to 20 passengers).
MIN_PASSENGERS = 100_000

# How much each component counts in the total score (adds up to 100).
WEIGHTS = {
    "capacity_pressure": 30,
    "demand_growth": 25,
    "congestion": 20,
    "market_scale": 15,
    "pricing_power": 10,
}

# "High" confidence needs all components and at least this many passengers.
HIGH_CONFIDENCE_PASSENGERS = 1_000_000


# --- Special questions ---

# Long haul = flights of at least this many miles (must match etl/routes.py).
LONG_HAUL_MILES = 3000
ALT_LONG_HAUL_MILES = 2500

# Long-haul share from fewer flights than this gets "Medium" confidence (a few routes change it a lot).
LONG_HAUL_MIN_FLIGHTS = 1000

# A "healthy" load factor. Above it, we say seats are missing.
TARGET_LOAD_FACTOR_PCT = 80


# --- Database ---

# Defaults = the local Docker database (docker-compose.yml uses the same ones).
# Inside Docker, docker-compose.yml sets the host to "db" and the port to 5432.
POSTGRES_USER = os.getenv("POSTGRES_USER") or "airport"
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD") or "airport"
POSTGRES_DB = os.getenv("POSTGRES_DB") or "airport"
POSTGRES_HOST = os.getenv("POSTGRES_HOST") or "localhost"
POSTGRES_PORT = os.getenv("POSTGRES_PORT") or "5433"  # the port Docker gives the database on your computer

# One string with everything needed to connect to the database.
# "postgresql+psycopg" = PostgreSQL, using the psycopg driver.
DATABASE_URL = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)
