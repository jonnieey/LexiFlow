from typing import Optional
from .base import TranscriptionService
from .speechmatics import SpeechmaticsService
from .revai import RevAIService
from .notebook_lm import NotebookLMService
from ..config import settings


def get_service(provider: str, api_key: Optional[str] = None) -> TranscriptionService:
    """
    Factory to get a transcription service instance.
    provider: 'speechmatics' or 'revai'
    api_key: if not provided, reads from environment variable SPEECHMATIX_API_KEY or REVAI_API_KEY.
    """
    provider = provider.lower()
    if provider == "speechmatics":
        api_key = api_key or settings.SPEECHMATIX_API_KEY
        if not api_key:
            raise ValueError("SPEECHMATIX_API_KEY not set and not provided")
        return SpeechmaticsService(api_key)
    elif provider == "revai":
        api_key = api_key or settings.REVAI_API_KEY
        if not api_key:
            raise ValueError("REVAI_API_KEY not set and not provided")
        return RevAIService(api_key)
    elif provider == "notebooklm":
        return NotebookLMService()
    else:
        raise ValueError(
            f"Unknown provider: {provider}. Choose 'speechmatics' or 'revai'"
        )
