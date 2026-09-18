import logging
import re
import shutil
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from lexiflow.base import Transcriptor
from lexiflow.utils import (
    TEMPLATE_MAPPING,
    extract_date_due,
    extract_job_number,
    get_media_duration,
    get_media_files,
    invoice_template_themes,
    parse_conditions,
    round_up,
    sc,
)
from lexiflow.utils import str_to_date as std
from lexiflow.utils.currency import (
    CURRENCY_SYMBOLS,
    display_currency_code,
    format_money,
    get_rate,
)
from lexiflow.utils.docx_utils import generate_cutoff_list_from_docx

logger = logging.getLogger(__name__)


# Shared DataTable sorting helpers
def _dt_to_float(val):
    try:
        if isinstance(val, str):
            cleaned = val.replace("$", "").replace(",", "").strip()
            cleaned = re.sub(r"[A-Za-z]{2,}\s*$", "", cleaned)
            return float(cleaned.strip())
        return float(val)
    except Exception:
        return 0.0


def _dt_to_int(val):
    try:
        return int(str(val).strip())
    except Exception:
        return 0


def _dt_to_lower(val):
    return str(val).lower() if val is not None else ""


def _currency_suffix(config, rate=None) -> str:
    return f" ({display_currency_code(config, rate)})"


def sort_datatable_by_column(
    table: DataTable,
    column_key: str,
    toggles: set,
    parse_date: Callable[[str], date] | None = None,
) -> None:
    """Sort a DataTable by `column_key`, toggling asc/desc per column.

    - `toggles` is a set tracking which columns should be reversed on next click.
    - `parse_date` optionally converts date strings to `date` objects using app format.
    """
    if column_key in {"menu", "select"}:
        return

    reverse = column_key in toggles
    if reverse:
        toggles.remove(column_key)
    else:
        toggles.add(column_key)

    def _to_date(val):
        if parse_date is None:
            return date.min
        try:
            return parse_date(str(val))
        except Exception:
            return date.min

    key_map = {
        "id": _dt_to_int,
        "job number": _dt_to_lower,
        "client": _dt_to_lower,
        "status": _dt_to_lower,
        "date due": _to_date,
        "job type": _dt_to_lower,
        "quantity": _dt_to_float,
        "rate": _dt_to_float,
        "amount": _dt_to_float,
    }

    key_fn = key_map.get(column_key, _dt_to_lower)
    table.sort(column_key, key=key_fn, reverse=reverse)


class BaseTable(Container):
    """Base class for tables with selectable rows and vim-like navigation."""

    UNIVERSAL_VIM_BINDINGS = [
        ("j/k", "Move down/up"),
        ("g/G", "Top/bottom"),
        ("h/l", "Move column"),
        ("r", "Refresh"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_items = []  # list of selected IDs
        self._sort_toggles = set()
        self.data = []  # raw data (list of dicts)
        self._custom_vim_bindings = []

    def add_vim_binding(self, key: str, description: str, method_name: str):
        """Register a custom vim key binding."""
        self._custom_vim_bindings.append((key, description, method_name))

    def get_vim_bindings(self) -> List[tuple[str, str]]:
        """Return all vim bindings (universal + custom) for display."""
        bindings = list(self.UNIVERSAL_VIM_BINDINGS)
        for key, desc, _ in self._custom_vim_bindings:
            bindings.append((key, desc))
        return bindings

    def get_table(self) -> DataTable:
        """Return the main DataTable widget (must be overridden)."""
        raise NotImplementedError

    def get_id_column(self) -> str:
        """Name of the column containing the unique ID."""
        return "id"

    def get_item_id(self, item) -> int:
        """Extract the ID from a data item."""
        return item.get("id") if isinstance(item, dict) else item.id

    def get_item_client_name(self, item) -> str:
        """Extract client name from a data item."""
        if hasattr(item.get("client"), "name"):
            return item.get("client").name
        return item.get("client_name", str(item.get("client", "")))

    def refresh_table(self):
        """Load data and populate table (must be overridden)."""
        raise NotImplementedError

    def update_selection_info(self):
        """Update the info Static widget (must be overridden)."""
        raise NotImplementedError

    def get_context_menu(self, item):
        """Return a ModalScreen for the given item (must be overridden)."""
        raise NotImplementedError

    def _row_count(self) -> int:
        try:
            return self.get_table().row_count
        except Exception:
            return len(self.data)

    def get_selected_data(self):
        """Return full dicts for selected items."""
        selected = []
        for item in self.data:
            item_id = self.get_item_id(item)
            if item_id in self.selected_items:

                client_name = item.get("client_name") or getattr(
                    item.get("client"), "name", "Unkown"
                )

                if hasattr(item, "__dict__"):
                    d = item.__dict__.copy()
                else:
                    d = dict(item)
                d["client_name"] = client_name
                selected.append(d)
        return selected

    # -------- cell click handling --------
    @on(DataTable.CellSelected)
    def handle_cell_click(self, event: DataTable.CellSelected):
        event.data_table
        row_key = event.cell_key.row_key
        column_key = event.cell_key.column_key

        if column_key == "menu":
            self._open_context_menu(row_key)
        elif column_key == "select":
            self._toggle_select(row_key)

    def _open_context_menu(self, row_key):
        # row_key is the key we set when adding rows (e.g., str(idx))
        idx = int(row_key.value)
        if 0 <= idx < len(self.data):
            self.app.push_screen(self.get_context_menu(self.data[idx]))

    def _toggle_select(self, row_key):
        table = self.get_table()
        item_id = int(table.get_cell(row_key, self.get_id_column()))
        current = table.get_cell(row_key, "select")
        if current == "☐":
            table.update_cell(row_key, "select", "☑")
            if item_id not in self.selected_items:
                self.selected_items.append(item_id)
        else:
            table.update_cell(row_key, "select", "☐")
            if item_id in self.selected_items:
                self.selected_items.remove(item_id)
        self.update_selection_info()

    # -------- sorting --------
    @on(DataTable.HeaderSelected)
    def on_header_selected(self, event: DataTable.HeaderSelected):
        """Sort table by clicked column, toggling reverse."""
        sort_datatable_by_column(
            self.get_table(),
            event.column_key,
            self._sort_toggles,
            parse_date=lambda s: std(
                s, self.app.transcriptor.config.date_format
            ),
        )

    def handle_vim_key(self, key: str) -> bool:
        """Handle vim keys common to all tables."""
        # Navigation and selection
        if key == "j":
            self.vim_move_down()
            return True
        if key == "k":
            self.vim_move_up()
            return True
        if key == "g":
            self.vim_top()
            return True
        if key == "G":
            self.vim_bottom()
            return True
        if key == "x":
            self.vim_toggle_select_current()
            return True
        if key in ("o", "enter"):
            self.vim_open_context_current()
            return True
        if key == "h":
            self._move_cursor_column(-1)
            return True
        if key == "l":
            self._move_cursor_column(1)
            return True
        if key == "r":
            self.refresh_table()
            return True
        # Action keys (to be overridden by subclasses that have them)

        for k, _, method_name in self._custom_vim_bindings:
            if key == k:
                method = getattr(self, method_name, None)
                if method:
                    method()
                    return True

        # if key == "a" and hasattr(self, "action_add_job"):
        #     self.action_add_job()
        #     return True
        #
        # if key == "e":
        #     # Try edit methods in priority order
        #     for attr in (
        #         "action_edit_job",
        #         "action_edit_client",
        #         "action_edit_rate",
        #     ):
        #         if hasattr(self, attr):
        #             getattr(self, attr)()
        #             return True
        # if key == "d" and hasattr(self, "action_delete_client"):
        #     self.action_delete_client()
        #     return True
        return False

    def _move_cursor_column(self, delta: int):
        """Move table cursor horizontally."""
        table = self.get_table()
        table.focus()
        if table.cursor_column is None:
            table.move_cursor(column=0)
        else:
            new_col = table.cursor_column + delta
            if 0 <= new_col < len(table.columns):
                table.move_cursor(column=new_col)

    # vim_* methods already focus the table, so we just need to ensure they do.
    def vim_move_down(self):
        table = self.get_table()
        table.focus()
        if table.cursor_row is None:
            table.move_cursor(row=0)
        else:
            rc = self._row_count()
            table.move_cursor(row=min(table.cursor_row + 1, max(0, rc - 1)))

    def vim_move_up(self):
        table = self.get_table()
        table.focus()
        if table.cursor_row is None:
            table.move_cursor(row=0)
        else:
            table.move_cursor(row=max(table.cursor_row - 1, 0))

    def vim_top(self):
        table = self.get_table()
        table.focus()
        table.move_cursor(row=0)

    def vim_bottom(self):
        table = self.get_table()
        table.focus()
        rc = self._row_count()
        if rc:
            table.move_cursor(row=rc - 1)

    def vim_toggle_select_current(self):
        table = self.get_table()
        table.focus()
        if table.cursor_row is None:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        self._toggle_select(row_key)

    def vim_open_context_current(self):
        table = self.get_table()
        table.focus()
        if table.cursor_row is None:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        self._open_context_menu(row_key)


class BaseAddScreen(ModalScreen):
    """Base class for simple add screens with common save/cancel buttons."""

    def __init__(self, title: str):
        super().__init__()
        self.title = title

    def compose(self) -> ComposeResult:
        with Container(id=self.get_container_id()):
            yield Label(self.title, classes="add-title")
            with VerticalScroll(id=self.get_form_id()):
                with Vertical():
                    yield from self.get_fields()
            with Horizontal(id="add-buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")

    def get_container_id(self) -> str:
        raise NotImplementedError

    def get_form_id(self) -> str:
        raise NotImplementedError

    def get_fields(self):
        raise NotImplementedError

    @on(Button.Pressed, "#save")
    def save(self):
        if self.validate():
            self.perform_add()
            self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss(False)

    def validate(self) -> bool:
        """Return True if input is valid."""
        raise NotImplementedError

    def perform_add(self):
        """Create the new item."""
        raise NotImplementedError


class BaseEditScreen(ModalScreen):
    """Base class for edit screens with common save/cancel buttons."""

    def __init__(self, data: Dict, title: str):
        super().__init__()
        self.data = data
        self.title = title

    def compose(self) -> ComposeResult:
        with Container(id=self.get_container_id()):
            yield Label(self.title, classes="edit-title")
            with VerticalScroll(id=self.get_form_id()):
                with Vertical():
                    yield from self.get_fields()
            with Horizontal(id="edit-buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")

    def get_container_id(self) -> str:
        """ID of the outer container."""
        raise NotImplementedError

    def get_form_id(self) -> str:
        """ID of the form container (VerticalScroll)."""
        raise NotImplementedError

    def get_fields(self):
        """Yield Label/Input/Select etc. for the form."""
        raise NotImplementedError

    @on(Button.Pressed, "#save")
    def save(self):
        updated = self.collect_values()
        if updated is not None:
            self.perform_update(updated)
            self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss(False)

    def collect_values(self) -> Dict | None:
        """Collect and validate input values. Return None on error."""
        raise NotImplementedError

    def perform_update(self, values: Dict):
        """Apply the update to the database."""
        raise NotImplementedError


class BaseContextMenu(ModalScreen):
    """Base class for context menus with common structure."""

    def __init__(self, item_data: Dict, title: str):
        super().__init__()
        self.item_data = item_data
        self.title = title

    def compose(self) -> ComposeResult:
        with Container(id="context-menu"):
            yield Label(self.title, classes="context-title")
            with ListView(id="action-list"):
                yield from self.get_menu_items()

    def get_menu_items(self):
        """Return list of ListItem widgets."""
        raise NotImplementedError

    @on(ListView.Selected)
    def handle_selection(self, event: ListView.Selected):
        action = event.item.id
        self.handle_action(action)

    def handle_action(self, action: str):
        raise NotImplementedError


class Dashboard(BaseTable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_vim_binding("a", "Add job", "action_add_job")
        self.add_vim_binding("e", "Edit job", "action_edit_job")
        self.add_vim_binding("t", "Transcribe job", "action_transcribe_job")
        self.add_vim_binding("x", "Toggle select", "action_toggle_select"),
        self.add_vim_binding(
            "o/Enter", "Context menu", "action_context_menu"
        ),

    def compose(self) -> ComposeResult:
        yield Label("Pending Jobs", classes="title")
        yield DataTable(id="pending-jobs-table")
        yield Static(id="pending-jobs-selection-info")
        with Container(id="dashboard-controls", classes="panel-controls"):
            with Horizontal(classes="button-bar"):
                yield Button("Add Job", id="dash-add-job")
                yield Button("Edit Job", id="dash-edit-job")
                yield Button("Transcribe", id="dash-transcribe-job")
                yield Button("Refresh", id="dash-refresh")

    def get_table(self) -> DataTable:
        return self.query_one("#pending-jobs-table", DataTable)

    def on_mount(self):
        self.refresh_table()

    def refresh_table(self):
        table = self.get_table()
        table.clear(columns=True)
        table.expand = True
        table.zebra_stripes = True
        config = self.app.transcriptor.config
        rate = get_rate(config)
        suffix = _currency_suffix(config, rate)
        table.add_columns(
            ("⋮", "menu"),
            ("", "select"),
            ("ID", "id"),
            ("Job Number", "job number"),
            ("Client", "client"),
            ("Status", "status"),
            ("Date Due", "date due"),
            ("Job Type", "job type"),
            ("Quantity", "quantity"),
            (f"Rate{suffix}", "rate"),
            (f"Amount{suffix}", "amount"),
            ("Transcription", "transcription"),
        )

        jobs = self.app.transcriptor.api.get_jobs(
            conditions={"status": [("=", "Pending")]}
        )
        self.data = jobs
        self.selected_items = []
        self.update_selection_info()

        for idx, job in enumerate(jobs):
            client_name = self.get_item_client_name(job)
            table.add_row(
                "⋯",
                "☐",
                str(job.get("id")),
                job.get("job_number"),
                client_name,
                job.get("status"),
                job.get("date_due"),
                job.get("job_type"),
                str(job.get("quantity")),
                format_money(
                    job.get("job_rate", 0),
                    config,
                    rate=rate,
                    show_currency=False,
                ),
                format_money(
                    job.get("amount", 0),
                    config,
                    rate=rate,
                    show_currency=False,
                ),
                job.get("transcription_status") or "-",
                key=str(idx),
            )

    def update_selection_info(self):
        self.query_one("#pending-jobs-selection-info", Static).update(
            f"Selected: {len(self.selected_items)} jobs"
        )

    def get_context_menu(self, item):
        return JobContextMenu(item)

    def action_edit_job(self):
        if not self.selected_items:
            self.notify("No job selected!", severity="error")
            return
        job_id = self.selected_items[0]
        jobs = self.app.transcriptor.api.get_jobs(
            conditions={"id": [("=", job_id)]}
        )
        if jobs:
            job_data = (
                jobs[0].__dict__
                if hasattr(jobs[0], "__dict__")
                else dict(jobs[0])
            )
            self.app.push_screen(
                JobEditScreen(job_data), lambda _: self.refresh_table()
            )

    def action_add_job(self):
        self.app.push_screen(AddJobScreen())

    def action_transcribe_job(self):
        if not self.selected_items:
            self.notify("No job selected!", severity="error")
            return
        job_id = self.selected_items[0]
        jobs = self.app.transcriptor.api.get_jobs(
            conditions={"id": [("=", job_id)]}
        )
        if jobs:
            job_data = (
                jobs[0].__dict__
                if hasattr(jobs[0], "__dict__")
                else dict(jobs[0])
            )
            self.app.push_screen(
                TranscriptionScreen(job_data), lambda _: self.refresh_table()
            )

    def action_toggle_select(self):
        self.vim_toggle_select_current()

    def action_context_menu(self):
        self.vim_open_context_current()

    def action_refresh_table(self):
        self.refresh_table()

    @on(Button.Pressed, "#dash-add-job")
    def on_jobs_add(self):
        self.action_add_job()

    @on(Button.Pressed, "#dash-edit-job")
    def on_jobs_edit(self):
        self.action_edit_job()

    @on(Button.Pressed, "#dash-transcribe-job")
    def on_jobs_transcribe(self):
        self.action_transcribe_job()

    @on(Button.Pressed, "#dash-refresh")
    def on_jobs_refresh(self):
        self.action_refresh_table()


class JobsTable(BaseTable):
    """All jobs table with selectable rows."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_vim_binding("a", "Add job", "action_add_job")
        self.add_vim_binding("e", "Edit job", "action_edit_job")
        self.add_vim_binding("t", "Transcribe job", "action_transcribe_job")
        self.add_vim_binding(
            "i", "Generate invoice", "action_generate_invoice"
        )
        self.add_vim_binding("x", "Toggle select", "action_toggle_select"),
        self.add_vim_binding(
            "o/Enter", "Context menu", "action_context_menu"
        ),

    def compose(self) -> ComposeResult:
        yield Label("All Jobs", classes="title")
        yield DataTable(id="jobs-data-table")
        yield Static(id="jobs-selection-info")
        with Container(id="jobs-controls", classes="panel-controls"):
            with Horizontal(classes="button-bar"):
                yield Button("Add Job", id="jobs-add-job")
                yield Button("Edit Job", id="jobs-edit-job")
                yield Button("Transcribe", id="jobs-transcribe-job")
                yield Button("Refresh", id="jobs-refresh")
                yield Button("Generate Invoice", id="jobs-generate-invoice")

    def on_mount(self):
        self.refresh_table()

    def get_table(self) -> DataTable:
        return self.query_one("#jobs-data-table", DataTable)

    def update_selection_info(self):
        self.query_one("#jobs-selection-info", Static).update(
            f"Selected: {len(self.selected_items)} jobs"
        )

    def get_context_menu(self, item):
        return JobContextMenu(item)

    def refresh_table(self):
        table = self.get_table()
        table.clear(columns=True)
        table.zebra_stripes = True
        config = self.app.transcriptor.config
        rate = get_rate(config)
        suffix = _currency_suffix(config, rate)
        table.add_columns(
            ("⋮", "menu"),
            ("", "select"),
            ("ID", "id"),
            ("Job Number", "job number"),
            ("Client", "client"),
            ("Status", "status"),
            ("Date Due", "date due"),
            ("Job Type", "job type"),
            ("Quantity", "quantity"),
            (f"Amount{suffix}", "amount"),
            ("Transcription", "transcription"),
        )

        # Load jobs
        jobs = self.app.transcriptor.api.get_jobs()
        self.data = jobs
        self.selected_items = []
        self.update_selection_info()

        for idx, job in enumerate(jobs):
            client_name = self.get_item_client_name(job)
            table.add_row(
                "⋯",
                "☐",
                str(job.get("id")),
                job.get("job_number"),
                client_name,
                job.get("status"),
                job.get("date_due"),
                job.get("job_type"),
                str(job.get("quantity")),
                format_money(
                    job.get("amount", 0),
                    config,
                    rate=rate,
                    show_currency=False,
                ),
                job.get("transcription_status") or "-",
                key=str(idx),
            )

        # Initial sort: latest first (by id descending)
        try:
            table.sort("id", key=lambda v: int(str(v)), reverse=True)
        except Exception:
            table.sort("id", reverse=True)

    # -------- actions --------
    def action_add_job(self) -> None:
        self.app.push_screen(AddJobScreen())

    def action_refresh_table(self) -> None:
        self.refresh_table()
        self.selected_items = []

    def action_edit_job(self) -> None:
        """Edit the first selected job."""
        if not self.selected_items:
            self.notify("No job selected!", severity="error")
            return

        job_id = self.selected_items[0]
        jobs = self.app.transcriptor.api.get_jobs(
            conditions={"id": [("=", job_id)]}
        )
        if jobs:
            job_data = jobs[0]
            if hasattr(job_data, "__dict__"):
                job_data = job_data.__dict__
            self.app.push_screen(
                JobEditScreen(job_data), lambda _: self.refresh_table()
            )

    def action_transcribe_job(self) -> None:
        """Open the transcription screen for the first selected job."""
        if not self.selected_items:
            self.notify("No job selected!", severity="error")
            return

        job_id = self.selected_items[0]
        jobs = self.app.transcriptor.api.get_jobs(
            conditions={"id": [("=", job_id)]}
        )
        if jobs:
            job_data = jobs[0]
            if hasattr(job_data, "__dict__"):
                job_data = job_data.__dict__
            self.app.push_screen(
                TranscriptionScreen(job_data), lambda _: self.refresh_table()
            )

    def action_generate_invoice(self) -> None:
        """Generate an invoice for selected jobs (must be Done and same client)."""
        if not self.selected_items:
            self.notify("No jobs selected!", severity="error")
            return

        selected = self.get_selected_data()
        if not selected:
            self.notify("Could not retrieve job data.", severity="error")
            return

        # Validate all jobs are Done
        for job in selected:
            if job.get("status", "").lower() != "done":
                self.notify(
                    f"Job {job.get('job_number')} is not Done. Only completed jobs can be invoiced.",
                    severity="error",
                )
                return

        # validate client

        # Validate same client
        client_ids = {job.get("client_id") for job in selected}
        if len(client_ids) != 1:
            self.notify(
                "Selected jobs must belong to the same client.",
                severity="error",
            )
            return

        client_id = selected[0].get("client_id")
        client_name = selected[0].get("client_name")
        if not client_name:
            try:
                clients = self.app.transcriptor.api.get_clients(
                    conditions={"id": [("=", client_id)]}
                )
                client_name = clients[0]["name"] if clients else "Unknown"
            except Exception:
                logger.debug(
                    "Failed to look up client name for id=%s",
                    client_id,
                    exc_info=True,
                )
                client_name = "Unknown"

        if client_name == "Unknown" or not client_name:
            return

        try:
            html, _ = self.app.transcriptor.generate_invoice(selected)
        except Exception as e:
            self.notify(
                f"Error generating invoice: {str(e)}", severity="error"
            )
            return

        self.app.push_screen(
            InvoicePreviewScreen(html, client_name, selected)
        )

    def action_toggle_select(self):
        self.vim_toggle_select_current()

    def action_context_menu(self):
        self.vim_open_context_current()

    # -------- button handlers --------
    @on(Button.Pressed, "#jobs-add-job")
    def on_jobs_add(self):
        self.action_add_job()

    @on(Button.Pressed, "#jobs-edit-job")
    def on_jobs_edit(self):
        self.action_edit_job()

    @on(Button.Pressed, "#jobs-transcribe-job")
    def on_jobs_transcribe(self):
        self.action_transcribe_job()

    @on(Button.Pressed, "#jobs-refresh")
    def on_jobs_refresh(self):
        self.action_refresh_table()

    @on(Button.Pressed, "#jobs-generate-invoice")
    def on_jobs_generate_invoice(self):
        self.action_generate_invoice()


class JobContextMenu(BaseContextMenu):
    def __init__(self, job_data: Dict):
        super().__init__(job_data, f"Job: {job_data.get('job_number', '')}")

    def get_menu_items(self):
        yield ListItem(Label("📝 Edit Job"), id="edit-job")
        yield ListItem(Label("🎙️ Transcribe"), id="transcribe-job")
        yield ListItem(Label("🗑️ Delete Job"), id="delete-job")
        yield ListItem(Label("❌ Cancel"), id="cancel-context")

    def handle_action(self, action: str):
        job_id = self.item_data.get("id")
        if action == "edit-job":
            job_dict = (
                self.item_data.__dict__
                if hasattr(self.item_data, "__dict__")
                else dict(self.item_data)
            )
            self.app.push_screen(JobEditScreen(job_dict), self.check_edit)
        elif action == "transcribe-job":
            job_dict = (
                self.item_data.__dict__
                if hasattr(self.item_data, "__dict__")
                else dict(self.item_data)
            )
            self.app.push_screen(
                TranscriptionScreen(job_dict), self.check_edit
            )
        elif action == "delete-job":

            def check_confirm(confirm):
                if confirm:
                    self.app.transcriptor.delete_jobs(
                        conditions={"id": [("=", job_id)]}
                    )
                    self.app.notify("Job deleted successfully!")
                    self.app.query_one(
                        "#dashboard-pane", Dashboard
                    ).refresh_table()
                    self.app.query_one(
                        "#jobstable-pane", JobsTable
                    ).refresh_table()
                    self.dismiss(True)
                else:
                    self.notify("Job deletion cancelled!")
                    self.dismiss(False)

            self.app.push_screen(ConfirmDelete("job"), check_confirm)
        elif action == "cancel-context":
            self.dismiss()

    def check_edit(self, confirm):
        if confirm:
            self.app.query_one("#dashboard-pane", Dashboard).refresh_table()
            self.app.query_one("#jobstable-pane", JobsTable).refresh_table()
        self.dismiss()


class TranscriptionScreen(ModalScreen):
    """Submit/poll/fetch external transcription for a job."""

    TRANSCRIPTION_PROVIDERS = [
        ("Speechmatics", "speechmatics"),
        ("Rev.ai", "revai"),
        ("NotebookLM", "notebooklm"),
    ]

    def __init__(self, job_data: Dict):
        super().__init__()
        self.job_data = dict(job_data)

    def compose(self) -> ComposeResult:
        with Container(id="transcription-screen"):
            yield Label(
                f"Transcription: {self.job_data.get('job_number', '')}",
                classes="transcription-title",
            )
            yield Static(id="transcription-info")
            with Container(id="transcription-submit-form"):
                yield Label("Provider:")
                yield Select(
                    self.TRANSCRIPTION_PROVIDERS,
                    id="transcription-provider",
                    prompt="Select a provider",
                )
                yield Button(
                    "Submit", variant="primary", id="transcription-submit"
                )
            with Horizontal(id="transcription-actions"):
                yield Button("Poll Status", id="transcription-poll")
                yield Button("Fetch Transcript", id="transcription-fetch")
                yield Button(
                    "Close", variant="default", id="transcription-close"
                )

    def on_mount(self):
        self._update_info_display()

    def _format_info(self) -> str:
        """Pure formatting, no widget access -- testable directly."""
        provider = self.job_data.get("provider")
        external_job_id = self.job_data.get("external_job_id")
        status = self.job_data.get("transcription_status")
        if provider:
            return (
                f"Provider: {provider}\n"
                f"External ID: {external_job_id}\n"
                f"Status: {status or 'unknown'}"
            )
        return "Not yet submitted for transcription."

    def _update_info_display(self):
        self.query_one("#transcription-info", Static).update(
            self._format_info()
        )

    async def do_submit(self, provider: str) -> str:
        """Submit this job for transcription. Raises on error.

        Kept free of widget access so it's directly testable.
        """
        job_id = self.job_data.get("id")
        external_id = await self.app.transcriptor.submit_transcription(
            job_id, provider
        )
        self.job_data["provider"] = provider
        self.job_data["external_job_id"] = external_id
        self.job_data["transcription_status"] = "in_progress"
        return external_id

    async def do_poll(self) -> Optional[str]:
        """Poll transcription status for this job. Raises on error."""
        job_id = self.job_data.get("id")
        status = await self.app.transcriptor.poll_transcription_status(
            job_id
        )
        if status is not None:
            self.job_data["transcription_status"] = status
        return status

    async def do_fetch(self) -> Path:
        """Fetch the transcript for this job. Raises on error."""
        job_id = self.job_data.get("id")
        transcript_path = await self.app.transcriptor.fetch_transcript(
            job_id
        )
        self.job_data["transcription_status"] = "transcribed"
        return transcript_path

    @on(Button.Pressed, "#transcription-submit")
    async def on_submit_pressed(self):
        provider = self.query_one("#transcription-provider", Select).value
        if not provider or provider is Select.BLANK:
            self.app.notify("Please select a provider.", severity="error")
            return
        try:
            external_id = await self.do_submit(provider)
        except Exception as e:
            self.app.notify(
                f"Error submitting transcription: {e}", severity="error"
            )
            return
        self._update_info_display()
        self.app.notify(f"Submitted to {provider}: {external_id}")

    @on(Button.Pressed, "#transcription-poll")
    async def on_poll_pressed(self):
        try:
            status = await self.do_poll()
        except Exception as e:
            self.app.notify(
                f"Error polling status: {e}", severity="error"
            )
            return
        if status is None:
            self.app.notify(
                "No transcription in progress, or the provider poll failed.",
                severity="warning",
            )
            return
        self._update_info_display()
        self.app.notify(f"Status: {status}")

    @on(Button.Pressed, "#transcription-fetch")
    async def on_fetch_pressed(self):
        try:
            transcript_path = await self.do_fetch()
        except Exception as e:
            self.app.notify(
                f"Error fetching transcript: {e}", severity="error"
            )
            return
        self._update_info_display()
        self.app.notify(f"Transcript saved to {transcript_path}")

    @on(Button.Pressed, "#transcription-close")
    def on_close_pressed(self):
        self.dismiss(True)


class JobEditScreen(BaseEditScreen):
    def __init__(self, job_data: Dict):
        super().__init__(
            job_data, f"Edit Job: {job_data.get('job_number', '')}"
        )
        self.client_rates = None

    def on_mount(self):
        """Load client rates when screen mounts."""
        client_id = self.data.get("client_id")
        if client_id:
            rates = self.app.transcriptor.api.get_rates(
                conditions={"client_id": [("=", client_id)]}
            )
            if rates:
                self.client_rates = rates[0]

    def get_container_id(self) -> str:
        return "job-edit"

    def get_form_id(self) -> str:
        return "job-form-container"

    def get_fields(self):
        yield Label("Job Number:")
        yield Input(value=self.data.get("job_number", ""), id="job_number")
        yield Label("Client ID:")
        yield Input(value=str(self.data.get("client_id", "")), id="client_id")
        yield Label("Status:")
        statuses = ["Pending", "Done"]
        current_status = self.data.get("status", "Pending")
        yield Select(
            [(s, s) for s in statuses], value=current_status, id="status"
        )
        yield Label("Amount Paid:")
        yield Input(
            value=str(self.data.get("amount_paid", "")), id="amount_paid"
        )
        yield Label("Job Type:")
        job_types = ["normal", "expedite", "interpreted"]
        current_job_type = self.data.get("job_type", "normal")
        yield Select(
            [(jt, jt) for jt in job_types],
            value=current_job_type,
            id="job_type",
        )
        yield Label("Date Submitted:")
        date_submitted = self.data.get("date_submitted", "")
        yield Input(
            value=date_submitted if date_submitted else "",
            id="date_submitted",
        )
        yield Label("Job Rate:")
        yield Input(value=str(self.data.get("job_rate", "")), id="job_rate")
        yield Label("Date Received:")
        yield Input(
            value=self.data.get("date_received", ""), id="date_received"
        )
        yield Label("Date Due:")
        yield Input(value=self.data.get("date_due", ""), id="date_due")
        yield Label("Quantity:")
        yield Input(value=str(self.data.get("quantity", "")), id="quantity")
        yield Label("Total Quantity:")
        yield Input(
            value=str(self.data.get("total_quantity", "")),
            id="total_quantity",
        )
        yield Label("Amount:")
        yield Input(value=str(self.data.get("amount", "")), id="amount")
        yield Label("Job Path:")
        yield Input(value=self.data.get("job_path", ""), id="job_path")
        yield Label("Note:")
        yield TextArea(self.data.get("note", ""), id="note")

    def collect_values(self) -> Dict | None:
        updated = {}

        # Text fields
        text_fields = [
            "job_number",
            "date_received",
            "date_due",
            "date_submitted",
            "job_path",
        ]
        for field in text_fields:
            widget = self.query_one(f"#{field}", Input)
            updated[field] = widget.value
        updated["date_submitted"] = updated["date_submitted"] or None

        # Numeric fields
        numeric_fields = [
            "client_id",
            "total_quantity",
            "quantity",
            "job_rate",
            "amount",
            "amount_paid",
        ]
        for field in numeric_fields:
            widget = self.query_one(f"#{field}", Input)
            try:
                if widget.value.strip():
                    if field == "client_id":
                        updated[field] = int(widget.value)
                    else:
                        updated[field] = float(widget.value)
                else:
                    updated[field] = 0.0 if field != "client_id" else 0
            except ValueError:
                self.app.notify(
                    f"Invalid value for {field}!", severity="error"
                )
                return None

        # Select fields
        select_fields = ["job_type", "status"]
        for field in select_fields:
            widget = self.query_one(f"#{field}", Select)
            updated[field] = widget.value

        # TextArea
        note_widget = self.query_one("#note", TextArea)
        updated["note"] = note_widget.text

        # Date validation
        if updated.get("date_submitted") and updated.get("date_received"):
            date_format = self.app.transcriptor.config.date_format
            try:
                date_submitted = datetime.strptime(
                    updated["date_submitted"], date_format
                ).date()
                date_received = datetime.strptime(
                    updated["date_received"], date_format
                ).date()
                if date_submitted < date_received:
                    self.app.notify(
                        "Error: Date submitted cannot be earlier than date received.",
                        severity="error",
                    )
                    return None
            except ValueError:
                self.app.notify(
                    f"Invalid date format. Use {date_format}.",
                    severity="error",
                )
                return None

        return updated

    def perform_update(self, values: Dict):
        job_id = self.data.get("id")
        if job_id:
            conditions = {"id": [("=", job_id)]}
            self.app.transcriptor.update_jobs(
                conditions=conditions, values=values
            )
            self.app.notify("Job updated successfully!")

    # Dynamic calculation methods remain unchanged
    def calculate_amount(self) -> float:
        try:
            quantity = float(self.query_one("#quantity", Input).value or 0)
            job_rate = float(self.query_one("#job_rate", Input).value or 0)
            return round_up(quantity * job_rate)
        except (ValueError, AttributeError):
            return 0.0

    def update_job_rate_from_type(self, job_type: str) -> None:
        if not self.client_rates:
            return
        job_type_lower = job_type.lower()
        rate_mapping = {
            "normal": self.client_rates.get("normal", 0),
            "expedite": self.client_rates.get("expedite", 0),
            "interpreted": self.client_rates.get("interpreted", 0),
        }
        new_rate = rate_mapping.get(job_type_lower, 0)
        if new_rate:
            self.query_one("#job_rate", Input).value = str(new_rate)

    @on(Input.Changed, "#job_rate")
    def on_job_rate_changed(self, event: Input.Changed) -> None:
        new_amount = self.calculate_amount()
        self.query_one("#amount", Input).value = f"{new_amount:.2f}"

    @on(Input.Changed, "#quantity")
    def on_quantity_changed(self, event: Input.Changed) -> None:
        new_amount = self.calculate_amount()
        self.query_one("#amount", Input).value = f"{new_amount:.2f}"

    @on(Select.Changed, "#job_type")
    def on_job_type_changed(self, event: Select.Changed) -> None:
        if event.value:
            self.update_job_rate_from_type(event.value)
            new_amount = self.calculate_amount()
            self.query_one("#amount", Input).value = f"{new_amount:.2f}"


class AddJobScreen(ModalScreen):
    """Screen for adding new jobs following CLI workflow"""

    def __init__(self):
        super().__init__()
        self.step = 1  # Track current step
        self.job_data = {}
        self.media_files = []
        self.current_media_index = 0

    def compose(self) -> ComposeResult:
        with Container(id="add-job-screen"):
            yield Label("Add New Job", classes="add-job-title")
            yield Static("Step 1/4: Select Job File", id="add-job-step-info")

            # Initial form for step 1
            with Container(id="add-job-form"):
                pass

            with Horizontal(id="add-job-buttons"):
                yield Button(
                    "Previous",
                    variant="default",
                    id="prev-step",
                    disabled=True,
                )
                yield Button("Next", variant="primary", id="next-step")
                yield Button("Cancel", variant="default", id="cancel-add-job")

    def on_mount(self):
        self.load_step_1()

    def clear_form(self):
        """Clear the form and remove all widgets to avoid duplicate IDs"""
        form = self.query_one("#add-job-form", Container)
        # Remove all children from the form
        for child in list(form.children):
            child.remove()

    def load_step_1(self):
        """Step 1: Job file selection"""
        self.step = 1
        self.clear_form()

        step_info = self.query_one("#add-job-step-info", Static)
        step_info.update("Step 1/4: Select Job File")

        form = self.query_one("#add-job-form", Container)
        form.mount(
            Container(
                Label("Job File Path:"),
                Input(
                    placeholder="Enter path to job file or folder",
                    id="job-file-path",
                ),
                Button("Browse", id="browse-file"),
            )
        )

        self.update_button_states()
        self.call_after_refresh(
            lambda: self.query_one("#job-file-path", Input).focus()
        )
        self.refresh(layout=True)

    def load_step_2(self):
        """Step 2: Job information"""
        self.step = 2
        self.clear_form()

        step_info = self.query_one("#add-job-step-info", Static)
        step_info.update("Step 2/4: Job Information")

        # Get clients for selection
        clients = self.app.transcriptor.api.get_clients()
        client_options = [
            (f"{client['name']} (ID: {client['id']})", str(client["id"]))
            for client in clients
        ]

        # Extract job number and date due from file path
        job_file = self.job_data.get("job_file", "")
        job_number = self.extract_job_number(job_file)
        date_due = self.extract_date_due(job_file)

        date_format = self.app.transcriptor.config.date_format
        today = datetime.now().strftime(date_format)

        form = self.query_one("#add-job-form", Container)
        form.mount(
            Label("Client:"),
            Select(
                client_options, id="client-select", prompt="Select a client"
            ),
            Label("Job Number:"),
            Input(
                value=job_number,
                id="job-number",
                placeholder="Auto-extracted or enter manually",
            ),
            Label("Date Received:"),
            Input(value=today, id="date-received", placeholder=date_format),
            Label("Date Due:"),
            Input(value=date_due, id="date-due", placeholder=date_format),
        )

        self.update_button_states()
        self.query_one("#client-select", Select).focus()
        self.refresh(layout=True)

    def load_step_3(self):
        """Step 3: Media file processing"""
        self.step = 3

        # Update step info
        step_info = self.query_one("#add-job-step-info", Static)

        # Get media files from the job directory

        client_name = self.job_data.get("client_name", "")
        job_number = self.job_data.get("job_number", "")
        date_received = self.job_data.get("date_received", "")
        date_due = self.job_data.get("date_due", "")

        job_dir = self.create_job_dir(
            client_name, job_number, date_received, date_due
        )

        job_file_path = Path(self.job_data.get("job_file", ""))

        self.mv_extract_job_file(job_file_path, job_dir)
        try:
            self.media_files = list(get_media_files(job_dir))
        except Exception as e:
            self.media_files = []
            self.app.notify(
                f"Error scanning for media files: {str(e)}", severity="error"
            )

        if not self.media_files:
            step_info.update("Step 3/4: No media files found")

            # Clear and rebuild form
            form = self.query_one("#add-job-form", Container)
            form.remove_children()

            form.mount(
                Label("No audio/video files found in the job directory."),
                Label("Please check the file path and try again."),
            )

            self.update_button_states()
            self.refresh(layout=True)
            return

        step_info.update(
            f"Step 3/4: Process Media Files ({len(self.media_files)} found)"
        )
        self.current_media_index = 0
        self.load_current_media_form()

    def mv_extract_job_file(
        self, job_file: Path | str, job_dir: Path | str
    ) -> None:
        """
        Move/Extract job file to jobs directory

        Arguments:
            job_file: Path object or path-like string to job file
            job_dir: Path object or path-like string to job directory
        """
        job_file = Path(job_file)
        if zipfile.is_zipfile(job_file):
            try:
                job_dir = Path(job_dir).resolve()
                with zipfile.ZipFile(job_file) as zf:
                    for member in zf.namelist():
                        target = (job_dir / member).resolve()
                        if (
                            job_dir not in target.parents
                            and target != job_dir
                        ):
                            raise ValueError(
                                f"Zip member escapes target directory: {member}"
                            )
                    zf.extractall(job_dir)
                job_file.unlink(missing_ok=True)
            except Exception as e:
                self.app.notify(
                    f"Error extracting zip file: {str(e)}", severity="error"
                )

        else:
            # shutil.move(job_file, job_dir)
            shutil.copy(job_file, job_dir)

    def load_current_media_form(self):
        """Load form for current media file"""
        if self.current_media_index >= len(self.media_files):
            self.load_step_4()
            return

        self.clear_form()

        current_file = self.media_files[self.current_media_index]
        media_info = self.query_one("#add-job-step-info", Static)
        media_info.update(
            f"Step 3/4: Media File {self.current_media_index + 1} of {len(self.media_files)}"
        )

        # Calculate media duration
        try:
            duration = get_media_duration(current_file)
            duration_text = f"{duration:.2f} minutes"
        except Exception as e:
            duration_text = f"Error: {str(e)}"
            duration = 0.0

        # Create unique IDs for this media file
        media_suffix = f"-{self.current_media_index}"

        form = self.query_one("#add-job-form", Container)
        form.mount(
            Label(f"File: {current_file.name}"),
            Label(f"Duration: {duration_text}"),
            Label(f"Path: {str(current_file)}"),
            Checkbox(
                "Process this file?",
                value=True,
                id=f"process-file{media_suffix}",
            ),
            Label("Job Type:"),
            Select(
                [
                    ("Normal", "normal"),
                    ("Expedite", "expedite"),
                    ("Interpreted", "interpreted"),
                ],
                value="normal",
                id=f"job-type{media_suffix}",
            ),
            Label("Quantity (minutes):"),
            Input(value=f"{duration:.2f}", id=f"quantity{media_suffix}"),
            Label("Template:"),
            Select(
                [
                    (v.replace(".docx", ""), k)
                    for k, v in TEMPLATE_MAPPING.items()
                ],
                value="zd",
                id=f"job-template{media_suffix}",
            ),
            Label("Note:"),
            TextArea(
                "",
                id=f"note{media_suffix}",
                placeholder="Optional note for this task",
            ),
        )

        self.update_button_states()
        self.query_one(f"#process-file{media_suffix}", Checkbox).focus()
        self.refresh(layout=True)

    def load_step_4(self):
        """Step 4: Review and confirmation"""
        self.step = 4

        # Update step info
        step_info = self.query_one("#add-job-step-info", Static)
        step_info.update("Step 4/4: Review and Confirm")

        client_name = self.job_data.get("client_name", "N/A")
        job_number = self.job_data.get("job_number", "N/A")
        date_received = self.job_data.get("date_received", "N/A")
        date_due = self.job_data.get("date_due", "N/A")
        tasks = self.job_data.get("tasks", [])

        # Clear and rebuild form
        form = self.query_one("#add-job-form", Container)
        form.remove_children()

        # Build summary content
        summary_widgets = [
            Label("Job Summary:", classes="summary-title"),
            Static(f"Client: {client_name}", classes="summary-item"),
            Static(f"Job Number: {job_number}", classes="summary-item"),
            Static(f"Date Received: {date_received}", classes="summary-item"),
            Static(f"Date Due: {date_due}", classes="summary-item"),
            Static(
                f"Media Files Found: {len(self.media_files)}",
                classes="summary-item",
            ),
            Static(f"Tasks to Create: {len(tasks)}", classes="summary-item"),
        ]

        if tasks:
            summary_widgets.append(Label("Tasks:", classes="summary-title"))
            for i, task in enumerate(tasks):
                summary_widgets.append(
                    Static(
                        f"{i+1}. {task.get('file_name', 'N/A')} - {task.get('job_type', 'N/A')} ({task.get('quantity', 'N/A')} min)",
                        classes="summary-item",
                    )
                )

        # Mount all summary widgets
        for widget in summary_widgets:
            form.mount(widget)

        # Update button states
        self.update_button_states()

        # Force refresh
        self.refresh(layout=True)

    def extract_job_number(self, file_path: str) -> str:
        """Extract job number from file path"""
        return extract_job_number(file_path)

    def extract_date_due(self, file_path: str) -> str:
        """Extract due date from file path"""
        date_due = extract_date_due(file_path)
        if date_due:
            # Convert to proper date format
            date_format = self.app.transcriptor.config.date_format
            try:
                # Try to parse various date formats
                for fmt in ["%m/%d", "%m-%d", "%m.%d"]:
                    try:
                        date_obj = datetime.strptime(date_due, fmt)
                        current_year = datetime.now().year
                        full_date = date_obj.replace(year=current_year)
                        return full_date.strftime(date_format)
                    except ValueError:
                        continue
            except Exception:
                pass
        return ""

    def create_job_dir(
        self,
        client_name: str,
        job_number: str,
        date_received: str,
        date_due: str,
    ) -> Path:
        """
        Create a job directory

        Arguments:
            client_name: Client name
            job_num: Job number
            date_rec: Date received
            date_due: Date due

        Returns:
            Job directory path object
        """
        date_format = self.app.transcriptor.config.date_format
        date_received_obj = std(date_received, date_format)
        date_due_obj = std(date_due, date_format)

        job_dir = (
            self.app.transcriptor.base_dir
            / "clients"
            / sc(client_name)
            / f"{date_received_obj.year}"
            / f"{date_received_obj.strftime('%B')}"
            / f"{date_received_obj.strftime('%d_%a')}_{job_number}_DUE_{date_due_obj.strftime('%d_%a')}"
        )
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    @on(Button.Pressed, "#browse-file")
    def browse_file(self):
        """Open file browser (placeholder - in real implementation, use textual-filebrowser)"""
        # For now, we'll just focus on the input field
        self.query_one("#job-file-path", Input).focus()

    @on(Button.Pressed, "#prev-step")
    def previous_step(self):
        """Go to previous step"""
        if self.step > 1:
            self.step -= 1
            if self.step == 1:
                self.load_step_1()
            elif self.step == 2:
                self.load_step_2()
            elif self.step == 3:
                self.load_step_3()

            # Update button states
            self.update_button_states()

    @on(Button.Pressed, "#next-step")
    def next_step(self):
        """Process current step and move to next"""
        if self.step == 1:
            if not self.process_step_1():
                return
            self.load_step_2()
        elif self.step == 2:
            if not self.process_step_2():
                return
            self.load_step_3()
        elif self.step == 3:
            if not self.process_step_3():
                return
            self.current_media_index += 1
            self.load_current_media_form()
        elif self.step == 4:
            self.create_job()
            return

        self.update_button_states()

    @on(Button.Pressed, "#cancel-add-job")
    def cancel_add_job(self):
        """Cancel job creation"""
        self.dismiss()

    def process_step_1(self) -> bool:
        """Process step 1: Validate job file"""
        file_input = self.query_one("#job-file-path", Input)
        file_path = file_input.value.strip("'").strip('"').strip()

        if not file_path:
            self.app.notify("Please enter a job file path", severity="error")
            return False

        path = Path(file_path)
        if not path.exists():
            self.app.notify(
                "File or directory does not exist", severity="error"
            )
            return False

        self.job_data["job_file"] = file_path
        return True

    def process_step_2(self) -> bool:
        """Process step 2: Validate job information"""
        client_select = self.query_one("#client-select", Select)
        job_number_input = self.query_one("#job-number", Input)
        date_received_input = self.query_one("#date-received", Input)
        date_due_input = self.query_one("#date-due", Input)

        if not client_select.value:
            self.app.notify("Please select a client", severity="error")
            return False

        if not job_number_input.value.strip():
            self.app.notify("Please enter a job number", severity="error")
            return False

        # Basic date validation
        date_format = self.app.transcriptor.config.date_format
        try:
            datetime.strptime(date_received_input.value, date_format)
            datetime.strptime(date_due_input.value, date_format)
        except ValueError:
            self.app.notify(
                f"Invalid date format. Use: {date_format}", severity="error"
            )
            return False

        # Get client name
        # Cast to int to mirror CLI behavior and DB schema
        client_id = int(client_select.value)
        clients = self.app.transcriptor.api.get_clients(
            conditions={"id": [("=", client_id)]}
        )
        client_name = clients[0]["name"] if clients else "Unknown"

        self.job_data.update(
            {
                "client_id": client_id,
                "client_name": client_name,
                "job_number": job_number_input.value,
                "date_received": date_received_input.value,
                "date_due": date_due_input.value,
            }
        )

        return True

    def process_step_3(self) -> bool:
        """Process step 3: Process current media file"""
        if self.current_media_index >= len(self.media_files):
            return True

        # Use the current media index to get the right IDs
        media_suffix = f"-{self.current_media_index}"

        process_checkbox = self.query_one(
            f"#process-file{media_suffix}", Checkbox
        )
        if not process_checkbox.value:
            return True  # Skip this file

        job_type_select = self.query_one(f"#job-type{media_suffix}", Select)
        quantity_input = self.query_one(f"#quantity{media_suffix}", Input)
        template_select = self.query_one(
            f"#job-template{media_suffix}", Select
        )
        note_textarea = self.query_one(f"#note{media_suffix}", TextArea)

        try:
            quantity = float(quantity_input.value)
        except ValueError:
            self.app.notify("Invalid quantity value", severity="error")
            return False

        current_file = self.media_files[self.current_media_index]

        task_data = {
            # Store absolute path to make matching robust when creating the job
            "file_path": str(current_file.resolve()),
            "file_name": current_file.name,
            "job_type": job_type_select.value,
            "quantity": quantity,
            "template": template_select.value,
            "note": note_textarea.text,
            # Keep original media duration for total_quantity like CLI flow
            "total_quantity": get_media_duration(current_file),
        }

        if "tasks" not in self.job_data:
            self.job_data["tasks"] = []
        self.job_data["tasks"].append(task_data)

        return True

    def create_job(self):
        """Create the job using the collected data, mirroring CLI callback flow."""
        try:
            job_info = {
                "client_id": self.job_data["client_id"],
                "job_number": self.job_data["job_number"],
                "date_received": self.job_data["date_received"],
                "date_due": self.job_data["date_due"],
            }

            # Build a mapping of media file absolute path -> per-file task settings
            tasks = self.job_data.get("tasks", [])
            task_map = {str(Path(t["file_path"]).resolve()): t for t in tasks}

            def task_callback(task_file: Path) -> Dict | None:
                """Return task_info for a given media file or None to skip it.

                This mirrors CLI's per-file interactive callback but uses data
                already collected in the TUI forms.
                """
                key = str(Path(task_file).resolve())
                info = task_map.get(key)
                if not info:
                    return None  # Skip files the user did not select/process
                return {
                    "job_type": str(info.get("job_type", "normal")).lower(),
                    "quantity": float(info.get("quantity", 0) or 0),
                    "job_template": info.get("template", "zd"),
                    "note": info.get("note", ""),
                    "total_quantity": float(
                        info.get("total_quantity", info.get("quantity", 0))
                        or 0
                    ),
                }

            # Delegate to core create_job which handles moving/extracting and rate/amount calc
            self.app.transcriptor.create_job(
                job_file=self.job_data["job_file"],
                job_info=job_info,
                task_callback=task_callback,
            )

            # Refresh relevant tables
            try:
                self.app.query_one(
                    "#dashboard-pane", Dashboard
                ).refresh_table()
            except Exception:
                logger.debug(
                    "Could not refresh dashboard pane after job creation",
                    exc_info=True,
                )
            try:
                self.app.query_one(
                    "#jobstable-pane", JobsTable
                ).refresh_table()
            except Exception:
                logger.debug(
                    "Could not refresh jobs table pane after job creation",
                    exc_info=True,
                )

            self.app.notify("Job created successfully!")
            self.dismiss()

        except Exception as e:
            self.app.notify(f"Error creating job: {str(e)}", severity="error")

    def update_button_states(self):
        """Update button states based on current step"""
        prev_button = self.query_one("#prev-step", Button)
        next_button = self.query_one("#next-step", Button)

        # Update previous button
        prev_button.disabled = self.step == 1

        # Update next button text
        if (
            self.step == 3
            and self.current_media_index == len(self.media_files) - 1
        ):
            next_button.label = "Review"
        elif self.step == 4:
            next_button.label = "Create Job"
        else:
            next_button.label = "Next"


class Clients(BaseTable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_vim_binding("a", "Add client", "action_add_client")
        self.add_vim_binding("e", "Edit client", "action_edit_client")
        self.add_vim_binding("d", "Delete client", "action_delete_client")
        self.add_vim_binding("x", "Toggle select", "action_toggle_select"),
        self.add_vim_binding(
            "o/Enter", "Context menu", "action_context_menu"
        ),

    def compose(self) -> ComposeResult:
        yield Label("Clients", classes="title")
        yield DataTable(id="clients-table")
        yield Static(id="clients-selection-info")
        with Container(id="clients-controls", classes="panel-controls"):
            with Horizontal(classes="button-bar"):
                yield Button("Add Client", id="clients-add")
                yield Button("Edit Client", id="clients-edit")
                yield Button("Delete Client", id="clients-delete")
                yield Button("Refresh", id="clients-refresh")

    def on_mount(self):
        self.refresh_table()

    def get_table(self) -> DataTable:
        return self.query_one("#clients-table", DataTable)

    def refresh_table(self):
        table = self.get_table()
        table.clear(columns=True)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.expand = True
        table.add_columns(
            ("⋮", "menu"),
            ("", "select"),
            ("ID", "id"),
            ("Name", "name"),
            ("Email", "email"),
        )

        clients = self.app.transcriptor.api.get_clients()
        self.data = clients
        self.update_selection_info()

        for idx, client in enumerate(clients):
            table.add_row(
                "⋯",
                "☐",
                str(client.get("id")),
                client.get("name"),
                client.get("email"),
                key=str(idx),
            )

    def update_selection_info(self):
        table = self.get_table()
        info = self.query_one("#clients-selection-info", Static)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(
            self.data
        ):
            client_name = self.data[table.cursor_row].get("name", "Unknown")
            info.update(f"Selected: {client_name}")
        else:
            info.update("Selected: None")

    def get_context_menu(self, client):
        return ClientContextMenu(client)

    # -------- actions --------
    def action_add_client(self) -> None:
        self.app.push_screen(AddClientScreen())

    def action_edit_client(self) -> None:
        if self.get_table().cursor_row is None:
            self.app.notify("No client selected!", severity="error")
            return
        client = self.data[self.get_table().cursor_row]
        client_dict = (
            client.__dict__ if hasattr(client, "__dict__") else dict(client)
        )
        self.app.push_screen(
            ClientEditScreen(client_dict), lambda _: self.refresh_table()
        )

    def action_delete_client(self) -> None:
        if self.get_table().cursor_row is None:
            self.app.notify("No client selected!", severity="error")
            return
        client_id = self.data[self.get_table().cursor_row].get("id")

        def check_confirm(confirm):
            if confirm:
                self.app.transcriptor.delete_clients(
                    conditions={"id": [("=", client_id)]}
                )
                self.app.notify("Client deleted successfully!")
                self.refresh_table()
                self.app.query_one("#rates-pane", Rates).refresh_table()
            else:
                self.app.notify("Client deletion cancelled!")

        self.app.push_screen(ConfirmDelete("client"), check_confirm)

    def action_toggle_select(self):
        self.vim_toggle_select_current()

    def action_context_menu(self):
        self.vim_open_context_current()

    # -------- button handlers --------
    @on(Button.Pressed, "#clients-add")
    def on_clients_add(self):
        self.action_add_client()

    @on(Button.Pressed, "#clients-edit")
    def on_clients_edit(self):
        self.action_edit_client()

    @on(Button.Pressed, "#clients-delete")
    def on_clients_delete(self):
        self.action_delete_client()

    @on(Button.Pressed, "#clients-refresh")
    def on_clients_refresh(self):
        self.refresh_table()


class ClientContextMenu(BaseContextMenu):
    def __init__(self, client_data: Dict):
        super().__init__(
            client_data, f"Client: {client_data.get('name', '')}"
        )

    def get_menu_items(self):
        yield ListItem(Label("📝 Edit Client"), id="edit-client")
        yield ListItem(Label("🗑️ Delete Client"), id="delete-client")
        yield ListItem(Label("❌ Cancel"), id="cancel-context")

    def handle_action(self, action: str):
        client_id = self.item_data.get("id")
        if action == "edit-client":
            client_dict = (
                self.item_data.__dict__
                if hasattr(self.item_data, "__dict__")
                else dict(self.item_data)
            )
            self.app.push_screen(
                ClientEditScreen(client_dict), self.check_edit
            )
        elif action == "delete-client":

            def check_confirm(confirm):
                if confirm:
                    self.app.transcriptor.delete_clients(
                        conditions={"id": [("=", client_id)]}
                    )
                    self.app.notify("Client deleted successfully!")
                    self.app.query_one(
                        "#clients-pane", Clients
                    ).refresh_table()
                    self.app.query_one("#rates-pane", Rates).refresh_table()
                    self.dismiss(True)
                else:
                    self.app.notify("Client deletion cancelled!")
                    self.dismiss(False)

            self.app.push_screen(ConfirmDelete("client"), check_confirm)
        elif action == "cancel-context":
            self.dismiss()

    def check_edit(self, confirm):
        if confirm:
            self.app.query_one("#clients-pane", Clients).refresh_table()
        self.dismiss()


class ClientEditScreen(BaseEditScreen):
    def __init__(self, client_data: Dict):
        super().__init__(
            client_data, f"Edit Client: {client_data.get('name', '')}"
        )

    def get_container_id(self) -> str:
        return "client-edit"

    def get_form_id(self) -> str:
        return "client-form-container"

    def get_fields(self):
        yield Label("Name:")
        yield Input(value=self.data.get("name", ""), id="client-name")
        yield Label("Email:")
        yield Input(value=self.data.get("email", ""), id="client-email")

    def collect_values(self) -> Dict | None:
        return {
            "name": self.query_one("#client-name", Input).value,
            "email": self.query_one("#client-email", Input).value,
        }

    def perform_update(self, values: Dict):
        client_id = self.data.get("id")
        if client_id:
            conditions = {"id": [("=", client_id)]}
            self.app.transcriptor.api.update_clients(
                conditions=conditions, values=values
            )
            self.app.notify("Client updated successfully!")


class AddClientScreen(BaseAddScreen):
    def __init__(self):
        super().__init__("Add New Client")

    def get_container_id(self) -> str:
        return "add-client"

    def get_form_id(self) -> str:
        return "add-client-form-container"

    def get_fields(self):
        yield Label("Name:")
        yield Input(id="add-client-name")
        yield Label("Email:")
        yield Input(id="add-client-email")

    def validate(self) -> bool:
        name = self.query_one("#add-client-name", Input).value
        email = self.query_one("#add-client-email", Input).value
        if not name or not email:
            self.app.notify("Name and email are required.", severity="error")
            return False
        return True

    def perform_add(self):
        name = self.query_one("#add-client-name", Input).value
        email = self.query_one("#add-client-email", Input).value
        self.app.transcriptor.create_client(name=name, email=email)
        self.app.notify("Client added successfully!")
        self.app.query_one("#clients-pane", Clients).refresh_table()
        self.app.query_one("#rates-pane", Rates).refresh_table()


class Rates(BaseTable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_vim_binding("e", "Edit rate", "action_edit_rate")
        self.add_vim_binding("x", "Toggle select", "action_toggle_select"),
        self.add_vim_binding(
            "o/Enter", "Context menu", "action_context_menu"
        ),

    def compose(self) -> ComposeResult:
        yield Label("Rates", classes="title")
        yield DataTable(id="rates-table")
        yield Static(id="rates-selection-info")
        with Container(id="rates-controls", classes="panel-controls"):
            with Horizontal(classes="button-bar"):
                yield Button("Edit Rate", id="rates-edit")
                yield Button("Refresh", id="rates-refresh")

    def on_mount(self):
        self.refresh_table()

    def get_table(self) -> DataTable:
        return self.query_one("#rates-table", DataTable)

    def refresh_table(self):
        table = self.get_table()
        table.clear(columns=True)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.expand = True
        table.add_columns(
            ("⋮", "menu"),
            ("", "select"),
            ("Client", "client"),
            ("Normal", "normal"),
            ("Expedite", "expedite"),
            ("Interpreted", "interpreted"),
        )

        rates = self.app.transcriptor.api.get_rates()
        self.data = rates
        self.update_selection_info()

        for idx, rate in enumerate(rates):
            table.add_row(
                "⋯",
                "☐",
                rate.get("client_name"),
                f"${rate.get('normal', 0):.2f}",
                f"${rate.get('expedite', 0):.2f}",
                f"${rate.get('interpreted', 0):.2f}",
                key=str(idx),
            )

    def update_selection_info(self):
        table = self.get_table()
        info = self.query_one("#rates-selection-info", Static)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(
            self.data
        ):
            client_name = self.data[table.cursor_row].get(
                "client_name", "Unknown"
            )
            info.update(f"Selected: {client_name}")
        else:
            info.update("Selected: None")

    def get_context_menu(self, rate):
        return RateContextMenu(rate)

    def action_edit_rate(self) -> None:
        if self.get_table().cursor_row is None:
            self.app.notify("No rate selected!", severity="error")
            return
        rate = self.data[self.get_table().cursor_row]
        rate_dict = rate.__dict__ if hasattr(rate, "__dict__") else dict(rate)
        self.app.push_screen(
            RateEditScreen(rate_dict), lambda _: self.refresh_table()
        )

    def action_toggle_select(self):
        self.vim_toggle_select_current()

    def action_context_menu(self):
        self.vim_open_context_current()

    # -------- button handlers --------
    @on(Button.Pressed, "#rates-edit")
    def on_rates_edit(self):
        self.action_edit_rate()

    @on(Button.Pressed, "#rates-refresh")
    def on_rates_refresh(self):
        self.refresh_table()


class RateContextMenu(BaseContextMenu):
    def __init__(self, rate_data: Dict):
        super().__init__(
            rate_data, f"Rate for: {rate_data.get('client_name', '')}"
        )

    def get_menu_items(self):
        yield ListItem(Label("📝 Edit Rate"), id="edit-rate")
        yield ListItem(Label("❌ Cancel"), id="cancel-context")

    def handle_action(self, action: str):
        if action == "edit-rate":
            rate_dict = (
                self.item_data.__dict__
                if hasattr(self.item_data, "__dict__")
                else dict(self.item_data)
            )
            self.app.push_screen(RateEditScreen(rate_dict), self.check_edit)
        elif action == "cancel-context":
            self.dismiss()

    def check_edit(self, confirm):
        if confirm:
            self.app.query_one("#rates-pane", Rates).refresh_table()
        self.dismiss()


class RateEditScreen(BaseEditScreen):
    def __init__(self, rate_data: Dict):
        super().__init__(
            rate_data, f"Edit Rate: {rate_data.get('client_name', '')}"
        )

    def get_container_id(self) -> str:
        return "rate-edit"

    def get_form_id(self) -> str:
        return "rate-form-container"

    def get_fields(self):
        yield Label("Normal:")
        yield Input(value=str(self.data.get("normal", 0.0)), id="rate-normal")
        yield Label("Expedite:")
        yield Input(
            value=str(self.data.get("expedite", 0.0)), id="rate-expedite"
        )
        yield Label("Interpreted:")
        yield Input(
            value=str(self.data.get("interpreted", 0.0)),
            id="rate-interpreted",
        )

    def collect_values(self) -> Dict | None:
        try:
            normal = float(self.query_one("#rate-normal", Input).value)
            expedite = float(self.query_one("#rate-expedite", Input).value)
            interpreted = float(
                self.query_one("#rate-interpreted", Input).value
            )
        except ValueError:
            self.app.notify("Rates must be numeric values.", severity="error")
            return None
        return {
            "normal": normal,
            "expedite": expedite,
            "interpreted": interpreted,
        }

    def perform_update(self, values: Dict):
        rate_id = self.data.get("id")
        if rate_id:
            conditions = {"id": [("=", rate_id)]}
            self.app.transcriptor.api.update_rates(
                conditions=conditions, values=values
            )
            self.app.notify("Rate updated successfully!")


class Invoice(Container):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = []
        self.selected_client_id = None
        self.invoice_jobs = []
        self.cutoffs_data = []
        self._vim_bindings = [
            ("a", "Add cutoffs", "action_add_cutoffs"),
            ("r", "Refresh cutoffs", "load_cutoffs"),
        ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="invoice-main-layout"):
            yield Label("Invoicing", classes="title")
            # Left pane: Invoice input sections
            with VerticalScroll(id="invoice-input-pane"):
                # Controls (form + buttons)
                with Container(id="invoice-controls"):
                    with Container(id="invoice-form-container"):
                        with Horizontal(classes="form-row"):
                            yield Label("Client:")
                            yield Select(
                                [],
                                id="client-select",
                                prompt="Select a client",
                            )
                        with Horizontal(classes="form-row two-col"):
                            yield Label("Start Date:")
                            yield Input(
                                placeholder="YYYY-MM-DD", id="start-date"
                            )
                            yield Label("End Date:")
                            yield Input(
                                placeholder="YYYY-MM-DD", id="end-date"
                            )

                    with Horizontal(classes="button-bar"):
                        yield Button(
                            "Generate Invoice", id="generate-invoice"
                        )
                        yield Button(
                            "Preview Markdown", id="preview-markdown"
                        )
                        yield Button("Save as PDF", id="save-pdf")
                        yield Button("Save as CSV", id="save-csv")

                # Bottom results pane (no switcher; we toggle visibility)
                with Container(id="invoice-results"):
                    yield DataTable(id="invoice-jobs-table")
                    with VerticalScroll(id="invoice-markdown"):
                        yield Markdown(id="markdown-preview")

            # Right pane: Cutoffs table
            with Container(id="invoice-cutoffs-container"):
                yield Label("Select Deposit Period", classes="title")
                yield DataTable(id="invoice-cutoffs-table")
                with Horizontal(classes="button-bar"):
                    yield Button("Add Cutoffs", id="cutoffs-add")

    def on_mount(self):
        self.load_clients()
        self.load_cutoffs()
        # Initial visibility: show table area, hide markdown
        try:
            self.query_one("#invoice-results", Container).display = True
            self.query_one("#invoice-jobs-table", DataTable).display = True
            self.query_one(
                "#invoice-markdown", VerticalScroll
            ).display = False
        except Exception:
            logger.debug(
                "Could not set initial invoicing pane visibility",
                exc_info=True,
            )

    def get_vim_bindings(self) -> List[tuple[str, str]]:
        return [(key, desc) for key, desc, _ in self._vim_bindings]

    def handle_vim_key(self, key: str) -> bool:
        for k, _, method_name in self._vim_bindings:
            if key == k:
                method = getattr(self, method_name, None)
                if method:
                    method()
                    return True
        return False

    def load_clients(self):
        self.clients = self.app.transcriptor.api.get_clients()
        client_select = self.query_one("#client-select", Select)
        client_options = [
            (f"{client['name']} (ID: {client['id']})", str(client["id"]))
            for client in self.clients
        ]
        client_select.set_options(client_options)

    def load_cutoffs(self):
        """Load cutoffs into the right-hand table"""
        table = self.query_one("#invoice-cutoffs-table", DataTable)
        table.cursor_type = "row"
        table.expand = True
        table.zebra_stripes = True
        table.clear(columns=True)
        table.add_columns("Cutoff Date", "Deposit Date")

        try:
            # We load raw cutoff data to get the list of dates
            # load_cutoffs(as_str=True) returns list of lists: [[header], [d1, d2], ...]
            # We skip header
            raw_cutoffs = self.app.transcriptor.load_cutoffs(as_str=True)
            self.cutoffs_data = raw_cutoffs[1:]  # Store data for indexing

            for idx, cutoff in enumerate(self.cutoffs_data):
                if len(cutoff) >= 2:
                    table.add_row(cutoff[0], cutoff[1], key=str(idx))
        except Exception as e:
            table.add_row("Error loading", str(e))

    def action_add_cutoffs(self):
        def check_add(confirm):
            if confirm:
                self.load_cutoffs()

        self.app.push_screen(AddCutoffsScreen(), check_add)

    @on(Button.Pressed, "#cutoffs-add")
    def on_cutoffs_add(self):
        self.action_add_cutoffs()

    @on(DataTable.RowHighlighted, "#invoice-cutoffs-table")
    def on_cutoff_highlighted(self, event: DataTable.RowHighlighted):
        """Auto-fill dates when a cutoff row is highlighted/selected"""
        if event.cursor_row is None:
            return

        row_index = event.cursor_row
        if 0 <= row_index < len(self.cutoffs_data):
            current_row = self.cutoffs_data[row_index]
            current_cutoff_str = current_row[0]

            # Logic:
            # End Date = Current Cutoff Date
            # Start Date = Previous Cutoff Date + 1 day
            # If it's the first row, we might default to start of year or similar logic?
            # Based on user prompt: "row with 2026-02-06, 2026-02-16" -> Start 07, End 16.
            # This implies the row represents the END of the period.

            date_fmt = self.app.transcriptor.config.date_format
            try:
                end_date_obj = datetime.strptime(
                    current_cutoff_str, date_fmt
                ).date()

                start_date_obj = None
                if row_index > 0:
                    prev_row = self.cutoffs_data[row_index - 1]
                    prev_cutoff_str = prev_row[0]
                    prev_cutoff_obj = datetime.strptime(
                        prev_cutoff_str, date_fmt
                    ).date()
                    start_date_obj = prev_cutoff_obj + timedelta(days=1)
                else:
                    # First cutoff of the list.
                    # Logic from base.py: select_cutoff_period uses previous year's last cutoff
                    # or defaults to Jan 1st of current year.
                    # Let's try to replicate simple fallback logic here:
                    # If we can't find previous, maybe just set start date to something reasonable
                    # or leave blank? User asked for specific behavior based on selection.
                    # Let's default to 1st of Jan of that year if no previous row.
                    start_date_obj = date(end_date_obj.year, 1, 1)

                self.query_one(
                    "#start-date", Input
                ).value = start_date_obj.strftime(date_fmt)
                self.query_one(
                    "#end-date", Input
                ).value = end_date_obj.strftime(date_fmt)

            except ValueError:
                logger.debug(
                    "Could not auto-fill start/end date from cutoff row",
                    exc_info=True,
                )

    @on(Select.Changed, "#client-select")
    def on_client_select(self, event: Select.Changed):
        self.selected_client_id = event.value

    @on(Button.Pressed, "#generate-invoice")
    def on_generate_invoice(self):
        if not self.selected_client_id:
            self.app.notify("Please select a client.", severity="error")
            return

        start_date = self.query_one("#start-date", Input).value
        end_date = self.query_one("#end-date", Input).value

        conditions = []
        if start_date:
            conditions.append(f"date_submitted>={start_date}")
        if end_date:
            conditions.append(f"date_submitted<={end_date}")

        if not conditions:
            self.app.notify(
                "Please enter a start or end date.", severity="error"
            )
            return

        conditions = parse_conditions(conditions)

        self.invoice_jobs = self.app.transcriptor.get_invoice_jobs(
            client_id=self.selected_client_id, conditions=conditions
        )

        # Show table in the bottom pane
        table = self.query_one("#invoice-jobs-table", DataTable)
        md_container = self.query_one("#invoice-markdown", VerticalScroll)
        results_container = self.query_one("#invoice-results", Container)
        results_container.display = True
        table.display = True
        md_container.display = False
        table.clear(columns=True)
        config = self.app.transcriptor.config
        rate = get_rate(config)
        suffix = _currency_suffix(config, rate)
        table.add_columns("Job Number", "Date Submitted", f"Amount{suffix}")

        if self.invoice_jobs:
            for job in self.invoice_jobs:
                table.add_row(
                    job["job_number"],
                    job["date_submitted"],
                    format_money(
                        job["amount"], config, rate=rate, show_currency=False
                    ),
                )
            # Move focus to the table and ensure it's visible
            try:
                table.move_cursor(row=0)
            except Exception:
                logger.debug(
                    "Could not move cursor on invoice jobs table",
                    exc_info=True,
                )
            try:
                table.focus()
                table.scroll_visible()
            except Exception:
                logger.debug(
                    "Could not focus/scroll invoice jobs table",
                    exc_info=True,
                )
        else:
            self.app.notify(
                "No jobs found for this period.", severity="warning"
            )
            # Keep table visible (empty) so the pane is present
            table.display = True
            md_container.display = False

    @on(Button.Pressed, "#preview-markdown")
    def on_preview_markdown(self):
        if not self.invoice_jobs:
            self.app.notify("No invoice jobs to preview.", severity="error")
            return

        html, _ = self.app.transcriptor.generate_invoice(self.invoice_jobs)
        md = self.app.transcriptor.to_md(html)
        self.query_one("#markdown-preview", Markdown).update(md)

        # Toggle to markdown in the bottom pane
        table = self.query_one("#invoice-jobs-table", DataTable)
        md_container = self.query_one("#invoice-markdown", VerticalScroll)
        table.display = False
        md_container.display = True
        # Move focus to markdown area so the user sees it
        try:
            md_container.focus()
        except Exception:
            logger.debug(
                "Could not focus invoice markdown container", exc_info=True
            )
        try:
            md_container.scroll_visible()
        except Exception:
            logger.debug(
                "Could not scroll invoice markdown container into view",
                exc_info=True,
            )
        try:
            self.query_one("#markdown-preview", Markdown).focus()
        except Exception:
            logger.debug(
                "Could not focus markdown-preview widget", exc_info=True
            )

    @on(Button.Pressed, "#save-pdf")
    def on_save_pdf(self):
        if not self.invoice_jobs:
            self.app.notify("No invoice jobs to save.", severity="error")
            return

        client_name = ""
        for client in self.clients:
            if str(client["id"]) == self.selected_client_id:
                client_name = client["name"]
                break

        html, _ = self.app.transcriptor.generate_invoice(self.invoice_jobs)
        self.app.transcriptor.html_to_pdf(html, client_name)
        self.app.notify(f"Invoice for {client_name} saved as PDF.")

    @on(Button.Pressed, "#save-csv")
    def on_save_csv(self):
        if not self.invoice_jobs:
            self.app.notify("No invoice jobs to save.", severity="error")
            return

        client_name = ""
        for client in self.clients:
            if str(client["id"]) == self.selected_client_id:
                client_name = client["name"]
                break

        self.app.transcriptor.generate_csv_invoice(
            self.invoice_jobs, client_name
        )
        self.app.notify(f"Invoice for {client_name} saved as CSV.")


class InvoicePreviewScreen(ModalScreen):
    def __init__(self, html_content: str, client_name: str, jobs: List[Dict]):
        super().__init__()
        self.html_content = html_content
        self.client_name = client_name
        self.jobs = jobs

    def compose(self) -> ComposeResult:
        with Container(id="invoice-preview"):
            yield Label("Invoice Preview", classes="preview-title")
            yield Markdown(
                self.app.transcriptor.to_md(self.html_content),
                id="invoice-markdown",
            )
            with Horizontal(id="preview-buttons"):
                yield Button(
                    "Generate PDF", variant="primary", id="generate-pdf"
                )
                yield Button(
                    "Generate CSV", variant="primary", id="generate-csv"
                )
                yield Button("Cancel", variant="default", id="cancel-preview")

    @on(Button.Pressed, "#generate-pdf")
    def generate_pdf(self):
        """Generate PDF invoice (mirrors Invoicing tab behavior)."""
        try:
            # Regenerate invoice to ensure latest data (same as Invoicing tab)
            html, _ = self.app.transcriptor.generate_invoice(self.jobs)
            self.app.transcriptor.html_to_pdf(html, self.client_name)
            self.app.notify(f"Invoice for {self.client_name} saved as PDF.")
            self.dismiss()
        except Exception as e:
            self.app.notify(
                f"Error generating PDF: {str(e)}", severity="error"
            )

    @on(Button.Pressed, "#generate-csv")
    def generate_csv(self):
        """Generate CSV invoice (mirrors Invoicing tab behavior)."""
        try:
            self.app.transcriptor.generate_csv_invoice(
                self.jobs, self.client_name
            )
            self.app.notify(f"Invoice for {self.client_name} saved as CSV.")
            self.dismiss()
        except Exception as e:
            self.app.notify(
                f"Error generating CSV: {str(e)}", severity="error"
            )

    @on(Button.Pressed, "#cancel-preview")
    def cancel_preview(self):
        self.dismiss()


class AddCutoffsScreen(BaseAddScreen):
    def __init__(self):
        super().__init__("Add Cutoffs from Docx")

    def get_container_id(self) -> str:
        return "add-cutoffs"

    def get_form_id(self) -> str:
        return "add-cutoffs-form-container"

    def get_fields(self):
        yield Label("Docx File Path:")
        yield Input(
            placeholder="Enter path to cutoffs docx file",
            id="cutoffs-file-path",
        )
        yield Button("Browse", id="browse-cutoffs-file")
        yield Label("Year:")
        yield Input(value=str(datetime.now().year), id="cutoffs-year")
        yield Label("Date Format:")
        yield Input(
            value=self.app.transcriptor.config.date_format,
            id="invoice-date-format",
        )

    def validate(self) -> bool:
        file_path = self.query_one("#cutoffs-file-path", Input).value
        if not file_path:
            self.app.notify("Please enter a file path.", severity="error")
            return False
        path = Path(file_path)
        if not path.exists():
            self.app.notify(f"File not found: {file_path}", severity="error")
            return False
        return True

    def perform_add(self):
        file_path = self.query_one("#cutoffs-file-path", Input).value
        year = self.query_one("#cutoffs-year", Input).value
        date_format = self.query_one("#invoice-date-format", Input).value
        cutoffs = generate_cutoff_list_from_docx(
            docx_path=file_path, date_fmt=date_format
        )
        self.app.transcriptor.save_cutoffs(cutoffs, year=year)
        self.app.notify("Cutoffs imported successfully!")


class Profile(Container):

    can_focus = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vim_bindings = [
            ("e", "Edit profile", "action_edit_profile"),
            ("r", "Refresh profile", "action_refresh_table"),
        ]

    def compose(self) -> ComposeResult:
        yield Label("Profile", classes="title")
        yield Static(id="profile-display")
        with Container(id="profile-controls", classes="panel-controls"):
            with Horizontal(classes="button-bar"):
                yield Button("Edit Profile", id="edit-profile")
                yield Button("Refresh", id="profile-refresh")

    def on_mount(self):
        self.refresh_table()

    def refresh_table(self):
        """Load current profile for display"""
        profile_display = self.query_one("#profile-display", Static)
        profile = self.app.transcriptor.profile
        display_text = f"""
Name: {profile.name}
Area: {profile.area}
Country: {profile.country}
        """
        profile_display.update(display_text)

    def action_refresh_table(self):
        self.refresh_table()

    def action_edit_profile(self):
        def check_edit(confirm):
            if confirm:
                self.refresh_table()

        profile_dict = self.app.transcriptor.profile.__dict__.copy()
        self.app.push_screen(ProfileEditScreen(profile_dict), check_edit)

    @on(Button.Pressed, "#edit-profile")
    def on_edit_profile_button(self):
        self.action_edit_profile()

    @on(Button.Pressed, "#profile-refresh")
    def on_profile_refresh(self):
        self.refresh_table()


class ProfileEditScreen(BaseEditScreen):
    def __init__(self, profile_data: Dict):
        super().__init__(profile_data, "Edit Profile")

    def get_container_id(self) -> str:
        return "profile-edit"

    def get_form_id(self) -> str:
        return "profile-form-container"

    def get_fields(self):
        yield Label("Name:")
        yield Input(value=self.data.get("name", ""), id="profile-name")
        yield Label("Area:")
        yield Input(value=self.data.get("area", ""), id="profile-area")
        yield Label("Country:")
        yield Input(value=self.data.get("country", ""), id="profile-country")

    def collect_values(self) -> Dict | None:
        return {
            "name": self.query_one("#profile-name", Input).value,
            "area": self.query_one("#profile-area", Input).value,
            "country": self.query_one("#profile-country", Input).value,
        }

    def perform_update(self, values: Dict):
        profile = self.app.transcriptor.profile
        profile.name = values["name"]
        profile.area = values["area"]
        profile.country = values["country"]
        self.app.transcriptor.save_profile()
        self.app.notify("Profile updated successfully!")


class ConfigurationScreen(ModalScreen):
    """Screen for editing configuration"""

    def compose(self) -> ComposeResult:
        with Container(id="config-edit"):
            yield Label("Edit Configuration", classes="config-title")

            with Vertical():
                yield Label("Base Directory:")
                yield Input(
                    value=self.app.transcriptor.config.base_dir, id="base_dir"
                )

                yield Label("Date Format:")
                yield Input(
                    value=self.app.transcriptor.config.date_format,
                    id="date_format",
                )

                yield Label("Invoice Theme:")
                # Fix: Import invoice_template_themes at the top
                themes = invoice_template_themes()
                select = Select(
                    [(theme, theme) for theme in themes],
                    id="invoice_theme",
                    value=self.app.transcriptor.config.invoice_theme,
                )
                yield select

                config = self.app.transcriptor.config
                currencies = sorted(
                    set(CURRENCY_SYMBOLS.keys())
                    | {config.display_currency, config.invoice_currency}
                )
                yield Label("Display Currency:")
                yield Select(
                    [(code, code) for code in currencies],
                    id="display_currency",
                    value=config.display_currency,
                )

                yield Label("Invoice Currency:")
                yield Select(
                    [(code, code) for code in currencies],
                    id="invoice_currency",
                    value=config.invoice_currency,
                )

                yield Label("Manual Conversion Rate (0 = auto):")
                yield Input(
                    value=str(config.conversion_rate),
                    id="conversion_rate",
                )

            with Horizontal(id="edit-buttons"):
                yield Button("Save", variant="primary", id="save-config")
                yield Button("Cancel", variant="default", id="cancel-config")

    @on(Button.Pressed, "#save-config")
    def save_config(self):
        base_dir = self.query_one("#base_dir", Input).value
        date_format = self.query_one("#date_format", Input).value
        invoice_theme_select = self.query_one("#invoice_theme", Select)
        invoice_theme = (
            invoice_theme_select.value
            if invoice_theme_select.value
            else "default"
        )
        display_currency = self.query_one("#display_currency", Select).value
        invoice_currency = self.query_one("#invoice_currency", Select).value
        conversion_rate = self.query_one("#conversion_rate", Input).value

        # Update config
        self.app.transcriptor.config.base_dir = base_dir
        self.app.transcriptor.config.date_format = date_format
        self.app.transcriptor.config.invoice_theme = invoice_theme
        self.app.transcriptor.config.display_currency = (
            display_currency or "USD"
        )
        self.app.transcriptor.config.invoice_currency = (
            invoice_currency or "USD"
        )
        try:
            self.app.transcriptor.config.conversion_rate = float(
                conversion_rate or 0
            )
        except ValueError:
            self.app.transcriptor.config.conversion_rate = 0.0

        # Save to file
        self.app.transcriptor.save_config()
        self.app.notify("Configuration saved successfully!")
        self.dismiss(True)
        # Refresh config display

    @on(Button.Pressed, "#cancel-config")
    def cancel_config(self):
        self.dismiss(True)


class Configuration(Container):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vim_bindings = [
            ("e", "Edit configuration", "action_edit_config"),
            ("r", "Refresh cutoffs", "action_refresh_table"),
        ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="config-container"):
            yield Label("Configuration & Settings", classes="title")
            yield Static(id="config-display")
            with Horizontal(classes="button-bar"):
                yield Button("Edit Config", id="edit-config")

            yield Label("Data Management", classes="title")
            with Horizontal(classes="button-bar"):
                yield Button("Backup Database", id="backup-db")
                yield Button("Restore Database", id="restore-db")
                yield Button("Purge Job Files", id="purge-jobs")
                yield Button("About", id="about-app")

    def on_mount(self):
        self.refresh_table()

    def get_vim_bindings(self) -> List[tuple[str, str]]:
        return [(key, desc) for key, desc, _ in self._vim_bindings]

    def handle_vim_key(self, key: str) -> bool:
        for k, _, method_name in self._vim_bindings:
            if key == k:
                method = getattr(self, method_name, None)
                if method:
                    method()
                    return True
        return False

    def refresh_table(self):
        """Load current configuration for display"""
        config_display = self.query_one("#config-display", Static)
        config = self.app.transcriptor.config
        display_text = f"""
Base Directory: {config.base_dir}
Date Format: {config.date_format}
Invoice Theme: {config.invoice_theme}
Display Currency: {config.display_currency}
Invoice Currency: {config.invoice_currency}
Conversion Rate: {config.conversion_rate}
        """
        config_display.update(display_text)

    def action_edit_config(self):
        def check_edit(confirm):
            if confirm:
                self.refresh_table()

        self.app.push_screen(ConfigurationScreen(), check_edit)

    @on(Button.Pressed, "#edit-config")
    def on_edit_config_button(self):
        self.action_edit_config()

    def action_refresh_table(self):
        self.refresh_table()

    @on(Button.Pressed, "#backup-db")
    def backup_database(self):
        try:
            path = self.app.transcriptor.backup.create_backup()
            self.app.notify(f"Backup created at {path}")
        except Exception as e:
            self.app.notify(f"Backup failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#restore-db")
    def restore_database(self):
        self.app.push_screen(RestoreScreen())

    @on(Button.Pressed, "#purge-jobs")
    def purge_jobs(self):
        self.app.push_screen(PurgeScreen())

    @on(Button.Pressed, "#about-app")
    def about_app(self):
        self.app.push_screen(AboutScreen())


class RestoreScreen(ModalScreen):
    """Screen for restoring database from backup"""

    def compose(self) -> ComposeResult:
        with Container(id="restore-screen"):
            yield Label("Restore Database", classes="restore-title")
            yield Label(
                "Select a backup to restore:", classes="restore-label"
            )
            yield Select([], id="backup-select", prompt="Select backup")
            with Horizontal(id="restore-buttons"):
                yield Button(
                    "Restore", variant="primary", id="confirm-restore"
                )
                yield Button("Cancel", variant="default", id="cancel-restore")

    def on_mount(self):
        backups = self.app.transcriptor.backup.list_backups()
        options = [(b.name, str(b)) for b in backups]
        self.query_one("#backup-select", Select).set_options(options)

    @on(Button.Pressed, "#confirm-restore")
    def confirm_restore(self):
        backup_path = self.query_one("#backup-select", Select).value
        if not backup_path:
            self.app.notify("Please select a backup.", severity="error")
            return

        try:
            self.app.transcriptor.backup.restore_backup(Path(backup_path))
            self.app.notify("Database restored successfully!")
            self.dismiss()
        except Exception as e:
            self.app.notify(f"Restore failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#cancel-restore")
    def cancel_restore(self):
        self.dismiss()


class PurgeScreen(ModalScreen):
    """Screen for purging job files"""

    def compose(self) -> ComposeResult:
        with Container(id="purge-screen"):
            yield Label("Purge Job Files", classes="purge-title")
            yield Label(
                "Delete media files for jobs matching:", classes="purge-label"
            )

            with Vertical():
                yield Label("Status:")
                yield Select(
                    [("Done", "Done"), ("Pending", "Pending")],
                    value="Done",
                    id="purge-status",
                )
                yield Label("Created Before (YYYY-MM-DD):")
                yield Input(
                    placeholder="Optional: 2023-01-01", id="purge-date"
                )

            with Horizontal(id="purge-buttons"):
                yield Button("Purge", variant="error", id="confirm-purge")
                yield Button("Cancel", variant="default", id="cancel-purge")

    @on(Button.Pressed, "#confirm-purge")
    def confirm_purge(self):
        status = self.query_one("#purge-status", Select).value
        date_limit = self.query_one("#purge-date", Input).value

        conditions = {}
        if status:
            conditions["status"] = [("=", status)]

        # This part is simplified. In a real scenario, we'd need to parse the date
        # and add it to conditions properly, potentially involving complex query logic
        # if the API supports it.
        # For now, let's just use status as the primary filter + date if provided via where clause construction.

        where_clauses = []
        if status:
            where_clauses.append(f"status='{status}'")
        if date_limit:
            where_clauses.append(f"date_received<'{date_limit}'")

        conditions = parse_conditions(where_clauses)

        jobs = self.app.transcriptor.api.get_jobs(conditions=conditions)

        if not jobs:
            self.app.notify(
                "No jobs found matching criteria.", severity="warning"
            )
            return

        def final_confirm(confirm):
            if confirm:
                try:
                    self.app.transcriptor.purge_job_files(jobs)
                    self.app.notify(f"Purged files for {len(jobs)} jobs.")
                    self.dismiss()
                except Exception as e:
                    self.app.notify(
                        f"Purge failed: {str(e)}", severity="error"
                    )

        self.app.push_screen(
            ConfirmDelete("files for these jobs"), final_confirm
        )

    @on(Button.Pressed, "#cancel-purge")
    def cancel_purge(self):
        self.dismiss()


class AboutScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="about-screen"):
            yield Label("About Transcriptor", classes="about-title")
            yield Label(
                f"Version: {self.app.transcriptor.version}",
                classes="about-text",
            )
            yield Label(
                "A CLI/TUI tool for managing transcription jobs.",
                classes="about-text",
            )

            with Horizontal(id="about-buttons"):
                yield Button("Close", variant="primary", id="close-about")

    @on(Button.Pressed, "#close-about")
    def close_about(self):
        self.dismiss()


class ConfirmDelete(ModalScreen[bool]):
    def __init__(self, item_type):
        super().__init__()
        self.item_type = item_type

    def compose(self):
        with Container(id="confirm-delete"):
            with Horizontal(id="confirm-delete-buttons"):
                yield Label(
                    "Are you sure you want to delete this item?",
                    classes="confirm-title",
                )
                yield Button(
                    "Yes", variant="primary", id="confirm-delete-yes"
                )
                yield Button("No", variant="default", id="confirm-delete-no")

    def on_mount(self):
        self.query_one("#confirm-delete-no")

    @on(Button.Pressed, "#confirm-delete-yes")
    def confirm_delete(self):
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-delete-no")
    def cancel_delete(self):
        self.dismiss(False)

    def key_escape(self):
        self.dismiss(False)


class VimHelpScreen(ModalScreen):
    """Display available vim keybindings."""

    def compose(self) -> ComposeResult:
        with Container(id="vim-help"):
            yield Label("Vim Mode Keybindings", classes="help-title")
            with VerticalScroll(id="help-content"):
                yield Markdown(self._get_help_text())
            with Horizontal(id="help-buttons"):
                yield Button("Close", variant="primary", id="close-help")

    def _get_help_text(self) -> str:
        # Determine active tab to show context-specific bindings
        active_id = self.app.query_one(TabbedContent).active
        pane_name = {
            "dashboard": "Dashboard",
            "all-jobs": "All Jobs",
            "clients": "Clients",
            "rates": "Rates",
            "profile": "Profile",
            "invoicing": "Invoicing",
            "config": "Configuration",
        }.get(active_id, "Current Pane")

        help_text = f"""# Vim Mode Help

## Global (always available)
- `v`          : Toggle vim mode on/off
- `H` / `L`    : Switch to previous/next tab
- `?`          : Show this help

## Navigation (when focused on a table or scrollable area)
- `j` / `k`    : Move down/up (table rows or scroll)
- `g` / `G`    : Go to top/bottom
- `x`          : Toggle selection (tables with checkboxes)
- `o` / `Enter`: Open context menu for current item

## Actions in **{pane_name}**
"""
        # Add pane-specific actions
        if active_id in ("dashboard", "all-jobs"):
            help_text += """
- `a` : Add new job
- `e` : Edit selected job
- `t` : Transcribe selected job (submit/poll/fetch)
- `r` : Refresh table
- `i` : Generate invoice from selected (All Jobs only)
"""
        elif active_id == "clients":
            help_text += """
- `a` : Add new client
- `e` : Edit selected client
- `d` : Delete selected client
- `r` : Refresh table
"""
        elif active_id == "rates":
            help_text += """
- `e` : Edit selected rate
- `r` : Refresh table
"""
        elif active_id == "profile":
            help_text += """
- `e` : Edit profile
- `r` : Refresh
"""
        elif active_id == "invoicing":
            help_text += """
- `a` : Add cutoffs
- `r` : Refresh cutoffs table
"""
        elif active_id == "config":
            help_text += """
- `e` : Edit configuration
- `r` : Refresh
"""

        help_text += """

## In modal screens (edit, context menu, etc.)
- `Esc` : Cancel / close
- `Tab` : Move between fields
- `Enter`: Select / confirm
"""
        return help_text

    @on(Button.Pressed, "#close-help")
    def close(self):
        self.dismiss()


class VimFooter(Static):
    """Dynamic footer showing vim key bindings for the active pane."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vim_mode = False
        self.bindings: List[tuple[str, str]] = []

    def set_vim_mode(self, enabled: bool):
        self.vim_mode = enabled
        self.update_display()

    def set_bindings(self, bindings: List[tuple[str, str]]):
        self.bindings = bindings
        self.update_display()

    def update_display(self):
        if not self.vim_mode:
            self.update("Vim Mode: Disabled (press 'v' to enable)")
            return

        if not self.bindings:
            self.update("Vim Mode: Enabled (no actions available)")
            return

        # Format as "key: description  |  next key: description"
        parts = [f"{key}: {desc}" for key, desc in self.bindings]
        self.update("Vim Mode: " + "  |  ".join(parts))


class TranscriptorTUI(App):
    """An application with per-tab and toggleable bindings."""

    CSS_PATH = "tui.css"

    # Reactive attribute to control the Vim mode
    vim_mode: reactive[bool] = reactive(False)

    BINDINGS = [
        ("v", "toggle_vim_mode", "Toggle Vim Mode (V)"),
        ("H", "vim_tab_left", "Tab Left (H)"),
        ("L", "vim_tab_right", "Tab Right (L)"),
        ("?", "show_vim_help", "Vim Help"),
    ]

    def __init__(self):
        super().__init__()
        self.transcriptor = Transcriptor()

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="dashboard"):
            with TabPane("Dashboard", id="dashboard"):
                yield Dashboard(
                    id="dashboard-pane", classes="dashboard-container"
                )

            with TabPane("All Jobs", id="all-jobs"):
                yield JobsTable(
                    id="jobstable-pane", classes="dashboard-container"
                )

            with TabPane("Clients", id="clients"):
                yield Clients(id="clients-pane", classes="clients-container")

            with TabPane("Rates", id="rates"):
                yield Rates(id="rates-pane", classes="rates-container")

            with TabPane("Profile", id="profile"):
                yield Profile(id="profile-pane", classes="profile-container")

            with TabPane("Invoicing", id="invoicing"):
                yield Invoice(
                    id="invoicing-pane", classes="invoicing-container"
                )

            with TabPane("Configuration", id="config"):
                yield Configuration(
                    id="config-pane", classes="config-container"
                )
        yield VimFooter(id="vim-footer")

    def action_toggle_vim_mode(self) -> None:
        self.vim_mode = not self.vim_mode
        # Optionally focus the main content after toggling
        self.query_one(TabbedContent).focus()

    def watch_vim_mode(self, enabled: bool) -> None:
        """Update footer when vim mode changes."""
        footer = self.query_one("#vim-footer", VimFooter)
        footer.set_vim_mode(enabled)
        # Also update bindings (in case pane changed while vim was off)
        self.update_vim_footer()

    def update_vim_footer(self):
        """Refresh footer with current pane's bindings."""
        footer = self.query_one("#vim-footer", VimFooter)
        pane = self._get_active_pane()
        if pane and hasattr(pane, "get_vim_bindings"):
            bindings = pane.get_vim_bindings()
            footer.set_bindings(bindings)
        else:
            footer.set_bindings([])

    def action_show_vim_help(self):
        self.push_screen(VimHelpScreen())

    def action_vim_tab_left(self) -> None:
        self.screen.set_focus(None)
        self._switch_tab(-1)

    #
    def action_vim_tab_right(self) -> None:
        self.screen.set_focus(None)
        self._switch_tab(1)

    def on_key(self, event: events.Key) -> None:
        """Global vim key dispatcher."""
        # Only active when vim_mode is on and not in a modal screen
        if not self.vim_mode or isinstance(self.screen, ModalScreen):
            return

        key = event.key

        # Delegate to the active pane
        pane = self._get_active_pane()
        if pane and hasattr(pane, "handle_vim_key"):
            if pane.handle_vim_key(key):
                event.stop()
                # No need to return; event.stop already prevents further processing

    def _switch_tab(self, direction: int):
        """Switch to previous (-1) or next (+1) tab."""
        tab_content = self.query_one(TabbedContent)
        pane_ids = [pane.id for pane in tab_content.query(TabPane)]
        try:
            current_index = pane_ids.index(tab_content.active)
            new_index = (current_index + direction) % len(pane_ids)
            tab_content.active = pane_ids[new_index]
        except ValueError:
            self.bell()

    def _get_active_pane(self):
        """Return the widget of the currently active tab."""
        tab_content = self.query_one(TabbedContent)
        active_id = tab_content.active
        mapping = {
            "dashboard": "#dashboard-pane",
            "all-jobs": "#jobstable-pane",
            "clients": "#clients-pane",
            "rates": "#rates-pane",
            "profile": "#profile-pane",
            "invoicing": "#invoicing-pane",
            "config": "#config-pane",
        }
        if active_id in mapping:
            return self.query_one(mapping[active_id])
        return None

    @on(TabbedContent.TabActivated)
    def on_tabs_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Refresh and focus the newly activated pane."""
        pane_id = event.pane.id
        self.call_after_refresh(lambda: self._refresh_and_focus_pane(pane_id))
        self.call_after_refresh(self.update_vim_footer)

    def _refresh_and_focus_pane(self, pane_id: str) -> None:
        """Refresh the pane's data and give focus to its main widget."""
        pane = self._get_active_pane()
        if pane is None:
            return
        # if hasattr(pane, "refresh_table") and pane.id not in ["#dashboard-pane", "#jobstable-pane"]:
        # pane.refresh_table()
        # Try to focus the main table if it exists
        if hasattr(pane, "get_table"):
            pane.get_table().focus()
        else:
            pane.focus()


def main():
    app = TranscriptorTUI()
    app.run()


if __name__ == "__main__":
    main()
