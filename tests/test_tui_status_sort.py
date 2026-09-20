"""Status column sort-key regression test.

Wiring format_status_badge() into the status/transcription DataTable
columns wraps the plain text in Rich markup + an icon prefix
(e.g. "Done" -> "[green]✓ Done[/green]"). Sorting must still behave
exactly as it did on the plain text -- clicking a column header is a
presentation affordance, not something the redesign is meant to change
the semantics of.
"""

from lexiflow.tui import _dt_status_sort_key


def test_strips_markup_and_icon_prefix():
    assert _dt_status_sort_key("[green]✓ Done[/green]") == "done"
    assert _dt_status_sort_key("[yellow]… Pending[/yellow]") == "pending"
    assert _dt_status_sort_key("[red]✗ failed[/red]") == "failed"


def test_dash_placeholder_sorts_as_empty():
    assert _dt_status_sort_key("[dim]-[/dim]") == "-"


def test_plain_text_without_markup_still_works():
    assert _dt_status_sort_key("Done") == "done"


def test_none_is_empty_string():
    assert _dt_status_sort_key(None) == ""
