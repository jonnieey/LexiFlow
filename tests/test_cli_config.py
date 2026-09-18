from lexiflow.cli import _mask_secret


def test_mask_secret_masks_long_api_key():
    assert _mask_secret("OPENAI_API_KEY", "sk-1234567890") == "sk-1*****7890"


def test_mask_secret_redacts_short_key():
    assert _mask_secret("REVAI_API_KEY", "short") == "[REDACTED]"


def test_mask_secret_redacts_empty_key():
    assert _mask_secret("SPEECHMATIX_API_KEY", "") == "[REDACTED]"


def test_mask_secret_leaves_non_key_values_untouched():
    assert _mask_secret("AI_MODEL", "gpt-4o-mini") == "gpt-4o-mini"
