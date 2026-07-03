"""Text normalization utilities."""

from __future__ import annotations

import re


def count_words(text: str) -> int:
    """Count approximate word count in text."""
    return len(re.findall(r"\b\w+\b", text))


def truncate_text(text: str, max_chars: int, suffix: str = "...") -> str:
    """Truncate text to a maximum character count, preserving word boundaries."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated + suffix


def detect_language(text: str) -> str:
    """Simple heuristic language detection based on character set.

    For production use, consider integrating langdetect or fasttext.
    """
    # Count CJK characters
    cjk_pattern = re.compile(r"[一-鿿぀-ゟ゠-ヿ가-힯]")
    cjk_chars = len(cjk_pattern.findall(text))

    if cjk_chars > len(text) * 0.1:
        return "zh"  # Chinese (simplified heuristic)

    # Default to English
    return "en"
