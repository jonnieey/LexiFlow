from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional


class TranscriptionService(ABC):
    """Abstract base class for transcription services."""

    @abstractmethod
    async def submit_job(
        self, file_path: Path, additional_vocabulary: Optional[List[str]] = None
    ) -> str:
        """Submit a file for transcription and return the provider's job ID."""
        pass

    @abstractmethod
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return job details including 'status' field (e.g., 'transcribed', 'failed', 'in_progress')."""
        pass

    @abstractmethod
    async def get_transcript(
        self, job_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Retrieve transcript text for a given job ID."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass
