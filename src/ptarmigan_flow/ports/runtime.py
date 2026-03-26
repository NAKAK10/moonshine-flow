"""Runtime ports for daemon orchestration."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import time
from typing import Protocol

import numpy as np


@dataclass(slots=True, frozen=True)
class BackendWarmState:
    resource_mode: str
    ready: bool
    warmed: bool
    warmup_running: bool
    supports_keydown_warmup: bool
    last_activity_at_monotonic: float | None = None


def format_backend_warm_state(state: BackendWarmState) -> str:
    last_activity_age = "never"
    if state.last_activity_at_monotonic is not None:
        age_seconds = max(0.0, time.monotonic() - state.last_activity_at_monotonic)
        last_activity_age = f"{age_seconds:.1f}s"
    return (
        "warm_state("
        f"resource_mode={state.resource_mode} "
        f"ready={'yes' if state.ready else 'no'} "
        f"warmed={'yes' if state.warmed else 'no'} "
        f"warmup_running={'yes' if state.warmup_running else 'no'} "
        f"keydown_warmup={'yes' if state.supports_keydown_warmup else 'no'} "
        f"last_activity_age={last_activity_age}"
        ")"
    )


class AudioInputPort(Protocol):
    @property
    def is_recording(self) -> bool: ...

    def is_stream_active(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> np.ndarray: ...

    def snapshot(self) -> np.ndarray: ...

    def close(self) -> None: ...


class SpeechToTextPort(Protocol):
    def preflight_model(self) -> str: ...

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str: ...

    def transcribe_stream(self, audio: np.ndarray, sample_rate: int) -> Iterator[str]: ...

    def warm_state(self) -> BackendWarmState: ...

    def warmup_for_low_latency(self) -> None: ...

    def supports_realtime_input(self) -> bool: ...

    def maybe_release_idle_resources(self) -> None: ...

    def runtime_status(self) -> str: ...

    def backend_summary(self) -> str: ...

    def close(self) -> None: ...


class TextOutputPort(Protocol):
    def inject(self, text: str) -> bool: ...


class ActivityIndicatorPort(Protocol):
    def show_recording(self) -> None: ...

    def show_processing(self) -> None: ...

    def hide(self) -> None: ...

    def close(self) -> None: ...
