"""Homebrew runtime bootstrap with automatic runtime recovery.

This module is executed by the Homebrew wrapper script with the system
`python@3.11` interpreter. It chooses a healthy runtime and then execs
`moonshine_flow.cli`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


class RuntimeRepairError(RuntimeError):
    """Raised when runtime recovery fails."""


@dataclass(frozen=True)
class RuntimeCandidate:
    """Represents one virtual environment candidate."""

    name: str
    venv_dir: Path

    @property
    def python_path(self) -> Path:
        return self.venv_dir / "bin" / "python"

    def is_healthy(self) -> bool:
        python = self.python_path
        return python.exists() and os.access(python, os.X_OK)

    def cli_command(self, cli_args: Sequence[str]) -> list[str]:
        return [str(self.python_path), "-m", "moonshine_flow.cli", *cli_args]


class FingerprintProvider(Protocol):
    """Computes a build fingerprint for runtime compatibility."""

    def build(self) -> str:
        """Return runtime fingerprint text."""


class ProjectFingerprint:
    """Computes a deterministic fingerprint from project manifests."""

    _MANIFESTS = ("pyproject.toml", "uv.lock")

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir

    def build(self) -> str:
        digest = hashlib.sha256()
        for name in self._MANIFESTS:
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            manifest_path = self._project_dir / name
            if manifest_path.exists():
                digest.update(manifest_path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()


class RuntimeStateStore:
    """Persists the active runtime fingerprint."""

    def __init__(self, state_dir: Path) -> None:
        self._state_file = state_dir / "runtime-fingerprint.txt"

    def read(self) -> str | None:
        if not self._state_file.exists():
            return None
        return self._state_file.read_text(encoding="utf-8").strip() or None

    def write(self, value: str) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(f"{value}\n", encoding="utf-8")


class RuntimeBuilder:
    """Creates and syncs a runtime virtual environment."""

    def __init__(self, project_dir: Path, python_bin: Path, uv_bin: Path) -> None:
        self._project_dir = project_dir
        self._python_bin = python_bin
        self._uv_bin = uv_bin

    def rebuild(self, runtime: RuntimeCandidate) -> None:
        runtime.venv_dir.parent.mkdir(parents=True, exist_ok=True)
        if runtime.venv_dir.exists():
            shutil.rmtree(runtime.venv_dir)

        self._run([str(self._python_bin), "-m", "venv", str(runtime.venv_dir)])

        env = os.environ.copy()
        env["UV_PROJECT"] = str(self._project_dir)
        env["UV_PYTHON"] = str(self._python_bin)
        env["UV_PYTHON_DOWNLOADS"] = "never"
        env["VIRTUAL_ENV"] = str(runtime.venv_dir)
        env["PATH"] = f"{runtime.venv_dir / 'bin'}:{env.get('PATH', '')}"

        self._run(
            [
                str(self._uv_bin),
                "sync",
                "--project",
                str(self._project_dir),
                "--frozen",
                "--active",
            ],
            env=env,
        )

    def _run(self, command: Sequence[str], env: dict[str, str] | None = None) -> None:
        try:
            subprocess.run(command, env=env, check=True)
        except FileNotFoundError as exc:
            raise RuntimeRepairError(f"Required command is missing: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            cmd_text = " ".join(command)
            raise RuntimeRepairError(
                f"Command failed with exit code {exc.returncode}: {cmd_text}"
            ) from exc


class RuntimeManager:
    """Selects runtime and performs automatic recovery when needed."""

    def __init__(
        self,
        project_dir: Path,
        state_dir: Path,
        python_bin: Path,
        uv_bin: Path,
        *,
        builder: RuntimeBuilder | None = None,
        state_store: RuntimeStateStore | None = None,
        fingerprint: FingerprintProvider | None = None,
    ) -> None:
        self._primary = RuntimeCandidate("primary", project_dir / ".venv")
        self._recovery = RuntimeCandidate("recovery", state_dir / ".venv")
        self._builder = builder or RuntimeBuilder(project_dir, python_bin, uv_bin)
        self._state_store = state_store or RuntimeStateStore(state_dir)
        self._fingerprint = fingerprint or ProjectFingerprint(project_dir)

    def resolve_runtime(self) -> RuntimeCandidate:
        if self._primary.is_healthy():
            return self._primary

        expected = self._fingerprint.build()
        current = self._state_store.read()
        should_rebuild = not self._recovery.is_healthy() or current != expected
        if should_rebuild:
            self._emit_recovery_notice()
            self._builder.rebuild(self._recovery)
            self._state_store.write(expected)

        if self._recovery.is_healthy():
            return self._recovery

        raise RuntimeRepairError("No healthy runtime available after recovery")

    def launch(self, cli_args: Sequence[str]) -> None:
        runtime = self.resolve_runtime()
        command = runtime.cli_command(cli_args)
        os.execv(command[0], command)

    def _emit_recovery_notice(self) -> None:
        print(
            "moonshine-flow runtime is unavailable. Rebuilding runtime cache...",
            file=sys.stderr,
        )


def _parse_bootstrap_args(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--libexec", required=True)
    parser.add_argument("--var-dir", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--uv", required=True)
    options, cli_args = parser.parse_known_args(argv)
    if cli_args and cli_args[0] == "--":
        cli_args = cli_args[1:]
    return options, cli_args


def main(argv: Sequence[str] | None = None) -> int:
    options, cli_args = _parse_bootstrap_args(argv or sys.argv[1:])
    manager = RuntimeManager(
        project_dir=Path(options.libexec),
        state_dir=Path(options.var_dir),
        python_bin=Path(options.python),
        uv_bin=Path(options.uv),
    )
    try:
        manager.launch(cli_args)
    except RuntimeRepairError as exc:
        print(f"moonshine-flow runtime recovery failed: {exc}", file=sys.stderr)
        print("Try: brew reinstall moonshine-flow", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
