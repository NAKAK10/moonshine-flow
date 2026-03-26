"""Canonical model ids and family-specific model resolution helpers."""

from __future__ import annotations

VOXTRAL_HF_MODEL_ID = "mistralai/Voxtral-Mini-4B-Realtime-2602"
VOXTRAL_MLX_MODEL_ID = "mlx-community/Voxtral-Mini-4B-Realtime-6bit"
GRANITE_HF_MODEL_ID = "ibm-granite/granite-4.0-1b-speech"
GRANITE_MLX_MODEL_ID = "mlx-community/granite-4.0-1b-speech-8bit"


def resolve_voxtral_mlx_model_id(model_id: str) -> str:
    normalized = model_id.strip()
    if normalized.lower() == VOXTRAL_HF_MODEL_ID.lower():
        return VOXTRAL_MLX_MODEL_ID
    return normalized


def resolve_granite_mlx_model_id(model_id: str) -> str:
    normalized = model_id.strip()
    if normalized.lower() == GRANITE_HF_MODEL_ID.lower():
        return GRANITE_MLX_MODEL_ID
    return normalized


def resolve_runtime_model_id(
    *,
    prefix: str,
    model_id: str,
    macos_arm64: bool,
) -> str:
    normalized_prefix = prefix.strip().lower()
    normalized_model_id = model_id.strip()
    if normalized_prefix == "voxtral" and macos_arm64:
        return resolve_voxtral_mlx_model_id(normalized_model_id)
    if normalized_prefix == "granite" and macos_arm64:
        return resolve_granite_mlx_model_id(normalized_model_id)
    return normalized_model_id
