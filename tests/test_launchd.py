from pathlib import Path

from moonshine_flow import launchd


def test_build_launch_agent_prefers_app_bundle_command_when_available(monkeypatch) -> None:
    monkeypatch.setattr(
        launchd,
        "resolve_launch_agent_app_command",
        lambda: [
            "/tmp/Applications/MoonshineFlow.app/Contents/MacOS/MoonshineFlow",
            "/tmp/libexec/src/moonshine_flow/homebrew_bootstrap.py",
            "--libexec",
            "/tmp/libexec",
            "--var-dir",
            "/tmp/var/moonshine-flow",
            "--python",
            "/tmp/python3.11",
            "--uv",
            "/tmp/uv",
            "--",
        ],
    )

    payload = launchd.build_launch_agent(Path("/tmp/config.toml"))

    assert payload["ProgramArguments"] == [
        "/tmp/Applications/MoonshineFlow.app/Contents/MacOS/MoonshineFlow",
        "/tmp/libexec/src/moonshine_flow/homebrew_bootstrap.py",
        "--libexec",
        "/tmp/libexec",
        "--var-dir",
        "/tmp/var/moonshine-flow",
        "--python",
        "/tmp/python3.11",
        "--uv",
        "/tmp/uv",
        "--",
        "run",
        "--config",
        "/tmp/config.toml",
    ]


def test_build_launch_agent_prefers_mflow_command(monkeypatch) -> None:
    monkeypatch.setattr(launchd, "resolve_launch_agent_app_command", lambda: None)
    monkeypatch.setattr(
        launchd.shutil,
        "which",
        lambda name: "/usr/local/bin/mflow" if name == "mflow" else None,
    )

    payload = launchd.build_launch_agent(Path("/tmp/config.toml"))

    assert payload["ProcessType"] == "Interactive"
    assert payload["ProgramArguments"] == [
        "/usr/local/bin/mflow",
        "run",
        "--config",
        "/tmp/config.toml",
    ]


def test_build_launch_agent_uses_moonshine_flow_when_mflow_missing(monkeypatch) -> None:
    monkeypatch.setattr(launchd, "resolve_launch_agent_app_command", lambda: None)
    monkeypatch.setattr(
        launchd.shutil,
        "which",
        lambda name: "/usr/local/bin/moonshine-flow" if name == "moonshine-flow" else None,
    )

    payload = launchd.build_launch_agent(Path("/tmp/config.toml"))

    assert payload["ProgramArguments"] == [
        "/usr/local/bin/moonshine-flow",
        "run",
        "--config",
        "/tmp/config.toml",
    ]


def test_build_launch_agent_falls_back_to_python_module(monkeypatch) -> None:
    monkeypatch.setattr(launchd, "resolve_launch_agent_app_command", lambda: None)
    monkeypatch.setattr(launchd.shutil, "which", lambda _: None)
    monkeypatch.setattr(launchd.sys, "executable", "/opt/python/bin/python3.11", raising=False)

    payload = launchd.build_launch_agent(Path("/tmp/config.toml"))

    assert payload["ProgramArguments"] == [
        "/opt/python/bin/python3.11",
        "-m",
        "moonshine_flow.cli",
        "run",
        "--config",
        "/tmp/config.toml",
    ]
