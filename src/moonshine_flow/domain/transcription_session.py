"""Domain logic for incremental transcription sessions."""

from __future__ import annotations

from dataclasses import dataclass

_NON_MONOTONIC_TAIL_TOLERANCE_CHARS = 4


@dataclass(slots=True)
class LiveInputState:
    """State for live incremental transcription output."""

    emitted_text: str = ""
    last_snapshot_samples: int = 0


def append_only_delta(
    previous: str,
    current: str,
    *,
    non_monotonic_tail_tolerance_chars: int = _NON_MONOTONIC_TAIL_TOLERANCE_CHARS,
) -> str:
    """Return append-only delta while tolerating tiny tail rewrites."""
    if current.startswith(previous):
        return current[len(previous) :]

    common_prefix_len = 0
    max_common = min(len(previous), len(current))
    while common_prefix_len < max_common and previous[common_prefix_len] == current[common_prefix_len]:
        common_prefix_len += 1

    if len(previous) - common_prefix_len <= non_monotonic_tail_tolerance_chars:
        if common_prefix_len >= len(current):
            return ""
        return current[common_prefix_len:]
    return ""


def has_sufficient_new_audio(
    *,
    total_samples: int,
    last_snapshot_samples: int,
    sample_rate: int,
    min_new_audio_seconds: float,
) -> bool:
    """Return whether enough new audio exists for another live inference tick."""
    if total_samples <= 0:
        return False

    min_new_audio_samples = max(1, int(float(sample_rate) * min_new_audio_seconds))
    if last_snapshot_samples > 0 and total_samples < last_snapshot_samples + min_new_audio_samples:
        return False
    return True
