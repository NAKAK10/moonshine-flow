from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import ptarmigan_flow.stt.mlx_whisper as whisper_module
from ptarmigan_flow.stt.mlx_whisper import MLXWhisperBackendSettings, MLXWhisperSTTBackend
from ptarmigan_flow.stt.model_families import WHISPER_HF_MODEL_ID, WHISPER_MLX_MODEL_ID


class _CountingPostProcessor:
    def __init__(self) -> None:
        self.apply_calls = 0
        self.inputs: list[str] = []

    def apply(self, text: str) -> str:
        self.apply_calls += 1
        self.inputs.append(text)
        return f"post:{text}"


def _make_backend(post_processor=None) -> MLXWhisperSTTBackend:
    settings = MLXWhisperBackendSettings(
        model_id=WHISPER_HF_MODEL_ID,
        language="ja",
        trailing_silence_seconds=1.0,
    )
    return MLXWhisperSTTBackend(settings, post_processor=post_processor)


def test_preflight_downloads_whisper_model_and_marks_backend_warmed(monkeypatch) -> None:
    processor = _CountingPostProcessor()
    backend = _make_backend(post_processor=processor)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        MLXWhisperSTTBackend,
        "_ensure_dependency",
        staticmethod(
            lambda: SimpleNamespace(
                transcribe=lambda wav_path, *, path_or_hf_repo, language: captured.update(
                    {
                        "wav_path": wav_path,
                        "path_or_hf_repo": path_or_hf_repo,
                        "language": language,
                    }
                )
                or {"text": "ignored"}
            )
        ),
    )
    monkeypatch.setattr(whisper_module.time, "monotonic", lambda: 123.0)
    monkeypatch.setattr(whisper_module.os, "unlink", lambda _path: None)
    monkeypatch.setattr(
        backend,
        "_prepare_temp_wav",
        lambda audio, *, sample_rate: captured.update(
            {
                "audio_size": int(audio.shape[0]),
                "sample_rate": sample_rate,
            }
        )
        or "/tmp/whisper-preflight.wav",
    )

    backend.preflight_model()

    state = backend.warm_state()
    assert state.ready is True
    assert state.warmed is True
    assert state.last_activity_at_monotonic == 123.0
    assert processor.apply_calls == 0
    assert captured == {
        "audio_size": 3200,
        "sample_rate": 16000,
        "wav_path": "/tmp/whisper-preflight.wav",
        "path_or_hf_repo": WHISPER_MLX_MODEL_ID,
        "language": "ja",
    }


def test_transcribe_updates_warm_state_and_runs_post_processor(monkeypatch) -> None:
    processor = _CountingPostProcessor()
    backend = _make_backend(post_processor=processor)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        MLXWhisperSTTBackend,
        "_ensure_dependency",
        staticmethod(
            lambda: SimpleNamespace(
                transcribe=lambda wav_path, *, path_or_hf_repo, language: captured.update(
                    {
                        "wav_path": wav_path,
                        "path_or_hf_repo": path_or_hf_repo,
                        "language": language,
                    }
                )
                or {"text": " hello "}
            )
        ),
    )
    monkeypatch.setattr(whisper_module.time, "monotonic", lambda: 456.0)
    monkeypatch.setattr(whisper_module.os, "unlink", lambda _path: None)
    monkeypatch.setattr(
        backend,
        "_prepare_temp_wav",
        lambda audio, *, sample_rate: captured.update(
            {
                "audio_size": int(audio.shape[0]),
                "sample_rate": sample_rate,
            }
        )
        or "/tmp/whisper-final.wav",
    )
    backend._ready = True

    result = backend.transcribe(np.zeros((160, 1), dtype=np.float32), 16000)

    state = backend.warm_state()
    assert result == "post:hello"
    assert processor.apply_calls == 1
    assert processor.inputs == ["hello"]
    assert state.ready is True
    assert state.warmed is True
    assert state.last_activity_at_monotonic == 456.0
    assert captured == {
        "audio_size": 160,
        "sample_rate": 16000,
        "wav_path": "/tmp/whisper-final.wav",
        "path_or_hf_repo": WHISPER_MLX_MODEL_ID,
        "language": "ja",
    }
