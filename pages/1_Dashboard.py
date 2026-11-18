from datetime import date
from math import isfinite

import altair as alt
import pandas as pd
import streamlit as st

from ui_helpers import (
    API_FAILURE, backend_healthy, fetch_api, open_run_details, open_run_script, run_table, valid_script_list,
)
from ui_theme import (
    dashboard_list_item, dashboard_metric_cards, format_duration, script_label, section,
    sidebar_connectivity, system_health_panel,
)


def count_is_valid(value):
    return type(value) is int and value >= 0


def number_in_range(value, maximum=float("inf")):
    return type(value) in (int, float) and 0 <= value <= maximum and isfinite(value)


def validate_summary(data):
    if not isinstance(data, dict):
        raise ValueError("Invalid summary")
    for key in ("total_runs", "successful_runs", "failed_runs", "running_runs"):
        if not count_is_valid(data[key]):
            raise ValueError("Invalid count")
    average = data.get("average_duration_ms")
    if not number_in_range(data["success_rate"], 100) or (average is not None and not number_in_range(average)):
        raise ValueError("Invalid execution metric")
    recent, activity = data["recent_executions"], data["daily_run_counts"]
    if not isinstance(recent, list) or not isinstance(activity, list):
        raise ValueError("Invalid execution history")
    run_ids = set()
    for run in recent:
        run_id = run["run_id"]
        duration = run.get("duration_ms")
        if (
            not count_is_valid(run_id) or run_id == 0 or run_id in run_ids
            or not isinstance(run["script_name"], str) or not isinstance(run["status"], str)
            or (run.get("started_at") is not None and not isinstance(run["started_at"], str))
            or (duration is not None and not number_in_range(duration))
        ):
            raise ValueError("Invalid execution")
        run_ids.add(run_id)
    for day in activity:
        date.fromisoformat(day["date"])
        if not count_is_valid(day["run_count"]):
            raise ValueError("Invalid daily count")
    return data


def execution_activity(days):
    section("Execution Activity", "Total executions over the last seven calendar days · UTC")
    if not days:
        st.info("No daily activity data is available.")
        return

    rows = [
        {"day": date.fromisoformat(day["date"]).strftime("%b %d"), "runs": day["run_count"]}
        for day in sorted(days, key=lambda day: day["date"])[-7:]
    ]
    chart = alt.Chart(pd.DataFrame(rows)).mark_bar(
        color="#6225FC", cornerRadiusTopLeft=5, cornerRadiusTopRight=5, size=24,
    ).encode(
        x=alt.X("day:O", sort=None, axis=alt.Axis(title=None, labelAngle=0, labelPadding=9, ticks=False)),
        y=alt.Y("runs:Q", axis=alt.Axis(title=None, tickMinStep=1, format="d", gridColor="#E4E8F2", ticks=False)),
        tooltip=[alt.Tooltip("day:O", title="Date (UTC)"), alt.Tooltip("runs:Q", title="Executions", format=",d")],
    ).properties(height=202).configure_view(stroke=None).configure_axis(
        domain=False, labelColor="#576480", labelFontSize=12,
    )
    st.altair_chart(chart, width="stretch")


def dashboard_header():
    with st.container(key="dashboard_header"):
        title, search, refresh = st.columns([1.5, 1.1, 0.22], vertical_alignment="center")
        title.markdown('<h1 class="se-title">Dashboard</h1>', unsafe_allow_html=True)
        with search, st.form("dashboard_search", border=False):
            field, action = st.columns([2, 1], gap="small")
            value = field.text_input("Search execution by Run ID", placeholder="Search by Run ID", label_visibility="collapsed")
            if action.form_submit_button("Search", help="Open an execution by Run ID", width="stretch"):
                try:
                    run_id = int(value)
                    if not 1 <= run_id <= 2147483647:
                        raise ValueError("Invalid run ID")
                except ValueError:
                    st.warning("Enter a valid positive whole-number run ID.")
                else:
                    open_run_details(run_id)
        refresh.button(":material/refresh:", help="Refresh dashboard", key="refresh_dashboard")


def dashboard_actions(recent):
    with st.container(key="dashboard_actions"):
        dataset, script, latest = st.columns(3, gap="small")
        with dataset, st.container(border=True, key="dashboard_action_dataset"):
            dashboard_list_item("fact_check", "Check your data", "Find missing values and review duplicates.", tone="green")
            if st.button("Check a dataset", type="primary", width="stretch"):
                st.switch_page("pages/5_Dataset_Health.py")
        with script, st.container(border=True, key="dashboard_action_script"):
            dashboard_list_item("play_circle", "Run a workflow", "Choose a script and process a CSV.")
            if st.button("Run New Script", width="stretch"):
                open_run_script()
        with latest, st.container(border=True, key="dashboard_action_latest"):
            detail = script_label(recent[0]["script_name"]) if recent else "Run a workflow to see results here."
            dashboard_list_item("history", "Latest execution", detail, tone="blue")
            if recent:
                run_id = recent[0]["run_id"]
                if st.button(f"Open run #{run_id}", width="stretch"):
                    open_run_details(run_id)


def render_dashboard():
    st.set_page_config(page_title="Dashboard · Script Executor", layout="wide")
    dashboard_header()

    connected = backend_healthy()
    sidebar_connectivity(connected)
    scripts = fetch_api("/scripts", optional=True)
    if not valid_script_list(scripts):
        scripts = None

    with st.spinner("Loading dashboard…"):
        payload = fetch_api("/analytics/summary", allow_failure=True)
    try:
        summary = validate_summary(payload)
    except (KeyError, TypeError, ValueError, OverflowError):
        if payload is not API_FAILURE:
            st.error("The API returned an unreadable dashboard response. Please try refreshing.")
        summary = {}

    recent = summary.get("recent_executions", [])
    rate = summary.get("success_rate")
    rate_label = f"{rate:.2f}%" if rate is not None else "—"
    average = summary.get("average_duration_ms")
    script_count = len(scripts) if scripts is not None else None
    database_verified = bool(summary) or scripts is not None

    dashboard_actions(recent)

    with st.container(key="dashboard_metrics"):
        dashboard_metric_cards([
            ("Total Executions", f"{summary['total_runs']:,}" if summary else "—", "layers", "purple"),
            ("Success Rate", rate_label, "check_circle", "green"),
            ("Failed Runs", f"{summary['failed_runs']:,}" if summary else "—", "error", "red"),
            ("Average Execution Time", format_duration(average, precision=2), "schedule", "blue"),
        ])

    with st.container(key="dashboard_monitoring"):
        activity, health = st.columns([1.4, 1], gap="small")
        with activity, st.container(border=True, key="dashboard_activity"):
            execution_activity(summary.get("daily_run_counts", []))
        with health, st.container(border=True, key="dashboard_health"):
            system_health_panel(connected, database_verified, script_count, summary.get("running_runs"))

    with st.container(border=True, key="dashboard_recent"):
        heading, action = st.columns([3, 1], vertical_alignment="center")
        with heading:
            section("Recent Executions")
        if action.button("View All History →", width="stretch"):
            st.switch_page("pages/3_Execution_History.py")
        if recent:
            status = st.segmented_control(
                "Execution status", ["All", "Success", "Failed", "Running"], default="All",
                key="dashboard_status", label_visibility="collapsed",
            )
            matching = [run for run in recent if status in (None, "All") or run["status"].lower() == status.lower()]
            if matching:
                run_table(matching[:5], row_actions=True)
            else:
                st.info(f"No recent runs with status {status.lower()}.")
        else:
            st.info("No executions yet." if summary else "Recent executions are unavailable.")

    with st.container(key="dashboard_followups"):
        quick, failures = st.columns(2, gap="small")
        with quick, st.container(border=True, key="dashboard_quick"):
            section("Quick Execution")
            script_icons = {"validate_dataset": "fact_check", "detect_duplicates": "content_copy", "generate_summary": "summarize"}
            for script in scripts or []:
                name = script["name"]
                with st.container(key=f"dashboard_quick_{name}"):
                    item, action = st.columns([3, 1], vertical_alignment="center", gap="small")
                    with item:
                        dashboard_list_item(script_icons.get(name, "terminal"), script_label(name), script.get("description"))
                    if action.button("Configure", key=f"configure_{name}", width="stretch"):
                        open_run_script(name)
            if not scripts:
                st.info("Approved scripts are unavailable." if scripts is None else "No approved scripts are available.")
        with failures, st.container(border=True, key="dashboard_failures"):
            section("Recent Failures", "From the latest executions")
            failed = [run for run in recent if run["status"].lower() == "failed"][:3]
            for run in failed:
                run_id = run["run_id"]
                with st.container(key=f"dashboard_failure_{run_id}"):
                    item, action = st.columns([3, 1], vertical_alignment="center", gap="small")
                    with item:
                        dashboard_list_item("error", f"#{run_id} · {script_label(run['script_name'])}", tone="red")
                    if action.button("Investigate", key=f"investigate_{run_id}", width="stretch"):
                        open_run_details(run_id)
            if not failed:
                st.info("No failures in the recent execution window." if summary else "Recent failures are unavailable.")


render_dashboard()
