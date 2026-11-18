import json

import streamlit as st

from ui_helpers import fetch_api
from ui_theme import api_connected, badge, format_timestamp, log_timeline, metric_cards, page_header, panel, result_panel, result_tone, section

page_header("Run Details", "Inspect the outcome, timing, and complete execution trail of a single run.", tone="blue")

# Links may use ?run_id=42; history/dashboard navigation uses session state.
initial_id = st.query_params.get("run_id", st.session_state.get("selected_run_id", ""))
with panel("run_lookup", "purple"):
    run_id_text = st.text_input("Run ID", value=str(initial_id))
    st.button("Load / refresh run", icon=":material/refresh:")

if not run_id_text.strip():
    st.info("Select a run from Execution History or enter a run ID above.")
    st.stop()
try:
    run_id = int(run_id_text)
    if run_id < 1 or run_id > 2147483647:
        raise ValueError("Invalid run ID")
except ValueError:
    st.warning("Enter a positive whole-number run ID.")
    st.stop()

with st.spinner("Loading run details…"):
    run = fetch_api(f"/runs/{run_id}")
try:
    for key in ("run_id", "script_name", "status", "started_at", "finished_at", "duration_ms", "result_summary", "logs"):
        run[key]
    if not isinstance(run["logs"], list):
        raise ValueError("Invalid logs")
    log_rows = [
        {"Timestamp": log["created_at"], "Level": log["level"], "Message": log["message"]}
        for log in run["logs"]
    ]
except (KeyError, TypeError, ValueError):
    st.error("The API returned unreadable run details. Please try refreshing.")
    st.stop()

api_connected()
with panel("details_overview", result_tone(run["status"])):
    section(run["script_name"].replace("_", " ").title(), f"RUN #{run['run_id']} · saved execution record")
    st.markdown(badge(run["status"]), unsafe_allow_html=True)
    duration = run["duration_ms"]
    metric_cards([
        ("Run ID", run["run_id"], "runid"),
        ("Duration", f"{duration} ms" if duration is not None else "—", "duration"),
    ])
    started_column, finished_column = st.columns(2)
    started_column.caption("STARTED AT")
    started_column.write(format_timestamp(run["started_at"]))
    finished_column.caption("FINISHED AT")
    finished_column.write(format_timestamp(run["finished_at"]))

result_summary = run["result_summary"]
structured = False
result = result_summary
if result_summary is not None:
    try:
        result = json.loads(result_summary)
    except (ValueError, TypeError):
        pass  # Failed runs can contain a plain-text summary.
    else:
        structured = True
with panel("details_result", result_tone(run["status"], result) if result_summary is not None else "blue"):
    section("Result summary")
    if result_summary is None:
        st.info("No result summary has been recorded yet.")
    elif structured:
        result_panel(result)
    else:
        st.text(result)

with panel("log_panel", "blue"):
    section("Execution timeline", "Chronological logs · timestamp and log ID order")
    if log_rows:
        log_timeline(run["logs"])
        with st.expander("Log table"):
            st.dataframe(log_rows, hide_index=True)
    else:
        st.info("No execution logs have been recorded for this run.")
