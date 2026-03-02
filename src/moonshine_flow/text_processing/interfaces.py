"""Text post-processing interfaces."""

from __future__ import annotations

from typing import Protocol


class TextPostProcessor(Protocol):
    """Apply post-processing to transcript text."""

    def apply(self, text: str) -> str:
        """Return processed text."""


class NoopTextPostProcessor:
    """No-op post processor."""

    def apply(self, text: str) -> str:
        return text


class ChainedTextPostProcessor:
    """Apply multiple post-processors in order."""

    def __init__(self, processors: list[TextPostProcessor]) -> None:
        self._processors = processors

    def apply(self, text: str) -> str:
        processed = text
        for processor in self._processors:
            processed = processor.apply(processed)
        return processed
