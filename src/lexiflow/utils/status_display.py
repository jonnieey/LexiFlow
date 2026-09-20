"""Status -> color+icon badge formatting for DataTable cells.

Job status is a fixed Pending/Done binary, but transcription_status is
whatever a provider returns on poll (in_progress, transcribed, or
arbitrary provider-specific strings) so classification is keyword-based
rather than an exact map.

DataTable cells render plain strings through Rich's own
Text.from_markup, not Textual's CSS variable system, so this uses
Rich's named colors directly (green/yellow/red/dim) rather than the
$status-* tokens defined in tui.css -- those tokens exist for
CSS-styled widgets elsewhere; markup strings can't reference them.
"""

_ERROR_KEYWORDS = ("error", "fail", "reject", "cancel")
_SUCCESS_KEYWORDS = ("done", "completed", "transcribed", "success", "finished")
_PROGRESS_KEYWORDS = (
    "pending",
    "progress",
    "running",
    "queued",
    "processing",
    "submitted",
)


def classify_status(status: str) -> str:
    """Classify a status string into 'success', 'error', 'in_progress',
    or 'unknown' via case-insensitive keyword matching."""
    lowered = status.lower()
    if any(keyword in lowered for keyword in _ERROR_KEYWORDS):
        return "error"
    if any(keyword in lowered for keyword in _SUCCESS_KEYWORDS):
        return "success"
    if any(keyword in lowered for keyword in _PROGRESS_KEYWORDS):
        return "in_progress"
    return "unknown"


_BADGE_STYLE = {
    "success": ("green", "✓"),
    "in_progress": ("yellow", "…"),
    "error": ("red", "✗"),
    "unknown": ("dim", "•"),
}


def format_status_badge(status: str | None, empty_text: str = "-") -> str:
    """Return a Rich-markup badge (color + icon + text) for a status
    value, for use as a DataTable cell. None/empty/'-' render as a dim
    placeholder instead of being classified."""
    if not status or status == "-":
        return f"[dim]{empty_text}[/dim]"

    color, icon = _BADGE_STYLE[classify_status(status)]
    return f"[{color}]{icon} {status}[/{color}]"
