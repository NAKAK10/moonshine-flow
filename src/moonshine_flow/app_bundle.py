"""Helpers for creating a local .app wrapper for daemon launches."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)

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


def _sha256_file(path: Path) -> str | None:
    """Return hex SHA-256 digest of a file, or None on error."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


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

    any_changed = False

    # --- executable: copy only when content differs ---
    source_resolved = source_python.resolve(strict=False)
    src_hash = _sha256_file(source_resolved)
    dst_hash = _sha256_file(executable_path) if executable_path.exists() else None
    if src_hash is None or src_hash != dst_hash:
        shutil.copy2(source_resolved, executable_path)
        executable_path.chmod(executable_path.stat().st_mode | 0o111)
        LOGGER.debug("app bundle: executable updated (%s)", executable_path)
        any_changed = True
    else:
        LOGGER.debug("app bundle: executable unchanged, skipping copy")

    # --- Info.plist: write only when content differs ---
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
    new_plist_bytes = plistlib.dumps(info_payload)
    existing_plist_bytes: bytes | None = None
    if info_plist_path.exists():
        try:
            existing_plist_bytes = info_plist_path.read_bytes()
        except OSError:
            pass
    if existing_plist_bytes != new_plist_bytes:
        info_plist_path.write_bytes(new_plist_bytes)
        LOGGER.debug("app bundle: Info.plist updated")
        any_changed = True
    else:
        LOGGER.debug("app bundle: Info.plist unchanged, skipping write")

    # --- bootstrap.json: write only when content differs ---
    metadata_path = resources_dir / "bootstrap.json"
    new_metadata = json.dumps(values, indent=2) + "\n"
    existing_metadata: str | None = None
    if metadata_path.exists():
        try:
            existing_metadata = metadata_path.read_text(encoding="utf-8")
        except OSError:
            pass
    if existing_metadata != new_metadata:
        metadata_path.write_text(new_metadata, encoding="utf-8")
        LOGGER.debug("app bundle: bootstrap.json updated")
        any_changed = True
    else:
        LOGGER.debug("app bundle: bootstrap.json unchanged, skipping write")

    # --- re-sign only when something actually changed ---
    if any_changed:
        LOGGER.debug("app bundle: re-signing after update")
        _resign_app_bundle(bundle_path)
    else:
        LOGGER.debug("app bundle: no changes detected, skipping re-sign")

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


def get_app_bundle_codesign_info(bundle_path: Path) -> dict[str, str] | None:
    """Return codesign metadata for *bundle_path*, or None when unavailable.

    Keys returned (when present): ``CDHash``, ``Identifier``, ``TeamIdentifier``,
    ``Signature Type``.  Values are raw strings from codesign output.
    """
    codesign = shutil.which("codesign")
    if not codesign:
        return None
    try:
        result = subprocess.run(
            [codesign, "--display", "--verbose=4", str(bundle_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    # codesign --display writes to stderr
    output = result.stderr or result.stdout
    if not output:
        return None

    info: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key in {"CDHash", "Identifier", "TeamIdentifier", "Signature Type"}:
                info[key] = value
        elif line.startswith("Signature="):
            info["Signature Type"] = line[len("Signature="):].strip()

    return info if info else None


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
