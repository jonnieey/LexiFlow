import unittest.mock
from datetime import date, datetime, timedelta

import pytest

from lexiflow.view import TranscriptorView


@pytest.fixture
def view():
    return TranscriptorView()


class TestViewGeneration:
    def test_generate_table_vertical_dict(self, view):
        data = {"key1": "value1", "key2": "value2"}
        view.generate_table(data, orientation="vertical")

        # Access the private table attribute to verify structure
        assert len(view.table.columns) == 2
        assert view.table.columns[0].header == "Option"
        assert view.table.columns[1].header == "Value"

    def test_generate_table_horizontal_list_of_dicts(self, view):
        data = [
            {"id": 1, "name": "Item 1", "amount": 10.0},
            {"id": 2, "name": "Item 2", "amount": 20.0},
        ]
        view.generate_table(data, orientation="horizontal")

        assert len(view.table.columns) == 3
        headers = [c.header for c in view.table.columns]
        assert "Id" in headers
        assert "Name" in headers
        assert "Amount" in headers

    def test_generate_table_horizontal_hides_provider_tracking_columns(
        self, view
    ):
        """provider/external_job_id/transcription_status aren't wired into
        any display logic yet (Phase 2), so `show jobs` shouldn't grow 3
        new blank columns just because the schema gained them."""
        data = [
            {
                "id": 1,
                "job_number": "J1",
                "amount": 10.0,
                "provider": None,
                "external_job_id": None,
                "transcription_status": None,
            }
        ]
        view.generate_table(data, orientation="horizontal")

        headers = [c.header for c in view.table.columns]
        assert "Provider" not in headers
        assert "External Job Id" not in headers
        assert "Transcription Status" not in headers

    def test_generate_table_horizontal_list_of_lists(self, view):
        data = [
            ["Header1", "Header2"],
            ["Val1", "Val2"],
            ["Val3", "Val4"],
        ]
        view.generate_table(data, orientation="horizontal")

        assert len(view.table.columns) == 2
        headers = [c.header for c in view.table.columns]
        assert "Header1" in headers
        assert "Header2" in headers

    def test_generate_table_with_ordination(self, view):
        data = {"key1": "value1", "key2": "value2"}
        view.generate_table(data, orientation="vertical", ordination=["key2"])
        # Should only have key2
        assert len(view.table.rows) == 1

    def test_generate_table_non_dict_object(self, view):
        class MockObj:
            def __init__(self):
                self.name = "Test"
                self.val = 10

        view.generate_table([MockObj()], orientation="horizontal")
        assert len(view.table.columns) == 2

    def test_generate_table_horizontal_with_totals(self, view):
        data = [
            {"name": "A", "amount": 10.0, "amount_paid": 5.0, "job_count": 1},
            {
                "name": "B",
                "amount": 20.0,
                "amount_paid": 10.0,
                "job_count": 2,
            },
        ]
        view.generate_table(data, orientation="horizontal")
        # Header + 2 rows + section + total row = 4 rows in rich Table.rows if section is a row?
        # Actually rich Table.rows doesn't include header.
        # 2 data rows + 1 total row = 3 rows.
        assert len(view.table.rows) == 3
        # Check totals
        # "10.00", "20.00" -> total "30.00"
        # "5.00", "10.00" -> total "15.00"
        # "1", "2" -> total "3"

    def test_empty_data(self, view):
        view.generate_table([])
        assert len(view.table.columns) == 0

    def test_generate_table_vertical_cutoffs_highlight(self, view):
        # Mock today to be inside the range
        today = date(2023, 1, 20)
        with unittest.mock.patch("lexiflow.view.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            # Header + one row that matches today
            data = [["Cutoff", "Deposit"], ["2023-01-15", "2023-01-31"]]
            view.generate_table(data, orientation="vertical")

            # In vertical mode for list of lists, it adds rows.
            # We expect 2 rows added (one for Cutoff, one for Deposit).
            # The style should be passed to add_row.
            # Since we can't easily inspect rich Table rows for style after add_row (it's internal),
            # we might need to mock table.add_row or inspect private attributes if possible.
            # However, looking at the implementation:
            # self.table.add_row(tc(str(col)), str(val), style=row_style)

            # Let's inspect the rows attribute of the table if available or rely on no exception.
            # Rich Table stores rows in .rows, which is a list of Row objects.
            # Row objects have a style attribute.

            assert len(view.table.rows) == 2
            # Check style of the first row
            assert view.table.rows[0].style == "#ff79c6"
            assert view.table.rows[1].style == "#ff79c6"

    def test_generate_table_horizontal_cutoffs_highlight(self, view):
        # Mock today to be inside the range
        today = date(2023, 1, 20)
        with unittest.mock.patch("lexiflow.view.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            # Header + one row that matches today (index, start, end)
            data = [
                ["Index", "Cutoff", "Deposit"],
                ["1", "2023-01-15", "2023-01-31"],
            ]
            view.generate_table(data, orientation="horizontal")

            # Expecting 1 row in the table (plus header which is columns)
            assert len(view.table.rows) == 1
            # Check style of the row
            assert view.table.rows[0].style == "#ff79c6"


class TestItemStyle:
    def test_submitted_paid_less(self, view):
        item = {
            "date_submitted": "2023-01-01",
            "amount": 100.0,
            "amount_paid": 50.0,
        }
        style = view._get_item_style(item)
        assert style == "#8be9fd"

    def test_submitted_paid_full(self, view):
        item = {
            "date_submitted": "2023-01-01",
            "amount": 100.0,
            "amount_paid": 100.0,
        }
        style = view._get_item_style(item)
        assert style == "#f8f8f2"

    def test_due_date_passed(self, view):
        past_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        item = {"date_due": past_date}
        style = view._get_item_style(item)
        assert style == "#bd93f9"

    def test_due_date_imminent(self, view):
        # 1 day left
        soon_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        item = {"date_due": soon_date}
        style = view._get_item_style(item)
        assert style == "#ff5555"

    def test_due_date_soon(self, view):
        # 3 days left
        soon_date = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
        item = {"date_due": soon_date}
        style = view._get_item_style(item)
        assert style == "#f1fa8c"

    def test_due_date_far(self, view):
        # 10 days left
        far_date = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        item = {"date_due": far_date}
        style = view._get_item_style(item)
        assert style == "#50fa7b"

    def test_due_date_as_date_obj(self, view):
        item = {"date_due": date.today() + timedelta(days=10)}
        style = view._get_item_style(item)
        assert style == "#50fa7b"

    def test_due_date_as_datetime_obj(self, view):
        item = {"date_due": datetime.now() + timedelta(days=10)}
        style = view._get_item_style(item)
        assert style == "#50fa7b"

    def test_invalid_date(self, view):
        item = {"date_due": "invalid-date"}
        style = view._get_item_style(item)
        assert style == "#f8f8f2"

    def test_default_style(self, view):
        item = {"other": "value"}
        style = view._get_item_style(item)
        assert style == "#f8f8f2"


class TestPrintTable:
    def test_generate_table_vertical_list_of_lists_date_error(self, view):
        # Trigger ValueError in date parsing
        data = [["Cutoff", "Deposit"], ["invalid-date", "2023-01-20"]]
        view.generate_table(data, orientation="vertical")
        # Should not crash, just not highlight
        assert len(view.table.rows) == 2

    def test_generate_table_horizontal_list_of_lists_date_error(self, view):
        data = [
            ["Index", "Cutoff", "Deposit"],
            ["1", "invalid-date", "2023-01-20"],
        ]
        view.generate_table(data, orientation="horizontal")
        assert len(view.table.rows) == 1

    def test_get_item_style_date_submitted_paid_full(self, view):
        item = {
            "date_submitted": "2023-01-01",
            "amount": 10.0,
            "amount_paid": 10.0,
        }
        assert view._get_item_style(item) == "#f8f8f2"

    def test_get_item_style_date_submitted_unpaid(self, view):
        item = {
            "date_submitted": "2023-01-01",
            "amount": 10.0,
            "amount_paid": 0.0,
        }
        assert view._get_item_style(item) == "#8be9fd"

    def test_get_item_style_date_due_invalid_string(self, view):
        item = {"date_due": "invalid"}
        assert view._get_item_style(item) == "#f8f8f2"

    def test_get_item_style_date_due_datetime(self, view):
        dt = datetime.now() + timedelta(days=10)
        item = {"date_due": dt}
        assert view._get_item_style(item) == "#50fa7b"

    def test_get_attr_dict(self, view):
        obj = {"key": "value"}
        assert view._get_attr(obj, "key") == "value"
        assert view._get_attr(obj, "missing", "default") == "default"

    def test_get_attr_object(self, view):
        class Obj:
            key = "value"

        obj = Obj()
        assert view._get_attr(obj, "key") == "value"
        assert view._get_attr(obj, "missing", "default") == "default"

    def test_generate_table_list_of_lists_column_index_error(self, view):
        # Trigger IndexError when accessing column
        data = [["Col1", "Col2"], ["Val1"]]  # Missing Val2
        view.generate_table(data, orientation="vertical")
        # Should handle it gracefully
        assert len(view.table.rows) == 2  # 2 rows added for vertical

    def test_generate_table_horizontal_list_of_lists_index_error(self, view):
        data = [["Col1", "Col2"], ["Val1"]]
        view.generate_table(data, orientation="horizontal")
        assert len(view.table.rows) == 1
