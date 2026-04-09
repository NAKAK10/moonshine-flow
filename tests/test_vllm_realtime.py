from __future__ import annotations

import sys
from types import ModuleType

import numpy as np
import pytest

import ptarmigan_flow.stt.vllm_realtime as vllm_module
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


class _TimeoutWebSocket:
    def __init__(self) -> None:
        self.recv_timeouts: list[float | None] = []

    def __enter__(self) -> _TimeoutWebSocket:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def send(self, _message: str) -> None:
        return None

    def recv(self, timeout=None):
        self.recv_timeouts.append(timeout)
        raise TimeoutError("timed out")


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


def test_stream_events_times_out_when_server_stalls(monkeypatch) -> None:
    backend = _make_backend(0.0)
    websocket = _TimeoutWebSocket()

    client_module = ModuleType("websockets.sync.client")
    client_module.connect = lambda *_args, **_kwargs: websocket  # type: ignore[attr-defined]
    sync_module = ModuleType("websockets.sync")
    sync_module.client = client_module  # type: ignore[attr-defined]
    websockets_module = ModuleType("websockets")
    websockets_module.sync = sync_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "websockets", websockets_module)
    monkeypatch.setitem(sys.modules, "websockets.sync", sync_module)
    monkeypatch.setitem(sys.modules, "websockets.sync.client", client_module)

    monotonic_values = iter([0.0, 1.1, 2.2, 3.3, 4.4, 5.5])
    monkeypatch.setattr(vllm_module.time, "monotonic", lambda: next(monotonic_values))

    with pytest.raises(RuntimeError, match="Realtime transcription stalled"):
        list(backend._stream_events(b"\x00\x00"))

    assert websocket.recv_timeouts
    assert all(
        timeout == vllm_module._WEBSOCKET_RECV_TIMEOUT_SECONDS
        for timeout in websocket.recv_timeouts
    )
