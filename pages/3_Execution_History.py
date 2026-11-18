import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from ui_helpers import run_details_selector, run_table
from ui_theme import api_connected, metric_cards, page_header, panel, section

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

page_header("Execution History", "A clear record of every execution. Filter results and trace a run from start to finish.", tone="blue")
st.button("Refresh history", icon=":material/refresh:")

try:
    with st.spinner("Loading execution history…"):
        response = requests.get(f"{API_BASE_URL}/runs", timeout=(5, 15))
        response.raise_for_status()
        runs = response.json()
        if not isinstance(runs, list) or not all(
            isinstance(run, dict)
            and isinstance(run.get("run_id"), int)
            and isinstance(run.get("script_name"), str)
            and run.get("status") in ("success", "failed", "running")
            and isinstance(run.get("started_at"), str)
            and (run.get("duration_ms") is None or isinstance(run["duration_ms"], int))
            for run in runs
        ):
            raise ValueError("Unexpected history response")
except requests.exceptions.Timeout:
    st.error("Loading history took too long. Please try refreshing.")
    st.stop()
except requests.exceptions.ConnectionError:
    st.error("Could not reach the API. Make sure the FastAPI server is running.")
    st.stop()
except (requests.exceptions.RequestException, ValueError):
    # Do not show raw response bodies, connection details, or tracebacks.
    st.error("Could not load execution history. Check that the API and database are available.")
    st.stop()

# Counts describe all fetched records, regardless of the selected display filter.
api_connected()
section("Recent execution records", "Showing up to 100 recent runs. Counts apply to these fetched records.")
metric_cards([
    ("Total runs", len(runs), "total"),
    ("Successful runs", sum(run["status"] == "success" for run in runs), "success"),
    ("Failed runs", sum(run["status"] == "failed" for run in runs), "failed"),
], tones=("blue", "green", "red"))

with panel("history_results", "blue"):
    status_filter = st.selectbox("Status", ["All", "Success", "Failed", "Running"])
    if not runs:
        st.info("No executions yet. Run a script to create your first history record.")
        st.stop()

    filtered_runs = [
        run for run in runs
        if status_filter == "All" or run["status"] == status_filter.lower()
    ]
    if not filtered_runs:
        st.info("No fetched runs match the selected status.")
    else:
        # Keep the database ID visible so each row can be checked against PostgreSQL.
        run_table(filtered_runs)
        st.caption("Times shown in UTC. A blank duration means it has not been recorded yet.")
        run_details_selector(filtered_runs)
