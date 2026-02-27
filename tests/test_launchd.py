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


def test_resolve_launch_agent_program_prefix_prefers_app_bundle_when_available(
    monkeypatch,
) -> None:
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

    prefix = launchd.resolve_launch_agent_program_prefix()

    assert prefix == [
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
    ]


def test_resolve_launch_agent_program_prefix_falls_back_to_mflow(monkeypatch) -> None:
    monkeypatch.setattr(launchd, "resolve_launch_agent_app_command", lambda: None)
    monkeypatch.setattr(
        launchd.shutil,
        "which",
        lambda name: "/usr/local/bin/mflow" if name == "mflow" else None,
    )

    prefix = launchd.resolve_launch_agent_program_prefix()

    assert prefix == ["/usr/local/bin/mflow"]


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
    marker_path = tmp_path / "restart-suppression.json"
    monkeypatch.setattr(launchd, "launch_agent_restart_suppression_path", lambda: marker_path)
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
    assert marker_path.exists()


def test_restart_launch_agent_falls_back_to_bootstrap(monkeypatch, tmp_path: Path) -> None:
    plist = tmp_path / "com.moonshineflow.daemon.plist"
    plist.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(launchd, "launch_agent_path", lambda: plist)
    marker_path = tmp_path / "restart-suppression.json"
    monkeypatch.setattr(launchd, "launch_agent_restart_suppression_path", lambda: marker_path)
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
    assert marker_path.exists()


def test_restart_launch_agent_raises_when_bootstrap_fails(monkeypatch, tmp_path: Path) -> None:
    plist = tmp_path / "com.moonshineflow.daemon.plist"
    plist.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(launchd, "launch_agent_path", lambda: plist)
    marker_path = tmp_path / "restart-suppression.json"
    monkeypatch.setattr(launchd, "launch_agent_restart_suppression_path", lambda: marker_path)
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
    assert not marker_path.exists()


def test_mark_restart_permission_suppression_writes_marker(monkeypatch, tmp_path: Path) -> None:
    marker_path = tmp_path / "restart-suppression.json"
    monkeypatch.setattr(launchd, "launch_agent_restart_suppression_path", lambda: marker_path)
    monkeypatch.setattr(launchd.time, "time", lambda: 100.0)

    launchd.mark_restart_permission_suppression(ttl_seconds=30)

    assert marker_path.exists()
    assert '"expires_at": 130.0' in marker_path.read_text(encoding="utf-8")


def test_consume_restart_permission_suppression_returns_true_and_removes_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "restart-suppression.json"
    marker_path.write_text('{"expires_at": 130}', encoding="utf-8")
    monkeypatch.setattr(launchd, "launch_agent_restart_suppression_path", lambda: marker_path)
    monkeypatch.setattr(launchd.time, "time", lambda: 120.0)

    assert launchd.consume_restart_permission_suppression() is True
    assert not marker_path.exists()


def test_consume_restart_permission_suppression_returns_false_when_expired(
    monkeypatch,
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "restart-suppression.json"
    marker_path.write_text('{"expires_at": 130}', encoding="utf-8")
    monkeypatch.setattr(launchd, "launch_agent_restart_suppression_path", lambda: marker_path)
    monkeypatch.setattr(launchd.time, "time", lambda: 131.0)

    assert launchd.consume_restart_permission_suppression() is False
    assert not marker_path.exists()
