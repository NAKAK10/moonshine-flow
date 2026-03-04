"""Realtime input capability helpers for STT models."""

from __future__ import annotations

_REALTIME_INPUT_MODEL_IDS = frozenset(
    {
        "mistralai/voxtral-mini-4b-realtime-2602",
        "mlx-community/voxtral-mini-4b-realtime-6bit",
    }
)


def supports_realtime_input_model(model_id: str) -> bool:
    normalized = model_id.strip().lower()
    if not normalized:
        return False
    return normalized in _REALTIME_INPUT_MODEL_IDS
