"""Homebrew runtime bootstrap with automatic runtime recovery.

This module is executed by the Homebrew wrapper script with the system
`python@3.11` interpreter. It chooses a healthy runtime and then execs
`moonshine_flow.cli`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


class RuntimeRepairError(RuntimeError):
    """Raised when runtime recovery fails."""


@dataclass(frozen=True)
class Toolchain:
    """Represents one python/uv toolchain pair."""

    name: str
    python_bin: Path
    uv_bin: Path
    arch: str


@dataclass(frozen=True)
class RuntimeCandidate:
    """Represents one virtual environment candidate."""

    name: str
    venv_dir: Path
    toolchain: Toolchain
    scope: str

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


@dataclass(frozen=True)
class RuntimeProbeResult:
    """Result of probing one runtime candidate."""

    ok: bool
    python_arch: str | None = None
    lib_path: str | None = None
    lib_arches: str | None = None
    error: str | None = None
    stderr: str | None = None
    returncode: int | None = None


class RuntimeProbe(Protocol):
    """Runtime health probe contract."""

    def probe(self, runtime: RuntimeCandidate) -> RuntimeProbeResult:
        """Probe runtime for moonshine binary compatibility."""


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
        self._state_dir = state_dir

    def _state_file(self, scope: str | None = None) -> Path:
        if not scope:
            return self._state_dir / "runtime-fingerprint.txt"
        safe_scope = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in scope)
        return self._state_dir / f"runtime-fingerprint-{safe_scope}.txt"

    def read(self, scope: str | None = None) -> str | None:
        state_file = self._state_file(scope)
        if not state_file.exists():
            return None
        return state_file.read_text(encoding="utf-8").strip() or None

    def write(self, value: str, scope: str | None = None) -> None:
        state_file = self._state_file(scope)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(f"{value}\n", encoding="utf-8")


_PROBE_SCRIPT = textwrap.dedent(
    """
    import ctypes
    import json
    import platform
    import subprocess
    import sys
    from pathlib import Path

    def describe_arches(path: Path) -> str | None:
        path_text = str(path)
        for cmd in (
            ["/usr/bin/lipo", "-archs", path_text],
            ["/usr/bin/file", path_text],
        ):
            try:
                output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            except Exception:
                continue
            if output:
                return output
        return None

    result = {
        "ok": False,
        "python_arch": platform.machine(),
        "lib_path": None,
        "lib_arches": None,
        "error": None,
    }

    try:
        import moonshine_flow.cli  # noqa: F401
        import moonshine_voice

        package_path = Path(moonshine_voice.__file__).resolve()
        lib_path = package_path.with_name("libmoonshine.dylib")
        result["lib_path"] = str(lib_path)
        result["lib_arches"] = describe_arches(lib_path)
        ctypes.CDLL(str(lib_path))
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)

    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 2)
    """
)


class SubprocessRuntimeProbe:
    """Probes runtime by executing a compatibility script in that venv."""

    def __init__(self, script: str = _PROBE_SCRIPT, project_src_dir: Path | None = None) -> None:
        self._script = script
        self._project_src_dir = project_src_dir

    def probe(self, runtime: RuntimeCandidate) -> RuntimeProbeResult:
        python = runtime.python_path
        if not python.exists() or not os.access(python, os.X_OK):
            return RuntimeProbeResult(ok=False, error="runtime python is missing or not executable")

        env = os.environ.copy()
        if self._project_src_dir and self._project_src_dir.is_dir():
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                f"{self._project_src_dir}:{existing}" if existing else str(self._project_src_dir)
            )

        try:
            process = subprocess.run(
                [str(python), "-c", self._script],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        except OSError as exc:
            return RuntimeProbeResult(ok=False, error=f"failed to execute runtime python: {exc}")

        payload = _extract_probe_payload(process.stdout)
        if payload is None:
            if process.returncode == 0:
                return RuntimeProbeResult(ok=True, returncode=process.returncode)
            output_error = process.stdout.strip().splitlines()[-1] if process.stdout.strip() else None
            fallback_error = "runtime probe failed without JSON output"
            if output_error:
                fallback_error = f"{fallback_error}: {output_error}"
            return RuntimeProbeResult(
                ok=False,
                error=fallback_error,
                stderr=process.stderr.strip() or None,
                returncode=process.returncode,
            )

        error = _string_or_none(payload.get("error"))
        ok = bool(payload.get("ok")) and process.returncode == 0
        if not ok and not error:
            error = process.stderr.strip() or f"runtime probe failed (exit {process.returncode})"

        return RuntimeProbeResult(
            ok=ok,
            python_arch=_normalize_arch(_string_or_none(payload.get("python_arch"))),
            lib_path=_string_or_none(payload.get("lib_path")),
            lib_arches=_string_or_none(payload.get("lib_arches")),
            error=error,
            stderr=process.stderr.strip() or None,
            returncode=process.returncode,
        )


class RuntimeBuilder:
    """Creates and syncs a runtime virtual environment."""

    _REQUIRED_PROJECT_FILES = (
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "src/moonshine_flow/__init__.py",
        "src/moonshine_flow/cli.py",
    )

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir

    def rebuild(self, runtime: RuntimeCandidate) -> None:
        self._validate_project_layout()
        python_bin = runtime.toolchain.python_bin
        uv_bin = runtime.toolchain.uv_bin
        runtime.venv_dir.parent.mkdir(parents=True, exist_ok=True)
        if runtime.venv_dir.exists():
            shutil.rmtree(runtime.venv_dir)

        self._run([str(python_bin), "-m", "venv", str(runtime.venv_dir)])

        env = os.environ.copy()
        env["UV_PROJECT"] = str(self._project_dir)
        env["UV_PYTHON"] = str(python_bin)
        env["UV_PYTHON_DOWNLOADS"] = "never"
        env["VIRTUAL_ENV"] = str(runtime.venv_dir)
        env["PATH"] = f"{runtime.venv_dir / 'bin'}:{env.get('PATH', '')}"

        self._run(
            [
                str(uv_bin),
                "sync",
                "--project",
                str(self._project_dir),
                "--frozen",
                "--active",
            ],
            env=env,
        )

    def _validate_project_layout(self) -> None:
        self._restore_readme_if_needed()
        missing = [
            name for name in self._REQUIRED_PROJECT_FILES if not (self._project_dir / name).is_file()
        ]
        if not missing:
            return

        missing_text = ", ".join(missing)
        raise RuntimeRepairError(
            "Homebrew runtime project is incomplete: "
            f"missing {missing_text} under {self._project_dir}. "
            "Try: brew reinstall moonshine-flow"
        )

    def _restore_readme_if_needed(self) -> None:
        readme_path = self._project_dir / "README.md"
        if readme_path.is_file():
            return

        # Homebrew may relocate README.md to the formula prefix as a metafile.
        prefix_readme = self._project_dir.parent / "README.md"
        if not prefix_readme.is_file():
            return

        try:
            shutil.copyfile(prefix_readme, readme_path)
        except OSError as exc:
            raise RuntimeRepairError(
                "Failed to restore README.md into runtime project layout: "
                f"{exc}"
            ) from exc

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
        runtime_probe: RuntimeProbe | None = None,
        toolchains: Sequence[Toolchain] | None = None,
        host_arch: str | None = None,
    ) -> None:
        self._project_dir = project_dir
        self._state_dir = state_dir
        self._host_arch = _normalize_arch(host_arch or _detect_host_arch())
        self._builder = builder or RuntimeBuilder(project_dir)
        self._state_store = state_store or RuntimeStateStore(state_dir)
        self._fingerprint = fingerprint or ProjectFingerprint(project_dir)
        self._runtime_probe = runtime_probe or SubprocessRuntimeProbe(
            project_src_dir=project_dir / "src"
        )
        if toolchains is None:
            resolved_toolchains = _discover_toolchains(
                python_bin=python_bin,
                uv_bin=uv_bin,
                host_arch=self._host_arch,
            )
        else:
            resolved_toolchains = list(toolchains)
        if not resolved_toolchains:
            resolved_toolchains = [Toolchain("primary", python_bin, uv_bin, self._host_arch)]
        self._toolchains = resolved_toolchains

    def resolve_runtime(self) -> RuntimeCandidate:
        failures: list[str] = []
        for toolchain in self._toolchains:
            try:
                return self._resolve_for_toolchain(toolchain)
            except RuntimeRepairError as exc:
                failures.append(str(exc))

        if failures:
            detail = "\n".join(failures)
            raise RuntimeRepairError(f"No healthy runtime available after recovery.\n{detail}")
        raise RuntimeRepairError("No healthy runtime available after recovery")

    def launch(self, cli_args: Sequence[str]) -> None:
        runtime = self.resolve_runtime()
        command = runtime.cli_command(cli_args)
        env = os.environ.copy()
        project_src = self._project_dir / "src"
        if project_src.is_dir():
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{project_src}:{existing}" if existing else str(project_src)
        os.execve(command[0], command, env)

    def _resolve_for_toolchain(self, toolchain: Toolchain) -> RuntimeCandidate:
        primary = RuntimeCandidate(
            name=f"primary-{toolchain.arch}",
            venv_dir=self._project_dir / f".venv-{toolchain.arch}",
            toolchain=toolchain,
            scope=toolchain.arch,
        )
        legacy_primary = RuntimeCandidate(
            name=f"primary-legacy-{toolchain.arch}",
            venv_dir=self._project_dir / ".venv",
            toolchain=toolchain,
            scope=toolchain.arch,
        )
        recovery = RuntimeCandidate(
            name=f"recovery-{toolchain.arch}",
            venv_dir=self._state_dir / f".venv-{toolchain.arch}",
            toolchain=toolchain,
            scope=toolchain.arch,
        )

        probes: list[tuple[RuntimeCandidate, RuntimeProbeResult]] = []

        for candidate in (primary, legacy_primary):
            probe = self._runtime_probe.probe(candidate)
            probes.append((candidate, probe))
            if probe.ok:
                return candidate

        expected = self._runtime_fingerprint(toolchain)
        current = self._state_store.read(scope=recovery.scope)
        recovery_probe = self._runtime_probe.probe(recovery)
        probes.append((recovery, recovery_probe))
        should_rebuild = not recovery_probe.ok or current != expected
        if should_rebuild:
            self._ensure_toolchain(toolchain)
            self._emit_recovery_notice(toolchain, recovery_probe)
            self._builder.rebuild(recovery)
            self._state_store.write(expected, scope=recovery.scope)
            recovery_probe = self._runtime_probe.probe(recovery)
            probes[-1] = (recovery, recovery_probe)

        if recovery_probe.ok:
            return recovery

        raise RuntimeRepairError(self._format_probe_failure(toolchain, probes))

    def _runtime_fingerprint(self, toolchain: Toolchain) -> str:
        return (
            f"{self._fingerprint.build()}|arch={toolchain.arch}"
            f"|python={toolchain.python_bin}|uv={toolchain.uv_bin}"
        )

    @staticmethod
    def _ensure_toolchain(toolchain: Toolchain) -> None:
        for label, path in (("python", toolchain.python_bin), ("uv", toolchain.uv_bin)):
            if not path.exists():
                raise RuntimeRepairError(
                    f"Toolchain '{toolchain.name}' is missing {label}: {path}"
                )
            if not os.access(path, os.X_OK):
                raise RuntimeRepairError(
                    f"Toolchain '{toolchain.name}' has non-executable {label}: {path}"
                )

    def _emit_recovery_notice(
        self,
        toolchain: Toolchain,
        previous_probe: RuntimeProbeResult | None = None,
    ) -> None:
        detail = ""
        if previous_probe and previous_probe.error:
            detail = f" Last error: {previous_probe.error}"
        print(
            "moonshine-flow runtime is unavailable "
            f"(toolchain={toolchain.name}, arch={toolchain.arch}). "
            f"Rebuilding runtime cache...{detail}",
            file=sys.stderr,
        )

    def _format_probe_failure(
        self,
        toolchain: Toolchain,
        probes: Sequence[tuple[RuntimeCandidate, RuntimeProbeResult]],
    ) -> str:
        lines = [
            f"Toolchain '{toolchain.name}' failed "
            f"(arch={toolchain.arch}, python={toolchain.python_bin}, uv={toolchain.uv_bin})",
        ]
        for runtime, probe in probes:
            lines.append(f"- {runtime.name}: {self._summarize_probe(runtime, probe)}")
        if self._host_arch == "arm64" and toolchain.arch == "x86_64":
            lines.append(
                "- hint: Apple Silicon host is using an x86_64 runtime. "
                "Install arm64 python@3.11 and uv in /opt/homebrew."
            )
        return "\n".join(lines)

    @staticmethod
    def _summarize_probe(runtime: RuntimeCandidate, probe: RuntimeProbeResult) -> str:
        if probe.ok:
            return f"ok (python={runtime.python_path})"
        parts = [f"python={runtime.python_path}"]
        if probe.python_arch:
            parts.append(f"python_arch={probe.python_arch}")
        if probe.lib_arches:
            parts.append(f"lib_arches={probe.lib_arches}")
        if probe.lib_path:
            parts.append(f"lib={probe.lib_path}")
        if probe.error:
            parts.append(f"error={probe.error}")
        if probe.stderr and not probe.error:
            parts.append(f"stderr={probe.stderr}")
        if probe.returncode is not None:
            parts.append(f"exit={probe.returncode}")
        return "; ".join(parts)


def _extract_probe_payload(output: str) -> dict[str, object] | None:
    for line in reversed(output.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_arch(value: str | None) -> str:
    if not value:
        return "unknown"
    text = value.strip().lower()
    if text in {"arm64", "aarch64"}:
        return "arm64"
    if text in {"x86_64", "amd64"}:
        return "x86_64"
    if "arm64" in text and "x86_64" not in text:
        return "arm64"
    if "x86_64" in text and "arm64" not in text:
        return "x86_64"
    if "x86_64" in text and "arm64" in text:
        return "universal2"
    return text.replace(" ", "_")


def _describe_binary_arch(binary_path: Path) -> str | None:
    path_text = str(binary_path)
    for command in (
        ["/usr/bin/lipo", "-archs", path_text],
        ["/usr/bin/file", path_text],
    ):
        try:
            output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            continue
        if output:
            return output
    return None


def _detect_python_arch(python_bin: Path, default_arch: str) -> str:
    if python_bin.exists() and os.access(python_bin, os.X_OK):
        try:
            process = subprocess.run(
                [str(python_bin), "-c", "import platform; print(platform.machine())"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            process = None
        if process is not None and process.returncode == 0:
            detected = _normalize_arch(process.stdout.strip())
            if detected != "unknown":
                return detected

    described = _normalize_arch(_describe_binary_arch(python_bin))
    if described != "unknown":
        return described
    return default_arch


def _detect_host_arch() -> str:
    detected = _normalize_arch(os.uname().machine if hasattr(os, "uname") else platform.machine())
    if detected == "x86_64" and sys.platform == "darwin":
        try:
            arm64_capable = subprocess.check_output(
                ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            arm64_capable = ""
        if arm64_capable == "1":
            return "arm64"
    return detected


def _discover_toolchains(*, python_bin: Path, uv_bin: Path, host_arch: str) -> list[Toolchain]:
    toolchains: list[Toolchain] = []
    seen: set[tuple[Path, Path, str]] = set()

    def add_toolchain(name: str, python_path: Path, uv_path: Path) -> None:
        arch = _detect_python_arch(python_path, default_arch=host_arch)
        key = (python_path.resolve(strict=False), uv_path.resolve(strict=False), arch)
        if key in seen:
            return
        seen.add(key)
        toolchains.append(Toolchain(name=name, python_bin=python_path, uv_bin=uv_path, arch=arch))

    add_toolchain("primary", python_bin, uv_bin)

    if host_arch == "arm64":
        opt_python = Path("/opt/homebrew/opt/python@3.11/bin/python3.11")
        opt_uv = Path("/opt/homebrew/opt/uv/bin/uv")
        if opt_python.exists() and opt_uv.exists():
            add_toolchain("opt-homebrew", opt_python, opt_uv)

    return toolchains


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


def _is_version_query(cli_args: Sequence[str]) -> bool:
    if not cli_args:
        return False
    version_flags = {"-v", "--version"}
    return all(arg in version_flags for arg in cli_args)


def _resolve_formula_version_from_project_dir(project_dir: Path) -> str | None:
    parts = project_dir.resolve().parts
    for idx, part in enumerate(parts):
        if part != "Cellar":
            continue
        if idx + 2 >= len(parts):
            break
        if parts[idx + 1] != "moonshine-flow":
            continue
        candidate = parts[idx + 2].strip()
        if candidate:
            return candidate
        break
    return None


def _resolve_fast_version(project_dir: Path) -> str:
    venv_python = project_dir / ".venv" / "bin" / "python"
    if venv_python.exists() and os.access(venv_python, os.X_OK):
        try:
            process = subprocess.run(
                [
                    str(venv_python),
                    "-c",
                    "from importlib.metadata import version; print(version('moonshine-flow'))",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            process = None
        if process is not None and process.returncode == 0:
            resolved = process.stdout.strip()
            if resolved:
                return resolved

    fallback = _resolve_formula_version_from_project_dir(project_dir)
    if fallback:
        return fallback
    return "0.0.0.dev0"


def main(argv: Sequence[str] | None = None) -> int:
    options, cli_args = _parse_bootstrap_args(argv or sys.argv[1:])
    project_dir = Path(options.libexec)
    if _is_version_query(cli_args):
        print(f"moonshine-flow {_resolve_fast_version(project_dir)}")
        return 0

    manager = RuntimeManager(
        project_dir=project_dir,
        state_dir=Path(options.var_dir),
        python_bin=Path(options.python),
        uv_bin=Path(options.uv),
    )
    try:
        manager.launch(cli_args)
    except RuntimeRepairError as exc:
        print(f"moonshine-flow runtime recovery failed: {exc}", file=sys.stderr)
        print("Try: brew reinstall moonshine-flow", file=sys.stderr)
        print(
            "If this is an Apple Silicon machine using /usr/local Homebrew, "
            "install arm64 python@3.11 and uv under /opt/homebrew.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
