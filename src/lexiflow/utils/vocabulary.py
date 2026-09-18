import re
from typing import Dict, List, Any

from ..config import settings


def process_metadata_to_vocabulary(metadata: Dict[str, Any]) -> List[str]:
    seen = set()
    result = []
    for value in metadata.values():
        if not value:
            continue
        tokens = tokenize_metadata_value(value)
        for token in tokens:
            normalized = token.title()
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result


def tokenize_metadata_value(value: str) -> List[str]:
    """
    Split a metadata string into words and abbreviations.
    Preserves common abbreviations like "p.a." as a single token.
    """
    if not value:
        return []
    value = value.replace("\n", " ").replace("\t", " ")
    words = value.split()
    tokens = []
    for word in words:
        if "." in word and any(c.isalpha() for c in word):
            cleaned = word.rstrip(",.;:!?")
            tokens.append(cleaned)
        else:
            parts = re.findall(r"[a-zA-Z\-\']+", word)
            tokens.extend(parts)
    tokens = [t for t in tokens if not any(c.isdigit() for c in t)]
    tokens = [t for t in tokens if any(c.isalpha() for c in t)]
    return tokens


def clean_vocabulary(phrase: str) -> str:
    """
    Remove characters not allowed by Rev.ai custom vocabulary.
    Allowed: U+0000-U+002F and U+003A-U+007F (control chars, space, punctuation, letters, symbols).
    Digits (0-9) are excluded.
    """
    # Keep only characters in the allowed ranges
    allowed_pattern = re.compile(r"[^\x00-\x2F\x3A-\x7F]")
    return allowed_pattern.sub("", phrase)


def filter_metadata_for_llm(metadata: Dict[str, Any]) -> Dict[str, str]:
    """
    Filter metadata to include only selected keys for LLM context.

    Args:
        metadata: Full metadata dictionary

    Returns:
        Filtered dictionary with only selected keys
    """
    # Get configured keys from settings
    keys_str = settings.NOTEBOOKLM_METADATA_KEYS
    selected_keys = [k.strip() for k in keys_str.split(",") if k.strip()]

    filtered = {}
    for key in selected_keys:
        if key in metadata:
            value = metadata[key]
            if value is not None:
                # Convert to string, handling both string and non-string values
                filtered[key] = str(value).strip()

    return filtered


def estimate_token_count(text: str) -> int:
    """
    Estimate token count for text (approximate: 1 token ≈ 4 characters).

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    # Simple estimation: 1 token ≈ 4 characters
    # This is a rough approximation for English text
    char_count = len(text)
    return max(1, char_count // 4)


def format_metadata_for_prompt(metadata: Dict[str, str]) -> str:
    """
    Format filtered metadata for inclusion in LLM prompt with token-aware truncation.

    Args:
        metadata: Filtered metadata dictionary

    Returns:
        Formatted metadata string for prompt
    """
    if not metadata:
        return ""

    # Format as key-value pairs
    lines = []
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")

    metadata_text = "\n".join(lines)

    # Check token limit
    max_tokens = settings.NOTEBOOKLM_MAX_METADATA_TOKENS
    current_tokens = estimate_token_count(metadata_text)

    if current_tokens <= max_tokens:
        # Within limit, return full metadata
        return f"METADATA CONTEXT:\n{metadata_text}\n"

    # Exceeds limit, need to truncate
    # Strategy: Include all keys but truncate values
    truncated_lines = []
    remaining_tokens = max_tokens

    # Reserve tokens for headers and formatting (approx 20 tokens)
    remaining_tokens -= 20

    # Calculate tokens per key (distribute evenly)
    keys = list(metadata.keys())
    tokens_per_key = max(1, remaining_tokens // len(keys))

    for key in keys:
        value = metadata[key]
        # Truncate value to fit within token budget
        max_chars = tokens_per_key * 4  # 4 chars per token
        if len(value) > max_chars:
            truncated_value = value[:max_chars] + "..."
        else:
            truncated_value = value

        truncated_lines.append(f"{key}: {truncated_value}")

    truncated_text = "\n".join(truncated_lines)
    return truncated_text
