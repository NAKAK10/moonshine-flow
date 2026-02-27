import argparse
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from moonshine_flow import cli
from moonshine_flow.permissions import LaunchdPermissionProbe, PermissionReport


def test_cmd_run_requests_missing_permissions_in_launchd_context(monkeypatch) -> None:
    fake_daemon_mod = ModuleType("moonshine_flow.daemon")
    calls = {"mic": 0, "ax": 0, "im": 0, "stop": 0}
    permission_states = [
        PermissionReport(microphone=False, accessibility=False, input_monitoring=False),
        PermissionReport(microphone=True, accessibility=True, input_monitoring=True),
    ]

    class FakeDaemon:
        def __init__(self, _config) -> None:
            self.transcriber = SimpleNamespace(preflight_model=lambda: "moonshine-voice")

        def run_forever(self) -> None:
            raise KeyboardInterrupt

        def stop(self) -> None:
            calls["stop"] += 1

    fake_daemon_mod.MoonshineFlowDaemon = FakeDaemon
    monkeypatch.setitem(sys.modules, "moonshine_flow.daemon", fake_daemon_mod)
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _: SimpleNamespace(runtime=SimpleNamespace(log_level="INFO")),
    )
    monkeypatch.setattr(cli, "configure_logging", lambda _level: None)
    monkeypatch.setattr(cli, "_has_moonshine_backend", lambda: True)
    monkeypatch.setattr(cli, "check_all_permissions", lambda: permission_states.pop(0))
    monkeypatch.setattr(
        cli,
        "request_microphone_permission",
        lambda: calls.__setitem__("mic", calls["mic"] + 1) or True,
    )
    monkeypatch.setattr(
        cli,
        "request_accessibility_permission",
        lambda: calls.__setitem__("ax", calls["ax"] + 1) or True,
    )
    monkeypatch.setattr(
        cli,
        "request_input_monitoring_permission",
        lambda: calls.__setitem__("im", calls["im"] + 1) or True,
    )
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.moonshineflow.daemon")

    exit_code = cli.cmd_run(argparse.Namespace(config=None))

    assert exit_code == 0
    assert calls["mic"] == 1
    assert calls["ax"] == 1
    assert calls["im"] == 1
    assert calls["stop"] == 1


def test_cmd_run_skips_permission_requests_outside_launchd(monkeypatch) -> None:
    fake_daemon_mod = ModuleType("moonshine_flow.daemon")
    calls = {"requests": 0, "stop": 0}

    class FakeDaemon:
        def __init__(self, _config) -> None:
            self.transcriber = SimpleNamespace(preflight_model=lambda: "moonshine-voice")

        def run_forever(self) -> None:
            raise KeyboardInterrupt

        def stop(self) -> None:
            calls["stop"] += 1

    fake_daemon_mod.MoonshineFlowDaemon = FakeDaemon
    monkeypatch.setitem(sys.modules, "moonshine_flow.daemon", fake_daemon_mod)
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _: SimpleNamespace(runtime=SimpleNamespace(log_level="INFO")),
    )
    monkeypatch.setattr(cli, "configure_logging", lambda _level: None)
    monkeypatch.setattr(cli, "_has_moonshine_backend", lambda: True)
    monkeypatch.setattr(
        cli,
        "check_all_permissions",
        lambda: PermissionReport(microphone=False, accessibility=False, input_monitoring=False),
    )
    monkeypatch.setattr(
        cli,
        "request_microphone_permission",
        lambda: calls.__setitem__("requests", calls["requests"] + 1) or True,
    )
    monkeypatch.setattr(
        cli,
        "request_accessibility_permission",
        lambda: calls.__setitem__("requests", calls["requests"] + 1) or True,
    )
    monkeypatch.setattr(
        cli,
        "request_input_monitoring_permission",
        lambda: calls.__setitem__("requests", calls["requests"] + 1) or True,
    )
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)

    exit_code = cli.cmd_run(argparse.Namespace(config=None))

    assert exit_code == 0
    assert calls["requests"] == 0
    assert calls["stop"] == 1


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


def test_doctor_parser_has_launchd_check_flag() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["doctor", "--launchd-check"])
    assert args.launchd_check is True


def test_install_app_bundle_parser_has_path() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["install-app-bundle", "--path", "/tmp/MoonshineFlow.app"])
    assert args.path == "/tmp/MoonshineFlow.app"


def test_install_launch_agent_parser_defaults() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["install-launch-agent"])
    assert args.request_permissions is True
    assert args.allow_missing_permissions is False
    assert args.verbose_bootstrap is False
    assert args.install_app_bundle is True


def test_install_launch_agent_parser_allows_no_request_permissions() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["install-launch-agent", "--no-request-permissions"])
    assert args.request_permissions is False


def test_install_launch_agent_parser_allows_no_install_app_bundle() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["install-launch-agent", "--no-install-app-bundle"])
    assert args.install_app_bundle is False


def test_restart_launch_agent_parser() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["restart-launch-agent"])
    assert args.command == "restart-launch-agent"


def test_cmd_install_launch_agent_aborts_when_permissions_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(cli, "load_config", lambda _: object())
    monkeypatch.setattr(cli, "install_app_bundle_from_env", lambda _path=None: None)
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
        install_app_bundle=True,
    )

    exit_code = cli.cmd_install_launch_agent(args)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Launch agent installation was aborted" in captured.err
    assert "allow-missing-permissions" in captured.err


def test_cmd_install_launch_agent_allows_missing_permissions(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_resolve_config_path", lambda _: Path("/tmp/config.toml"))
    monkeypatch.setattr(cli, "load_config", lambda _: object())
    monkeypatch.setattr(cli, "install_app_bundle_from_env", lambda _path=None: None)
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
        install_app_bundle=True,
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
    monkeypatch.setattr(cli, "install_app_bundle_from_env", lambda _path=None: None)
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
        install_app_bundle=True,
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
    monkeypatch.setattr(cli, "recommended_permission_target", lambda: Path("/tmp/target.app"))

    exit_code = cli.cmd_doctor(argparse.Namespace(config=None, launchd_check=False))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LaunchAgent plist: FOUND (/tmp/com.moonshineflow.daemon.plist)" in captured.out
    assert "LaunchAgent program: /usr/bin/python3 -m moonshine_flow.cli run" in captured.out
    assert "Permission target (recommended): /tmp/target.app" in captured.out
    assert "Daemon stdout log: /tmp/daemon.out.log" in captured.out
    assert "Daemon stderr log: /tmp/daemon.err.log" in captured.out


def test_cmd_install_app_bundle_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "install_app_bundle_from_env", lambda _path: Path("/tmp/MoonshineFlow.app"))

    exit_code = cli.cmd_install_app_bundle(argparse.Namespace(path="/tmp/MoonshineFlow.app"))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Installed app bundle: /tmp/MoonshineFlow.app" in captured.out


def test_cmd_install_app_bundle_reports_unavailable_context(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "install_app_bundle_from_env", lambda _path: None)

    exit_code = cli.cmd_install_app_bundle(argparse.Namespace(path=None))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "App bundle install is unavailable in this context" in captured.err


def test_cmd_restart_launch_agent_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "restart_launch_agent", lambda: True)
    monkeypatch.setattr(cli, "launch_agent_path", lambda: Path("/tmp/com.moonshineflow.daemon.plist"))

    exit_code = cli.cmd_restart_launch_agent(argparse.Namespace())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Restarted launch agent: /tmp/com.moonshineflow.daemon.plist" in captured.out


def test_cmd_restart_launch_agent_reports_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "restart_launch_agent", lambda: False)

    exit_code = cli.cmd_restart_launch_agent(argparse.Namespace())

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Launch agent is not installed." in captured.out


def test_cmd_restart_launch_agent_reports_failure(monkeypatch, capsys) -> None:
    def raise_error() -> bool:
        raise RuntimeError("launchctl restart failed: denied")

    monkeypatch.setattr(cli, "restart_launch_agent", raise_error)

    exit_code = cli.cmd_restart_launch_agent(argparse.Namespace())

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "launchctl restart failed: denied" in captured.err


def test_latest_launchd_runtime_warning_detects_not_trusted(tmp_path: Path) -> None:
    err_log = tmp_path / "daemon.err.log"
    err_log.write_text(
        "\n".join(
            [
                "2026-02-27 10:00:00,000 INFO Moonshine Flow daemon starting",
                "2026-02-27 10:00:00,100 WARNING [pynput.keyboard.Listener] This process is not trusted!",
            ]
        ),
        encoding="utf-8",
    )

    warning = cli._latest_launchd_runtime_warning(err_log)
    assert warning is not None
    assert "not trusted" in warning


def test_cmd_doctor_prints_runtime_warning_from_daemon_log(monkeypatch, capsys, tmp_path: Path) -> None:
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
    out_log = tmp_path / "daemon.out.log"
    err_log = tmp_path / "daemon.err.log"
    err_log.write_text(
        "\n".join(
            [
                "2026-02-27 10:00:00,000 INFO [moonshine_flow.daemon] Moonshine Flow daemon starting",
                "2026-02-27 10:00:00,100 WARNING [pynput.keyboard.Listener] This process is not trusted!",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "launch_agent_log_paths", lambda: (out_log, err_log))
    monkeypatch.setattr(cli, "recommended_permission_target", lambda: Path("/tmp/target.app"))

    exit_code = cli.cmd_doctor(argparse.Namespace(config=None, launchd_check=False))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Launchd runtime status: WARNING" in captured.out
    assert "not trusted" in captured.out


def test_cmd_doctor_marks_permissions_incomplete_when_runtime_warning_present(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
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
    out_log = tmp_path / "daemon.out.log"
    err_log = tmp_path / "daemon.err.log"
    err_log.write_text(
        "\n".join(
            [
                "2026-02-27 10:00:00,000 INFO [moonshine_flow.daemon] Moonshine Flow daemon starting",
                "2026-02-27 10:00:00,100 WARNING [pynput.keyboard.Listener] This process is not trusted!",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "launch_agent_log_paths", lambda: (out_log, err_log))
    monkeypatch.setattr(cli, "recommended_permission_target", lambda: Path("/tmp/target.app"))
    monkeypatch.setattr(
        cli,
        "check_permissions_in_launchd_context",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("launchd check should not run")),
    )

    exit_code = cli.cmd_doctor(argparse.Namespace(config=None, launchd_check=False))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Terminal permissions: OK" in captured.out
    assert "Permissions: INCOMPLETE" in captured.out
    assert "Launchd runtime log indicates trust failure" in captured.out


def test_cmd_doctor_prints_install_hint_when_launch_agent_missing(monkeypatch, capsys) -> None:
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
    monkeypatch.setattr(cli, "read_launch_agent_plist", lambda: None)
    monkeypatch.setattr(cli, "launch_agent_path", lambda: Path("/tmp/com.moonshineflow.daemon.plist"))
    monkeypatch.setattr(
        cli,
        "launch_agent_log_paths",
        lambda: (Path("/tmp/daemon.out.log"), Path("/tmp/daemon.err.log")),
    )
    monkeypatch.setattr(cli, "recommended_permission_target", lambda: Path("/tmp/target.app"))

    exit_code = cli.cmd_doctor(argparse.Namespace(config=None, launchd_check=False))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LaunchAgent plist: MISSING (/tmp/com.moonshineflow.daemon.plist)" in captured.out
    assert "Install LaunchAgent: mflow install-launch-agent" in captured.out


def test_cmd_doctor_compares_launchd_permissions_when_enabled(monkeypatch, capsys) -> None:
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
    called: dict[str, list[str]] = {}

    def fake_launchd_check(*, command: list[str]) -> LaunchdPermissionProbe:
        called["command"] = command
        return LaunchdPermissionProbe(
            ok=True,
            report=PermissionReport(microphone=False, accessibility=True, input_monitoring=True),
        )

    monkeypatch.setattr(cli, "check_permissions_in_launchd_context", fake_launchd_check)

    exit_code = cli.cmd_doctor(argparse.Namespace(config=None, launchd_check=True))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert called["command"] == ["/usr/bin/python3", "-m", "moonshine_flow.cli", "check-permissions"]
    assert "Launchd permissions: INCOMPLETE" in captured.out
    assert "Launchd missing permissions: Microphone" in captured.out
    assert "Permission mismatch detected between terminal and launchd contexts" in captured.out


def test_cmd_doctor_reports_launchd_check_error(monkeypatch, capsys) -> None:
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
            "ProgramArguments": ["/usr/local/bin/mflow", "run", "--config", "/tmp/config.toml"],
        },
    )
    monkeypatch.setattr(cli, "launch_agent_path", lambda: Path("/tmp/com.moonshineflow.daemon.plist"))
    monkeypatch.setattr(
        cli,
        "launch_agent_log_paths",
        lambda: (Path("/tmp/daemon.out.log"), Path("/tmp/daemon.err.log")),
    )
    called: dict[str, list[str]] = {}

    def fake_launchd_check(*, command: list[str]) -> LaunchdPermissionProbe:
        called["command"] = command
        return LaunchdPermissionProbe(
            ok=False,
            error="Could not parse permission status from launchd check output (exit=1)",
            stderr="launchctl failed",
        )

    monkeypatch.setattr(cli, "check_permissions_in_launchd_context", fake_launchd_check)

    exit_code = cli.cmd_doctor(argparse.Namespace(config=None, launchd_check=True))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert called["command"] == ["/usr/local/bin/mflow", "check-permissions"]
    assert "Launchd permissions: ERROR" in captured.out
    assert "Launchd check error:" in captured.out
    assert "Launchd check stderr: launchctl failed" in captured.out


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
