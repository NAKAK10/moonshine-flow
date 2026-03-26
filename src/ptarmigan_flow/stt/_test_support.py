"""Internal test helpers for isolated STT backend tests."""

from __future__ import annotations

import os
import time

import numpy as np

from ptarmigan_flow.config import AppConfig
from ptarmigan_flow.ports.runtime import BackendWarmState, format_backend_warm_state
from ptarmigan_flow.stt.base import SpeechToTextBackend


class _BaseTestBackend(SpeechToTextBackend):
    def __init__(self, *, mode: str) -> None:
        self._mode = mode
        self._ready = False
        self._last_activity_at_monotonic: float | None = None

    def preflight_model(self) -> str:
        self._ready = True
        return f"test-{self._mode}"

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        self._ready = True
        total_samples = int(audio.shape[0]) if audio.ndim else 0
        duration_seconds = total_samples / float(sample_rate) if sample_rate > 0 else 0.0
        if duration_seconds >= 0.5:
            if self._mode == "timeout":
                time.sleep(0.5)
            if self._mode == "crash":
                os._exit(17)
        self._last_activity_at_monotonic = time.monotonic()
        return f"samples={total_samples}"

    def transcribe_stream(self, audio: np.ndarray, sample_rate: int):
        text = self.transcribe(audio, sample_rate)
        if text:
            yield text

    def warm_state(self) -> BackendWarmState:
        return BackendWarmState(
            resource_mode="in_process",
            ready=self._ready,
            warmed=self._last_activity_at_monotonic is not None,
            warmup_running=False,
            supports_keydown_warmup=False,
            last_activity_at_monotonic=self._last_activity_at_monotonic,
        )

    def warmup_for_low_latency(self) -> None:
        self._ready = True
        self._last_activity_at_monotonic = time.monotonic()

    def supports_realtime_input(self) -> bool:
        return False

    def maybe_release_idle_resources(self) -> None:
        return None

    def runtime_status(self) -> str:
        return (
            "🚀 Backend ready (test child): "
            f"{self.backend_summary()} {format_backend_warm_state(self.warm_state())}"
        )

    def backend_summary(self) -> str:
        return f"backend=test-{self._mode}"

    def close(self) -> None:
        self._ready = False
        self._last_activity_at_monotonic = None


def build_echo_backend(config: AppConfig) -> SpeechToTextBackend:
    del config
    return _BaseTestBackend(mode="echo")


def build_timeout_backend(config: AppConfig) -> SpeechToTextBackend:
    del config
    return _BaseTestBackend(mode="timeout")


def build_crash_backend(config: AppConfig) -> SpeechToTextBackend:
    del config
    return _BaseTestBackend(mode="crash")
