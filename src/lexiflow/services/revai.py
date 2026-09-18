import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from rev_ai import apiclient

from .base import TranscriptionService


class RevAIService(TranscriptionService):
    """Rev.ai transcription service (sync client wrapped in async)."""

    def __init__(
        self,
        api_key: str,
        max_jobs: int = 10,
    ):
        self.api_key = api_key
        self.sync_client = apiclient.RevAiAPIClient(self.api_key)
        self.max_jobs = max_jobs
        self.provider = "revai"

    async def submit_job(
        self, file_path: Path, additional_vocabulary: Optional[List[str]] = None
    ) -> str:
        # Prepare custom vocabularies only if additional_vocabulary is provided and non-empty
        kwargs = {
            "filename": str(file_path),
            "transcriber": "machine",
            "skip_diarization": False,
            "skip_punctuation": False,
            "filter_profanity": False,
            "remove_disfluencies": True,
            "skip_postprocessing": False,
            "remove_atmospherics": True,
            "diarization_type": "standard",
        }

        if additional_vocabulary:
            max_word_len = 34
            filtered = [w for w in additional_vocabulary if len(w) <= max_word_len]
            skipped = [w for w in additional_vocabulary if len(w) > max_word_len]
            if skipped:
                import logging

                logging.getLogger(__name__).warning(
                    "Skipping %d word(s) exceeding %d-char limit: %s",
                    len(skipped),
                    max_word_len,
                    skipped,
                )
            kwargs["custom_vocabularies"] = [{"phrases": filtered}]

        # Submit job in a thread to avoid blocking the event loop
        job = await asyncio.to_thread(self.sync_client.submit_job_local_file, **kwargs)
        return job.id

    async def get_transcript(
        self, job_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        transcript_text = await asyncio.to_thread(
            self.sync_client.get_transcript_text,
            job_id,
        )
        return transcript_text

    async def close(self) -> None:
        # No explicit close needed for Rev.ai client
        pass

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            job_details = await asyncio.to_thread(
                self.sync_client.get_job_details, job_id
            )
            return {
                "id": job_details.id,
                "status": job_details.status,
                "created_at": job_details.created_on,
            }
        except Exception:
            return None
