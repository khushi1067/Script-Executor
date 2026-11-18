"""Page checks with mocked HTTP requests; no API or database is contacted."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import requests
from streamlit.testing.v1 import AppTest


PAGE = Path(__file__).resolve().parent.parent / "pages" / "2_Run_Script.py"


def response(data):
    mock = MagicMock()
    mock.json.return_value = data
    return mock


class RunScriptPageTests(unittest.TestCase):
    def setUp(self):
        self.scripts = [{"name": "generate_summary", "description": "Count records by city."}]

    def test_loads_names_and_description(self):
        with patch.dict("os.environ", {"API_BASE_URL": "http://demo.test/"}):
            with patch("requests.get", return_value=response(self.scripts)) as get:
                page = AppTest.from_file(str(PAGE)).run()
        self.assertFalse(page.exception)
        self.assertEqual(page.selectbox[0].value, "generate_summary")
        self.assertIn("Count records by city.", [caption.value for caption in page.caption])
        get.assert_called_once_with("http://demo.test/scripts", timeout=(5, 15))

    def test_success_posts_selected_name_and_displays_result(self):
        outcome = {"run_id": 42, "status": "success", "duration_ms": 3, "result": {"total_records": 20}}
        with patch("requests.get", return_value=response(self.scripts)):
            with patch("requests.post", return_value=response(outcome)) as post:
                page = AppTest.from_file(str(PAGE)).run()
                page.button[0].click().run()
        self.assertFalse(page.exception)
        self.assertTrue(page.success)
        self.assertEqual(post.call_args.kwargs["json"], {"script_name": "generate_summary"})
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 120))
        self.assertIn("Run ID: 42 · Status: success", [item.value for item in page.caption])
        self.assertTrue(page.json)

    def test_empty_list(self):
        with patch("requests.get", return_value=response([])):
            page = AppTest.from_file(str(PAGE)).run()
        self.assertTrue(page.info)
        self.assertFalse(page.button)
        self.assertFalse(page.exception)

    def test_csv_upload_sends_the_selected_file_on_run(self):
        dataset = b"city\nOttawa\n"
        outcome = {"run_id": 42, "status": "success", "duration_ms": 3, "result": {"total_records": 1}}
        with patch("requests.get", return_value=response(self.scripts)), patch("requests.post", return_value=response(outcome)) as post:
            page = AppTest.from_file(str(PAGE)).run()
            page.radio[0].set_value("Upload CSV").run()
            self.assertTrue(page.button[0].proto.disabled)
            page.file_uploader[0].set_value(("custom.csv", dataset, "text/csv")).run()
            self.assertFalse(page.button[0].proto.disabled)
            post.assert_not_called()
            page.button[0].click().run()
            self.assertFalse(page.exception)
            self.assertTrue(page.success)
            post.assert_called_once()
            self.assertTrue(post.call_args.args[0].endswith("/scripts/run-upload"))
            self.assertEqual(post.call_args.kwargs["data"], {"script_name": "generate_summary"})
            self.assertEqual(post.call_args.kwargs["files"], {"dataset": ("custom.csv", dataset, "text/csv")})

    def test_load_failures_do_not_expose_errors(self):
        for error in (requests.ConnectionError("secret"), requests.Timeout("secret"), ValueError("secret")):
            with patch("requests.get", side_effect=error):
                page = AppTest.from_file(str(PAGE)).run()
            self.assertFalse(page.exception)
            self.assertTrue(page.error)
            self.assertNotIn("secret", page.error[0].value)

    def test_run_failures_and_timeout_are_friendly(self):
        for error in (requests.ConnectionError("secret"), requests.Timeout("secret")):
            with patch("requests.get", return_value=response(self.scripts)):
                with patch("requests.post", side_effect=error):
                    page = AppTest.from_file(str(PAGE)).run()
                    page.button[0].click().run()
            self.assertFalse(page.exception)
            self.assertIn("before retrying", page.error[0].value)
            self.assertNotIn("secret", page.error[0].value)

    def test_failed_execution_hides_raw_error(self):
        outcome = {"run_id": 42, "status": "failed", "duration_ms": 3, "error": "secret"}
        with patch("requests.get", return_value=response(self.scripts)):
            with patch("requests.post", return_value=response(outcome)):
                page = AppTest.from_file(str(PAGE)).run()
                page.button[0].click().run()
        self.assertFalse(page.exception)
        self.assertTrue(page.error)
        self.assertNotIn("secret", page.error[0].value)

    def test_http_errors_are_friendly(self):
        for status in (400, 503):
            failed = response({"detail": "secret"})
            failed.status_code = status
            failed.raise_for_status.side_effect = requests.HTTPError("secret")
            with patch("requests.get", return_value=response(self.scripts)):
                with patch("requests.post", return_value=failed):
                    page = AppTest.from_file(str(PAGE)).run()
                    page.button[0].click().run()
            self.assertFalse(page.exception)
            self.assertTrue(page.error)
            self.assertNotIn("secret", page.error[0].value)
