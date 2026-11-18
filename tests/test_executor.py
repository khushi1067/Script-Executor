"""Executor checks using mocked connections; these never contact Neon."""

import unittest
from unittest.mock import MagicMock, patch

from services import executor


class ExecutorTests(unittest.TestCase):
    def connection(self, rows):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = rows
        cursor.rowcount = 1
        return connection, cursor

    def test_registration_preserves_existing_rows(self):
        connection, cursor = self.connection([])
        with patch.object(executor, "get_connection", return_value=connection):
            executor.register_scripts()
        self.assertEqual(cursor.execute.call_count, 3)
        for call in cursor.execute.call_args_list:
            self.assertIn("ON CONFLICT (name) DO NOTHING", call.args[0])

    def test_unknown_script_never_opens_connection(self):
        with patch.object(executor, "get_connection") as connect:
            with self.assertRaises(ValueError):
                executor.run_script("unapproved")
            connect.assert_not_called()

    def test_missing_or_inactive_script_is_rejected(self):
        for row in (None, (1, False)):
            with self.subTest(row=row):
                connection, cursor = self.connection([row])
                with patch.object(executor, "get_connection", return_value=connection):
                    with self.assertRaises(ValueError):
                        executor.run_script("generate_summary")
                self.assertEqual(cursor.execute.call_count, 1)

    def test_success_commits_start_before_processing(self):
        start, _ = self.connection([(1, True), (42,)])
        finish, cursor = self.connection([])

        def process():
            start.__exit__.assert_called_once_with(None, None, None)
            finish.__enter__.assert_not_called()
            return {"message": "Done", "total_records": 20}

        with patch.object(executor, "get_connection", side_effect=[start, finish]):
            with patch.object(executor, "APPROVED_SCRIPTS", {"generate_summary": process}):
                outcome = executor.run_script("generate_summary")
        self.assertEqual(outcome["run_id"], 42)
        self.assertEqual(outcome["status"], "success")
        self.assertEqual(outcome["result"]["total_records"], 20)
        self.assertGreaterEqual(outcome["duration_ms"], 0)
        self.assertEqual(cursor.execute.call_args_list[0].args[1][0], "success")

    def test_processing_failure_saves_safe_error(self):
        start, _ = self.connection([(1, True), (42,)])
        finish, cursor = self.connection([])
        process = MagicMock(side_effect=RuntimeError("secret-password"))
        with patch.object(executor, "get_connection", side_effect=[start, finish]):
            with patch.object(executor, "APPROVED_SCRIPTS", {"generate_summary": process}):
                outcome = executor.run_script("generate_summary")
        self.assertEqual(outcome["status"], "failed")
        self.assertNotIn("secret-password", str(outcome))
        self.assertNotIn("secret-password", str(cursor.execute.call_args_list))
        self.assertEqual(cursor.execute.call_args_list[-1].args[1][1], "ERROR")

    def test_start_log_failure_prevents_execution(self):
        start, cursor = self.connection([(1, True), (42,)])
        cursor.execute.side_effect = [None, None, RuntimeError("secret")]
        process = MagicMock()
        with patch.object(executor, "get_connection", return_value=start):
            with patch.object(executor, "APPROVED_SCRIPTS", {"generate_summary": process}):
                with self.assertRaisesRegex(RuntimeError, "Script was not executed"):
                    executor.run_script("generate_summary")
        process.assert_not_called()
        self.assertIsNotNone(start.__exit__.call_args.args[0])

    def test_final_log_failure_reports_unsaved_outcome(self):
        start, _ = self.connection([(1, True), (42,)])
        finish, cursor = self.connection([])
        cursor.execute.side_effect = [None, RuntimeError("secret")]
        with patch.object(executor, "get_connection", side_effect=[start, finish]):
            with self.assertRaisesRegex(RuntimeError, "run 42.*could not be confirmed"):
                executor.run_script("generate_summary")
        self.assertIsNotNone(finish.__exit__.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
