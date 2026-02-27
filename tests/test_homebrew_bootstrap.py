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

    def fake_run(command, env=None) -> None:
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

    def fake_run(command, env=None) -> None:
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
