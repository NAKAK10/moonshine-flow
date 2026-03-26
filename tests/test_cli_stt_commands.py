from __future__ import annotations

import ptarmigan_flow.presentation.cli.commands as commands
from ptarmigan_flow.stt.model_families import GRANITE_HF_MODEL_ID, GRANITE_MLX_MODEL_ID


def test_stt_model_presets_include_granite() -> None:
    assert f"granite:{GRANITE_HF_MODEL_ID}" in commands._stt_model_presets()


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


def test_granite_backend_guidance_mentions_expected_dependency(monkeypatch) -> None:
    monkeypatch.setattr(commands, "_is_macos_arm64", lambda: True)
    assert "mlx-audio" in commands._granite_backend_guidance()

    monkeypatch.setattr(commands, "_is_macos_arm64", lambda: False)
    assert "transformers torch" in commands._granite_backend_guidance()
