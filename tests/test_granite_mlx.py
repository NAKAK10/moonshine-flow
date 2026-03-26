from __future__ import annotations

import numpy as np

import ptarmigan_flow.stt.granite_mlx as granite_module
from ptarmigan_flow.stt.granite_mlx import GraniteMLXSettings, GraniteMLXSTTBackend


class _CountingPostProcessor:
    def __init__(self) -> None:
        self.apply_calls = 0
        self.inputs: list[str] = []

    def apply(self, text: str) -> str:
        self.apply_calls += 1
        self.inputs.append(text)
        return f"post:{text}"


def _make_backend(post_processor=None) -> GraniteMLXSTTBackend:
    settings = GraniteMLXSettings(
        model_id="ibm-granite/granite-4.0-1b-speech",
        language="ja",
        trailing_silence_seconds=1.0,
    )
    return GraniteMLXSTTBackend(settings, post_processor=post_processor)


def test_preflight_marks_granite_ready_but_not_warmed(monkeypatch) -> None:
    backend = _make_backend()

    monkeypatch.setattr(
        GraniteMLXSTTBackend,
        "_ensure_dependencies",
        staticmethod(
            lambda: (
                lambda _model_id: object(),
                lambda **_kwargs: {"text": "ignored"},
            )
        ),
    )

    backend.preflight_model()

    state = backend.warm_state()
    assert state.ready is True
    assert state.warmed is False
    assert state.supports_keydown_warmup is True
    assert "warm_state(" in backend.runtime_status()


def test_warmup_marks_granite_warmed_without_post_processing(monkeypatch) -> None:
    processor = _CountingPostProcessor()
    backend = _make_backend(post_processor=processor)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        GraniteMLXSTTBackend,
        "_ensure_dependencies",
        staticmethod(
            lambda: (
                lambda _model_id: object(),
                lambda **_kwargs: {"text": "ignored"},
            )
        ),
    )
    monkeypatch.setattr(granite_module.time, "monotonic", lambda: 123.0)
    monkeypatch.setattr(granite_module.os, "unlink", lambda _path: None)
    monkeypatch.setattr(
        backend,
        "_prepare_temp_wav",
        lambda audio, *, sample_rate, trailing_silence_seconds=None: captured.update(
            {
                "audio_size": int(audio.shape[0]),
                "sample_rate": sample_rate,
                "trailing_silence_seconds": trailing_silence_seconds,
            }
        )
        or "/tmp/granite-warmup.wav",
    )

    backend.preflight_model()
    backend.warmup_for_low_latency()

    state = backend.warm_state()
    assert state.ready is True
    assert state.warmed is True
    assert state.last_activity_at_monotonic == 123.0
    assert processor.apply_calls == 0
    assert captured == {
        "audio_size": 3200,
        "sample_rate": 16000,
        "trailing_silence_seconds": 0.0,
    }


def test_transcribe_updates_warm_state_and_runs_post_processor(monkeypatch) -> None:
    processor = _CountingPostProcessor()
    backend = _make_backend(post_processor=processor)

    monkeypatch.setattr(
        GraniteMLXSTTBackend,
        "_ensure_dependencies",
        staticmethod(
            lambda: (
                lambda _model_id: object(),
                lambda **_kwargs: {"text": " hello "},
            )
        ),
    )
    monkeypatch.setattr(granite_module.time, "monotonic", lambda: 456.0)
    monkeypatch.setattr(granite_module.os, "unlink", lambda _path: None)
    monkeypatch.setattr(
        backend,
        "_prepare_temp_wav",
        lambda audio, *, sample_rate, trailing_silence_seconds=None: "/tmp/granite-final.wav",
    )

    backend.preflight_model()
    result = backend.transcribe(np.zeros((160, 1), dtype=np.float32), 16000)

    state = backend.warm_state()
    assert result == "post:hello"
    assert processor.apply_calls == 1
    assert processor.inputs == ["hello"]
    assert state.ready is True
    assert state.warmed is True
    assert state.last_activity_at_monotonic == 456.0
