"""History page tests use mocked HTTP responses, never PostgreSQL."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import requests
from streamlit.testing.v1 import AppTest


PAGE = Path(__file__).resolve().parent.parent / "pages" / "3_Execution_History.py"


def response(data):
    mock = MagicMock()
    mock.json.return_value = data
    return mock


class HistoryPageTests(unittest.TestCase):
    def setUp(self):
        self.runs = [
            {"run_id": index, "script_name": "generate_summary", "status": status,
             "started_at": "2026-11-16T12:00:00+00:00", "finished_at": None,
             "duration_ms": None if status == "running" else 3}
            for index, status in enumerate(("running", "success", "failed"), start=1)
        ]

    def test_table_counts_filter_and_configurable_url(self):
        with patch.dict("os.environ", {"API_BASE_URL": "http://demo.test/"}):
            with patch("requests.get", return_value=response(self.runs)) as get:
                page = AppTest.from_file(str(PAGE), default_timeout=30).run()
                self.assertFalse(page.exception)
                self.assertEqual([metric.value for metric in page.metric], ["3", "1", "1"])
                self.assertEqual(len(page.dataframe[0].value), 3)
                get.assert_called_with("http://demo.test/runs", timeout=(5, 15))
                for label in ("Success", "Failed", "Running"):
                    page.selectbox[0].select(label).run()
                    self.assertEqual(list(page.dataframe[0].value["Status"]), [label.lower()])
                    self.assertEqual(page.metric[0].value, "3")
                page.button[0].click().run()
                self.assertGreaterEqual(get.call_count, 5)

    def test_empty_history(self):
        with patch("requests.get", return_value=response([])):
            page = AppTest.from_file(str(PAGE), default_timeout=30).run()
        self.assertFalse(page.exception)
        self.assertTrue(page.info)
        self.assertFalse(page.dataframe)
        self.assertEqual(page.metric[0].value, "0")

    def test_no_filter_matches(self):
        with patch("requests.get", return_value=response([self.runs[0]])):
            page = AppTest.from_file(str(PAGE), default_timeout=30).run()
            page.selectbox[0].select("Failed").run()
        self.assertTrue(page.info)
        self.assertFalse(page.dataframe)

    def test_failures_are_friendly(self):
        for error in (requests.ConnectionError("secret"), requests.Timeout("secret"), requests.HTTPError("secret"), ValueError("secret")):
            with patch("requests.get", side_effect=error):
                page = AppTest.from_file(str(PAGE), default_timeout=30).run()
            self.assertFalse(page.exception)
            self.assertTrue(page.error)
            self.assertNotIn("secret", page.error[0].value)

    def test_invalid_response_is_handled(self):
        with patch("requests.get", return_value=response({"unexpected": "secret"})):
            page = AppTest.from_file(str(PAGE), default_timeout=30).run()
        self.assertFalse(page.exception)
        self.assertTrue(page.error)
