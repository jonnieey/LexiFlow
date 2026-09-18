from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from rich.console import Console
from rich.style import Style
from rich.table import Table
from sqlalchemy.engine.row import RowMapping

from lexiflow.models import Client  # type: ignore
from lexiflow.utils import tc  # type: ignore
from lexiflow.utils.currency import (
    display_currency_code,
    format_money,
    get_rate,
)


class TranscriptorView:
    MONEY_COLUMNS = {
        "amount",
        "amount_paid",
        "job_rate",
        "total",
        "normal",
        "expedite",
        "interpreted",
    }

    def __init__(self):
        self.console = Console()
        self.table = Table(
            show_header=True,
            header_style="bold #bd93f9",
            border_style="#6272a4",
            title_style="bold #ff79c6",
            caption_style="#6272a4",
            title_justify="center",
            padding=(0, 0),
            expand=True,
        )

    def _get_attr(self, obj: Any, attr: str, default: Any = None) -> Any:
        """Helper to get attribute from dict or object."""
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    def _money_label(
        self, col: str, config: Any = None, rate: Any = None
    ) -> str:
        """Return the column title, adding the currency code in brackets."""
        if config is None or col not in self.MONEY_COLUMNS:
            return tc(str(col))
        return f"{tc(str(col))} ({display_currency_code(config, rate)})"

    def _format_cell(self, col: str, val: Any, config: Any, rate: Any) -> str:
        if config is not None and col in self.MONEY_COLUMNS:
            try:
                return format_money(
                    float(val),
                    config,
                    rate=rate,
                    show_currency=False,
                )
            except (TypeError, ValueError):
                return str(val)
        return str(val)

    def generate_table(
        self,
        objects: Union[Dict, List, Tuple],
        orientation: str = "vertical",
        ordination: Optional[List[str]] = None,
        title: Optional[str] = None,
        config: Any = None,
    ):
        if not objects:
            return

        if title:
            self.table.title = title

        rate = None
        if config is not None:
            rate = get_rate(config)

        # Prepare data for processing
        if isinstance(objects, dict):
            data_list = [objects]
            is_list_of_lists = False
        elif (
            isinstance(objects, (list, tuple))
            and objects
            and isinstance(objects[0], (list, tuple))
        ):
            header = objects[0]
            data_list = objects[1:]
            columns = header
            is_list_of_lists = True
        else:
            data_list = list(objects)
            is_list_of_lists = False

        if not is_list_of_lists:
            first_item = data_list[0] if data_list else {}
            if ordination:
                columns = ordination
            else:
                if isinstance(first_item, dict):
                    columns = list(first_item.keys())
                else:
                    columns = [
                        c
                        for c in getattr(first_item, "__dict__", {}).keys()
                        if not c.startswith("_")
                    ]

        if orientation == "vertical":
            self.table.add_column(tc("Option"), style="#8be9fd")
            self.table.add_column(tc("Value"), style="#f8f8f2")

            for item in data_list:
                row_style = None
                if is_list_of_lists and len(item) >= 2:
                    try:
                        # Check if item has date range that includes today
                        # Assuming item[0] is start/cutoff and item[1] is end/deposit
                        # or some date pair. The user example showed a row with 2 dates.
                        d1 = datetime.strptime(
                            str(item[0]), "%Y-%m-%d"
                        ).date()
                        d2 = datetime.strptime(
                            str(item[1]), "%Y-%m-%d"
                        ).date()
                        # Sort dates to ensure range is valid regardless of order
                        start_date, end_date = sorted([d1, d2])
                        if start_date <= date.today() <= end_date:
                            row_style = "#ff79c6"
                    except (ValueError, TypeError, IndexError):
                        pass

                for col in columns:
                    if is_list_of_lists:
                        # For list of lists in vertical mode, this might be weird
                        # but let's support it by showing all items
                        try:
                            val = item[columns.index(col)]
                        except (ValueError, IndexError):
                            val = ""
                    else:
                        val = self._get_attr(item, col)
                    self.table.add_row(
                        tc(str(col)), str(val), style=row_style
                    )
                if len(data_list) > 1:
                    self.table.add_section()

        elif orientation == "horizontal":
            filtered_columns = [
                col
                for col in columns
                if col
                not in (
                    "_sa_instance_state",
                    "job_path",
                    "client",
                    "job",
                    "rate",
                    "client_email",
                    "provider",
                    "external_job_id",
                    "transcription_status",
                    "transcription_last_polled_at",
                    "transcription_last_error",
                )
            ]
            for col in filtered_columns:
                label = self._money_label(col, config, rate)
                if "date" in col.lower():
                    self.table.add_column(label, no_wrap=True, min_width=10)
                else:
                    self.table.add_column(label)

            total_amount = 0.0
            total_paid = 0.0
            total_sum = 0.0
            total_job_count = 0
            has_totals = False

            for item in data_list:
                style = "#f8f8f2"
                if is_list_of_lists:
                    # Check for cutoff highlighting: [index, start_date, end_date]
                    if len(item) >= 3:
                        try:
                            # Assuming item format [index, date1, date2]
                            d1 = datetime.strptime(
                                str(item[1]), "%Y-%m-%d"
                            ).date()
                            d2 = datetime.strptime(
                                str(item[2]), "%Y-%m-%d"
                            ).date()
                            start, end = sorted([d1, d2])
                            if start <= date.today() <= end:
                                style = "#ff79c6"
                        except (ValueError, IndexError):
                            pass
                else:
                    style = self._get_item_style(item)

                if is_list_of_lists:
                    try:
                        row = [
                            str(item[columns.index(col)])
                            for col in filtered_columns
                        ]
                    except (ValueError, IndexError):
                        row = [""] * len(filtered_columns)
                else:
                    row = [
                        self._format_cell(
                            col, self._get_attr(item, col, ""), config, rate
                        )
                        for col in filtered_columns
                    ]

                self.table.add_row(*row, style=style)

                if not is_list_of_lists:
                    # Accumulate totals if columns exist
                    amount = self._get_attr(item, "amount")
                    paid = self._get_attr(item, "amount_paid")
                    total = self._get_attr(item, "total")
                    job_count = self._get_attr(item, "job_count")

                    if amount is not None:
                        total_amount += float(amount)
                        has_totals = True
                    if paid is not None:
                        total_paid += float(paid)
                        has_totals = True
                    if total is not None:
                        total_sum += float(total)
                        has_totals = True
                    if job_count is not None:
                        total_job_count += int(job_count)
                        has_totals = True

            if has_totals:
                self.table.add_section()
                summary_row = [""] * len(filtered_columns)
                if "amount" in filtered_columns:
                    summary_row[
                        filtered_columns.index("amount")
                    ] = self._format_cell(
                        "amount", total_amount, config, rate
                    )
                if "amount_paid" in filtered_columns:
                    summary_row[
                        filtered_columns.index("amount_paid")
                    ] = self._format_cell(
                        "amount_paid", total_paid, config, rate
                    )
                if "total" in filtered_columns:
                    summary_row[
                        filtered_columns.index("total")
                    ] = self._format_cell("total", total_sum, config, rate)
                if "job_count" in filtered_columns:
                    summary_row[filtered_columns.index("job_count")] = str(
                        total_job_count
                    )
                self.table.add_row(*summary_row)

    def _get_item_style(self, item: Any) -> str:
        date_submitted = self._get_attr(item, "date_submitted")
        date_due = self._get_attr(item, "date_due")
        amount = self._get_attr(item, "amount")
        amount_paid = self._get_attr(item, "amount_paid")

        if date_submitted:
            if (
                amount is not None
                and amount_paid is not None
                and float(amount_paid) < float(amount)
            ):
                return "#8be9fd"
            return "#f8f8f2"

        if date_due:
            if isinstance(date_due, str):
                try:
                    date_due = datetime.strptime(date_due, "%Y-%m-%d").date()
                except ValueError:
                    return "#f8f8f2"

            if isinstance(date_due, datetime):
                date_due = date_due.date()

            if isinstance(date_due, date):
                days_left = (date_due - date.today()).days
                if days_left < 0:
                    return "#bd93f9"
                if days_left < 2:
                    return "#ff5555"
                if days_left < 4:
                    return "#f1fa8c"
                return "#50fa7b"
        return "#f8f8f2"

    def print_table(
        self,
        objects: Union[
            Dict[str, str],
            List[Dict[str, Optional[Union[int, str, Client, float]]]],
            List[Dict[str, Union[int, float]]],
            List[RowMapping],
            List[List[str]],
        ],
        orientation: str = "vertical",
        ordination: None = None,
        title: Optional[str] = None,
        config: Any = None,
    ):
        self.generate_table(
            objects,
            orientation=orientation,
            ordination=ordination,
            title=title,
            config=config,
        )
        self.console.print(self.table)
