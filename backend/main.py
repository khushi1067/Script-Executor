from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

from database.connection import get_connection
from scripts.dataset import MAX_DATASET_BYTES, MAX_DATASET_MB, validate_upload
from services.executor import APPROVED_SCRIPTS, run_script

app = FastAPI()

RUN_COLUMNS = ("run_id", "script_name", "status", "started_at", "finished_at", "duration_ms", "result_summary")


def _recent_runs(cursor, limit):
    """Share the same recent-run query between history and the dashboard."""
    cursor.execute(
        "SELECT r.id AS run_id, s.name AS script_name, r.status, "
        "r.started_at, r.finished_at, r.duration_ms, r.result_summary "
        "FROM script_runs AS r JOIN scripts AS s ON r.script_id = s.id "
        "ORDER BY r.started_at DESC, r.id DESC LIMIT %s",
        (limit,),
    )
    return [dict(zip(RUN_COLUMNS, row)) for row in cursor.fetchall()]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/runs")
def list_runs():
    """Return up to 100 recent runs, including scripts that are now inactive."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                runs = _recent_runs(cursor, 100)
        return runs
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Could not load execution history. Check database availability and configuration.",
        ) from None


@app.get("/runs/{run_id}")
def get_run(run_id: int):
    """Retrieve a saved run and its logs, including runs of inactive scripts."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT r.id, s.name, r.status, r.started_at, r.finished_at, "
                    "r.duration_ms, r.result_summary "
                    "FROM script_runs AS r JOIN scripts AS s ON r.script_id = s.id "
                    "WHERE r.id = %s",
                    (run_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Run not found.")
                run = dict(zip(RUN_COLUMNS, row))
                cursor.execute(
                    "SELECT id, created_at, level, message FROM execution_logs "
                    "WHERE run_id = %s ORDER BY created_at ASC, id ASC",
                    (run_id,),
                )
                log_columns = ("log_id", "created_at", "level", "message")
                run["logs"] = [dict(zip(log_columns, log)) for log in cursor.fetchall()]
        return run
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Could not load run details. Check database availability and configuration.") from None


@app.get("/analytics/summary")
def analytics_summary():
    """Aggregate all-time metrics in SQL; fetch only a small recent-run list."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*), "
                    "COUNT(*) FILTER (WHERE status = %s), "
                    "COUNT(*) FILTER (WHERE status = %s), "
                    "COUNT(*) FILTER (WHERE status = %s), "
                    "AVG(duration_ms) FILTER (WHERE status IN (%s, %s)) "
                    "FROM script_runs",
                    ("success", "failed", "running", "success", "failed"),
                )
                total, successful, failed, running, average = cursor.fetchone()
                recent = _recent_runs(cursor, 10)
                # Use UTC calendar days consistently and include days with zero runs.
                cursor.execute(
                    "WITH days AS ("
                    " SELECT generate_series("
                    " (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date - %s,"
                    " (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date,"
                    " INTERVAL '1 day')::date AS day"
                    "), counts AS ("
                    " SELECT (started_at AT TIME ZONE 'UTC')::date AS day, COUNT(*) AS run_count"
                    " FROM script_runs"
                    " WHERE started_at >= (((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date - %s) AT TIME ZONE 'UTC')"
                    " AND started_at < (((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date + 1) AT TIME ZONE 'UTC')"
                    " GROUP BY (started_at AT TIME ZONE 'UTC')::date"
                    ") SELECT days.day, COALESCE(counts.run_count, 0)"
                    " FROM days LEFT JOIN counts ON counts.day = days.day ORDER BY days.day",
                    (6, 6),
                )
                daily_counts = [{"date": day, "run_count": count} for day, count in cursor.fetchall()]
        return {
            "total_runs": total,
            "successful_runs": successful,
            "failed_runs": failed,
            "running_runs": running,
            # Success rate includes running runs in the denominator.
            "success_rate": round(100 * successful / total, 2) if total else 0.0,
            "average_duration_ms": round(float(average), 2) if average is not None else None,
            "recent_executions": recent,
            "daily_run_counts": daily_counts,
        }
    except Exception:
        raise HTTPException(status_code=503, detail="Could not load analytics. Check database availability and configuration.") from None


class RunScriptRequest(BaseModel):
    # Accept a name only, never code, file paths, or shell commands.
    model_config = ConfigDict(extra="forbid")
    script_name: str


@app.get("/scripts")
def list_scripts():
    """List registered, active scripts that are also in the service allowlist."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name, description FROM scripts "
                    "WHERE is_active = %s AND name = ANY(%s) ORDER BY name",
                    (True, list(APPROVED_SCRIPTS)),
                )
                rows = cursor.fetchall()
        return [
            {
                "name": name,
                # Registration may leave descriptions empty; reuse function docs.
                "description": description or APPROVED_SCRIPTS[name].__doc__ or "",
            }
            for name, description in rows
        ]
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Could not load scripts. Check database availability and configuration.",
        ) from None


@app.post("/scripts/run")
def execute_script(request: RunScriptRequest):
    """Delegate execution and PostgreSQL logging to the existing service."""
    return _execute_script(request.script_name)


@app.post("/scripts/run-upload")
def execute_uploaded_script(script_name: str = Form(), dataset: UploadFile = File()):
    """Validate an uploaded CSV before creating its execution record."""
    if script_name not in APPROVED_SCRIPTS:
        raise HTTPException(status_code=400, detail="Choose an approved script name.")
    data = dataset.file.read(MAX_DATASET_BYTES + 1)
    if len(data) > MAX_DATASET_BYTES:
        raise HTTPException(status_code=413, detail=f"CSV files must be {MAX_DATASET_MB} MB or smaller.")
    try:
        text = validate_upload(data, script_name)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return _execute_script(script_name, dataset=text)


def _execute_script(script_name, *, dataset=None):
    try:
        return run_script(script_name) if dataset is None else run_script(script_name, dataset=dataset)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Script must be approved, registered, and active.",
        ) from None
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Could not confirm execution records were saved. "
                "The script may have executed; check run history before retrying."
            ),
        ) from None
    except Exception:
        # Never send raw exception messages or connection details to API clients.
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while handling the script run.",
        ) from None
