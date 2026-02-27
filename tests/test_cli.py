import pytest

from moonshine_flow import cli


def test_has_moonshine_backend_true(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "find_spec",
        lambda name: object() if name == "moonshine_voice" else None,
    )
    assert cli._has_moonshine_backend()


def test_has_moonshine_backend_false(monkeypatch) -> None:
    monkeypatch.setattr(cli, "find_spec", lambda name: None)
    assert not cli._has_moonshine_backend()


def test_backend_guidance_has_actionable_text() -> None:
    guidance = cli._backend_guidance()
    assert "uv sync" in guidance
    assert "Moonshine backend package is missing" in guidance


def test_check_permissions_parser_has_request_flag() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["check-permissions", "--request"])
    assert args.request is True


def test_parser_version_long_flag_outputs_version(capsys) -> None:
    version_value = "9.9.9"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "package_version", lambda name: version_value)
    try:
        parser = cli.build_parser()
        parser.prog = "moonshine-flow"
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
    finally:
        monkeypatch.undo()

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.out.strip() == f"moonshine-flow {version_value}"


def test_parser_version_short_flag_outputs_version(capsys) -> None:
    version_value = "9.9.10"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "package_version", lambda name: version_value)
    try:
        parser = cli.build_parser()
        parser.prog = "moonshine-flow"
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["-v"])
    finally:
        monkeypatch.undo()

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.out.strip() == f"moonshine-flow {version_value}"


def test_parser_version_falls_back_when_package_metadata_missing(capsys) -> None:
    def raise_not_found(name: str) -> str:
        raise cli.PackageNotFoundError(name)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "package_version", raise_not_found)
    try:
        parser = cli.build_parser()
        parser.prog = "moonshine-flow"
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
    finally:
        monkeypatch.undo()

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.out.strip() == "moonshine-flow 0.0.0.dev0"


def test_resolve_app_version_reads_installed_metadata() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "package_version", lambda name: "1.2.3")
    try:
        assert cli._resolve_app_version() == "1.2.3"
    finally:
        monkeypatch.undo()


def test_resolve_app_version_fallback_when_metadata_missing() -> None:
    def raise_not_found(name: str) -> str:
        raise cli.PackageNotFoundError(name)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "package_version", raise_not_found)
    try:
        assert cli._resolve_app_version() == "0.0.0.dev0"
    finally:
        monkeypatch.undo()
