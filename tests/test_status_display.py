from lexiflow.utils import format_status_badge


def test_done_is_success_styled():
    result = format_status_badge("Done")
    assert "[green]" in result
    assert "✓" in result
    assert "Done" in result


def test_pending_is_progress_styled():
    result = format_status_badge("Pending")
    assert "[yellow]" in result
    assert "Pending" in result


def test_in_progress_is_progress_styled():
    result = format_status_badge("in_progress")
    assert "[yellow]" in result
    assert "in_progress" in result


def test_failed_is_error_styled():
    result = format_status_badge("failed")
    assert "[red]" in result
    assert "✗" in result
    assert "failed" in result


def test_error_keyword_is_error_styled():
    result = format_status_badge("Rejected")
    assert "[red]" in result


def test_transcribed_is_success_styled():
    result = format_status_badge("transcribed")
    assert "[green]" in result


def test_none_status_shows_dim_placeholder():
    result = format_status_badge(None)
    assert "[dim]" in result
    assert "-" in result


def test_empty_string_status_shows_dim_placeholder():
    result = format_status_badge("")
    assert "[dim]" in result


def test_dash_placeholder_shows_dim():
    result = format_status_badge("-")
    assert "[dim]" in result


def test_unrecognized_status_falls_back_to_neutral_but_shows_text():
    """An arbitrary provider-specific status string we don't recognize
    should still display (never silently dropped), just neutrally
    styled instead of guessing a color."""
    result = format_status_badge("some_weird_provider_state")
    assert "[dim]" in result
    assert "some_weird_provider_state" in result


def test_custom_empty_text_is_used():
    result = format_status_badge(None, empty_text="n/a")
    assert "n/a" in result
