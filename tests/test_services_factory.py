from unittest.mock import patch

import pytest

from lexiflow.services.factory import get_service
from lexiflow.services.speechmatics import SpeechmaticsService
from lexiflow.services.revai import RevAIService
from lexiflow.services.notebook_lm import NotebookLMService


def test_get_service_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_service("unknown-provider")


def test_get_service_speechmatics_missing_key_raises():
    with patch("lexiflow.services.factory.settings") as mock_settings:
        mock_settings.SPEECHMATIX_API_KEY = None
        with pytest.raises(ValueError, match="SPEECHMATIX_API_KEY"):
            get_service("speechmatics")


def test_get_service_revai_missing_key_raises():
    with patch("lexiflow.services.factory.settings") as mock_settings:
        mock_settings.REVAI_API_KEY = None
        with pytest.raises(ValueError, match="REVAI_API_KEY"):
            get_service("revai")


def test_get_service_speechmatics_uses_provided_key():
    with patch("lexiflow.services.factory.SpeechmaticsService") as mock_cls:
        get_service("speechmatics", api_key="explicit-key")
        mock_cls.assert_called_once_with("explicit-key")


def test_get_service_revai_uses_provided_key():
    with patch("lexiflow.services.factory.RevAIService") as mock_cls:
        get_service("revai", api_key="explicit-key")
        mock_cls.assert_called_once_with("explicit-key")


def test_get_service_provider_name_is_case_insensitive():
    with patch("lexiflow.services.factory.SpeechmaticsService") as mock_cls:
        get_service("SpeechMatics", api_key="k")
        mock_cls.assert_called_once()


def test_get_service_returns_correct_type_with_mocked_clients():
    with patch("lexiflow.services.speechmatics.AsyncClient"):
        service = get_service("speechmatics", api_key="k")
        assert isinstance(service, SpeechmaticsService)

    with patch("lexiflow.services.revai.apiclient.RevAiAPIClient"):
        service = get_service("revai", api_key="k")
        assert isinstance(service, RevAIService)
