from unittest.mock import patch

from lexiflow.utils.vocabulary import (
    clean_vocabulary,
    estimate_token_count,
    filter_metadata_for_llm,
    format_metadata_for_prompt,
    process_metadata_to_vocabulary,
    tokenize_metadata_value,
)


def test_tokenize_metadata_value_splits_words():
    assert tokenize_metadata_value("John Smith") == ["John", "Smith"]


def test_tokenize_metadata_value_preserves_abbreviations():
    # Trailing terminal punctuation is stripped, but internal dots in an
    # abbreviation like "p.a." survive as a single token, not split apart.
    assert "p.a" in tokenize_metadata_value("Smith & Jones p.a.")


def test_tokenize_metadata_value_drops_pure_digit_tokens():
    tokens = tokenize_metadata_value("Case 2024-CV-001")
    assert "2024" not in tokens
    assert "Case" in tokens


def test_tokenize_metadata_value_empty():
    assert tokenize_metadata_value("") == []
    assert tokenize_metadata_value(None) == []


def test_process_metadata_to_vocabulary_dedupes_and_title_cases():
    metadata = {"WITNESS_NAME": "john smith", "COURT_REPORTER_NAME": "John Smith"}
    result = process_metadata_to_vocabulary(metadata)
    assert result.count("John") == 1
    assert result.count("Smith") == 1


def test_process_metadata_to_vocabulary_skips_empty_values():
    metadata = {"A": "", "B": None, "C": "Valid Name"}
    result = process_metadata_to_vocabulary(metadata)
    assert result == ["Valid", "Name"]


def test_clean_vocabulary_strips_digits():
    assert clean_vocabulary("abc123def") == "abcdef"


def test_clean_vocabulary_keeps_allowed_punctuation():
    assert clean_vocabulary("O'Brien-Smith") == "O'Brien-Smith"


def test_filter_metadata_for_llm_selects_configured_keys():
    metadata = {"WITNESS_NAME": "Jane Doe", "IRRELEVANT_KEY": "noise"}
    with patch(
        "lexiflow.utils.vocabulary.settings.NOTEBOOKLM_METADATA_KEYS",
        "WITNESS_NAME,CASE_NUMBER",
    ):
        result = filter_metadata_for_llm(metadata)
    assert result == {"WITNESS_NAME": "Jane Doe"}


def test_filter_metadata_for_llm_skips_none_values():
    metadata = {"WITNESS_NAME": None}
    with patch(
        "lexiflow.utils.vocabulary.settings.NOTEBOOKLM_METADATA_KEYS",
        "WITNESS_NAME",
    ):
        result = filter_metadata_for_llm(metadata)
    assert result == {}


def test_estimate_token_count_approximation():
    assert estimate_token_count("a" * 40) == 10


def test_estimate_token_count_minimum_one():
    assert estimate_token_count("") == 1


def test_format_metadata_for_prompt_empty():
    assert format_metadata_for_prompt({}) == ""


def test_format_metadata_for_prompt_within_limit():
    with patch(
        "lexiflow.utils.vocabulary.settings.NOTEBOOKLM_MAX_METADATA_TOKENS", 530
    ):
        result = format_metadata_for_prompt({"WITNESS_NAME": "Jane Doe"})
    assert "METADATA CONTEXT:" in result
    assert "WITNESS_NAME: Jane Doe" in result


def test_format_metadata_for_prompt_truncates_when_over_limit():
    long_value = "x" * 1000
    with patch("lexiflow.utils.vocabulary.settings.NOTEBOOKLM_MAX_METADATA_TOKENS", 10):
        result = format_metadata_for_prompt({"KEY": long_value})
    assert "METADATA CONTEXT:" not in result
    assert "..." in result
