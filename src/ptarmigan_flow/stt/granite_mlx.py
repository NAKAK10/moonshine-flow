"""Granite STT backend implemented with mlx-audio."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

from ptarmigan_flow.ports.runtime import BackendWarmState, format_backend_warm_state
from ptarmigan_flow.stt.base import SpeechToTextBackend
from ptarmigan_flow.stt.model_families import resolve_granite_mlx_model_id
from ptarmigan_flow.text_processing.interfaces import NoopTextPostProcessor, TextPostProcessor
from ptarmigan_flow.text_processing.normalizer import normalize_transcript_text

_TARGET_SAMPLE_RATE = 16000


@dataclass(slots=True)
class GraniteMLXSettings:
    model_id: str
    language: str
    trailing_silence_seconds: float


class GraniteMLXSTTBackend(SpeechToTextBackend):
    """Transcribe audio with mlx-audio Granite speech models."""

    def __init__(
        self,
        settings: GraniteMLXSettings,
        *,
        post_processor: TextPostProcessor | None = None,
    ) -> None:
        self._settings = settings
        self._post_processor = post_processor or NoopTextPostProcessor()
        self._ready = False
        self._model: Any | None = None
        self._transcribe: Any | None = None
        self._resolved_model_id = resolve_granite_mlx_model_id(settings.model_id)
        self._warmup_running = False
        self._last_activity_at_monotonic: float | None = None
        self._state_lock = threading.Lock()

    @staticmethod
    def _ensure_dependencies() -> tuple[Any, Any]:
        try:
            from mlx_audio.stt.generate import generate_transcription
            from mlx_audio.stt.utils import load_model
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("mlx-audio package is required for granite backend on macOS") from exc

        return load_model, generate_transcription

    def preflight_model(self) -> str:
        if self._ready:
            return "granite-mlx"
        load_model, generate_transcription = self._ensure_dependencies()
        self._model = load_model(self._resolved_model_id)
        self._transcribe = generate_transcription
        self._ready = True
        return "granite-mlx"

    def _ensure_ready(self) -> None:
        if self._ready:
            return
        self.preflight_model()

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio.size == 0:
            return ""
        self._ensure_ready()
        assert self._model is not None
        assert self._transcribe is not None

        wav_path = self._prepare_temp_wav(audio, sample_rate=sample_rate)
        try:
            result = self._transcribe(
                model=self._model,
                audio=wav_path,
            )
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

        self._mark_activity()
        text = ""
        if isinstance(result, str):
            text = result
        elif isinstance(result, dict):
            value = result.get("text")
            if isinstance(value, str):
                text = value
        else:
            value = getattr(result, "text", "")
            if isinstance(value, str):
                text = value

        normalized = normalize_transcript_text(text)
        if not normalized:
            return ""
        return self._post_processor.apply(normalized)

    def transcribe_stream(self, audio: np.ndarray, sample_rate: int) -> Iterator[str]:
        text = self.transcribe(audio, sample_rate)
        if text:
            yield text

    def supports_realtime_input(self) -> bool:
        return False

    def warm_state(self) -> BackendWarmState:
        with self._state_lock:
            ready = self._ready
            warmup_running = self._warmup_running
            last_activity = self._last_activity_at_monotonic
        return BackendWarmState(
            resource_mode="in_process",
            ready=ready,
            warmed=last_activity is not None,
            warmup_running=warmup_running,
            supports_keydown_warmup=True,
            last_activity_at_monotonic=last_activity,
        )

    def warmup_for_low_latency(self) -> None:
        with self._state_lock:
            if self._warmup_running:
                return
            self._warmup_running = True
        try:
            self._ensure_ready()
            assert self._model is not None
            assert self._transcribe is not None

            warmup_audio = np.zeros(int(_TARGET_SAMPLE_RATE * 0.2), dtype=np.float32)
            wav_path = self._prepare_temp_wav(
                warmup_audio,
                sample_rate=_TARGET_SAMPLE_RATE,
                trailing_silence_seconds=0.0,
            )
            try:
                self._transcribe(
                    model=self._model,
                    audio=wav_path,
                )
            finally:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
            self._mark_activity()
        finally:
            with self._state_lock:
                self._warmup_running = False

    def maybe_release_idle_resources(self) -> None:
        return None

    def runtime_status(self) -> str:
        return (
            "🚀 Backend ready (no external server): "
            f"{self.backend_summary()} {format_backend_warm_state(self.warm_state())}"
        )

    def _prepare_temp_wav(
        self,
        audio: np.ndarray,
        *,
        sample_rate: int,
        trailing_silence_seconds: float | None = None,
    ) -> str:
        mono = self._to_mono_float32(audio)
        mono = self._append_trailing_silence(
            mono,
            sample_rate=sample_rate,
            trailing_silence_seconds=trailing_silence_seconds,
        )
        if sample_rate != _TARGET_SAMPLE_RATE:
            mono = self._resample_linear(mono, src_rate=sample_rate, dst_rate=_TARGET_SAMPLE_RATE)
        pcm16 = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
            path = temp.name
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(_TARGET_SAMPLE_RATE)
            wav_file.writeframes(pcm16.tobytes())
        return path

    @staticmethod
    def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
        if audio.ndim == 2:
            return np.mean(audio, axis=1).astype(np.float32, copy=False)
        return audio.astype(np.float32, copy=False)

    def _append_trailing_silence(
        self,
        audio: np.ndarray,
        *,
        sample_rate: int,
        trailing_silence_seconds: float | None = None,
    ) -> np.ndarray:
        if trailing_silence_seconds is None:
            trailing_silence_seconds = float(self._settings.trailing_silence_seconds)
        trailing = max(0.0, min(1.0, float(trailing_silence_seconds)))
        trailing_samples = int(sample_rate * trailing)
        if trailing_samples <= 0:
            return audio
        return np.concatenate((audio, np.zeros(trailing_samples, dtype=np.float32)))

    @staticmethod
    def _resample_linear(audio: np.ndarray, *, src_rate: int, dst_rate: int) -> np.ndarray:
        if src_rate <= 0 or dst_rate <= 0 or audio.size == 0:
            return audio
        dst_len = int(round(audio.size * (dst_rate / src_rate)))
        if dst_len <= 1:
            return audio
        src_x = np.linspace(0.0, 1.0, num=audio.size, endpoint=True)
        dst_x = np.linspace(0.0, 1.0, num=dst_len, endpoint=True)
        return np.interp(dst_x, src_x, audio).astype(np.float32, copy=False)

    def backend_summary(self) -> str:
        return (
            "backend=granite-mlx "
            f"model={self._resolved_model_id} "
            f"language={self._settings.language}"
        )

    def _mark_activity(self) -> None:
        with self._state_lock:
            self._last_activity_at_monotonic = time.monotonic()

    def close(self) -> None:
        self._model = None
        self._transcribe = None
        self._ready = False
        with self._state_lock:
            self._warmup_running = False
            self._last_activity_at_monotonic = None
