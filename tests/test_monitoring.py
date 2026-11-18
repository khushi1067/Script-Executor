"""Monitoring endpoint and page checks without a live API or database."""

from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import requests
from streamlit.testing.v1 import AppTest

from tests.test_api import request


ROOT = Path(__file__).resolve().parent.parent
STARTED = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
RUN = {
    "run_id": 42, "script_name": "generate_summary", "status": "success",
    "started_at": STARTED.isoformat(), "finished_at": STARTED.isoformat(),
    "duration_ms": 4, "result_summary": '{"total_records": 20}',
}


def response(data, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = data
    return mock


def summary(total=150):
    return {
        "total_runs": total, "successful_runs": 120, "failed_runs": 25,
        "running_runs": 5, "success_rate": 80.0, "average_duration_ms": 4.0,
        "recent_executions": [RUN],
        "daily_run_counts": [{"date": f"2026-11-{day}", "run_count": 0} for day in range(10, 17)],
    }


class MonitoringApiTests(unittest.TestCase):
    def connection(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        return connection, cursor

    def test_details_and_ordered_logs(self):
        connection, cursor = self.connection()
        cursor.fetchone.return_value = (42, "generate_summary", "success", STARTED, STARTED, 4, RUN["result_summary"])
        cursor.fetchall.return_value = [(1, STARTED, "INFO", "Started"), (2, STARTED, "INFO", "Finished")]
        with patch("backend.main.get_connection", return_value=connection):
            status, body = request("GET", "/runs/42")
        self.assertEqual(status, 200)
        self.assertEqual(body["run_id"], 42)
        self.assertEqual([log["log_id"] for log in body["logs"]], [1, 2])
        self.assertEqual(cursor.execute.call_args_list[0].args[1], (42,))
        self.assertIn("ORDER BY created_at ASC, id ASC", cursor.execute.call_args.args[0])

    def test_missing_and_invalid_run(self):
        connection, cursor = self.connection()
        cursor.fetchone.return_value = None
        with patch("backend.main.get_connection", return_value=connection):
            self.assertEqual(request("GET", "/runs/999")[0], 404)
        self.assertEqual(request("GET", "/runs/not-an-id")[0], 422)

    def test_analytics_aggregates_all_history_and_seven_days(self):
        connection, cursor = self.connection()
        cursor.fetchone.return_value = (150, 120, 25, 5, 4)
        cursor.fetchall.side_effect = [
            [(42, "generate_summary", "success", STARTED, STARTED, 4, RUN["result_summary"])],
            [(date(2026, 11, day), 0) for day in range(10, 17)],
        ]
        with patch("backend.main.get_connection", return_value=connection):
            status, body = request("GET", "/analytics/summary")
        self.assertEqual(status, 200)
        self.assertEqual(body["total_runs"], 150)  # Not the length of recent executions.
        self.assertEqual(body["success_rate"], 80.0)
        self.assertEqual(body["average_duration_ms"], 4.0)
        self.assertEqual(len(body["daily_run_counts"]), 7)
        self.assertEqual(cursor.execute.call_args_list[1].args[1], (10,))
        self.assertIn("AVG(duration_ms)", cursor.execute.call_args_list[0].args[0])
        self.assertIn("generate_series", cursor.execute.call_args_list[2].args[0])

    def test_empty_analytics_has_no_division_error(self):
        connection, cursor = self.connection()
        cursor.fetchone.return_value = (0, 0, 0, 0, None)
        cursor.fetchall.side_effect = [[], [(date(2026, 11, day), 0) for day in range(10, 17)]]
        with patch("backend.main.get_connection", return_value=connection):
            status, body = request("GET", "/analytics/summary")
        self.assertEqual(status, 200)
        self.assertEqual(body["success_rate"], 0)
        self.assertIsNone(body["average_duration_ms"])

    def test_database_errors_are_safe(self):
        for path in ("/runs/42", "/analytics/summary"):
            with patch("backend.main.get_connection", side_effect=RuntimeError("secret-password")):
                status, body = request("GET", path)
            self.assertEqual(status, 503)
            self.assertNotIn("secret-password", str(body))


class MonitoringPageTests(unittest.TestCase):
    def page(self, name):
        return AppTest.from_file(str(ROOT / "pages" / name), default_timeout=30)

    def test_dashboard_metrics_chart_and_navigation(self):
        with patch("requests.get", return_value=response(summary())):
            page = self.page("1_Dashboard.py").run()
            self.assertFalse(page.exception)
            self.assertEqual([metric.value for metric in page.metric], ["150", "80.00%", "25", "4.00 ms"])
            self.assertEqual(len(page.get("vega_lite_chart")), 1)
            self.assertEqual(sum(button.label == "View Details" for button in page.button), 1)
            page.segmented_control(key="dashboard_status").set_value("Failed").run()
            self.assertIn("No recent runs with status failed.", [item.value for item in page.info])
            page.segmented_control(key="dashboard_status").set_value("Success").run()
            with patch("streamlit.switch_page") as switch:
                page.button(key="details_42").click().run()
                switch.assert_called_once_with("pages/4_Run_Details.py")
                self.assertEqual(page.session_state["selected_run_id"], 42)

    def test_history_navigation(self):
        with patch("requests.get", return_value=response([RUN])):
            page = self.page("3_Execution_History.py").run()
            with patch("streamlit.switch_page") as switch:
                page.button[1].click().run()
                switch.assert_called_once_with("pages/4_Run_Details.py")
                self.assertEqual(page.session_state["selected_run_id"], 42)

    def test_details_query_parameter_and_json_result(self):
        details = {**RUN, "logs": [{"created_at": STARTED.isoformat(), "level": "INFO", "message": "Finished"}]}
        with patch.dict("os.environ", {"API_BASE_URL": "http://demo.test"}):
            with patch("requests.get", return_value=response(details)) as get:
                page = self.page("4_Run_Details.py")
                page.query_params["run_id"] = "42"
                page.run()
        self.assertFalse(page.exception)
        self.assertTrue(page.json)
        self.assertEqual(len(page.dataframe[0].value), 1)
        get.assert_called_once_with("http://demo.test/runs/42", timeout=(5, 15))

    def test_details_session_selection_and_plain_text_failure(self):
        with patch("requests.get", return_value=response({**RUN, "status": "failed", "result_summary": "Safe failure", "logs": []})):
            page = self.page("4_Run_Details.py")
            page.session_state["selected_run_id"] = 42
            page.run()
        self.assertFalse(page.exception)
        self.assertEqual(page.text[0].value, "Safe failure")
        self.assertTrue(page.info)

    def test_missing_invalid_and_nonexistent_run_ids(self):
        with patch("requests.get") as get:
            page = self.page("4_Run_Details.py").run()
            self.assertTrue(page.info)
            page.text_input[0].input("invalid").run()
            self.assertTrue(page.warning)
            get.assert_not_called()
        with patch("requests.get", return_value=response({}, 404)):
            page = self.page("4_Run_Details.py")
            page.query_params["run_id"] = "999"
            page.run()
            self.assertFalse(page.exception)
            self.assertIn("does not exist", page.info[0].value)

    def test_empty_dashboard(self):
        data = summary(0)
        data.update(successful_runs=0, failed_runs=0, running_runs=0, success_rate=0, average_duration_ms=None, recent_executions=[])
        with patch("requests.get", return_value=response(data)):
            page = self.page("1_Dashboard.py").run()
        self.assertFalse(page.exception)
        self.assertTrue(page.info)
        self.assertFalse(page.selectbox)

    def test_new_pages_handle_api_errors(self):
        for name in ("1_Dashboard.py", "4_Run_Details.py"):
            for error in (requests.ConnectionError("secret"), requests.Timeout("secret"), requests.HTTPError("secret"), ValueError("secret")):
                with patch("requests.get", side_effect=error):
                    page = self.page(name)
                    if name == "4_Run_Details.py":
                        page.query_params["run_id"] = "42"
                    page.run()
                self.assertFalse(page.exception)
                self.assertTrue(page.error)
                self.assertNotIn("secret", page.error[0].value)
