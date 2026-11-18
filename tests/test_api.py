"""Exercise the API without a live server, database, or extra test packages."""

import asyncio
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests

from backend.main import app


def request(method, path, body=None, *, files=None):
    """Send an HTTP request directly to the ASGI application."""
    if files is None:
        payload, content_type = json.dumps(body).encode(), "application/json"
    else:
        prepared = requests.Request(method, "http://test" + path, data=body, files=files).prepare()
        payload, content_type = prepared.body, prepared.headers["Content-Type"]

    async def send_request():
        messages = []

        async def receive():
            return {"type": "http.request", "body": payload}

        async def send(message):
            messages.append(message)

        await app(
            {
                "type": "http", "asgi": {"version": "3.0"},
                "http_version": "1.1", "method": method, "scheme": "http",
                "path": path, "raw_path": path.encode(), "query_string": b"",
                "headers": [(b"content-type", content_type.encode())],
                "server": ("test", 80), "client": ("test", 1234),
                "root_path": "",
            },
            receive,
            send,
        )
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, json.loads(content)

    return asyncio.run(send_request())


class ApiTests(unittest.TestCase):
    def test_runs_join_limit_and_datetime_serialization(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        started = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        cursor.fetchall.return_value = [(42, "generate_summary", "running", started, None, None, None)]
        with patch("backend.main.get_connection", return_value=connection):
            status, body = request("GET", "/runs")
        self.assertEqual(status, 200)
        self.assertEqual(body, [{"run_id": 42, "script_name": "generate_summary", "status": "running", "started_at": started.isoformat(), "finished_at": None, "duration_ms": None, "result_summary": None}])
        sql, parameters = cursor.execute.call_args.args
        self.assertIn("JOIN scripts AS s ON r.script_id = s.id", sql)
        self.assertIn("ORDER BY r.started_at DESC, r.id DESC LIMIT %s", sql)
        self.assertEqual(parameters, (100,))

    def test_runs_empty(self):
        connection = MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        with patch("backend.main.get_connection", return_value=connection):
            self.assertEqual(request("GET", "/runs"), (200, []))

    def test_runs_database_failure_is_safe(self):
        with patch("backend.main.get_connection", side_effect=RuntimeError("secret")):
            status, body = request("GET", "/runs")
        self.assertEqual(status, 503)
        self.assertNotIn("secret", str(body))

    def test_health(self):
        self.assertEqual(request("GET", "/health"), (200, {"status": "ok"}))

    def test_list_filters_approved_active_names_and_falls_back_to_docstring(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [("generate_summary", None)]
        with patch("backend.main.get_connection", return_value=connection):
            status, body = request("GET", "/scripts")
        self.assertEqual(status, 200)
        self.assertEqual(body[0]["name"], "generate_summary")
        self.assertTrue(body[0]["description"])
        sql, parameters = cursor.execute.call_args.args
        self.assertIn("is_active = %s AND name = ANY(%s)", sql)
        self.assertTrue(parameters[0])
        self.assertEqual(len(parameters[1]), 3)

    def test_run_returns_service_outcomes(self):
        for outcome_status in ("success", "failed"):
            outcome = {
                "run_id": 7, "script_name": "generate_summary",
                "status": outcome_status, "duration_ms": 2,
            }
            outcome["result" if outcome_status == "success" else "error"] = "safe outcome"
            with patch("backend.main.run_script", return_value=outcome) as run:
                self.assertEqual(request("POST", "/scripts/run", {"script_name": "generate_summary"}), (200, outcome))
                run.assert_called_once_with("generate_summary")

    def test_run_errors_are_safe(self):
        for error, expected in ((ValueError("secret"), 400), (RuntimeError("secret"), 503), (Exception("secret"), 500)):
            with patch("backend.main.run_script", side_effect=error):
                status, body = request("POST", "/scripts/run", {"script_name": "unknown"})
            self.assertEqual(status, expected)
            self.assertNotIn("secret", str(body))

    def test_uploaded_rows_are_processed_and_saved(self):
        dataset = b"\xef\xbb\xbfrecord_id,name,age,city,email\r\n1,Ana,27,Ottawa,ana@example.org\r\n1,Ben,130,Ottawa\r\n"
        results = {
            "generate_summary": ("records_by_city", {"Ottawa": 2}),
            "detect_duplicates": ("duplicate_rows", 1),
            "validate_dataset": ("invalid_records", 1),
        }
        for name, (result_key, expected) in results.items():
            with self.subTest(script=name):
                with patch("services.executor._start_run", return_value=42) as start, patch("services.executor._finish_run") as finish:
                    status, outcome = request("POST", "/scripts/run-upload", {"script_name": name}, files={"dataset": ("custom.csv", dataset)})
                self.assertEqual(status, 200)
                self.assertEqual(outcome["status"], "success")
                self.assertEqual(outcome["result"][result_key], expected)
                start.assert_called_once_with(name)
                self.assertEqual(json.loads(finish.call_args.args[3]), outcome["result"])

    def test_invalid_uploads_never_start_execution(self):
        cases = [
            (b"age\n12\n", 422),
            (b"city\n\xff\n", 422),
            (b'city\n"x', 422),
            (b"", 422),
            (b"city\n123456", 413),
        ]
        for dataset, expected in cases:
            with self.subTest(dataset=dataset):
                with patch("backend.main.MAX_DATASET_BYTES", 10), patch("backend.main.run_script") as run:
                    status, _ = request("POST", "/scripts/run-upload", {"script_name": "generate_summary"}, files={"dataset": ("custom.csv", dataset)})
                self.assertEqual(status, expected)
                run.assert_not_called()

    def test_list_database_error_is_safe(self):
        with patch("backend.main.get_connection", side_effect=ValueError("secret")):
            status, body = request("GET", "/scripts")
        self.assertEqual(status, 503)
        self.assertNotIn("secret", str(body))

    def test_invalid_request_never_executes(self):
        for body in ({}, {"script_name": 123}, {"script_name": "generate_summary", "code": "print(1)"}):
            with patch("backend.main.run_script") as run:
                status, _ = request("POST", "/scripts/run", body)
                self.assertEqual(status, 422)
                run.assert_not_called()
