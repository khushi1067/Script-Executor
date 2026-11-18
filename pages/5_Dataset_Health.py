from hashlib import sha256
from itertools import islice
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.dataset import MAX_AGE, MAX_DATASET_MB, MIN_AGE, REQUIRED_COLUMNS, SAMPLE_DATASET
from scripts.validate_dataset import record_findings
from services.dataset_review import build_cleaned_csv, check_dataset, correct_row, field_label, matching_groups, rows_to_remove
from ui_theme import metric_cards, page_header, panel, section

WORKSPACE_KEY = "dataset_review_workspace"
COMPARISON_PAGE_SIZE = 20


def record_table(columns, rows, numbers):
    return pd.DataFrame(rows, columns=columns, index=pd.Index(numbers, name="CSV row"))


def show_field_findings(workspace, category, label):
    report = workspace["report"]
    findings = report[category]
    if not findings:
        st.success(f"No {label.lower()} found.")
        return
    st.caption("Select a finding to view the row and edit its flagged values.")
    selection = st.dataframe(
        findings, hide_index=True, width="stretch", on_select="rerun",
        selection_mode="single-row", key=f"health_table_{label}",
    ).selection.rows
    index = selection[0] if selection and selection[0] < len(findings) else 0
    row = findings[index]["CSV row"]
    st.caption(f"Current values from row {row}")
    columns, values = report["columns"], report["rows"][row - 2]
    st.dataframe(record_table(columns, [values], [row]), hide_index=False, width="stretch")
    record = dict(zip(columns, values))
    fields = [field for field, kind, _ in record_findings(record) if kind == category]
    with st.form(f"health_edit_{category}_{row}"):
        section(f"Edit row {row}")
        if row in rows_to_remove(report, workspace["decisions"]):
            st.warning("Your duplicate decision marks this row for removal.")
        inputs = {}
        for field in fields:
            placeholder = {
                "age": f"Whole number from {MIN_AGE} to {MAX_AGE}",
                "email": "name@example.com",
            }.get(field)
            inputs[field] = st.text_input(
                field_label(field), value=record[field], placeholder=placeholder,
                key=f"health_edit_{category}_{row}_{field}",
            )
        if st.form_submit_button("Save corrections", type="primary"):
            try:
                updated, decisions = correct_row(report, workspace["decisions"], row, inputs)
            except ValueError as error:
                st.error(str(error))
            else:
                notice = f"Saved corrections to row {row}."
                if len(decisions) < len(workspace["decisions"]):
                    notice += " Review any duplicate groups affected by the Record ID change."
                workspace.update(report=updated, decisions=decisions, correction_notice=notice)
                st.rerun()


def show_comparison(report, group):
    numbers, values = group["row_numbers"], group["record_values"]
    different = [
        column
        for column, entries in zip(report["columns"], zip(*values))
        if any(value != entries[0] for value in entries[1:])
    ]
    if different:
        st.text(f"Fields that differ: {', '.join(different)}")
    else:
        st.caption("Every field matches in this group.")

    start = 0
    if len(numbers) > COMPARISON_PAGE_SIZE:
        page = st.number_input(
            "Comparison page", min_value=1, max_value=(len(numbers) - 1) // COMPARISON_PAGE_SIZE + 1,
            key=f"health_compare_page_{numbers[0]}",
        )
        start = (page - 1) * COMPARISON_PAGE_SIZE
    end = start + COMPARISON_PAGE_SIZE
    table = record_table(report["columns"], values[start:end], numbers[start:end])
    if different and table.size <= 20_000:
        table = table.style.set_properties(subset=different, **{"background-color": "#fff4dd", "color": "#5c3d09"})
    st.dataframe(table, hide_index=False, width="stretch")


def review_duplicates(report, decisions):
    groups = report["duplicates"]
    if not groups:
        st.success("No repeated Record IDs found.")
        return

    st.caption(
        "Rows are grouped by Record ID. Compare the values and choose one row to keep, "
        "or leave the group for later. Groups left for later stay in the export."
    )
    exact = matching_groups(report)
    undecided_exact = {record_id: row for record_id, row in exact.items() if record_id not in decisions}
    if undecided_exact and st.button(
        f"Keep first row in identical groups ({len(undecided_exact):,})",
        help="Applies to undecided groups where every field matches.",
    ):
        decisions.update(undecided_exact)

    def group_label(record_id):
        status = "Reviewed" if record_id in decisions else "To review"
        return f"{record_id} · {len(groups[record_id]['row_numbers'])} rows · {status}"

    st.caption(f"{len(groups) - len(decisions):,} of {len(groups):,} groups left to review.")
    selected = st.selectbox("Record ID to review", list(groups), format_func=group_label, key="health_review_group")
    group = groups[selected]
    show_comparison(report, group)

    numbers = group["row_numbers"]
    saved_row = decisions.get(selected, 0)
    options = [0, *numbers]
    with st.form("health_review_decision"):
        choice = st.selectbox(
            "Which row should stay in the cleaned CSV?",
            options, index=options.index(saved_row),
            format_func=lambda row: f"Keep row {row}" if row else "Review later · keep all rows",
            key=f"health_keep_{numbers[0]}_{saved_row}",
        )
        if st.form_submit_button("Save decision", type="primary"):
            if choice:
                decisions[selected] = choice
            else:
                decisions.pop(selected, None)
            st.rerun()


def show_export(report, decisions, filename):
    section("Preview and download", "The export includes your saved corrections and duplicate decisions.")
    removed = rows_to_remove(report, decisions)
    remaining = len(report["rows"]) - len(removed)
    outstanding = len(report["duplicates"]) - len(decisions)
    groups_label = "group" if outstanding == 1 else "groups"
    st.caption(
        f"{remaining:,} rows in the export · {len(removed):,} removed · "
        f"{outstanding:,} duplicate {groups_label} still to review"
    )
    if report["missing"] or report["invalid"]:
        st.caption("Any remaining missing or invalid values stay in the export.")

    kept = ((number, row) for number, row in enumerate(report["rows"], start=2) if number not in removed)
    preview = list(islice(kept, 20))
    if preview:
        rows, values = zip(*preview)
        st.caption(f"Showing the first {len(preview)} rows. Row numbers refer to the source CSV.")
        st.dataframe(record_table(report["columns"], values, rows), hide_index=False, width="stretch")
    else:
        st.info("The CSV contains a header and zero data rows.")

    if decisions:
        with st.expander("Review decisions"):
            st.dataframe([
                {
                    "Record ID": record_id,
                    "Kept row": row,
                    "Removed rows": ", ".join(str(number) for number in report["duplicates"][record_id]["row_numbers"] if number != row),
                }
                for record_id, row in decisions.items()
            ], hide_index=True, width="stretch")

    st.download_button(
        "Download cleaned CSV", data=build_cleaned_csv(report, removed),
        file_name=f"{Path(filename).stem}_cleaned.csv", mime="text/csv", on_click="ignore",
        icon=":material/download:",
    )


def render_page():
    page_header("Dataset Health", "Check a CSV for common issues, review repeated records, and download a cleaned copy.", tone="green")
    st.caption("Your CSV, corrections, and review decisions stay in the current session.")
    with panel("health_source", "green"):
        source = st.radio("Dataset source", ["Upload CSV", "Bundled sample"], horizontal=True)
        st.caption("Required columns · " + ", ".join(REQUIRED_COLUMNS["validate_dataset"]))
        if source == "Bundled sample":
            filename, data = "records.csv", SAMPLE_DATASET.read_bytes()
        else:
            uploaded = st.file_uploader("Dataset CSV", type=["csv"], max_upload_size=MAX_DATASET_MB, key="health_upload")
            filename, data = (uploaded.name, uploaded.getvalue()) if uploaded else (None, None)

        identity = (source, filename, sha256(data).digest()) if data is not None else None
        workspace = st.session_state.get(WORKSPACE_KEY)
        if workspace and workspace["identity"] != identity:
            st.session_state.pop(WORKSPACE_KEY)
            workspace = None
        if not workspace and st.button("Check dataset", type="primary", disabled=data is None):
            try:
                with st.spinner("Checking your dataset…"):
                    report = check_dataset(data)
            except ValueError as error:
                st.error(str(error))
            else:
                workspace = {"identity": identity, "report": report, "decisions": {}}
                st.session_state[WORKSPACE_KEY] = workspace

    if not workspace:
        return

    report = workspace["report"]
    decisions = workspace["decisions"]
    section("Health report", "Row 1 contains the headers. Empty lines are skipped when counting rows.")
    if notice := workspace.pop("correction_notice", None):
        st.success(notice)
    metric_cards([
        ("Rows checked", len(report["rows"]), "health_rows"),
        ("Repeated IDs", len(report["duplicates"]), "health_duplicates"),
        ("Missing values", len(report["missing"]), "health_missing"),
        ("Invalid values", len(report["invalid"]), "health_invalid"),
    ], tones=("blue", "purple", "amber", "red"))
    with panel("health_review", "amber"):
        view = st.radio(
            "Choose findings to review", ["Duplicate records", "Missing values", "Invalid values"],
            horizontal=True, key="health_findings",
        )
        if view == "Duplicate records":
            review_duplicates(report, decisions)
        elif view == "Missing values":
            show_field_findings(workspace, "missing", view)
        else:
            show_field_findings(workspace, "invalid", view)

    with panel("health_export", "green"):
        show_export(report, decisions, filename)


render_page()
