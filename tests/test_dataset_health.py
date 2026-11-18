import csv
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from services.dataset_review import build_cleaned_csv, check_dataset, correct_row, matching_groups, rows_to_remove

ROOT = Path(__file__).resolve().parent.parent
DATA = (
    b"record_id,name,age,city,email,notes\n"
    b'001,Ana,22,Ottawa,ana@example.org,"line one\nline two"\n'
    b"001,Ana,25,Ottawa,ana@example.org,updated\n"
    b"2,Ben,50,Toronto,ben@example.org,\n"
    b"2,Ben,50,Toronto,ben@example.org,\n"
    b"3,,bad,Ottawa,wrong,\n"
    b"3,Cal,30,Ottawa,cal@example.org,\n"
)


def test_cleaned_csv_applies_only_saved_decisions():
    report = check_dataset(DATA)
    assert matching_groups(report) == {"2": 4}
    assert [finding["CSV row"] for finding in report["missing"]] == [6]
    assert [finding["CSV row"] for finding in report["invalid"]] == [6, 6]
    removed = rows_to_remove(report, {"2": 4, "001": 2, "3": 999})
    assert removed == {3, 5}
    data = build_cleaned_csv(report, removed).decode()
    rows = list(csv.DictReader(StringIO(data, newline="")))
    assert [row["record_id"] for row in rows] == ["001", "2", "3", "3"]
    assert rows[0]["notes"] == "line one\nline two"
    assert rows[2]["age"] == "bad"


def test_combined_report_and_duplicate_review():
    page = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    with patch("ui_helpers.backend_healthy", return_value=True):
        page.switch_page("pages/5_Dataset_Health.py").run()
        page.file_uploader[0].set_value(("messy.csv", DATA, "text/csv")).run()
        next(button for button in page.button if button.label == "Check dataset").click().run()
        assert not page.exception
        assert [metric.value for metric in page.metric] == ["6", "3", "1", "2"]
        assert "Fields that differ: age, notes" in [text.value for text in page.text]

        page.selectbox(key="health_keep_2_0").select(3)
        next(button for button in page.button if button.label == "Save decision").click().run()
        assert not page.exception
        assert page.session_state["dataset_review_workspace"]["decisions"] == {"001": 3}
        next(button for button in page.button if button.label.startswith("Keep first row")).click().run()
        assert page.session_state["dataset_review_workspace"]["decisions"] == {"001": 3, "2": 4}
        assert "4 rows in the export · 2 removed · 1 duplicate group still to review" in [
            item.value for item in page.caption
        ]

        page.radio(key="health_findings").set_value("Invalid values").run()
        assert page.dataframe[0].value["CSV row"].tolist() == [6, 6]
        assert page.dataframe[1].value.index.tolist() == [6]

        page.text_input(key="health_edit_invalid_6_age").input("121")
        next(button for button in page.button if button.label == "Save corrections").click().run()
        assert "0 and 120" in page.error[0].value
        assert page.metric[3].value == "2"

        page.text_input(key="health_edit_invalid_6_age").input("31")
        page.text_input(key="health_edit_invalid_6_email").input("cal@example.org")
        next(button for button in page.button if button.label == "Save corrections").click().run()
        assert page.metric[3].value == "0"
        page.radio(key="health_findings").set_value("Missing values").run()
        page.text_input(key="health_edit_missing_6_name").input("Cal")
        next(button for button in page.button if button.label == "Save corrections").click().run()
        assert page.metric[2].value == "0"
        preview = page.dataframe[0].value
        assert preview.loc[6, ["name", "age", "email"]].tolist() == ["Cal", "31", "cal@example.org"]

        page.file_uploader[0].set_value(("new.csv", b"record_id\n1\n", "text/csv")).run()
        assert not page.metric
        next(button for button in page.button if button.label == "Check dataset").click().run()
        assert "Missing required CSV columns" in page.error[0].value


def test_correcting_record_id_reopens_only_the_affected_group():
    report = check_dataset(DATA + b",Dana,28,Ottawa,dana@example.org,\n")
    decisions = {"001": 3, "2": 4}
    with pytest.raises(ValueError, match="whole number"):
        correct_row(report, decisions, 6, {"age": "wrong"})
    updated, retained = correct_row(report, decisions, 8, {"record_id": "2"})
    assert updated["duplicates"]["2"]["row_numbers"] == [4, 5, 8]
    assert retained == {"001": 3}
    corrected, retained = correct_row(updated, retained, 6, {"name": "Cal", "age": "31", "email": "cal@example.org"})
    data = build_cleaned_csv(corrected, rows_to_remove(corrected, retained)).decode()
    rows = list(csv.DictReader(StringIO(data, newline="")))
    assert rows[4]["email"] == "cal@example.org"
    assert rows[-1]["record_id"] == "2"
