"""
The connection to PostgreSQL.

Every part of the backend that needs the database imports `engine` from here.
"""

from sqlalchemy import create_engine

from backend.config import DATABASE_URL

# The engine manages connections to the database for us.
engine = create_engine(DATABASE_URL)
