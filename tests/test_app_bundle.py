from __future__ import annotations

import os
import plistlib
from pathlib import Path

from moonshine_flow import app_bundle


def _write_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def test_launch_agent_prefix_from_env_returns_none_without_env(monkeypatch) -> None:
    for key in (
        app_bundle.ENV_BOOTSTRAP_SCRIPT,
        app_bundle.ENV_LIBEXEC,
        app_bundle.ENV_VAR_DIR,
        app_bundle.ENV_PYTHON,
        app_bundle.ENV_UV,
        app_bundle.ENV_DAEMON_PYTHON,
    ):
        monkeypatch.delenv(key, raising=False)

    prefix = app_bundle.launch_agent_prefix_from_env(executable_path=Path("/tmp/MoonshineFlow"))
    assert prefix is None


def test_install_app_bundle_from_env_creates_bundle(tmp_path: Path, monkeypatch) -> None:
    bootstrap_script = tmp_path / "libexec" / "src" / "moonshine_flow" / "homebrew_bootstrap.py"
    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_script.write_text("print('ok')\n", encoding="utf-8")
    python_bin = tmp_path / "python3.11"
    daemon_python = tmp_path / "MoonshineFlow"
    uv_bin = tmp_path / "uv"
    _write_executable(python_bin)
    _write_executable(daemon_python)
    _write_executable(uv_bin)

    monkeypatch.setenv(app_bundle.ENV_BOOTSTRAP_SCRIPT, str(bootstrap_script))
    monkeypatch.setenv(app_bundle.ENV_LIBEXEC, str(tmp_path / "libexec"))
    monkeypatch.setenv(app_bundle.ENV_VAR_DIR, str(tmp_path / "var"))
    monkeypatch.setenv(app_bundle.ENV_PYTHON, str(python_bin))
    monkeypatch.setenv(app_bundle.ENV_UV, str(uv_bin))
    monkeypatch.setenv(app_bundle.ENV_DAEMON_PYTHON, str(daemon_python))

    destination = tmp_path / "Applications" / app_bundle.APP_BUNDLE_NAME
    installed = app_bundle.install_app_bundle_from_env(destination)

    assert installed == destination
    executable = app_bundle.app_bundle_executable_path(destination)
    assert executable.exists()
    assert os.access(executable, os.X_OK)
    with (destination / "Contents" / "Info.plist").open("rb") as fp:
        payload = plistlib.load(fp)
    assert payload["CFBundleExecutable"] == app_bundle.APP_EXECUTABLE_NAME
    assert payload["CFBundleIdentifier"] == app_bundle.APP_BUNDLE_IDENTIFIER
    assert "NSMicrophoneUsageDescription" in payload


def test_resolve_launch_agent_app_command_uses_default_bundle_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bootstrap_script = tmp_path / "libexec" / "src" / "moonshine_flow" / "homebrew_bootstrap.py"
    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_script.write_text("print('ok')\n", encoding="utf-8")
    python_bin = tmp_path / "python3.11"
    uv_bin = tmp_path / "uv"
    _write_executable(python_bin)
    _write_executable(uv_bin)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(app_bundle.ENV_BOOTSTRAP_SCRIPT, str(bootstrap_script))
    monkeypatch.setenv(app_bundle.ENV_LIBEXEC, str(tmp_path / "libexec"))
    monkeypatch.setenv(app_bundle.ENV_VAR_DIR, str(tmp_path / "var"))
    monkeypatch.setenv(app_bundle.ENV_PYTHON, str(python_bin))
    monkeypatch.setenv(app_bundle.ENV_UV, str(uv_bin))
    monkeypatch.delenv(app_bundle.ENV_DAEMON_PYTHON, raising=False)

    command = app_bundle.resolve_launch_agent_app_command()

    assert command is not None
    assert command[0].endswith("/Applications/MoonshineFlow.app/Contents/MacOS/MoonshineFlow")
    assert command[1] == str(bootstrap_script)
    assert command[-1] == "--"
