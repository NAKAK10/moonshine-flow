from __future__ import annotations

from pathlib import Path

import pytest

from ptarmigan_flow.transcription_corrections import (
    CorrectionDictionaryError,
    default_dictionary_path,
    load_corrections_dictionary,
    resolve_dictionary_path,
)


def test_load_missing_default_dictionary_is_disabled_without_warning(tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"

    result = load_corrections_dictionary(path, explicitly_configured=False)

    assert result.loaded is False
    assert result.rules.exact_count == 0
    assert result.rules.regex_count == 0
    assert result.warnings == []


def test_load_missing_explicit_dictionary_warns_and_continues(tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"

    result = load_corrections_dictionary(path, explicitly_configured=True)

    assert result.loaded is False
    assert len(result.warnings) == 1
    assert "not found" in result.warnings[0].message


def test_load_invalid_toml_reports_line_and_column(tmp_path: Path) -> None:
    path = tmp_path / "dictionary.toml"
    path.write_text("[exact]\n\"Ptarmigan Flow\" = [\"a\"\n", encoding="utf-8")

    with pytest.raises(CorrectionDictionaryError) as exc_info:
        load_corrections_dictionary(path, explicitly_configured=False)

    message = str(exc_info.value)
    assert str(path) in message
    assert "line" in message or "at" in message


def test_apply_exact_and_regex_rules(tmp_path: Path) -> None:
    path = tmp_path / "dictionary.toml"
    path.write_text(
        """
[exact]
"Ptarmigan Flow" = ["ぷたーみがんふろー", "ぷたーみがんふ"]

[regex]
"Ptarmigan Flow" = ["ぷたーみがんふ(ろー)?"]
"GPT" = ["(?i)じーぴーてぃー"]
""".strip(),
        encoding="utf-8",
    )

    result = load_corrections_dictionary(path, explicitly_configured=False)

    assert result.loaded is True
    assert result.rules.apply("ぷたーみがんふ") == "Ptarmigan Flow"
    assert result.rules.apply("これは ぷたーみがんふろー です") == "これはPtarmigan Flowです"
    assert result.rules.apply("じーぴーてぃー") == "GPT"


def test_invalid_regex_is_disabled_with_warning(tmp_path: Path) -> None:
    path = tmp_path / "dictionary.toml"
    path.write_text(
        """
[regex]
"Ptarmigan Flow" = ["(invalid"]
""".strip(),
        encoding="utf-8",
    )

    result = load_corrections_dictionary(path, explicitly_configured=False)

    assert result.loaded is True
    assert result.rules.regex_count == 0
    assert result.disabled_regex_count == 1
    assert len(result.warnings) == 1


def test_resolve_dictionary_path_defaults_and_explicit(tmp_path: Path) -> None:
    default_path, explicit_default = resolve_dictionary_path(None)
    assert default_path == default_dictionary_path()
    assert explicit_default is False

    explicit_path, explicit = resolve_dictionary_path(
        "dictionary.toml",
        config_path=tmp_path / "config.toml",
    )
    assert explicit is True
    assert explicit_path == (tmp_path / "dictionary.toml").resolve()
