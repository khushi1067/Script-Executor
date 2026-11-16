"""Run from the project root with: python -m database.test_connection"""

import psycopg

from database.connection import get_connection


def main():
    try:
        # Context managers close the cursor and connection when finished.
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS connected")
                result = cursor.fetchone()

        if result == (1,):
            print("Success: connected to PostgreSQL and SELECT 1 returned 1.")
            return 0

        print("Connection test failed: SELECT 1 returned an unexpected result.")
        return 1
    except (ValueError, ConnectionError) as error:
        # These messages are defined in connection.py and contain no secrets.
        print(error)
        return 1
    except psycopg.Error:
        # Do not print the original database error, which may contain details.
        print("Connection test failed: the database query could not be completed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
