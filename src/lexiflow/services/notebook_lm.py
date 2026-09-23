import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from notebooklm import NotebookLMClient, ReportFormat, SourceStatus, RPCError

from .base import TranscriptionService
from ..config import settings

logger = logging.getLogger(__name__)


class NotebookLMService(TranscriptionService):
    """NotebookLM service that uploads a file and asks a prompt to get a transcript."""

    MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB

    def __init__(
        self,
        storage_path: Optional[str] = None,
        notebook_id: Optional[str] = None,
        prompt_file: Optional[Path] = None,
        max_jobs: int = 10,
    ):
        self.storage_path = storage_path or settings.NOTEBOOKLM_STORAGE_PATH
        self.notebook_id = notebook_id or settings.NOTEBOOKLM_NOTEBOOK_ID
        self.prompt_file = prompt_file or settings.NOTEBOOKLM_PROMPT_FILE

        if not self.notebook_id:
            raise ValueError("NotebookLM notebook ID not set (NOTEBOOKLM_NOTEBOOK_ID)")
        if not self.prompt_file:
            raise ValueError("NotebookLM prompt file not set (NOTEBOOKLM_PROMPT_FILE)")
        self.prompt_file = Path(self.prompt_file)
        if not self.prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_file}")

        self.max_jobs = max_jobs
        self.client: Optional[NotebookLMClient] = None
        self._entered = False
        self.provider = "notebooklm"

    async def _ensure_client(self) -> None:
        """Create and enter the NotebookLM client if not already done."""
        if self.client is None:
            self.client = await NotebookLMClient.from_storage(self.storage_path)
            await self.client.__aenter__()
            self._entered = True

    async def submit_job(
        self, file_path: Path, additional_vocabulary: Optional[List[str]] = None
    ) -> str:
        """Upload file as a source and return source ID."""
        # Ensure audio source is <200MB, otherwise notify to reduce file size
        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE_BYTES:
            mb_size = file_size / (1024 * 1024)
            limit_mb = self.MAX_FILE_SIZE_BYTES / (1024 * 1024)
            raise ValueError(
                f"Audio file size ({mb_size:.1f} MB) exceeds limit of {limit_mb:.0f} MB. "
                "Please reduce file size before uploading."
            )
        await self._ensure_client()
        try:
            source = await self.client.sources.add_file(
                self.notebook_id, str(file_path)
            )
        except RPCError as e:
            # If RPC fails, we can't proceed
            raise RuntimeError(f"Failed to upload file: {e}")

        return source.id

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Check source status and return dict with 'status' key."""
        await self._ensure_client()
        try:
            source = await self.client.sources.get(self.notebook_id, job_id)

            status_map = {
                SourceStatus.PROCESSING: "in_progress",
                SourceStatus.PREPARING: "in_progress",
                SourceStatus.READY: "transcribed",
                SourceStatus.ERROR: "failed",
            }
            # source.status is an int, we need to convert
            status_str = status_map.get(source.status, "in_progress")

            return {
                "id": source.id,
                "status": status_str,
                "created_at": getattr(source, "created_at", None),
            }
        except RPCError:
            return None

    async def get_transcript(
        self, job_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Ask the notebook using the prompt and return the answer."""
        await self._ensure_client()

        # Read prompt from file
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Enhance prompt with metadata if provided
        if metadata:
            from ..utils import filter_metadata_for_llm, format_metadata_for_prompt

            filtered_metadata = filter_metadata_for_llm(metadata)
            metadata_context = format_metadata_for_prompt(filtered_metadata)
            metadata_prompt = f"""Preferred Vocabulary:
- The following words/phrases are expected in the audio.
- Use them when they match what is spoken.

Vocabulary List:
{metadata_context.title()}
"""
            prompt = f"\n{prompt}\n{metadata_prompt}"

        logger.debug("NotebookLM prompt (includes case metadata): %s", prompt)
        try:
            status = await self.client.artifacts.generate_report(
                self.notebook_id,
                report_format=ReportFormat.CUSTOM,
                source_ids=[job_id],
                custom_prompt=prompt,
            )
            final_status = await self.client.artifacts.wait_for_completion(
                self.notebook_id, status.task_id
            )
            if final_status.is_failed:
                raise RuntimeError(
                    f"Failed to get transcript: {final_status.error}"
                )

            with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                await self.client.artifacts.download_report(
                    self.notebook_id, tmp_path, artifact_id=status.task_id
                )
                return Path(tmp_path).read_text(encoding="utf-8")
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except RPCError as e:
            raise RuntimeError(f"Failed to get transcript: {e}")

    async def close(self) -> None:
        """Close the NotebookLM client if it was opened."""
        if self.client and self._entered:
            await self.client.__aexit__(None, None, None)
        self.client = None
        self._entered = False
