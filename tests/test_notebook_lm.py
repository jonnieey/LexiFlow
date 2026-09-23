import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from notebooklm import ReportFormat

from lexiflow.services.notebook_lm import NotebookLMService


@pytest.fixture
def prompt_file(tmp_path: Path) -> Path:
    p = tmp_path / "prompt.txt"
    p.write_text("Transcribe this audio precisely.", encoding="utf-8")
    return p


@pytest.fixture
def service(prompt_file: Path) -> NotebookLMService:
    return NotebookLMService(
        storage_path="/tmp/notebooklm-storage",
        notebook_id="nb-123",
        prompt_file=prompt_file,
    )


def _mock_client(final_status_kwargs=None, downloaded_text="hello transcript"):
    client = MagicMock()
    status = MagicMock(task_id="task-1")
    final_status = MagicMock(**(final_status_kwargs or {"is_failed": False, "error": None}))

    client.artifacts.generate_report = AsyncMock(return_value=status)
    client.artifacts.wait_for_completion = AsyncMock(return_value=final_status)

    async def fake_download(notebook_id, output_path, artifact_id=None):
        Path(output_path).write_text(downloaded_text, encoding="utf-8")
        return output_path

    client.artifacts.download_report = AsyncMock(side_effect=fake_download)
    return client, status, final_status


def test_get_transcript_generates_report_with_custom_prompt(service):
    client, status, final_status = _mock_client()
    service.client = client

    result = asyncio.run(service.get_transcript("job-1"))

    client.artifacts.generate_report.assert_awaited_once_with(
        "nb-123",
        report_format=ReportFormat.CUSTOM,
        source_ids=["job-1"],
        custom_prompt="Transcribe this audio precisely.",
    )
    assert result == "hello transcript"


def test_get_transcript_waits_for_completion(service):
    client, status, final_status = _mock_client()
    service.client = client

    asyncio.run(service.get_transcript("job-1"))

    client.artifacts.wait_for_completion.assert_awaited_once_with("nb-123", "task-1")


def test_get_transcript_downloads_report_with_task_id(service):
    client, status, final_status = _mock_client()
    service.client = client

    asyncio.run(service.get_transcript("job-1"))

    client.artifacts.download_report.assert_awaited_once()
    call_args = client.artifacts.download_report.call_args
    assert call_args.args[0] == "nb-123"
    assert call_args.kwargs["artifact_id"] == "task-1"


def test_get_transcript_raises_when_generation_failed(service):
    client, status, final_status = _mock_client(
        final_status_kwargs={"is_failed": True, "error": "quota exceeded"}
    )
    service.client = client

    with pytest.raises(RuntimeError, match="quota exceeded"):
        asyncio.run(service.get_transcript("job-1"))

    client.artifacts.download_report.assert_not_awaited()


def test_get_transcript_includes_metadata_in_custom_prompt(service):
    client, status, final_status = _mock_client()
    service.client = client

    metadata = {"WITNESS_NAME": "Jane Doe", "CASE_NUMBER": "12345"}
    asyncio.run(service.get_transcript("job-1", metadata=metadata))

    call_kwargs = client.artifacts.generate_report.call_args.kwargs
    prompt = call_kwargs["custom_prompt"]
    assert "Transcribe this audio precisely." in prompt
    assert "Jane Doe" in prompt or "jane doe" in prompt.lower()
