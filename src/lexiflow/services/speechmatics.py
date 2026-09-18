from pathlib import Path
from typing import List, Dict, Any, Optional

from speechmatics.batch import (
    AsyncClient,
    TranscriptionConfig,
    FormatType,
    OperatingPoint,
    TranscriptFilteringConfig,
)

from .base import TranscriptionService


class SpeechmaticsService(TranscriptionService):
    """Speechmatics batch transcription service."""

    def __init__(
        self,
        api_key: str,
        max_jobs: int = 10,
    ):
        self.api_key = api_key
        self.client = AsyncClient(api_key=self.api_key)
        self.max_jobs = max_jobs
        self.provider = "speechmatics"

    async def submit_job(
        self, file_path: Path, additional_vocabulary: Optional[List[str]] = None
    ) -> str:
        config = TranscriptionConfig(
            language="en",
            diarization="speaker",
            enable_entities=True,
            operating_point=OperatingPoint.STANDARD,
            punctuation_overrides={"permitted_marks": ["all"]},
            additional_vocab=additional_vocabulary,
            transcript_filtering_config=TranscriptFilteringConfig(
                remove_disfluencies=True,
                replacements=[
                    {"from": "gonna", "to": "going to"},
                    {"from": "wanna", "to": "want to"},
                    {"from": "gotta", "to": "got to"},
                    {"from": "alright", "to": "all right"},
                ],
            ),
        )

        job = await self.client.submit_job(str(file_path), transcription_config=config)
        return job.id

    async def get_transcript(
        self, job_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        result = await self.client.get_transcript(job_id, format_type=FormatType.JSON)
        return result.transcript_text

    async def close(self) -> None:
        await self.client.close()

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            job = await self.client.get_job_info(job_id)
            return {
                "id": job.id,
                "status": job.status,
                "created_at": job.created_at,
            }
        except Exception:
            return None
