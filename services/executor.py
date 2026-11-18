"""Run only the predefined processing functions and record their outcomes."""

import json
import time
from types import MappingProxyType

from database.connection import get_connection
from scripts.detect_duplicates import detect_duplicates
from scripts.generate_summary import generate_summary
from scripts.validate_dataset import validate_dataset


# This read-only allowlist never imports or executes user-provided code.
APPROVED_SCRIPTS = MappingProxyType({
    "validate_dataset": validate_dataset,
    "detect_duplicates": detect_duplicates,
    "generate_summary": generate_summary,
})


def register_scripts():
    """Register missing approved names without changing existing scripts."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for name in APPROVED_SCRIPTS:
                    cursor.execute(
                        "INSERT INTO scripts (name) VALUES (%s) "
                        "ON CONFLICT (name) DO NOTHING",
                        (name,),
                    )
        # Leaving the connection context commits and closes the connection.
    except Exception:
        raise RuntimeError(
            "Script registration could not be confirmed. Check database availability and configuration."
        ) from None


def _start_run(script_name):
    """Save the running record and its first log in one short transaction."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, is_active FROM scripts WHERE name = %s FOR UPDATE",
                    (script_name,),
                )
                script = cursor.fetchone()
                if script is not None and script[1]:
                    cursor.execute(
                        "INSERT INTO script_runs (script_id, status) "
                        "VALUES (%s, %s) RETURNING id",
                        (script[0], "running"),
                    )
                    run_id = cursor.fetchone()[0]
                    cursor.execute(
                        "INSERT INTO execution_logs (run_id, level, message) "
                        "VALUES (%s, %s, %s)",
                        (run_id, "INFO", "Script execution started."),
                    )
    except Exception:
        # Do not expose database exceptions, which can contain connection details.
        raise RuntimeError(
            "Could not confirm the starting run and INFO log were saved. Script was not executed."
        ) from None

    if script is None:
        raise ValueError("Script is not registered. Call register_scripts() first.")
    if not script[1]:
        raise ValueError("Script is inactive and cannot be run.")
    return run_id


def _finish_run(run_id, status, duration_ms, result_summary, error):
    """Save the outcome and completion log together, or roll both back."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE script_runs SET status = %s, finished_at = CURRENT_TIMESTAMP, "
                    "duration_ms = %s, result_summary = %s WHERE id = %s",
                    (status, duration_ms, result_summary, run_id),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Run record was not found.")
                level = "ERROR" if error else "INFO"
                message = error or "Script execution completed successfully."
                cursor.execute(
                    "INSERT INTO execution_logs (run_id, level, message) "
                    "VALUES (%s, %s, %s)",
                    (run_id, level, message),
                )
    except Exception:
        raise RuntimeError(
            f"Script execution ended, but the final status and log for run {run_id} "
            "could not be confirmed as saved. The run may still appear as running."
        ) from None


def run_script(script_name, *, dataset=None):
    """Run an approved, active script and return its saved outcome."""
    if script_name not in APPROVED_SCRIPTS:
        raise ValueError("Unknown script. Choose an approved script name.")

    run_id = _start_run(script_name)
    # No database connection or transaction stays open during processing.
    started = time.perf_counter()
    result = None
    error = None
    try:
        process = APPROVED_SCRIPTS[script_name]
        result = process() if dataset is None else process(dataset)
        result_summary = json.dumps(result)
        status = "success"
    except Exception:
        # Never save raw exceptions: they may include secrets or private data.
        error = "Script execution failed. Check the approved function and its input data."
        result_summary = error
        status = "failed"
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))

    # Database failures propagate instead of being mistaken for saved outcomes.
    _finish_run(run_id, status, duration_ms, result_summary, error)
    outcome = {
        "run_id": run_id,
        "script_name": script_name,
        "status": status,
        "duration_ms": duration_ms,
    }
    if error:
        outcome["error"] = error
    else:
        outcome["result"] = result
    return outcome
