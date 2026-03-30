from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import ptarmigan_flow.presentation.cli.commands as commands
from ptarmigan_flow.presentation.cli.parser import build_parser


def _set_homebrew_env(monkeypatch) -> None:
    monkeypatch.setenv(commands.ENV_BOOTSTRAP_SCRIPT, "/tmp/homebrew_bootstrap.py")
    monkeypatch.setenv(commands.ENV_LIBEXEC, "/tmp/libexec")
    monkeypatch.setenv(commands.ENV_VAR_DIR, "/tmp/var")
    monkeypatch.setenv(commands.ENV_PYTHON, "/tmp/python3.11")
    monkeypatch.setenv(commands.ENV_UV, "/tmp/uv")


def test_build_parser_registers_update_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["update"])

    assert args.func is commands.cmd_update


def test_cmd_update_rejects_non_homebrew_runtime(monkeypatch, capsys) -> None:
    for key in commands._HOMEBREW_RUNTIME_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    result = commands.cmd_update(argparse.Namespace())

    assert result == 2
    captured = capsys.readouterr()
    assert "Homebrew update is unavailable in this context" in captured.err


def test_cmd_update_requires_brew(monkeypatch, capsys) -> None:
    _set_homebrew_env(monkeypatch)
    monkeypatch.setattr(commands.shutil, "which", lambda _name: None)

    result = commands.cmd_update(argparse.Namespace())

    assert result == 2
    captured = capsys.readouterr()
    assert "Homebrew `brew` command is not available." in captured.err


def test_cmd_update_runs_brew_upgrade_when_no_launch_agent(monkeypatch) -> None:
    _set_homebrew_env(monkeypatch)
    monkeypatch.setattr(
        commands.shutil,
        "which",
        lambda name: "/opt/homebrew/bin/brew" if name == "brew" else "/opt/homebrew/bin/pflow",
    )
    monkeypatch.setattr(commands, "launch_agent_path", lambda: Path("/tmp/missing.plist"))
    calls: list[tuple[list[str], object | None]] = []

    def fake_run(command: list[str], check: bool, stdin=None):
        calls.append((command, stdin))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(commands.subprocess, "run", fake_run)

    result = commands.cmd_update(argparse.Namespace())

    assert result == 0
    assert calls == [(["/opt/homebrew/bin/brew", "upgrade", "ptarmigan-flow"], None)]


def test_cmd_update_refreshes_launch_agent_after_success(monkeypatch, tmp_path: Path) -> None:
    _set_homebrew_env(monkeypatch)
    plist_path = tmp_path / "com.ptarmiganflow.daemon.plist"
    plist_path.write_text("plist", encoding="utf-8")
    config_path = tmp_path / "custom.toml"
    monkeypatch.setattr(
        commands.shutil,
        "which",
        lambda name: {
            "brew": "/opt/homebrew/bin/brew",
            "pflow": "/opt/homebrew/bin/pflow",
        }.get(name),
    )
    monkeypatch.setattr(commands, "launch_agent_path", lambda: plist_path)
    monkeypatch.setattr(
        commands,
        "read_launch_agent_plist",
        lambda: {
            "ProgramArguments": [
                "/opt/homebrew/bin/pflow",
                "run",
                "--config",
                str(config_path),
            ]
        },
    )
    calls: list[tuple[list[str], object | None]] = []

    def fake_run(command: list[str], check: bool, stdin=None):
        calls.append((command, stdin))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(commands.subprocess, "run", fake_run)

    result = commands.cmd_update(argparse.Namespace())

    assert result == 0
    assert calls == [
        (["/opt/homebrew/bin/brew", "upgrade", "ptarmigan-flow"], None),
        (
            ["/opt/homebrew/bin/pflow", "_refresh-launch-agent-after-update"],
            subprocess.DEVNULL,
        ),
    ]


def test_cmd_update_propagates_brew_failure_without_refresh(monkeypatch, tmp_path: Path) -> None:
    _set_homebrew_env(monkeypatch)
    plist_path = tmp_path / "com.ptarmiganflow.daemon.plist"
    plist_path.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(
        commands.shutil,
        "which",
        lambda name: {
            "brew": "/opt/homebrew/bin/brew",
            "pflow": "/opt/homebrew/bin/pflow",
        }.get(name),
    )
    monkeypatch.setattr(commands, "launch_agent_path", lambda: plist_path)
    monkeypatch.setattr(commands, "read_launch_agent_plist", lambda: {"ProgramArguments": []})
    calls: list[tuple[list[str], object | None]] = []

    def fake_run(command: list[str], check: bool, stdin=None):
        calls.append((command, stdin))
        return subprocess.CompletedProcess(command, 5)

    monkeypatch.setattr(commands.subprocess, "run", fake_run)

    result = commands.cmd_update(argparse.Namespace())

    assert result == 5
    assert calls == [(["/opt/homebrew/bin/brew", "upgrade", "ptarmigan-flow"], None)]


def test_cmd_update_returns_2_when_launch_agent_refresh_fails(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    _set_homebrew_env(monkeypatch)
    plist_path = tmp_path / "com.ptarmiganflow.daemon.plist"
    plist_path.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(
        commands.shutil,
        "which",
        lambda name: {
            "brew": "/opt/homebrew/bin/brew",
            "pflow": "/opt/homebrew/bin/pflow",
        }.get(name),
    )
    monkeypatch.setattr(commands, "launch_agent_path", lambda: plist_path)
    monkeypatch.setattr(
        commands,
        "read_launch_agent_plist",
        lambda: {
            "ProgramArguments": [
                "/opt/homebrew/bin/pflow",
                "run",
                "--config",
                str(tmp_path / "config.toml"),
            ]
        },
    )
    calls: list[tuple[list[str], object | None]] = []

    def fake_run(command: list[str], check: bool, stdin=None):
        calls.append((command, stdin))
        return subprocess.CompletedProcess(command, 0 if len(calls) == 1 else 3)

    monkeypatch.setattr(commands.subprocess, "run", fake_run)

    result = commands.cmd_update(argparse.Namespace())

    assert result == 2
    captured = capsys.readouterr()
    assert "refreshing the installed launch agent failed" in captured.err


def test_cmd_refresh_launch_agent_after_update_preserves_launchd_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_homebrew_env(monkeypatch)
    config_path = tmp_path / "config.toml"
    plist_path = tmp_path / "com.ptarmiganflow.daemon.plist"
    monkeypatch.setattr(
        commands,
        "read_launch_agent_plist",
        lambda: {
            "ProgramArguments": [
                "/opt/homebrew/bin/pflow",
                "run",
                "--config",
                str(config_path),
            ],
            "EnvironmentVariables": {"PFLOW_LLM_ENABLED": "1"},
        },
    )
    monkeypatch.setattr(commands, "launch_agent_path", lambda: plist_path)
    monkeypatch.setattr(
        commands,
        "_install_or_update_app_bundle_for_refresh",
        lambda: (tmp_path / "PtarmiganFlow.app", False),
    )
    reset_calls: list[str] = []
    monkeypatch.setattr(
        commands,
        "reset_app_bundle_tcc",
        lambda identifier: reset_calls.append(identifier) or True,
    )
    install_calls: list[tuple[Path, bool | None]] = []
    monkeypatch.setattr(
        commands,
        "install_launch_agent",
        lambda path, llm_enabled_override=None: install_calls.append(
            (path, llm_enabled_override)
        )
        or plist_path,
    )

    result = commands.cmd_refresh_launch_agent_after_update(argparse.Namespace())

    assert result == 0
    assert install_calls == [(config_path, True)]
    assert reset_calls == []


def test_cmd_refresh_launch_agent_after_update_resets_tcc_when_bundle_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_homebrew_env(monkeypatch)
    plist_path = tmp_path / "com.ptarmiganflow.daemon.plist"
    monkeypatch.setattr(
        commands,
        "read_launch_agent_plist",
        lambda: {
            "ProgramArguments": [
                "/opt/homebrew/bin/pflow",
                "run",
                "--config",
                str(tmp_path / "config.toml"),
            ],
        },
    )
    monkeypatch.setattr(commands, "launch_agent_path", lambda: plist_path)
    monkeypatch.setattr(
        commands,
        "_install_or_update_app_bundle_for_refresh",
        lambda: (tmp_path / "PtarmiganFlow.app", True),
    )
    reset_calls: list[str] = []
    monkeypatch.setattr(
        commands,
        "reset_app_bundle_tcc",
        lambda identifier: reset_calls.append(identifier) or True,
    )
    monkeypatch.setattr(commands, "install_launch_agent", lambda path, llm_enabled_override=None: plist_path)

    result = commands.cmd_refresh_launch_agent_after_update(argparse.Namespace())

    assert result == 0
    assert reset_calls == [commands.APP_BUNDLE_IDENTIFIER]
