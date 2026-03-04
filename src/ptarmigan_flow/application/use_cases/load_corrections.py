"""Use case for loading transcription correction dictionaries."""

from __future__ import annotations

from pathlib import Path

from ptarmigan_flow.text_processing.repository import CorrectionDictionaryError, CorrectionDictionaryLoadResult
from ptarmigan_flow.text_processing.service import CorrectionService


def load_corrections_with_diagnostics(
    config: object,
    *,
    config_path: Path,
) -> tuple[CorrectionDictionaryLoadResult | None, str | None]:
    service = CorrectionService.create_default()
    try:
        result = service.load_for_config(
            config=config,
            config_path=config_path,
        )
    except CorrectionDictionaryError as exc:
        return None, str(exc)
    return result, None
