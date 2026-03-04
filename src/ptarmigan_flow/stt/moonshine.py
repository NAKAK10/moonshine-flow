"""Moonshine STT backend wrapper."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from ptarmigan_flow.stt.base import SpeechToTextBackend
from ptarmigan_flow.transcriber import MoonshineTranscriber


class MoonshineSTTBackend(MoonshineTranscriber, SpeechToTextBackend):
    """Moonshine backend with a streaming-compatible interface."""

    def transcribe_stream(self, audio: np.ndarray, sample_rate: int) -> Iterator[str]:
        text = self.transcribe(audio, sample_rate)
        if text:
            yield text

    def supports_realtime_input(self) -> bool:
        return False

    def maybe_release_idle_resources(self) -> None:
        return None

    def runtime_status(self) -> str:
        return f"🚀 Backend ready (no external server): {self.backend_summary()}"
