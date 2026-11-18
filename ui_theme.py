"""Shared visual components. API text is escaped before rendering HTML."""

from datetime import datetime, timezone
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


def apply_theme():
    css = (Path(__file__).resolve().parent / "styles" / "dashboard.css").read_text()
    st.markdown(f'<style id="se-workspace-theme">{css}</style>', unsafe_allow_html=True)


def workspace_header(home_page):
    with st.container(key="workspace_header"):
        st.page_link(home_page, label="Script Executor", icon=":material/terminal:")


def panel(key, tone="purple"):
    """Create a tinted workspace card using the shared dashboard palette."""
    return st.container(key=f"surface_{tone}_{key}", border=True)


def page_header(title, subtitle, *, tone="purple"):
    st.set_page_config(page_title=f"{title} · Script Executor", page_icon="⚡", layout="wide")
    with panel("page_intro", tone):
        st.markdown(
            f'<header><h1 class="se-title">{escape(title)}</h1>'
            f'<p class="se-subtitle">{escape(subtitle)}</p></header>',
            unsafe_allow_html=True,
        )


def section(title, note=""):
    subtitle = f'<div class="se-section-note">{escape(note)}</div>' if note else ""
    st.markdown(
        f'<h2 class="se-section-title">{escape(title)}</h2>{subtitle}', unsafe_allow_html=True,
    )


def badge(status, *, label=None):
    style = str(status).lower()
    if style not in {"success", "failed", "running", "info", "warning", "error"}:
        style = "neutral"
    return f'<span class="se-badge se-{style}">{escape(str(status) if label is None else label)}</span>'


def result_tone(status, result=None):
    if status == "failed":
        return "red"
    if isinstance(result, dict) and (result.get("duplicates") or result.get("issues")):
        return "amber"
    return "green" if status == "success" else "blue"


def sidebar_connectivity(connected):
    indicator = badge("success" if connected else "failed", label="Connected" if connected else "Unavailable")
    st.sidebar.markdown(
        f'<div class="se-sidebar-health"><strong>API status</strong>{indicator}</div>',
        unsafe_allow_html=True,
    )


def icon_tile(icon, tone="purple"):
    return f'<span class="se-icon se-icon-{tone} material-symbols-rounded" aria-hidden="true">{escape(icon)}</span>'


def dashboard_metric_cards(items):
    for column, (label, value, icon, tone) in zip(st.columns(4, gap="small"), items):
        with column, st.container(key=f"dashboard_kpi_{tone}", border=True):
            st.markdown(icon_tile(icon, tone), unsafe_allow_html=True)
            st.metric(label, value)


def system_health_panel(connected, database_verified, script_count, running):
    section("System Health")
    rows = (
        ("FastAPI Backend", badge("success" if connected else "failed", label="Connected" if connected else "Unavailable")),
        ("Neon PostgreSQL", badge("success", label="Connected") if database_verified else badge("neutral", label="Unknown")),
        ("Approved Scripts", f"{script_count} available" if script_count is not None else "Unavailable"),
        ("Currently Running", f"{running:,}" if running is not None else "—"),
    )
    items = "".join(f'<div class="se-health-row"><span>{label}</span><strong>{value}</strong></div>' for label, value in rows)
    st.markdown(f'<div class="se-health-list">{items}</div>', unsafe_allow_html=True)


def script_label(name):
    return name.replace("_", " ").title()


def dashboard_list_item(icon, title, description=None, *, tone="purple"):
    detail = f"<small>{escape(description)}</small>" if description else ""
    st.markdown(
        f'<div class="se-list-item">{icon_tile(icon, tone)}'
        f'<div><strong>{escape(title)}</strong>{detail}</div></div>',
        unsafe_allow_html=True,
    )


def table_cell(label, value="", *, style="", markup=None):
    return (
        f'<div class="se-table-cell" data-label="{escape(label)}">'
        f'<span class="{escape(style)}">{markup or escape(value)}</span></div>'
    )


def format_duration(milliseconds, *, precision=0):
    if milliseconds is None:
        return "—"
    if milliseconds >= 1000:
        return f"{milliseconds / 1000:.3f}".rstrip("0").rstrip(".") + "s"
    return f"{milliseconds:.{precision}f} ms"


def api_connected():
    # Display this only after a successful response; no extra health requests needed.
    st.caption(f"● API response received · {datetime.now(timezone.utc):%H:%M:%S} UTC")


def metric_cards(items, *, tones=None):
    """Items are (label, value, key); each card uses native, accessible metrics."""
    with st.container(key=f"metrics_{items[0][2]}"):
        colors = tones or ("blue",) * len(items)
        for column, (label, value, key), tone in zip(st.columns(len(items), gap="small"), items, colors, strict=True):
            with column, panel(f"kpi_{key}", tone):
                st.metric(label, value)


def format_timestamp(value, *, compact=False):
    if not value:
        return "Not recorded yet"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if compact:
            return parsed.astimezone(timezone.utc).strftime("%b %d, %Y · %H:%M")
        return parsed.astimezone(timezone.utc).strftime("%d %b %Y · %H:%M:%S UTC")
    except (ValueError, TypeError, AttributeError):
        return str(value)


def script_card(name, description):
    symbols = {"validate_dataset": "✓", "detect_duplicates": "≋", "generate_summary": "▥"}
    st.markdown(
        '<div class="se-script">'
        f'<div class="se-script-icon">{symbols.get(name, ">_")}</div>'
        f'<h3>{escape(script_label(name))}</h3>'
        f'<p>{escape(description or "Approved Python processing function.")}</p></div>',
        unsafe_allow_html=True,
    )


def duplicate_report(result):
    """Show repeated IDs and the rows to compare, including for saved runs."""
    duplicates = result["duplicates"]
    repeat_count = sum(len(item["row_numbers"]) - 1 for item in duplicates)
    if duplicates:
        id_label = "ID" if len(duplicates) == 1 else "IDs"
        row_label = "row" if repeat_count == 1 else "rows"
        st.warning(
            f"{len(duplicates):,} record {id_label} found more than once. "
            f"Review {repeat_count:,} {row_label} where the IDs appear again."
        )
    else:
        st.success("No repeated record IDs found.")

    total = result.get("total_records")
    if isinstance(total, int):
        st.caption(f"{total:,} data rows checked. Blank record IDs are skipped when looking for matches.")
    st.write("Rows are flagged when they have the same Record ID. Other columns may contain different values.")
    if not duplicates:
        return

    rows = []
    for item in duplicates:
        first, *later = item["row_numbers"]
        rows.append({
            "Repeated Record ID": item["record_id"],
            "First seen on row": first,
            "Also found on rows": ", ".join(map(str, later)),
            "Times found": len(later) + 1,
        })
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("The header counts as row 1. Empty lines are skipped when counting rows.")

    columns = result.get("record_columns")
    if not columns:
        st.info("This saved run contains row numbers only. Run Detect Duplicates again with the same CSV to see the record values.")
        return

    section("Compare records")
    matching = {item["record_id"]: item for item in duplicates}
    selected_id = st.selectbox("Record ID to compare", options=list(matching))
    group = matching[selected_id]
    records = pd.DataFrame(
        group["record_values"],
        columns=columns,
        index=pd.Index(group["row_numbers"], name="CSV row"),
    )
    different_columns = [column for column in columns if records[column].nunique(dropna=False) > 1]
    if different_columns:
        st.text("Fields with different values: " + ", ".join(different_columns))
    else:
        st.caption("Every field has the same value in these rows.")
    st.dataframe(records, hide_index=False, width="stretch")


def distribution_chart(rows, category, *, highlighted=None):
    data = pd.DataFrame(rows)
    color = alt.value("#6225FC") if highlighted is None else alt.condition(
        alt.datum[category] == highlighted, alt.value("#6225FC"), alt.value("#B7A3F4"),
    )
    chart = alt.Chart(data).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
        y=alt.Y(f"{category}:N", sort=None, title=None, axis=alt.Axis(labelLimit=180)),
        x=alt.X("Rows:Q", title="Rows", axis=alt.Axis(tickMinStep=1, format="d")),
        color=color,
        tooltip=[f"{category}:N", "Rows:Q", alt.Tooltip("Share:Q", format=".1%")],
    ).properties(height=max(90, 26 * len(rows)))
    st.altair_chart(chart, width="stretch")


def dataset_overview(result):
    section("Dataset Overview")
    total = result["total_records"]
    unique = result["unique_record_ids"]
    metric_cards([
        ("Total rows", f"{total:,}", "summary_total"),
        ("Unique Record IDs", "—" if unique is None else f"{unique:,}", "summary_ids"),
        ("Cities represented", f"{result['city_count']:,}", "summary_cities"),
    ], tones=("blue", "purple", "green"))
    st.caption(
        "Unique Record IDs require a record_id column." if unique is None
        else "Unique Record IDs and city counts exclude blank values."
    )
    if not total:
        st.info("This CSV contains a header and no data rows.")
        return

    section("Records by city", "Choose a city to highlight it and see its source records.")
    groups = result["city_groups"]
    names = {group["city"] for group in groups}
    missing_label = "City missing"
    while missing_label in names:
        missing_label += " (blank)"
    labels = [group["city"] or missing_label for group in groups]
    selected = st.selectbox("City to explore", range(len(groups)), format_func=labels.__getitem__)
    visible = list(range(min(len(groups), 12)))
    if selected not in visible:
        visible[-1] = selected
    if len(groups) > len(visible):
        st.caption("Chart shows the largest groups and the selected city. All cities are available in the selector.")
    distribution_chart([
        {"City": labels[index], "Rows": len(groups[index]["records"]), "Share": len(groups[index]["records"]) / total}
        for index in visible
    ], "City", highlighted=labels[selected])
    records = groups[selected]["records"]
    st.caption(f"{len(records):,} of {total:,} rows ({len(records) / total:.1%}). CSV row 1 is the header. Empty lines are skipped.")
    st.dataframe(records, hide_index=True, width="stretch")

    age = result["age_summary"]
    if age is not None:
        section("Age breakdown", "Only whole-number ages in the accepted range are included.")
        st.caption(f"{age['valid_count']:,} valid ages · {age['missing_count']:,} blank · {age['invalid_count']:,} invalid")
        if age["valid_count"]:
            st.metric("Median age", f"{age['median']:g} years")
            distribution_chart([
                {"Age range": item["range"], "Rows": item["count"], "Share": item["count"] / age["valid_count"]}
                for item in age["ranges"]
            ], "Age range")
        else:
            st.info("No valid ages were available to summarize.")


def result_panel(result):
    """Explain known processing results without hiding their original JSON."""
    if isinstance(result, dict) and "duplicates" in result:
        duplicate_report(result)
    elif isinstance(result, dict) and "city_groups" in result:
        dataset_overview(result)
    elif isinstance(result, dict):
        if "message" in result:
            st.write(result["message"])
        if "total_records" in result:
            st.caption(f"Records processed: {result['total_records']}")
        if "issues" in result:
            metric_cards([
                ("Valid records", result.get("valid_records", "—"), "valid"),
                ("Invalid records", result.get("invalid_records", "—"), "invalid"),
            ], tones=("green", "red"))
            issues = [{"CSV row": issue["row_number"], "Validation issues": "; ".join(issue["errors"])} for issue in result["issues"]]
            if issues:
                st.dataframe(issues, hide_index=True)
            else:
                st.success("All records passed validation.")
        if "records_by_city" in result:
            st.dataframe([{"City": city, "Records": count} for city, count in result["records_by_city"].items()], hide_index=True)
    with st.expander("Technical details (JSON)", expanded=False):
        st.json(result)


def log_timeline(logs):
    for log in logs:
        level = log["level"]
        style = level.lower() if level in {"INFO", "WARNING", "ERROR"} else "neutral"
        st.markdown(
            f'<div class="se-log se-log-{style}"><div class="se-log-line"></div><div>'
            f'<div class="se-log-meta">{badge(level)}<time>{escape(format_timestamp(log["created_at"]))}</time></div>'
            f'<p>{escape(log["message"])}</p></div></div>', unsafe_allow_html=True,
        )
