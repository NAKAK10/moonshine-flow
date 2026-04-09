from ptarmigan_flow.stt.model_families import (
    GRANITE_MLX_MODEL_ID,
    VOXTRAL_MLX_MODEL_ID,
    WHISPER_MLX_MODEL_ID,
    resolve_granite_mlx_model_id,
    resolve_runtime_model_id,
    resolve_voxtral_mlx_model_id,
    resolve_whisper_mlx_model_id,
)


def test_resolve_voxtral_mlx_model_id_maps_canonical_hf_model() -> None:
    assert (
        resolve_voxtral_mlx_model_id("mistralai/Voxtral-Mini-4B-Realtime-2602")
        == VOXTRAL_MLX_MODEL_ID
    )


def test_resolve_granite_mlx_model_id_maps_canonical_hf_model() -> None:
    assert (
        resolve_granite_mlx_model_id("ibm-granite/granite-4.0-1b-speech")
        == GRANITE_MLX_MODEL_ID
    )


def test_resolve_whisper_mlx_model_id_maps_canonical_hf_model() -> None:
    assert resolve_whisper_mlx_model_id("openai/whisper-large-v3-turbo") == WHISPER_MLX_MODEL_ID


def test_resolve_runtime_model_id_preserves_non_mlx_runtime() -> None:
    assert (
        resolve_runtime_model_id(
            prefix="granite",
            model_id="ibm-granite/granite-4.0-1b-speech",
            macos_arm64=False,
        )
        == "ibm-granite/granite-4.0-1b-speech"
    )


def test_resolve_runtime_model_id_maps_whisper_for_mlx_runtime() -> None:
    assert (
        resolve_runtime_model_id(
            prefix="mlx",
            model_id="openai/whisper-large-v3-turbo",
            macos_arm64=True,
        )
        == WHISPER_MLX_MODEL_ID
    )
