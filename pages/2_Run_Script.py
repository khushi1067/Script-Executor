import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from scripts.dataset import MAX_DATASET_MB, REQUIRED_COLUMNS
from ui_helpers import open_run_details, valid_script_list
from ui_theme import api_connected, badge, format_duration, metric_cards, page_header, panel, result_panel, result_tone, script_card, script_label, section

# Read local configuration without depending on the working directory.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

page_header("Run Script", "Choose an approved processing task. Execute with confidence, with every result and log tracked.")

try:
    response = requests.get(f"{API_BASE_URL}/scripts", timeout=(5, 15))
    response.raise_for_status()
    scripts = response.json()
    if not valid_script_list(scripts):
        raise ValueError("Unexpected script list")
except requests.exceptions.Timeout:
    st.error("Loading scripts took too long. Please try refreshing the page.")
    st.stop()
except requests.exceptions.ConnectionError:
    st.error("Could not reach the API. Make sure the FastAPI server is running.")
    st.stop()
except (requests.exceptions.RequestException, ValueError):
    # Do not display raw response bodies or exception messages.
    st.error("Could not load scripts. Check that the API and database are available.")
    st.stop()

if not scripts:
    st.info("No active approved scripts are available. Register or activate scripts first.")
    st.stop()

scripts_by_name = {script["name"]: script for script in scripts}
api_connected()
section("Script library", "Only active scripts approved by the backend are available to execute.")
for column, script in zip(st.columns(min(len(scripts), 3), gap="small"), scripts):
    tone = {"validate_dataset": "green", "detect_duplicates": "purple", "generate_summary": "blue"}.get(script["name"], "purple")
    with column, panel(f"library_{script['name']}", tone):
        script_card(script["name"], script.get("description"))

with panel("script_setup", "purple"):
    section("Configure execution", "Choose an approved script and its input dataset.")
    script_names = list(scripts_by_name)
    preferred_script = st.session_state.pop("dashboard_selected_script", None)
    if preferred_script in scripts_by_name:
        st.session_state["run_script_selection"] = preferred_script
    selected_name = st.selectbox("Script", options=script_names, key="run_script_selection")
    description = scripts_by_name[selected_name].get("description")
    if description:
        st.caption(description)
    if selected_name == "detect_duplicates":
        st.caption("Matching rows and their field values are saved in Run Details for later review.")
    elif selected_name == "generate_summary":
        st.caption("See record counts, explore cities, and summarize ages. The city view saves CSV row numbers and available IDs, names, and ages in Run Details.")

    dataset_source = st.radio("Dataset source", ["Bundled sample", "Upload CSV"], horizontal=True)
    uploaded_dataset = None
    if dataset_source == "Upload CSV":
        required_columns = REQUIRED_COLUMNS.get(selected_name)
        if required_columns:
            st.caption("Required CSV columns · " + ", ".join(required_columns))
        uploaded_dataset = st.file_uploader(
            "Dataset CSV",
            type=["csv"],
            max_upload_size=MAX_DATASET_MB,
            help="Upload a UTF-8 CSV with a header row.",
            key="execution_dataset",
        )
    else:
        st.caption("Using the bundled sample_data/records.csv.")

    with st.container(key="run_action"):
        run_clicked = st.button(
            "Run Script", type="primary", icon=":material/play_arrow:", width="stretch",
            disabled=dataset_source == "Upload CSV" and uploaded_dataset is None,
        )

if run_clicked:
    try:
        with st.spinner("Running script…"):
            # Execution happens only through FastAPI. Never retry a POST automatically.
            if uploaded_dataset is None:
                response = requests.post(
                    f"{API_BASE_URL}/scripts/run",
                    json={"script_name": selected_name},
                    timeout=(5, 120),
                )
            else:
                response = requests.post(
                    f"{API_BASE_URL}/scripts/run-upload",
                    data={"script_name": selected_name},
                    files={"dataset": (uploaded_dataset.name, uploaded_dataset.getvalue(), "text/csv")},
                    timeout=(5, 120),
                )
            response.raise_for_status()
            outcome = response.json()
            if (
                not isinstance(outcome, dict)
                or outcome.get("status") not in ("success", "failed")
                or not isinstance(outcome.get("run_id"), int)
                or not isinstance(outcome.get("duration_ms"), (int, float))
                or outcome["duration_ms"] < 0
                or (outcome["status"] == "success" and "result" not in outcome)
            ):
                raise ValueError("Unexpected execution response")
    except requests.exceptions.Timeout:
        st.error("The API took too long to respond. The script may still run; check execution history before retrying.")
    except requests.exceptions.ConnectionError:
        st.error("Could not communicate with the API. Check the server and execution history before retrying; the script may have run.")
    except requests.exceptions.HTTPError:
        if response.status_code == 400:
            st.error("This script is no longer available to run. Refresh the page to reload active scripts.")
        elif uploaded_dataset is not None and response.status_code == 413:
            st.error(f"CSV files must be {MAX_DATASET_MB} MB or smaller.")
        elif uploaded_dataset is not None and response.status_code == 422:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            st.error(detail if isinstance(detail, str) else "Check the file encoding, CSV format, and required columns.")
        else:
            st.error("The API could not confirm the run was saved. Check the server and execution history before retrying.")
    except (requests.exceptions.RequestException, ValueError):
        st.error("Could not read the execution result. Check execution history before retrying.")
    else:
        if outcome["status"] == "success" and selected_name != "detect_duplicates":
            st.success("Script completed successfully.")
        elif outcome["status"] == "failed":
            st.error("The script failed. Check its input data or ask the project maintainer for help.")

        st.session_state["latest_script_outcome"] = outcome

# Keep the latest result visible during normal widget reruns, without rerunning it.
outcome = st.session_state.get("latest_script_outcome")
if outcome:
    result = outcome.get("result")
    is_duplicate_report = isinstance(result, dict) and "duplicates" in result
    is_overview = isinstance(result, dict) and "city_groups" in result
    with panel("run_result", result_tone(outcome["status"], result)):
        if is_duplicate_report:
            section("Duplicate Check Results")
        elif not is_overview:
            section("Execution result", script_label(outcome.get("script_name", "Latest execution")))
            st.markdown(badge(outcome["status"]), unsafe_allow_html=True)
            metric_cards([
                ("Run ID", outcome["run_id"], "runid"),
                ("Duration", format_duration(outcome["duration_ms"]), "runtime"),
            ])
            st.caption(f"Run ID: {outcome['run_id']} · Status: {outcome['status']}")
        if outcome["status"] == "success":
            result_panel(result)
        else:
            st.error("This execution failed. Review the recorded run details for more information.")
        if is_duplicate_report or is_overview:
            st.caption(f"Run #{outcome['run_id']} · {format_duration(outcome['duration_ms'])}")
        if st.button("View this run", icon=":material/arrow_forward:"):
            open_run_details(outcome["run_id"])
