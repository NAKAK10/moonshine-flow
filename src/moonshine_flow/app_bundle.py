"""Helpers for creating a local .app wrapper for daemon launches."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

APP_BUNDLE_NAME = "MoonshineFlow.app"
APP_EXECUTABLE_NAME = "MoonshineFlow"
APP_BUNDLE_IDENTIFIER = "com.moonshineflow.app"

ENV_BOOTSTRAP_SCRIPT = "MOONSHINE_FLOW_BOOTSTRAP_SCRIPT"
ENV_LIBEXEC = "MOONSHINE_FLOW_LIBEXEC"
ENV_VAR_DIR = "MOONSHINE_FLOW_VAR_DIR"
ENV_PYTHON = "MOONSHINE_FLOW_PYTHON"
ENV_UV = "MOONSHINE_FLOW_UV"

_REQUIRED_ENV_KEYS = (
    ENV_BOOTSTRAP_SCRIPT,
    ENV_LIBEXEC,
    ENV_VAR_DIR,
    ENV_PYTHON,
    ENV_UV,
)


def default_app_bundle_path() -> Path:
    return Path("~/Applications").expanduser() / APP_BUNDLE_NAME


def app_bundle_executable_path(app_bundle_path: Path) -> Path:
    return app_bundle_path / "Contents" / "MacOS" / APP_EXECUTABLE_NAME


def _environment_values() -> dict[str, str] | None:
    values: dict[str, str] = {}
    for key in _REQUIRED_ENV_KEYS:
        raw = os.environ.get(key, "").strip()
        if not raw:
            return None
        values[key] = raw

    bootstrap_path = Path(values[ENV_BOOTSTRAP_SCRIPT]).expanduser()
    if not bootstrap_path.exists():
        return None

    return values


def launch_agent_prefix_from_env(*, executable_path: Path) -> list[str] | None:
    values = _environment_values()
    if values is None:
        return None

    return [
        str(executable_path),
        values[ENV_BOOTSTRAP_SCRIPT],
        "--libexec",
        values[ENV_LIBEXEC],
        "--var-dir",
        values[ENV_VAR_DIR],
        "--python",
        values[ENV_PYTHON],
        "--uv",
        values[ENV_UV],
        "--",
    ]


def install_app_bundle_from_env(app_bundle_path: Path | None = None) -> Path | None:
    values = _environment_values()
    if values is None:
        return None

    source_python = _resolve_real_python_binary(Path(values[ENV_PYTHON]).expanduser())
    if not source_python.exists():
        return None

    bundle_path = (app_bundle_path or default_app_bundle_path()).expanduser()
    executable_path = app_bundle_executable_path(bundle_path)
    resources_dir = bundle_path / "Contents" / "Resources"
    executable_path.parent.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_python.resolve(strict=False), executable_path)
    executable_path.chmod(executable_path.stat().st_mode | 0o111)

    info_plist_path = bundle_path / "Contents" / "Info.plist"
    info_payload = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": "MoonshineFlow",
        "CFBundleExecutable": APP_EXECUTABLE_NAME,
        "CFBundleIdentifier": APP_BUNDLE_IDENTIFIER,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "MoonshineFlow",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSBackgroundOnly": True,
        "NSMicrophoneUsageDescription": "MoonshineFlow records audio only while hotkey is held.",
    }
    with info_plist_path.open("wb") as fp:
        plistlib.dump(info_payload, fp)

    metadata_path = resources_dir / "bootstrap.json"
    metadata_path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    _resign_app_bundle(bundle_path)
    return bundle_path


def _resolve_real_python_binary(executable: Path) -> Path:
    resolved = executable.resolve(strict=False)
    marker = "/Frameworks/Python.framework/Versions/"
    text = str(resolved)
    if marker not in text:
        return resolved

    prefix, suffix = text.split(marker, 1)
    version = suffix.split("/", 1)[0].strip()
    if not version:
        return resolved

    candidate = (
        Path(prefix)
        / "Frameworks"
        / "Python.framework"
        / "Versions"
        / version
        / "Resources"
        / "Python.app"
        / "Contents"
        / "MacOS"
        / "Python"
    )
    if candidate.exists():
        return candidate
    return resolved


def resolve_launch_agent_app_command() -> list[str] | None:
    bundle_path = install_app_bundle_from_env()
    if bundle_path is None:
        return None
    return launch_agent_prefix_from_env(executable_path=app_bundle_executable_path(bundle_path))


def _resign_app_bundle(bundle_path: Path) -> None:
    codesign = shutil.which("codesign")
    if not codesign:
        return
    try:
        subprocess.run(
            [
                codesign,
                "--force",
                "--deep",
                "--sign",
                "-",
                "--identifier",
                APP_BUNDLE_IDENTIFIER,
                str(bundle_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return
