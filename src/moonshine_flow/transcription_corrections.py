"""Backward-compatible exports for transcription correction features."""

from __future__ import annotations

from pathlib import Path

from moonshine_flow.text_processing.corrections import (
    CompiledRegexRule,
    CorrectionRuleSet as TranscriptionCorrections,
)
from moonshine_flow.text_processing.normalizer import normalize_transcript_text
from moonshine_flow.text_processing.repository import (
    CorrectionDictionaryError,
    CorrectionDictionaryLoadResult,
    CorrectionLoadWarning,
    TomlCorrectionRepository,
)

_REPOSITORY = TomlCorrectionRepository()


def default_dictionary_path() -> Path:
    return _REPOSITORY.default_dictionary_path()


def resolve_dictionary_path(
    dictionary_path: str | None,
    *,
    config_path: Path | None = None,
) -> tuple[Path, bool]:
    return _REPOSITORY.resolve_dictionary_path(dictionary_path, config_path=config_path)


def load_corrections_dictionary(
    path: Path,
    *,
    explicitly_configured: bool,
) -> CorrectionDictionaryLoadResult:
    return _REPOSITORY.load(path, explicitly_configured=explicitly_configured)
