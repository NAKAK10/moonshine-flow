from __future__ import annotations

import logging

import ptarmigan_flow.presentation.cli.commands as commands
from ptarmigan_flow.stt.model_families import (
    GRANITE_HF_MODEL_ID,
    GRANITE_MLX_MODEL_ID,
    WHISPER_HF_MODEL_ID,
    WHISPER_MLX_MODEL_ID,
)


def test_stt_model_presets_include_granite() -> None:
    assert f"granite:{GRANITE_HF_MODEL_ID}" in commands._stt_model_presets()


def test_stt_model_presets_include_whisper() -> None:
    assert f"mlx:{WHISPER_HF_MODEL_ID}" in commands._stt_model_presets()


def test_stt_model_downloaded_display_resolves_granite_mlx_variant(monkeypatch) -> None:
    seen: list[str] = []

    monkeypatch.setattr(commands, "_is_macos_arm64", lambda: True)
    monkeypatch.setattr(
        commands,
        "_is_huggingface_model_downloaded",
        lambda model_id: seen.append(model_id) or True,
    )

    assert commands._stt_model_downloaded_display(f"granite:{GRANITE_HF_MODEL_ID}") == "yes"
    assert seen == [GRANITE_MLX_MODEL_ID]


def test_stt_model_downloaded_display_resolves_whisper_mlx_variant(monkeypatch) -> None:
    seen: list[str] = []

    monkeypatch.setattr(commands, "_is_macos_arm64", lambda: True)
    monkeypatch.setattr(
        commands,
        "_is_huggingface_model_downloaded",
        lambda model_id: seen.append(model_id) or True,
    )

    assert commands._stt_model_downloaded_display(f"mlx:{WHISPER_HF_MODEL_ID}") == "yes"
    assert seen == [WHISPER_MLX_MODEL_ID]


def test_stt_model_requires_startup_download_for_missing_huggingface_model(monkeypatch) -> None:
    monkeypatch.setattr(commands, "_stt_model_downloaded_display", lambda _token: "no")
    assert commands._stt_model_requires_startup_download(f"mlx:{WHISPER_HF_MODEL_ID}") is True


def test_log_stt_startup_download_if_needed_logs_backend_name(monkeypatch, caplog) -> None:
    monkeypatch.setattr(commands, "_stt_model_requires_startup_download", lambda _token: True)

    with caplog.at_level(logging.INFO, logger=commands.__name__):
        commands._log_stt_startup_download_if_needed(f"mlx:{WHISPER_HF_MODEL_ID}")

    assert (
        "Selected MLX model is not downloaded yet; startup preflight will download it now"
        in caplog.text
    )


def test_granite_backend_guidance_mentions_expected_dependency(monkeypatch) -> None:
    monkeypatch.setattr(commands, "_is_macos_arm64", lambda: True)
    assert "mlx-audio" in commands._granite_backend_guidance()

    monkeypatch.setattr(commands, "_is_macos_arm64", lambda: False)
    assert "transformers torch" in commands._granite_backend_guidance()
