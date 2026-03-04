"""Shared interfaces for STT backends."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

import numpy as np


class SpeechToTextBackend(Protocol):
    """Speech-to-text backend protocol."""

    def preflight_model(self) -> str:
        """Ensure backend/model is ready and return backend identifier."""

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Return a final transcript for one audio segment."""

    def transcribe_stream(self, audio: np.ndarray, sample_rate: int) -> Iterator[str]:
        """Yield cumulative transcript updates for one audio segment."""

    def supports_realtime_input(self) -> bool:
        """Return whether this backend/model supports true live input while recording."""

    def maybe_release_idle_resources(self) -> None:
        """Release optional backend resources when daemon detects an idle period."""

    def runtime_status(self) -> str:
        """Return runtime state text for operator-facing logs."""

    def backend_summary(self) -> str:
        """Return a short backend summary for diagnostics."""

    def close(self) -> None:
        """Release backend resources."""
