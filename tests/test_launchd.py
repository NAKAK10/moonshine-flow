from pathlib import Path
from types import SimpleNamespace

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


def test_restart_launch_agent_returns_false_when_plist_missing(monkeypatch) -> None:
    monkeypatch.setattr(launchd, "launch_agent_path", lambda: Path("/tmp/missing.plist"))

    assert launchd.restart_launch_agent() is False


def test_restart_launch_agent_uses_kickstart_when_available(monkeypatch, tmp_path: Path) -> None:
    plist = tmp_path / "com.moonshineflow.daemon.plist"
    plist.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(launchd, "launch_agent_path", lambda: plist)
    monkeypatch.setattr(
        launchd.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "501\n",
    )
    calls: list[tuple[str, ...]] = []

    def fake_launchctl(*args: str):
        calls.append(args)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(launchd, "_launchctl", fake_launchctl)

    assert launchd.restart_launch_agent() is True
    assert calls == [("kickstart", "-k", "gui/501/com.moonshineflow.daemon")]


def test_restart_launch_agent_falls_back_to_bootstrap(monkeypatch, tmp_path: Path) -> None:
    plist = tmp_path / "com.moonshineflow.daemon.plist"
    plist.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(launchd, "launch_agent_path", lambda: plist)
    monkeypatch.setattr(
        launchd.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "501\n",
    )
    calls: list[tuple[str, ...]] = []

    def fake_launchctl(*args: str):
        calls.append(args)
        if args[:2] == ("kickstart", "-k"):
            return SimpleNamespace(returncode=1, stderr="kickstart failed")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(launchd, "_launchctl", fake_launchctl)

    assert launchd.restart_launch_agent() is True
    assert calls == [
        ("kickstart", "-k", "gui/501/com.moonshineflow.daemon"),
        ("bootout", "gui/501", str(plist)),
        ("bootstrap", "gui/501", str(plist)),
    ]


def test_restart_launch_agent_raises_when_bootstrap_fails(monkeypatch, tmp_path: Path) -> None:
    plist = tmp_path / "com.moonshineflow.daemon.plist"
    plist.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(launchd, "launch_agent_path", lambda: plist)
    monkeypatch.setattr(
        launchd.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "501\n",
    )

    def fake_launchctl(*args: str):
        if args[:2] == ("kickstart", "-k"):
            return SimpleNamespace(returncode=1, stderr="kickstart failed")
        if args and args[0] == "bootstrap":
            return SimpleNamespace(returncode=1, stderr="bootstrap failed")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(launchd, "_launchctl", fake_launchctl)

    try:
        launchd.restart_launch_agent()
    except RuntimeError as exc:
        assert "launchctl restart failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
