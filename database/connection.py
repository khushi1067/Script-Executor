import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def get_connection():
    """Open a PostgreSQL connection using the project's local .env file."""
    # Use the project root so this works from any working directory.
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
    database_url = os.getenv("DATABASE_URL")

    if not database_url or not database_url.strip():
        raise ValueError("DATABASE_URL is missing. Set it in your local .env file.")

    try:
        return psycopg.connect(database_url, connect_timeout=10)
    except psycopg.Error:
        # Keep connection details and credentials out of error messages.
        raise ConnectionError(
            "Could not connect to PostgreSQL. Check your DATABASE_URL and network connection."
        ) from None
