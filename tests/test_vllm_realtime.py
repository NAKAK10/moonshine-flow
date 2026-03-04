from __future__ import annotations

import numpy as np

from ptarmigan_flow.stt.vllm_realtime import VLLMRealtimeBackendSettings, VLLMRealtimeSTTBackend


class _FakeServerManager:
    endpoint_url = "http://127.0.0.1:8000"
    websocket_url = "ws://127.0.0.1:8000/v1/realtime?intent=transcription"

    def ensure_started(self, _model_id: str) -> str:
        return "http://127.0.0.1:8000"

    def mark_activity(self) -> None:
        return None

    def stop_if_idle(self, _idle_seconds: float) -> bool:
        return False

    def stop(self) -> None:
        return None


class _StoppedServerManager(_FakeServerManager):
    @property
    def endpoint_url(self) -> str:  # type: ignore[override]
        raise RuntimeError("vLLM server is not started")


def _make_backend(trailing_silence_seconds: float) -> VLLMRealtimeSTTBackend:
    settings = VLLMRealtimeBackendSettings(
        model_id="mistralai/Voxtral-Mini-4B-Realtime-2602",
        language="ja",
        trailing_silence_seconds=trailing_silence_seconds,
        idle_shutdown_seconds=30.0,
    )
    return VLLMRealtimeSTTBackend(settings, server_manager=_FakeServerManager())


def test_append_trailing_silence_keeps_length_when_zero() -> None:
    backend = _make_backend(0.0)
    audio = np.array([0.25, 0.5], dtype=np.float32)
    out = backend._append_trailing_silence(audio, sample_rate=16000)
    assert out.shape == audio.shape
    assert backend.supports_realtime_input() is True


def test_append_trailing_silence_extends_audio() -> None:
    backend = _make_backend(0.25)
    audio = np.array([0.25, 0.5], dtype=np.float32)
    out = backend._append_trailing_silence(audio, sample_rate=10)
    assert out.shape[0] == 4


def test_append_trailing_silence_clamps_negative_to_zero() -> None:
    backend = _make_backend(-1.0)
    audio = np.array([0.25, 0.5], dtype=np.float32)
    out = backend._append_trailing_silence(audio, sample_rate=16000)
    assert out.shape == audio.shape


def test_runtime_status_reports_active_server() -> None:
    backend = _make_backend(0.0)
    status = backend.runtime_status()
    assert status.startswith("🚀 External server active:")
    assert "endpoint=http://127.0.0.1:8000" in status


def test_runtime_status_reports_stopped_server() -> None:
    settings = VLLMRealtimeBackendSettings(
        model_id="mistralai/Voxtral-Mini-4B-Realtime-2602",
        language="ja",
        trailing_silence_seconds=0.0,
        idle_shutdown_seconds=30.0,
    )
    backend = VLLMRealtimeSTTBackend(settings, server_manager=_StoppedServerManager())
    status = backend.runtime_status()
    assert status.startswith("💨 External server stopped:")
