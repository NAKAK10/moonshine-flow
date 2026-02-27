import argparse
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from moonshine_flow import cli
from moonshine_flow.permissions import PermissionReport


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


def test_install_launch_agent_parser_defaults() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["install-launch-agent"])
    assert args.request_permissions is True
    assert args.allow_missing_permissions is False
    assert args.verbose_bootstrap is False


def test_install_launch_agent_parser_allows_no_request_permissions() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["install-launch-agent", "--no-request-permissions"])
    assert args.request_permissions is False


def test_cmd_install_launch_agent_aborts_when_permissions_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(cli, "load_config", lambda _: object())
    monkeypatch.setattr(
        cli,
        "request_all_permissions",
        lambda: PermissionReport(microphone=False, accessibility=True, input_monitoring=True),
    )
    monkeypatch.setattr(
        cli,
        "install_launch_agent",
        lambda _: (_ for _ in ()).throw(AssertionError("install should not run")),
    )
    args = argparse.Namespace(
        config=None,
        request_permissions=True,
        allow_missing_permissions=False,
        verbose_bootstrap=False,
    )

    exit_code = cli.cmd_install_launch_agent(args)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Launch agent installation was aborted" in captured.err
    assert "allow-missing-permissions" in captured.err


def test_cmd_install_launch_agent_allows_missing_permissions(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(cli, "load_config", lambda _: object())
    monkeypatch.setattr(
        cli,
        "request_all_permissions",
        lambda: PermissionReport(microphone=False, accessibility=True, input_monitoring=True),
    )
    monkeypatch.setattr(cli, "install_launch_agent", lambda _: Path("/tmp/agent.plist"))
    args = argparse.Namespace(
        config=None,
        request_permissions=True,
        allow_missing_permissions=True,
        verbose_bootstrap=False,
    )

    exit_code = cli.cmd_install_launch_agent(args)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "continuing with missing permissions" in captured.err
    assert "Installed launch agent: /tmp/agent.plist" in captured.out


def test_cmd_install_launch_agent_uses_check_permissions_when_request_disabled(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(cli, "load_config", lambda _: object())
    monkeypatch.setattr(
        cli,
        "request_all_permissions",
        lambda: (_ for _ in ()).throw(AssertionError("request should not run")),
    )
    monkeypatch.setattr(
        cli,
        "check_all_permissions",
        lambda: PermissionReport(microphone=True, accessibility=True, input_monitoring=True),
    )
    monkeypatch.setattr(cli, "install_launch_agent", lambda _: Path("/tmp/agent.plist"))
    args = argparse.Namespace(
        config=None,
        request_permissions=False,
        allow_missing_permissions=False,
        verbose_bootstrap=False,
    )

    exit_code = cli.cmd_install_launch_agent(args)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Installed launch agent: /tmp/agent.plist" in captured.out


def test_cmd_doctor_prints_launch_agent_and_log_paths(monkeypatch, capsys) -> None:
    fake_transcriber_mod = ModuleType("moonshine_flow.transcriber")

    class FakeTranscriber:
        def __init__(self, model_size: str, language: str, device: str) -> None:
            self._summary = f"{model_size}:{language}:{device}"

        def backend_summary(self) -> str:
            return self._summary

    fake_transcriber_mod.MoonshineTranscriber = FakeTranscriber
    monkeypatch.setitem(sys.modules, "moonshine_flow.transcriber", fake_transcriber_mod)
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _: SimpleNamespace(
            model=SimpleNamespace(size=SimpleNamespace(value="base"), language="ja", device="mps")
        ),
    )
    monkeypatch.setattr(cli, "find_spec", lambda _: object())
    monkeypatch.setattr(
        cli,
        "check_all_permissions",
        lambda: PermissionReport(microphone=True, accessibility=True, input_monitoring=True),
    )
    monkeypatch.setattr(
        cli,
        "read_launch_agent_plist",
        lambda: {
            "Label": "com.moonshineflow.daemon",
            "ProgramArguments": ["/usr/bin/python3", "-m", "moonshine_flow.cli", "run"],
        },
    )
    monkeypatch.setattr(cli, "launch_agent_path", lambda: Path("/tmp/com.moonshineflow.daemon.plist"))
    monkeypatch.setattr(
        cli,
        "launch_agent_log_paths",
        lambda: (Path("/tmp/daemon.out.log"), Path("/tmp/daemon.err.log")),
    )

    exit_code = cli.cmd_doctor(argparse.Namespace(config=None))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LaunchAgent plist: FOUND (/tmp/com.moonshineflow.daemon.plist)" in captured.out
    assert "LaunchAgent program: /usr/bin/python3 -m moonshine_flow.cli run" in captured.out
    assert "Daemon stdout log: /tmp/daemon.out.log" in captured.out
    assert "Daemon stderr log: /tmp/daemon.err.log" in captured.out


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
