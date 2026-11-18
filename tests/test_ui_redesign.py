"""Check real multipage navigation and readable script output without Neon."""

from pathlib import Path
import unittest
from unittest.mock import patch

import requests
from streamlit.testing.v1 import AppTest

from tests.test_monitoring import RUN, response, summary
from ui_theme import badge


ROOT = Path(__file__).resolve().parent.parent


class RedesignTests(unittest.TestCase):
    def api_response(self, url, **kwargs):
        if url.endswith("/health"):
            return response({"status": "ok"})
        if url.endswith("/analytics/summary"):
            return response(summary())
        if url.endswith("/scripts"):
            return response([
                {"name": "validate_dataset", "description": "Check dataset quality."},
                {"name": "generate_summary", "description": "Count records by city."},
            ])
        if url.endswith("/runs"):
            return response([RUN])
        if url.endswith("/runs/42"):
            return response({**RUN, "logs": [{"created_at": RUN["started_at"], "level": "INFO", "message": "Finished"}]})
        raise AssertionError("Unexpected API path")

    def test_full_app_navigation_and_execution(self):
        with patch("requests.get", side_effect=self.api_response):
            page = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            self.assertFalse(page.exception)
            self.assertTrue(page.metric)
            page.button(key="configure_generate_summary").click().run()
            self.assertFalse(page.exception)
            self.assertEqual(page.selectbox[0].value, "generate_summary")
            outcome = {"run_id": 42, "script_name": "generate_summary", "status": "success", "duration_ms": 4, "result": {"total_records": 20, "records_by_city": {"Toronto": 20}}}
            with patch("requests.post", return_value=response(outcome)) as post:
                next(button for button in page.button if button.label == "Run Script").click().run()
                self.assertFalse(page.exception)
                post.assert_called_once()
                self.assertEqual(post.call_args.kwargs["json"], {"script_name": "generate_summary"})
                self.assertTrue(page.dataframe)
            next(button for button in page.button if button.label == "View this run").click().run()
            self.assertFalse(page.exception)
            self.assertEqual(page.text_input[0].value, "42")

    def test_dashboard_search_opens_saved_run(self):
        with patch("requests.get", side_effect=self.api_response):
            page = AppTest.from_file(str(ROOT / "app.py")).run()
            page.text_input[0].input("42")
            next(button for button in page.button if button.label == "Search").click().run()
            self.assertFalse(page.exception)
            self.assertEqual(page.text_input[0].label, "Run ID")
            self.assertEqual(page.text_input[0].value, "42")
            page.switch_page("pages/1_Dashboard.py").run()
            next(button for button in page.button if button.label == "View All History →").click().run()
            self.assertFalse(page.exception)
            self.assertIn("Open Run Details", [button.label for button in page.button])
            page.switch_page("pages/3_Execution_History.py").run()
            next(button for button in page.button if button.label == "Open Run Details").click().run()
            self.assertFalse(page.exception)
            self.assertEqual(page.text_input[0].value, "42")

    def test_dashboard_handles_failed_health_and_script_probes(self):
        def degraded_api(url, **kwargs):
            if url.endswith(("/health", "/scripts")):
                raise requests.ConnectionError("internal error")
            data = summary()
            data["recent_executions"] = [{**RUN, "status": "failed", "duration_ms": 2400}]
            return response(data)

        with patch("requests.get", side_effect=degraded_api):
            page = AppTest.from_file(str(ROOT / "app.py")).run()
            self.assertFalse(page.exception)
            content = " ".join(item.value for item in page.markdown)
            self.assertNotIn("Operational", content)
            self.assertIn("Connected", content)  # The analytics query verified PostgreSQL.
            self.assertIn("2.4s", content)
            self.assertIn("Approved scripts are unavailable.", [item.value for item in page.info])
            with patch("streamlit.switch_page") as switch:
                page.button(key="investigate_42").click().run()
                switch.assert_called_once_with("pages/4_Run_Details.py")
                self.assertEqual(page.session_state["selected_run_id"], 42)

    def test_each_real_processing_result_renders(self):
        for name in ("validate_dataset", "detect_duplicates", "generate_summary"):
            page = AppTest.from_string(
                f"from scripts.{name} import {name}\n"
                "from ui_theme import result_panel\n"
                f"result_panel({name}())\n",
                default_timeout=30,
            ).run()
            self.assertFalse(page.exception)
            self.assertTrue(page.dataframe)
            self.assertTrue(page.json)

    def test_duplicate_report_separates_first_and_later_rows(self):
        csv_text = "record_id,name\n003,Ada\n7,Ben\n003,Ada L\n003,Ada Lee\n"
        page = AppTest.from_string(
            "from scripts.detect_duplicates import detect_duplicates\n"
            "from ui_theme import result_panel\n"
            f"result_panel(detect_duplicates({csv_text!r}))\n"
        ).run()
        self.assertFalse(page.exception)
        self.assertIn("Review 2 rows", page.warning[0].value)
        self.assertEqual(page.dataframe[0].value.to_dict("records"), [{
            "Repeated Record ID": "003",
            "First seen on row": 2,
            "Also found on rows": "4, 5",
            "Times found": 3,
        }])
        self.assertEqual(page.selectbox[0].value, "003")
        compared = page.dataframe[1].value
        self.assertEqual(compared.index.tolist(), [2, 4, 5])
        self.assertEqual(compared["name"].tolist(), ["Ada", "Ada L", "Ada Lee"])
        self.assertEqual(page.text[0].value, "Fields with different values: name")

    def test_html_components_escape_api_text(self):
        self.assertNotIn("<script>", badge("<script>alert(1)</script>"))
        page = AppTest.from_string(
            "from ui_theme import log_timeline\n"
            "log_timeline([{'created_at': None, 'level': 'ERROR', 'message': '<script>secret</script>'}])\n",
            default_timeout=30,
        ).run()
        self.assertFalse(page.exception)
        self.assertIn("&lt;script&gt;", page.markdown[0].value)
        self.assertNotIn("<script>", page.markdown[0].value)

    def test_dataset_overview_city_drilldown_and_age_coverage(self):
        from scripts.generate_summary import generate_summary

        dataset = (
            "record_id,name,city,age,email\n"
            "001,Ada,Toronto,24,private@example.org\n"
            "001,Ada,,25,private@example.org\n"
            "7,Ben,Unknown,121,private@example.org\n"
            ",Cal,Toronto,,private@example.org\n"
        )
        result = generate_summary(dataset)
        self.assertEqual(result["unique_record_ids"], 2)
        self.assertEqual(result["city_count"], 2)
        self.assertEqual(result["age_summary"]["median"], 24.5)
        self.assertEqual((result["age_summary"]["missing_count"], result["age_summary"]["invalid_count"]), (1, 1))
        self.assertEqual([group["count"] for group in result["age_summary"]["ranges"]][:3], [0, 1, 1])
        self.assertNotIn("private@example.org", repr(result))
        page = AppTest.from_string(
            "from ui_theme import result_panel\n"
            f"result_panel({result!r})\n"
        ).run()
        self.assertFalse(page.exception)
        self.assertEqual([metric.value for metric in page.metric], ["4", "2", "2", "24.5 years"])
        self.assertIn("City missing", page.selectbox[0].options)
        page.selectbox[0].select(next(i for i, group in enumerate(result["city_groups"]) if group["city"] is None)).run()
        self.assertEqual(page.dataframe[0].value["CSV row"].tolist(), [3])

    def test_dataset_summary_accepts_city_only(self):
        from scripts.generate_summary import generate_summary

        result = generate_summary("city\nToronto\n")
        self.assertIsNone(result["unique_record_ids"])
        self.assertIsNone(result["age_summary"])
        self.assertEqual(result["city_groups"][0]["records"], [{"CSV row": 2}])
