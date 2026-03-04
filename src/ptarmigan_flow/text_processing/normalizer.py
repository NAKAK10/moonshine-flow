"""Transcript text normalization helpers."""

from __future__ import annotations

import re

_JAPANESE_CHAR_CLASS = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆ヵヶー"
_JAPANESE_INNER_WHITESPACE_PATTERN = re.compile(
    rf"(?<=[{_JAPANESE_CHAR_CLASS}])(?:\s|\u3000)+(?=[{_JAPANESE_CHAR_CLASS}])"
)


def normalize_transcript_text(text: str) -> str:
    """Normalize transcript text for Japanese and mixed-language output."""
    normalized = text.strip()
    if not normalized:
        return ""
    return _JAPANESE_INNER_WHITESPACE_PATTERN.sub("", normalized)
