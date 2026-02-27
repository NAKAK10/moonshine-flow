from __future__ import annotations

from pathlib import Path

import moonshine_flow.homebrew_bootstrap as bootstrap
import pytest
from moonshine_flow.homebrew_bootstrap import (
    ProjectFingerprint,
    RuntimeCandidate,
    RuntimeBuilder,
    RuntimeManager,
    RuntimeProbeResult,
    RuntimeRepairError,
    RuntimeStateStore,
    Toolchain,
    _consume_verbose_bootstrap_flag,
    _parse_bootstrap_args,
)


class _FixedFingerprint:
    def __init__(self, value: str) -> None:
        self.value = value

    def build(self) -> str:
        return self.value


class _FakeBuilder:
    def __init__(self) -> None:
        self.calls = 0

    def rebuild(self, runtime: RuntimeCandidate) -> None:
        self.calls += 1
        python = runtime.python_path
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        python.chmod(0o755)


class _FakeProbe:
    def __init__(self, callback) -> None:
        self._callback = callback

    def probe(self, runtime: RuntimeCandidate) -> RuntimeProbeResult:
        return self._callback(runtime)


def _probe_from_executable(runtime: RuntimeCandidate) -> RuntimeProbeResult:
    ok = runtime.python_path.exists()
    return RuntimeProbeResult(ok=ok, python_arch=runtime.toolchain.arch)


def _write_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def _write_project_files(project_dir: Path) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (project_dir / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (project_dir / "README.md").write_text("# demo\n", encoding="utf-8")
    package_dir = project_dir / "src" / "moonshine_flow"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("__version__ = '0.0.0'\n", encoding="utf-8")
    (package_dir / "cli.py").write_text("def main() -> int:\n    return 0\n", encoding="utf-8")


def test_project_fingerprint_changes_with_lockfile(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (project_dir / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    fingerprint = ProjectFingerprint(project_dir)
    first = fingerprint.build()

    (project_dir / "uv.lock").write_text("version = 2\n", encoding="utf-8")
    second = fingerprint.build()

    assert first != second


def test_runtime_manager_accepts_none_toolchains_without_crash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    discovered = [Toolchain("discovered", tmp_path / "python3.11", tmp_path / "uv", "arm64")]
    monkeypatch.setattr(bootstrap, "_discover_toolchains", lambda **_: discovered)

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        toolchains=None,
        host_arch="arm64",
    )

    assert manager._toolchains == discovered


def test_runtime_manager_uses_discovered_toolchains_when_none(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    discovered = [Toolchain("discovered", tmp_path / "python3.11", tmp_path / "uv", "arm64")]
    monkeypatch.setattr(bootstrap, "_discover_toolchains", lambda **_: discovered)

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        toolchains=None,
        host_arch="arm64",
    )

    assert manager._toolchains[0].name == "discovered"
    assert manager._toolchains[0].arch == "arm64"


def test_detect_host_arch_prefers_arm64_on_rosetta(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.os, "uname", lambda: type("U", (), {"machine": "x86_64"})())
    monkeypatch.setattr(bootstrap.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(
        bootstrap.subprocess,
        "check_output",
        lambda *args, **kwargs: "1\n",
    )

    assert bootstrap._detect_host_arch() == "arm64"


def test_runtime_manager_falls_back_to_primary_when_toolchains_empty(tmp_path: Path) -> None:
    manager = RuntimeManager(
        project_dir=tmp_path / "libexec",
        state_dir=tmp_path / "var",
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        toolchains=[],
        host_arch="arm64",
    )

    assert len(manager._toolchains) == 1
    assert manager._toolchains[0].name == "primary"
    assert manager._toolchains[0].arch == "arm64"
    assert manager._toolchains[0].python_bin == tmp_path / "python3.11"
    assert manager._toolchains[0].uv_bin == tmp_path / "uv"


def test_runtime_manager_prefers_primary_arch_runtime(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    builder = _FakeBuilder()

    primary_python = project_dir / ".venv-arm64" / "bin" / "python"
    primary_python.parent.mkdir(parents=True, exist_ok=True)
    primary_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    primary_python.chmod(0o755)

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        builder=builder,
        fingerprint=_FixedFingerprint("abc"),
        runtime_probe=_FakeProbe(_probe_from_executable),
        toolchains=[Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64")],
        host_arch="arm64",
    )

    runtime = manager.resolve_runtime()
    assert runtime.name == "primary-arm64"
    assert runtime.venv_dir == project_dir / ".venv-arm64"
    assert builder.calls == 0


def test_runtime_manager_builds_recovery_runtime_when_primary_missing(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    builder = _FakeBuilder()

    _write_executable(tmp_path / "python3.11")
    _write_executable(tmp_path / "uv")

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        builder=builder,
        fingerprint=_FixedFingerprint("expected"),
        runtime_probe=_FakeProbe(_probe_from_executable),
        toolchains=[Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64")],
        host_arch="arm64",
    )

    runtime = manager.resolve_runtime()
    store = RuntimeStateStore(state_dir)

    assert runtime.name == "recovery-arm64"
    assert runtime.venv_dir == state_dir / ".venv-arm64"
    assert builder.calls == 1
    assert store.read(scope="arm64") == "expected|arch=arm64|python=" + str(
        tmp_path / "python3.11"
    ) + "|uv=" + str(tmp_path / "uv")


def test_runtime_manager_rebuilds_when_fingerprint_mismatch(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    builder = _FakeBuilder()
    store = RuntimeStateStore(state_dir)

    recovery_python = state_dir / ".venv-arm64" / "bin" / "python"
    recovery_python.parent.mkdir(parents=True, exist_ok=True)
    recovery_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    recovery_python.chmod(0o755)
    store.write("old", scope="arm64")

    _write_executable(tmp_path / "python3.11")
    _write_executable(tmp_path / "uv")

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        builder=builder,
        state_store=store,
        fingerprint=_FixedFingerprint("new"),
        runtime_probe=_FakeProbe(_probe_from_executable),
        toolchains=[Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64")],
        host_arch="arm64",
    )

    runtime = manager.resolve_runtime()

    assert runtime.name == "recovery-arm64"
    assert builder.calls == 1
    assert store.read(scope="arm64") == "new|arch=arm64|python=" + str(
        tmp_path / "python3.11"
    ) + "|uv=" + str(tmp_path / "uv")


def test_runtime_manager_falls_back_to_secondary_toolchain(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    builder = _FakeBuilder()

    primary_toolchain = Toolchain("primary", tmp_path / "python-x86", tmp_path / "uv-x86", "x86_64")
    fallback_toolchain = Toolchain("opt-homebrew", tmp_path / "python-arm", tmp_path / "uv-arm", "arm64")

    for tool in (primary_toolchain, fallback_toolchain):
        _write_executable(tool.python_bin)
        _write_executable(tool.uv_bin)

    def probe(runtime: RuntimeCandidate) -> RuntimeProbeResult:
        if runtime.toolchain.name == "primary":
            return RuntimeProbeResult(
                ok=False,
                python_arch="x86_64",
                lib_arches="arm64",
                error="incompatible architecture",
            )
        return _probe_from_executable(runtime)

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=primary_toolchain.python_bin,
        uv_bin=primary_toolchain.uv_bin,
        builder=builder,
        fingerprint=_FixedFingerprint("expected"),
        runtime_probe=_FakeProbe(probe),
        toolchains=[primary_toolchain, fallback_toolchain],
        host_arch="arm64",
    )

    runtime = manager.resolve_runtime()

    assert runtime.name == "recovery-arm64"
    assert runtime.toolchain.name == "opt-homebrew"
    assert builder.calls == 2


def test_runtime_builder_requires_metadata_files(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    _write_project_files(project_dir)
    (project_dir / "README.md").unlink()

    builder = RuntimeBuilder(project_dir)
    runtime = RuntimeCandidate(
        name="recovery-arm64",
        venv_dir=tmp_path / "var" / ".venv-arm64",
        toolchain=Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64"),
        scope="arm64",
    )

    with pytest.raises(RuntimeRepairError, match="README.md"):
        builder.rebuild(runtime)


def test_runtime_builder_restores_readme_from_prefix(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "opt" / "moonshine-flow" / "libexec"
    _write_project_files(project_dir)
    (project_dir / "README.md").unlink()
    (project_dir.parent / "README.md").write_text("# moonshine-flow\n", encoding="utf-8")

    builder = RuntimeBuilder(project_dir)
    commands: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run(command, env=None, quiet_on_success=False) -> None:
        commands.append((list(command), env))

    monkeypatch.setattr(builder, "_run", fake_run)

    runtime = RuntimeCandidate(
        name="recovery-arm64",
        venv_dir=tmp_path / "var" / ".venv-arm64",
        toolchain=Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64"),
        scope="arm64",
    )

    builder.rebuild(runtime)

    assert (project_dir / "README.md").is_file()
    assert (project_dir / "README.md").read_text(encoding="utf-8") == "# moonshine-flow\n"
    assert len(commands) == 2


def test_runtime_builder_rebuild_runs_when_metadata_present(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "libexec"
    _write_project_files(project_dir)

    builder = RuntimeBuilder(project_dir)
    commands: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run(command, env=None, quiet_on_success=False) -> None:
        commands.append((list(command), env))

    monkeypatch.setattr(builder, "_run", fake_run)

    runtime = RuntimeCandidate(
        name="recovery-arm64",
        venv_dir=tmp_path / "var" / ".venv-arm64",
        toolchain=Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64"),
        scope="arm64",
    )

    builder.rebuild(runtime)

    assert len(commands) == 2
    assert commands[0][0] == [str(tmp_path / "python3.11"), "-m", "venv", str(runtime.venv_dir)]
    assert commands[1][0][0] == str(tmp_path / "uv")
    assert commands[1][1] is not None
    assert commands[1][1]["UV_PROJECT"] == str(project_dir)


def test_runtime_builder_suppresses_sync_output_by_default(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "libexec"
    _write_project_files(project_dir)
    builder = RuntimeBuilder(project_dir)

    calls: list[dict[str, object]] = []

    def fake_subprocess_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        if kwargs.get("capture_output"):
            return type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_subprocess_run)

    _write_executable(tmp_path / "python3.11")
    _write_executable(tmp_path / "uv")
    runtime = RuntimeCandidate(
        name="recovery-arm64",
        venv_dir=tmp_path / "var" / ".venv-arm64",
        toolchain=Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64"),
        scope="arm64",
    )
    builder.rebuild(runtime)

    assert len(calls) == 2
    assert calls[0].get("capture_output") is None
    assert calls[1].get("capture_output") is True


def test_runtime_builder_sync_failure_includes_captured_output(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "libexec"
    _write_project_files(project_dir)
    builder = RuntimeBuilder(project_dir)

    def fake_subprocess_run(command, **kwargs):
        if kwargs.get("capture_output"):
            return type("P", (), {"returncode": 1, "stdout": "sync out", "stderr": "sync err"})()
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_subprocess_run)

    _write_executable(tmp_path / "python3.11")
    _write_executable(tmp_path / "uv")
    runtime = RuntimeCandidate(
        name="recovery-arm64",
        venv_dir=tmp_path / "var" / ".venv-arm64",
        toolchain=Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64"),
        scope="arm64",
    )

    with pytest.raises(RuntimeRepairError, match="sync out"):
        builder.rebuild(runtime)


def test_runtime_builder_verbose_mode_keeps_sync_output_unsuppressed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "libexec"
    _write_project_files(project_dir)
    builder = RuntimeBuilder(project_dir, verbose=True)

    calls: list[dict[str, object]] = []

    def fake_subprocess_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_subprocess_run)

    _write_executable(tmp_path / "python3.11")
    _write_executable(tmp_path / "uv")
    runtime = RuntimeCandidate(
        name="recovery-arm64",
        venv_dir=tmp_path / "var" / ".venv-arm64",
        toolchain=Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64"),
        scope="arm64",
    )
    builder.rebuild(runtime)

    assert len(calls) == 2
    assert calls[1].get("capture_output") is None


def test_parse_bootstrap_args_preserves_cli_options_after_separator() -> None:
    options, cli_args = _parse_bootstrap_args(
        [
            "--libexec",
            "/tmp/libexec",
            "--var-dir",
            "/tmp/var",
            "--python",
            "/tmp/python",
            "--uv",
            "/tmp/uv",
            "--",
            "--help",
        ]
    )

    assert options.libexec == "/tmp/libexec"
    assert cli_args == ["--help"]


def test_consume_verbose_bootstrap_flag() -> None:
    cli_args, verbose = _consume_verbose_bootstrap_flag(
        ["install-launch-agent", "--verbose-bootstrap", "--config", "/tmp/a.toml"]
    )
    assert verbose is True
    assert cli_args == ["install-launch-agent", "--config", "/tmp/a.toml"]


def test_is_version_query() -> None:
    assert bootstrap._is_version_query(["-v"]) is True
    assert bootstrap._is_version_query(["--version"]) is True
    assert bootstrap._is_version_query(["-v", "--version"]) is True
    assert bootstrap._is_version_query([]) is False
    assert bootstrap._is_version_query(["run"]) is False


def test_resolve_formula_version_from_project_dir_cellar_path(tmp_path: Path) -> None:
    project_dir = tmp_path / "Cellar" / "moonshine-flow" / "0.0.1-beta.8" / "libexec"
    project_dir.mkdir(parents=True, exist_ok=True)

    assert bootstrap._resolve_formula_version_from_project_dir(project_dir) == "0.0.1-beta.8"


def test_resolve_fast_version_prefers_libexec_venv_metadata(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "libexec"
    (project_dir / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    python_path = project_dir / ".venv" / "bin" / "python"
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)

    class _Process:
        returncode = 0
        stdout = "0.0.1b8\n"

    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: _Process())

    assert bootstrap._resolve_fast_version(project_dir) == "0.0.1b8"


def test_main_short_version_query_skips_runtime_manager(tmp_path: Path, monkeypatch, capsys) -> None:
    project_dir = tmp_path / "Cellar" / "moonshine-flow" / "0.0.3" / "libexec"
    project_dir.mkdir(parents=True, exist_ok=True)

    class _Process:
        returncode = 0
        stdout = "0.0.3\n"

    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: _Process())

    def fail_runtime_manager(*args, **kwargs):
        raise AssertionError("RuntimeManager should not be created for -v")

    monkeypatch.setattr(bootstrap, "RuntimeManager", fail_runtime_manager)

    exit_code = bootstrap.main(
        [
            "--libexec",
            str(project_dir),
            "--var-dir",
            str(tmp_path / "var"),
            "--python",
            str(tmp_path / "python"),
            "--uv",
            str(tmp_path / "uv"),
            "--",
            "-v",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "moonshine-flow 0.0.3"


def test_runtime_manager_launch_injects_project_src_into_pythonpath(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    _write_project_files(project_dir)

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        runtime_probe=_FakeProbe(_probe_from_executable),
        toolchains=[Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64")],
        host_arch="arm64",
    )

    runtime = RuntimeCandidate(
        name="recovery-arm64",
        venv_dir=state_dir / ".venv-arm64",
        toolchain=Toolchain("primary", tmp_path / "python3.11", tmp_path / "uv", "arm64"),
        scope="arm64",
    )
    monkeypatch.setattr(manager, "resolve_runtime", lambda: runtime)

    captured: dict[str, object] = {}

    def fake_execve(path: str, args: list[str], env: dict[str, str]) -> None:
        captured["path"] = path
        captured["args"] = args
        captured["env"] = env
        raise RuntimeError("exec-called")

    monkeypatch.setattr(bootstrap.os, "execve", fake_execve)

    with pytest.raises(RuntimeError, match="exec-called"):
        manager.launch(["--help"])

    assert captured["path"] == str(runtime.python_path)
    assert captured["args"] == [
        str(runtime.python_path),
        "-m",
        "moonshine_flow.cli",
        "--help",
    ]
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PYTHONPATH"] == str(project_dir / "src")
