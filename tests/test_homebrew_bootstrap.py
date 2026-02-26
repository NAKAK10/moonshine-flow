from __future__ import annotations

from pathlib import Path

from moonshine_flow.homebrew_bootstrap import (
    ProjectFingerprint,
    RuntimeCandidate,
    RuntimeManager,
    RuntimeStateStore,
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


def _write_python(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


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


def test_runtime_manager_prefers_primary_runtime(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    builder = _FakeBuilder()

    _write_python(project_dir / ".venv" / "bin" / "python")

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        builder=builder,
        fingerprint=_FixedFingerprint("abc"),
    )

    runtime = manager.resolve_runtime()
    assert runtime.name == "primary"
    assert builder.calls == 0


def test_runtime_manager_builds_recovery_runtime_when_primary_missing(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    builder = _FakeBuilder()

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        builder=builder,
        fingerprint=_FixedFingerprint("expected"),
    )

    runtime = manager.resolve_runtime()
    store = RuntimeStateStore(state_dir)

    assert runtime.name == "recovery"
    assert builder.calls == 1
    assert store.read() == "expected"


def test_runtime_manager_rebuilds_when_fingerprint_mismatch(tmp_path: Path) -> None:
    project_dir = tmp_path / "libexec"
    state_dir = tmp_path / "var"
    builder = _FakeBuilder()
    store = RuntimeStateStore(state_dir)

    recovery_python = state_dir / ".venv" / "bin" / "python"
    _write_python(recovery_python)
    store.write("old")

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=state_dir,
        python_bin=tmp_path / "python3.11",
        uv_bin=tmp_path / "uv",
        builder=builder,
        state_store=store,
        fingerprint=_FixedFingerprint("new"),
    )

    runtime = manager.resolve_runtime()

    assert runtime.name == "recovery"
    assert builder.calls == 1
    assert store.read() == "new"


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
