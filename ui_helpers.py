"""Small shared display and API helpers for the monitoring pages."""

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from ui_theme import badge, format_duration, format_timestamp, script_label, table_cell

API_FAILURE = object()


def fetch_api(path, *, optional=False, allow_failure=False):
    """Fetch JSON, with silent optional probes and recoverable panel errors."""
    load_dotenv(Path(__file__).resolve().parent / ".env")
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        response = requests.get(f"{base_url}{path}", timeout=(2, 4) if optional else (5, 15))
        if response.status_code == 404 and path.startswith("/runs/") and not optional:
            st.info("That run does not exist. Check the run ID in Execution History.")
            st.stop()
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        message = "The API took too long to respond. Please refresh and try again."
    except requests.exceptions.ConnectionError:
        message = "Could not reach the API. Make sure the FastAPI server is running."
    except (requests.exceptions.RequestException, ValueError):
        message = "Could not load data. Check that the API and database are available."
    if not optional:
        st.error(message)
    if not (optional or allow_failure):
        st.stop()
    return API_FAILURE


def backend_healthy():
    health = fetch_api("/health", optional=True)
    return isinstance(health, dict) and health.get("status") == "ok"


def valid_script_list(scripts):
    if not isinstance(scripts, list) or not all(
        isinstance(script, dict)
        and isinstance(script.get("name"), str)
        and script["name"]
        and (script.get("description") is None or isinstance(script["description"], str))
        for script in scripts
    ):
        return False
    return len({script["name"] for script in scripts}) == len(scripts)


def open_run_details(run_id):
    st.session_state["selected_run_id"] = run_id
    st.switch_page("pages/4_Run_Details.py")


def open_run_script(script_name=None):
    if script_name is not None:
        st.session_state["dashboard_selected_script"] = script_name
    st.switch_page("pages/2_Run_Script.py")


def run_table(runs, *, row_actions=False):
    """Render the dashboard's actionable rows or the history data grid."""
    if row_actions:
        labels = ("Run ID", "Script Name", "Status", "Start Time (UTC)", "Duration", "Action")
        widths = (0.8, 1.4, 0.9, 1.55, 0.75, 1.1)
        with st.container(key="execution_table_header"):
            for column, label in zip(st.columns(widths, gap="small"), labels):
                column.markdown(f"**{label}**")
        for run in runs:
            run_id = run["run_id"]
            with st.container(key=f"execution_row_{run_id}"):
                columns = st.columns(widths, gap="small", vertical_alignment="center")
                cells = (
                    table_cell(labels[0], f"#{run_id}", style="se-run-id"),
                    table_cell(labels[1], script_label(run["script_name"])),
                    table_cell(labels[2], markup=badge(run["status"], label=run["status"].title())),
                    table_cell(labels[3], format_timestamp(run.get("started_at"), compact=True)),
                    table_cell(labels[4], format_duration(run.get("duration_ms"))),
                )
                for column, cell in zip(columns, cells):
                    column.markdown(cell, unsafe_allow_html=True)
                if columns[-1].button("View Details", key=f"details_{run_id}"):
                    open_run_details(run_id)
        return
    # Status words keep the table understandable without relying on color alone.
    rows = [
        {"Run ID": run["run_id"], "Script name": run["script_name"],
         "Status": run["status"], "Start time": run["started_at"],
         "Duration (ms)": run["duration_ms"]}
        for run in runs
    ]
    # Streamlit includes pandas; use its Styler only for native table cell colors.
    import pandas as pd

    table = pd.DataFrame(rows)
    table["Start time"] = table["Start time"].map(format_timestamp)
    colors = {"success": "#146C38", "failed": "#B92C45", "running": "#1C55BE"}
    backgrounds = {"success": "#E9F8EF", "failed": "#FFEEF1", "running": "#EDF3FF"}
    styled = table.style.map(
        lambda status: f"color: {colors.get(status, '#475569')}; background-color: {backgrounds.get(status, '#F0F3F8')}; font-weight: 600",
        subset=["Status"],
    )
    st.dataframe(styled, hide_index=True, column_config={
        "Run ID": st.column_config.NumberColumn(format="%d"),
        "Duration (ms)": st.column_config.NumberColumn(format="%d ms"),
    })


def run_details_selector(runs):
    """Session state carries the ID across standard Streamlit page navigation."""
    selected_id = st.selectbox("Run ID to inspect", [run["run_id"] for run in runs])
    if st.button("Open Run Details", icon=":material/arrow_forward:"):
        open_run_details(selected_id)
