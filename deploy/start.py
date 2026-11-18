"""Start and supervise the authenticated Render container."""

import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event

from database.connection import get_connection
from services.executor import register_scripts

ROOT = Path(__file__).resolve().parent.parent


def initialize_database():
    with get_connection() as connection:
        connection.execute((ROOT / "database" / "schema.sql").read_text())
    register_scripts()


def main():
    password = os.environ.pop("APP_PASSWORD", "")
    if not 20 <= len(password.encode("utf-8")) <= 72:
        sys.exit("Set APP_PASSWORD to a strong password between 20 and 72 bytes.")
    if not os.environ.get("DATABASE_URL", "").strip():
        sys.exit("Set DATABASE_URL to the Neon connection string.")

    try:
        password_hash = subprocess.run(
            ["caddy", "hash-password", "--plaintext", password],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("Could not configure the deployment password.")

    try:
        initialize_database()
    except Exception:
        sys.exit("Could not initialize Neon. Check DATABASE_URL and schema permissions.")

    stopping = Event()

    def stop(*_):
        stopping.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    private_env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
    processes = []
    try:
        processes.append(subprocess.Popen([
            sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000",
        ]))
        processes.append(subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
            "--server.address=127.0.0.1", "--server.port=8501", "--browser.gatherUsageStats=false",
        ], env={**private_env, "API_BASE_URL": "http://127.0.0.1:8000"}))
        processes.append(subprocess.Popen(
            ["caddy", "run", "--config", str(ROOT / "deploy" / "Caddyfile"), "--adapter", "caddyfile"],
            env={**private_env, "APP_PASSWORD_HASH": password_hash},
        ))
        while not stopping.wait(0.5):
            if any(process.poll() is not None for process in processes):
                print("A service exited. Shutting down the deployment.", file=sys.stderr)
                return 1
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    sys.exit(main())
